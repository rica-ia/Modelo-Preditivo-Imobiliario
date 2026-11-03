"""Administração do banco: seções, busca, paginação, whitelist, exportação, faturas, exclusão, saúde e backup."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from modulo2_api.app import main

ADMIN = {"X-Admin-Token": "token-de-teste"}
BASE = "/v1/admin/banco"

# Mesmo formato da tabela de faturamento do esquema; criada aqui só se o banco ainda não a tiver.
FATURAS = """
CREATE TABLE IF NOT EXISTS faturas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id   INTEGER NOT NULL REFERENCES clientes (id),
    chave_id     INTEGER REFERENCES chaves (id),
    competencia  TEXT NOT NULL,
    plano        TEXT NOT NULL,
    valor_usd    REAL NOT NULL,
    predicoes    INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL CHECK (status IN ('paga', 'em_aberto', 'vencida', 'cancelada')),
    emitida_em   TEXT NOT NULL,
    vencimento   TEXT NOT NULL,
    paga_em      TEXT
)
"""


@pytest.fixture(scope="module")
def cliente(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AVALIADOR_BANCO", str(tmp_path_factory.mktemp("banco") / "admin_banco.db"))
        mp.setenv("AVALIADOR_ADMIN_TOKEN", "token-de-teste")
        mp.setenv("SMTP_USUARIO", "")
        mp.setenv("SMTP_SENHA_APP", "")
        with TestClient(main.app) as cliente:
            with sqlite3.connect(main.app.state.banco.caminho) as con:
                con.execute(FATURAS)
            yield cliente


@pytest.fixture(scope="module")
def emitido(cliente):
    dados = {"nome": "Zuleica Tabelião", "email": "zuleica@exemplo.com", "empresa": "Cartório Exemplo",
             "plano": "profissional"}
    resposta = cliente.post("/v1/comercial/chaves", json=dados, headers=ADMIN)
    assert resposta.status_code == 201
    return resposta.json()


def criar_fatura(cliente, emitido, status="em_aberto", competencia="2026-10") -> int:
    with sqlite3.connect(main.app.state.banco.caminho) as con:
        cursor = con.execute(
            "INSERT INTO faturas (cliente_id, chave_id, competencia, plano, valor_usd, predicoes, status, emitida_em,"
            " vencimento) VALUES (?, ?, ?, 'profissional', 199.0, 42, ?, '2026-11-01', '2026-11-10')",
            (emitido["cliente_id"], emitido["chave_id"], competencia, status),
        )
        return cursor.lastrowid


def test_sem_admin_401(cliente):
    for rota in ("/secoes", "/saude", "/backup", "/clientes", "/clientes/1", "/clientes/exportar"):
        resposta = cliente.get(BASE + rota)
        assert resposta.status_code == 401, rota
        assert resposta.json()["erro"] == "nao_autorizado"
    assert cliente.delete(BASE + "/avaliacoes/1").status_code == 401
    assert cliente.patch(BASE + "/faturas/1", json={"status": "paga"}).status_code == 401


def test_secoes_whitelist_e_campos_sensiveis(cliente, emitido):
    resposta = cliente.get(BASE + "/secoes", headers=ADMIN)
    assert resposta.status_code == 200
    secoes = {s["secao"]: s for s in resposta.json()}
    assert list(secoes) == ["clientes", "chaves", "faturas", "envios_email", "eventos_comerciais", "avaliacoes",
                            "predicoes", "vendas_historicas", "modelos"]
    assert secoes["faturas"]["titulo"] == "Faturamento"
    assert secoes["clientes"]["total"] >= 1
    assert "hash_sha256" not in secoes["chaves"]["colunas"]
    assert "entrada_json" not in secoes["avaliacoes"]["colunas"]
    assert secoes["chaves"]["colunas_busca"] == ["prefixo", "cliente_nome"]
    assert {s for s, c in secoes.items() if c["pode_excluir"]} == {"avaliacoes", "faturas"}
    assert {s for s, c in secoes.items() if c["pode_editar"]} == {"faturas"}


def test_busca_parametrizada_e_join(cliente, emitido):
    resposta = cliente.get(BASE + "/clientes", params={"busca": "Zuleica"}, headers=ADMIN)
    corpo = resposta.json()
    assert resposta.status_code == 200 and corpo["total"] == 1
    assert corpo["linhas"][0]["email"] == "zuleica@exemplo.com"
    chaves = cliente.get(BASE + "/chaves", params={"busca": "tabelião"}, headers=ADMIN).json()
    assert chaves["total"] == 1
    linha = chaves["linhas"][0]
    assert linha["cliente_nome"] == "Zuleica Tabelião" and linha["situacao"] == "ativa"
    assert "hash_sha256" not in linha
    eventos = cliente.get(BASE + "/eventos_comerciais", params={"busca": "Zuleica"}, headers=ADMIN).json()
    assert eventos["total"] >= 1 and eventos["linhas"][0]["tipo"] == "emissao"
    # Curingas do LIKE são tratados como texto: "%" sozinho não casa com tudo
    assert cliente.get(BASE + "/clientes", params={"busca": "%"}, headers=ADMIN).json()["total"] == 0


def test_paginacao_e_ordem(cliente):
    resposta = cliente.get(BASE + "/vendas_historicas", params={"pagina": 2, "por_pagina": 5, "ordem": "preco_usd",
                                                                "direcao": "asc"}, headers=ADMIN)
    corpo = resposta.json()
    assert resposta.status_code == 200
    assert corpo["pagina"] == 2 and corpo["por_pagina"] == 5 and len(corpo["linhas"]) == 5
    assert corpo["paginas"] == -(-corpo["total"] // 5)
    precos = [linha["preco_usd"] for linha in corpo["linhas"]]
    assert precos == sorted(precos)
    assert cliente.get(BASE + "/vendas_historicas", params={"por_pagina": 101}, headers=ADMIN).status_code == 422
    assert cliente.get(BASE + "/vendas_historicas", params={"pagina": 0}, headers=ADMIN).status_code == 422


def test_ordem_fora_da_whitelist_e_injecao(cliente):
    for ordem in ("1;DROP TABLE clientes", "hash_sha256", "nome; --"):
        resposta = cliente.get(BASE + "/clientes", params={"ordem": ordem}, headers=ADMIN)
        assert resposta.status_code == 400 and resposta.json()["erro"] == "regra_de_negocio"
    injecao = cliente.get(BASE + "/clientes", params={"busca": "' OR 1=1 --"}, headers=ADMIN)
    assert injecao.status_code == 200 and injecao.json()["total"] == 0
    assert cliente.get(BASE + "/clientes", headers=ADMIN).json()["total"] >= 1  # tabela intacta


def test_secao_e_registro_inexistentes_404(cliente):
    assert cliente.get(BASE + "/sqlite_master", headers=ADMIN).status_code == 404
    assert cliente.get(BASE + "/clientes/999999", headers=ADMIN).json()["erro"] == "nao_encontrado"
    assert cliente.get(BASE + "/clientes/999999", headers=ADMIN).status_code == 404


def test_detalhe_sem_hash_e_laudo_com_entrada(cliente, emitido):
    chave = cliente.get(f"{BASE}/chaves/{emitido['chave_id']}", headers=ADMIN).json()
    assert chave["secao"] == "chaves" and chave["registro"]["cliente_nome"] == "Zuleica Tabelião"
    assert "hash_sha256" not in chave["registro"]
    laudos = cliente.get(BASE + "/avaliacoes", params={"por_pagina": 1}, headers=ADMIN).json()
    assert laudos["total"] > 0
    laudo = cliente.get(f"{BASE}/avaliacoes/{laudos['linhas'][0]['id']}", headers=ADMIN).json()
    assert "entrada_json" in laudo["registro"]
    venda = cliente.get(BASE + "/vendas_historicas", params={"por_pagina": 1}, headers=ADMIN).json()["linhas"][0]
    detalhe = cliente.get(f"{BASE}/vendas_historicas/{venda['id_venda']}", headers=ADMIN).json()
    assert detalhe["registro"]["id_venda"] == venda["id_venda"]


def test_exportar_csv_e_json(cliente, emitido):
    resposta = cliente.get(BASE + "/clientes/exportar", params={"busca": "Zuleica"}, headers=ADMIN)
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/csv")
    assert 'filename="banco_clientes_' in resposta.headers["content-disposition"]
    assert resposta.content.startswith(b"\xef\xbb\xbf")
    linhas = resposta.content.decode("utf-8-sig").splitlines()
    assert linhas[0].startswith("id;nome;email") and len(linhas) == 2 and "Zuleica" in linhas[1]
    json_ = cliente.get(BASE + "/chaves/exportar", params={"formato": "json"}, headers=ADMIN)
    assert json_.status_code == 200 and json_.headers["content-type"].startswith("application/json")
    assert all("hash_sha256" not in linha for linha in json_.json())


def test_baixa_de_fatura(cliente, emitido):
    fatura_id = criar_fatura(cliente, emitido)
    paga = cliente.patch(f"{BASE}/faturas/{fatura_id}", json={"status": "paga"}, headers=ADMIN)
    assert paga.status_code == 200
    registro = paga.json()["registro"]
    assert registro["status"] == "paga" and registro["paga_em"] and registro["cliente_nome"] == "Zuleica Tabelião"
    reaberta = cliente.patch(f"{BASE}/faturas/{fatura_id}", json={"status": "em_aberto"}, headers=ADMIN).json()
    assert reaberta["registro"]["status"] == "em_aberto" and reaberta["registro"]["paga_em"] is None
    assert cliente.patch(f"{BASE}/faturas/{fatura_id}", json={"status": "quitada"}, headers=ADMIN).status_code == 422
    assert cliente.patch(f"{BASE}/faturas/999999", json={"status": "paga"}, headers=ADMIN).status_code == 404
    busca = cliente.get(BASE + "/faturas", params={"busca": "Zuleica"}, headers=ADMIN).json()
    assert busca["total"] >= 1 and busca["linhas"][0]["competencia"] == "2026-10"


def test_exclusao_permitida_e_proibida(cliente, emitido):
    fatura_id = criar_fatura(cliente, emitido, status="cancelada", competencia="2026-09")
    excluida = cliente.delete(f"{BASE}/faturas/{fatura_id}", headers=ADMIN)
    assert excluida.status_code == 200 and excluida.json() == {"secao": "faturas", "id": fatura_id, "excluido": True}
    assert cliente.get(f"{BASE}/faturas/{fatura_id}", headers=ADMIN).status_code == 404

    laudo_id = cliente.get(BASE + "/avaliacoes", params={"por_pagina": 1}, headers=ADMIN).json()["linhas"][0]["id"]
    assert cliente.delete(f"{BASE}/avaliacoes/{laudo_id}", headers=ADMIN).status_code == 200
    assert cliente.get(f"{BASE}/avaliacoes/{laudo_id}", headers=ADMIN).status_code == 404
    assert cliente.delete(f"{BASE}/avaliacoes/{laudo_id}", headers=ADMIN).status_code == 404

    for secao in ("clientes", "chaves", "eventos_comerciais", "predicoes", "vendas_historicas", "envios_email"):
        proibida = cliente.delete(f"{BASE}/{secao}/1", headers=ADMIN)
        assert proibida.status_code == 400 and proibida.json()["erro"] == "regra_de_negocio", secao
    assert cliente.get(f"{BASE}/clientes/{emitido['cliente_id']}", headers=ADMIN).status_code == 200


def test_saude(cliente):
    corpo = cliente.get(BASE + "/saude", headers=ADMIN).json()
    assert corpo["integridade"] == "ok" and corpo["tamanho_bytes"] > 0
    tabelas = {t["nome"]: t["linhas"] for t in corpo["tabelas"]}
    assert {"clientes", "chaves", "avaliacoes", "vendas_historicas", "faturas"} <= set(tabelas)
    assert tabelas["vendas_historicas"] > 0
    assert corpo["sinteticos"]["clientes"] >= 0


def test_backup(cliente, tmp_path):
    resposta = cliente.get(BASE + "/backup", headers=ADMIN)
    assert resposta.status_code == 200
    assert resposta.content.startswith(b"SQLite format 3\x00")
    disposicao = resposta.headers["content-disposition"]
    assert "avaliador-backup-" in disposicao and ".db" in disposicao
    copia = tmp_path / "copia.db"
    copia.write_bytes(resposta.content)
    with sqlite3.connect(copia) as con:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert con.execute("SELECT COUNT(*) FROM clientes").fetchone()[0] >= 1


def test_faturas_ausente_some_da_lista(tmp_path):
    from modulo2_api.app.services.admin_banco import ServicoAdminBanco
    from modulo2_api.app.services.banco import Banco
    from modulo2_api.app.services.excecoes import NaoEncontradoError

    banco = Banco(tmp_path / "antigo.db", tmp_path / "nao_usado.sql")
    banco.executar("CREATE TABLE clientes (id INTEGER PRIMARY KEY, nome TEXT, email TEXT, empresa TEXT, plano TEXT,"
                   " criado_em TEXT)")
    banco.executar("CREATE TABLE chaves (id INTEGER PRIMARY KEY, cliente_id INTEGER, prefixo TEXT, hash_sha256 TEXT,"
                   " limite_mensal INTEGER, criada_em TEXT, revogada_em TEXT, suspensa_em TEXT)")
    servico = ServicoAdminBanco(banco)
    secoes = {s["secao"]: s for s in servico.secoes()}
    assert set(secoes) == {"clientes", "chaves"}
    assert "sintetico" not in secoes["clientes"]["colunas"]
    with pytest.raises(NaoEncontradoError):
        servico.listar("faturas")
    assert servico.saude()["sinteticos"] == {"clientes": 0}
