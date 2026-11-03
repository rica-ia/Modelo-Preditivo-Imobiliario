"""Registro no MLflow num tracking temporário: métricas do JSON, versão, alias e previsão igual à da API."""

import json

import pytest

mlflow = pytest.importorskip("mlflow")

from modulo2_api.app.config import ARQUIVO_METRICAS, ARQUIVO_MODELO  # noqa: E402
from modulo2_api.ferramentas import registrar_mlflow as rm  # noqa: E402


@pytest.fixture(scope="module")
def registro(tmp_path_factory):
    pasta = tmp_path_factory.mktemp("mlflow")
    uri = rm.uri_sqlite(pasta / "mlflow.db")
    resultado = rm.registrar(tracking_uri=uri, pasta_artefatos=pasta / "artefatos")
    yield resultado
    mlflow.set_tracking_uri(None)


def test_metricas_iguais_ao_json(registro):
    esperadas = json.loads(ARQUIVO_METRICAS.read_text(encoding="utf-8"))["metricas"]
    run = mlflow.MlflowClient(tracking_uri=registro["tracking_uri"]).get_run(registro["run_id"])
    for conjunto in ("validacao", "teste"):
        for nome in ("R2", "MAE", "RMSE", "MAPE"):
            assert run.data.metrics[f"{conjunto}_{nome}"] == pytest.approx(esperadas[conjunto][nome])
    assert run.data.tags["artefato_sha256"] == rm.sha256(ARQUIVO_MODELO)
    assert run.data.params["divisao"] == "60/20/20"


def test_versao_registrada_com_alias(registro):
    cliente = mlflow.MlflowClient(tracking_uri=registro["tracking_uri"], registry_uri=registro["tracking_uri"])
    versao = cliente.get_model_version_by_alias(rm.MODELO_REGISTRADO, rm.ALIAS)
    assert str(versao.version) == registro["versao"] == "1"
    assert versao.run_id == registro["run_id"]


def test_previsao_registrada_igual_a_da_api(registro):
    via_mlflow, via_api = rm.conferir(registro)
    assert via_mlflow == pytest.approx(via_api, abs=0.01)
