from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from .config import FIGURES_DIR

sns.set_theme(style="whitegrid", context="notebook")
CORES = {"azul": "#1d4ed8", "laranja": "#ea580c", "verde": "#15803d"}


def _salvar(fig, nome: str, pasta: Path = FIGURES_DIR):
    pasta.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(pasta / nome, dpi=160, bbox_inches="tight")
    return fig


def resumir_distribuicao_alvo(serie: pd.Series) -> pd.DataFrame:
    """Quantifica a cauda do preço antes e depois da transformação logarítmica."""
    escalas = {"price": serie.astype(float), "log1p(price)": np.log1p(serie)}
    return pd.DataFrame(
        [
            {
                "escala": nome,
                "media": valores.mean(),
                "mediana": valores.median(),
                "assimetria": valores.skew(),
                "curtose_excesso": valores.kurt(),
            }
            for nome, valores in escalas.items()
        ]
    )


def plot_distribuicao_preco(df: pd.DataFrame):
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))
    sns.histplot(df["price"], bins=55, ax=axes[0], color=CORES["azul"])
    axes[0].set(title="Distribuição do preço", xlabel="Preço (US$)", ylabel="Imóveis")
    sns.histplot(np.log1p(df["price"]), bins=55, ax=axes[1], color=CORES["verde"])
    axes[1].set(title="Distribuição após log1p", xlabel="log1p(preço)", ylabel="Imóveis")
    return _salvar(fig, "01_distribuicao_preco.png")


def plot_relacoes_preco(df: pd.DataFrame):
    amostra = df.sample(min(5_000, len(df)), random_state=42)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    sns.scatterplot(data=amostra, x="sqft_living", y="price", alpha=0.35, ax=axes[0])
    axes[0].set(title="Área construída × preço", xlabel="Área construída (ft²)", ylabel="Preço (US$)")
    sns.boxplot(data=df, x="grade", y="price", color="#93c5fd", showfliers=False, ax=axes[1])
    axes[1].set(title="Padrão construtivo × preço", xlabel="Grade", ylabel="Preço (US$)")
    return _salvar(fig, "02_relacoes_preco.png")


def plot_correlacao(df: pd.DataFrame):
    colunas = [
        "price", "bedrooms", "bathrooms", "sqft_living", "sqft_lot", "floors",
        "waterfront", "view", "condition", "grade", "sqft_above", "sqft_basement",
        "yr_built", "lat", "long", "sqft_living15", "sqft_lot15",
    ]
    fig, ax = plt.subplots(figsize=(12.5, 9.5))
    sns.heatmap(df[colunas].corr(), cmap="vlag", center=0, square=True, ax=ax)
    ax.set_title("Correlação de Pearson entre variáveis numéricas")
    return _salvar(fig, "03_correlacao_pearson.png")


def plot_boxplots(df: pd.DataFrame):
    colunas = ["price", "bedrooms", "bathrooms", "sqft_living", "sqft_lot"]
    fig, axes = plt.subplots(1, len(colunas), figsize=(15, 5))
    for ax, coluna in zip(axes, colunas):
        sns.boxplot(y=df[coluna], ax=ax, color="#bfdbfe")
        ax.set(title=coluna, xlabel="", ylabel="")
    return _salvar(fig, "04_boxplots_outliers.png")


