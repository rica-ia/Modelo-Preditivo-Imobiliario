"""
# Roteador de avaliações (laudos)

Cria, lista com filtros, exporta e imprime laudos. A predição é sempre
recalculada no servidor a partir do imóvel enviado.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response, Security
from fastapi.responses import HTMLResponse

from ..schemas.avaliacoes import AvaliacaoEntrada, AvaliacaoSaida, Formato, ListaAvaliacoesSaida, Ordenacao, Origem
from ..schemas.sistema import ErroSaida
from ..services.avaliacoes import ServicoAvaliacoes
from .dependencias import cabecalho_chave, obter_avaliacoes

router = APIRouter(prefix="/v1/avaliacoes", tags=["Avaliações"])


def filtros_avaliacao(
    cep: str | None = Query(None, pattern=r"^98\d{3}$", description="CEP de King County."),
    cidade: str | None = Query(None, max_length=40, description="Cidade, por exemplo Seattle."),
    quartos: int | None = Query(None, ge=0, le=15, description="Número exato de quartos."),
    faixa_preco: str | None = Query(None, max_length=40, description="Quartil de preço, como aparece nos registros."),
    origem: Origem | None = Query(None, description="portal, api ou amostra_base."),
    preco_min: float | None = Query(None, ge=0, description="Preço estimado mínimo, em USD."),
    preco_max: float | None = Query(None, ge=0, description="Preço estimado máximo, em USD."),
    busca: str | None = Query(None, max_length=60, description="Trecho do título."),
) -> dict:
    return {
        "cep": cep, "cidade": cidade, "quartos": quartos, "faixa_preco": faixa_preco, "origem": origem,
        "preco_min": preco_min, "preco_max": preco_max, "busca": busca,
    }


@router.post(
    "",
    status_code=201,
    response_model=AvaliacaoSaida,
    responses={400: {"model": ErroSaida}, 401: {"model": ErroSaida}, 403: {"model": ErroSaida},
               422: {"model": ErroSaida}, 429: {"model": ErroSaida}},
    summary="Avalia o imóvel e grava o laudo",
)
def criar(
    dados: AvaliacaoEntrada,
    request: Request,
    tarefas: BackgroundTasks,
    chave: str | None = Security(cabecalho_chave),
    servico: ServicoAvaliacoes = Depends(obter_avaliacoes),
) -> AvaliacaoSaida:
    avaliacao = servico.criar(dados.titulo, dados.responsavel, dados.imovel, chave)
    # Endereço e comodidades entram no cache em 2º plano: o laudo abre sem esperar o OpenStreetMap
    for nome, metodo in (("endereco", "endereco"), ("comodidades", "comodidades")):
        if (externo := getattr(request.app.state, nome, None)) is not None:
            tarefas.add_task(getattr(externo, metodo), dados.imovel.latitude, dados.imovel.longitude)
    return AvaliacaoSaida(**avaliacao)


@router.get("", response_model=ListaAvaliacoesSaida, summary="Lista laudos com filtros, paginação e ordenação")
def listar(
    filtros: dict = Depends(filtros_avaliacao),
    pagina: int = Query(1, ge=1, description="Página (começa em 1)."),
    limite: int = Query(20, ge=1, le=100, description="Itens por página (1 a 100)."),
    ordenacao: Ordenacao = Query("recentes", description="recentes, antigas, preco_desc ou preco_asc."),
    servico: ServicoAvaliacoes = Depends(obter_avaliacoes),
) -> ListaAvaliacoesSaida:
    return ListaAvaliacoesSaida(**servico.listar(filtros, pagina, limite, ordenacao))


@router.get(
    "/exportar",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}, "application/json": {}}, "description": "Arquivo para download."}},
    summary="Exporta os laudos filtrados em CSV (Excel pt-BR) ou JSON",
)
def exportar(
    formato: Formato = Query("csv", description="csv ou json."),
    filtros: dict = Depends(filtros_avaliacao),
    ordenacao: Ordenacao = Query("recentes"),
    servico: ServicoAvaliacoes = Depends(obter_avaliacoes),
) -> Response:
    conteudo, tipo, nome = servico.exportar(filtros, formato, ordenacao)
    return Response(conteudo, media_type=tipo, headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@router.get(
    "/{avaliacao_id}",
    response_model=AvaliacaoSaida,
    responses={404: {"model": ErroSaida}},
    summary="Consulta um laudo",
)
def obter(avaliacao_id: int, servico: ServicoAvaliacoes = Depends(obter_avaliacoes)) -> AvaliacaoSaida:
    return AvaliacaoSaida(**servico.obter(avaliacao_id))


@router.get(
    "/{avaliacao_id}/laudo",
    response_class=HTMLResponse,
    responses={404: {"model": ErroSaida}},
    summary="Laudo HTML pronto para imprimir ou salvar em PDF",
    description=(
        "Laudo de avaliação mercadológica em oito seções: identificação com endereço completo, sumário executivo,"
        " características, análise de mercado do CEP com comparáveis, comodidades do entorno com distâncias e"
        " tempos (OpenStreetMap), metodologia e métricas do modelo, limitações e responsabilidade."
    ),
)
def laudo(avaliacao_id: int, request: Request, servico: ServicoAvaliacoes = Depends(obter_avaliacoes)) -> HTMLResponse:
    estado = request.app.state
    return HTMLResponse(servico.laudo_html(avaliacao_id, getattr(estado, "endereco", None),
                                           getattr(estado, "comodidades", None)))
