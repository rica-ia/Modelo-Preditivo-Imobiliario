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

from .config import ARQUIVO_METRICAS, ARQUIVO_MODELO, ARQUIVO_REGIOES, PASTA_WEB, VERSAO_API
from .erros import registrar_tratadores
from .routers import modelo, predicao, saude
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

# ## Portal web (opcional): servido pela própria API quando a pasta existir
app.mount("/assets", StaticFiles(directory=PASTA_WEB / "assets", check_dir=False), name="assets")


@app.get("/", include_in_schema=False)
def portal():
    pagina = PASTA_WEB / "index.html"
    return FileResponse(pagina) if pagina.exists() else RedirectResponse("/docs")
