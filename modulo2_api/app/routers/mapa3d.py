"""
# Configuração da visão 3D

Entrega à página local a chave do Google Maps (Photorealistic 3D Tiles) lida do
.env. A chave só sai para quem acessa da própria máquina; nunca vai para log.
"""

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from ..config import obter

router = APIRouter(prefix="/v1/config", tags=["Configuração"])

HOSTS_LOCAIS = {"127.0.0.1", "::1", "localhost"}


class Mapa3dSaida(BaseModel):
    disponivel: bool = Field(..., description="Indica se a visão 3D pode ser usada neste acesso.")
    chave: str | None = Field(None, description="Chave do Google Maps, entregue só em acesso local.")
    provedor: str = Field("Google Photorealistic 3D Tiles")


@router.get("/mapa3d", response_model=Mapa3dSaida, summary="Configuração da visão 3D (apenas acesso local)")
def config_mapa3d(request: Request) -> Mapa3dSaida:
    chave = obter("GOOGLE_MAPS_API_KEY").strip()
    local = request.client is not None and request.client.host in HOSTS_LOCAIS
    if not chave or not local:
        return Mapa3dSaida(disponivel=False, chave=None)
    return Mapa3dSaida(disponivel=True, chave=chave)
