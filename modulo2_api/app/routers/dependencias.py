"""Injeção de dependência: entrega às rotas o serviço criado no lifespan."""

from fastapi import Request

from ..services.modelo import ServicoModelo


def obter_servico(request: Request) -> ServicoModelo:
    return request.app.state.servico_modelo
