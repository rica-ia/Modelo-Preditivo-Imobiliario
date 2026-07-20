import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.utils.validation import check_is_fitted

from .config import MODEL_FEATURES, TARGET


def _quartos_incompativeis_com_area(df: pd.DataFrame) -> pd.Series:
    area_por_quarto = df["sqft_living"].div(df["bedrooms"].replace(0, np.nan))
    return df["bedrooms"].gt(10) & area_por_quarto.lt(100)


def auditar_dados(df: pd.DataFrame) -> dict:
    contagem_id = df.groupby("id").size()
    ano_venda = pd.to_numeric(df["date"].astype(str).str[:4], errors="coerce")
    return {
        "linhas": int(len(df)),
        "colunas": int(df.shape[1]),
        "duplicatas_exatas": int(df.duplicated().sum()),
        "ids_com_revenda": int(contagem_id.gt(1).sum()),
        "registros_adicionais_de_revenda": int(df.duplicated("id").sum()),
        "ausentes": {k: int(v) for k, v in df.isna().sum().items() if v},
        "quartos_incompativeis_com_area": int(_quartos_incompativeis_com_area(df).sum()),
        "vendas_antes_do_ano_de_construcao": int(df["yr_built"].gt(ano_venda).sum()),
    }


def limpar_dados(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    dados = df.drop_duplicates().copy()
    dados["date"] = pd.to_datetime(dados["date"], format="%Y%m%dT%H%M%S")

    mediana_sqft_above = float(dados["sqft_above"].median())
    nulos_imputados = int(dados["sqft_above"].isna().sum())
    dados["sqft_above"] = dados["sqft_above"].fillna(mediana_sqft_above)

    anomalia = _quartos_incompativeis_com_area(dados)
    comparaveis = dados.loc[
        ~anomalia
        & dados["sqft_living"].between(1_400, 1_800)
        & dados["bathrooms"].between(1.5, 2.0),
        "bedrooms",
    ]
    quartos_substitutos = float(comparaveis.median()) if len(comparaveis) else 3.0
    dados.loc[anomalia, "bedrooms"] = quartos_substitutos

    relatorio = {
        "duplicatas_removidas": int(len(df) - len(dados)),
        "nulos_sqft_above_imputados": nulos_imputados,
        "mediana_sqft_above": mediana_sqft_above,
        "anomalias_bedrooms_corrigidas": int(anomalia.sum()),
        "imoveis_comparaveis": int(len(comparaveis)),
        "mediana_quartos_comparaveis": quartos_substitutos,
    }
    return dados, relatorio


def criar_features(df: pd.DataFrame) -> pd.DataFrame:
    dados = df.copy()
    ano_venda = dados["date"].dt.year
    idade_imovel = (ano_venda - dados["yr_built"]).clip(lower=0)
    area_m2 = dados["sqft_living"] * 0.092903
    dados = dados.assign(
        ano_venda=ano_venda,
        mes_venda=dados["date"].dt.month,
        idade_imovel=idade_imovel,
        foi_reformado=dados["yr_renovated"].gt(0).astype("int8"),
        tem_porao=dados["sqft_basement"].gt(0).astype("int8"),
        log_sqft_lot=np.log1p(dados["sqft_lot"]),
        log_sqft_lot15=np.log1p(dados["sqft_lot15"]),
        area_m2=area_m2,
    )
    if TARGET in dados:
        dados["preco_por_m2"] = dados[TARGET] / area_m2
    return dados


def calcular_vif(df: pd.DataFrame, colunas: list[str]) -> pd.DataFrame:
    matriz = SimpleImputer(strategy="median").fit_transform(df[colunas])
    valores = []
    for indice, coluna in enumerate(colunas):
        demais = np.delete(matriz, indice, axis=1)
        r2 = LinearRegression().fit(demais, matriz[:, indice]).score(demais, matriz[:, indice])
        valores.append({"variavel": coluna, "VIF": 1 / max(1 - r2, 1e-12)})
    return pd.DataFrame(valores).sort_values("VIF", ascending=False, ignore_index=True)


def comparar_correlacoes(df: pd.DataFrame, colunas: list[str]) -> pd.DataFrame:
    base = df[colunas + [TARGET]]
    resultado = pd.DataFrame(
        {
            "Pearson": base.corr(method="pearson")[TARGET].drop(TARGET),
            "Spearman": base.corr(method="spearman")[TARGET].drop(TARGET),
        }
    )
    resultado["diferenca_absoluta"] = resultado["Spearman"].abs() - resultado["Pearson"].abs()
    return resultado.sort_values("Spearman", key=lambda s: s.abs(), ascending=False)


def preparar_preditores(df: pd.DataFrame) -> pd.DataFrame:
    X = df[MODEL_FEATURES].copy()
    X["zipcode"] = X["zipcode"].astype(str)
    return X


class RawFeatureTransformer(TransformerMixin, BaseEstimator):
    """Converte registros brutos nas variáveis esperadas pelo preprocessador."""

    def __init__(self, feature_names=tuple(MODEL_FEATURES)):
        self.feature_names = feature_names

    @staticmethod
    def _normalizar_data(df: pd.DataFrame) -> pd.DataFrame:
        dados = df.copy()
        if "date" not in dados:
            raise ValueError("A coluna bruta 'date' é obrigatória para a inferência.")
        if not pd.api.types.is_datetime64_any_dtype(dados["date"]):
            dados["date"] = pd.to_datetime(
                dados["date"].astype(str), format="%Y%m%dT%H%M%S", errors="raise"
            )
        return dados

    def fit(self, X: pd.DataFrame, y=None):
        dados = self._normalizar_data(X)
        anomalia = _quartos_incompativeis_com_area(dados)
        comparaveis = dados.loc[
            ~anomalia
            & dados["sqft_living"].between(1_400, 1_800)
            & dados["bathrooms"].between(1.5, 2.0),
            "bedrooms",
        ]
        self.quartos_substitutos_ = float(comparaveis.median()) if len(comparaveis) else 3.0
        self.feature_names_in_ = np.asarray(dados.columns, dtype=object)
        self.n_features_in_ = len(self.feature_names_in_)
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        check_is_fitted(self, ["quartos_substitutos_", "feature_names_in_"])
        dados = self._normalizar_data(X)
        anomalia = _quartos_incompativeis_com_area(dados)
        dados.loc[anomalia, "bedrooms"] = self.quartos_substitutos_
        return preparar_preditores(criar_features(dados)).loc[:, list(self.feature_names)]

    def get_feature_names_out(self, input_features=None):
        check_is_fitted(self, "feature_names_in_")
        return np.asarray(self.feature_names, dtype=object)


def separar_xy_grupos(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    return preparar_preditores(df), df[TARGET].copy(), df["id"].copy()


def separar_brutos_alvo_grupos(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    return df.drop(columns=[TARGET, "id"]).copy(), df[TARGET].copy(), df["id"].copy()
