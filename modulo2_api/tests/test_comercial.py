"""Módulo comercial: chaves de API por cliente, e-mail, consumo e relatórios do SQLite."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from modulo2_api.app import main
from modulo2_api.app.schemas.imovel import EXEMPLO_IMOVEL

ADMIN = {"X-Admin-Token": "token-de-teste"}
CLIENTE = {"nome": "Cliente Teste", "email": "cliente@exemplo.com", "empresa": "Exemplo", "plano": "basico"}


@pytest.fixture(scope="module")
def cliente(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AVALIADOR_BANCO", str(tmp_path_factory.mktemp("banco") / "comercial.db"))
        mp.setenv("AVALIADOR_ADMIN_TOKEN", "token-de-teste")
        mp.setenv("SMTP_USUARIO", "")
        mp.setenv("SMTP_SENHA_APP", "")
        with TestClient(main.app) as cliente:
            yield cliente


@pytest.fixture(scope="module")
def nova_chave(cliente):
    resposta = cliente.post("/v1/comercial/chaves", json=CLIENTE, headers=ADMIN)
    assert resposta.status_code == 201
    return resposta.json()


def test_criar_chave_201(nova_chave):
    assert nova_chave["chave"].startswith("aval_")
    assert nova_chave["limite_mensal"] == 1000
    assert nova_chave["prefixo"] == nova_chave["chave"][:12]


def test_chave_guardada_so_como_hash(cliente, nova_chave):
    banco = cliente.app.state.banco
    registro = banco.um("SELECT * FROM chaves WHERE id = ?", (nova_chave["chave_id"],))
    assert nova_chave["chave"] not in str(registro.values())
    assert len(registro["hash_sha256"]) == 64


@pytest.mark.parametrize("cabecalhos", [{}, {"X-Admin-Token": "errado"}])
def test_admin_ausente_ou_errado_401(cliente, cabecalhos):
    resposta = cliente.post("/v1/comercial/chaves", json=CLIENTE, headers=cabecalhos)
    assert resposta.status_code == 401
    assert resposta.json()["erro"] == "nao_autorizado"


def test_console_sem_token_configurado_503(cliente, monkeypatch):
    monkeypatch.setenv("AVALIADOR_ADMIN_TOKEN", "")
    resposta = cliente.get("/v1/comercial/clientes", headers=ADMIN)
    assert resposta.status_code == 503
    assert resposta.json()["erro"] == "console_nao_configurado"


def test_predict_com_chave_valida_conta_uso(cliente, nova_chave):
    chave = {"X-API-Key": nova_chave["chave"]}
    antes = cliente.get("/v1/comercial/uso", headers=chave).json()["usadas_mes"]
    assert cliente.post("/v1/predict", json=EXEMPLO_IMOVEL, headers=chave).status_code == 200
    uso = cliente.get("/v1/comercial/uso", headers=chave).json()
    assert uso["usadas_mes"] == antes + 1
    assert uso["restantes"] == 1000 - uso["usadas_mes"]
    assert uso["cliente"] == CLIENTE["nome"]


def test_predict_sem_chave_continua_aberto(cliente):
    assert cliente.post("/v1/predict", json=EXEMPLO_IMOVEL).status_code == 200
    assert cliente.post("/v1/predict", json=EXEMPLO_IMOVEL, headers={"X-Origem": "portal"}).status_code == 200
    origens = {o["origem"] for o in cliente.get("/v1/relatorios/resumo").json()["por_origem"]}
    assert {"api", "anonima", "portal"} <= origens


def test_chave_invalida_401(cliente):
    resposta = cliente.post("/v1/predict", json=EXEMPLO_IMOVEL, headers={"X-API-Key": "aval_inexistente"})
    assert resposta.status_code == 401
    assert resposta.json()["erro"] == "chave_invalida"


def test_chave_revogada_403(cliente):
    emitida = cliente.post("/v1/comercial/chaves", json={**CLIENTE, "plano": "profissional"}, headers=ADMIN).json()
    revogacao = cliente.post(f"/v1/comercial/chaves/{emitida['chave_id']}/revogar", headers=ADMIN)
    assert revogacao.status_code == 200
    resposta = cliente.post("/v1/predict", json=EXEMPLO_IMOVEL, headers={"X-API-Key": emitida["chave"]})
    assert resposta.status_code == 403
    assert resposta.json()["erro"] == "chave_revogada"
    lista = cliente.get("/v1/comercial/clientes", headers=ADMIN).json()
    assert next(c for c in lista if c["chave_id"] == emitida["chave_id"])["ativa"] is False


def test_limite_excedido_429(cliente, nova_chave):
    banco = cliente.app.state.banco
    banco.executar("UPDATE chaves SET limite_mensal = 0 WHERE id = ?", (nova_chave["chave_id"],))
    try:
        resposta = cliente.post("/v1/predict", json=EXEMPLO_IMOVEL, headers={"X-API-Key": nova_chave["chave"]})
        assert resposta.status_code == 429
        assert resposta.json()["erro"] == "limite_excedido"
    finally:
        banco.executar("UPDATE chaves SET limite_mensal = 1000 WHERE id = ?", (nova_chave["chave_id"],))


def test_email_em_modo_arquivo(cliente, nova_chave):
    email = nova_chave["email"]
    assert email["modo"] == "arquivo" and email["enviado"] is False
    arquivo = cliente.app.state.banco.um("SELECT arquivo FROM envios_email WHERE id = ?", (email["envio_id"],))["arquivo"]
    assert Path(arquivo).suffix == ".eml" and Path(arquivo).exists()
    previa = cliente.get(f"/v1/comercial/emails/{email['envio_id']}", headers=ADMIN)
    assert previa.status_code == 200
    # A cópia em disco nunca guarda a chave completa: só o prefixo, marcado como oculto
    assert nova_chave["chave"] not in previa.text and "(oculta)" in previa.text
    assert nova_chave["chave"] not in Path(arquivo).read_text(encoding="utf-8", errors="ignore")


def test_relatorios_e_esquema_200(cliente):
    resumo = cliente.get("/v1/relatorios/resumo")
    assert resumo.status_code == 200 and resumo.json()["total_predicoes"] >= 3
    recentes = cliente.get("/v1/relatorios/predicoes", params={"limite": 5})
    assert recentes.status_code == 200 and len(recentes.json()) <= 5
    esquema = cliente.get("/v1/relatorios/esquema")
    assert esquema.status_code == 200
    nomes = {t["nome"] for t in esquema.json()["tabelas"]}
    assert {"clientes", "chaves", "predicoes", "envios_email"} <= nomes
    assert cliente.get("/v1/relatorios/predicoes", params={"limite": 500}).status_code == 422


def test_plano_invalido_422_em_portugues(cliente):
    resposta = cliente.post("/v1/comercial/chaves", headers=ADMIN,
                            json={"nome": "Plano", "email": "plano@exemplo.com", "plano": "ouro"})
    assert resposta.status_code == 422
    assert "Input should" not in resposta.text and "opção inválida" in resposta.text
