"""
# Rastreamento e registro do modelo no MLflow (local, custo zero)

Publica no MLflow o artefato que a API já usa (`modulo2_api/models/modelo_imobiliario_v2.joblib`),
sem retreinar e sem mudar o modelo entregue. O MLflow é uma camada **opcional** de
rastreamento e registro: a API continua carregando o `.joblib` e não depende dele.

## O que é registrado
- **Run** no experimento `avaliador-imobiliario`, com:
  - parâmetros: algoritmo, hiperparâmetros do estimador final, divisão 60/20/20 agrupada
    por `id`, `random_state` e versão do artefato;
  - métricas de validação e teste (R², MAE, RMSE, MAPE) lidas de `metricas_v2.json`,
    sem recalcular nada;
  - tags: base King County, número de vendas da base bruta e sha256 do `.joblib`;
  - artefatos: `metricas_v2.json` e o próprio `.joblib`.
- **Modelo** via `mlflow.sklearn.log_model`, com assinatura (`infer_signature`) feita sobre
  vendas reais de `data/raw/kc_house_data.csv` nas mesmas colunas e tipos que a API envia
  ao pipeline, e `input_example`. O pacote `src/` vai junto (`code_paths`), porque o
  regressor em log é uma classe do Módulo 1. A serialização é a padrão do MLflow (skops,
  sem pickle), com a lista explícita de tipos confiáveis do artefato.
- **Model Registry:** nova versão de `avaliador-imobiliario` com o alias `producao`.
  Rodar de novo cria outra versão e move o alias para ela.

## Armazenamento
Backend SQLite em `mlruns/mlflow.db` e artefatos em `mlruns/artefatos/`, na raiz do
repositório. Os dois são gerados e ficam fora do Git (`.gitignore`).

Uso, na raiz do repositório:
    python -m modulo2_api.ferramentas.registrar_mlflow             # registra o .joblib entregue
    python -m modulo2_api.ferramentas.registrar_mlflow --treinar   # retreina antes (muda o artefato)
    mlflow ui --backend-store-uri sqlite:///mlruns/mlflow.db --port 5000 --host 127.0.0.1

Instalação do MLflow (fora do requirements mínimo da API):
    python -m pip install -r requirements-mlflow.txt
"""

import argparse
import hashlib
import json
import sys
import warnings
from importlib.metadata import version
from pathlib import Path

import pandas as pd

from modulo2_api.app.config import (
    ARQUIVO_METRICAS,
    ARQUIVO_MODELO,
    ARQUIVO_REGIOES,
    RAIZ_REPOSITORIO,
)
from modulo2_api.app.schemas.imovel import EXEMPLO_IMOVEL, ImovelEntrada
from modulo2_api.app.services.modelo import ServicoModelo

EXPERIMENTO = "avaliador-imobiliario"
MODELO_REGISTRADO = "avaliador-imobiliario"
ALIAS = "producao"
PASTA_MLFLOW = RAIZ_REPOSITORIO / "mlruns"
BANCO_MLFLOW = PASTA_MLFLOW / "mlflow.db"
PASTA_ARTEFATOS = PASTA_MLFLOW / "artefatos"
DADOS_BRUTOS = RAIZ_REPOSITORIO / "data" / "raw" / "kc_house_data.csv"
PASTA_SRC = RAIZ_REPOSITORIO / "src"
TAMANHO_AMOSTRA = 200
RANDOM_STATE = 42

# O MLflow serializa com skops (formato seguro, sem pickle) e só aceita tipos revisados.
# Estes são os do próprio artefato: as duas classes do Módulo 1 (src/) e as do scikit-learn/numpy.
TIPOS_CONFIAVEIS = [
    "numpy.dtype",
    "sklearn.ensemble._hist_gradient_boosting.predictor.TreePredictor",
    "src.features.RawFeatureTransformer",
    "src.modeling.LogSmearingRegressor",
]

# Dependências gravadas junto do modelo (as mesmas versões da API, lidas do ambiente)
PACOTES_DO_MODELO = ["scikit-learn", "pandas", "numpy", "scipy", "joblib"]


def uri_sqlite(banco: Path) -> str:
    """URI SQLite com barras normais, aceita no Windows e no Linux."""
    return f"sqlite:///{Path(banco).resolve().as_posix()}"


def sha256(arquivo: Path) -> str:
    resumo = hashlib.sha256()
    with open(arquivo, "rb") as fluxo:
        for bloco in iter(lambda: fluxo.read(1 << 20), b""):
            resumo.update(bloco)
    return resumo.hexdigest()


