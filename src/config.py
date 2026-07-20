from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DATA = ROOT / "data/raw/kc_house_data.csv"
PROCESSED_DATA = ROOT / "data/processed/kc_house_processed.csv"
FINAL_DATA = ROOT / "data/final/kc_house_final.csv"
FIGURES_DIR = ROOT / "outputs/figures"
MAPS_DIR = ROOT / "outputs/maps"
MODEL_DIR = ROOT / "models/v1"

RANDOM_STATE = 42
TEST_SIZE = 0.20
CV_FOLDS = 5
N_JOBS = 1
TARGET = "price"
H3_RESOLUTION = 7
H3_MIN_SALES = 20

NUMERIC_FEATURES = [
    "bedrooms",
    "bathrooms",
    "sqft_living",
    "floors",
    "waterfront",
    "view",
    "condition",
    "grade",
    "sqft_basement",
    "lat",
    "long",
    "sqft_living15",
    "log_sqft_lot",
    "idade_imovel",
    "foi_reformado",
    "tem_porao",
    "mes_venda",
    "ano_venda",
]
CATEGORICAL_FEATURES = ["zipcode"]
MODEL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

VIF_BEFORE = [
    "bedrooms",
    "bathrooms",
    "sqft_living",
    "floors",
    "waterfront",
    "view",
    "condition",
    "grade",
    "sqft_above",
    "sqft_basement",
    "lat",
    "long",
    "sqft_living15",
    "log_sqft_lot",
    "log_sqft_lot15",
    "idade_imovel",
]
VIF_AFTER = [coluna for coluna in VIF_BEFORE if coluna not in {"sqft_above", "log_sqft_lot15"}]
