"""Comodidades do entorno (Overpass/OpenStreetMap) e o laudo completo, sempre com consulta falsa, sem rede."""

import io
import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

from modulo2_api.app import main
from modulo2_api.app.services import comodidades as modulo
from modulo2_api.app.services.comodidades import (
    ServicoComodidades,
    consulta_overpass,
    haversine_m,
    montar_comodidades,
    tempos,
)
from modulo2_api.app.services.endereco import ServicoEndereco

LAT, LNG = 47.6101, -122.2015
BRUTO = {"elements": [
    {"type": "node", "lat": 47.6105, "lon": -122.2015, "tags": {"amenity": "pharmacy", "name": "CVS Pharmacy"}},
    {"type": "node", "lat": 47.6130, "lon": -122.2015, "tags": {"shop": "supermarket", "name": "Safeway"}},
    {"type": "node", "lat": 47.6102, "lon": -122.2016, "tags": {"highway": "bus_stop", "name": "Bellevue Way & Main St"}},
    {"type": "node", "lat": 47.6103, "lon": -122.2016, "tags": {"highway": "bus_stop", "name": "Bellevue Way & Main St"}},
    {"type": "node", "lat": 47.6110, "lon": -122.2000, "tags": {"highway": "bus_stop"}},
    {"type": "way", "center": {"lat": 47.6125, "lon": -122.2040}, "tags": {"leisure": "park", "name": "Downtown Park"}},
    {"type": "node", "lat": 47.6160, "lon": -122.2015, "tags": {"amenity": "school", "name": "Bellevue High <School>"}},
    {"type": "node", "lat": 47.6400, "lon": -122.2015, "tags": {"amenity": "bank", "name": "Banco longe"}},
    {"type": "node", "lat": 47.6104, "lon": -122.2014, "tags": {"amenity": "cafe", "brand": "Starbucks"}},
    {"type": "node", "lat": 47.6104, "lon": -122.2014, "tags": {"tourism": "hotel", "name": "Fora das categorias"}},
]}


def _bruto_em(lat: float, lng: float) -> dict:
    """O mesmo entorno de BRUTO, deslocado para o ponto consultado."""
    elementos = []
    for el in BRUTO["elements"]:
        novo = json.loads(json.dumps(el))
        alvo = novo.get("center", novo)
        alvo["lat"] += lat - LAT
        alvo["lon"] += lng - LNG
        elementos.append(novo)
    return {"elements": elementos}


def _categoria(resultado: dict, chave: str) -> dict:
    return next(c for c in resultado["categorias"] if c["chave"] == chave)


def test_haversine_e_tempos():
    assert haversine_m(47.0, -122.0, 48.0, -122.0) == pytest.approx(111_195, rel=1e-3)  # 1 grau de latitude
    assert tempos(400) == (7, 2)  # 520 m de rota: 6,5 min a pé e 1,04 min de carro, arredondados para cima
    assert tempos(5) == (1, 1)


def test_consulta_traz_todas_as_categorias_no_raio():
    texto = consulta_overpass(LAT, LNG)
    assert texto.startswith("[out:json][timeout:8]") and texto.endswith("out tags center;")
    for filtro in ('"amenity"="bank"', '"highway"="bus_stop"', '"shop"~"^(supermarket', '"leisure"~"^(park'):
        assert filtro in texto
    assert f"(around:1500,{LAT},{LNG})" in texto


def test_monta_categorias_ordenadas_e_indice():
    r = montar_comodidades(BRUTO, LAT, LNG)
    assert r["disponivel"] and r["raio_m"] == 1500 and "OpenStreetMap contributors" in r["fonte"]
    assert [c["chave"] for c in r["categorias"]] == [
        "escolas", "saude", "mercados", "transporte", "parques", "alimentacao", "bancos"]
    transporte = _categoria(r, "transporte")
    assert transporte["quantidade"] == 3  # contagem bruta, com as duas plataformas do mesmo ponto
    assert [i["nome"] for i in transporte["mais_proximos"]] == ["Bellevue Way & Main St", "Ponto de ônibus"]
    assert transporte["mais_proximos"][0]["distancia_m"] < 20
    parque = _categoria(r, "parques")["mais_proximos"][0]
    assert parque["nome"] == "Downtown Park" and parque["tipo"] == "Parque"  # área (way) pelo centro
    assert _categoria(r, "alimentacao")["mais_proximos"][0]["nome"] == "Starbucks"  # sem nome: usa a marca
    assert _categoria(r, "bancos")["quantidade"] == 0  # 3,3 km: fora do raio
    mercado = _categoria(r, "mercados")["mais_proximos"][0]
    assert 300 < mercado["distancia_m"] < 360 and mercado["a_pe_min"] == 6 and mercado["carro_min"] == 1
    indice = r["indice_conveniencia"]
    assert 0 <= indice["valor"] <= 100 and indice["classificacao"] in {"Excelente", "Boa", "Regular", "Limitada"}
    assert indice["valor"] == 87  # tudo a até 400 m, menos a escola (656 m: 15 × 0,77) e os bancos (fora, peso 10)


