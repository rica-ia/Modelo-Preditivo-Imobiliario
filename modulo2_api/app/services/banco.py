"""
# Banco SQLite de documentação

Guarda clientes, chaves de API (só o hash), o histórico de predições, os
e-mails enviados e as faturas. Linhas com `sintetico = 1` (em `clientes` e
`avaliacoes`) são a carga de exemplo de `services/sinteticos.py`, removível à parte. Cada operação abre e fecha a própria conexão: simples, segura
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
        "sintetico": "1 se o cliente é dado sintético de exemplo (fictício), 0 se é real.",
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
        "suspensa_em": "Data e hora da suspensão temporária (vazio se liberada).",
    },
    "eventos_comerciais": {
        "_tabela": "Trilha de auditoria do console comercial.",
        "id": "Identificador do evento.",
        "cliente_id": "Cliente afetado.",
        "chave_id": "Chave afetada (vazio em edição de cadastro).",
        "tipo": "emissao, troca_plano, suspensao, reativacao, rotacao, revogacao ou edicao.",
        "detalhe": "Resumo legível da mudança (por exemplo, basico → profissional).",
        "criado_em": "Data e hora do evento.",
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
    "faturas": {
        "_tabela": "Faturas mensais de cada cliente (na carga de exemplo, faturamento fictício).",
        "id": "Identificador da fatura.",
        "cliente_id": "Cliente faturado.",
        "chave_id": "Chave de API cobrada.",
        "competencia": "Mês de referência, no formato AAAA-MM.",
        "plano": "Plano vigente na competência.",
        "valor_usd": "Valor da mensalidade, em dólares (preço do plano).",
        "predicoes": "Predições atendidas (HTTP 200) na competência.",
        "status": "paga, em_aberto, vencida ou cancelada.",
        "emitida_em": "Data e hora da emissão.",
        "vencimento": "Data de vencimento.",
        "paga_em": "Data e hora do pagamento (vazio se não paga).",
    },
    "vendas_historicas": {
        "_tabela": "Vendas reais de King County (mai/2014 a mai/2015), limpas pelas regras do Módulo 1.",
        "id_venda": "Identificador da venda.",
        "id_imovel": "Identificador do imóvel na base original (há revendas).",
        "data_venda": "Data da venda.",
        "preco_usd": "Preço de venda, em dólares.",
        "quartos": "Número de quartos.",
        "banheiros": "Número de banheiros.",
        "area_util_m2": "Área útil, em m².",
        "area_terreno_m2": "Área do terreno, em m².",
        "padrao": "Padrão construtivo do condado (1 a 13).",
        "condicao": "Estado de conservação (1 a 5).",
        "vista": "Qualidade da vista (0 a 4).",
        "frente_agua": "1 se tem frente para a água.",
        "ano_construcao": "Ano de construção.",
        "ano_reforma": "Ano da última reforma (vazio se nunca reformado).",
        "cep": "CEP (zipcode).",
        "cidade": "Cidade de King County correspondente ao CEP.",
        "latitude": "Latitude.",
        "longitude": "Longitude.",
        "preco_m2_usd": "Preço por m² de área útil.",
        "faixa_preco": "Quartil de preço da base.",
    },
    "avaliacoes": {
        "_tabela": "Laudos de avaliação: os feitos no portal ou pela API e a amostra da base de teste.",
        "id": "Identificador do laudo.",
        "criado_em": "Data e hora da avaliação.",
        "titulo": "Título do laudo.",
        "responsavel": "Responsável pela avaliação.",
        "cliente_chave_id": "Chave de API usada (vazio no portal).",
        "origem": "portal, api ou amostra_base.",
        "entrada_json": "JSON completo enviado ao modelo.",
        "quartos": "Número de quartos.",
        "banheiros": "Número de banheiros.",
        "area_util_m2": "Área útil, em m².",
        "padrao": "Padrão construtivo.",
        "cep": "CEP do imóvel.",
        "cidade": "Cidade do imóvel.",
        "latitude": "Latitude.",
        "longitude": "Longitude.",
        "preco_estimado_usd": "Preço estimado pelo modelo.",
        "faixa_min": "Limite inferior da faixa provável.",
        "faixa_max": "Limite superior da faixa provável.",
        "preco_m2_usd": "Preço estimado por m².",
        "faixa_preco": "Quartil do preço estimado, nos limites da base.",
        "preco_real_usd": "Preço real de venda (só na amostra da base).",
        "versao_modelo": "Versão do modelo usada.",
        "latencia_ms": "Tempo de inferência.",
        "sintetico": "1 se o laudo é dado sintético de exemplo (fictício), 0 se é real.",
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
            # Bancos criados antes da suspensão de chaves ganham a coluna nova (o CREATE IF NOT EXISTS não altera tabelas)
            if con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chaves'").fetchone():
                colunas = {c["name"] for c in con.execute("PRAGMA table_info(chaves)").fetchall()}
                if "suspensa_em" not in colunas:
                    con.execute("ALTER TABLE chaves ADD COLUMN suspensa_em TEXT")
            # A marca de dado sintético (carga de exemplo) chega do mesmo jeito a clientes e avaliações
            for tabela in ("clientes", "avaliacoes"):
                if con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (tabela,)).fetchone():
                    colunas = {c["name"] for c in con.execute(f"PRAGMA table_info({tabela})").fetchall()}
                    if "sintetico" not in colunas:
                        con.execute(f"ALTER TABLE {tabela} ADD COLUMN sintetico INTEGER NOT NULL DEFAULT 0")
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
