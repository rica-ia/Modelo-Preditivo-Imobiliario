import json
from collections import OrderedDict
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression
from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import GroupKFold, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.utils.validation import check_is_fitted

from .features import RawFeatureTransformer


class LogSmearingRegressor(RegressorMixin, BaseEstimator):
    """Regressão em log com correção de retransformação aprendida no treino."""

    def __init__(self, regressor):
        self.regressor = regressor

    def fit(self, X, y):
        y = np.asarray(y)
        if np.any(y < 0):
            raise ValueError("O alvo deve ser não negativo para a transformação log1p.")
        y_log = np.log1p(y)
        self.regressor_ = clone(self.regressor).fit(X, y_log)
        residuos_log = y_log - self.regressor_.predict(X)
        self.smearing_factor_ = float(np.mean(np.exp(residuos_log)))
        return self

    def predict(self, X):
        check_is_fitted(self, ["regressor_", "smearing_factor_"])
        previsao = np.exp(self.regressor_.predict(X)) * self.smearing_factor_ - 1
        return np.maximum(previsao, 0)


def construir_preprocessador(numericas: list[str], categoricas: list[str]) -> ColumnTransformer:
    numerico = Pipeline(
        [("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]
    )
    try:
        categorico = OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        categorico = OneHotEncoder(handle_unknown="ignore", sparse=False)
    return ColumnTransformer([("num", numerico, numericas), ("cat", categorico, categoricas)])


def _hgb(random_state: int) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        max_iter=500,
        learning_rate=0.06,
        max_leaf_nodes=15,
        min_samples_leaf=30,
        l2_regularization=5.0,
        early_stopping=True,
        random_state=random_state,
    )


def modelos_candidatos(random_state: int = 42) -> OrderedDict:
    return OrderedDict(
        {
            "Baseline pela média": DummyRegressor(strategy="mean"),
            "Regressão Linear": LinearRegression(),
            "HistGradientBoosting": _hgb(random_state),
            "HistGradientBoosting Log": LogSmearingRegressor(_hgb(random_state)),
        }
    )


def criar_pipeline(preprocessador, modelo) -> Pipeline:
    return Pipeline(
        [
            ("engenharia_atributos", RawFeatureTransformer()),
            ("preprocessador", clone(preprocessador)),
            ("modelo", clone(modelo)),
        ]
    )


def calcular_metricas(y_true, y_pred) -> dict:
    mse = mean_squared_error(y_true, y_pred)
    return {
        "MAE": mean_absolute_error(y_true, y_pred),
        "MSE": mse,
        "RMSE": np.sqrt(mse),
        "R2": r2_score(y_true, y_pred),
        "MAPE": mean_absolute_percentage_error(y_true, y_pred),
    }


def validar_candidatos(
    modelos, preprocessador, X, y, grupos, folds=5, random_state=42, n_jobs=1
):
    try:
        cv = GroupKFold(n_splits=folds, shuffle=True, random_state=random_state)
    except TypeError:
        cv = GroupKFold(n_splits=folds)
    linhas = []
    scoring = {
        "mae": "neg_mean_absolute_error",
        "mse": "neg_mean_squared_error",
        "r2": "r2",
        "mape": "neg_mean_absolute_percentage_error",
    }
    for nome, modelo in modelos.items():
        scores = cross_validate(
            criar_pipeline(preprocessador, modelo),
            X,
            y,
            groups=grupos,
            cv=cv,
            scoring=scoring,
            n_jobs=n_jobs,
        )
        for fold in range(folds):
            linhas.append(
                {
                    "modelo": nome,
                    "fold": fold + 1,
                    "MAE": -scores["test_mae"][fold],
                    "RMSE": np.sqrt(-scores["test_mse"][fold]),
                    "R2": scores["test_r2"][fold],
                    "MAPE": -scores["test_mape"][fold],
                }
            )
    por_fold = pd.DataFrame(linhas)
    resumo = (
        por_fold.groupby("modelo", sort=False)
        .agg(
            MAE_medio=("MAE", "mean"),
            MAE_desvio=("MAE", "std"),
            RMSE_medio=("RMSE", "mean"),
            RMSE_desvio=("RMSE", "std"),
            R2_medio=("R2", "mean"),
            R2_desvio=("R2", "std"),
            MAPE_medio=("MAPE", "mean"),
            MAPE_desvio=("MAPE", "std"),
        )
        .reset_index()
    )
    return por_fold, resumo.sort_values("RMSE_medio", ignore_index=True)


def avaliar_holdout(modelos, preprocessador, X_train, X_test, y_train, y_test):
    ajustados, linhas = {}, []
    for nome, modelo in modelos.items():
        pipeline = criar_pipeline(preprocessador, modelo).fit(X_train, y_train)
        ajustados[nome] = pipeline
        for conjunto, X, y in [("Treino", X_train, y_train), ("Teste", X_test, y_test)]:
            linhas.append(
                {"modelo": nome, "conjunto": conjunto, **calcular_metricas(y, pipeline.predict(X))}
            )
    return ajustados, pd.DataFrame(linhas)


def diagnosticar_generalizacao(resultados: pd.DataFrame) -> pd.DataFrame:
    linhas = []
    for modelo, grupo in resultados.groupby("modelo", sort=False):
        tabela = grupo.set_index("conjunto")
        linhas.append(
            {
                "modelo": modelo,
                "delta_R2": tabela.loc["Treino", "R2"] - tabela.loc["Teste", "R2"],
                "razao_RMSE_teste_treino": tabela.loc["Teste", "RMSE"] / tabela.loc["Treino", "RMSE"],
                "razao_MAE_teste_treino": tabela.loc["Teste", "MAE"] / tabela.loc["Treino", "MAE"],
            }
        )
    return pd.DataFrame(linhas)


def erros_por_faixa(y_true, y_pred) -> pd.DataFrame:
    dados = pd.DataFrame({"real": np.asarray(y_true), "previsto": np.asarray(y_pred)})
    dados["erro_absoluto"] = (dados["real"] - dados["previsto"]).abs()
    dados["erro_percentual"] = dados["erro_absoluto"] / dados["real"]
    dados["faixa_preco"] = pd.qcut(
        dados["real"], 4, labels=["Q1 — menor preço", "Q2", "Q3", "Q4 — maior preço"]
    )
    return (
        dados.groupby("faixa_preco", observed=True)
        .agg(
            registros=("real", "size"),
            preco_mediano=("real", "median"),
            MAE=("erro_absoluto", "mean"),
            MAPE=("erro_percentual", "mean"),
            MdAPE=("erro_percentual", "median"),
            erro_absoluto_p90=("erro_absoluto", lambda s: s.quantile(0.90)),
        )
        .reset_index()
    )


def salvar_versao_modelo(pipeline, metricas: dict, modelo_path, metricas_path) -> None:
    modelo_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipeline, modelo_path, compress=3)
    payload = {"treinado_em_utc": datetime.now(timezone.utc).isoformat(), **metricas}
    metricas_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
