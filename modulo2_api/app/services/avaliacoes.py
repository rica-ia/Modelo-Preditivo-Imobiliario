"""
# Serviço de avaliações (laudos)

Grava cada avaliação com a predição recalculada no servidor (o cliente nunca
informa o preço), lista com filtros e paginação, exporta em CSV/JSON e monta o
laudo HTML (ver `services/laudo.py`) com comparáveis reais, referências de mercado do mesmo CEP e
cidade, endereço e comodidades do entorno.
"""

import csv
import io
import json
import statistics
from datetime import datetime

from ..schemas.imovel import ImovelEntrada
from .banco import Banco, agora
from .carga import classificar, mapa_de_cidades, rotulos_de_faixa
from .comercial import ServicoComercial
from .excecoes import NaoEncontradoError, RegraDeNegocioError
from .laudo import montar_laudo
from .modelo import ServicoModelo

ORDENACOES = {
    "recentes": "id DESC",
    "antigas": "id ASC",
    "preco_desc": "preco_estimado_usd DESC",
    "preco_asc": "preco_estimado_usd ASC",
}

COLUNAS_EXPORTACAO = [
    "id", "criado_em", "titulo", "responsavel", "origem", "cidade", "cep", "quartos", "banheiros", "area_util_m2",
    "padrao", "preco_estimado_usd", "faixa_min", "faixa_max", "preco_m2_usd", "faixa_preco", "preco_real_usd",
    "versao_modelo", "latencia_ms",
]


def _registro(linha: dict) -> dict:
    linha = dict(linha)
    linha["imovel"] = json.loads(linha.pop("entrada_json"))
    return linha


def _filtros(filtros: dict) -> tuple[str, list]:
    condicoes, valores = [], []
    for campo in ("cep", "cidade", "quartos", "faixa_preco", "origem"):
        if filtros.get(campo) is not None:
            condicoes.append(f"{campo} = ?")
            valores.append(filtros[campo])
    if filtros.get("preco_min") is not None:
        condicoes.append("preco_estimado_usd >= ?")
        valores.append(filtros["preco_min"])
    if filtros.get("preco_max") is not None:
        condicoes.append("preco_estimado_usd <= ?")
        valores.append(filtros["preco_max"])
    if filtros.get("busca"):
        condicoes.append("titulo LIKE ?")
        valores.append(f"%{filtros['busca']}%")
    return (" WHERE " + " AND ".join(condicoes)) if condicoes else "", valores


def _numero_br(valor) -> str:
    if valor is None:
        return ""
    if isinstance(valor, float):
        return f"{valor:.2f}".replace(".", ",")
    return str(valor)