def plot_validacao_cruzada(por_fold: pd.DataFrame):
    ordem = por_fold.groupby("modelo")["RMSE"].mean().sort_values().index.tolist()
    baseline = por_fold.loc[
        por_fold["modelo"].eq("Baseline pela média"), ["fold", "RMSE"]
    ].rename(columns={"RMSE": "RMSE_baseline"})
    comparacao = por_fold.merge(baseline, on="fold", how="left")
    comparacao["reducao_RMSE"] = 100 * (
        comparacao["RMSE_baseline"] - comparacao["RMSE"]
    ) / comparacao["RMSE_baseline"]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.2))
    cores = ["#21485f", "#5e959f", "#b08d57", "#9aa8b5"]
    for posicao, (nome, cor) in enumerate(zip(ordem, cores)):
        valores = por_fold.loc[por_fold["modelo"].eq(nome), "RMSE"].to_numpy()
        deslocamento = np.linspace(-0.07, 0.07, len(valores))
        axes[0].scatter(np.full(len(valores), posicao) + deslocamento, valores, color=cor, s=46)
        axes[0].scatter(posicao, valores.mean(), marker="D", color="#172033", s=50, zorder=3)

    aprendidos = [nome for nome in ordem if nome != "Baseline pela média"]
    for posicao, (nome, cor) in enumerate(zip(aprendidos, cores)):
        valores = comparacao.loc[comparacao["modelo"].eq(nome), "reducao_RMSE"].to_numpy()
        deslocamento = np.linspace(-0.07, 0.07, len(valores))
        axes[1].scatter(np.full(len(valores), posicao) + deslocamento, valores, color=cor, s=46)
        axes[1].scatter(posicao, valores.mean(), marker="D", color="#172033", s=50, zorder=3)

    axes[0].set(title="RMSE observado em cada fold", ylabel="RMSE (US$)", xlabel="")
    axes[0].set_xticks(range(len(ordem)), ordem, rotation=14)
    axes[1].axhline(0, color="#9aa8b5", lw=1)
    axes[1].set(title="Redução do RMSE frente ao baseline", ylabel="Redução (%)", xlabel="")
    axes[1].set_xticks(range(len(aprendidos)), aprendidos, rotation=14)
    fig.suptitle("Estabilidade da validação cruzada — pontos: folds; losangos: médias", y=1.02)
    return _salvar(fig, "05_validacao_cruzada_modelos.png")


def plot_generalizacao(resultados: pd.DataFrame):
    base = resultados[resultados["conjunto"].isin(["Treino", "Teste"])]
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    sns.barplot(data=base, x="modelo", y="RMSE", hue="conjunto", ax=axes[0])
    sns.barplot(data=base, x="modelo", y="R2", hue="conjunto", ax=axes[1])
    axes[0].set(title="RMSE: treino × teste", xlabel="", ylabel="RMSE (US$)")
    axes[1].set(title="R²: treino × teste", xlabel="", ylabel="R²")
    for ax in axes:
        ax.tick_params(axis="x", rotation=13)
    return _salvar(fig, "06_generalizacao_modelos.png")


def plot_real_previsto(y_true, y_pred):
    fig, ax = plt.subplots(figsize=(7.5, 6.2))
    ax.scatter(y_true, y_pred, alpha=0.35, s=18, color=CORES["azul"])
    limites = [min(np.min(y_true), np.min(y_pred)), max(np.max(y_true), np.max(y_pred))]
    ax.plot(limites, limites, "--", color=CORES["laranja"], label="previsão perfeita")
    ax.set(title="Preço real × previsto — teste isolado", xlabel="Real (US$)", ylabel="Previsto (US$)")
    ax.legend()
    return _salvar(fig, "07_real_vs_previsto.png")


def plot_residuos(y_true, y_pred):
    residuos = np.asarray(y_true) - np.asarray(y_pred)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.7))
    sns.histplot(residuos, bins=55, ax=axes[0], color=CORES["azul"])
    axes[0].axvline(0, ls="--", color=CORES["laranja"])
    axes[0].set(title="Distribuição dos resíduos", xlabel="Real − previsto (US$)")
    axes[1].scatter(y_pred, residuos, alpha=0.30, s=16, color=CORES["verde"])
    axes[1].axhline(0, ls="--", color=CORES["laranja"])
    axes[1].set(title="Resíduos × previsto", xlabel="Previsto (US$)", ylabel="Resíduo (US$)")
    return _salvar(fig, "08_residuos.png")


def plot_importancia(importancias: pd.DataFrame):
    dados = importancias.nlargest(12, "importancia").sort_values("importancia")
    fig, ax = plt.subplots(figsize=(8.8, 6))
    ax.barh(dados["variavel"], dados["importancia"], color=CORES["azul"])
    ax.set(title="Importância por permutação no teste", xlabel="Aumento do MAE ao embaralhar", ylabel="")
    return _salvar(fig, "09_importancia_permutacao.png")
