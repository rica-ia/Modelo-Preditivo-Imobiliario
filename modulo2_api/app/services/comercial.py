"""
# Serviço comercial: clientes, chaves de API e consumo

A chave tem o formato `aval_<aleatório>` e só é mostrada na emissão; o banco
guarda apenas o SHA-256. O uso conta as predições atendidas (HTTP 200) no mês
corrente e é comparado ao limite do plano.
"""

import hashlib
import logging
import secrets
from datetime import datetime
from email import message_from_bytes, policy
from pathlib import Path

from .banco import Banco, agora
from .email import enviar, montar_email
from .excecoes import ChaveInvalidaError, ChaveRevogadaError, LimiteExcedidoError, NaoEncontradoError

log = logging.getLogger("avaliador")

LIMITES = {"basico": 100, "profissional": 1_000, "empresarial": 10_000}


def _hash(chave: str) -> str:
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()


def _inicio_do_mes() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-01")


class ServicoComercial:
    def __init__(self, banco: Banco):
        self.banco = banco

    # ## Emissão
    def criar_chave(self, nome: str, email: str, empresa: str | None, plano: str) -> dict:
        limite = LIMITES[plano]
        cliente_id = self.banco.executar(
            "INSERT INTO clientes (nome, email, empresa, plano, criado_em) VALUES (?, ?, ?, ?, ?)",
            (nome, email, empresa, plano, agora()),
        )
        chave = "aval_" + secrets.token_urlsafe(24)
        prefixo = chave[:12]
        chave_id = self.banco.executar(
            "INSERT INTO chaves (cliente_id, prefixo, hash_sha256, limite_mensal, criada_em) VALUES (?, ?, ?, ?, ?)",
            (cliente_id, prefixo, _hash(chave), limite, agora()),
        )
        mensagem = montar_email(nome, email, chave, plano, limite)
        resultado = enviar(mensagem, self.banco.pasta_emails, f"cliente{cliente_id}", chave, prefixo)
        envio_id = self.banco.executar(
            "INSERT INTO envios_email (cliente_id, destinatario, assunto, modo, status, criado_em, arquivo)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (cliente_id, email, mensagem["Subject"], resultado["modo"], resultado["status"], agora(), resultado["arquivo"]),
        )
        return {
            "cliente_id": cliente_id,
            "chave_id": chave_id,
            "prefixo": prefixo,
            "chave": chave,
            "plano": plano,
            "limite_mensal": limite,
            "email": {
                "enviado": resultado["enviado"],
                "modo": resultado["modo"],
                "destinatario": email,
                "mensagem": resultado["mensagem"],
                "envio_id": envio_id,
            },
        }

    def listar_clientes(self) -> list[dict]:
        linhas = self.banco.consultar(
            """
            SELECT c.id AS cliente_id, c.nome, c.email, c.empresa, c.plano, c.criado_em,
                   k.id AS chave_id, k.prefixo, k.limite_mensal, k.revogada_em,
                   (SELECT COUNT(*) FROM predicoes p
                     WHERE p.chave_id = k.id AND p.status_http = 200 AND p.criado_em >= ?) AS uso_mes
              FROM clientes c JOIN chaves k ON k.cliente_id = c.id
             ORDER BY k.id DESC
            """,
            (_inicio_do_mes(),),
        )
        for linha in linhas:
            linha["ativa"] = linha.pop("revogada_em") is None
        return linhas

    def revogar(self, chave_id: int) -> dict:
        chave = self.banco.um("SELECT id, revogada_em FROM chaves WHERE id = ?", (chave_id,))
        if not chave:
            raise NaoEncontradoError(f"Chave {chave_id} não encontrada.")
        revogada_em = chave["revogada_em"] or agora()
        self.banco.executar("UPDATE chaves SET revogada_em = ? WHERE id = ?", (revogada_em, chave_id))
        return {"chave_id": chave_id, "revogada_em": revogada_em}

    def html_do_email(self, envio_id: int) -> str:
        envio = self.banco.um("SELECT arquivo FROM envios_email WHERE id = ?", (envio_id,))
        if not envio or not envio["arquivo"] or not Path(envio["arquivo"]).exists():
            raise NaoEncontradoError(f"E-mail {envio_id} não encontrado.")
        mensagem = message_from_bytes(Path(envio["arquivo"]).read_bytes(), policy=policy.default)
        return mensagem.get_body(preferencelist=("html", "plain")).get_content()

    # ## Uso da chave
    def _usadas_no_mes(self, chave_id: int) -> int:
        linha = self.banco.um(
            "SELECT COUNT(*) AS total FROM predicoes WHERE chave_id = ? AND status_http = 200 AND criado_em >= ?",
            (chave_id, _inicio_do_mes()),
        )
        return linha["total"]

    def autenticar(self, chave: str | None, quantidade: int = 1) -> dict | None:
        """Sem chave: acesso livre (None). Com chave: valida, confere a cota e devolve o registro."""
        if not chave:
            return None
        registro = self.banco.um(
            "SELECT k.id, k.limite_mensal, k.revogada_em, c.nome, c.plano"
            " FROM chaves k JOIN clientes c ON c.id = k.cliente_id WHERE k.hash_sha256 = ?",
            (_hash(chave),),
        )
        if not registro:
            raise ChaveInvalidaError("Chave de API inválida.")
        if registro["revogada_em"]:
            raise ChaveRevogadaError("Esta chave de API foi revogada.")
        if self._usadas_no_mes(registro["id"]) + quantidade > registro["limite_mensal"]:
            raise LimiteExcedidoError("Limite mensal do plano atingido.")
        return registro

    def uso(self, chave: str | None) -> dict:
        registro = self.autenticar(chave, quantidade=0)
        if registro is None:
            raise ChaveInvalidaError("Informe a chave no cabeçalho X-API-Key.")
        usadas = self._usadas_no_mes(registro["id"])
        return {
            "cliente": registro["nome"],
            "plano": registro["plano"],
            "limite_mensal": registro["limite_mensal"],
            "usadas_mes": usadas,
            "restantes": max(registro["limite_mensal"] - usadas, 0),
        }

    # ## Registro das predições (nunca derruba a resposta)
    def registrar(self, linhas: list[dict]) -> None:
        try:
            with self.banco.conexao() as con:
                con.executemany(
                    "INSERT INTO predicoes (criado_em, chave_id, origem, cep, area_util_m2, preco_estimado_usd,"
                    " latencia_ms, status_http) VALUES (:criado_em, :chave_id, :origem, :cep, :area_util_m2,"
                    " :preco_estimado_usd, :latencia_ms, :status_http)",
                    [{"criado_em": agora(), **linha} for linha in linhas],
                )
        except Exception:
            log.exception("Falha ao registrar predição no banco")
