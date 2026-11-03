"""
# Administração do banco SQLite

Navegação do console por **seções** (clientes, chaves, faturamento, e-mails, histórico
comercial, laudos, uso da API e vendas reais): busca, paginação, ordenação, detalhe de um
registro, exportação em CSV/JSON, baixa e exclusão de faturas, exclusão de laudos, saúde do
arquivo e cópia de segurança.

Segurança do SQL:
- nomes de tabela e de coluna saem **só** da lista fixa `SECOES`, nunca da requisição;
- a busca e os identificadores entram sempre como parâmetros (`?`);
- `chaves.hash_sha256` nunca é devolvido e `avaliacoes.entrada_json` só aparece no detalhe.

A tabela `faturas` e a coluna `clientes.sintetico` são opcionais aqui: num banco antigo,
sem elas, a seção de faturamento some da lista e a coluna deixa de aparecer.
"""

import json
import math
import os
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime
from pathlib import Path

from .avaliacoes import exportar_csv
from .banco import DESCRICOES, Banco, agora
from .excecoes import NaoEncontradoError, RegraDeNegocioError

SITUACAO_CHAVE = (
    "CASE WHEN ch.revogada_em IS NOT NULL THEN 'revogada' "
    "WHEN ch.suspensa_em IS NOT NULL THEN 'suspensa' ELSE 'ativa' END"
)
STATUS_FATURA = ("paga", "em_aberto", "vencida", "cancelada")

