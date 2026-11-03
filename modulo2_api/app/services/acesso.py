"""
# Acesso ao console com senha e segundo fator (2FA)

Só biblioteca padrão, sem serviço externo nem custo:
- TOTP do RFC 6238 (HMAC-SHA1, 6 dígitos, passo de 30 s), o mesmo padrão dos apps
  autenticadores (Google Authenticator, Microsoft Authenticator, Authy etc.);
- a senha própria fica em `AVALIADOR_SENHA_HASH`, só como hash PBKDF2-SHA256 (gravado por
  `configurar_2fa --senha`); sem ele, vale `AVALIADOR_SENHA_ACESSO` e, se também estiver
  vazia, a senha de app do e-mail (`SMTP_SENHA_APP`);
- o segredo do TOTP fica em `AVALIADOR_TOTP_SEGREDO` (gerado por
  `python -m modulo2_api.ferramentas.configurar_2fa`). Sem ele, o 2FA fica desligado e
  o console continua usando só o token de administrador;
- 5 falhas seguidas bloqueiam novas tentativas por 5 minutos;
- a sessão é um token aleatório válido por 8 horas, guardado só como hash, na memória e num
  arquivo local fora do git (`banco/sessoes.json`), para sobreviver a um reinício da API.

A API pública de predição (`/v1/predict`) continua aberta: o 2FA protege apenas o
console administrativo.
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import threading
import time

from pathlib import Path

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
    """URI lido pelo QR Code nos apps autenticadores. Curto de propósito: só o rótulo e o segredo
    (6 dígitos e 30 s são o padrão do TOTP), o que cabe num QR de 33 x 33 pontos."""
    return f"otpauth://totp/Avaliador?secret={segredo}"


# ## Configuração lida do ambiente / .env
def segredo_configurado() -> str:
    return obter("AVALIADOR_TOTP_SEGREDO").strip()


def senha_esperada() -> str:
    return (obter("AVALIADOR_SENHA_ACESSO").strip() or obter("SMTP_SENHA_APP").strip()).replace(" ", "")


# ## Senha própria guardada só como hash (PBKDF2-SHA256), nunca em texto puro
ITERACOES_PBKDF2 = 200_000


def hash_senha(senha: str, sal: bytes | None = None, iteracoes: int = ITERACOES_PBKDF2) -> str:
    sal = sal or secrets.token_bytes(16)
    resumo = hashlib.pbkdf2_hmac("sha256", senha.encode(), sal, iteracoes)
    return f"pbkdf2_sha256${iteracoes}${sal.hex()}${resumo.hex()}"


def senha_confere(senha: str) -> bool:
    """Com `AVALIADOR_SENHA_HASH`, confere a senha digitada contra o hash; sem ele, contra a senha em texto."""
    guardado = obter("AVALIADOR_SENHA_HASH").strip()
    if guardado:
        try:
            _, iteracoes, sal, resumo = guardado.split("$")
            calculado = hashlib.pbkdf2_hmac("sha256", senha.encode(), bytes.fromhex(sal), int(iteracoes))
        except ValueError:
            return False
        return hmac.compare_digest(calculado.hex(), resumo)
    esperada = senha_esperada()
    return bool(esperada) and hmac.compare_digest(senha.replace(" ", "").encode(), esperada.encode())


def senha_configurada() -> bool:
    return bool(obter("AVALIADOR_SENHA_HASH").strip() or senha_esperada())


def _hash(valor: str) -> str:
    return hashlib.sha256(valor.encode()).hexdigest()


class ServicoAcesso:
    """Tentativas e bloqueio em memória; sessões em memória e, com `arquivo`, também em disco
    (só os hashes), para que reiniciar a API não derrube quem já entrou."""

    def __init__(self, arquivo: Path | None = None):
        self._trava = threading.Lock()
        self._falhas = 0
        self._bloqueado_ate = 0.0
        self._arquivo = arquivo
        self._sessoes: dict[str, float] = self._ler_sessoes()  # hash da sessão -> expiração (epoch)

    def _ler_sessoes(self) -> dict[str, float]:
        if not self._arquivo or not self._arquivo.exists():
            return {}
        try:
            agora = time.time()
            return {h: float(t) for h, t in json.loads(self._arquivo.read_text(encoding="utf-8")).items() if float(t) > agora}
        except (OSError, ValueError, AttributeError):
            return {}

    def _gravar_sessoes(self) -> None:
        """Chamado com a trava adquirida; grava de forma atômica (arquivo temporário + troca)."""
        if not self._arquivo:
            return
        try:
            self._arquivo.parent.mkdir(parents=True, exist_ok=True)
            temporario = self._arquivo.with_suffix(".tmp")
            temporario.write_text(json.dumps(self._sessoes), encoding="utf-8")
            os.replace(temporario, self._arquivo)
        except OSError:
            pass  # sem disco, as sessões seguem só na memória

    @staticmethod
    def exige_2fa() -> bool:
        return bool(segredo_configurado())

    def entrar(self, senha: str, codigo: str) -> dict:
        agora = time.time()
        with self._trava:
            if agora < self._bloqueado_ate:
                minutos = max(1, round((self._bloqueado_ate - agora) / 60))
                raise MuitasTentativasError(f"Muitas tentativas incorretas. Tente de novo em {minutos} min.")
            segredo = segredo_configurado()
            if not segredo or not senha_configurada():
                raise CredenciaisInvalidasError("O acesso com senha e 2FA não está configurado neste servidor.")
            if not (senha_confere(senha) and codigo_confere(segredo, codigo.strip(), agora)):
                self._registrar_falha(agora, "Senha ou código do autenticador incorretos")
            self._falhas = 0
        return self.abrir_sessao()

    def _conferir(self, ok, motivo: str) -> None:
        """Aplica o contador de falhas e o bloqueio a uma conferência (`ok` é chamado já com a trava)."""
        agora = time.time()
        with self._trava:
            if agora < self._bloqueado_ate:
                minutos = max(1, round((self._bloqueado_ate - agora) / 60))
                raise MuitasTentativasError(f"Muitas tentativas incorretas. Tente de novo em {minutos} min.")
            if not ok():
                self._registrar_falha(agora, motivo)
            self._falhas = 0

    def confirmar_senha(self, senha: str | None) -> None:
        """Confirmação com a senha da conta em ações sensíveis (emitir chave), dentro de uma sessão."""
        if not senha_configurada():
            raise CredenciaisInvalidasError("A senha de acesso não está configurada neste servidor.")
        self._conferir(lambda: senha_confere(senha or ""), "Senha da conta incorreta")

    def entrar_so_senha(self, senha: str) -> dict:
        """Entrada só com a senha (comando `avaliador senha`, restrito à própria máquina pela rota)."""
        if not senha_configurada():
            raise CredenciaisInvalidasError("A senha de acesso não está configurada neste servidor.")
        self._conferir(lambda: senha_confere(senha), "Senha incorreta")
        return self.abrir_sessao()

    def _registrar_falha(self, agora: float, motivo: str) -> None:
        """Chamado com a trava já adquirida; sempre levanta a exceção."""
        self._falhas += 1
        if self._falhas >= MAX_FALHAS:
            # A 5ª falha ainda responde 401; a partir da 6ª tentativa, 429 até o fim do bloqueio
            self._falhas, self._bloqueado_ate = 0, agora + BLOQUEIO_S
            raise CredenciaisInvalidasError(f"{motivo}. O acesso ficou bloqueado por 5 min.")
        restantes = MAX_FALHAS - self._falhas
        raise CredenciaisInvalidasError(f"{motivo}. Restam {restantes} tentativa(s).")

    def abrir_sessao(self) -> dict:
        """Sessão nova de 8 h (usada após senha + código, ou pela entrada de contingência local)."""
        agora = time.time()
        sessao = secrets.token_urlsafe(32)
        expira = agora + VALIDADE_SESSAO_S
        with self._trava:
            self._sessoes = {h: t for h, t in self._sessoes.items() if t > agora}
            self._sessoes[_hash(sessao)] = expira
            self._gravar_sessoes()
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
                self._gravar_sessoes()
                return False
            return True

    def sair(self, sessao: str | None) -> None:
        if sessao:
            with self._trava:
                self._sessoes.pop(_hash(sessao), None)
                self._gravar_sessoes()
