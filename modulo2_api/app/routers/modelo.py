"""
# Roteador de informações do modelo

Expõe as métricas documentadas na Fase 1 e o agregado por CEP. Os dados vêm da
memória (carregados no lifespan junto com o artefato).
"""

from fastapi import APIRouter, Depends

from ..schemas.sistema import ErroSaida, ModeloInfoSaida, RegiaoSaida
from ..services.excecoes import ModeloIndisponivelError
from ..services.modelo import ServicoModelo
from .dependencias import obter_servico

router = APIRouter(prefix="/v1", tags=["Modelo"])


def _exigir_modelo(servico: ServicoModelo) -> None:
    if not servico.carregado:
        raise ModeloIndisponivelError("O modelo não está carregado na memória.")


@router.get(
    "/modelo",
    response_model=ModeloInfoSaida,
    responses={503: {"model": ErroSaida}},
    summary="Métricas, divisão dos dados e importância das variáveis",
)
def info_modelo(servico: ServicoModelo = Depends(obter_servico)) -> ModeloInfoSaida:
    _exigir_modelo(servico)
    return ModeloInfoSaida(**servico.metricas)


@router.get(
    "/regioes",
    response_model=list[RegiaoSaida],
    responses={503: {"model": ErroSaida}},
    summary="Preço mediano e preço por m² por CEP",
)
def regioes(servico: ServicoModelo = Depends(obter_servico)) -> list[RegiaoSaida]:
    _exigir_modelo(servico)
    return [RegiaoSaida(**regiao) for regiao in servico.regioes]
