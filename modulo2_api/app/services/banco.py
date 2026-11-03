"""
# Banco SQLite de documentação

Guarda clientes, chaves de API (só o hash), o histórico de predições e os
e-mails enviados. Cada operação abre e fecha a própria conexão: simples, segura
entre threads do servidor e suficiente para o volume de uma amostra.
"""

import sqlite3
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path

DESCRICOES = {
    "clientes": {
        "_tabela": "Clientes que contrataram a API.",
        "id": "Identificador do cliente.",
        "nome": "Nome do responsável.",
        "email": "E-mail que recebe a chave e as instruções.",
        "empresa": "Empresa do cliente (opcional).",
        "plano": "Plano contratado: basico, profissional ou empresarial.",
        "criado_em": "Data e hora do cadastro.",
    },
    "chaves": {
        "_tabela": "Chaves de API emitidas. A chave em si nunca é gravada, só o hash SHA-256.",
        "id": "Identificador da chave.",
        "cliente_id": "Cliente dono da chave.",
        "prefixo": "Início da chave, para identificação visual.",
        "hash_sha256": "Hash SHA-256 da chave completa.",
        "limite_mensal": "Predições permitidas por mês no plano.",
        "criada_em": "Data e hora da emissão.",
        "revogada_em": "Data e hora da revogação (vazio se ativa).",
    },
    "predicoes": {
        "_tabela": "Histórico de cada predição atendida ou recusada por regra de negócio.",
        "id": "Identificador da predição.",
        "criado_em": "Data e hora da requisição.",
        "chave_id": "Chave usada (vazio sem chave).",
        "origem": "api (com chave), portal ou anonima.",
        "cep": "CEP do imóvel avaliado.",
        "area_util_m2": "Área útil informada.",
        "preco_estimado_usd": "Preço devolvido pelo modelo (vazio em caso de erro).",
        "latencia_ms": "Tempo de inferência.",
        "status_http": "Código HTTP devolvido.",
    },
    "envios_email": {
        "_tabela": "E-mails de boas-vindas com a chave e as instruções de uso.",
        "id": "Identificador do envio.",
        "cliente_id": "Cliente destinatário.",
        "destinatario": "Endereço de destino.",
        "assunto": "Assunto do e-mail.",
        "modo": "smtp (enviado pelo Gmail) ou arquivo (.eml salvo localmente).",
        "status": "Resultado do envio.",
        "criado_em": "Data e hora do envio.",
        "arquivo": "Cópia .eml usada na pré-visualização.",
    },
}


def agora() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Banco:
    def __init__(self, caminho: Path, esquema: Path):
        self.caminho = Path(caminho)
        self.esquema = Path(esquema)

    @property
    def pasta_emails(self) -> Path:
        return self.caminho.parent / "emails"

    @contextmanager
    def conexao(self):
        with closing(sqlite3.connect(self.caminho, timeout=5)) as con:
            con.row_factory = sqlite3.Row
            con.execute("PRAGMA foreign_keys = ON")
            with con:
                yield con

    def migrar(self) -> None:
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        with self.conexao() as con:
            con.executescript(self.esquema.read_text(encoding="utf-8"))

    def executar(self, sql: str, parametros: tuple = ()) -> int:
        with self.conexao() as con:
            return con.execute(sql, parametros).lastrowid

    def consultar(self, sql: str, parametros: tuple = ()) -> list[dict]:
        with self.conexao() as con:
            return [dict(linha) for linha in con.execute(sql, parametros).fetchall()]

    def um(self, sql: str, parametros: tuple = ()) -> dict | None:
        linhas = self.consultar(sql, parametros)
        return linhas[0] if linhas else None

    def esquema_documentado(self) -> list[dict]:
        tabelas = []
        with self.conexao() as con:
            for nome, descricoes in DESCRICOES.items():
                colunas = con.execute(f"PRAGMA table_info({nome})").fetchall()
                linhas = con.execute(f"SELECT COUNT(*) FROM {nome}").fetchone()[0]
                indices = [
                    {
                        "nome": i["name"],
                        "colunas": [c["name"] for c in con.execute(f"PRAGMA index_info({i['name']})").fetchall()],
                        "unico": bool(i["unique"]),
                    }
                    for i in con.execute(f"PRAGMA index_list({nome})").fetchall()
                ]
                tabelas.append(
                    {
                        "nome": nome,
                        "descricao": descricoes["_tabela"],
                        "linhas": linhas,
                        "colunas": [
                            {"nome": c["name"], "tipo": c["type"], "descricao": descricoes.get(c["name"], "")}
                            for c in colunas
                        ],
                        "indices": indices,
                    }
                )
        return tabelas
