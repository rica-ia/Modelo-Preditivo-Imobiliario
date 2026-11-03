"""
# Configuração central da API

Todos os caminhos são relativos à pasta do projeto (nada de caminho absoluto da
máquina), para que qualquer avaliador rode a API depois do `git clone`.
"""

import sys
from pathlib import Path

PASTA_APP = Path(__file__).resolve().parent
PASTA_MODULO2 = PASTA_APP.parent
RAIZ_REPOSITORIO = PASTA_MODULO2.parent

# O artefato serializado referencia classes do pacote `src/` do Módulo 1
# (engenharia de atributos e regressor em log). A raiz precisa estar no path
# para que o joblib consiga reconstruir o pipeline.
if str(RAIZ_REPOSITORIO) not in sys.path:
    sys.path.insert(0, str(RAIZ_REPOSITORIO))

PASTA_MODELOS = PASTA_MODULO2 / "models"
ARQUIVO_MODELO = PASTA_MODELOS / "modelo_imobiliario_v2.joblib"
ARQUIVO_METRICAS = PASTA_MODELOS / "metricas_v2.json"
ARQUIVO_REGIOES = PASTA_MODELOS / "regioes_v2.json"
PASTA_WEB = PASTA_APP / "web"

VERSAO_API = "2.0.0"
M2_POR_SQFT = 0.092903
REFERENCIA_MERCADO = "King County (WA), vendas de mai/2014 a mai/2015"
