"""
# Roteador comercial

Console do administrador (emitir, listar e revogar chaves; trocar plano, suspender, reativar
e trocar a chave; editar o cliente, ver a ficha com histórico e o faturamento; ver o e-mail enviado)
protegido pelo cabeçalho `X-Admin-Token` ou por uma sessão 2FA (`X-Admin-Sessao`; emitir
chave pede também a senha da conta em `X-Senha-Conta`), e consulta de consumo do cliente pela
própria chave (`X-API-Key`).
"""

from fastapi import APIRouter, Depends, Security
from fastapi.responses import HTMLResponse

from ..schemas.comercial import (
    ClienteSaida,
    DetalheClienteSaida,
    EdicaoClienteEntrada,
    FaturamentoSaida,
    NovaChaveEntrada,
    NovaChaveSaida,
    PlanoSaida,
    RevogacaoSaida,
    RotacaoSaida,
    SituacaoSaida,
    SuspensaoEntrada,
    TrocaPlanoEntrada,
    TrocaPlanoSaida,
    UsoSaida,
)
from ..schemas.sistema import ErroSaida
from ..services.comercial import ServicoComercial
from ..services.planos import catalogo
from .dependencias import cabecalho_chave, confirmar_senha_conta, exigir_admin, obter_comercial

router = APIRouter(prefix="/v1/comercial", tags=["Comercial"])

ERROS_ADMIN = {
    401: {"model": ErroSaida, "description": "Token de administrador ausente ou incorreto."},
    503: {"model": ErroSaida, "description": "Console não configurado no .env."},
}


@router.get("/planos", response_model=list[PlanoSaida], summary="Planos comerciais: limite mensal e preço")
def planos() -> list[PlanoSaida]:
    return [PlanoSaida(**p) for p in catalogo()]


@router.post(
    "/chaves",
    status_code=201,
    response_model=NovaChaveSaida,
    responses={**ERROS_ADMIN, 429: {"model": ErroSaida, "description": "Senha da conta errada 5 vezes: bloqueio de 5 min."}},
    dependencies=[Depends(exigir_admin), Depends(confirmar_senha_conta)],
    summary="Cadastra o cliente, emite a chave e envia as instruções por e-mail",
    description="Com o token de administrador, basta o corpo. Numa sessão 2FA (`X-Admin-Sessao`), a emissão "
                "pede também a senha da conta no cabeçalho `X-Senha-Conta`.",
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


# ## Gestão do cliente
ERROS_GESTAO = {**ERROS_ADMIN, 400: {"model": ErroSaida, "description": "Regra de negócio (mesmo plano, chave revogada)."},
                404: {"model": ErroSaida}}


@router.get(
    "/faturamento",
    response_model=FaturamentoSaida,
    responses=ERROS_ADMIN,
    dependencies=[Depends(exigir_admin)],
    summary="Receita recorrente (MRR), previsão anual, receita por plano e clientes perto do limite",
)
def faturamento(comercial: ServicoComercial = Depends(obter_comercial)) -> FaturamentoSaida:
    return FaturamentoSaida(**comercial.faturamento())


@router.get(
    "/clientes/{cliente_id}",
    response_model=DetalheClienteSaida,
    responses={**ERROS_ADMIN, 404: {"model": ErroSaida}},
    dependencies=[Depends(exigir_admin)],
    summary="Ficha do cliente: chaves, consumo por dia, histórico e e-mails",
)
def detalhe_cliente(cliente_id: int, comercial: ServicoComercial = Depends(obter_comercial)) -> DetalheClienteSaida:
    return DetalheClienteSaida(**comercial.detalhe_cliente(cliente_id))


@router.patch(
    "/clientes/{cliente_id}",
    response_model=DetalheClienteSaida,
    responses={**ERROS_ADMIN, 404: {"model": ErroSaida}},
    dependencies=[Depends(exigir_admin)],
    summary="Edita nome, e-mail ou empresa do cliente",
)
def editar_cliente(cliente_id: int, dados: EdicaoClienteEntrada,
                   comercial: ServicoComercial = Depends(obter_comercial)) -> DetalheClienteSaida:
    return DetalheClienteSaida(**comercial.editar_cliente(cliente_id, dados.model_dump(exclude_unset=True)))


@router.patch(
    "/chaves/{chave_id}/plano",
    response_model=TrocaPlanoSaida,
    responses=ERROS_GESTAO,
    dependencies=[Depends(exigir_admin)],
    summary="Troca o plano do cliente (upgrade ou downgrade); o novo limite vale na hora",
)
def trocar_plano(chave_id: int, dados: TrocaPlanoEntrada,
                 comercial: ServicoComercial = Depends(obter_comercial)) -> TrocaPlanoSaida:
    return TrocaPlanoSaida(**comercial.trocar_plano(chave_id, dados.plano))


@router.post(
    "/chaves/{chave_id}/suspender",
    response_model=SituacaoSaida,
    responses=ERROS_GESTAO,
    dependencies=[Depends(exigir_admin)],
    summary="Suspende a chave temporariamente (a API responde 403 chave_suspensa e a mensalidade sai da receita)",
)
def suspender(chave_id: int, dados: SuspensaoEntrada | None = None,
              comercial: ServicoComercial = Depends(obter_comercial)) -> SituacaoSaida:
    return SituacaoSaida(**comercial.suspender(chave_id, dados.motivo if dados else None))


@router.post(
    "/chaves/{chave_id}/reativar",
    response_model=SituacaoSaida,
    responses=ERROS_GESTAO,
    dependencies=[Depends(exigir_admin)],
    summary="Reativa uma chave suspensa",
)
def reativar(chave_id: int, comercial: ServicoComercial = Depends(obter_comercial)) -> SituacaoSaida:
    return SituacaoSaida(**comercial.reativar(chave_id))


@router.post(
    "/chaves/{chave_id}/rotacionar",
    status_code=201,
    response_model=RotacaoSaida,
    responses={**ERROS_GESTAO, 429: {"model": ErroSaida, "description": "Senha da conta errada 5 vezes: bloqueio de 5 min."}},
    dependencies=[Depends(exigir_admin), Depends(confirmar_senha_conta)],
    summary="Troca a chave: revoga a atual, emite outra no mesmo plano e envia por e-mail",
    description="Para vazamento ou troca de equipe do cliente. Numa sessão 2FA, pede a senha da conta em `X-Senha-Conta`.",
)
def rotacionar(chave_id: int, comercial: ServicoComercial = Depends(obter_comercial)) -> RotacaoSaida:
    return RotacaoSaida(**comercial.rotacionar(chave_id))
