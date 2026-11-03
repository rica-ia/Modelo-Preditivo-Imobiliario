"""
# Roteador dos dados sintéticos de exemplo

Carrega ou remove a carga de demonstração do banco (clientes, chaves, e-mails, eventos,
predições, laudos e faturas fictícios, marcados com `sintetico = 1`). Só o administrador
(`X-Admin-Token` ou sessão 2FA). Ambas as operações são idempotentes e devolvem as
contagens por tabela.
"""

from fastapi import APIRouter, Depends

from ..schemas.sistema import ErroSaida
from ..services.banco import Banco
from ..services.modelo import ServicoModelo
from ..services.sinteticos import carregar_sinteticos, remover_sinteticos
from .dependencias import exigir_admin, obter_banco, obter_servico

router = APIRouter(prefix="/v1/admin/banco", tags=["Banco de dados"], dependencies=[Depends(exigir_admin)])

ERROS_ADMIN = {
    401: {"model": ErroSaida, "description": "Token de administrador ausente ou incorreto."},
    503: {"model": ErroSaida, "description": "Console não configurado no .env."},
}


@router.post(
    "/sinteticos",
    response_model=dict[str, int],
    responses=ERROS_ADMIN,
    summary="Carrega os dados sintéticos de exemplo (não duplica se já existirem)",
)
def carregar(banco: Banco = Depends(obter_banco), servico: ServicoModelo = Depends(obter_servico)) -> dict[str, int]:
    return carregar_sinteticos(banco, servico)


@router.delete(
    "/sinteticos",
    response_model=dict[str, int],
    responses=ERROS_ADMIN,
    summary="Remove só os dados sintéticos de exemplo, preservando os reais",
)
def remover(banco: Banco = Depends(obter_banco)) -> dict[str, int]:
    return remover_sinteticos(banco)