class ServicoAvaliacoes:
    def __init__(self, banco: Banco, servico: ServicoModelo, comercial: ServicoComercial, limites: list[float]):
        self.banco = banco
        self.servico = servico
        self.comercial = comercial
        self.limites = limites
        self.cidades = mapa_de_cidades()

    # ## Criação (predição recalculada no servidor)
    def criar(self, titulo: str, responsavel: str | None, imovel: ImovelEntrada, chave: str | None) -> dict:
        registro_chave = self.comercial.autenticar(chave)
        chave_id = registro_chave["id"] if registro_chave else None
        origem = "api" if registro_chave else "portal"
        base_log = {"chave_id": chave_id, "origem": origem, "cep": imovel.cep, "area_util_m2": imovel.area_util_m2}
        try:
            previsao = self.servico.prever([imovel])[0]
        except RegraDeNegocioError:
            self.comercial.registrar([{**base_log, "preco_estimado_usd": None, "latencia_ms": None, "status_http": 400}])
            raise
        self.comercial.registrar(
            [{**base_log, "preco_estimado_usd": previsao.preco_estimado_usd, "latencia_ms": previsao.latencia_ms,
              "status_http": 200}]
        )
        novo_id = self.banco.executar(
            "INSERT INTO avaliacoes (criado_em, titulo, responsavel, cliente_chave_id, origem, entrada_json, quartos,"
            " banheiros, area_util_m2, padrao, cep, cidade, latitude, longitude, preco_estimado_usd, faixa_min,"
            " faixa_max, preco_m2_usd, faixa_preco, preco_real_usd, versao_modelo, latencia_ms)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                agora(), titulo, responsavel, chave_id, origem, imovel.model_dump_json(), imovel.quartos,
                imovel.banheiros, imovel.area_util_m2, imovel.padrao_construtivo, imovel.cep,
                self.cidades.get(imovel.cep, "King County"), imovel.latitude, imovel.longitude,
                previsao.preco_estimado_usd, previsao.faixa_provavel_usd.minimo, previsao.faixa_provavel_usd.maximo,
                previsao.preco_por_m2_usd, classificar(previsao.preco_estimado_usd, self.limites), None,
                previsao.versao_modelo, previsao.latencia_ms,
            ),
        )
        return self.obter(novo_id)

    # ## Consulta
    def obter(self, avaliacao_id: int) -> dict:
        linha = self.banco.um("SELECT * FROM avaliacoes WHERE id = ?", (avaliacao_id,))
        if not linha:
            raise NaoEncontradoError(f"Avaliação {avaliacao_id} não encontrada.")
        return _registro(linha)

    def listar(self, filtros: dict, pagina: int, limite: int, ordenacao: str) -> dict:
        onde, valores = _filtros(filtros)
        total = self.banco.um(f"SELECT COUNT(*) AS n FROM avaliacoes{onde}", tuple(valores))["n"]
        itens = self.banco.consultar(
            f"SELECT * FROM avaliacoes{onde} ORDER BY {ORDENACOES[ordenacao]} LIMIT ? OFFSET ?",
            (*valores, limite, (pagina - 1) * limite),
        )
        return {"total": total, "pagina": pagina, "limite": limite, "itens": [_registro(i) for i in itens]}

    def faixas(self) -> list[str]:
        return rotulos_de_faixa(self.limites)

    # ## Exportação
    def exportar(self, filtros: dict, formato: str, ordenacao: str = "recentes") -> tuple[bytes, str, str]:
        onde, valores = _filtros(filtros)
        linhas = self.banco.consultar(
            f"SELECT {', '.join(COLUNAS_EXPORTACAO)} FROM avaliacoes{onde} ORDER BY {ORDENACOES[ordenacao]}",
            tuple(valores),
        )
        carimbo = datetime.now().strftime("%Y%m%d-%H%M")
        if formato == "json":
            conteudo = json.dumps(linhas, ensure_ascii=False, indent=2).encode("utf-8")
            return conteudo, "application/json; charset=utf-8", f"avaliacoes_{carimbo}.json"
        return exportar_csv(linhas, COLUNAS_EXPORTACAO), "text/csv; charset=utf-8", f"avaliacoes_{carimbo}.csv"

    # ## Laudo HTML
    def _referencias(self, cep: str, cidade: str, preco_m2: float | None = None) -> dict:
        """Medianas e quartis do CEP e da cidade e o percentil do US$/m² do imóvel entre as vendas do CEP."""
        do_cep = self.banco.consultar("SELECT preco_usd, preco_m2_usd FROM vendas_historicas WHERE cep = ?", (cep,))
        da_cidade = self.banco.consultar("SELECT preco_usd, preco_m2_usd FROM vendas_historicas WHERE cidade = ?",
                                         (cidade,))
        m2_cep = sorted(r["preco_m2_usd"] for r in do_cep)
        m2_cidade = [r["preco_m2_usd"] for r in da_cidade]

        def quantil(valores: list[float], q: float) -> float | None:
            return statistics.quantiles(valores, n=100, method="inclusive")[round(q * 100) - 1] if len(valores) > 1 else None

        return {
            "cep": statistics.median(m2_cep) if m2_cep else None,
            "cidade": statistics.median(m2_cidade) if m2_cidade else None,
            "vendas_cep": len(m2_cep),
            "vendas_cidade": len(m2_cidade),
            "preco_mediano_cep": statistics.median(r["preco_usd"] for r in do_cep) if do_cep else None,
            "preco_mediano_cidade": statistics.median(r["preco_usd"] for r in da_cidade) if da_cidade else None,
            "m2_p10": quantil(m2_cep, 0.10), "m2_p25": quantil(m2_cep, 0.25),
            "m2_p75": quantil(m2_cep, 0.75), "m2_p90": quantil(m2_cep, 0.90),
            "percentil_m2": (sum(v <= preco_m2 for v in m2_cep) / len(m2_cep)) if m2_cep and preco_m2 else None,
        }

    def comparaveis(self, avaliacao: dict, quantidade: int = 5) -> list[dict]:
        imovel = avaliacao["imovel"]
        vendas = self.banco.consultar(
            "SELECT data_venda, preco_usd, quartos, banheiros, area_util_m2, padrao, ano_construcao, preco_m2_usd"
            " FROM vendas_historicas WHERE cep = ?",
            (imovel["cep"],),
        )

        def distancia(v: dict) -> float:
            return (
                abs(v["area_util_m2"] - imovel["area_util_m2"]) / max(imovel["area_util_m2"], 1)
                + abs(v["quartos"] - imovel["quartos"]) * 0.15
                + abs(v["banheiros"] - imovel["banheiros"]) * 0.10
                + abs(v["padrao"] - imovel["padrao_construtivo"]) * 0.20
                + abs(v["ano_construcao"] - imovel["ano_construcao"]) / 100
            )

        return sorted(vendas, key=distancia)[:quantidade]

    def laudo_html(self, avaliacao_id: int, endereco=None, comodidades=None) -> str:
        """Laudo completo; `endereco` e `comodidades` são os serviços do OpenStreetMap (opcionais, com cache)."""
        a = self.obter(avaliacao_id)
        imovel = a["imovel"]
        ref = self._referencias(a["cep"], a["cidade"], a["preco_m2_usd"])
        lat, lng = imovel["latitude"], imovel["longitude"]
        local = endereco.endereco(lat, lng) if endereco else None
        entorno = comodidades.comodidades(lat, lng) if comodidades else None
        return montar_laudo(a, imovel, ref, self.comparaveis(a), self.servico.metricas, local, entorno)


def exportar_csv(linhas: list[dict], colunas: list[str]) -> bytes:
    """CSV para o Excel em pt-BR: UTF-8 com BOM, separador ';' e vírgula decimal."""
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(colunas)
    for linha in linhas:
        escritor.writerow([_numero_br(linha.get(c)) for c in colunas])
    return ("﻿" + saida.getvalue()).encode("utf-8")
