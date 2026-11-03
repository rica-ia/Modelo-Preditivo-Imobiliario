"""
# Roteador de relatórios

Indicadores de uso e a documentação viva do banco SQLite (tabelas, colunas,
índices e contagem de linhas).
"""

from fastapi import APIRouter, Depends, Query

from ..schemas.comercial import EsquemaSaida, PredicaoRegistrada, ResumoSaida
from ..services import relatorios
from ..services.banco import Banco
from .dependencias import obter_banco

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
