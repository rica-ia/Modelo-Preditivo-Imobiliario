"""Injeção de dependência: entrega às rotas os serviços criados no lifespan."""

import secrets

from fastapi import Request, Security
from fastapi.security import APIKeyHeader

from ..config import obter
from ..services.acesso import ServicoAcesso
from ..services.avaliacoes import ServicoAvaliacoes
from ..services.banco import Banco
from ..services.comercial import ServicoComercial
from ..services.excecoes import AcessoNegadoError, ConsoleNaoConfiguradoError
from ..services.modelo import ServicoModelo

# Aparecem no botão "Authorize" do Swagger (/docs).
cabecalho_chave = APIKeyHeader(name="X-API-Key", auto_error=False, description="Chave do cliente (opcional no /predict).")
cabecalho_admin = APIKeyHeader(name="X-Admin-Token", auto_error=False, description="Token do console administrativo.")
cabecalho_codigo = APIKeyHeader(name="X-Codigo-2FA", auto_error=False,
                                description="Código de 6 dígitos do app, exigido ao emitir chave dentro de uma sessão 2FA.")
cabecalho_sessao = APIKeyHeader(name="X-Admin-Sessao", auto_error=False,
                                description="Sessão aberta em /v1/acesso/entrar (senha + código 2FA).")


def obter_servico(request: Request) -> ServicoModelo:
    return request.app.state.servico_modelo


def obter_banco(request: Request) -> Banco:
    return request.app.state.banco


def obter_comercial(request: Request) -> ServicoComercial:
    return request.app.state.comercial


def obter_avaliacoes(request: Request) -> ServicoAvaliacoes:
    return request.app.state.avaliacoes


def obter_acesso(request: Request) -> ServicoAcesso:
    return request.app.state.acesso


def exigir_admin(
    request: Request,
    token: str | None = Security(cabecalho_admin),
    sessao: str | None = Security(cabecalho_sessao),
) -> None:
    """Console aceita o token de administrador (scripts e testes) ou uma sessão 2FA válida."""
    if sessao is not None:
        if obter_acesso(request).sessao_valida(sessao):
            return
        raise AcessoNegadoError("Sessão inválida ou expirada. Entre de novo com a senha e o código.")
    esperado = obter("AVALIADOR_ADMIN_TOKEN")
    if not esperado:
        raise ConsoleNaoConfiguradoError("Defina AVALIADOR_ADMIN_TOKEN no arquivo .env para usar o console.")
    if not token or not secrets.compare_digest(token, esperado):
        raise AcessoNegadoError("Token de administrador ausente ou incorreto.")


def confirmar_2fa(
    request: Request,
    sessao: str | None = Security(cabecalho_sessao),
    codigo: str | None = Security(cabecalho_codigo),
) -> None:
    """Na sessão 2FA, a emissão de chave pede de novo o código do app; o token de administrador
    (scripts e testes) segue sem essa etapa."""
    acesso = obter_acesso(request)
    if sessao is not None and acesso.exige_2fa():
        acesso.confirmar_codigo(codigo)
