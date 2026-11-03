"""Coerência comercial: melhorar o imóvel nunca pode reduzir o preço estimado."""

import pytest
from fastapi.testclient import TestClient

from modulo2_api.app import main

BASE = {
    "quartos": 3, "banheiros": 2, "area_util_m2": 170, "area_terreno_m2": 700, "andares": 1,
    "frente_agua": False, "vista": 0, "condicao": 3, "padrao_construtivo": 7, "area_porao_m2": 0,
    "ano_construcao": 1990, "ano_reforma": None,
}
CEPS = ["98103", "98065", "98052", "98004", "98118"]


@pytest.fixture(scope="module")
def cliente():
    with TestClient(main.app) as cliente:
        yield cliente


@pytest.mark.parametrize("cep", CEPS)
def test_melhorias_nao_reduzem_o_preco(cliente, cep):
    regiao = next(r for r in cliente.get("/v1/regioes").json() if r["cep"] == cep)
    base = {**BASE, "cep": cep, "latitude": regiao["latitude"], "longitude": regiao["longitude"]}
    cenarios = {
        "padrão +1": {**base, "padrao_construtivo": base["padrao_construtivo"] + 1},
        "área +20 %": {**base, "area_util_m2": round(base["area_util_m2"] * 1.2)},
        "vista +1": {**base, "vista": base["vista"] + 1},
        "reforma": {**base, "ano_reforma": 2015},
    }
    resposta = cliente.post("/v1/predict/lote", json={"imoveis": [base, *cenarios.values()]})
    assert resposta.status_code == 200
    precos = [p["preco_estimado_usd"] for p in resposta.json()["previsoes"]]
    for nome, preco in zip(cenarios, precos[1:]):
        assert preco >= precos[0], f"{nome} reduziu o preço no CEP {cep}"
