"""
# Endereço do ponto (rua, número, bairro, cidade e CEP)

Geocodificação reversa pelo OpenStreetMap (Nominatim), com cache; ver `services/endereco.py`.
"""

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field

from ..services.endereco import ServicoEndereco

router = APIRouter(prefix="/v1", tags=["Regiões"])


class EnderecoSaida(BaseModel):
    disponivel: bool = Field(..., description="Falso quando o geocodificador não respondeu; o portal mantém o CEP.")
    endereco: str | None = Field(None, description="Endereço completo em uma linha.", examples=["3015 NE 89th St, Wedgwood, Seattle, WA 98115"])
    rua: str | None = None
    numero: str | None = None
    bairro: str | None = None
    cidade: str | None = None
    cep: str | None = None
    fonte: str = Field(..., description="Crédito exigido pelo OpenStreetMap.")


def obter_endereco(request: Request) -> ServicoEndereco:
    return request.app.state.endereco


@router.get("/endereco", response_model=EnderecoSaida, summary="Endereço completo de uma coordenada de King County")
def endereco(
    lat: float = Query(..., ge=46.9, le=48.0, description="Latitude (King County, WA)."),
    lng: float = Query(..., ge=-123.2, le=-120.7, description="Longitude (King County, WA)."),
    servico: ServicoEndereco = Depends(obter_endereco),
) -> EnderecoSaida:
    return EnderecoSaida(**servico.endereco(lat, lng))
