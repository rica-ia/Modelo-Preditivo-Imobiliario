"""
# Roteador do registro do artefato

Lista os artefatos do modelo guardados no SQLite (tabela `modelos`) e verifica a
integridade de um deles: sha256 do BLOB, do arquivo em disco e do artefato lido na
subida, mais a previsão do modelo restaurado comparada à do modelo em memória.
A listagem é pública, como `GET /v1/modelo`, e só devolve metadados, nunca o binário. A
verificação é uma auditoria do administrador: restaura o BLOB num arquivo temporário (fora do
caminho das predições, que usam só o modelo carregado uma vez na subida).
`GET /v1/modelo/mlflow` resume o modelo registrado no MLflow local para o portal.
"""

from fastapi import APIRouter, Depends, Request

from ..schemas.sistema import ArtefatoSaida, ErroSaida, VerificacaoArtefatoSaida
from ..services import mlflow_painel
from ..services.excecoes import ModeloIndisponivelError
from ..services.registro_modelo import ServicoRegistroModelo
from .dependencias import exigir_admin

router = APIRouter(prefix="/v1/modelo", tags=["Modelo"])


def obter_registro(request: Request) -> ServicoRegistroModelo:
    registro = getattr(request.app.state, "registro_modelo", None)
    if registro is None:
        raise ModeloIndisponivelError("O registro do artefato não está disponível nesta execução.")
    return registro


@router.get(
    "/artefatos",
    response_model=list[ArtefatoSaida],
    responses={503: {"model": ErroSaida}},
    summary="Artefatos do modelo registrados no SQLite (sem o binário)",
)
def listar_artefatos(registro: ServicoRegistroModelo = Depends(obter_registro)) -> list[ArtefatoSaida]:
    return [ArtefatoSaida(**linha) for linha in registro.listar()]


@router.get(
    "/artefatos/{artefato_id}/verificar",
    response_model=VerificacaoArtefatoSaida,
    responses={401: {"model": ErroSaida}, 404: {"model": ErroSaida}, 503: {"model": ErroSaida}},
    dependencies=[Depends(exigir_admin)],
    summary="Auditoria (administrador): restaura o BLOB, confere o sha256 e compara a previsão com a do modelo em memória",
)
def verificar_artefato(artefato_id: int, registro: ServicoRegistroModelo = Depends(obter_registro)) -> VerificacaoArtefatoSaida:
    return VerificacaoArtefatoSaida(**registro.verificar(artefato_id))


@router.get(
    "/mlflow",
    summary="Modelo registrado no MLflow local: versão @producao, run, métricas e atalhos para a interface",
    description="Lido do banco SQLite do MLflow em modo somente leitura; a API não depende do pacote mlflow.",
)
def resumo_mlflow() -> dict:
    return mlflow_painel.resumo()
