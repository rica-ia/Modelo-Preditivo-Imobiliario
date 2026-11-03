"""
# Tratamento padronizado de erros HTTP

Cada falha vira um JSON previsível, em português, e a API nunca cai:
- 400: regra de negócio violada (dados bem formados, mas incoerentes);
- 422: contrato Pydantic violado (tipo, faixa, campo ausente ou desconhecido);
- 404/405: rota inexistente ou método não permitido;
- 503: modelo fora da memória;
- 500: qualquer erro inesperado, sem expor detalhes internos.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .services.excecoes import ModeloIndisponivelError, RegraDeNegocioError

log = logging.getLogger("avaliador")

MENSAGENS = {
    "missing": "campo obrigatório",
    "extra_forbidden": "campo não permitido",
    "int_parsing": "deve ser um número inteiro",
    "int_from_float": "deve ser um número inteiro",
    "float_parsing": "deve ser um número",
    "bool_parsing": "deve ser verdadeiro ou falso",
    "string_type": "deve ser texto",
    "string_pattern_mismatch": "formato inválido",
    "multiple_of": "deve ser múltiplo de {multiple_of}",
    "greater_than_equal": "deve ser maior ou igual a {ge}",
    "less_than_equal": "deve ser menor ou igual a {le}",
    "too_short": "deve ter ao menos {min_length} item(ns)",
    "too_long": "deve ter no máximo {max_length} item(ns)",
    "json_invalid": "JSON malformado",
}


def _traduzir(erro: dict) -> dict:
    if erro.get("type") == "json_invalid":
        return {"campo": "corpo", "mensagem": MENSAGENS["json_invalid"]}
    campo = ".".join(str(parte) for parte in erro.get("loc", ()) if parte != "body") or "corpo"
    modelo = MENSAGENS.get(erro.get("type", ""))
    try:
        mensagem = modelo.format(**erro.get("ctx", {})) if modelo else erro.get("msg", "valor inválido")
    except (KeyError, IndexError):
        mensagem = erro.get("msg", "valor inválido")
    return {"campo": campo, "mensagem": mensagem}


async def dados_invalidos(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "erro": "dados_invalidos",
            "mensagem": "A requisição não atende ao contrato de entrada.",
            "detalhes": [_traduzir(erro) for erro in exc.errors()],
        },
    )


async def regra_de_negocio(request: Request, exc: RegraDeNegocioError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"erro": "regra_de_negocio", "mensagem": str(exc)})


async def modelo_indisponivel(request: Request, exc: ModeloIndisponivelError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"erro": "modelo_indisponivel", "mensagem": str(exc)})


HTTP_MENSAGENS = {
    404: ("nao_encontrado", "Rota não encontrada. Consulte a documentação em /docs."),
    405: ("metodo_nao_permitido", "Método HTTP não permitido nesta rota."),
}


async def erro_http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    codigo, mensagem = HTTP_MENSAGENS.get(exc.status_code, ("erro_http", str(exc.detail)))
    return JSONResponse(status_code=exc.status_code, content={"erro": codigo, "mensagem": mensagem}, headers=exc.headers)


async def erro_interno(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Erro inesperado em %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"erro": "erro_interno", "mensagem": "Erro inesperado no servidor. Tente novamente."},
    )


def registrar_tratadores(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, dados_invalidos)
    app.add_exception_handler(StarletteHTTPException, erro_http)
    app.add_exception_handler(RegraDeNegocioError, regra_de_negocio)
    app.add_exception_handler(ModeloIndisponivelError, modelo_indisponivel)
    app.add_exception_handler(Exception, erro_interno)
