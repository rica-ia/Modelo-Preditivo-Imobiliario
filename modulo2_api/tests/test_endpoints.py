"""Fase 5: endpoints e códigos HTTP semânticos (200, 400, 422, 500, 503)."""

import pytest
from fastapi.testclient import TestClient

from modulo2_api.app import main
from modulo2_api.app.schemas.imovel import EXEMPLO_IMOVEL


@pytest.fixture(scope="module")
def cliente():
    with TestClient(main.app, raise_server_exceptions=False) as cliente:
        yield cliente


def _imovel(**alteracoes):
    return {**EXEMPLO_IMOVEL, **alteracoes}


# ## 200 OK
def test_health_200(cliente):
    resposta = cliente.get("/health")
    assert resposta.status_code == 200
    assert resposta.json()["modelo_carregado"] is True


def test_predict_200(cliente):
    resposta = cliente.post("/v1/predict", json=_imovel())
    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["moeda"] == "USD"
    faixa = corpo["faixa_provavel_usd"]
    assert faixa["minimo"] < corpo["preco_estimado_usd"] < faixa["maximo"]


def test_predict_lote_200(cliente):
    resposta = cliente.post("/v1/predict/lote", json={"imoveis": [_imovel(), _imovel(area_util_m2=250)]})
    assert resposta.status_code == 200
    precos = [p["preco_estimado_usd"] for p in resposta.json()["previsoes"]]
    assert precos[1] > precos[0]


def test_modelo_e_regioes_200(cliente):
    info = cliente.get("/v1/modelo")
    assert info.status_code == 200
    assert info.json()["metricas"]["teste"]["R2"] > 0.8
    regioes = cliente.get("/v1/regioes")
    assert regioes.status_code == 200
    assert len(regioes.json()) == 70


# ## 422 Unprocessable Entity (Pydantic)
@pytest.mark.parametrize(
    "corpo, campo",
    [
        (_imovel(area_util_m2="cem"), "area_util_m2"),  # texto em campo numérico
        (_imovel(quartos=40), "quartos"),  # fora da faixa
        ({k: v for k, v in EXEMPLO_IMOVEL.items() if k != "cep"}, "cep"),  # campo ausente
        (_imovel(cep="1234"), "cep"),  # padrão inválido
        (_imovel(piscina=True), "piscina"),  # campo desconhecido
    ],
)
def test_predict_422(cliente, corpo, campo):
    resposta = cliente.post("/v1/predict", json=corpo)
    assert resposta.status_code == 422
    corpo_erro = resposta.json()
    assert corpo_erro["erro"] == "dados_invalidos"
    assert any(d["campo"] == campo for d in corpo_erro["detalhes"])


def test_lote_acima_do_limite_422(cliente):
    resposta = cliente.post("/v1/predict/lote", json={"imoveis": [_imovel()] * 21})
    assert resposta.status_code == 422


# ## 400 Bad Request (regra de negócio)
@pytest.mark.parametrize(
    "alteracoes",
    [
        {"area_porao_m2": 300.0},  # porão maior que a área útil
        {"ano_reforma": 1980},  # reforma antes da construção
        {"ano_reforma": 2020},  # reforma depois da base de treino
        {"cep": "98999"},  # CEP fora da região do treino
    ],
)
def test_predict_400(cliente, alteracoes):
    resposta = cliente.post("/v1/predict", json=_imovel(**alteracoes))
    assert resposta.status_code == 400
    assert resposta.json()["erro"] == "regra_de_negocio"


# ## 500 e 503: a API responde JSON limpo em vez de cair
def test_predict_500(cliente, monkeypatch):
    servico = cliente.app.state.servico_modelo

    def falhar(*args, **kwargs):
        raise RuntimeError("falha simulada")

    monkeypatch.setattr(servico.modelo, "predict", falhar)
    resposta = cliente.post("/v1/predict", json=_imovel())
    assert resposta.status_code == 500
    assert resposta.json() == {
        "erro": "erro_interno",
        "mensagem": "Erro inesperado no servidor. Tente novamente.",
    }


def test_predict_503_sem_modelo(cliente, monkeypatch):
    servico = cliente.app.state.servico_modelo
    monkeypatch.setattr(servico, "modelo", None)
    assert cliente.get("/health").json()["modelo_carregado"] is False
    resposta = cliente.post("/v1/predict", json=_imovel())
    assert resposta.status_code == 503
    assert resposta.json()["erro"] == "modelo_indisponivel"


# ## Fase 3 na prática: várias predições sem nenhuma leitura de disco
def test_predicoes_nao_releem_o_artefato(cliente, monkeypatch):
    from modulo2_api.app.services import modelo as servico_modelo

    def proibido(*args, **kwargs):
        raise AssertionError("a rota não pode ler o arquivo .joblib")

    monkeypatch.setattr(servico_modelo.joblib, "load", proibido)
    for _ in range(5):
        assert cliente.post("/v1/predict", json=_imovel()).status_code == 200


# ## 404 e 405 em português
def test_rota_inexistente_404(cliente):
    resposta = cliente.get("/v1/inexistente")
    assert resposta.status_code == 404
    assert resposta.json()["erro"] == "nao_encontrado"


def test_metodo_nao_permitido_405(cliente):
    resposta = cliente.get("/v1/predict")
    assert resposta.status_code == 405
    assert resposta.json()["erro"] == "metodo_nao_permitido"


def test_corpo_nao_utf8_400_em_portugues(cliente):
    resposta = cliente.post(
        "/v1/predict", content="{\"cep\": \"98103\", \"nome\": \"é\"}".encode("latin-1"),
        headers={"Content-Type": "application/json"},
    )
    assert resposta.status_code in (400, 422)
    assert resposta.json()["erro"] in ("corpo_invalido", "dados_invalidos")
    assert "There was an error" not in resposta.text


def test_visao3d_servida_fora_do_schema(cliente):
    resposta = cliente.get("/visao3d")
    assert resposta.status_code == 200
    assert "text/html" in resposta.headers["content-type"]
    assert "/visao3d" not in cliente.get("/openapi.json").json()["paths"]
