"""
# Roteador de inferência

As rotas só recebem o JSON já validado pelo Pydantic e delegam ao serviço;
nenhuma regra de negócio nem leitura de disco acontece aqui.

A chave de API (`X-API-Key`) é opcional: sem ela o acesso continua livre; com
ela, o consumo é contado no plano do cliente. Toda predição fica registrada no
banco, e uma falha no registro nunca derruba a resposta.
"""

from fastapi import APIRouter, Depends, Header, Security

from ..schemas.imovel import ImovelEntrada, LoteEntrada, LoteSaida, PrevisaoSaida
from ..schemas.sistema import ErroSaida
from ..services.comercial import ServicoComercial
from ..services.excecoes import RegraDeNegocioError
from ..services.modelo import ServicoModelo
from .dependencias import cabecalho_chave, obter_comercial, obter_servico

router = APIRouter(prefix="/v1", tags=["Predição"])

RESPOSTAS_DE_ERRO = {
    400: {"model": ErroSaida, "description": "Regra de negócio violada."},
    401: {"model": ErroSaida, "description": "Chave de API inválida."},
    403: {"model": ErroSaida, "description": "Chave de API revogada."},
    422: {"model": ErroSaida, "description": "JSON fora do contrato (tipo, faixa ou campo)."},
    429: {"model": ErroSaida, "description": "Limite mensal do plano atingido."},
    500: {"model": ErroSaida, "description": "Erro inesperado no servidor."},
    503: {"model": ErroSaida, "description": "Modelo fora da memória."},
}


def _atender(
    imoveis: list[ImovelEntrada],
    chave: str | None,
    origem_informada: str | None,
    servico: ServicoModelo,
    comercial: ServicoComercial,
) -> list[PrevisaoSaida]:
    registro = comercial.autenticar(chave, quantidade=len(imoveis))
    chave_id = registro["id"] if registro else None
    origem = "api" if registro else ("portal" if origem_informada == "portal" else "anonima")

    def linhas(status: int, previsoes: list[PrevisaoSaida] | None = None) -> list[dict]:
        return [
            {
                "chave_id": chave_id,
                "origem": origem,
                "cep": imovel.cep,
                "area_util_m2": imovel.area_util_m2,
                "preco_estimado_usd": previsoes[i].preco_estimado_usd if previsoes else None,
                "latencia_ms": previsoes[i].latencia_ms if previsoes else None,
                "status_http": status,
            }
            for i, imovel in enumerate(imoveis)
        ]

    try:
        previsoes = servico.prever(imoveis)
    except RegraDeNegocioError:
        comercial.registrar(linhas(400))
        raise
    comercial.registrar(linhas(200, previsoes))
    return previsoes


@router.post(
    "/predict",
    response_model=PrevisaoSaida,
    responses=RESPOSTAS_DE_ERRO,
    summary="Estima o preço de um imóvel",
)
def prever(
    imovel: ImovelEntrada,
    servico: ServicoModelo = Depends(obter_servico),
    comercial: ServicoComercial = Depends(obter_comercial),
    chave: str | None = Security(cabecalho_chave),
    x_origem: str | None = Header(None, include_in_schema=False),
) -> PrevisaoSaida:
    return _atender([imovel], chave, x_origem, servico, comercial)[0]


@router.post(
    "/predict/lote",
    response_model=LoteSaida,
    responses=RESPOSTAS_DE_ERRO,
    summary="Estima o preço de 1 a 20 imóveis (cenários)",
)
def prever_lote(
    lote: LoteEntrada,
    servico: ServicoModelo = Depends(obter_servico),
    comercial: ServicoComercial = Depends(obter_comercial),
    chave: str | None = Security(cabecalho_chave),
    x_origem: str | None = Header(None, include_in_schema=False),
) -> LoteSaida:
    return LoteSaida(previsoes=_atender(lote.imoveis, chave, x_origem, servico, comercial))
