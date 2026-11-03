"""
# Módulo 2 · Ponto de entrada da API (main.py)

Monta a aplicação: ciclo de vida (lifespan), tratamento de erros, inclusão dos
roteadores e, quando existir, o portal web. As regras de negócio ficam em
`services/`, os contratos de dados em `schemas/` e as rotas em `routers/`.

Execução, a partir da raiz do repositório:
    uvicorn modulo2_api.app.main:app --reload
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import (
    ARQUIVO_ESQUEMA,
    ARQUIVO_METRICAS,
    ARQUIVO_MODELO,
    ARQUIVO_REGIOES,
    PASTA_WEB,
    VERSAO_API,
    caminho_banco,
)
from .erros import registrar_tratadores
from .routers import comercial, modelo, predicao, relatorios, saude
from .services.banco import Banco
from .services.comercial import ServicoComercial
from .services.modelo import ServicoModelo

log = logging.getLogger("avaliador")


# ## Fase 3 — Ciclo de vida: o modelo vai para a RAM uma única vez, na subida
@asynccontextmanager
async def lifespan(app: FastAPI):
    servico = ServicoModelo(ARQUIVO_MODELO, ARQUIVO_METRICAS, ARQUIVO_REGIOES)
    try:
        servico.carregar()
        servico.aquecer()
        log.info("Modelo %s carregado na memória", servico.versao)
    except Exception:
        # A API sobe mesmo assim: /health mostra o problema e /v1/predict devolve 503.
        log.exception("Falha ao carregar o modelo")
    app.state.servico_modelo = servico

    # Banco SQLite de documentação: criado e migrado aqui, sem afetar o modelo.
    banco = Banco(caminho_banco(), ARQUIVO_ESQUEMA)
    try:
        banco.migrar()
    except Exception:
        log.exception("Falha ao preparar o banco SQLite")
    app.state.banco = banco
    app.state.comercial = ServicoComercial(banco)
    yield
    servico.descarregar()


app = FastAPI(
    title="Avaliador Imobiliário · API preditiva",
    version=VERSAO_API,
    description="Estimativa de preço de imóveis de King County (WA) a partir do modelo do Módulo 1.",
    lifespan=lifespan,
)

# ## Fase 5 — Erros padronizados e roteadores
registrar_tratadores(app)
app.include_router(saude.router)
app.include_router(predicao.router)
app.include_router(modelo.router)
app.include_router(comercial.router)
app.include_router(relatorios.router)

# ## Portal web (opcional): servido pela própria API quando a pasta existir
app.mount("/assets", StaticFiles(directory=PASTA_WEB / "assets", check_dir=False), name="assets")


@app.get("/", include_in_schema=False)
def portal():
    pagina = PASTA_WEB / "index.html"
    return FileResponse(pagina) if pagina.exists() else RedirectResponse("/docs")
