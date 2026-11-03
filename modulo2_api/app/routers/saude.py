"""
# Roteador de monitoramento

`GET /health` responde se o serviço está no ar e se o modelo está na memória.
"""

from fastapi import APIRouter, Request

from ..schemas.sistema import SaudeSaida

router = APIRouter(tags=["Monitoramento"])


@router.get("/health", response_model=SaudeSaida, summary="Verifica se a API e o modelo estão disponíveis")
def health(request: Request) -> SaudeSaida:
    servico = request.app.state.servico_modelo
    return SaudeSaida(
        status="ok",
        modelo_carregado=servico.carregado,
        versao_modelo=servico.versao,
        carregado_em=servico.carregado_em.isoformat() if servico.carregado_em else None,
        uptime_s=servico.uptime_s,
    )