# Cada seção: tabela base (alias t), JOINs de leitura, colunas da listagem (nome -> expressão SQL),
# colunas pesquisáveis e permissões. Uma coluna com "requer" só aparece se existir na tabela base.
SECOES: dict[str, dict] = {
    "clientes": {
        "titulo": "Clientes",
        "tabela": "clientes",
        "chave": "id",
        "juncoes": "",
        "colunas": {
            "id": "t.id", "nome": "t.nome", "email": "t.email", "empresa": "t.empresa", "plano": "t.plano",
            "criado_em": "t.criado_em", "sintetico": "t.sintetico",
            "chaves": "(SELECT COUNT(*) FROM chaves c2 WHERE c2.cliente_id = t.id)",
        },
        "requer": {"sintetico": "sintetico"},
        "busca": ["nome", "email", "empresa"],
        "rotulos": {"chaves": "Chaves emitidas para o cliente."},
    },
    "chaves": {
        "titulo": "Chaves de API emitidas",
        "tabela": "chaves",
        "chave": "id",
        "juncoes": "LEFT JOIN clientes cl ON cl.id = t.cliente_id",
        "colunas": {
            "id": "t.id", "cliente_id": "t.cliente_id", "cliente_nome": "cl.nome", "prefixo": "t.prefixo",
            "limite_mensal": "t.limite_mensal", "situacao": SITUACAO_CHAVE.replace("ch.", "t."),
            "criada_em": "t.criada_em", "suspensa_em": "t.suspensa_em", "revogada_em": "t.revogada_em",
        },
        "busca": ["prefixo", "cliente_nome"],
        "rotulos": {"situacao": "ativa, suspensa ou revogada."},
        "ocultas": ["hash_sha256"],
    },
    "faturas": {
        "titulo": "Faturamento",
        "tabela": "faturas",
        "chave": "id",
        "juncoes": "LEFT JOIN clientes cl ON cl.id = t.cliente_id",
        "colunas": {
            "id": "t.id", "cliente_id": "t.cliente_id", "cliente_nome": "cl.nome", "chave_id": "t.chave_id",
            "competencia": "t.competencia", "plano": "t.plano", "valor_usd": "t.valor_usd",
            "predicoes": "t.predicoes", "status": "t.status", "emitida_em": "t.emitida_em",
            "vencimento": "t.vencimento", "paga_em": "t.paga_em",
        },
        "busca": ["competencia", "status", "plano", "cliente_nome"],
        "descricao": "Faturas mensais por chave: competência, plano, valor e situação do pagamento.",
        "rotulos": {
            "id": "Identificador da fatura.", "cliente_id": "Cliente cobrado.", "chave_id": "Chave faturada.",
            "competencia": "Mês de referência (AAAA-MM).", "plano": "Plano no mês.",
            "valor_usd": "Valor da fatura, em dólares.", "predicoes": "Predições atendidas no mês.",
            "status": "paga, em_aberto, vencida ou cancelada.", "emitida_em": "Data de emissão.",
            "vencimento": "Data de vencimento.", "paga_em": "Data do pagamento (vazio se não paga).",
        },
        "pode_excluir": True,
        "pode_editar": True,
    },
    "envios_email": {
        "titulo": "E-mails enviados",
        "tabela": "envios_email",
        "chave": "id",
        "juncoes": "LEFT JOIN clientes cl ON cl.id = t.cliente_id",
        "colunas": {
            "id": "t.id", "cliente_id": "t.cliente_id", "cliente_nome": "cl.nome", "destinatario": "t.destinatario",
            "assunto": "t.assunto", "modo": "t.modo", "status": "t.status", "criado_em": "t.criado_em",
            "arquivo": "t.arquivo",
        },
        "busca": ["destinatario", "assunto", "status"],
    },
    "eventos_comerciais": {
        "titulo": "Histórico comercial",
        "tabela": "eventos_comerciais",
        "chave": "id",
        "juncoes": "LEFT JOIN clientes cl ON cl.id = t.cliente_id",
        "colunas": {
            "id": "t.id", "cliente_id": "t.cliente_id", "cliente_nome": "cl.nome", "chave_id": "t.chave_id",
            "tipo": "t.tipo", "detalhe": "t.detalhe", "criado_em": "t.criado_em",
        },
        "busca": ["tipo", "detalhe", "cliente_nome"],
    },
    "avaliacoes": {
        "titulo": "Laudos de avaliação",
        "tabela": "avaliacoes",
        "chave": "id",
        "juncoes": "",
        "colunas": {
            "id": "t.id", "criado_em": "t.criado_em", "titulo": "t.titulo", "responsavel": "t.responsavel",
            "origem": "t.origem", "cep": "t.cep", "cidade": "t.cidade", "quartos": "t.quartos",
            "banheiros": "t.banheiros", "area_util_m2": "t.area_util_m2", "padrao": "t.padrao",
            "preco_estimado_usd": "t.preco_estimado_usd", "preco_real_usd": "t.preco_real_usd",
            "faixa_preco": "t.faixa_preco", "versao_modelo": "t.versao_modelo", "sintetico": "t.sintetico",
        },
        "requer": {"sintetico": "sintetico"},
        "busca": ["titulo", "cep", "cidade", "responsavel"],
        "pode_excluir": True,
    },
    "predicoes": {
        "titulo": "Uso da API (predições)",
        "tabela": "predicoes",
        "chave": "id",
        "juncoes": "LEFT JOIN chaves ch ON ch.id = t.chave_id LEFT JOIN clientes cl ON cl.id = ch.cliente_id",
        "colunas": {
            "id": "t.id", "criado_em": "t.criado_em", "chave_id": "t.chave_id", "chave_prefixo": "ch.prefixo",
            "cliente_nome": "cl.nome", "origem": "t.origem", "cep": "t.cep", "area_util_m2": "t.area_util_m2",
            "preco_estimado_usd": "t.preco_estimado_usd", "latencia_ms": "t.latencia_ms",
            "status_http": "t.status_http",
        },
        "busca": ["cep", "origem", "status_http"],
        "rotulos": {"chave_prefixo": "Prefixo da chave usada."},
    },
    "vendas_historicas": {
        "titulo": "Vendas reais (base)",
        "tabela": "vendas_historicas",
        "chave": "id_venda",
        "juncoes": "",
        "colunas": {
            "id_venda": "t.id_venda", "id_imovel": "t.id_imovel", "data_venda": "t.data_venda",
            "preco_usd": "t.preco_usd", "quartos": "t.quartos", "banheiros": "t.banheiros",
            "area_util_m2": "t.area_util_m2", "padrao": "t.padrao", "condicao": "t.condicao",
            "ano_construcao": "t.ano_construcao", "cep": "t.cep", "cidade": "t.cidade",
            "preco_m2_usd": "t.preco_m2_usd", "faixa_preco": "t.faixa_preco",
        },
        "busca": ["cep", "cidade"],
    },
}

ROTULOS_COMUNS = {"cliente_nome": "Nome do cliente."}


