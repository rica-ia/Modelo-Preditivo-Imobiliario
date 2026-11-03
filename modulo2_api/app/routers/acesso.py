"""
# Acesso ao console com senha e segundo fator (2FA)

O portal pergunta em /v1/acesso/estado se o 2FA está ligado. Se estiver, a pessoa
entra com a senha e o código de 6 dígitos do app autenticador e recebe uma sessão,
enviada depois no cabeçalho X-Admin-Sessao das rotas do console comercial.
A API pública de predição (/v1/predict) não passa por aqui e continua aberta.
"""

from fastapi import APIRouter, Depends, Security
from pydantic import BaseModel, ConfigDict, Field

from ..schemas.sistema import ErroSaida
from ..services.acesso import ServicoAcesso
from .dependencias import cabecalho_sessao, obter_acesso

router = APIRouter(prefix="/v1/acesso", tags=["Acesso"])


class EstadoAcessoSaida(BaseModel):
    exige_2fa: bool = Field(..., description="Verdadeiro quando o console exige senha + código do autenticador.")


class EntrarEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    senha: str = Field(..., min_length=1, max_length=128, description="Senha de acesso ao console.")
    codigo: str = Field(..., pattern=r"^\d{6}$", description="Código de 6 dígitos do app autenticador.")


class SessaoSaida(BaseModel):
    sessao: str = Field(..., description="Enviar no cabeçalho X-Admin-Sessao. Válida por 8 horas.")
    expira_em: str = Field(..., description="Data e hora de expiração da sessão.")


class SairSaida(BaseModel):
    mensagem: str


@router.get("/estado", response_model=EstadoAcessoSaida, summary="Informa se o console exige 2FA")
def estado(acesso: ServicoAcesso = Depends(obter_acesso)) -> EstadoAcessoSaida:
    return EstadoAcessoSaida(exige_2fa=acesso.exige_2fa())


@router.post(
    "/entrar",
    response_model=SessaoSaida,
    summary="Entra no console com senha e código do autenticador",
    responses={
        401: {"model": ErroSaida, "description": "Senha ou código incorretos (`acesso_negado`)."},
        429: {"model": ErroSaida, "description": "5 falhas seguidas: bloqueio de 5 minutos (`muitas_tentativas`)."},
    },
)
def entrar(dados: EntrarEntrada, acesso: ServicoAcesso = Depends(obter_acesso)) -> SessaoSaida:
    return SessaoSaida(**acesso.entrar(dados.senha, dados.codigo))


@router.post("/sair", response_model=SairSaida, summary="Encerra a sessão do console")
def sair(sessao: str | None = Security(cabecalho_sessao), acesso: ServicoAcesso = Depends(obter_acesso)) -> SairSaida:
    acesso.sair(sessao)
    return SairSaida(mensagem="Sessão encerrada.")
