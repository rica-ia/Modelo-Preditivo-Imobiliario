"""
# Roteador de inferência

As rotas só recebem o JSON já validado pelo Pydantic e delegam ao serviço;
nenhuma regra de negócio nem leitura de disco acontece aqui.
"""

from fastapi import APIRouter, Depends

from ..schemas.imovel import ImovelEntrada, LoteEntrada, LoteSaida, PrevisaoSaida
from ..schemas.sistema import ErroSaida
from ..services.modelo import ServicoModelo
from .dependencias import obter_servico

router = APIRouter(prefix="/v1", tags=["Predição"])

RESPOSTAS_DE_ERRO = {
    400: {"model": ErroSaida, "description": "Regra de negócio violada."},
    422: {"model": ErroSaida, "description": "JSON fora do contrato (tipo, faixa ou campo)."},
    500: {"model": ErroSaida, "description": "Erro inesperado no servidor."},
    503: {"model": ErroSaida, "description": "Modelo fora da memória."},
}


@router.post(
    "/predict",
    response_model=PrevisaoSaida,
    responses=RESPOSTAS_DE_ERRO,
    summary="Estima o preço de um imóvel",
)
def prever(imovel: ImovelEntrada, servico: ServicoModelo = Depends(obter_servico)) -> PrevisaoSaida:
    return servico.prever([imovel])[0]


@router.post(
    "/predict/lote",
    response_model=LoteSaida,
    responses=RESPOSTAS_DE_ERRO,
    summary="Estima o preço de 1 a 20 imóveis (cenários)",
)
def prever_lote(lote: LoteEntrada, servico: ServicoModelo = Depends(obter_servico)) -> LoteSaida:
    return LoteSaida(previsoes=servico.prever(lote.imoveis))