class ServicoAdminBanco:
    def __init__(self, banco: Banco):
        self.banco = banco

    # ## Estrutura disponível no arquivo atual
    def _colunas_da_tabela(self, tabela: str) -> set[str]:
        # `tabela` vem só de SECOES; PRAGMA não aceita parâmetro, por isso a lista fixa.
        return {c["name"] for c in self.banco.consultar(f'PRAGMA table_info("{tabela}")')}

    def _secao(self, secao: str) -> tuple[dict, dict[str, str]]:
        """Configuração da seção e colunas efetivas; 404 se a seção não existe ou a tabela falta."""
        config = SECOES.get(secao)
        if config is None:
            raise NaoEncontradoError(f"Seção desconhecida: {secao}. Consulte /v1/admin/banco/secoes.")
        existentes = self._colunas_da_tabela(config["tabela"])
        if not existentes:
            raise NaoEncontradoError(f"A seção {secao} ainda não existe neste banco.")
        requer = config.get("requer", {})
        colunas = {nome: expr for nome, expr in config["colunas"].items()
                   if nome not in requer or requer[nome] in existentes}
        return config, colunas

    def _rotulos(self, secao: str, config: dict, colunas: dict) -> dict[str, str]:
        base = DESCRICOES.get(config["tabela"], {})
        extras = config.get("rotulos", {})
        return {c: extras.get(c) or base.get(c) or ROTULOS_COMUNS.get(c, "") for c in colunas}

    def _onde(self, config: dict, colunas: dict, busca: str | None) -> tuple[str, tuple]:
        termo = (busca or "").strip()
        if not termo:
            return "", ()
        termo = termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        alvos = [colunas[c] for c in config["busca"] if c in colunas]
        clausula = " OR ".join(f"CAST({expr} AS TEXT) LIKE ? ESCAPE '\\'" for expr in alvos)
        return f" WHERE ({clausula})", tuple(f"%{termo}%" for _ in alvos)

    def _total(self, tabela: str) -> int:
        return self.banco.um(f'SELECT COUNT(*) AS n FROM "{tabela}"')["n"]

    # ## Seções
    def secoes(self) -> list[dict]:
        resultado = []
        for secao, config in SECOES.items():
            try:
                _, colunas = self._secao(secao)
            except NaoEncontradoError:
                continue  # tabela ausente neste banco (por exemplo, faturas ainda não criada)
            resultado.append({
                "secao": secao,
                "titulo": config["titulo"],
                "descricao": config.get("descricao") or DESCRICOES.get(config["tabela"], {}).get("_tabela", ""),
                "tabela": config["tabela"],
                "total": self._total(config["tabela"]),
                "colunas": list(colunas),
                "colunas_busca": [c for c in config["busca"] if c in colunas],
                "rotulos": self._rotulos(secao, config, colunas),
                "pode_excluir": config.get("pode_excluir", False),
                "pode_editar": config.get("pode_editar", False),
            })
        return resultado

    def _consulta(self, config: dict, colunas: dict, busca: str | None, ordem: str | None, direcao: str) -> tuple:
        if ordem is not None and ordem not in colunas:
            raise RegraDeNegocioError(f"Ordenação inválida: use uma das colunas {', '.join(colunas)}.")
        chave = f"t.{config['chave']}"
        sentido = "ASC" if direcao == "asc" else "DESC"
        ordenacao = f"{colunas[ordem]} {sentido}, {chave} {sentido}" if ordem else f"{chave} {sentido}"
        selecao = ", ".join(f'{expr} AS "{nome}"' for nome, expr in colunas.items())
        de = f'FROM "{config["tabela"]}" t {config["juncoes"]}'
        onde, valores = self._onde(config, colunas, busca)
        return selecao, de, onde, valores, ordenacao

    def listar(self, secao: str, busca: str | None = None, pagina: int = 1, por_pagina: int = 20,
               ordem: str | None = None, direcao: str = "desc") -> dict:
        config, colunas = self._secao(secao)
        selecao, de, onde, valores, ordenacao = self._consulta(config, colunas, busca, ordem, direcao)
        total = self.banco.um(f"SELECT COUNT(*) AS n {de}{onde}", valores)["n"]
        linhas = self.banco.consultar(
            f"SELECT {selecao} {de}{onde} ORDER BY {ordenacao} LIMIT ? OFFSET ?",
            (*valores, por_pagina, (pagina - 1) * por_pagina),
        )
        return {
            "secao": secao, "titulo": config["titulo"], "total": total, "pagina": pagina,
            "por_pagina": por_pagina, "paginas": max(1, math.ceil(total / por_pagina)),
            "colunas": list(colunas), "linhas": linhas,
        }

    def registro(self, secao: str, registro_id: int) -> dict:
        config, colunas = self._secao(secao)
        extras = ", ".join(f'{expr} AS "{nome}"' for nome, expr in colunas.items() if not expr.startswith("t."))
        selecao = "t.*" + (f", {extras}" if extras else "")
        linha = self.banco.um(
            f'SELECT {selecao} FROM "{config["tabela"]}" t {config["juncoes"]} WHERE t.{config["chave"]} = ?',
            (registro_id,),
        )
        if linha is None:
            raise NaoEncontradoError(f"Registro {registro_id} não encontrado em {config['titulo']}.")
        for oculta in config.get("ocultas", []):
            linha.pop(oculta, None)
        return {"secao": secao, "registro": linha}

    # ## Exportação (mesmas regras de busca e ordem da listagem, sem paginação)
    def exportar(self, secao: str, busca: str | None, formato: str, ordem: str | None = None,
                 direcao: str = "desc") -> tuple[bytes, str, str]:
        config, colunas = self._secao(secao)
        selecao, de, onde, valores, ordenacao = self._consulta(config, colunas, busca, ordem, direcao)
        linhas = self.banco.consultar(f"SELECT {selecao} {de}{onde} ORDER BY {ordenacao}", valores)
        carimbo = datetime.now().strftime("%Y%m%d-%H%M")
        if formato == "json":
            conteudo = json.dumps(linhas, ensure_ascii=False, indent=2).encode("utf-8")
            return conteudo, "application/json; charset=utf-8", f"banco_{secao}_{carimbo}.json"
        return exportar_csv(linhas, list(colunas)), "text/csv; charset=utf-8", f"banco_{secao}_{carimbo}.csv"

    # ## Faturas: baixa (troca de status)
    def atualizar_fatura(self, fatura_id: int, status: str) -> dict:
        if status not in STATUS_FATURA:
            raise RegraDeNegocioError(f"Status inválido: use {', '.join(STATUS_FATURA)}.")
        self._secao("faturas")
        atual = self.banco.um("SELECT id, status, paga_em FROM faturas WHERE id = ?", (fatura_id,))
        if atual is None:
            raise NaoEncontradoError(f"Fatura {fatura_id} não encontrada.")
        paga_em = (atual["paga_em"] or agora()) if status == "paga" else None
        self.banco.executar("UPDATE faturas SET status = ?, paga_em = ? WHERE id = ?", (status, paga_em, fatura_id))
        return self.registro("faturas", fatura_id)

    # ## Exclusão: só laudos e faturas (o resto é trilha de auditoria ou base do modelo)
    def excluir(self, secao: str, registro_id: int) -> dict:
        config, _ = self._secao(secao)
        if not config.get("pode_excluir", False):
            raise RegraDeNegocioError(
                f"{config['titulo']} não pode ser excluído pelo console: é histórico ou base de referência."
            )
        self.registro(secao, registro_id)  # 404 se não existir
        self.banco.executar(f'DELETE FROM "{config["tabela"]}" WHERE {config["chave"]} = ?', (registro_id,))
        return {"secao": secao, "id": registro_id, "excluido": True}

    # ## Saúde e cópia de segurança
    def saude(self) -> dict:
        caminho = self.banco.caminho
        integridade = self.banco.um("PRAGMA integrity_check")
        nomes = self.banco.consultar(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        tabelas = []
        for item in nomes:
            nome = item["name"].replace('"', '""')
            tabelas.append({"nome": item["name"], "linhas": self.banco.um(f'SELECT COUNT(*) AS n FROM "{nome}"')["n"]})
        sinteticos = 0
        if "sintetico" in self._colunas_da_tabela("clientes"):
            sinteticos = self.banco.um("SELECT COUNT(*) AS n FROM clientes WHERE sintetico = 1")["n"]
        return {
            "arquivo": str(caminho),
            "tamanho_bytes": caminho.stat().st_size if caminho.exists() else 0,
            "integridade": next(iter(integridade.values())) if integridade else "desconhecida",
            "tabelas": tabelas,
            "sinteticos": {"clientes": sinteticos},
        }

    def backup(self) -> tuple[Path, str]:
        """Cópia consistente (API de backup do sqlite3) num arquivo temporário; quem chama apaga depois."""
        descritor, destino = tempfile.mkstemp(prefix="avaliador-backup-", suffix=".db")
        os.close(descritor)
        with closing(sqlite3.connect(self.banco.caminho, timeout=5)) as origem, \
                closing(sqlite3.connect(destino)) as copia:
            origem.backup(copia)
        nome = f"avaliador-backup-{datetime.now().strftime('%Y%m%d-%H%M')}.db"
        return Path(destino), nome