# ## Entrada no formato da API
def entrada_da_api(servico: ServicoModelo, imovel: dict = EXEMPLO_IMOVEL) -> pd.DataFrame:
    """DataFrame exatamente como `ServicoModelo.prever` monta antes do `predict`."""
    return pd.DataFrame([servico._para_colunas_do_modelo(ImovelEntrada(**imovel))])


def amostra_real(servico: ServicoModelo, n: int = TAMANHO_AMOSTRA) -> pd.DataFrame:
    """Vendas reais da base, nas colunas e nos tipos que a API entrega ao pipeline."""
    referencia = entrada_da_api(servico)
    base = pd.read_csv(DADOS_BRUTOS, dtype={"date": str})
    amostra = base.sample(n=min(n, len(base)), random_state=RANDOM_STATE)
    return amostra[referencia.columns].astype(referencia.dtypes.to_dict()).reset_index(drop=True)


# ## Parâmetros do estimador final (só valores simples, como texto quando preciso)
def parametros_do_modelo(modelo, metricas: dict) -> dict:
    estimador = modelo.steps[-1][1] if hasattr(modelo, "steps") else modelo
    parametros = {
        "versao": metricas.get("versao"),
        "algoritmo": metricas.get("algoritmo"),
        "estimador_final": type(estimador).__name__,
        "divisao": "60/20/20",
        "divisao_criterio": metricas["divisao"]["criterio"],
        "divisao_treino": metricas["divisao"]["treino"],
        "divisao_validacao": metricas["divisao"]["validacao"],
        "divisao_teste": metricas["divisao"]["teste"],
        "random_state": RANDOM_STATE,
        "alvo": metricas.get("alvo"),
        "criterio_selecao": metricas.get("criterio_selecao"),
    }
    for nome, valor in estimador.get_params(deep=True).items():
        if valor is None or isinstance(valor, (bool, int, float, str)):
            parametros[f"hp_{nome}"] = valor
        elif isinstance(valor, (dict, list, tuple)):
            parametros[f"hp_{nome}"] = json.dumps(valor, ensure_ascii=False, default=str)
    return {nome: ("None" if valor is None else valor) for nome, valor in parametros.items()}


def metricas_do_json(metricas: dict) -> dict:
    """R², MAE, RMSE e MAPE de validação e teste, como estão no metricas_v2.json."""
    saida = {}
    for conjunto in ("validacao", "teste"):
        for nome in ("R2", "MAE", "RMSE", "MAPE"):
            saida[f"{conjunto}_{nome}"] = float(metricas["metricas"][conjunto][nome])
    for nome in ("R2", "RMSE"):
        saida[f"baseline_teste_{nome}"] = float(metricas["baseline"]["teste"][nome])
    return saida


