"""Endereço por geocodificação reversa: montagem dos campos, cache e falha de rede (sem acesso à internet)."""

from fastapi.testclient import TestClient

from modulo2_api.app import main
from modulo2_api.app.services.endereco import ServicoEndereco, montar_endereco

BRUTO = {"address": {"house_number": "3015", "road": "Northeast 89th Street", "neighbourhood": "Wedgwood",
                     "city": "Seattle", "postcode": "98115-3532"}}


def test_monta_endereco_completo():
    e = montar_endereco(BRUTO)
    assert e["disponivel"] and e["cep"] == "98115" and e["rua"] == "Northeast 89th Street"
    assert e["endereco"] == "3015 Northeast 89th Street, Wedgwood, Seattle, WA 98115"


def test_cache_e_falha_de_rede(monkeypatch):
    monkeypatch.setenv("AVALIADOR_GEOCODIFICAR", "1")
    chamadas = []
    servico = ServicoEndereco(consultar=lambda lat, lng: chamadas.append((lat, lng)) or BRUTO)
    assert servico.endereco(47.69, -122.29)["disponivel"]
    assert servico.endereco(47.690001, -122.290001)["disponivel"] and len(chamadas) == 1  # mesmo ponto: cache

    def sem_rede(lat, lng):
        raise OSError("sem rede")
    assert ServicoEndereco(consultar=sem_rede).endereco(47.6, -122.3) == {"disponivel": False, "endereco": None,
                                                                         "fonte": "© OpenStreetMap (Nominatim)"}


def test_rota_valida_king_county(monkeypatch):
    with TestClient(main.app) as cliente:
        main.app.state.endereco = ServicoEndereco(consultar=lambda lat, lng: BRUTO)
        monkeypatch.setenv("AVALIADOR_GEOCODIFICAR", "1")
        r = cliente.get("/v1/endereco", params={"lat": 47.69, "lng": -122.29})
        assert r.status_code == 200 and r.json()["endereco"].startswith("3015 Northeast 89th Street")
        assert cliente.get("/v1/endereco", params={"lat": 40.7, "lng": -74.0}).status_code == 422
