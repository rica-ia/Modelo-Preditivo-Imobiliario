"""
# Módulo 2 · Ponto de entrada da API (main.py)

Monta a aplicação e inclui os roteadores. As regras de negócio ficam em
`services/`, os contratos de dados em `schemas/` e as rotas em `routers/`.

Execução, a partir da raiz do repositório:
    uvicorn modulo2_api.app.main:app --reload
"""

from fastapi import FastAPI

from .config import VERSAO_API
from .routers import saude

app = FastAPI(
    title="Avaliador Imobiliário · API preditiva",
    version=VERSAO_API,
    description="Estimativa de preço de imóveis de King County (WA) a partir do modelo do Módulo 1.",
)

app.include_router(saude.router)
