"""
# Laudo de avaliação mercadológica (HTML pronto para imprimir ou salvar em PDF)

Monta o documento no padrão de um laudo comercial, em oito seções:

1. Identificação: número do laudo, data de emissão, solicitante, finalidade e endereço completo
   (geocodificação reversa do OpenStreetMap, quando disponível).
2. Sumário executivo: valor estimado, faixa provável, US$/m², posição no CEP e conveniência.
3. Características do imóvel.
4. Análise de mercado do CEP e da cidade, com a régua do US$/m² e as vendas comparáveis.
5. Localização e comodidades (Overpass/OpenStreetMap): quantidade, distância e tempos.
6. Metodologia e desempenho do modelo, lidos do arquivo de métricas do treino.
7. Limitações e aviso legal.
8. Responsabilidade e rodapé.

Tudo é escapado antes de entrar no HTML (nomes de lugares vêm de base colaborativa).
"""

from datetime import datetime
from html import escape as e

ORIGENS = {"portal": "Portal web", "api": "API (integração)", "amostra_base": "Amostra da base histórica"}
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]


# ## Formatação em pt-BR
def _usd(valor) -> str:
    return "—" if valor is None else "US$ " + f"{valor:,.0f}".replace(",", ".")


def _num(valor, casas: int = 0) -> str:
    if valor is None:
        return "—"
    return f"{valor:,.{casas}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _num_curto(valor) -> str:
    """Número sem zeros à direita, com vírgula decimal (2,25 banheiros; 2 andares)."""
    return f"{valor:g}".replace(".", ",")


def _pct(valor, casas: int = 1, sinal: bool = False) -> str:
    if valor is None:
        return "—"
    texto = f"{abs(valor) * 100:.{casas}f}".replace(".", ",") + " %"
    if sinal:
        texto = ("+" if valor >= 0 else "−") + texto
    return texto


