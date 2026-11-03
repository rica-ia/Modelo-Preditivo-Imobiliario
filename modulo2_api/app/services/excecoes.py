"""Exceções de domínio, traduzidas em códigos HTTP pelo main.py."""


class RegraDeNegocioError(ValueError):
    """Dados bem formados, mas incoerentes para o negócio (vira HTTP 400)."""


class ModeloIndisponivelError(RuntimeError):
    """O artefato não está na memória (vira HTTP 503)."""


class AcessoNegadoError(PermissionError):
    """Token de administrador ausente ou incorreto (vira HTTP 401)."""


class ConsoleNaoConfiguradoError(RuntimeError):
    """AVALIADOR_ADMIN_TOKEN não configurado no .env (vira HTTP 503)."""


class ChaveInvalidaError(PermissionError):
    """X-API-Key desconhecida (vira HTTP 401)."""


class ChaveRevogadaError(PermissionError):
    """X-API-Key revogada pelo administrador (vira HTTP 403)."""


class LimiteExcedidoError(RuntimeError):
    """Cota mensal do plano esgotada (vira HTTP 429)."""


class NaoEncontradoError(LookupError):
    """Recurso inexistente (vira HTTP 404)."""


class CredenciaisInvalidasError(PermissionError):
    """Senha ou código do autenticador incorretos no acesso com 2FA (vira HTTP 401)."""


class MuitasTentativasError(RuntimeError):
    """Falhas seguidas no acesso com 2FA: bloqueio temporário (vira HTTP 429)."""


class ChaveSuspensaError(PermissionError):
    """Chave suspensa temporariamente pelo administrador (vira HTTP 403)."""
