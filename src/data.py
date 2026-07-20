import pandas as pd

from .config import FIGURES_DIR, MAPS_DIR, MODEL_DIR, RAW_DATA, ROOT


def garantir_pastas() -> None:
    for caminho in [ROOT / "data/processed", ROOT / "data/final", FIGURES_DIR, MAPS_DIR, MODEL_DIR]:
        caminho.mkdir(parents=True, exist_ok=True)


def carregar_dados(caminho=RAW_DATA) -> pd.DataFrame:
    return pd.read_csv(caminho)


def salvar_csv(df: pd.DataFrame, caminho) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(caminho, index=False)
