"""
# Serviço comercial: clientes, chaves de API e consumo

A chave tem o formato `aval_<aleatório>` e só é mostrada na emissão; o banco
guarda apenas o SHA-256. O uso conta as predições atendidas (HTTP 200) no mês
corrente e é comparado ao limite do plano.

Gestão do cliente: troca de plano (o limite vale na hora), suspensão temporária e
reativação, troca da chave (a antiga é revogada e a nova vai por e-mail), edição do
cadastro e revogação definitiva, com aviso por e-mail ao cliente (só com o prefixo
da chave). Cada ação fica na trilha `eventos_comerciais`, e o
faturamento soma as mensalidades das chaves ativas.
"""

import hashlib
import logging
import secrets
from datetime import datetime
from email import message_from_bytes, policy
from pathlib import Path

from .banco import Banco, agora
from .email import enviar, montar_email, montar_email_revogacao
from .excecoes import (
    ChaveInvalidaError,
    ChaveRevogadaError,
    ChaveSuspensaError,
    LimiteExcedidoError,
    NaoEncontradoError,
    RegraDeNegocioError,
)
from .planos import LIMITES, NOMES_PLANOS, PLANOS, PRECOS_USD

ALERTA_CONSUMO = 0.8  # chaves com 80 % ou mais do limite aparecem como "perto do limite"

log = logging.getLogger("avaliador")

def _hash(chave: str) -> str:
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()


def _inicio_do_mes() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-01")


