"""
# Acesso ao console com senha e segundo fator (2FA)

Só biblioteca padrão, sem serviço externo nem custo:
- TOTP do RFC 6238 (HMAC-SHA1, 6 dígitos, passo de 30 s), o mesmo padrão dos apps
  autenticadores (Google Authenticator, Microsoft Authenticator, Authy etc.);
- a senha esperada é `AVALIADOR_SENHA_ACESSO`; se estiver vazia, vale a senha de app
  do e-mail (`SMTP_SENHA_APP`), por escolha do titular;
- o segredo do TOTP fica em `AVALIADOR_TOTP_SEGREDO` (gerado por
  `python -m modulo2_api.ferramentas.configurar_2fa`). Sem ele, o 2FA fica desligado e
  o console continua usando só o token de administrador;
- 5 falhas seguidas bloqueiam novas tentativas por 5 minutos;
- a sessão é um token aleatório válido por 8 horas, guardado na memória só como hash.

A API pública de predição (`/v1/predict`) continua aberta: o 2FA protege apenas o
console administrativo.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import threading
import time

from ..config import obter
from .excecoes import CredenciaisInvalidasError, MuitasTentativasError

PASSO_S = 30
DIGITOS = 6
JANELA = 1  # aceita o código anterior e o seguinte (relógio do celular adiantado ou atrasado)
MAX_FALHAS = 5
BLOQUEIO_S = 5 * 60
VALIDADE_SESSAO_S = 8 * 60 * 60


# ## TOTP (RFC 6238 sobre o HOTP do RFC 4226)
def gerar_segredo() -> str:
    """Segredo de 160 bits em base32, sem o preenchimento '='."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _decodificar(segredo: str) -> bytes:
    limpo = segredo.replace(" ", "").upper()
    return base64.b32decode(limpo + "=" * (-len(limpo) % 8))


def hotp(chave: bytes, contador: int, digitos: int = DIGITOS, algoritmo=hashlib.sha1) -> str:
    resumo = hmac.new(chave, struct.pack(">Q", contador), algoritmo).digest()
    deslocamento = resumo[-1] & 0x0F
    numero = struct.unpack(">I", resumo[deslocamento:deslocamento + 4])[0] & 0x7FFFFFFF
    return str(numero % 10 ** digitos).zfill(digitos)


def totp(segredo: str, instante: float | None = None) -> str:
    instante = time.time() if instante is None else instante
    return hotp(_decodificar(segredo), int(instante // PASSO_S))


def codigo_confere(segredo: str, codigo: str, instante: float | None = None) -> bool:
    if not (codigo.isdigit() and len(codigo) == DIGITOS):
        return False
    instante = time.time() if instante is None else instante
    chave, passo = _decodificar(segredo), int(instante // PASSO_S)
    return any(hmac.compare_digest(hotp(chave, passo + d), codigo) for d in range(-JANELA, JANELA + 1))


def uri_autenticador(segredo: str, conta: str = "admin") -> str:
    """URI lido pelo QR Code nos apps autenticadores."""
    emissor = "Avaliador%20Imobili%C3%A1rio"
    return f"otpauth://totp/{emissor}:{conta}?secret={segredo}&issuer={emissor}&digits={DIGITOS}&period={PASSO_S}"


# ## Configuração lida do ambiente / .env
def segredo_configurado() -> str:
    return obter("AVALIADOR_TOTP_SEGREDO").strip()


def senha_esperada() -> str:
    return (obter("AVALIADOR_SENHA_ACESSO").strip() or obter("SMTP_SENHA_APP").strip()).replace(" ", "")


def _hash(valor: str) -> str:
    return hashlib.sha256(valor.encode()).hexdigest()


class ServicoAcesso:
    """Tentativas, bloqueio e sessões do console, em memória (zeram ao reiniciar a API)."""

    def __init__(self):
        self._trava = threading.Lock()
        self._falhas = 0
        self._bloqueado_ate = 0.0
        self._sessoes: dict[str, float] = {}  # hash da sessão -> expiração (epoch)

    @staticmethod
    def exige_2fa() -> bool:
        return bool(segredo_configurado())

    def entrar(self, senha: str, codigo: str) -> dict:
        agora = time.time()
        with self._trava:
            if agora < self._bloqueado_ate:
                minutos = max(1, round((self._bloqueado_ate - agora) / 60))
                raise MuitasTentativasError(f"Muitas tentativas incorretas. Tente de novo em {minutos} min.")
            segredo, esperada = segredo_configurado(), senha_esperada()
            if not segredo or not esperada:
                raise CredenciaisInvalidasError("O acesso com senha e 2FA não está configurado neste servidor.")
            senha_ok = hmac.compare_digest(senha.replace(" ", "").encode(), esperada.encode())
            if not (senha_ok and codigo_confere(segredo, codigo.strip(), agora)):
                self._falhas += 1
                if self._falhas >= MAX_FALHAS:
                    # A 5ª falha ainda responde 401; a partir da 6ª tentativa, 429 até o fim do bloqueio
                    self._falhas, self._bloqueado_ate = 0, agora + BLOQUEIO_S
                    raise CredenciaisInvalidasError("Senha ou código incorretos. O acesso ficou bloqueado por 5 min.")
                restantes = MAX_FALHAS - self._falhas
                raise CredenciaisInvalidasError(f"Senha ou código do autenticador incorretos. Restam {restantes} tentativa(s).")
            self._falhas = 0
            sessao = secrets.token_urlsafe(32)
            expira = agora + VALIDADE_SESSAO_S
            self._sessoes = {h: t for h, t in self._sessoes.items() if t > agora}
            self._sessoes[_hash(sessao)] = expira
        return {"sessao": sessao, "expira_em": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(expira))}

    def sessao_valida(self, sessao: str | None) -> bool:
        if not sessao:
            return False
        with self._trava:
            expira = self._sessoes.get(_hash(sessao))
            if expira is None:
                return False
            if expira <= time.time():
                self._sessoes.pop(_hash(sessao), None)
                return False
            return True

    def sair(self, sessao: str | None) -> None:
        if sessao:
            with self._trava:
                self._sessoes.pop(_hash(sessao), None)