def _data_hora(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        d = datetime.fromisoformat(iso)
    except ValueError:
        return e(iso)
    if d.tzinfo is not None:
        d = d.astimezone()  # horário local da máquina que emite o laudo
    return d.strftime("%d/%m/%Y às %Hh%M")


def _data(texto: str | None) -> str:
    """Datas do dataset (2014-10-13 ou 20141013T000000) em dd/mm/aaaa."""
    if not texto:
        return "—"
    limpo = texto.replace("-", "")[:8]
    if len(limpo) == 8 and limpo.isdigit():
        return f"{limpo[6:8]}/{limpo[4:6]}/{limpo[:4]}"
    return e(texto)


def numero_laudo(avaliacao: dict) -> str:
    ano = (avaliacao.get("criado_em") or "")[:4] or str(datetime.now().year)
    return f"AV-{ano}-{avaliacao['id']:06d}"


# ## Blocos do documento
def _linhas_dl(pares: list[tuple[str, str]]) -> str:
    return "".join(f"<div><dt>{e(rotulo)}</dt><dd>{valor}</dd></div>" for rotulo, valor in pares)


def _regua(ref: dict, preco_m2: float) -> str:
    """Régua do US$/m² das vendas do CEP (P10 a P90), com a mediana e o imóvel avaliado."""
    p10, p90 = ref.get("m2_p10"), ref.get("m2_p90")
    if not p10 or not p90 or p90 <= p10:
        return ""

    def posicao(valor: float) -> float:
        return max(0.0, min(100.0, (valor - p10) / (p90 - p10) * 100))

    return f"""
  <div class="regua" role="img" aria-label="Posição do US$/m² do imóvel entre as vendas do CEP">
    <div class="regua-barra">
      <span class="regua-quartis" style="left:{posicao(ref['m2_p25']):.1f}%;width:{posicao(ref['m2_p75']) - posicao(ref['m2_p25']):.1f}%"></span>
      <span class="regua-mediana" style="left:{posicao(ref['cep']):.1f}%"></span>
      <span class="regua-imovel" style="left:{posicao(preco_m2):.1f}%"></span>
    </div>
    <div class="regua-escala"><span>P10 · {_usd(p10)}/m²</span><span>P90 · {_usd(p90)}/m²</span></div>
    <p class="legenda"><i class="lg lg-quartis"></i>metade central das vendas (P25 a P75)
      <i class="lg lg-mediana"></i>mediana do CEP <i class="lg lg-imovel"></i>imóvel avaliado</p>
  </div>"""


def _secao_comodidades(comodidades: dict | None, lat: float, lng: float) -> str:
    mapa = (f"https://www.openstreetmap.org/?mlat={lat:.5f}&amp;mlon={lng:.5f}#map=16/{lat:.5f}/{lng:.5f}")
    if not comodidades or not comodidades.get("disponivel"):
        return f"""
  <p class="nota">A consulta de comodidades ao OpenStreetMap não respondeu no momento da emissão. Reemita o laudo
  mais tarde para incluir escolas, saúde, mercados, transporte, parques, restaurantes e bancos do entorno.
  Localização: <a href="{mapa}">{lat:.5f}, {lng:.5f}</a>.</p>"""

    indice = comodidades.get("indice_conveniencia") or {}
    linhas = []
    for categoria in comodidades["categorias"]:
        if categoria["mais_proximos"]:
            itens = "".join(
                f"<li><b>{e(i['nome'])}</b> <span class='tipo'>{e(i['tipo'])}</span>"
                f"<span class='medidas'>{_num(i['distancia_m'])} m · {i['a_pe_min']} min a pé · "
                f"{i['carro_min']} min de carro</span></li>"
                for i in categoria["mais_proximos"]
            )
            proximos = f"<ul class='proximos'>{itens}</ul>"
        else:
            proximos = "<span class='tipo'>Nenhum registro no raio pesquisado.</span>"
        linhas.append(f"<tr><th scope='row'>{e(categoria['nome'])}</th>"
                      f"<td class='num'>{categoria['quantidade']}</td><td>{proximos}</td></tr>")
    raio = _num(comodidades["raio_m"] / 1000, 1).replace(",0", "")
    return f"""
  <div class="indice">
    <div class="indice-valor"><b>{indice.get('valor', '—')}</b><span>de 100</span></div>
    <div><p class="indice-titulo">Índice de conveniência: {e(indice.get('classificacao', '—'))}</p>
      <p class="nota">{e(indice.get('explicacao', ''))}</p></div>
  </div>
  <div class="tabela"><table class="comodidades">
    <thead><tr><th>Categoria</th><th class="num">No raio de {raio} km</th><th>Mais próximos (distância em linha reta e tempos estimados)</th></tr></thead>
    <tbody>{''.join(linhas)}</tbody>
  </table></div>
  <p class="nota">{e(comodidades.get('metodo', ''))} Consulta em {_data_hora(comodidades.get('consultado_em'))}.
  <a href="{mapa}">Ver a localização no OpenStreetMap</a>.</p>
  <p class="credito">Dados de comodidades: {e(comodidades.get('fonte', '© OpenStreetMap contributors'))}.
  Base colaborativa: pode haver lugares ausentes ou desatualizados.</p>"""


CSS = """
  :root { --tinta:#1b2433; --suave:#5b6474; --linha:#d9dee7; --fundo:#eef1f5; --marca:#1f3a5f; --realce:#b8862b;
          --claro:#f6f8fb; }
  * { box-sizing:border-box }
  html { -webkit-print-color-adjust:exact; print-color-adjust:exact }
  body { margin:0; font-family:"Segoe UI",-apple-system,Roboto,Helvetica,Arial,sans-serif; color:var(--tinta);
         background:var(--fundo); font-size:13.5px; line-height:1.5 }
  a { color:var(--marca) }
  .acoes { max-width:860px; margin:20px auto 0; display:flex; justify-content:flex-end; gap:8px; padding:0 16px }
  .acoes button { background:var(--marca); color:#fff; border:0; border-radius:6px; padding:9px 16px; font-size:13px; cursor:pointer }
  .folha { max-width:860px; margin:12px auto 32px; background:#fff; padding:44px 48px; border-top:6px solid var(--marca);
           box-shadow:0 1px 10px rgba(20,30,50,.08) }
  .capa { display:flex; justify-content:space-between; align-items:flex-start; gap:24px; padding-bottom:18px;
          border-bottom:2px solid var(--marca) }
  .marca { display:flex; align-items:center; gap:12px }
  .marca img { width:46px; height:46px }
  .marca b { display:block; font-size:17px; letter-spacing:.02em }
  .marca span { color:var(--suave); font-size:12px }
  .numero { text-align:right; font-size:12px; color:var(--suave) }
  .numero b { display:block; color:var(--tinta); font-size:16px; letter-spacing:.04em }
  h1 { font-family:Georgia,"Times New Roman",serif; font-weight:normal; font-size:26px; margin:22px 0 2px; color:var(--marca) }
  .subtitulo { margin:0 0 4px; font-size:15px }
  .endereco { margin:0; color:var(--suave) }
  h2 { font-size:13px; text-transform:uppercase; letter-spacing:.08em; color:var(--marca); margin:30px 0 12px;
       padding-bottom:6px; border-bottom:1px solid var(--linha) }
  h2 span { color:var(--realce); margin-right:8px }
  dl { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:0 28px; margin:0 }
  dl div { display:flex; justify-content:space-between; gap:12px; padding:6px 0; border-bottom:1px dotted var(--linha) }
  dt { color:var(--suave) } dd { margin:0; font-weight:600; text-align:right }
  dl.largo { grid-template-columns:1fr }
  .kpis { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; margin-bottom:14px }
  .kpi { background:var(--claro); border:1px solid var(--linha); border-radius:6px; padding:12px }
  .kpi span { display:block; color:var(--suave); font-size:11.5px; text-transform:uppercase; letter-spacing:.04em }
  .kpi b { display:block; font-size:19px; margin-top:4px }
  .kpi small { color:var(--suave) }
  .kpi.destaque { background:var(--marca); border-color:var(--marca); color:#fff }
  .kpi.destaque span, .kpi.destaque small { color:#d6deea }
  .kpi.destaque b { font-size:23px }
  .conclusao { background:var(--claro); border-left:4px solid var(--realce); padding:12px 16px; margin:0 }
  table { width:100%; border-collapse:collapse; font-size:12.5px }
  th, td { text-align:left; padding:7px 8px; border-bottom:1px solid var(--linha); vertical-align:top }
  thead th { background:var(--claro); color:var(--suave); font-weight:600; font-size:11.5px; text-transform:uppercase;
             letter-spacing:.03em }
  tbody th { font-weight:600 }
  .num { text-align:right; white-space:nowrap }
  .tabela { overflow-x:auto }
  .regua { margin:16px 0 4px }
  .regua-barra { position:relative; height:14px; background:#e6eaf0; border-radius:7px }
  .regua-quartis { position:absolute; top:0; bottom:0; background:#b9c7da; border-radius:7px }
  .regua-mediana { position:absolute; top:-4px; width:2px; height:22px; background:var(--marca) }
  .regua-imovel { position:absolute; top:-5px; width:14px; height:24px; margin-left:-7px; background:var(--realce);
                  border:2px solid #fff; border-radius:4px; box-shadow:0 0 0 1px var(--realce) }
  .regua-escala { display:flex; justify-content:space-between; color:var(--suave); font-size:11.5px; margin-top:6px }
  .legenda { color:var(--suave); font-size:11.5px; margin:4px 0 0 }
  .lg { display:inline-block; width:10px; height:10px; border-radius:2px; margin:0 4px 0 12px; vertical-align:-1px }
  .lg:first-child { margin-left:0 }
  .lg-quartis { background:#b9c7da } .lg-mediana { background:var(--marca) } .lg-imovel { background:var(--realce) }
  .indice { display:flex; gap:18px; align-items:center; margin-bottom:12px }
  .indice-valor { min-width:96px; text-align:center; border:2px solid var(--marca); border-radius:8px; padding:8px }
  .indice-valor b { display:block; font-size:30px; color:var(--marca); line-height:1.1 }
  .indice-valor span { color:var(--suave); font-size:11px }
  .indice-titulo { margin:0; font-weight:600; font-size:14px }
  .proximos { margin:0; padding:0; list-style:none }
  .proximos li { padding:1px 0 }
  .tipo { color:var(--suave); font-size:11.5px; margin-left:4px }
  .medidas { display:block; color:var(--suave); font-size:11.5px }
  .nota { color:var(--suave); font-size:12px; margin:8px 0 0 }
  .credito { color:var(--suave); font-size:11px; margin:4px 0 0 }
  ul.limites { margin:0; padding-left:18px } ul.limites li { margin:3px 0 }
  .aviso { background:#fbf6ea; border:1px solid #ecdcb5; border-radius:6px; padding:12px 16px; margin-top:12px; font-size:12.5px }
  .assinatura { display:grid; grid-template-columns:1fr 1fr; gap:40px; margin-top:34px }
  .assinatura div { border-top:1px solid var(--tinta); padding-top:6px; font-size:12px; color:var(--suave) }
  .assinatura b { display:block; color:var(--tinta) }
  footer { margin-top:30px; padding-top:10px; border-top:1px solid var(--linha); display:flex; justify-content:space-between;
           color:var(--suave); font-size:11px }
  section { break-inside:auto }
  @media (max-width:700px) {
    .folha { padding:24px 18px } .capa { flex-direction:column } .numero { text-align:left }
    dl { grid-template-columns:1fr } .kpis { grid-template-columns:1fr 1fr } .assinatura { grid-template-columns:1fr }
  }
  @media print {
    body { background:#fff; font-size:11.5px } .acoes { display:none }
    .folha { box-shadow:none; margin:0; max-width:none; padding:0; border-top:0 }
    h2 { break-after:avoid } tr, .kpis, .indice, .regua, .assinatura, dl div { break-inside:avoid }
    .kpis { grid-template-columns:repeat(4,minmax(0,1fr)) } dl { grid-template-columns:repeat(2,minmax(0,1fr)) }
    a { color:inherit; text-decoration:none }
    @page { size:A4; margin:15mm 14mm 16mm; @bottom-right { content:"Página " counter(page) " de " counter(pages);
            font-size:9pt; color:#5b6474 } }
  }
"""


def montar_laudo(a: dict, imovel: dict, ref: dict, comparaveis: list[dict], info_modelo: dict,
                 endereco: dict | None = None, comodidades: dict | None = None) -> str:
    sim = lambda v: "Sim" if v else "Não"  # noqa: E731
    numero = numero_laudo(a)
    emissao = _data_hora(a.get("criado_em"))
    lat, lng = imovel["latitude"], imovel["longitude"]
    if endereco and endereco.get("disponivel") and endereco.get("endereco"):
        endereco_txt = e(endereco["endereco"])
        fonte_endereco = f"Endereço por geocodificação reversa ({e(endereco.get('fonte', 'OpenStreetMap'))})."
    else:
        endereco_txt = f"{e(a['cidade'])}, WA {e(a['cep'])}"
        fonte_endereco = "Logradouro não identificado pelo geocodificador; localização pelas coordenadas."

    # Posição no mercado do CEP
    preco_m2 = a["preco_m2_usd"]
    delta_cep = preco_m2 / ref["cep"] - 1 if ref.get("cep") else None
    delta_cidade = preco_m2 / ref["cidade"] - 1 if ref.get("cidade") else None
    percentil = ref.get("percentil_m2")
    if delta_cep is None:
        posicao_txt = "Sem vendas registradas no CEP para comparação."
    else:
        lado = "acima" if delta_cep >= 0 else "abaixo"
        posicao_txt = f"{_pct(abs(delta_cep))} {lado} da mediana do CEP"
        if percentil is not None:
            posicao_txt += f"; supera {_pct(percentil, 0)} das vendas do CEP em US$/m²"

    # Conveniência
    indice = (comodidades or {}).get("indice_conveniencia") if (comodidades or {}).get("disponivel") else None
    kpi_conveniencia = (
        f"<div class='kpi'><span>Conveniência do entorno</span><b>{indice['valor']} / 100</b>"
        f"<small>{e(indice['classificacao'])}</small></div>"
        if indice else
        f"<div class='kpi'><span>Posição no CEP</span><b>{_pct(delta_cep, 1, True) if delta_cep is not None else '—'}</b>"
        f"<small>US$/m² frente à mediana</small></div>"
    )

    # Sumário executivo em texto
    total_vendas = sum((info_modelo.get("divisao") or {}).get(k, 0) for k in ("treino", "validacao", "teste"))
    frase_mercado = (
        f" O US$/m² estimado fica {_pct(abs(delta_cep))} {'acima' if delta_cep >= 0 else 'abaixo'} da mediana das"
        f" {ref['vendas_cep']} vendas do CEP {e(a['cep'])}." if delta_cep is not None else ""
    )
    frase_entorno = (
        f" O entorno tem índice de conveniência {indice['valor']}/100 ({e(indice['classificacao']).lower()})"
        f" num raio de 1,5 km." if indice else ""
    )
    conclusao = (
        f"Com base em {_num(total_vendas)} vendas reais de King County, o imóvel de {_num(imovel['area_util_m2'])} m²"
        f" de área útil, {imovel['quartos']} quartos e padrão construtivo"
        f" {imovel['padrao_construtivo']}/13 tem valor de mercado estimado em <b>{_usd(a['preco_estimado_usd'])}</b>,"
        f" com faixa provável de {_usd(a['faixa_min'])} a {_usd(a['faixa_max'])}.{frase_mercado}{frase_entorno}"
    )

    # Comparáveis
    linhas_comp = "".join(
        f"<tr><td>{_data(c['data_venda'])}</td><td class='num'>{_usd(c['preco_usd'])}</td><td class='num'>{c['quartos']}</td>"
        f"<td class='num'>{_num_curto(c['banheiros'])}</td><td class='num'>{_num(c['area_util_m2'])} m²</td>"
        f"<td class='num'>{c['padrao']}</td><td class='num'>{c['ano_construcao']}</td>"
        f"<td class='num'>{_usd(c['preco_m2_usd'])}</td>"
        f"<td class='num'>{_pct(c['preco_m2_usd'] / preco_m2 - 1, 0, True) if preco_m2 else '—'}</td></tr>"
        for c in comparaveis
    ) or '<tr><td colspan="9">Sem vendas registradas neste CEP.</td></tr>'

    preco_real = (
        f"<div><dt>Preço real de venda (registro histórico)</dt><dd>{_usd(a['preco_real_usd'])} · desvio do modelo"
        f" {_pct(a['preco_estimado_usd'] / a['preco_real_usd'] - 1, 1, True)}</dd></div>"
        if a.get("preco_real_usd") else ""
    )

    # Modelo (somente números do arquivo de métricas do treino)
    teste = info_modelo.get("metricas", {}).get("teste", {})
    base = info_modelo.get("baseline", {}).get("teste", {})
    divisao = info_modelo.get("divisao", {})
    faixa = info_modelo.get("faixa_erro", {})
    ganho_mae = (1 - teste["MAE"] / base["MAE"]) if teste.get("MAE") and base.get("MAE") else None
    importantes = ", ".join(e(i["variavel"]) for i in (info_modelo.get("importancia") or [])[:5]) or "—"
    metricas_dl = _linhas_dl([
        ("Algoritmo", f"{e(info_modelo.get('algoritmo', '—'))} · versão {e(a['versao_modelo'])}"),
        ("Treinado em", _data_hora(info_modelo.get("treinado_em"))),
        ("Amostras (treino · validação · teste)",
         f"{_num(divisao.get('treino'))} · {_num(divisao.get('validacao'))} · {_num(divisao.get('teste'))}"),
        ("Critério da divisão", e(divisao.get("criterio", "—"))),
        ("R² no teste", _num(teste.get("R2"), 3)),
        ("MAE no teste (erro absoluto médio)", _usd(teste.get("MAE"))),
        ("RMSE no teste", _usd(teste.get("RMSE"))),
        ("MAPE no teste (erro percentual médio)", _pct(teste.get("MAPE"))),
        ("MAE do modelo de referência (média)", f"{_usd(base.get('MAE'))}"
         + (f" · redução de {_pct(ganho_mae, 0)}" if ganho_mae is not None else "")),
        ("Faixa provável (validação)",
         f"80 % entre {_pct(faixa['p10'] - 1, 1, True)} e {_pct(faixa['p90'] - 1, 1, True)}" if faixa.get("p10") else "—"),
    ])
    data_base = _data(info_modelo.get("data_referencia"))
    fim_periodo = (f"{MESES[int(data_base[3:5]) - 1]}/{data_base[6:]}" if data_base[3:5].isdigit() else "mai/2015")

    identificacao = _linhas_dl([
        ("Solicitante / responsável", e(a.get("responsavel") or "—")),
        ("Finalidade", "Estimativa do valor de mercado para compra e venda"),
        ("Objeto", "Imóvel residencial urbano"),
        ("Cidade e CEP", f"{e(a['cidade'])}, WA · CEP {e(a['cep'])}"),
        ("Coordenadas", f"{lat:.5f}, {lng:.5f}"),
        ("Origem do pedido", ORIGENS.get(a["origem"], e(a["origem"]))),
        ("Data-base dos dados de mercado", f"vendas até {data_base}"),
        ("Moeda", "Dólar americano (US$)"),
    ])
    caracteristicas = _linhas_dl([
        ("Área útil", f"{_num(imovel['area_util_m2'])} m²"),
        ("Área do terreno", f"{_num(imovel['area_terreno_m2'])} m²"),
        ("Área de porão", f"{_num(imovel.get('area_porao_m2') or 0)} m²"),
        ("Quartos", str(imovel["quartos"])),
        ("Banheiros", _num_curto(imovel["banheiros"])),
        ("Andares", _num_curto(imovel["andares"])),
        ("Padrão construtivo", f"{imovel['padrao_construtivo']} de 13"),
        ("Estado de conservação", f"{imovel['condicao']} de 5"),
        ("Qualidade da vista", f"{imovel['vista']} de 4"),
        ("Frente para a água", sim(imovel["frente_agua"])),
        ("Ano de construção", str(imovel["ano_construcao"])),
        ("Última reforma", str(imovel.get("ano_reforma") or "Sem registro de reforma")),
    ])
    mercado = f"""
  <div class="tabela"><table>
    <thead><tr><th>Indicador</th><th class="num">CEP {e(a['cep'])}</th><th class="num">{e(a['cidade'])}</th><th class="num">Imóvel avaliado</th></tr></thead>
    <tbody>
      <tr><th scope="row">Vendas registradas</th><td class="num">{_num(ref['vendas_cep'])}</td><td class="num">{_num(ref['vendas_cidade'])}</td><td class="num">—</td></tr>
      <tr><th scope="row">Preço mediano</th><td class="num">{_usd(ref.get('preco_mediano_cep'))}</td><td class="num">{_usd(ref.get('preco_mediano_cidade'))}</td><td class="num">{_usd(a['preco_estimado_usd'])}</td></tr>
      <tr><th scope="row">US$/m² mediano</th><td class="num">{_usd(ref.get('cep'))}</td><td class="num">{_usd(ref.get('cidade'))}</td><td class="num">{_usd(preco_m2)}</td></tr>
      <tr><th scope="row">US$/m² · metade central (P25 a P75)</th><td class="num">{_usd(ref.get('m2_p25'))} a {_usd(ref.get('m2_p75'))}</td><td class="num">—</td><td class="num">—</td></tr>
      <tr><th scope="row">Diferença do US$/m² do imóvel</th><td class="num">{_pct(delta_cep, 1, True)}</td><td class="num">{_pct(delta_cidade, 1, True)}</td><td class="num">—</td></tr>
    </tbody>
  </table></div>
  {_regua(ref, preco_m2)}
  <p class="nota">Posição do imóvel: {posicao_txt}.</p>"""

    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Laudo de avaliação nº {numero} · Avaliador Imobiliário</title>
<style>{CSS}</style></head>
<body>
<div class="acoes"><button type="button" onclick="window.print()">Imprimir ou salvar em PDF</button></div>
<main class="folha">
  <header class="capa">
    <div class="marca"><img src="/assets/logo.svg" alt=""><div><b>Avaliador Imobiliário</b><span>Avaliação mercadológica por dados de mercado</span></div></div>
    <div class="numero">Laudo nº<b>{numero}</b>Emitido em {emissao}</div>
  </header>
  <h1>Laudo de Avaliação Mercadológica</h1>
  <p class="subtitulo">{e(a['titulo'])}</p>
  <p class="endereco">{endereco_txt}</p>

  <section><h2><span>1</span>Identificação</h2>
  <dl>{identificacao}</dl>
  <p class="nota">{fonte_endereco}</p></section>

  <section><h2><span>2</span>Sumário executivo</h2>
  <div class="kpis">
    <div class="kpi destaque"><span>Valor de mercado estimado</span><b>{_usd(a['preco_estimado_usd'])}</b><small>{e(a.get('faixa_preco') or '')}</small></div>
    <div class="kpi"><span>Faixa provável (80 %)</span><b>{_usd(a['faixa_min'])}</b><small>a {_usd(a['faixa_max'])}</small></div>
    <div class="kpi"><span>Valor por m²</span><b>{_usd(preco_m2)}</b><small>sobre {_num(a['area_util_m2'])} m² úteis</small></div>
    {kpi_conveniencia}
  </div>
  <p class="conclusao">{conclusao}</p></section>

  <section><h2><span>3</span>Características do imóvel</h2>
  <dl>{caracteristicas}</dl></section>

  <section><h2><span>4</span>Análise de mercado</h2>
  {mercado}
  <h3 style="font-size:13px;margin:20px 0 8px">Comparáveis: 5 vendas mais parecidas no mesmo CEP</h3>
  <div class="tabela"><table><thead><tr><th>Data da venda</th><th class="num">Preço</th><th class="num">Quartos</th><th class="num">Banheiros</th><th class="num">Área útil</th><th class="num">Padrão</th><th class="num">Ano</th><th class="num">US$/m²</th><th class="num">Δ US$/m²</th></tr></thead>
  <tbody>{linhas_comp}</tbody></table></div>
  <p class="nota">Semelhança por área útil, quartos, banheiros, padrão construtivo e ano de construção. Δ US$/m²: diferença do comparável frente ao valor por m² estimado.</p>
  {f'<dl class="largo">{preco_real}</dl>' if preco_real else ''}</section>

  <section><h2><span>5</span>Localização e comodidades</h2>
  {_secao_comodidades(comodidades, lat, lng)}</section>

  <section><h2><span>6</span>Metodologia e desempenho do modelo</h2>
  <p style="margin:0 0 10px">Método comparativo direto de dados de mercado, com tratamento por inferência estatística:
  um modelo de aprendizado de máquina treinado com as vendas reais de King County (WA) estima o preço a partir das
  características e da localização do imóvel. O valor é recalculado no servidor a cada avaliação.</p>
  <dl>{metricas_dl}</dl>
  <p class="nota">Variáveis de maior influência no modelo: {importantes}.</p></section>

  <section><h2><span>7</span>Limitações e aviso legal</h2>
  <ul class="limites">
    <li>Os dados de mercado são vendas de King County (WA) de mai/2014 a {fim_periodo}, em dólares, sem correção monetária até a data de emissão.</li>
    <li>O imóvel não foi vistoriado: as características são as informadas pelo solicitante e não foram conferidas em campo nem em matrícula.</li>
    <li>A faixa provável reflete o erro observado na validação do modelo (80 % dos casos); valores fora dela são possíveis.</li>
    <li>As comodidades vêm do OpenStreetMap, base colaborativa; distâncias são em linha reta e os tempos, estimativas sem trânsito.</li>
  </ul>
  <p class="aviso"><b>Aviso legal.</b> Este documento é uma estimativa estatística de valor de mercado, de caráter
  informativo. Não substitui laudo técnico de avaliação elaborado e assinado por profissional habilitado, conforme a
  ABNT NBR 14653, nem a vistoria do imóvel, e não deve ser usado isoladamente como garantia em operações de crédito
  ou em processos judiciais.</p></section>

  <section><h2><span>8</span>Responsabilidade</h2>
  <div class="assinatura">
    <div><b>{e(a.get('responsavel') or 'Responsável pela emissão')}</b>Responsável pela emissão</div>
    <div><b>Avaliador Imobiliário</b>Laudo nº {numero} · {emissao}</div>
  </div></section>

  <footer><span>Avaliador Imobiliário · Laudo nº {numero}</span><span>Mapas e comodidades © OpenStreetMap contributors</span></footer>
</main></body></html>"""
