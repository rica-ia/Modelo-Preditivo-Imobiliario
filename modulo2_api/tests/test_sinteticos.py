"""Dados sintéticos de exemplo: carga no lifespan, contagens, idempotência, faturas, remoção e proteção da rota."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from modulo2_api.app import main
from modulo2_api.app.config import ARQUIVO_ESQUEMA
from modulo2_api.app.schemas.imovel import EXEMPLO_IMOVEL
from modulo2_api.app.services.banco import Banco
from modulo2_api.app.services.planos import LIMITES, PRECOS_USD

ADMIN = {"X-Admin-Token": "token-de-teste"}
ROTA = "/v1/admin/banco/sinteticos"


@pytest.fixture(scope="module")
def cliente(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AVALIADOR_BANCO", str(tmp_path_factory.mktemp("banco") / "sinteticos.db"))
        mp.setenv("AVALIADOR_ADMIN_TOKEN", "token-de-teste")
        mp.setenv("AVALIADOR_DADOS_SINTETICOS", "1")
        mp.setenv("SMTP_USUARIO", "")
        mp.setenv("SMTP_SENHA_APP", "")
        with TestClient(main.app) as cliente:
            yield cliente


def contar(cliente, sql: str, parametros: tuple = ()) -> int:
    return cliente.app.state.banco.um(f"SELECT COUNT(*) AS n FROM {sql}", parametros)["n"]


def test_lifespan_carrega_cerca_de_20_por_secao(cliente):
    assert contar(cliente, "clientes WHERE sintetico = 1") == 20
    sinteticos = "(SELECT id FROM clientes WHERE sintetico = 1)"
    assert contar(cliente, f"chaves WHERE cliente_id IN {sinteticos}") == 20
    assert contar(cliente, f"envios_email WHERE cliente_id IN {sinteticos} AND status = 'exemplo_sintetico'") == 20
    assert contar(cliente, "avaliacoes WHERE sintetico = 1 AND origem = 'api'") == 20
    assert contar(cliente, f"eventos_comerciais WHERE cliente_id IN {sinteticos} AND tipo = 'emissao'") == 20
    assert 200 <= contar(cliente, "predicoes WHERE origem = 'api'") <= 1500
    assert 20 <= contar(cliente, "faturas") <= 40
    assert 2 <= contar(cliente, "chaves WHERE suspensa_em IS NOT NULL AND revogada_em IS NULL") <= 3
    assert 2 <= contar(cliente, "chaves WHERE revogada_em IS NOT NULL") <= 3
    emails = cliente.app.state.banco.consultar("SELECT email FROM clientes WHERE sintetico = 1")
    assert all(e["email"].endswith("@exemplo.com") for e in emails)
    assert contar(cliente, "clientes WHERE sintetico = 1 AND empresa IS NULL") >= 3


def test_chaves_no_formato_e_limite_do_plano(cliente):
    chaves = cliente.app.state.banco.consultar(
        "SELECT k.prefixo, k.limite_mensal, k.hash_sha256, c.plano FROM chaves k JOIN clientes c ON c.id = k.cliente_id"
        " WHERE c.sintetico = 1"
    )
    assert all(k["prefixo"].startswith("aval_") and len(k["prefixo"]) == 12 for k in chaves)
    assert all(k["limite_mensal"] == LIMITES[k["plano"]] for k in chaves)
    assert all(len(k["hash_sha256"]) == 64 for k in chaves)


def test_faturas_com_valor_do_plano_e_status_coerente(cliente):
    faturas = cliente.app.state.banco.consultar(
        "SELECT f.*, k.revogada_em FROM faturas f JOIN chaves k ON k.id = f.chave_id"
    )
    assert all(f["valor_usd"] == PRECOS_USD[f["plano"]] for f in faturas)
    status = [f["status"] for f in faturas]
    assert status.count("paga") > len(status) / 2
    assert {"cancelada", "vencida"} <= set(status)
    assert all(f["revogada_em"] for f in faturas if f["status"] == "cancelada")
    assert all(f["paga_em"] for f in faturas if f["status"] == "paga")


def test_algum_cliente_perto_do_limite(cliente):
    uso = cliente.app.state.banco.consultar(
        "SELECT k.limite_mensal, (SELECT COUNT(*) FROM predicoes p WHERE p.chave_id = k.id AND p.status_http = 200"
        " AND p.criado_em >= strftime('%Y-%m-01', 'now', 'localtime')) AS uso FROM chaves k"
        " JOIN clientes c ON c.id = k.cliente_id WHERE c.sintetico = 1 AND k.revogada_em IS NULL AND k.suspensa_em IS NULL"
    )
    assert any(u["uso"] >= 0.8 * u["limite_mensal"] for u in uso)


def test_rotas_exigem_admin(cliente):
    assert cliente.post(ROTA).status_code == 401
    assert cliente.delete(ROTA).status_code == 401


def test_carga_e_idempotente(cliente):
    antes = contar(cliente, "predicoes")
    resposta = cliente.post(ROTA, headers=ADMIN)
    assert resposta.status_code == 200
    assert not any(resposta.json().values())
    assert contar(cliente, "clientes WHERE sintetico = 1") == 20 and contar(cliente, "predicoes") == antes


def test_remocao_preserva_dados_reais_e_recarga(cliente):
    real = cliente.post("/v1/comercial/chaves", json={"nome": "Cliente Real", "email": "real@exemplo.com",
                                                      "empresa": "Exemplo", "plano": "basico"}, headers=ADMIN).json()
    assert cliente.post("/v1/predict", json=EXEMPLO_IMOVEL, headers={"X-API-Key": real["chave"]}).status_code == 200
    reais = {
        "clientes": contar(cliente, "clientes WHERE sintetico = 0"),
        "chaves": contar(cliente, "chaves WHERE cliente_id IN (SELECT id FROM clientes WHERE sintetico = 0)"),
        "predicoes": contar(cliente, "predicoes WHERE chave_id IS NULL OR chave_id = ?", (real["chave_id"],)),
        "avaliacoes": contar(cliente, "avaliacoes WHERE sintetico = 0"),
        "vendas": contar(cliente, "vendas_historicas"),
    }
    removidos = cliente.delete(ROTA, headers=ADMIN)
    assert removidos.status_code == 200
    assert removidos.json()["clientes"] == 20 and removidos.json()["avaliacoes"] == 20
    assert contar(cliente, "clientes WHERE sintetico = 1") == 0 and contar(cliente, "faturas") == 0
    assert contar(cliente, "avaliacoes WHERE sintetico = 1") == 0
    assert reais == {
        "clientes": contar(cliente, "clientes WHERE sintetico = 0"),
        "chaves": contar(cliente, "chaves WHERE cliente_id IN (SELECT id FROM clientes WHERE sintetico = 0)"),
        "predicoes": contar(cliente, "predicoes WHERE chave_id IS NULL OR chave_id = ?", (real["chave_id"],)),
        "avaliacoes": contar(cliente, "avaliacoes WHERE sintetico = 0"),
        "vendas": contar(cliente, "vendas_historicas"),
    }
    assert not any(cliente.delete(ROTA, headers=ADMIN).json().values())  # remover de novo não faz nada
    recarga = cliente.post(ROTA, headers=ADMIN).json()
    assert recarga["clientes"] == 20 and recarga["faturas"] >= 20


def test_migracao_acrescenta_coluna_sintetico_em_banco_antigo(tmp_path):
    caminho = tmp_path / "antigo.db"
    with sqlite3.connect(caminho) as con:
        con.execute("CREATE TABLE clientes (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, email TEXT NOT NULL,"
                    " empresa TEXT, plano TEXT NOT NULL, criado_em TEXT NOT NULL)")
        con.execute("INSERT INTO clientes (nome, email, plano, criado_em) VALUES ('Antigo', 'a@exemplo.com', 'basico', 'x')")
    con.close()
    banco = Banco(caminho, ARQUIVO_ESQUEMA)
    banco.migrar()
    assert banco.um("SELECT sintetico FROM clientes")["sintetico"] == 0
    assert banco.um("SELECT COUNT(*) AS n FROM faturas")["n"] == 0
