"""Fase 3: o artefato é lido do disco uma única vez, no lifespan."""

from fastapi.testclient import TestClient

from modulo2_api.app import main
from modulo2_api.app.services import modelo as servico_modelo


def test_lifespan_carrega_modelo_na_memoria():
    with TestClient(main.app) as cliente:
        corpo = cliente.get("/health").json()
    assert corpo["status"] == "ok"
    assert corpo["modelo_carregado"] is True
    assert corpo["carregado_em"]


def test_modelo_e_lido_do_disco_uma_unica_vez(monkeypatch):
    original = servico_modelo.joblib.load
    chamadas = []

    def contar(caminho, *args, **kwargs):
        chamadas.append(caminho)
        return original(caminho, *args, **kwargs)

    monkeypatch.setattr(servico_modelo.joblib, "load", contar)
    with TestClient(main.app) as cliente:
        for _ in range(5):
            assert cliente.get("/health").status_code == 200
    assert len(chamadas) == 1
