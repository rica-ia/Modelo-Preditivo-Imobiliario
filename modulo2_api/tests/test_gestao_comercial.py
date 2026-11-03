"""Gestão comercial: troca de plano, suspensão, troca de chave, edição, ficha e faturamento."""

import pytest
from fastapi.testclient import TestClient

from modulo2_api.app import main
from modulo2_api.app.schemas.imovel import EXEMPLO_IMOVEL

ADMIN = {"X-Admin-Token": "token-de-teste"}


@pytest.fixture(scope="module")
def cliente(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AVALIADOR_BANCO", str(tmp_path_factory.mktemp("banco") / "gestao.db"))
        mp.setenv("AVALIADOR_ADMIN_TOKEN", "token-de-teste")
        mp.setenv("SMTP_USUARIO", "")
        mp.setenv("SMTP_SENHA_APP", "")
        with TestClient(main.app) as cliente:
            yield cliente


def emitir(cliente, plano="basico", nome="Cliente Gestão"):
    dados = {"nome": nome, "email": "gestao@exemplo.com", "empresa": "Exemplo", "plano": plano}
    resposta = cliente.post("/v1/comercial/chaves", json=dados, headers=ADMIN)
    assert resposta.status_code == 201
    return resposta.json()


def prever(cliente, chave):
    return cliente.post("/v1/predict", json=EXEMPLO_IMOVEL, headers={"X-API-Key": chave})


def test_troca_de_plano_muda_limite_e_registra_evento(cliente):
    nova = emitir(cliente)
    resposta = cliente.patch(f"/v1/comercial/chaves/{nova['chave_id']}/plano", json={"plano": "profissional"}, headers=ADMIN)
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["movimento"] == "upgrade" and corpo["limite_mensal"] == 1_000 and corpo["preco_mensal_usd"] == 199.0
    assert cliente.get("/v1/comercial/uso", headers={"X-API-Key": nova["chave"]}).json()["limite_mensal"] == 1_000
    ficha = cliente.get(f"/v1/comercial/clientes/{nova['cliente_id']}", headers=ADMIN).json()
    assert [e["tipo"] for e in ficha["eventos"]] == ["troca_plano", "emissao"]
    assert "Básico → Profissional" in ficha["eventos"][0]["detalhe"]


def test_mesmo_plano_400(cliente):
    nova = emitir(cliente)
    resposta = cliente.patch(f"/v1/comercial/chaves/{nova['chave_id']}/plano", json={"plano": "basico"}, headers=ADMIN)
    assert resposta.status_code == 400
    assert resposta.json()["erro"] == "regra_de_negocio"


def test_suspensao_bloqueia_e_reativacao_libera(cliente):
    nova = emitir(cliente)
    assert prever(cliente, nova["chave"]).status_code == 200
    suspensa = cliente.post(f"/v1/comercial/chaves/{nova['chave_id']}/suspender", json={"motivo": "Fatura em atraso"},
                            headers=ADMIN)
    assert suspensa.json()["situacao"] == "suspensa"
    bloqueada = prever(cliente, nova["chave"])
    assert bloqueada.status_code == 403 and bloqueada.json()["erro"] == "chave_suspensa"
    linha = next(c for c in cliente.get("/v1/comercial/clientes", headers=ADMIN).json() if c["chave_id"] == nova["chave_id"])
    assert linha["situacao"] == "suspensa" and linha["ativa"]
    assert cliente.post(f"/v1/comercial/chaves/{nova['chave_id']}/reativar", headers=ADMIN).json()["situacao"] == "ativa"
    assert prever(cliente, nova["chave"]).status_code == 200


def test_rotacao_revoga_a_antiga_e_entrega_nova_chave(cliente):
    nova = emitir(cliente, plano="empresarial")
    resposta = cliente.post(f"/v1/comercial/chaves/{nova['chave_id']}/rotacionar", headers=ADMIN)
    assert resposta.status_code == 201
    trocada = resposta.json()
    assert trocada["chave_anterior_id"] == nova["chave_id"] and trocada["chave"] != nova["chave"]
    assert trocada["cliente_id"] == nova["cliente_id"] and trocada["plano"] == "empresarial"
    assert trocada["email"]["envio_id"]
    assert prever(cliente, nova["chave"]).status_code == 403
    assert prever(cliente, trocada["chave"]).status_code == 200
    revogada = cliente.patch(f"/v1/comercial/chaves/{nova['chave_id']}/plano", json={"plano": "basico"}, headers=ADMIN)
    assert revogada.status_code == 400


def test_edicao_do_cliente_registra_os_campos(cliente):
    nova = emitir(cliente)
    resposta = cliente.patch(f"/v1/comercial/clientes/{nova['cliente_id']}",
                             json={"empresa": "Exemplo Ltda.", "email": "novo@exemplo.com"}, headers=ADMIN)
    assert resposta.status_code == 200
    ficha = resposta.json()
    assert ficha["empresa"] == "Exemplo Ltda." and ficha["email"] == "novo@exemplo.com"
    assert ficha["eventos"][0] == {**ficha["eventos"][0], "tipo": "edicao", "detalhe": "alterado: email, empresa"}
    assert cliente.patch(f"/v1/comercial/clientes/{nova['cliente_id']}", json={"email": "invalido"},
                         headers=ADMIN).status_code == 422
    assert cliente.get("/v1/comercial/clientes/99999", headers=ADMIN).status_code == 404
    sem_empresa = cliente.patch(f"/v1/comercial/clientes/{nova['cliente_id']}", json={"empresa": None}, headers=ADMIN)
    assert sem_empresa.json()["empresa"] is None


def test_faturamento_soma_so_chaves_ativas(cliente):
    antes = cliente.get("/v1/comercial/faturamento", headers=ADMIN).json()
    ativa = emitir(cliente, plano="profissional")
    suspensa = emitir(cliente, plano="empresarial")
    cliente.post(f"/v1/comercial/chaves/{suspensa['chave_id']}/suspender", headers=ADMIN)
    depois = cliente.get("/v1/comercial/faturamento", headers=ADMIN).json()
    assert depois["receita_mensal_usd"] == pytest.approx(antes["receita_mensal_usd"] + 199.0)
    assert depois["receita_anual_prevista_usd"] == pytest.approx(depois["receita_mensal_usd"] * 12)
    assert depois["chaves_suspensas"] == antes["chaves_suspensas"] + 1
    profissional = next(p for p in depois["por_plano"] if p["plano"] == "profissional")
    assert profissional["chaves_ativas"] >= 1 and ativa["chave_id"]


def test_consumo_alto_aparece_no_faturamento(cliente):
    nova = emitir(cliente, nome="Cliente Intenso")
    cliente.app.state.banco.executar("UPDATE chaves SET limite_mensal = 2 WHERE id = ?", (nova["chave_id"],))
    for _ in range(2):
        assert prever(cliente, nova["chave"]).status_code == 200
    perto = cliente.get("/v1/comercial/faturamento", headers=ADMIN).json()["perto_do_limite"]
    assert any(p["chave_id"] == nova["chave_id"] and p["consumo_pct"] == 100.0 for p in perto)


@pytest.mark.parametrize("rota", ["/v1/comercial/faturamento", "/v1/comercial/clientes/1"])
def test_gestao_exige_admin(cliente, rota):
    assert cliente.get(rota).status_code == 401
