"""
# Roteador de relatórios

Indicadores de uso, a documentação viva do banco SQLite (tabelas, colunas,
índices e contagem de linhas) e os relatórios de mercado das vendas reais.
"""

from fastapi import APIRouter, Depends, Query, Response

from ..schemas.avaliacoes import Dimensao, Formato, MercadoSaida
from ..schemas.comercial import EsquemaSaida, PredicaoRegistrada, ResumoSaida
from ..services import mercado, relatorios
from ..services.avaliacoes import ServicoAvaliacoes
from ..services.banco import Banco
from .dependencias import obter_avaliacoes, obter_banco

router = APIRouter(prefix="/v1/relatorios", tags=["Relatórios"])


@router.get("/resumo", response_model=ResumoSaida, summary="Indicadores de uso da API")
def resumo(banco: Banco = Depends(obter_banco)) -> ResumoSaida:
    return ResumoSaida(**relatorios.resumo(banco))


@router.get("/predicoes", response_model=list[PredicaoRegistrada], summary="Predições mais recentes")
def predicoes(
    limite: int = Query(20, ge=1, le=100, description="Quantidade de registros (1 a 100)."),
    banco: Banco = Depends(obter_banco),
) -> list[PredicaoRegistrada]:
    return [PredicaoRegistrada(**linha) for linha in relatorios.predicoes_recentes(banco, limite)]


@router.get("/esquema", response_model=EsquemaSaida, summary="Documentação do banco SQLite")
def esquema(banco: Banco = Depends(obter_banco)) -> EsquemaSaida:
    return EsquemaSaida(**relatorios.esquema(banco))


def filtros_mercado(
    cidade: str | None = Query(None, max_length=40, description="Restringe a uma cidade."),
    quartos: int | None = Query(None, ge=0, le=15, description="Restringe a um número de quartos."),
    faixa_preco: str | None = Query(None, max_length=40, description="Restringe a um quartil de preço."),
) -> dict:
    return {"cidade": cidade, "quartos": quartos, "faixa_preco": faixa_preco}


@router.get("/mercado", response_model=MercadoSaida, summary="Vendas reais agrupadas por uma dimensão")
def mercado_relatorio(
    dimensao: Dimensao = Query("quartos", description="quartos, cidade, cep, faixa_preco, padrao ou ano_venda."),
    filtros: dict = Depends(filtros_mercado),
    banco: Banco = Depends(obter_banco),
    avaliacoes: ServicoAvaliacoes = Depends(obter_avaliacoes),
) -> MercadoSaida:
    return MercadoSaida(**mercado.relatorio(banco, dimensao, filtros, avaliacoes.faixas()))


@router.get(
    "/mercado/exportar",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}, "application/json": {}}, "description": "Arquivo para download."}},
    summary="Exporta o relatório de mercado em CSV (Excel pt-BR) ou JSON",
)
def mercado_exportar(
    formato: Formato = Query("csv", description="csv ou json."),
    dimensao: Dimensao = Query("quartos"),
    filtros: dict = Depends(filtros_mercado),
    banco: Banco = Depends(obter_banco),
    avaliacoes: ServicoAvaliacoes = Depends(obter_avaliacoes),
) -> Response:
    dados = mercado.relatorio(banco, dimensao, filtros, avaliacoes.faixas())
    conteudo, tipo, nome = mercado.exportar(dados, formato)
    return Response(conteudo, media_type=tipo, headers={"Content-Disposition": f'attachment; filename="{nome}"'})
