"""
# Painel do MLflow no portal

Resumo do modelo registrado no MLflow local (experimento, run, versão com o alias
`producao` e métricas), lido direto do banco SQLite do MLflow em modo somente leitura.
A API não importa o `mlflow`: se o banco não existir, o painel diz como criá-lo, e o
portal mostra o atalho para a interface do MLflow quando ela está no ar.
"""

import os
import sqlite3
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from ..config import RAIZ_REPOSITORIO

MODELO = "avaliador-imobiliario"
ALIAS = "producao"
METRICAS = ("teste_R2", "teste_MAE", "teste_RMSE", "teste_MAPE", "validacao_R2", "validacao_RMSE")


def _banco() -> Path:
    return Path(os.getenv("AVALIADOR_MLFLOW_DB") or RAIZ_REPOSITORIO / "mlruns" / "mlflow.db")


def _url() -> str:
    return (os.getenv("AVALIADOR_MLFLOW_URL") or "http://127.0.0.1:5000").rstrip("/")


def _ui_no_ar(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "/health", timeout=0.8) as resposta:
            return resposta.status == 200
    except OSError:
        return False


def _data(ms: int | None) -> str | None:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat() if ms else None


def resumo() -> dict:
    url, caminho = _url(), _banco()
    base = {"disponivel": False, "ui_url": url, "ui_no_ar": _ui_no_ar(url), "modelo": MODELO, "alias": ALIAS,
            "comando_registrar": "python -m modulo2_api.ferramentas.registrar_mlflow",
            "comando_ui": "mlflow ui --backend-store-uri sqlite:///mlruns/mlflow.db --port 5000 --host 127.0.0.1"}
    if not caminho.exists():
        return base
    con = sqlite3.connect(f"file:{caminho.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        versao = con.execute(
            "SELECT v.version, v.run_id, v.creation_time FROM registered_model_aliases a"
            " JOIN model_versions v ON v.name = a.name AND v.version = a.version WHERE a.name = ? AND a.alias = ?",
            (MODELO, ALIAS)).fetchone()
        if not versao:
            return base
        run = con.execute("SELECT name, experiment_id, status FROM runs WHERE run_uuid = ?", (versao["run_id"],)).fetchone()
        metricas = {r["key"]: r["value"] for r in con.execute(
            f"SELECT key, value FROM latest_metrics WHERE run_uuid = ? AND key IN ({','.join('?' * len(METRICAS))})",
            (versao["run_id"], *METRICAS))}
        total = con.execute("SELECT COUNT(*) FROM model_versions WHERE name = ?", (MODELO,)).fetchone()[0]
    except sqlite3.Error:
        return base
    finally:
        con.close()
    experimento = run["experiment_id"] if run else None
    return {**base, "disponivel": True, "versao": int(versao["version"]), "versoes": total, "run_id": versao["run_id"],
            "run_nome": run["name"] if run else None, "status_run": run["status"] if run else None,
            "registrado_em": _data(versao["creation_time"]), "metricas": metricas,
            "link_run": f"{url}/#/experiments/{experimento}/runs/{versao['run_id']}" if experimento is not None else url,
            "link_modelo": f"{url}/#/models/{MODELO}/versions/{versao['version']}"}
