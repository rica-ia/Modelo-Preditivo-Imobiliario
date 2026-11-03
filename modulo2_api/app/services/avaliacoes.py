"""
# Serviço de avaliações (laudos)

Grava cada avaliação com a predição recalculada no servidor (o cliente nunca
informa o preço), lista com filtros e paginação, exporta em CSV/JSON e monta o
laudo HTML com comparáveis reais e referências de mercado do mesmo CEP e cidade.
"""

import csv
import io
import json
import statistics
from datetime import datetime
from html import escape

from ..schemas.imovel import ImovelEntrada
from .banco import Banco, agora
from .carga import classificar, mapa_de_cidades, rotulos_de_faixa
from .comercial import ServicoComercial
from .excecoes import NaoEncontradoError, RegraDeNegocioError
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
    def _referencias(self, cep: str, cidade: str) -> dict:
        por_cep = [r["preco_m2_usd"] for r in self.banco.consultar(
            "SELECT preco_m2_usd FROM vendas_historicas WHERE cep = ?", (cep,))]
        por_cidade = [r["preco_m2_usd"] for r in self.banco.consultar(
            "SELECT preco_m2_usd FROM vendas_historicas WHERE cidade = ?", (cidade,))]
        return {
            "cep": statistics.median(por_cep) if por_cep else None,
            "cidade": statistics.median(por_cidade) if por_cidade else None,
            "vendas_cep": len(por_cep),
            "vendas_cidade": len(por_cidade),
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

    def laudo_html(self, avaliacao_id: int) -> str:
        a = self.obter(avaliacao_id)
        imovel = a["imovel"]
        ref = self._referencias(a["cep"], a["cidade"])
        comparaveis = self.comparaveis(a)
        metricas = self.servico.metricas.get("metricas", {}).get("teste", {})
        return montar_laudo(a, imovel, ref, comparaveis, metricas, self.servico.metricas.get("algoritmo", ""))


def exportar_csv(linhas: list[dict], colunas: list[str]) -> bytes:
    """CSV para o Excel em pt-BR: UTF-8 com BOM, separador ';' e vírgula decimal."""
    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";", lineterminator="\r\n")
    escritor.writerow(colunas)
    for linha in linhas:
        escritor.writerow([_numero_br(linha.get(c)) for c in colunas])
    return ("﻿" + saida.getvalue()).encode("utf-8")


def _usd(valor) -> str:
    return "—" if valor is None else "US$ " + f"{valor:,.0f}".replace(",", ".")


