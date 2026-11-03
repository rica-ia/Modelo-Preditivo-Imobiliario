"""
# Acesso ao console com senha e segundo fator (2FA)

O portal pergunta em /v1/acesso/estado se o 2FA está ligado. Se estiver, a pessoa
entra com a senha e o código de 6 dígitos do app autenticador e recebe uma sessão,
enviada depois no cabeçalho X-Admin-Sessao das rotas do console comercial.
A API pública de predição (/v1/predict) não passa por aqui e continua aberta.
"""

from fastapi import APIRouter, Depends, Request, Security
from pydantic import BaseModel, ConfigDict, Field

from ..schemas.sistema import ErroSaida
from ..services.acesso import ServicoAcesso
from ..services.excecoes import AcessoNegadoError
from .dependencias import cabecalho_sessao, exigir_admin, obter_acesso
from .mapa3d import HOSTS_LOCAIS

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


@router.post(
    "/entrar-local",
    response_model=SessaoSaida,
    summary="Entrada de contingência, só na própria máquina",
    description="Abre uma sessão sem senha nem código, para o caso de o celular não estar à mão. "
                "Exige o token de administrador (`X-Admin-Token`, que só existe no `.env` local) e só "
                "responde a chamadas de 127.0.0.1; é o que o comando `avaliador direto` usa.",
    responses={401: {"model": ErroSaida, "description": "Token ausente/incorreto ou chamada fora da máquina local."}},
    dependencies=[Depends(exigir_admin)],
)
def entrar_local(request: Request, acesso: ServicoAcesso = Depends(obter_acesso)) -> SessaoSaida:
    if request.client is None or request.client.host not in HOSTS_LOCAIS:
        raise AcessoNegadoError("A entrada de contingência só funciona na própria máquina.")
    return SessaoSaida(**acesso.abrir_sessao())


class EntrarSenhaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    senha: str = Field(..., min_length=1, max_length=128, description="Senha da conta.")


@router.post(
    "/entrar-senha",
    response_model=SessaoSaida,
    summary="Entrada só com a senha, só na própria máquina",
    description="Abre uma sessão com a senha da conta, sem o código do app. Só responde a chamadas de "
                "127.0.0.1; é o que o comando `avaliador senha` usa. Mesmo contador de 5 falhas e bloqueio de 5 min.",
    responses={401: {"model": ErroSaida, "description": "Senha incorreta ou chamada fora da máquina local."},
               429: {"model": ErroSaida, "description": "Bloqueio de 5 min após 5 falhas."}},
)
def entrar_senha(dados: EntrarSenhaEntrada, request: Request, acesso: ServicoAcesso = Depends(obter_acesso)) -> SessaoSaida:
    if request.client is None or request.client.host not in HOSTS_LOCAIS:
        raise AcessoNegadoError("A entrada só com senha funciona apenas na própria máquina.")
    return SessaoSaida(**acesso.entrar_so_senha(dados.senha))
