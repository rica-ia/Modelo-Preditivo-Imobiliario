"""Acesso ao console com senha e segundo fator (TOTP, RFC 6238)."""

import time

import pytest
from fastapi.testclient import TestClient

from modulo2_api.app import main
from modulo2_api.app.services import acesso as servico_acesso
from modulo2_api.app.services.acesso import ServicoAcesso, codigo_confere, gerar_segredo, hotp, totp, uri_autenticador

SENHA = "senha-de-teste"
NOVA_CHAVE = {"nome": "Cliente 2FA", "email": "cliente2fa@exemplo.com", "plano": "basico"}


def test_totp_vetores_do_rfc_6238():
    chave = b"12345678901234567890"
    vetores = {59: "94287082", 1111111109: "07081804", 1111111111: "14050471",
               1234567890: "89005924", 2000000000: "69279037", 20000000000: "65353130"}
    for instante, esperado in vetores.items():
        assert hotp(chave, instante // 30, digitos=8) == esperado


def test_codigo_aceita_uma_janela_de_tolerancia():
    segredo = gerar_segredo()
    agora = 1_800_000_000
    assert codigo_confere(segredo, totp(segredo, agora - 30), agora)
    assert codigo_confere(segredo, totp(segredo, agora + 30), agora)
    assert not codigo_confere(segredo, totp(segredo, agora - 90), agora)
    assert not codigo_confere(segredo, "12a456", agora)


@pytest.fixture()
def cliente_2fa(monkeypatch):
    segredo = gerar_segredo()
    monkeypatch.setenv("AVALIADOR_TOTP_SEGREDO", segredo)
    monkeypatch.setenv("AVALIADOR_SENHA_ACESSO", SENHA)
    with TestClient(main.app, raise_server_exceptions=False) as cliente:
        main.app.state.acesso = ServicoAcesso()  # tentativas e sessões zeradas a cada teste
        yield cliente, segredo


def test_sem_segredo_2fa_desligado():
    with TestClient(main.app) as cliente:
        assert cliente.get("/v1/acesso/estado").json() == {"exige_2fa": False}


def test_entrar_200_e_sessao_aceita_no_console(cliente_2fa):
    cliente, segredo = cliente_2fa
    assert cliente.get("/v1/acesso/estado").json() == {"exige_2fa": True}
    resposta = cliente.post("/v1/acesso/entrar", json={"senha": SENHA, "codigo": totp(segredo)})
    assert resposta.status_code == 200
    sessao = resposta.json()["sessao"]
    assert len(sessao) >= 40 and resposta.json()["expira_em"]
    console = cliente.get("/v1/comercial/clientes", headers={"X-Admin-Sessao": sessao})
    assert console.status_code == 200
    # Na sessão, emitir chave pede a senha da conta de novo
    sem_senha = cliente.post("/v1/comercial/chaves", json=NOVA_CHAVE, headers={"X-Admin-Sessao": sessao})
    assert sem_senha.status_code == 401 and sem_senha.json()["erro"] == "acesso_negado"
    assert cliente.post("/v1/comercial/chaves", json=NOVA_CHAVE,
                        headers={"X-Admin-Sessao": sessao, "X-Senha-Conta": "errada"}).status_code == 401
    criada = cliente.post("/v1/comercial/chaves", json=NOVA_CHAVE,
                          headers={"X-Admin-Sessao": sessao, "X-Senha-Conta": SENHA})
    assert criada.status_code == 201
    # O token de administrador (scripts) segue sem a confirmação
    assert cliente.post("/v1/comercial/chaves", json=NOVA_CHAVE, headers={"X-Admin-Token": "token-de-teste"}).status_code == 201
    assert cliente.post("/v1/acesso/sair", headers={"X-Admin-Sessao": sessao}).status_code == 200
    assert cliente.get("/v1/comercial/clientes", headers={"X-Admin-Sessao": sessao}).status_code == 401


def test_senha_ou_codigo_errados_401(cliente_2fa):
    cliente, segredo = cliente_2fa
    errada = cliente.post("/v1/acesso/entrar", json={"senha": "outra", "codigo": totp(segredo)})
    assert errada.status_code == 401 and errada.json()["erro"] == "acesso_negado"
    codigo = "000000" if totp(segredo) != "000000" else "111111"
    errado = cliente.post("/v1/acesso/entrar", json={"senha": SENHA, "codigo": codigo})
    assert errado.status_code == 401 and "incorretos" in errado.json()["mensagem"]


def test_codigo_mal_formado_422_em_portugues(cliente_2fa):
    cliente, _ = cliente_2fa
    resposta = cliente.post("/v1/acesso/entrar", json={"senha": SENHA, "codigo": "12ab"})
    assert resposta.status_code == 422 and resposta.json()["erro"] == "dados_invalidos"


def test_sexta_tentativa_429_e_bloqueio(cliente_2fa):
    cliente, segredo = cliente_2fa
    for _ in range(5):
        assert cliente.post("/v1/acesso/entrar", json={"senha": "x", "codigo": "123456"}).status_code == 401
    # 6ª tentativa: bloqueada, mesmo com a senha e o código certos
    sexta = cliente.post("/v1/acesso/entrar", json={"senha": SENHA, "codigo": totp(segredo)})
    assert sexta.status_code == 429 and sexta.json()["erro"] == "muitas_tentativas"


def test_sessao_inventada_ou_expirada_401(cliente_2fa, monkeypatch):
    cliente, segredo = cliente_2fa
    inventada = cliente.get("/v1/comercial/clientes", headers={"X-Admin-Sessao": "sessao-inventada"})
    assert inventada.status_code == 401 and inventada.json()["erro"] == "nao_autorizado"
    sessao = cliente.post("/v1/acesso/entrar", json={"senha": SENHA, "codigo": totp(segredo)}).json()["sessao"]
    futuro = time.time() + servico_acesso.VALIDADE_SESSAO_S + 1
    monkeypatch.setattr(servico_acesso.time, "time", lambda: futuro)
    assert cliente.get("/v1/comercial/clientes", headers={"X-Admin-Sessao": sessao}).status_code == 401


def test_predicao_publica_continua_aberta_com_2fa(cliente_2fa):
    cliente, _ = cliente_2fa
    from modulo2_api.app.schemas.imovel import EXEMPLO_IMOVEL
    assert cliente.post("/v1/predict", json=EXEMPLO_IMOVEL).status_code == 200


def test_senha_propria_guardada_como_hash(monkeypatch):
    from modulo2_api.app.services.acesso import hash_senha, senha_confere

    guardado = hash_senha("Senha da conta 2026", iteracoes=1_000)
    assert "Senha da conta" not in guardado and guardado.startswith("pbkdf2_sha256$1000$")
    monkeypatch.setenv("AVALIADOR_SENHA_HASH", guardado)
    monkeypatch.setenv("AVALIADOR_SENHA_ACESSO", "outra")
    assert senha_confere("Senha da conta 2026")
    assert not senha_confere("outra") and not senha_confere("senha da conta 2026")
    monkeypatch.setenv("AVALIADOR_SENHA_HASH", "corrompido")
    assert not senha_confere("Senha da conta 2026")


def test_entrar_com_senha_em_hash(cliente_2fa, monkeypatch):
    from modulo2_api.app.services.acesso import hash_senha

    cliente, segredo = cliente_2fa
    monkeypatch.setenv("AVALIADOR_SENHA_HASH", hash_senha("Minha senha", iteracoes=1_000))
    assert cliente.post("/v1/acesso/entrar", json={"senha": "Minha senha", "codigo": totp(segredo)}).status_code == 200


def test_qr_quadrado_e_uri_curta():
    import qrcode

    from modulo2_api.ferramentas.configurar_2fa import desenho_quadrado

    qr = qrcode.QRCode(border=1, error_correction=qrcode.constants.ERROR_CORRECT_L)
    qr.add_data(uri_autenticador(gerar_segredo()))
    qr.make(fit=True)
    linhas = desenho_quadrado(qr.get_matrix()).splitlines()
    assert qr.version == 4 and len(linhas[0]) == 35 and len(linhas) == 18  # 35 x 36 pontos ~ quadrado


def test_entrada_de_contingencia_so_local_e_com_token(cliente_2fa):
    cliente, _ = cliente_2fa
    # O TestClient se apresenta como host "testclient": fora da máquina local, mesmo com o token certo
    assert cliente.post("/v1/acesso/entrar-local", headers={"X-Admin-Token": "token-de-teste"}).status_code == 401
    with TestClient(main.app, client=("127.0.0.1", 50000)) as local:
        assert local.post("/v1/acesso/entrar-local").status_code == 401
        assert local.post("/v1/acesso/entrar-local", headers={"X-Admin-Token": "errado"}).status_code == 401
        r = local.post("/v1/acesso/entrar-local", headers={"X-Admin-Token": "token-de-teste"})
        assert r.status_code == 200
        assert local.get("/v1/comercial/clientes", headers={"X-Admin-Sessao": r.json()["sessao"]}).status_code == 200


def test_entrada_so_com_senha_apenas_local(cliente_2fa):
    cliente, _ = cliente_2fa
    assert cliente.post("/v1/acesso/entrar-senha", json={"senha": SENHA}).status_code == 401  # host "testclient"
    with TestClient(main.app, client=("127.0.0.1", 50001)) as local:
        assert local.post("/v1/acesso/entrar-senha", json={"senha": "errada"}).status_code == 401
        r = local.post("/v1/acesso/entrar-senha", json={"senha": SENHA})
        assert r.status_code == 200
        assert local.get("/v1/comercial/clientes", headers={"X-Admin-Sessao": r.json()["sessao"]}).status_code == 200


def test_sessao_sobrevive_ao_reinicio(tmp_path):
    arquivo = tmp_path / "sessoes.json"
    primeira = ServicoAcesso(arquivo=arquivo)
    sessao = primeira.abrir_sessao()["sessao"]
    assert sessao not in arquivo.read_text(encoding="utf-8")  # só o hash vai para o disco
    reiniciada = ServicoAcesso(arquivo=arquivo)
    assert reiniciada.sessao_valida(sessao)
    reiniciada.sair(sessao)
    assert not ServicoAcesso(arquivo=arquivo).sessao_valida(sessao)
