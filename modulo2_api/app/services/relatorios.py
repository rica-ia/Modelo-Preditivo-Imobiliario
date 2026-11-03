"""Relatórios de uso calculados direto no SQLite."""

from datetime import datetime

from ..config import RAIZ_REPOSITORIO
from .banco import Banco


def resumo(banco: Banco) -> dict:
    hoje = datetime.now().astimezone().strftime("%Y-%m-%d")
    totais = banco.um(
        """
        SELECT COUNT(*) AS total_predicoes,
               SUM(CASE WHEN substr(criado_em, 1, 10) = ? THEN 1 ELSE 0 END) AS predicoes_hoje,
               AVG(CASE WHEN status_http = 200 THEN latencia_ms END) AS latencia_media_ms,
               AVG(CASE WHEN status_http = 200 THEN preco_estimado_usd END) AS preco_medio_usd
          FROM predicoes
        """,
        (hoje,),
    )
    return {
        "total_predicoes": totais["total_predicoes"] or 0,
        "predicoes_hoje": totais["predicoes_hoje"] or 0,
        "clientes": banco.um("SELECT COUNT(*) AS n FROM clientes")["n"],
        "chaves_ativas": banco.um("SELECT COUNT(*) AS n FROM chaves WHERE revogada_em IS NULL")["n"],
        "latencia_media_ms": round(totais["latencia_media_ms"] or 0.0, 2),
        "preco_medio_usd": round(totais["preco_medio_usd"] or 0.0, 2),
        "por_dia": banco.consultar(
            "SELECT substr(criado_em, 1, 10) AS dia, COUNT(*) AS total FROM predicoes"
            " GROUP BY dia ORDER BY dia DESC LIMIT 14"
        )[::-1],
        "por_origem": banco.consultar(
            "SELECT origem, COUNT(*) AS total FROM predicoes GROUP BY origem ORDER BY total DESC"
        ),
        "por_status": banco.consultar(
            "SELECT status_http AS status, COUNT(*) AS total FROM predicoes GROUP BY status_http ORDER BY status_http"
        ),
    }


def predicoes_recentes(banco: Banco, limite: int) -> list[dict]:
    return banco.consultar(
        """
        SELECT p.id, p.criado_em, p.origem, COALESCE(c.nome, 'anônimo') AS cliente, p.cep,
               p.area_util_m2, p.preco_estimado_usd, p.latencia_ms, p.status_http
          FROM predicoes p
          LEFT JOIN chaves k ON k.id = p.chave_id
          LEFT JOIN clientes c ON c.id = k.cliente_id
         ORDER BY p.id DESC LIMIT ?
        """,
        (limite,),
    )


def esquema(banco: Banco) -> dict:
    try:
        arquivo = str(banco.caminho.relative_to(RAIZ_REPOSITORIO))
    except ValueError:
        arquivo = banco.caminho.name
    return {"banco": "SQLite", "arquivo": arquivo.replace("\\", "/"), "tabelas": banco.esquema_documentado()}
