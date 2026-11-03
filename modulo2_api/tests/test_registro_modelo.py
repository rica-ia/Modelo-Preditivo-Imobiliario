"""Registro do artefato no SQLite: BLOB versionado, idempotente, restaurável e verificável."""

import hashlib

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from modulo2_api.app import main
from modulo2_api.app.config import ARQUIVO_MODELO
from modulo2_api.app.schemas.imovel import EXEMPLO_IMOVEL, ImovelEntrada
from modulo2_api.app.services.registro_modelo import ServicoRegistroModelo

ADMIN = {"X-Admin-Token": "token-de-teste"}
SHA_DISCO = hashlib.sha256(ARQUIVO_MODELO.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def cliente(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AVALIADOR_BANCO", str(tmp_path_factory.mktemp("banco") / "registro.db"))
        mp.setenv("AVALIADOR_ADMIN_TOKEN", "token-de-teste")
        with TestClient(main.app) as cliente:
            yield cliente


def test_lifespan_registra_artefato_com_sha256_do_arquivo(cliente):
    banco = cliente.app.state.banco
    linha = banco.um("SELECT sha256, tamanho_bytes, formato, ativo, length(artefato) AS blob FROM modelos")
    assert linha["sha256"] == SHA_DISCO
    assert linha["tamanho_bytes"] == linha["blob"] == ARQUIVO_MODELO.stat().st_size
    assert linha["formato"] == "joblib" and linha["ativo"] == 1
    ativo = cliente.app.state.registro_modelo.registro_ativo
    assert ativo["sha256"] == SHA_DISCO and ativo["versao"] == "v2"


def test_registro_idempotente(cliente):
    banco = cliente.app.state.banco
    registro = ServicoRegistroModelo(banco, cliente.app.state.servico_modelo)
    segundo = registro.registrar()
    assert segundo["novo"] is False
    assert banco.um("SELECT COUNT(*) AS n FROM modelos")["n"] == 1
    assert banco.um("SELECT COUNT(*) AS n FROM modelos WHERE ativo = 1")["n"] == 1


def test_restauracao_preve_igual_ao_modelo_em_memoria(cliente):
    servico = cliente.app.state.servico_modelo
    registro = cliente.app.state.registro_modelo
    restaurado = registro.restaurar(registro.registro_ativo["id"])
    entrada = pd.DataFrame([servico._para_colunas_do_modelo(ImovelEntrada(**EXEMPLO_IMOVEL))])
    assert float(restaurado.predict(entrada)[0]) == float(servico.modelo.predict(entrada)[0])


def test_rota_lista_artefatos_sem_blob(cliente):
    resposta = cliente.get("/v1/modelo/artefatos")
    assert resposta.status_code == 200
    artefatos = resposta.json()
    assert len(artefatos) == 1
    artefato = artefatos[0]
    assert "artefato" not in artefato
    assert artefato["sha256"] == SHA_DISCO and artefato["ativo"] is True
    assert artefato["nome_arquivo"].endswith("models/modelo_imobiliario_v2.joblib")
    assert artefato["metricas"]["teste"]["R2"] > 0.8


def test_verificacao_integra(cliente):
    artefato_id = cliente.get("/v1/modelo/artefatos").json()[0]["id"]
    corpo = cliente.get(f"/v1/modelo/artefatos/{artefato_id}/verificar", headers=ADMIN).json()
    assert corpo["integro"] is True
    assert corpo["sha256_blob"] == corpo["sha256_disco"] == corpo["sha256_carregado"] == SHA_DISCO
    assert corpo["previsao_restaurada"] == corpo["previsao_em_memoria"] > 0
    assert cliente.get("/v1/modelo/artefatos/9999/verificar", headers=ADMIN).status_code == 404
    assert cliente.get(f"/v1/modelo/artefatos/{artefato_id}/verificar").status_code == 401


def test_explorador_do_banco_mostra_modelos_sem_blob(cliente):
    secoes = {s["secao"]: s for s in cliente.get("/v1/admin/banco/secoes", headers=ADMIN).json()}
    assert secoes["modelos"]["titulo"] == "Modelos (artefatos)"
    assert "artefato" not in secoes["modelos"]["colunas"] and not secoes["modelos"]["pode_excluir"]
    linhas = cliente.get("/v1/admin/banco/modelos", headers=ADMIN).json()["linhas"]
    artefato_id = linhas[0]["id"]
    assert linhas[0]["sha256"] == SHA_DISCO and "artefato" not in linhas[0]
    detalhe = cliente.get(f"/v1/admin/banco/modelos/{artefato_id}", headers=ADMIN).json()["registro"]
    assert "artefato" not in detalhe and detalhe["tamanho_bytes"] > 0
    assert cliente.delete(f"/v1/admin/banco/modelos/{artefato_id}", headers=ADMIN).status_code == 400


def test_blob_adulterado_nao_e_integro(cliente):
    banco = cliente.app.state.banco
    original = bytes(banco.um("SELECT artefato FROM modelos WHERE ativo = 1")["artefato"])
    adulterado = original[:-16] + bytes(16)
    banco.executar("INSERT INTO modelos (versao, nome_arquivo, sha256, tamanho_bytes, formato, registrado_em, ativo, artefato) "
                   "VALUES ('v2', 'adulterado.joblib', ?, ?, 'joblib', '2026-11-03', 0, ?)",
                   (hashlib.sha256(original).hexdigest()[::-1], len(adulterado), adulterado))
    adulterado_id = banco.um("SELECT id FROM modelos WHERE nome_arquivo = 'adulterado.joblib'")["id"]
    corpo = cliente.get(f"/v1/modelo/artefatos/{adulterado_id}/verificar", headers=ADMIN).json()
    assert corpo["integro"] is False
    assert corpo["sha256_blob"] != corpo["sha256_disco"]
    banco.executar("DELETE FROM modelos WHERE id = ?", (adulterado_id,))


def test_resumo_mlflow_sem_registro_explica_como_criar(cliente, monkeypatch, tmp_path):
    monkeypatch.setenv("AVALIADOR_MLFLOW_DB", str(tmp_path / "inexistente.db"))
    monkeypatch.setenv("AVALIADOR_MLFLOW_URL", "http://127.0.0.1:9")
    corpo = cliente.get("/v1/modelo/mlflow").json()
    assert corpo["disponivel"] is False and corpo["ui_no_ar"] is False
    assert "registrar_mlflow" in corpo["comando_registrar"] and "mlflow ui" in corpo["comando_ui"]
