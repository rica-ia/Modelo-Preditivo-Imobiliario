"""
# Roteador comercial

Console do administrador (emitir, listar e revogar chaves; ver o e-mail enviado)
protegido pelo cabeçalho `X-Admin-Token`, e consulta de consumo do cliente pela
própria chave (`X-API-Key`).
"""

from fastapi import APIRouter, Depends, Security
from fastapi.responses import HTMLResponse

from ..schemas.comercial import ClienteSaida, NovaChaveEntrada, NovaChaveSaida, RevogacaoSaida, UsoSaida
from ..schemas.sistema import ErroSaida
from ..services.comercial import ServicoComercial
from .dependencias import cabecalho_chave, exigir_admin, obter_comercial

router = APIRouter(prefix="/v1/comercial", tags=["Comercial"])

ERROS_ADMIN = {
    401: {"model": ErroSaida, "description": "Token de administrador ausente ou incorreto."},
    503: {"model": ErroSaida, "description": "Console não configurado no .env."},
}


@router.post(
    "/chaves",
    status_code=201,
    response_model=NovaChaveSaida,
    responses=ERROS_ADMIN,
    dependencies=[Depends(exigir_admin)],
    summary="Cadastra o cliente, emite a chave e envia as instruções por e-mail",
)
def criar_chave(dados: NovaChaveEntrada, comercial: ServicoComercial = Depends(obter_comercial)) -> NovaChaveSaida:
    return NovaChaveSaida(**comercial.criar_chave(dados.nome, dados.email, dados.empresa, dados.plano))


@router.get(
    "/clientes",
    response_model=list[ClienteSaida],
    responses=ERROS_ADMIN,
    dependencies=[Depends(exigir_admin)],
    summary="Lista clientes, chaves e consumo do mês",
)
def listar_clientes(comercial: ServicoComercial = Depends(obter_comercial)) -> list[ClienteSaida]:
    return [ClienteSaida(**linha) for linha in comercial.listar_clientes()]


@router.post(
    "/chaves/{chave_id}/revogar",
    response_model=RevogacaoSaida,
    responses={**ERROS_ADMIN, 404: {"model": ErroSaida}},
    dependencies=[Depends(exigir_admin)],
    summary="Revoga uma chave de API",
)
def revogar(chave_id: int, comercial: ServicoComercial = Depends(obter_comercial)) -> RevogacaoSaida:
    return RevogacaoSaida(**comercial.revogar(chave_id))


@router.get(
    "/emails/{envio_id}",
    response_class=HTMLResponse,
    responses={**ERROS_ADMIN, 404: {"model": ErroSaida}},
    dependencies=[Depends(exigir_admin)],
    summary="Pré-visualiza o e-mail enviado ao cliente",
)
def ver_email(envio_id: int, comercial: ServicoComercial = Depends(obter_comercial)) -> HTMLResponse:
    return HTMLResponse(comercial.html_do_email(envio_id))


@router.get(
    "/uso",
    response_model=UsoSaida,
    responses={401: {"model": ErroSaida}, 403: {"model": ErroSaida}},
    summary="Consumo do mês da chave informada em X-API-Key",
)
def uso(chave: str | None = Security(cabecalho_chave), comercial: ServicoComercial = Depends(obter_comercial)) -> UsoSaida:
    return UsoSaida(**comercial.uso(chave))