class ServicoComercial:
    def __init__(self, banco: Banco):
        self.banco = banco

    # ## Emissão
    def criar_chave(self, nome: str, email: str, empresa: str | None, plano: str) -> dict:
        cliente_id = self.banco.executar(
            "INSERT INTO clientes (nome, email, empresa, plano, criado_em) VALUES (?, ?, ?, ?, ?)",
            (nome, email, empresa, plano, agora()),
        )
        resultado = self._emitir(cliente_id, nome, email, plano)
        self._evento(cliente_id, resultado["chave_id"], "emissao", f"plano {NOMES_PLANOS[plano]}")
        return resultado

    def _emitir(self, cliente_id: int, nome: str, email: str, plano: str) -> dict:
        """Gera a chave, grava o hash e envia o e-mail com as instruções."""
        limite = LIMITES[plano]
        chave = "aval_" + secrets.token_urlsafe(24)
        prefixo = chave[:12]
        chave_id = self.banco.executar(
            "INSERT INTO chaves (cliente_id, prefixo, hash_sha256, limite_mensal, criada_em) VALUES (?, ?, ?, ?, ?)",
            (cliente_id, prefixo, _hash(chave), limite, agora()),
        )
        mensagem = montar_email(nome, email, chave, plano, limite)
        return {
            "cliente_id": cliente_id,
            "chave_id": chave_id,
            "prefixo": prefixo,
            "chave": chave,
            "plano": plano,
            "limite_mensal": limite,
            "preco_mensal_usd": PRECOS_USD[plano],
            "email": self._enviar_ao_cliente(cliente_id, email, mensagem, chave, prefixo),
        }

    def _enviar_ao_cliente(self, cliente_id: int, email: str, mensagem, chave: str | None, prefixo: str) -> dict:
        """Envia (ou salva em .eml) e registra o envio em `envios_email`."""
        resultado = enviar(mensagem, self.banco.pasta_emails, f"cliente{cliente_id}", chave, prefixo)
        envio_id = self.banco.executar(
            "INSERT INTO envios_email (cliente_id, destinatario, assunto, modo, status, criado_em, arquivo)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (cliente_id, email, mensagem["Subject"], resultado["modo"], resultado["status"], agora(), resultado["arquivo"]),
        )
        return {
            "enviado": resultado["enviado"],
            "modo": resultado["modo"],
            "destinatario": email,
            "mensagem": resultado["mensagem"],
            "envio_id": envio_id,
        }

    def listar_clientes(self) -> list[dict]:
        linhas = self.banco.consultar(
            """
            SELECT c.id AS cliente_id, c.nome, c.email, c.empresa, c.plano, c.criado_em,
                   k.id AS chave_id, k.prefixo, k.limite_mensal, k.revogada_em, k.suspensa_em,
                   (SELECT COUNT(*) FROM predicoes p
                     WHERE p.chave_id = k.id AND p.status_http = 200 AND p.criado_em >= ?) AS uso_mes
              FROM clientes c JOIN chaves k ON k.cliente_id = c.id
             ORDER BY k.id DESC
            """,
            (_inicio_do_mes(),),
        )
        for linha in linhas:
            self._situacao(linha)
        return linhas

    @staticmethod
    def _situacao(linha: dict) -> dict:
        revogada, suspensa = linha.pop("revogada_em", None), linha.pop("suspensa_em", None)
        linha["ativa"] = revogada is None
        linha["situacao"] = "revogada" if revogada else "suspensa" if suspensa else "ativa"
        linha["preco_mensal_usd"] = PRECOS_USD.get(linha["plano"], 0.0)
        return linha

    # ## Gestão do cliente
    def _evento(self, cliente_id: int, chave_id: int | None, tipo: str, detalhe: str | None = None) -> None:
        self.banco.executar(
            "INSERT INTO eventos_comerciais (cliente_id, chave_id, tipo, detalhe, criado_em) VALUES (?, ?, ?, ?, ?)",
            (cliente_id, chave_id, tipo, detalhe, agora()),
        )

    def _chave(self, chave_id: int, viva: bool = True) -> dict:
        chave = self.banco.um(
            "SELECT k.id, k.cliente_id, k.prefixo, k.revogada_em, k.suspensa_em, c.nome, c.email, c.plano"
            " FROM chaves k JOIN clientes c ON c.id = k.cliente_id WHERE k.id = ?",
            (chave_id,),
        )
        if not chave:
            raise NaoEncontradoError(f"Chave {chave_id} não encontrada.")
        if viva and chave["revogada_em"]:
            raise RegraDeNegocioError("Esta chave foi revogada; emita uma nova chave para o cliente.")
        return chave

    def revogar(self, chave_id: int) -> dict:
        chave = self._chave(chave_id, viva=False)
        revogada_em = chave["revogada_em"] or agora()
        aviso = None
        if not chave["revogada_em"]:
            self.banco.executar("UPDATE chaves SET revogada_em = ? WHERE id = ?", (revogada_em, chave_id))
            self._evento(chave["cliente_id"], chave_id, "revogacao", "revogação definitiva")
            mensagem = montar_email_revogacao(chave["nome"], chave["email"], chave["prefixo"], chave["plano"])
            aviso = self._enviar_ao_cliente(chave["cliente_id"], chave["email"], mensagem, None, chave["prefixo"])
        return {"chave_id": chave_id, "revogada_em": revogada_em, "email": aviso}

    def trocar_plano(self, chave_id: int, plano: str) -> dict:
        chave = self._chave(chave_id)
        anterior = chave["plano"]
        if plano == anterior:
            raise RegraDeNegocioError(f"O cliente já está no plano {NOMES_PLANOS[plano]}.")
        self.banco.executar("UPDATE clientes SET plano = ? WHERE id = ?", (plano, chave["cliente_id"]))
        self.banco.executar(
            "UPDATE chaves SET limite_mensal = ? WHERE cliente_id = ? AND revogada_em IS NULL",
            (LIMITES[plano], chave["cliente_id"]),
        )
        movimento = "upgrade" if PRECOS_USD[plano] > PRECOS_USD[anterior] else "downgrade"
        self._evento(chave["cliente_id"], chave_id, "troca_plano",
                     f"{NOMES_PLANOS[anterior]} → {NOMES_PLANOS[plano]} ({movimento})")
        return {"chave_id": chave_id, "plano_anterior": anterior, "plano": plano, "movimento": movimento,
                "limite_mensal": LIMITES[plano], "preco_mensal_usd": PRECOS_USD[plano]}

    def suspender(self, chave_id: int, motivo: str | None = None) -> dict:
        chave = self._chave(chave_id)
        suspensa_em = chave["suspensa_em"] or agora()
        if not chave["suspensa_em"]:
            self.banco.executar("UPDATE chaves SET suspensa_em = ? WHERE id = ?", (suspensa_em, chave_id))
            self._evento(chave["cliente_id"], chave_id, "suspensao", motivo or "suspensão temporária")
        return {"chave_id": chave_id, "situacao": "suspensa", "em": suspensa_em}

    def reativar(self, chave_id: int) -> dict:
        chave = self._chave(chave_id)
        if chave["suspensa_em"]:
            self.banco.executar("UPDATE chaves SET suspensa_em = NULL WHERE id = ?", (chave_id,))
            self._evento(chave["cliente_id"], chave_id, "reativacao", "acesso liberado")
        return {"chave_id": chave_id, "situacao": "ativa", "em": agora()}

    def rotacionar(self, chave_id: int) -> dict:
        """Troca a chave (vazamento, saída de funcionário etc.): revoga a antiga e envia a nova por e-mail."""
        chave = self._chave(chave_id)
        self.banco.executar("UPDATE chaves SET revogada_em = ? WHERE id = ?", (agora(), chave_id))
        resultado = self._emitir(chave["cliente_id"], chave["nome"], chave["email"], chave["plano"])
        if chave["suspensa_em"]:  # a suspensão acompanha o cliente na chave nova
            self.banco.executar("UPDATE chaves SET suspensa_em = ? WHERE id = ?",
                                (chave["suspensa_em"], resultado["chave_id"]))
        self._evento(chave["cliente_id"], resultado["chave_id"], "rotacao",
                     f"chave #{chave_id} substituída pela #{resultado['chave_id']}")
        return {**resultado, "chave_anterior_id": chave_id}

    def editar_cliente(self, cliente_id: int, dados: dict) -> dict:
        atual = self.banco.um("SELECT id, nome, email, empresa FROM clientes WHERE id = ?", (cliente_id,))
        if not atual:
            raise NaoEncontradoError(f"Cliente {cliente_id} não encontrado.")
        mudancas = {k: v for k, v in dados.items()
                    if k in ("nome", "email", "empresa") and (v is not None or k == "empresa") and v != atual[k]}
        if mudancas:
            colunas = ", ".join(f"{k} = ?" for k in mudancas)
            self.banco.executar(f"UPDATE clientes SET {colunas} WHERE id = ?", (*mudancas.values(), cliente_id))
            self._evento(cliente_id, None, "edicao", "alterado: " + ", ".join(sorted(mudancas)))
        return self.detalhe_cliente(cliente_id)

    def detalhe_cliente(self, cliente_id: int) -> dict:
        cliente = self.banco.um(
            "SELECT id AS cliente_id, nome, email, empresa, plano, criado_em FROM clientes WHERE id = ?", (cliente_id,))
        if not cliente:
            raise NaoEncontradoError(f"Cliente {cliente_id} não encontrado.")
        inicio = _inicio_do_mes()
        chaves = [self._situacao(c) for c in self.banco.consultar(
            "SELECT k.id AS chave_id, k.prefixo, k.limite_mensal, k.criada_em, k.revogada_em, k.suspensa_em, ? AS plano,"
            " (SELECT COUNT(*) FROM predicoes p WHERE p.chave_id = k.id AND p.status_http = 200 AND p.criado_em >= ?)"
            " AS uso_mes FROM chaves k WHERE k.cliente_id = ? ORDER BY k.id DESC",
            (cliente["plano"], inicio, cliente_id))]
        eventos = self.banco.consultar(
            "SELECT tipo, detalhe, chave_id, criado_em FROM eventos_comerciais WHERE cliente_id = ?"
            " ORDER BY id DESC LIMIT 50", (cliente_id,))
        uso_dias = self.banco.consultar(
            "SELECT substr(p.criado_em, 1, 10) AS dia, COUNT(*) AS total FROM predicoes p"
            " JOIN chaves k ON k.id = p.chave_id WHERE k.cliente_id = ? AND p.status_http = 200 AND p.criado_em >= ?"
            " GROUP BY dia ORDER BY dia", (cliente_id, inicio))
        emails = self.banco.consultar(
            "SELECT id AS envio_id, assunto, modo, status, criado_em FROM envios_email WHERE cliente_id = ?"
            " ORDER BY id DESC", (cliente_id,))
        uso_mes = sum(c["uso_mes"] for c in chaves)
        limite = LIMITES[cliente["plano"]]
        return {**cliente, "plano_nome": NOMES_PLANOS[cliente["plano"]], "limite_mensal": limite,
                "preco_mensal_usd": PRECOS_USD[cliente["plano"]], "uso_mes": uso_mes,
                "consumo_pct": round(100 * uso_mes / limite, 1), "chaves": chaves, "eventos": eventos,
                "uso_por_dia": uso_dias, "emails": emails, "faturas": self._faturas(cliente_id)}

    def _tem_faturas(self) -> bool:
        return bool(self.banco.um("SELECT 1 AS ok FROM sqlite_master WHERE type = 'table' AND name = 'faturas'"))

    def _faturas(self, cliente_id: int) -> list[dict]:
        if not self._tem_faturas():
            return []
        return self.banco.consultar(
            "SELECT id, competencia, plano, valor_usd, predicoes, status, vencimento, paga_em FROM faturas"
            " WHERE cliente_id = ? ORDER BY competencia DESC, id DESC", (cliente_id,))

    def _resumo_faturas(self) -> dict:
        """Contas a receber: recebido no mês corrente, em aberto e vencido."""
        vazio = {"recebido_mes_usd": 0.0, "em_aberto_usd": 0.0, "vencido_usd": 0.0, "qtd_vencidas": 0}
        if not self._tem_faturas():
            return vazio
        linha = self.banco.um(
            "SELECT COALESCE(SUM(CASE WHEN status = 'paga' AND paga_em >= ? THEN valor_usd END), 0) AS recebido_mes_usd,"
            " COALESCE(SUM(CASE WHEN status = 'em_aberto' THEN valor_usd END), 0) AS em_aberto_usd,"
            " COALESCE(SUM(CASE WHEN status = 'vencida' THEN valor_usd END), 0) AS vencido_usd,"
            " COUNT(CASE WHEN status = 'vencida' THEN 1 END) AS qtd_vencidas FROM faturas", (_inicio_do_mes(),))
        return {**vazio, **(linha or {})}

    def faturamento(self) -> dict:
        """Receita recorrente: chaves ativas pagam a mensalidade; suspensas e revogadas, não."""
        clientes = self.listar_clientes()
        pagantes = [c for c in clientes if c["situacao"] == "ativa"]
        receita = sum(c["preco_mensal_usd"] for c in pagantes)
        por_plano = []
        for codigo, plano in PLANOS.items():
            do_plano = [c for c in pagantes if c["plano"] == codigo]
            por_plano.append({"plano": codigo, "nome": plano["nome"], "chaves_ativas": len(do_plano),
                              "receita_mensal_usd": sum(c["preco_mensal_usd"] for c in do_plano),
                              "predicoes_mes": sum(c["uso_mes"] for c in do_plano)})
        perto = [{"cliente_id": c["cliente_id"], "chave_id": c["chave_id"], "nome": c["nome"], "plano": c["plano"],
                  "uso_mes": c["uso_mes"], "limite_mensal": c["limite_mensal"],
                  "consumo_pct": round(100 * c["uso_mes"] / c["limite_mensal"], 1)}
                 for c in pagantes if c["limite_mensal"] and c["uso_mes"] >= ALERTA_CONSUMO * c["limite_mensal"]]
        return {
            "receita_mensal_usd": receita,
            "receita_anual_prevista_usd": receita * 12,
            "ticket_medio_usd": round(receita / len(pagantes), 2) if pagantes else 0.0,
            "chaves_ativas": len(pagantes),
            "chaves_suspensas": sum(c["situacao"] == "suspensa" for c in clientes),
            "chaves_revogadas": sum(c["situacao"] == "revogada" for c in clientes),
            "predicoes_mes": sum(c["uso_mes"] for c in clientes),
            "por_plano": por_plano,
            "perto_do_limite": perto,
            "faturas": self._resumo_faturas(),
        }

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
            "SELECT k.id, k.limite_mensal, k.revogada_em, k.suspensa_em, c.nome, c.plano"
            " FROM chaves k JOIN clientes c ON c.id = k.cliente_id WHERE k.hash_sha256 = ?",
            (_hash(chave),),
        )
        if not registro:
            raise ChaveInvalidaError("Chave de API inválida.")
        if registro["revogada_em"]:
            raise ChaveRevogadaError("Esta chave de API foi revogada.")
        if registro["suspensa_em"]:
            raise ChaveSuspensaError("Esta chave de API está suspensa. Fale com o administrador da plataforma.")
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
