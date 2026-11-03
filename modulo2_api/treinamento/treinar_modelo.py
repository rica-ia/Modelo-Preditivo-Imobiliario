"""
# Módulo 2 · Fase 1 — Preparação e serialização do modelo (pipeline offline)

Este script reaproveita o pipeline do Módulo 1 (pasta `src/`) e gera o artefato
que a API do Módulo 2 carrega na inicialização.

## Decisões técnicas
- **Reaproveitamento (Opção A do projeto):** limpeza, engenharia de atributos e o
  regressor com alvo em log vêm do Módulo 1, que já foi validado.
- **Divisão treino / validação / teste (60/20/20) agrupada por `id`:** um mesmo
  imóvel pode ter sido revendido; agrupar pelo `id` impede que a mesma casa
  apareça em dois conjuntos (vazamento de dados).
- **Seleção na validação, nota final no teste:** os candidatos são comparados no
  conjunto de validação; o teste só é usado uma vez, no modelo escolhido.
- **Pré-processamento dentro do Pipeline:** imputação pela mediana, one-hot do CEP
  e escalonamento ficam no próprio artefato, então a API recebe dados brutos e
  aplica exatamente o mesmo tratamento do treino.
- **Faixa provável:** quantis 10 % e 90 % da razão real/previsto na validação.
- **Coerência comercial (restrições monotônicas):** sem restrição, o boosting
  pode aprender oscilações locais, por exemplo "padrão construtivo +1" baixar o
  preço em um CEP. O candidato "HistGradientBoosting Log monotônico" obriga o
  preço a nunca cair quando sobem área útil, padrão, vista, condição, frente para
  a água, banheiros, área dos vizinhos ou quando o imóvel foi reformado. Ele é
  adotado se perder no máximo 0,01 de R² na validação para o modelo sem restrição.

Execução, a partir da raiz do repositório:
    python -m modulo2_api.treinamento.treinar_modelo
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.inspection import permutation_importance
from sklearn.model_selection import GroupShuffleSplit

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from src.config import CATEGORICAL_FEATURES, NUMERIC_FEATURES, RANDOM_STATE  # noqa: E402
from src.features import limpar_dados, separar_brutos_alvo_grupos  # noqa: E402
from src.modeling import (  # noqa: E402
    LogSmearingRegressor,
    _hgb,
    calcular_metricas,
    construir_preprocessador,
    criar_pipeline,
    modelos_candidatos,
)

# ## Caminhos relativos ao repositório (nada de caminho absoluto da máquina)
DADOS_BRUTOS = RAIZ / "data" / "raw" / "kc_house_data.csv"
PASTA_MODELOS = RAIZ / "modulo2_api" / "models"
ARQUIVO_MODELO = PASTA_MODELOS / "modelo_imobiliario_v2.joblib"
ARQUIVO_METRICAS = PASTA_MODELOS / "metricas_v2.json"
ARQUIVO_REGIOES = PASTA_MODELOS / "regioes_v2.json"

M2_POR_SQFT = 0.092903

# Nomes amigáveis das colunas brutas, usados no painel de importância
ROTULOS = {
    "bedrooms": "Quartos",
    "bathrooms": "Banheiros",
    "sqft_living": "Área útil",
    "sqft_lot": "Área do terreno",
    "floors": "Andares",
    "waterfront": "Frente para a água",
    "view": "Vista",
    "condition": "Condição",
    "grade": "Padrão construtivo",
    "sqft_basement": "Área do porão",
    "yr_built": "Ano de construção",
    "yr_renovated": "Ano da reforma",
    "zipcode": "CEP",
    "lat": "Latitude",
    "long": "Longitude",
    "sqft_living15": "Área útil dos vizinhos",
    "sqft_lot15": "Terreno dos vizinhos",
    "date": "Data da venda",
}


SEM_RESTRICAO = "HistGradientBoosting Log"
MONOTONICO = "HistGradientBoosting Log monotônico"
PERDA_MAXIMA_R2 = 0.01

# Atributos em que o preço só pode subir (ou ficar igual) quando o valor sobe.
# Os nomes seguem a saída do ColumnTransformer em pandas ("num__<coluna>");
# os demais atributos, inclusive o one-hot do CEP, ficam sem restrição.
CRESCENTES = [
    "sqft_living",
    "grade",
    "view",
    "condition",
    "waterfront",
    "bathrooms",
    "sqft_living15",
    "foi_reformado",
]


def candidatos() -> dict:
    """Candidatos do Módulo 1 + o HGB em log com restrições monotônicas."""
    modelos = dict(modelos_candidatos(RANDOM_STATE))
    restricoes = {f"num__{coluna}": 1 for coluna in CRESCENTES}
    modelos[MONOTONICO] = LogSmearingRegressor(_hgb(RANDOM_STATE).set_params(monotonic_cst=restricoes))
    return modelos


def _arredondar(metricas: dict) -> dict:
    return {nome: round(float(valor), 4) for nome, valor in metricas.items()}


# ## Etapa 1 — Carga e limpeza (mesmas regras do Módulo 1)
def carregar_base() -> pd.DataFrame:
    bruto = pd.read_csv(DADOS_BRUTOS)
    limpo, _ = limpar_dados(bruto)
    return limpo


# ## Etapa 2 — Divisão agrupada em treino, validação e teste
def dividir(df: pd.DataFrame):
    X, y, grupos = separar_brutos_alvo_grupos(df)
    corte_teste = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=RANDOM_STATE)
    idx_resto, idx_teste = next(corte_teste.split(X, y, grupos))
    # 25 % dos 80 % restantes = 20 % do total para validação
    corte_val = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=RANDOM_STATE)
    idx_treino, idx_val = next(
        corte_val.split(X.iloc[idx_resto], y.iloc[idx_resto], grupos.iloc[idx_resto])
    )
    idx_treino, idx_val = idx_resto[idx_treino], idx_resto[idx_val]

    partes = {
        nome: (X.iloc[idx], y.iloc[idx], grupos.iloc[idx])
        for nome, idx in [("treino", idx_treino), ("validacao", idx_val), ("teste", idx_teste)]
    }
    ids = [set(g) for _, _, g in partes.values()]
    assert not (ids[0] & ids[1] or ids[0] & ids[2] or ids[1] & ids[2]), "id em dois conjuntos"
    return partes


# ## Etapa 3 — Seleção do modelo no conjunto de validação
def selecionar(partes) -> tuple[str, dict, dict]:
    X_tr, y_tr, _ = partes["treino"]
    X_val, y_val, _ = partes["validacao"]
    # Saída em pandas: as restrições monotônicas são indicadas pelo nome da coluna.
    preprocessador = construir_preprocessador(NUMERIC_FEATURES, CATEGORICAL_FEATURES).set_output(
        transform="pandas"
    )

    resultados, ajustados = {}, {}
    for nome, modelo in candidatos().items():
        pipeline = criar_pipeline(preprocessador, modelo).fit(X_tr, y_tr)
        resultados[nome] = _arredondar(calcular_metricas(y_val, pipeline.predict(X_val)))
        ajustados[nome] = pipeline
        print(f"  validação · {nome:<36} RMSE={resultados[nome]['RMSE']:>12,.0f}  R2={resultados[nome]['R2']:.4f}")

    escolhido = min(resultados, key=lambda n: resultados[n]["RMSE"])
    # Regra de coerência comercial: o monotônico vence se perder no máximo 0,01 de R².
    if escolhido == SEM_RESTRICAO:
        perda = resultados[SEM_RESTRICAO]["R2"] - resultados[MONOTONICO]["R2"]
        if perda <= PERDA_MAXIMA_R2:
            escolhido = MONOTONICO
        print(f"  perda de R² com restrições monotônicas: {perda:.4f} (limite {PERDA_MAXIMA_R2})")
    return escolhido, resultados, ajustados


# ## Etapa 4 — Faixa provável a partir dos erros relativos na validação
def faixa_erro(pipeline, X_val, y_val) -> dict:
    razao = np.asarray(y_val) / np.maximum(pipeline.predict(X_val), 1.0)
    return {"p10": round(float(np.quantile(razao, 0.10)), 4), "p90": round(float(np.quantile(razao, 0.90)), 4)}


# ## Etapa 5 — Importância por permutação (amostra pequena para economizar tempo)
def importancia(pipeline, X_val, y_val) -> list[dict]:
    amostra = X_val.sample(n=min(1500, len(X_val)), random_state=RANDOM_STATE)
    resultado = permutation_importance(
        pipeline,
        amostra,
        y_val.loc[amostra.index],
        n_repeats=3,
        random_state=RANDOM_STATE,
        scoring="r2",
        n_jobs=1,
    )
    linhas = [
        {"variavel": ROTULOS.get(col, col), "coluna": col, "importancia": round(float(valor), 4)}
        for col, valor in zip(amostra.columns, resultado.importances_mean)
        if col in ROTULOS
    ]
    return sorted(linhas, key=lambda linha: linha["importancia"], reverse=True)


# ## Etapa 6 — Agregado por CEP, usado no mapa de valor do portal
def regioes(df: pd.DataFrame) -> list[dict]:
    base = df.assign(preco_m2=df["price"] / (df["sqft_living"] * M2_POR_SQFT))
    agregado = (
        base.groupby("zipcode")
        .agg(
            latitude=("lat", "mean"),
            longitude=("long", "mean"),
            vendas=("price", "size"),
            preco_mediano_usd=("price", "median"),
            preco_m2_mediano_usd=("preco_m2", "median"),
        )
        .reset_index()
    )
    return [
        {
            "cep": str(linha.zipcode),
            "latitude": round(float(linha.latitude), 5),
            "longitude": round(float(linha.longitude), 5),
            "vendas": int(linha.vendas),
            "preco_mediano_usd": round(float(linha.preco_mediano_usd), 2),
            "preco_m2_mediano_usd": round(float(linha.preco_m2_mediano_usd), 2),
        }
        for linha in agregado.itertuples()
    ]


def main() -> None:
    print("Fase 1 · treino do modelo v2")
    df = carregar_base()
    partes = dividir(df)
    escolhido, resultados_val, ajustados = selecionar(partes)
    print(f"  escolhido pela validação: {escolhido}")

    X_tr, y_tr, _ = partes["treino"]
    X_val, y_val, _ = partes["validacao"]
    X_te, y_te, _ = partes["teste"]

    faixa = faixa_erro(ajustados[escolhido], X_val, y_val)
    importancias = importancia(ajustados[escolhido], X_val, y_val)

    # Modelo final: reajustado em treino + validação; o teste só é usado aqui, uma vez.
    modelo_final = clone(ajustados[escolhido]).fit(
        pd.concat([X_tr, X_val]), pd.concat([y_tr, y_val])
    )
    metricas_teste = _arredondar(calcular_metricas(y_te, modelo_final.predict(X_te)))
    baseline_teste = _arredondar(
        calcular_metricas(y_te, ajustados["Baseline pela média"].predict(X_te))
    )
    print(f"  teste · RMSE={metricas_teste['RMSE']:,.0f}  R2={metricas_teste['R2']:.4f}")

    PASTA_MODELOS.mkdir(parents=True, exist_ok=True)
    joblib.dump(modelo_final, ARQUIVO_MODELO, compress=3)

    metricas = {
        "versao": "v2",
        "algoritmo": escolhido,
        "treinado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "alvo": "price (USD)",
        "data_referencia": df["date"].max().strftime("%Y%m%dT000000"),
        "divisao": {
            "treino": int(len(X_tr)),
            "validacao": int(len(X_val)),
            "teste": int(len(X_te)),
            "criterio": "GroupShuffleSplit por id (60/20/20), random_state 42",
        },
        "metricas": {"validacao": resultados_val[escolhido], "teste": metricas_teste},
        "comparacao_validacao": resultados_val,
        "criterio_selecao": (
            "menor RMSE na validação; o HGB Log monotônico é preferido se perder até "
            f"{PERDA_MAXIMA_R2} de R² para o HGB Log sem restrição"
        ),
        "restricoes_monotonicas_crescentes": CRESCENTES,
        "baseline": {"modelo": "Baseline pela média", "teste": baseline_teste},
        "importancia": importancias,
        "faixa_erro": faixa,
        "ceps_conhecidos": sorted(df["zipcode"].astype(str).unique().tolist()),
    }
    ARQUIVO_METRICAS.write_text(json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8")
    ARQUIVO_REGIOES.write_text(json.dumps(regioes(df), indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  artefatos salvos em {PASTA_MODELOS.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
