"""
# Módulo 2 · Ponto de entrada da API (main.py)

Monta a aplicação: ciclo de vida (lifespan), tratamento de erros, inclusão dos
roteadores e, quando existir, o portal web. As regras de negócio ficam em
`services/`, os contratos de dados em `schemas/` e as rotas em `routers/`.

Execução, a partir da raiz do repositório:
    uvicorn modulo2_api.app.main:app --reload
"""

import logging
import time
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
    caminho_sessoes,
)
from .erros import registrar_tratadores
from .routers import acesso, avaliacoes, comercial, comodidades, endereco, mapa3d, modelo, predicao, relatorios, saude
from .routers import admin_banco
from .routers import sinteticos
from .services.acesso import ServicoAcesso
from .services.comodidades import ServicoComodidades
from .services.endereco import ServicoEndereco
from .services.avaliacoes import ServicoAvaliacoes
from .services.banco import Banco
from .services.carga import carga_inicial, limites_de_faixa
from .services.sinteticos import carga_automatica
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
    try:
        inicio = time.perf_counter()
        inseridos = carga_inicial(banco, servico)
        if any(inseridos.values()):
            log.info("Carga inicial do banco: %s em %.1f s", inseridos, time.perf_counter() - inicio)
    except Exception:
        log.exception("Falha na carga inicial do banco")
    try:
        sinteticos_inseridos = carga_automatica(banco, servico)  # AVALIADOR_DADOS_SINTETICOS=0 desliga
        if sinteticos_inseridos and any(sinteticos_inseridos.values()):
            log.info("Dados sintéticos de exemplo: %s", sinteticos_inseridos)
    except Exception:
        log.exception("Falha na carga dos dados sintéticos de exemplo")
    app.state.banco = banco
    app.state.comercial = ServicoComercial(banco)
    app.state.avaliacoes = ServicoAvaliacoes(banco, servico, app.state.comercial, limites_de_faixa(banco))
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
app.include_router(avaliacoes.router)
app.include_router(mapa3d.router)
app.include_router(acesso.router)
app.include_router(endereco.router)
app.include_router(comodidades.router)
app.include_router(admin_banco.router)
app.include_router(sinteticos.router)

# Sessões do console: hashes em memória e em banco/sessoes.json (fora do git), para sobreviver a reinícios
app.state.acesso = ServicoAcesso(arquivo=caminho_sessoes())
# Endereços já consultados no OpenStreetMap ficam em cache durante a execução
app.state.endereco = ServicoEndereco()
# Comodidades do entorno (Overpass/OpenStreetMap), também em cache durante a execução
app.state.comodidades = ServicoComodidades()

# ## Portal web (opcional): servido pela própria API quando a pasta existir
app.mount("/assets", StaticFiles(directory=PASTA_WEB / "assets", check_dir=False), name="assets")


@app.get("/", include_in_schema=False)
def portal():
    pagina = PASTA_WEB / "index.html"
    return FileResponse(pagina) if pagina.exists() else RedirectResponse("/docs")


@app.get("/visao3d", include_in_schema=False)
@app.get("/visao3d.html", include_in_schema=False)
def visao3d():
    """Voo 360° fotorrealista; sem chave no .env, a página cai na visão 3D do MapLibre."""
    pagina = PASTA_WEB / "visao3d.html"
    return FileResponse(pagina) if pagina.exists() else RedirectResponse("/")
