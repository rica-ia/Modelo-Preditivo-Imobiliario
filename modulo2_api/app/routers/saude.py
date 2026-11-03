"""
# Roteador de monitoramento

`GET /health` responde se o serviço está no ar e se o modelo está na memória.
"""

from fastapi import APIRouter, Request

router = APIRouter(tags=["Monitoramento"])


@router.get("/health", summary="Verifica se a API e o modelo estão disponíveis")
def health(request: Request) -> dict:
    servico = getattr(request.app.state, "servico_modelo", None)
    return {"status": "ok", "modelo_carregado": bool(servico and servico.carregado)}