def registrar(
    tracking_uri: str | None = None,
    pasta_artefatos: Path = PASTA_ARTEFATOS,
    experimento: str = EXPERIMENTO,
    modelo_registrado: str = MODELO_REGISTRADO,
    alias: str = ALIAS,
) -> dict:
    """Cria um run com o artefato entregue, registra a versão e aponta o alias para ela."""
    import mlflow
    from mlflow.models import infer_signature
    from mlflow.tracking import MlflowClient

    tracking_uri = tracking_uri or uri_sqlite(BANCO_MLFLOW)
    if tracking_uri.startswith("sqlite:///"):
        Path(tracking_uri.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    pasta_artefatos = Path(pasta_artefatos).resolve()
    pasta_artefatos.mkdir(parents=True, exist_ok=True)
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_registry_uri(tracking_uri)

    if mlflow.get_experiment_by_name(experimento) is None:
        mlflow.create_experiment(experimento, artifact_location=pasta_artefatos.as_uri())
    mlflow.set_experiment(experimento)

    # Mesmo carregamento da API: pipeline, métricas e regiões
    servico = ServicoModelo(ARQUIVO_MODELO, ARQUIVO_METRICAS, ARQUIVO_REGIOES)
    servico.carregar()
    metricas = servico.metricas
    vendas = sum(1 for _ in open(DADOS_BRUTOS, encoding="utf-8")) - 1

    amostra = amostra_real(servico)
    # A API nunca envia nulos às colunas inteiras (reforma ausente vira 0), então o aviso
    # do MLflow sobre inteiros com valores ausentes não se aplica aqui.
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Hint: Inferred schema contains integer")
        assinatura = infer_signature(amostra, servico.modelo.predict(amostra))
    exemplo = amostra.head(3)

    with mlflow.start_run(run_name=f"modelo-{metricas['versao']}") as run:
        mlflow.log_params(parametros_do_modelo(servico.modelo, metricas))
        mlflow.log_metrics(metricas_do_json(metricas))
        mlflow.set_tags(
            {
                "dataset": "King County (kc_house_data.csv)",
                "dataset_vendas": str(vendas),
                "artefato": ARQUIVO_MODELO.name,
                "artefato_sha256": sha256(ARQUIVO_MODELO),
                "treinado_em": metricas.get("treinado_em", ""),
                "data_referencia": metricas.get("data_referencia", ""),
                "mlflow.note.content": (
                    f"{metricas['algoritmo']} treinado na base de King County "
                    f"({vendas:,} vendas). ".replace(",", ".")
                    + "Artefato idêntico ao carregado pela API (sha256 na tag artefato_sha256)."
                ),
            }
        )
        mlflow.log_artifact(str(ARQUIVO_METRICAS), artifact_path="metricas")
        mlflow.log_artifact(str(ARQUIVO_MODELO), artifact_path="artefato_original")
        info = mlflow.sklearn.log_model(
            servico.modelo,
            name="modelo",
            signature=assinatura,
            input_example=exemplo,
            code_paths=[str(PASTA_SRC)],
            skops_trusted_types=TIPOS_CONFIAVEIS,
            pip_requirements=[f"{pacote}=={version(pacote)}" for pacote in PACOTES_DO_MODELO],
            registered_model_name=modelo_registrado,
        )

    cliente = MlflowClient(tracking_uri=tracking_uri, registry_uri=tracking_uri)
    versao = str(info.registered_model_version)
    cliente.set_registered_model_alias(modelo_registrado, alias, versao)
    cliente.update_registered_model(
        modelo_registrado,
        description="Avaliador de imóveis de King County (preço em USD). Alias 'producao' = versão servida pela API.",
    )
    cliente.update_model_version(
        modelo_registrado,
        versao,
        description=f"{metricas['algoritmo']} · R² teste {metricas['metricas']['teste']['R2']:.4f} · "
        f"sha256 {sha256(ARQUIVO_MODELO)[:12]}",
    )
    return {
        "tracking_uri": tracking_uri,
        "run_id": run.info.run_id,
        "experimento_id": run.info.experiment_id,
        "versao": versao,
        "uri_modelo": f"models:/{modelo_registrado}@{alias}",
        "servico": servico,
    }


def conferir(resultado: dict) -> tuple[float, float]:
    """Compara a previsão do modelo registrado com a do serviço da API para o EXEMPLO_IMOVEL."""
    import mlflow

    servico = resultado["servico"]
    registrado = mlflow.pyfunc.load_model(resultado["uri_modelo"])
    via_mlflow = round(float(registrado.predict(entrada_da_api(servico))[0]), 2)
    via_api = servico.prever([ImovelEntrada(**EXEMPLO_IMOVEL)])[0].preco_estimado_usd
    return via_mlflow, via_api


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Registra o modelo entregue no MLflow local.")
    parser.add_argument("--tracking-uri", default=None, help="padrão: sqlite:///<raiz>/mlruns/mlflow.db")
    parser.add_argument("--treinar", action="store_true", help="retreina o modelo antes (muda o .joblib)")
    parser.add_argument("--sem-conferir", action="store_true", help="não compara a previsão com a API")
    args = parser.parse_args(argv)

    if args.treinar:
        from modulo2_api.treinamento import treinar_modelo

        treinar_modelo.main()

    resultado = registrar(tracking_uri=args.tracking_uri)
    print(f"Experimento : {EXPERIMENTO} (id {resultado['experimento_id']})")
    print(f"Run         : {resultado['run_id']}")
    print(f"Registro    : {MODELO_REGISTRADO} versão {resultado['versao']} · alias @{ALIAS}")

    if not args.sem_conferir:
        via_mlflow, via_api = conferir(resultado)
        igual = abs(via_mlflow - via_api) < 0.01
        print(f"Conferência : MLflow {via_mlflow:,.2f} USD | API {via_api:,.2f} USD -> {'iguais' if igual else 'DIFERENTES'}")
        if not igual:
            return 1

    print("\nPara abrir a interface do MLflow (na raiz do repositório):")
    uri_ui = "sqlite:///mlruns/mlflow.db" if args.tracking_uri is None else f'"{resultado["tracking_uri"]}"'
    print(f"  mlflow ui --backend-store-uri {uri_ui} --port 5000 --host 127.0.0.1")
    print("  e acesse http://127.0.0.1:5000")
    return 0


if __name__ == "__main__":
    sys.exit(main())
