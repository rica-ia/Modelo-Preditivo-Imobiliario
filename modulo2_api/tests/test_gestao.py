"""Plataforma de gestão: vendas reais, laudos, exportações e relatórios de mercado."""

import csv
import io

import pytest
from fastapi.testclient import TestClient

from modulo2_api.app import main
from modulo2_api.app.schemas.imovel import EXEMPLO_IMOVEL


@pytest.fixture(scope="module")
def cliente(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("AVALIADOR_BANCO", str(tmp_path_factory.mktemp("banco") / "gestao.db"))
        with TestClient(main.app) as cliente:
            yield cliente


def test_carga_inicial_e_indices(cliente):
    banco = cliente.app.state.banco
    assert banco.um("SELECT COUNT(*) AS n FROM vendas_historicas")["n"] == 21613
    amostra = banco.um("SELECT COUNT(*) AS n FROM avaliacoes WHERE origem = 'amostra_base'")["n"]
    assert 280 <= amostra <= 320
    assert banco.um("SELECT COUNT(*) AS n FROM avaliacoes WHERE preco_real_usd IS NULL AND origem = 'amostra_base'")["n"] == 0
    tabelas = {t["nome"]: t for t in cliente.get("/v1/relatorios/esquema").json()["tabelas"]}
    indices_vendas = {i["nome"] for i in tabelas["vendas_historicas"]["indices"]}
    assert {"idx_vendas_cep", "idx_vendas_quartos", "idx_vendas_faixa", "idx_vendas_cidade", "idx_vendas_data"} <= indices_vendas
    assert {"idx_avaliacoes_cep", "idx_avaliacoes_origem"} <= {i["nome"] for i in tabelas["avaliacoes"]["indices"]}
    assert tabelas["vendas_historicas"]["linhas"] == 21613


def test_carga_nao_duplica_ao_reiniciar(cliente):
    from modulo2_api.app.services.carga import carga_inicial

    assert carga_inicial(cliente.app.state.banco, cliente.app.state.servico_modelo) == {"vendas": 0, "avaliacoes": 0}


def test_criar_avaliacao_201_recalcula_no_servidor(cliente):
    resposta = cliente.post(
        "/v1/avaliacoes", json={"titulo": "Casa em Redmond", "responsavel": "Ricardo", "imovel": EXEMPLO_IMOVEL}
    )
    assert resposta.status_code == 201
    laudo = resposta.json()
    direto = cliente.post("/v1/predict", json=EXEMPLO_IMOVEL).json()
    assert laudo["preco_estimado_usd"] == direto["preco_estimado_usd"]
    assert laudo["origem"] == "portal" and laudo["cidade"] == "Redmond"
    assert cliente.get(f"/v1/avaliacoes/{laudo['id']}").status_code == 200


def test_avaliacao_rejeita_preco_enviado_pelo_cliente_422(cliente):
    corpo = {"titulo": "Tentativa", "imovel": EXEMPLO_IMOVEL, "preco_estimado_usd": 1}
    assert cliente.post("/v1/avaliacoes", json=corpo).status_code == 422


def test_filtros_e_paginacao(cliente):
    resposta = cliente.get("/v1/avaliacoes", params={"cidade": "Seattle", "quartos": 3, "limite": 5})
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["limite"] == 5 and len(corpo["itens"]) <= 5
    assert all(i["cidade"] == "Seattle" and i["quartos"] == 3 for i in corpo["itens"])
    caros = cliente.get("/v1/avaliacoes", params={"preco_min": 800000, "ordenacao": "preco_asc"}).json()["itens"]
    assert all(i["preco_estimado_usd"] >= 800000 for i in caros)
    assert [i["preco_estimado_usd"] for i in caros] == sorted(i["preco_estimado_usd"] for i in caros)
    assert cliente.get("/v1/avaliacoes", params={"busca": "Redmond"}).json()["total"] >= 1
    assert cliente.get("/v1/avaliacoes", params={"limite": 101}).status_code == 422


def test_laudo_html_200(cliente):
    primeiro = cliente.get("/v1/avaliacoes", params={"origem": "amostra_base", "limite": 1}).json()["itens"][0]
    resposta = cliente.get(f"/v1/avaliacoes/{primeiro['id']}/laudo")
    assert resposta.status_code == 200
    assert resposta.headers["content-type"].startswith("text/html")
    assert "Laudo de avaliação" in resposta.text and "Comparáveis" in resposta.text and "@media print" in resposta.text


def test_avaliacao_inexistente_404(cliente):
    for rota in ("/v1/avaliacoes/999999", "/v1/avaliacoes/999999/laudo"):
        resposta = cliente.get(rota)
        assert resposta.status_code == 404
        assert resposta.json()["erro"] == "nao_encontrado"


def test_exportar_csv_excel_ptbr(cliente):
    resposta = cliente.get("/v1/avaliacoes/exportar", params={"formato": "csv", "cidade": "Seattle"})
    assert resposta.status_code == 200
    assert "attachment" in resposta.headers["content-disposition"]
    assert resposta.content.startswith(b"\xef\xbb\xbf")
    linhas = list(csv.reader(io.StringIO(resposta.content.decode("utf-8-sig")), delimiter=";"))
    assert linhas[0][:4] == ["id", "criado_em", "titulo", "responsavel"]
    assert "preco_estimado_usd" in linhas[0] and len(linhas) > 1
    json_export = cliente.get("/v1/avaliacoes/exportar", params={"formato": "json", "quartos": 3})
    assert json_export.status_code == 200 and all(i["quartos"] == 3 for i in json_export.json())


@pytest.mark.parametrize("dimensao", ["quartos", "cidade", "faixa_preco", "ano_venda"])
def test_relatorio_de_mercado(cliente, dimensao):
    resposta = cliente.get("/v1/relatorios/mercado", params={"dimensao": dimensao})
    assert resposta.status_code == 200
    linhas = resposta.json()["linhas"]
    assert sum(linha["vendas"] for linha in linhas) == 21613
    assert all(linha["p25_usd"] <= linha["preco_mediano_usd"] <= linha["p75_usd"] for linha in linhas)


def test_relatorio_de_mercado_filtrado_e_exportado(cliente):
    seattle = cliente.get("/v1/relatorios/mercado", params={"dimensao": "quartos", "cidade": "Seattle"}).json()
    assert 0 < sum(linha["vendas"] for linha in seattle["linhas"]) < 21613
    arquivo = cliente.get("/v1/relatorios/mercado/exportar", params={"formato": "csv", "dimensao": "cidade"})
    assert arquivo.status_code == 200 and arquivo.content.startswith(b"\xef\xbb\xbfgrupo;vendas")


def test_mapa3d_sem_chave_indisponivel(cliente):
    resposta = cliente.get("/v1/config/mapa3d")
    assert resposta.status_code == 200
    assert resposta.json() == {"disponivel": False, "chave": None, "provedor": "Google Photorealistic 3D Tiles"}
