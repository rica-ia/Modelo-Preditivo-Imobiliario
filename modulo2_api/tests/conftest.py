"""Isola os testes: banco SQLite temporário, SMTP e 2FA desligados e token de teste."""

import os
import tempfile
from pathlib import Path

_PASTA = Path(tempfile.mkdtemp(prefix="avaliador-testes-"))
os.environ["AVALIADOR_BANCO"] = str(_PASTA / "teste.db")
os.environ["AVALIADOR_ADMIN_TOKEN"] = "token-de-teste"
os.environ["SMTP_USUARIO"] = ""
os.environ["SMTP_SENHA_APP"] = ""
os.environ["GOOGLE_MAPS_API_KEY"] = ""
os.environ["AVALIADOR_TOTP_SEGREDO"] = ""
os.environ["AVALIADOR_SENHA_ACESSO"] = ""
os.environ["AVALIADOR_SENHA_HASH"] = ""
os.environ["AVALIADOR_GEOCODIFICAR"] = "0"