def test_cache_falha_e_espera(monkeypatch):
    monkeypatch.setenv("AVALIADOR_COMODIDADES", "1")
    chamadas = []
    servico = ServicoComodidades(consultar=lambda lat, lng: chamadas.append((lat, lng)) or BRUTO)
    assert servico.comodidades(LAT, LNG)["disponivel"]
    assert servico.comodidades(LAT + 0.00001, LNG)["disponivel"] and len(chamadas) == 1  # mesmo ponto: cache

    falhas = []

    def sem_rede(lat, lng):
        falhas.append(1)
        raise OSError("sem rede")
    servico = ServicoComodidades(consultar=sem_rede)
    vazio = servico.comodidades(LAT, LNG)
    assert vazio["disponivel"] is False and vazio["categorias"] == [] and vazio["indice_conveniencia"] is None
    servico.comodidades(LAT, LNG)
    assert len(falhas) == 1  # dentro da espera de 60 s não tenta de novo


def test_desligado_por_variavel(monkeypatch):
    monkeypatch.setenv("AVALIADOR_COMODIDADES", "0")
    servico = ServicoComodidades(consultar=lambda lat, lng: pytest.fail("não deveria consultar"))
    assert servico.comodidades(LAT, LNG)["disponivel"] is False


def test_espelho_quando_o_principal_recusa(monkeypatch):
    usados = []

    def abrir(pedido, timeout):
        usados.append(pedido.full_url)
        assert pedido.data.startswith(b"data=") and timeout <= modulo.TIMEOUT_S
        if len(usados) == 1:
            raise urllib.error.HTTPError(pedido.full_url, 502, "ocupado", {}, None)
        return io.BytesIO(json.dumps(BRUTO).encode("utf-8"))
    monkeypatch.setattr(modulo.urllib.request, "urlopen", abrir)
    monkeypatch.delenv("AVALIADOR_OVERPASS_URL", raising=False)
    assert modulo._consultar_overpass(LAT, LNG) == BRUTO
    assert usados == list(modulo.URLS_OVERPASS)


@pytest.fixture(scope="module")
def cliente():
    with TestClient(main.app) as cliente:
        yield cliente


@pytest.fixture
def servicos_falsos():
    """Troca os serviços do OpenStreetMap por versões com consulta falsa e devolve os originais no fim."""
    estado = main.app.state
    originais = (estado.comodidades, estado.endereco)
    estado.comodidades = ServicoComodidades(consultar=_bruto_em)
    estado.endereco = ServicoEndereco(consultar=lambda lat, lng: {
        "address": {"house_number": "10", "road": "Main Street", "city": "Bellevue", "postcode": "98004"}})
    yield estado
    estado.comodidades, estado.endereco = originais


def test_rota_comodidades(cliente, servicos_falsos, monkeypatch):
    monkeypatch.setenv("AVALIADOR_COMODIDADES", "1")
    r = cliente.get("/v1/comodidades", params={"lat": LAT, "lng": LNG})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["disponivel"] and corpo["indice_conveniencia"]["valor"] == 87
    assert {"nome", "tipo", "distancia_m", "a_pe_min", "carro_min"} <= set(corpo["categorias"][1]["mais_proximos"][0])
    assert cliente.get("/v1/comodidades", params={"lat": 40.7, "lng": -74.0}).status_code == 422
    assert "/v1/comodidades" in cliente.get("/openapi.json").json()["paths"]


def _primeira_amostra(cliente) -> dict:
    return cliente.get("/v1/avaliacoes", params={"origem": "amostra_base", "limite": 1}).json()["itens"][0]


def test_laudo_completo_com_comodidades_e_endereco(cliente, servicos_falsos, monkeypatch):
    monkeypatch.setenv("AVALIADOR_COMODIDADES", "1")
    monkeypatch.setenv("AVALIADOR_GEOCODIFICAR", "1")
    amostra = _primeira_amostra(cliente)
    html = cliente.get(f"/v1/avaliacoes/{amostra['id']}/laudo").text
    for trecho in ("Laudo de Avaliação Mercadológica", "Sumário executivo", "Características do imóvel",
                   "Análise de mercado", "Comparáveis", "Localização e comodidades", "Índice de conveniência",
                   "Metodologia e desempenho do modelo", "Limitações e aviso legal", "@media print",
                   "10 Main Street, Bellevue, WA 98004", "CVS Pharmacy", "min a pé", "min de carro",
                   "© OpenStreetMap contributors", f"AV-{amostra['criado_em'][:4]}-{amostra['id']:06d}"):
        assert trecho in html, trecho
    assert "Bellevue High &lt;School&gt;" in html and "<School>" not in html  # nomes do OSM escapados
    metricas = main.app.state.servico_modelo.metricas["metricas"]["teste"]
    assert f"{metricas['R2']:.3f}".replace(".", ",") in html  # R² lido do arquivo de métricas


def test_laudo_sem_comodidades(cliente):
    amostra = _primeira_amostra(cliente)
    resposta = cliente.get(f"/v1/avaliacoes/{amostra['id']}/laudo")
    assert resposta.status_code == 200
    assert "não respondeu no momento da emissão" in resposta.text and "Índice de conveniência" not in resposta.text
    assert "Posição no CEP" in resposta.text  # o indicador de mercado ocupa o lugar do índice
