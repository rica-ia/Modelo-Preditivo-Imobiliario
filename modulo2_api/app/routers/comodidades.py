"""
# Comodidades perto de um ponto (escolas, saúde, mercados, transporte, parques, alimentação e bancos)

Consulta ao OpenStreetMap pela Overpass API, com cache, distâncias e tempos estimados a pé e de
carro e o índice de conveniência; ver `services/comodidades.py`.
"""

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from ..services.comodidades import ServicoComodidades

router = APIRouter(prefix="/v1", tags=["Regiões"])


class ComodidadeSaida(BaseModel):
    nome: str = Field(..., description="Nome no OpenStreetMap; sem nome, o tipo do lugar.", examples=["QFC"])
    tipo: str = Field(..., description="Tipo do lugar em português.", examples=["Supermercado"])
    distancia_m: int = Field(..., description="Distância em linha reta (haversine), em metros.", examples=[420])
    a_pe_min: int = Field(..., description="Tempo estimado a pé, em minutos (rota ≈ 1,3 × linha reta, 80 m/min).")
    carro_min: int = Field(..., description="Tempo estimado de carro, em minutos (30 km/h urbano).")
    latitude: float
    longitude: float


class CategoriaSaida(BaseModel):
    chave: str = Field(..., examples=["mercados"])
    nome: str = Field(..., examples=["Supermercados e mercados"])
    quantidade: int = Field(..., description="Quantidade de lugares da categoria dentro do raio.")
    mais_proximos: list[ComodidadeSaida] = Field(..., description="Até 3 lugares mais próximos, com nomes distintos.")


class IndiceSaida(BaseModel):
    valor: int = Field(..., ge=0, le=100, description="Índice de conveniência de 0 a 100.", examples=[82])
    classificacao: str = Field(..., description="Excelente (≥ 80), Boa (≥ 60), Regular (≥ 40) ou Limitada.")
    explicacao: str = Field(..., description="Como o índice é calculado.")


class ComodidadesSaida(BaseModel):
    disponivel: bool = Field(..., description="Falso quando a Overpass não respondeu; o laudo segue sem a seção.")
    latitude: float
    longitude: float
    raio_m: int = Field(..., description="Raio da busca, em metros.", examples=[1500])
    categorias: list[CategoriaSaida]
    indice_conveniencia: IndiceSaida | None = None
    metodo: str = Field(..., description="Como distâncias e tempos foram estimados.")
    fonte: str = Field(..., description="Crédito exigido pelo OpenStreetMap.")
    consultado_em: str | None = Field(None, description="Data e hora da consulta (ISO 8601).")


def obter_comodidades(request: Request) -> ServicoComodidades:
    return request.app.state.comodidades


@router.get(
    "/comodidades",
    response_model=ComodidadesSaida,
    summary="Comodidades num raio de 1,5 km de uma coordenada de King County",
    description=(
        "Escolas, saúde, supermercados, transporte público, parques, restaurantes e bancos do OpenStreetMap,"
        " com a quantidade no raio, os 3 mais próximos de cada categoria, distâncias, tempos estimados a pé e"
        " de carro e um índice de conveniência de 0 a 100. Dados © OpenStreetMap contributors (ODbL)."
    ),
)
def comodidades(
    lat: float = Query(..., ge=46.9, le=48.0, description="Latitude (King County, WA)."),
    lng: float = Query(..., ge=-123.2, le=-120.7, description="Longitude (King County, WA)."),
    servico: ServicoComodidades = Depends(obter_comodidades),
) -> ComodidadesSaida:
    return ComodidadesSaida(**servico.comodidades(lat, lng))
