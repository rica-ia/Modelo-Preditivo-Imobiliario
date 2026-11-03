"""
# Configuração central da API

Todos os caminhos são relativos à pasta do projeto (nada de caminho absoluto da
máquina), para que qualquer avaliador rode a API depois do `git clone`.
"""

import os
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

PASTA_BANCO = PASTA_MODULO2 / "banco"
ARQUIVO_ESQUEMA = PASTA_BANCO / "esquema.sql"
ARQUIVO_CEPS = PASTA_BANCO / "ceps_king_county.json"
ARQUIVO_ENV = RAIZ_REPOSITORIO / ".env"


# ## Variáveis de ambiente (.env na raiz, lido sem bibliotecas externas)
def _ler_env(caminho: Path) -> dict:
    valores = {}
    if caminho.exists():
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                chave, valor = linha.split("=", 1)
                valores[chave.strip()] = valor.strip().strip('"').strip("'")
    return valores


_ENV = _ler_env(ARQUIVO_ENV)


def obter(nome: str, padrao: str = "") -> str:
    """Variável do ambiente do sistema; se ausente, a do arquivo .env."""
    if nome in os.environ:
        return os.environ[nome]
    return _ENV.get(nome, padrao)


def caminho_banco() -> Path:
    caminho = Path(obter("AVALIADOR_BANCO", "modulo2_api/banco/avaliador.db"))
    return caminho if caminho.is_absolute() else RAIZ_REPOSITORIO / caminho


VERSAO_API = "2.0.0"
M2_POR_SQFT = 0.092903
REFERENCIA_MERCADO = "King County (WA), vendas de mai/2014 a mai/2015"
