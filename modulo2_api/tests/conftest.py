"""Isola os testes: banco SQLite temporário, SMTP desligado e token de teste."""

import os
import tempfile
from pathlib import Path

_PASTA = Path(tempfile.mkdtemp(prefix="avaliador-testes-"))
os.environ["AVALIADOR_BANCO"] = str(_PASTA / "teste.db")
os.environ["AVALIADOR_ADMIN_TOKEN"] = "token-de-teste"
os.environ["SMTP_USUARIO"] = ""
os.environ["SMTP_SENHA_APP"] = ""
