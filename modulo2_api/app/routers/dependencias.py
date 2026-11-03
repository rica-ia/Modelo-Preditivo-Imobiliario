"""Injeção de dependência: entrega às rotas os serviços criados no lifespan."""

import secrets

from fastapi import Request, Security
from fastapi.security import APIKeyHeader

from ..config import obter
from ..services.banco import Banco
from ..services.comercial import ServicoComercial
from ..services.excecoes import AcessoNegadoError, ConsoleNaoConfiguradoError
from ..services.modelo import ServicoModelo

# Aparecem no botão "Authorize" do Swagger (/docs).
cabecalho_chave = APIKeyHeader(name="X-API-Key", auto_error=False, description="Chave do cliente (opcional no /predict).")
cabecalho_admin = APIKeyHeader(name="X-Admin-Token", auto_error=False, description="Token do console administrativo.")


def obter_servico(request: Request) -> ServicoModelo:
    return request.app.state.servico_modelo


def obter_banco(request: Request) -> Banco:
    return request.app.state.banco


def obter_comercial(request: Request) -> ServicoComercial:
    return request.app.state.comercial


def exigir_admin(token: str | None = Security(cabecalho_admin)) -> None:
    esperado = obter("AVALIADOR_ADMIN_TOKEN")
    if not esperado:
        raise ConsoleNaoConfiguradoError("Defina AVALIADOR_ADMIN_TOKEN no arquivo .env para usar o console.")
    if not token or not secrets.compare_digest(token, esperado):
        raise AcessoNegadoError("Token de administrador ausente ou incorreto.")
