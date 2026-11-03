"""
# Roteador da administração do banco

Console do administrador para o SQLite: seções navegáveis com busca, paginação e ordenação,
detalhe de um registro, exportação (CSV pt-BR ou JSON), baixa e exclusão de faturas, exclusão
de laudos, saúde do arquivo e cópia de segurança. Tudo exige `X-Admin-Token` ou sessão 2FA.

As rotas fixas (`/secoes`, `/saude`, `/backup`) e `/{secao}/exportar` vêm antes das rotas com
parâmetro, para não serem capturadas por `/{secao}` ou `/{secao}/{registro_id}`.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Query, Response
from fastapi.responses import FileResponse

from ..schemas.admin_banco import (
    BaixaFaturaEntrada,
    Direcao,
    ExclusaoSaida,
    FormatoExportacao,
    ListagemSaida,
    RegistroSaida,
    SaudeBancoSaida,
    SecaoSaida,
)
from ..schemas.sistema import ErroSaida
from ..services.admin_banco import ServicoAdminBanco
from ..services.banco import Banco
from .dependencias import exigir_admin, obter_banco

router = APIRouter(prefix="/v1/admin/banco", tags=["Banco de dados"], dependencies=[Depends(exigir_admin)])

ERROS_ADMIN = {
    401: {"model": ErroSaida, "description": "Token de administrador ausente ou incorreto."},
    503: {"model": ErroSaida, "description": "Console não configurado no .env."},
}
ERROS_SECAO = {**ERROS_ADMIN, 404: {"model": ErroSaida, "description": "Seção ou registro inexistente."}}
SECAO = Path(..., description="clientes, chaves, faturas, envios_email, eventos_comerciais, avaliacoes, "
                              "predicoes, vendas_historicas ou modelos.", examples=["clientes"])


def obter_admin_banco(banco: Banco = Depends(obter_banco)) -> ServicoAdminBanco:
    return ServicoAdminBanco(banco)


@router.get("/secoes", response_model=list[SecaoSaida], responses=ERROS_ADMIN,
            summary="Seções do banco: título, total de registros, colunas e permissões")
def secoes(servico: ServicoAdminBanco = Depends(obter_admin_banco)) -> list[SecaoSaida]:
    return [SecaoSaida(**s) for s in servico.secoes()]


@router.get("/saude", response_model=SaudeBancoSaida, responses=ERROS_ADMIN,
            summary="Saúde do arquivo: tamanho, integridade e linhas por tabela")
def saude(servico: ServicoAdminBanco = Depends(obter_admin_banco)) -> SaudeBancoSaida:
    return SaudeBancoSaida(**servico.saude())


@router.get(
    "/backup",
    response_class=FileResponse,
    responses={**ERROS_ADMIN, 200: {"content": {"application/vnd.sqlite3": {}}, "description": "Cópia do banco."}},
    summary="Baixa uma cópia consistente do banco (API de backup do SQLite)",
)
def backup(tarefas: BackgroundTasks, servico: ServicoAdminBanco = Depends(obter_admin_banco)) -> FileResponse:
    caminho, nome = servico.backup()
    tarefas.add_task(caminho.unlink, missing_ok=True)
    return FileResponse(caminho, media_type="application/vnd.sqlite3", filename=nome)


@router.patch("/faturas/{registro_id}", response_model=RegistroSaida,
              responses={**ERROS_SECAO, 400: {"model": ErroSaida}},
              summary="Baixa de fatura: muda o status (paga preenche paga_em; os demais o limpam)")
def atualizar_fatura(registro_id: int, dados: BaixaFaturaEntrada,
                     servico: ServicoAdminBanco = Depends(obter_admin_banco)) -> RegistroSaida:
    return RegistroSaida(**servico.atualizar_fatura(registro_id, dados.status))


@router.get(
    "/{secao}/exportar",
    response_class=Response,
    responses={**ERROS_SECAO, 200: {"content": {"text/csv": {}, "application/json": {}},
                                    "description": "Arquivo para download."}},
    summary="Exporta a seção (com a busca aplicada) em CSV (Excel pt-BR) ou JSON",
)
def exportar(
    secao: str = SECAO,
    busca: str | None = Query(None, max_length=120, description="Texto procurado nas colunas de busca."),
    formato: FormatoExportacao = Query("csv", description="csv ou json."),
    ordem: str | None = Query(None, max_length=40, description="Coluna de ordenação (da lista da seção)."),
    direcao: Direcao = Query("desc"),
    servico: ServicoAdminBanco = Depends(obter_admin_banco),
) -> Response:
    conteudo, tipo, nome = servico.exportar(secao, busca, formato, ordem, direcao)
    return Response(conteudo, media_type=tipo, headers={"Content-Disposition": f'attachment; filename="{nome}"'})


@router.get("/{secao}", response_model=ListagemSaida, responses={**ERROS_SECAO, 400: {"model": ErroSaida}},
            summary="Lista a seção com busca, paginação e ordenação")
def listar(
    secao: str = SECAO,
    busca: str | None = Query(None, max_length=120, description="Texto procurado nas colunas de busca."),
    pagina: int = Query(1, ge=1, description="Página (a partir de 1)."),
    por_pagina: int = Query(20, ge=1, le=100, description="Registros por página (1 a 100)."),
    ordem: str | None = Query(None, max_length=40, description="Coluna de ordenação (da lista da seção)."),
    direcao: Direcao = Query("desc", description="asc ou desc."),
    servico: ServicoAdminBanco = Depends(obter_admin_banco),
) -> ListagemSaida:
    return ListagemSaida(**servico.listar(secao, busca, pagina, por_pagina, ordem, direcao))


@router.get("/{secao}/{registro_id}", response_model=RegistroSaida, responses=ERROS_SECAO,
            summary="Mostra um registro completo da seção")
def registro(registro_id: int, secao: str = SECAO,
             servico: ServicoAdminBanco = Depends(obter_admin_banco)) -> RegistroSaida:
    return RegistroSaida(**servico.registro(secao, registro_id))


@router.delete("/{secao}/{registro_id}", response_model=ExclusaoSaida,
               responses={**ERROS_SECAO, 400: {"model": ErroSaida, "description": "Seção sem exclusão permitida."}},
               summary="Exclui um registro (só laudos de avaliação e faturas)")
def excluir(registro_id: int, secao: str = SECAO,
            servico: ServicoAdminBanco = Depends(obter_admin_banco)) -> ExclusaoSaida:
    return ExclusaoSaida(**servico.excluir(secao, registro_id))