def montar_laudo(a: dict, imovel: dict, ref: dict, comparaveis: list[dict], metricas: dict, algoritmo: str) -> str:
    e = escape
    sim = lambda v: "Sim" if v else "Não"  # noqa: E731

    def comparar(referencia):
        if not referencia:
            return "—"
        delta = a["preco_m2_usd"] / referencia - 1
        lado = "acima" if delta >= 0 else "abaixo"
        percentual = f"{abs(delta):.1%}".replace(".", ",")
        return f"{_usd(referencia)} · este imóvel está {percentual} {lado}"

    linhas_comp = "".join(
        f"<tr><td>{e(c['data_venda'])}</td><td>{_usd(c['preco_usd'])}</td><td>{c['quartos']}</td>"
        f"<td>{c['banheiros']:g}</td><td>{c['area_util_m2']:.0f} m²</td><td>{c['padrao']}</td>"
        f"<td>{c['ano_construcao']}</td><td>{_usd(c['preco_m2_usd'])}</td></tr>"
        for c in comparaveis
    ) or '<tr><td colspan="8">Sem vendas registradas neste CEP.</td></tr>'
    preco_real = (
        f"<div class='kpi'><span>Preço real de venda</span><b>{_usd(a['preco_real_usd'])}</b>"
        f"<small>erro do modelo: {(a['preco_estimado_usd'] / a['preco_real_usd'] - 1):+.1%}</small></div>"
        if a.get("preco_real_usd") else ""
    )
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Laudo de avaliação nº {a['id']} · Avaliador Imobiliário</title>
<style>
  :root {{ --tinta:#1d1d1f; --suave:#6e6e73; --linha:#e5e5ea; --marca:#7c5cff; }}
  * {{ box-sizing:border-box }}
  body {{ margin:0; font-family:-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; color:var(--tinta); background:#f5f5f7 }}
  .folha {{ max-width:820px; margin:24px auto; background:#fff; border-radius:18px; padding:40px; box-shadow:0 2px 16px rgba(0,0,0,.06) }}
  header {{ display:flex; align-items:center; gap:14px; border-bottom:1px solid var(--linha); padding-bottom:18px }}
  header img {{ width:44px; height:44px }}
  header h1 {{ font-size:20px; margin:0 }}
  header p {{ margin:2px 0 0; color:var(--suave); font-size:13px }}
  h2 {{ font-size:15px; text-transform:uppercase; letter-spacing:.06em; color:var(--suave); margin:28px 0 10px }}
  .titulo {{ font-size:24px; margin:22px 0 4px }}
  .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px }}
  .kpi {{ border:1px solid var(--linha); border-radius:14px; padding:14px }}
  .kpi span {{ display:block; color:var(--suave); font-size:12px }}
  .kpi b {{ display:block; font-size:22px; margin-top:4px }}
  .kpi small {{ color:var(--suave) }}
  .destaque b {{ color:var(--marca); font-size:28px }}
  table {{ width:100%; border-collapse:collapse; font-size:13px }}
  th, td {{ text-align:left; padding:8px 6px; border-bottom:1px solid var(--linha) }}
  th {{ color:var(--suave); font-weight:600 }}
  dl {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:6px 18px; margin:0; font-size:14px }}
  dt {{ color:var(--suave) }} dd {{ margin:0 0 6px; font-weight:600 }}
  .aviso {{ background:#fff4e5; color:#8a4b00; border-radius:12px; padding:14px; font-size:13px; line-height:1.5 }}
  .acoes {{ text-align:right; margin-bottom:12px }}
  .acoes button {{ background:var(--marca); color:#fff; border:0; border-radius:999px; padding:10px 18px; font-size:14px; cursor:pointer }}
  @media print {{
    body {{ background:#fff }} .folha {{ box-shadow:none; margin:0; max-width:none; border-radius:0; padding:0 }}
    .acoes {{ display:none }} h2 {{ break-after:avoid }} table, .kpis {{ break-inside:avoid }}
    @page {{ size:A4; margin:16mm }}
  }}
</style></head>
<body><div class="folha">
  <div class="acoes"><button onclick="window.print()">Imprimir ou salvar em PDF</button></div>
  <header><img src="/assets/logo.svg" alt="">
    <div><h1>Avaliador Imobiliário</h1><p>Laudo de avaliação nº {a['id']} · emitido em {e(a['criado_em'][:16].replace('T', ' '))}</p></div>
  </header>
  <p class="titulo">{e(a['titulo'])}</p>
  <p style="color:var(--suave);margin:0">Responsável: {e(a.get('responsavel') or '—')} · Origem: {e(a['origem'])} · {e(a['cidade'])}, CEP {e(a['cep'])}</p>

  <h2>Valor estimado</h2>
  <div class="kpis">
    <div class="kpi destaque"><span>Preço estimado</span><b>{_usd(a['preco_estimado_usd'])}</b><small>{e(a['faixa_preco'])}</small></div>
    <div class="kpi"><span>Faixa provável (80 %)</span><b>{_usd(a['faixa_min'])}</b><small>até {_usd(a['faixa_max'])}</small></div>
    <div class="kpi"><span>Preço por m²</span><b>{_usd(a['preco_m2_usd'])}</b><small>área útil de {a['area_util_m2']:.0f} m²</small></div>
    {preco_real}
  </div>

  <h2>Referência de mercado (vendas reais)</h2>
  <dl>
    <dt>Mediana do US$/m² no CEP {e(a['cep'])} ({ref['vendas_cep']} vendas)</dt><dd>{comparar(ref['cep'])}</dd>
    <dt>Mediana do US$/m² em {e(a['cidade'])} ({ref['vendas_cidade']} vendas)</dt><dd>{comparar(ref['cidade'])}</dd>
  </dl>

  <h2>Dados do imóvel</h2>
  <dl>
    <dt>Quartos</dt><dd>{imovel['quartos']}</dd>
    <dt>Banheiros</dt><dd>{imovel['banheiros']:g}</dd>
    <dt>Área útil</dt><dd>{imovel['area_util_m2']:.0f} m²</dd>
    <dt>Terreno</dt><dd>{imovel['area_terreno_m2']:.0f} m²</dd>
    <dt>Andares</dt><dd>{imovel['andares']:g}</dd>
    <dt>Porão</dt><dd>{imovel.get('area_porao_m2') or 0:.0f} m²</dd>
    <dt>Padrão construtivo</dt><dd>{imovel['padrao_construtivo']} de 13</dd>
    <dt>Conservação</dt><dd>{imovel['condicao']} de 5</dd>
    <dt>Vista</dt><dd>{imovel['vista']} de 4</dd>
    <dt>Frente para a água</dt><dd>{sim(imovel['frente_agua'])}</dd>
    <dt>Ano de construção</dt><dd>{imovel['ano_construcao']}</dd>
    <dt>Reforma</dt><dd>{imovel.get('ano_reforma') or 'Nunca reformado'}</dd>
    <dt>Localização</dt><dd>{imovel['latitude']:.4f}, {imovel['longitude']:.4f}</dd>
  </dl>

  <h2>Comparáveis: 5 vendas mais parecidas no mesmo CEP</h2>
  <table><thead><tr><th>Data</th><th>Preço</th><th>Quartos</th><th>Banheiros</th><th>Área</th><th>Padrão</th><th>Ano</th><th>US$/m²</th></tr></thead>
  <tbody>{linhas_comp}</tbody></table>

  <h2>Modelo</h2>
  <dl>
    <dt>Algoritmo</dt><dd>{e(algoritmo)} · versão {e(a['versao_modelo'])}</dd>
    <dt>Desempenho no conjunto de teste</dt><dd>R² {metricas.get('R2', 0):.3f} · MAE {_usd(metricas.get('MAE'))} · MAPE {metricas.get('MAPE', 0):.1%}</dd>
  </dl>

  <h2>Aviso de uso</h2>
  <p class="aviso">Estimativa estatística gerada por modelo de machine learning treinado com vendas de King County (WA)
  entre mai/2014 e mai/2015, em dólares. Não substitui laudo técnico de avaliação assinado por profissional habilitado
  (NBR 14653) nem vistoria do imóvel. A faixa provável cobre cerca de 80 % dos erros observados na validação.</p>
</div></body></html>"""
