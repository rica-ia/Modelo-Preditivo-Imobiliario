"""Exceções de domínio, traduzidas em códigos HTTP pelo main.py."""


class RegraDeNegocioError(ValueError):
    """Dados bem formados, mas incoerentes para o negócio (vira HTTP 400)."""


class ModeloIndisponivelError(RuntimeError):
    """O artefato não está na memória (vira HTTP 503)."""
