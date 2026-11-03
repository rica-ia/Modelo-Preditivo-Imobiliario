/* Avaliador Imobiliário — lógica do portal (SPA por hash, sem framework).
   Toda chamada é same-origin para a própria API FastAPI.
   Um único objeto de estado (imóvel atual e CEP selecionado) é lido por todos os módulos. */
(function () {
  "use strict";

  // ---------------------------------------------------------------- utilidades
  const $ = (sel, raiz = document) => raiz.querySelector(sel);
  const $$ = (sel, raiz = document) => Array.from(raiz.querySelectorAll(sel));
  const usd = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  const num = (v, d = 0) => (Math.abs(Number(v)) < 0.5 * 10 ** -d ? 0 : Number(v)).toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d });
  const pct = (v, d = 1) => num(v * 100, d) + " %";
  const sinal = (v, d = 1) => `${v >= 0 ? "+" : "−"}${num(Math.abs(v), d)} %`;
  const curto = (v) => (v >= 1e6 ? `US$ ${num(v / 1e6, 1)} mi` : `US$ ${num(v / 1e3, 0)} mil`);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const cssVar = (nome) => getComputedStyle(document.documentElement).getPropertyValue(nome).trim();
  const temMapa = () => typeof maplibregl !== "undefined";
  const temGrafico = () => typeof Chart !== "undefined";

  function toast(msg) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.add("on");
    clearTimeout(toast.t);
    toast.t = setTimeout(() => el.classList.remove("on"), 2800);
  }

  /** Chamada HTTP com tempo-limite; devolve {ok, status, dados, ms} e nunca lança. */
  async function api(caminho, opcoes = {}) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), opcoes.timeout || 12000);
    const t0 = performance.now();
    try {
      const cab = { ...(opcoes.corpo ? { "Content-Type": "application/json" } : {}), ...(opcoes.headers || {}) };
      const resp = await fetch(caminho, {
        method: opcoes.metodo || "GET",
        headers: Object.keys(cab).length ? cab : undefined,
        body: opcoes.corpo ? JSON.stringify(opcoes.corpo) : undefined,
        cache: "no-store",
        signal: ctrl.signal,
      });
      let dados = null;
      if (opcoes.texto) { try { dados = await resp.text(); } catch (e) { dados = null; } }
      else { try { dados = await resp.json(); } catch (e) { dados = null; } }
      return { ok: resp.ok, status: resp.status, dados, ms: performance.now() - t0 };
    } catch (e) {
      return { ok: false, status: 0, dados: null, ms: performance.now() - t0 };
    } finally {
      clearTimeout(t);
    }
  }

  const cache = { modelo: null, regioes: null };
  async function carregarModelo() {
    if (cache.modelo) return cache.modelo;
    const r = await api("/v1/modelo");
    if (r.ok && r.dados) cache.modelo = r.dados;
    return cache.modelo;
  }
  let promessaRegioes = null;
  function carregarRegioes() {
    if (cache.regioes) return Promise.resolve(cache.regioes);
    if (promessaRegioes) return promessaRegioes;
    promessaRegioes = api("/v1/regioes").then((r) => {
      const lista = r.ok ? (Array.isArray(r.dados) ? r.dados : r.dados && r.dados.regioes) : null;
      if (Array.isArray(lista)) cache.regioes = lista.map((g) => ({ ...g, cep: String(g.cep), latitude: Number(g.latitude), longitude: Number(g.longitude) }));
      promessaRegioes = null;
      return cache.regioes;
    });
    return promessaRegioes;
  }
  const regiaoDoCep = (cep) => (cache.regioes || []).find((g) => g.cep === String(cep));

  // ---------------------------------------------------------------- estado compartilhado
  const PADRAO = {
    quartos: 3, banheiros: 2, area_util_m2: 170, area_terreno_m2: 700, andares: 1, frente_agua: false,
    vista: 0, condicao: 3, padrao_construtivo: 7, area_porao_m2: 0, ano_construcao: 1990, ano_reforma: null,
    cep: "98103", latitude: 47.67, longitude: -122.34,
  };
  const estado = { imovel: { ...PADRAO }, cep: PADRAO.cep, ultimoResultado: null, cenarioAplicado: null };
  const ouvintes = [];
  const ouvir = (fn) => ouvintes.push(fn);
  /** Atualiza o estado e avisa os módulos. `origem` evita que o módulo que mudou reaja a si mesmo. */
  function atualizarEstado(parcial, origem) {
    Object.assign(estado.imovel, parcial);
    if (parcial.cep !== undefined) estado.cep = String(parcial.cep);
    ouvintes.forEach((fn) => { try { fn(origem); } catch (e) { /* um módulo não derruba os outros */ } });
  }
  const resultadoAtual = () => estado.ultimoResultado && JSON.stringify(estado.ultimoResultado.payload) === JSON.stringify(estado.imovel);

  // ---------------------------------------------------------------- tema
  function temaAtual() {
    try { return localStorage.getItem("ai-tema") || "dark"; } catch (e) { return "dark"; }
  }
  function escuroAtivo() {
    const t = document.documentElement.getAttribute("data-theme");
    if (t === "dark") return true;
    if (t === "light") return false;
    return !window.matchMedia("(prefers-color-scheme: light)").matches;
  }
  function aplicarTema(t) {
    if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
    else document.documentElement.removeAttribute("data-theme");
    try { localStorage.setItem("ai-tema", t); } catch (e) {}
    $$(".tema button").forEach((b) => b.classList.toggle("ativo", b.dataset.tema === t));
    aoMudarTema();
  }
  $$(".tema button").forEach((b) => b.addEventListener("click", () => aplicarTema(b.dataset.tema)));
  window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => { if (temaAtual() === "auto") aoMudarTema(); });
  (function temaInicial() {
    const t = temaAtual();
    if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
    $$(".tema button").forEach((b) => b.classList.toggle("ativo", b.dataset.tema === t));
  })();

  function aoMudarTema() {
    mapas.forEach((reg) => {
      if (reg.tema === escuroAtivo()) return;
      reg.tema = escuroAtivo();
      reg.m.setStyle(estiloUrl(), { diff: false });
    });
    if (graficos.sim) desenharSimulacao(ultimaSimulacao);
    if (graficos.imp && cache.modelo) desenharImportancia(cache.modelo);
    if (graficos.ranking) desenharRanking();
  }

  // ---------------------------------------------------------------- mapas (MapLibre)
  // Base vetorial do OpenFreeMap (sem chave), um estilo por tema, e imagens de satélite
  // da Esri como camada raster opcional abaixo dos rótulos. Camadas próprias são refeitas
  // a cada troca de estilo, no evento style.load.
  const OFM = "https://tiles.openfreemap.org/styles/";
  const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
  const estiloUrl = () => OFM + (escuroAtivo() ? "dark" : "positron");
  const LIMITE_MAPA = [[-123.1, 46.95], [-120.75, 47.98]];
  const mapas = [];
  const basePreferida = { avaliar: "mapa", valor: "mapa", detalhe: "mapa" };
  window.__errosMapa = [];
  function criarMapa(chave, centro, zoom, depoisDoEstilo) {
    const m = new maplibregl.Map({
      container: "mapa-" + chave, style: estiloUrl(), center: centro, zoom,
      attributionControl: { compact: true }, dragRotate: false, pitchWithRotate: false, maxBounds: LIMITE_MAPA,
    });
    m.touchZoomRotate.disableRotation();
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    // Tela cheia da área inteira do mapa, para levar junto os chips, a legenda e os seletores sobrepostos
    const area = m.getContainer().closest(".mapa-area") || m.getContainer().parentElement;
    m.addControl(new maplibregl.FullscreenControl({ container: area }), "bottom-right");
    const reg = { m, chave, tema: escuroAtivo(), depoisDoEstilo, tres: false, raf: null };
    m.on("style.load", () => { adicionarSatelite(reg); adicionarPredios(reg); if (reg.depoisDoEstilo) reg.depoisDoEstilo(); });
    m.on("error", (e) => { window.__errosMapa.push(String((e && e.error && e.error.message) || e)); });
    // Alguns estilos citam padrões de preenchimento ausentes do sprite: um pixel transparente evita o aviso.
    m.on("styleimagemissing", (e) => { if (!m.hasImage(e.id)) m.addImage(e.id, { width: 1, height: 1, data: new Uint8Array(4) }); });
    mapas.push(reg);
    return reg;
  }
  function adicionarSatelite(reg) {
    const m = reg.m;
    if (!m.getSource("satelite")) m.addSource("satelite", { type: "raster", tiles: [ESRI], tileSize: 256, maxzoom: 19, attribution: "Imagens: Esri, Maxar, Earthstar Geographics" });
    // A foto entra acima de todo o desenho do estilo (prédios e ruas em cor escura) e abaixo só dos
    // rótulos finais; o primeiro rótulo (nome da água) vem antes dos prédios e deixava tudo preto.
    const camadas = m.getStyle().layers || [];
    const ultimaForma = camadas.reduce((u, l, i) => (l.type !== "symbol" ? i : u), -1);
    const rotulos = camadas.slice(ultimaForma + 1).find((l) => l.type === "symbol");
    if (!m.getLayer("satelite")) {
      m.addLayer({ id: "satelite", type: "raster", source: "satelite", layout: { visibility: basePreferida[reg.chave] === "satelite" ? "visible" : "none" } }, rotulos && rotulos.id);
    }
  }
  $$('[data-controle="base"]').forEach((grupo) => grupo.addEventListener("click", (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    const chave = grupo.dataset.mapa;
    basePreferida[chave] = b.dataset.v;
    $$("button", grupo).forEach((x) => x.classList.toggle("ativo", x === b));
    const reg = mapas.find((r) => r.chave === chave);
    if (reg) definirBase(reg, b.dataset.v);
  }));

  function distancia(a, b, c, d) {
    const r = Math.PI / 180, x = (d - b) * r * Math.cos(((a + c) / 2) * r), y = (c - a) * r;
    return Math.sqrt(x * x + y * y);
  }
  function cepMaisProximo(lat, lon) {
    let melhor = null, dMin = Infinity;
    (cache.regioes || []).forEach((g) => {
      const dd = distancia(lat, lon, g.latitude, g.longitude);
      if (dd < dMin) { dMin = dd; melhor = g; }
    });
    return melhor;
  }
  const arred = (v) => Math.round(v * 10000) / 10000;
  // Área atendida pelo modelo (limites aceitos pela API) e uma folga para navegar no mapa.
  const AREA = { latMin: 47.15, latMax: 47.78, lonMin: -122.52, lonMax: -121.31 };
  const dentroDaArea = (lat, lon) => lat >= AREA.latMin && lat <= AREA.latMax && lon >= AREA.lonMin && lon <= AREA.lonMax;
  const AVISO_AREA = "Fora da área atendida: o modelo cobre King County (WA). Escolha um ponto dentro da região dos CEPs.";

  // Camada de círculos por CEP (US$/m² mediano), usada nos dois mapas.
  const ESCALA = ["#e4dbff", "#c2acfc", "#9b7bf9", "#7046f2", "#4b22b5"];
  const DESTAQUE = "#ff9f0a";
  function quantis(valores, n) {
    const v = valores.slice().sort((a, b) => a - b);
    return Array.from({ length: n - 1 }, (_, i) => v[Math.floor(((i + 1) / n) * (v.length - 1))]);
  }
  function geojsonCeps(regioes) {
    return {
      type: "FeatureCollection",
      features: regioes.map((g) => ({
        type: "Feature", properties: { cep: g.cep, vendas: Number(g.vendas), pm2: Number(g.preco_m2_mediano_usd), mediano: Number(g.preco_mediano_usd) },
        geometry: { type: "Point", coordinates: [g.longitude, g.latitude] },
      })),
    };
  }
  function adicionarCeps(m, visivel) {
    if (!cache.regioes) return false;
    if (!m.getSource("ceps")) m.addSource("ceps", { type: "geojson", data: geojsonCeps(cache.regioes), promoteId: "cep" });
    if (!m.getLayer("ceps")) m.addLayer({ id: "ceps", type: "circle", source: "ceps", layout: { visibility: visivel ? "visible" : "none" }, paint: { "circle-opacity": 0.82 } });
    const vals = cache.regioes.map((g) => Number(g.preco_m2_mediano_usd));
    const cortes = quantis(vals, ESCALA.length);
    const passos = ["step", ["get", "pm2"], ESCALA[0]];
    cortes.forEach((c, i) => passos.push(c, ESCALA[i + 1]));
    const maxV = Math.max(...cache.regioes.map((g) => Number(g.vendas) || 1));
    const borda = escuroAtivo() ? "rgba(255,255,255,0.6)" : "rgba(75,34,181,0.55)";
    m.setPaintProperty("ceps", "circle-color", passos);
    m.setPaintProperty("ceps", "circle-radius", ["interpolate", ["linear"], ["sqrt", ["/", ["get", "vendas"], maxV]], 0, 6, 1, 20]);
    m.setPaintProperty("ceps", "circle-stroke-color", ["case", ["boolean", ["feature-state", "destaque"], false], DESTAQUE, borda]);
    m.setPaintProperty("ceps", "circle-stroke-width", ["case", ["boolean", ["feature-state", "destaque"], false], 4, ["boolean", ["feature-state", "hover"], false], 2.5, 1]);
    return true;
  }
  function faixasEscala() {
    const vals = cache.regioes.map((g) => Number(g.preco_m2_mediano_usd));
    return { vals, cortes: quantis(vals, ESCALA.length), min: Math.min(...vals), max: Math.max(...vals) };
  }
  function marcarCep(m, anterior, novo) {
    if (!m || !m.getSource("ceps")) return;
    if (anterior) m.setFeatureState({ source: "ceps", id: anterior }, { destaque: false });
    if (novo) m.setFeatureState({ source: "ceps", id: novo }, { destaque: true });
  }

  // ---------------------------------------------------------------- roteamento
  const inicializadas = new Set();
  const APELIDOS = { inicio: "painel", relatorios: "banco" };
  let viewAtual = "painel";
  function rotear() {
    let nome = (location.hash || "#painel").slice(1).split("?")[0] || "painel";
    nome = APELIDOS[nome] || nome;
    const alvo = $(`.view[data-view="${nome}"]`) ? nome : "painel";
    viewAtual = alvo;
    $$(".view").forEach((v) => { v.hidden = v.dataset.view !== alvo; });
    $$("[data-nav]").forEach((a) => a.classList.toggle("ativo", a.dataset.nav === alvo));
    const link = $(`.menu a[data-nav="${alvo}"], .lateral-rodape a[data-nav="${alvo}"]`);
    $("#cab-titulo").textContent = link ? link.textContent.trim() : "Painel";
    document.title = `${link ? link.textContent.trim() : "Painel"} · Avaliador Imobiliário`;
    fecharMenu();
    if (!rotear.semRolagem) window.scrollTo({ top: 0 });
    rotear.semRolagem = false;
    const init = {
      painel: initPainel, avaliar: initAvaliar, avaliacoes: initAvaliacoes, simulador: initSimulador, mercado: initMercado,
      mapa: initMapa, modelo: initModelo, comercial: initComercial, banco: initBanco, dev: initDev, sobre: initInicio,
    }[alvo];
    if (!inicializadas.has(alvo)) { inicializadas.add(alvo); init && init(); }
    else ({ painel: atualizarPainel, banco: () => { atualizarUso(); if (window.TelaBanco) window.TelaBanco.atualizar(); }, avaliacoes: carregarAvaliacoes, comercial: carregarClientes }[alvo] || (() => {}))();
    setTimeout(() => { mapas.forEach((r) => r.m.resize()); arrumarPins(); }, 60);
  }
  window.addEventListener("hashchange", rotear);
  function irPara(view, semRolagem) {
    rotear.semRolagem = !!semRolagem;
    if (location.hash === "#" + view) rotear();
    else location.hash = "#" + view;
  }

  // ---------------------------------------------------------------- início e saúde da API
  function fmtUptime(s) {
    s = Math.max(0, Math.floor(Number(s) || 0));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
    if (h > 0) return `${h} h ${m} min`;
    if (m > 0) return `${m} min`;
    return `${s} s`;
  }
  async function verificarSaude() {
    const selo = $("#selo-saude");
    const r = await api("/health", { timeout: 5000 });
    const d = r.dados || {};
    if (r.ok && d.modelo_carregado) {
      selo.className = "selo on";
      selo.querySelector("span").textContent = `API no ar · modelo ${d.versao_modelo || ""}`;
      selo.title = `Modelo ${d.versao_modelo || ""} na memória${d.uptime_s !== undefined ? " há " + fmtUptime(d.uptime_s) : ""}`;
    } else if (r.ok) {
      selo.className = "selo off";
      selo.querySelector("span").textContent = "API no ar · modelo não carregado";
    } else {
      selo.className = "selo off";
      selo.querySelector("span").textContent = "API indisponível";
    }
  }
  async function initInicio() {
    carregarRegioes().then((rs) => {
      if (!rs) return;
      $("#st-vendas").textContent = num(rs.reduce((s, g) => s + (Number(g.vendas) || 0), 0));
      $("#st-ceps").textContent = num(rs.length);
    });
    carregarModelo().then((m) => {
      const t = m && m.metricas && m.metricas.teste;
      if (t && t.R2 !== undefined) $("#st-r2").textContent = num(t.R2, 3);
    });
    const r = await prever({ ...PADRAO });
    if (r.ok && r.dados) {
      const fx = r.dados.faixa_provavel_usd || {};
      $("#st-lat").textContent = `${num(r.ms, 0)} ms`;
      $("#hero-cep").textContent = PADRAO.cep;
      $("#hero-preco").textContent = usd.format(r.dados.preco_estimado_usd);
      $("#hero-faixa").textContent = `faixa ${usd.format(fx.minimo)} – ${usd.format(fx.maximo)} · ${PADRAO.area_util_m2} m², ${PADRAO.quartos} quartos`;
    } else {
      $("#hero-faixa").textContent = "API indisponível no momento";
    }
  }

  // ---------------------------------------------------------------- formulário (espelho do estado)
  const form = $("#form-imovel");
  function atualizarSaidas() {
    $$("output[data-out]", form).forEach((o) => {
      const v = form.elements[o.dataset.out].value;
      o.textContent = o.dataset.out.endsWith("_m2") ? `${num(v)} m²` : v;
    });
  }
  function atualizarResumos() {
    const v = estado.imovel;
    $("#resumo-estrutura").textContent = `${v.quartos} qt · ${num(v.banheiros, v.banheiros % 1 ? 2 : 0)} bh · ${num(v.area_util_m2)} m²`;
    $("#resumo-qualidade").textContent = `padrão ${v.padrao_construtivo} · cons. ${v.condicao} · vista ${v.vista}`;
    $("#resumo-local").textContent = `CEP ${v.cep} · ${v.ano_construcao}${v.ano_reforma ? " / " + v.ano_reforma : ""}`;
  }
  function garantirOpcaoCep(cep) {
    const sel = form.elements.cep;
    if (![...sel.options].some((o) => o.value === String(cep))) sel.add(new Option(String(cep), String(cep)));
  }
  /** Escreve o estado no formulário. */
  function sincronizarFormulario() {
    const v = estado.imovel;
    Object.entries(v).forEach(([k, val]) => {
      const el = form.elements[k];
      if (!el) return;
      if (el instanceof RadioNodeList) { el.value = String(val); return; }
      if (el.type === "checkbox") el.checked = !!val;
      else if (k === "cep") { garantirOpcaoCep(val); el.value = String(val); }
      else el.value = val === null || val === undefined ? "" : val;
    });
    atualizarSaidas();
    atualizarResumos();
  }
  /** Lê o formulário para o formato do contrato da API. */
  function lerFormulario() {
    const f = form.elements;
    const n = (k) => Number(f[k].value);
    const reforma = f.ano_reforma.value.trim();
    return {
      quartos: n("quartos"), banheiros: n("banheiros"), area_util_m2: n("area_util_m2"), area_terreno_m2: n("area_terreno_m2"),
      andares: n("andares"), frente_agua: f.frente_agua.checked, vista: Number(f.vista.value), condicao: Number(f.condicao.value),
      padrao_construtivo: n("padrao_construtivo"), area_porao_m2: n("area_porao_m2"), ano_construcao: n("ano_construcao"),
      ano_reforma: reforma === "" ? null : Number(reforma), cep: String(f.cep.value), latitude: n("latitude"), longitude: n("longitude"),
    };
  }
  form.addEventListener("input", () => { atualizarSaidas(); estado.cenarioAplicado = null; atualizarEstado(lerFormulario(), "form"); });
  form.addEventListener("change", (ev) => {
    if (ev.target.name === "cep") {
      const g = regiaoDoCep(ev.target.value);
      const parcial = { cep: ev.target.value };
      if (g) { parcial.latitude = arred(g.latitude); parcial.longitude = arred(g.longitude); }
      atualizarEstado(parcial, "form-cep");
      sincronizarFormulario();
      if (mapaAvaliar && g) mapaAvaliar.m.easeTo({ center: [g.longitude, g.latitude] });
    } else if (ev.target.name === "latitude" || ev.target.name === "longitude") {
      const lat = Number(form.elements.latitude.value), lon = Number(form.elements.longitude.value);
      const g = Number.isFinite(lat) && Number.isFinite(lon) ? cepMaisProximo(lat, lon) : null;
      atualizarEstado({ latitude: lat, longitude: lon, ...(g ? { cep: g.cep } : {}) }, "form-coord");
      sincronizarFormulario();
    }
  });
  $$(".stepper button", form).forEach((b) => b.addEventListener("click", () => {
    const el = form.elements[b.dataset.alvo];
    const v = Math.min(Number(el.max), Math.max(Number(el.min), (Number(el.value) || 0) + Number(b.dataset.step)));
    el.value = Math.round(v * 100) / 100;
    form.dispatchEvent(new Event("input"));
  }));
  $("#btn-padrao").addEventListener("click", () => {
    limparErros();
    estado.cenarioAplicado = null;
    atualizarEstado({ ...PADRAO }, "padrao");
    sincronizarFormulario();
  });
  ouvir((origem) => { if (!String(origem).startsWith("form")) sincronizarFormulario(); else atualizarResumos(); });

  function limparErros() {
    $$(".campo.invalido", form).forEach((c) => c.classList.remove("invalido"));
    $$(".erro", form).forEach((e) => { e.textContent = ""; });
  }
  function nomeCampo(campo) {
    if (Array.isArray(campo)) campo = campo[campo.length - 1];
    const partes = String(campo || "").split(".");
    return partes[partes.length - 1];
  }
  /** Normaliza o corpo de erro da API (formato próprio ou o padrão do FastAPI). */
  function detalhesErro(dados) {
    if (!dados) return [];
    if (Array.isArray(dados.detalhes)) return dados.detalhes.map((d) => ({ campo: nomeCampo(d.campo), mensagem: d.mensagem || d.msg }));
    if (Array.isArray(dados.detail)) return dados.detail.map((d) => ({ campo: nomeCampo(d.loc), mensagem: d.msg }));
    return [];
  }
  function marcarErros(lista) {
    lista.forEach(({ campo, mensagem }) => {
      const alvo = $(`.erro[data-erro="${campo}"]`, form);
      if (!alvo) return;
      alvo.textContent = mensagem || "Valor inválido";
      alvo.closest(".campo").classList.add("invalido");
      const det = alvo.closest("details");
      if (det) det.open = true;
    });
  }
  function alertaHTML(titulo, msg, lista, tipo) {
    const itens = lista.length ? `<ul>${lista.map((d) => `<li><b>${esc(d.campo)}</b>: ${esc(d.mensagem)}</li>`).join("")}</ul>` : "";
    return `<div class="alerta ${tipo}"><h4>${esc(titulo)}</h4><p>${esc(msg)}</p>${itens}</div>`;
  }
  function tituloErro(status) {
    return status === 422 ? "Dados inválidos (422)" : status === 400 ? "Regra de negócio violada (400)" : status === 503 ? "Modelo indisponível (503)" : `Erro ${status}`;
  }
  function mensagemErro(r) {
    if (r.status === 0) return "Não foi possível falar com o servidor. Confirme que a API está rodando (uvicorn) e tente de novo.";
    return (r.dados && (r.dados.mensagem || (typeof r.dados.detail === "string" ? r.dados.detail : ""))) || "Revise os campos destacados.";
  }

  // ---------------------------------------------------------------- avaliação
  const ORIGEM = { "X-Origem": "portal" };
  function prever(payload) {
    return api("/v1/predict", { metodo: "POST", corpo: payload, headers: ORIGEM });
  }
  /** Avalia o imóvel do estado e atualiza cartão, popup e comparativo do CEP. */
  async function avaliarEstado(comPopup) {
    limparErros();
    const btn = $("#btn-avaliar");
    btn.disabled = true;
    btn.innerHTML = '<span class="carregando"></span> Avaliando…';
    const payload = { ...estado.imovel };
    const r = await prever(payload);
    btn.disabled = false;
    btn.textContent = "Avaliar imóvel";
    const caixa = $("#resultado");
    if (r.ok && r.dados) {
      estado.ultimoResultado = { dados: r.dados, payload };
      mostrarResultado(r.dados, payload);
      if (comPopup) popupAvaliacao(r.dados, payload);
      atualizarChips();
      return;
    }
    const lista = detalhesErro(r.dados);
    marcarErros(lista);
    // Regra de negócio (400) vem sem lista de campos: liga a mensagem ao campo citado nela.
    if (r.status === 400 && !lista.length && r.dados && r.dados.mensagem) {
      const msg = normalizar(r.dados.mensagem);
      const campo = msg.includes("reforma") ? "ano_reforma" : msg.includes("cep") ? "cep" : msg.includes("constru") ? "ano_construcao" : null;
      if (campo) marcarErros([{ campo, mensagem: r.dados.mensagem }]);
    }
    caixa.innerHTML = alertaHTML(r.status ? tituloErro(r.status) : "API indisponível", mensagemErro(r), lista, r.status >= 500 ? "" : "aviso");
    if (comPopup && popupAval) popupAval.remove();
    atualizarChips();
  }
  form.addEventListener("submit", (ev) => { ev.preventDefault(); avaliarEstado(true); });

  function comparativoCep(d, payload) {
    const regiao = regiaoDoCep(payload.cep);
    if (!regiao || !regiao.preco_m2_mediano_usd || !d.preco_por_m2_usd) return { texto: "—", classe: "" };
    const dif = Number(d.preco_por_m2_usd) / Number(regiao.preco_m2_mediano_usd) - 1;
    return { texto: sinal(dif * 100), classe: dif >= 0 ? "pos" : "neg", regiao };
  }
  function relativo(v) {
    v = Number(v);
    return v > 0.3 && v < 3 ? (v - 1) * 100 : v * 100;
  }
  function blocoConfianca() {
    const m = cache.modelo;
    const t = m && m.metricas && m.metricas.teste;
    if (!t || t.R2 === undefined) return "";
    const graus = Math.max(0, Math.min(1, t.R2)) * 360;
    const faixa = m.faixa_erro && m.faixa_erro.p10 !== undefined
      ? ` 80 % dos imóveis de validação ficaram entre ${sinal(relativo(m.faixa_erro.p10))} e ${sinal(relativo(m.faixa_erro.p90))} do valor estimado.` : "";
    return `<div class="confianca"><div class="anel" style="background:radial-gradient(closest-side, var(--card) 74%, transparent 76%), conic-gradient(var(--accent) ${graus}deg, var(--line2) 0)">${num(t.R2 * 100, 0)}%</div>
      <p>Confiança do modelo: R² de ${num(t.R2, 3)} no teste, erro percentual médio de ${pct(t.MAPE)}.${faixa}</p></div>`;
  }
  function mostrarResultado(d, payload) {
    const preco = Number(d.preco_estimado_usd);
    const fx = d.faixa_provavel_usd || {};
    const min = Number(fx.minimo ?? preco), max = Number(fx.maximo ?? preco);
    const pos = max > min ? Math.min(100, Math.max(0, ((preco - min) / (max - min)) * 100)) : 50;
    const comp = comparativoCep(d, payload);
    $("#resultado").innerHTML = `
      <div class="res-topo"><div><h3 class="res-titulo">Avaliação do imóvel</h3>
        <p class="res-local">${esc(num(payload.area_util_m2))} m² · ${esc(payload.quartos)} quartos · CEP ${esc(payload.cep)} · <span id="res-endereco">${num(payload.latitude, 4)}, ${num(payload.longitude, 4)}</span></p></div>
        ${d.versao_modelo ? `<span class="chip">modelo ${esc(d.versao_modelo)}</span>` : ""}</div>
      <div class="res-rotulo">Valor estimado</div>
      <div class="res-preco"><small>US$</small>${num(preco)}</div>
      <div class="res-rotulo">Faixa provável</div>
      <div class="faixa-barra"><div class="faixa-ponto" style="left:${pos}%"></div></div>
      <div class="faixa-valores"><span>mín. <b>${usd.format(min)}</b></span><span>máx. <b>${usd.format(max)}</b></span></div>
      <div class="res-grade">
        <div class="res-item"><small>US$ por m²</small><b>${d.preco_por_m2_usd ? usd.format(d.preco_por_m2_usd) : "—"}</b></div>
        <div class="res-item"><small>vs. mediana do CEP${comp.regiao ? " (" + usd.format(comp.regiao.preco_m2_mediano_usd) + "/m²)" : ""}</small><b class="${comp.classe}">${comp.texto}</b></div>
        <div class="res-item"><small>Resposta da API</small><b>${d.latencia_ms !== undefined ? num(d.latencia_ms, 1) + " ms" : "—"}</b></div>
      </div>
      ${blocoConfianca()}
      <div class="entorno" id="res-entorno"><div class="res-rotulo">Entorno · 1,5 km</div><p class="nota">Consultando escolas, saúde, mercados e transporte no OpenStreetMap…</p></div>
      <p class="ref">${esc(d.referencia_mercado || "")}</p>`;
    mostrarEndereco($("#res-endereco"), payload.latitude, payload.longitude, (e) => e.endereco);
    mostrarEntorno($("#res-entorno"), payload.latitude, payload.longitude);
  }
  // ---------------------------------------------------------------- entorno (comodidades do OpenStreetMap)
  const entornos = new Map();
  function mostrarEntorno(el, lat, lng) {
    if (!el) return;
    const k = chaveCoord(lat, lng);
    el.dataset.coord = k;
    if (!entornos.has(k)) {
      entornos.set(k, api(`/v1/comodidades?lat=${encodeURIComponent(lat)}&lng=${encodeURIComponent(lng)}`)
        .then((r) => (r.ok && r.dados && r.dados.disponivel ? r.dados : (entornos.delete(k), null)))
        .catch(() => (entornos.delete(k), null)));
    }
    entornos.get(k).then((c) => {
      if (el.dataset.coord !== k) return;
      if (!c) { el.innerHTML = `<div class="res-rotulo">Entorno · 1,5 km</div><p class="nota">O OpenStreetMap não respondeu agora; o laudo traz o entorno quando for emitido de novo.</p>`; return; }
      const ix = c.indice_conveniencia;
      const linhas = c.categorias.map((cat) => {
        const p = cat.mais_proximos[0];
        return `<li><span>${esc(cat.nome)} <em>${num(cat.quantidade)}</em></span><b>${p ? `${esc(p.nome)} · ${num(p.distancia_m)} m · ${num(p.a_pe_min)} min a pé` : "nenhum no raio"}</b></li>`;
      }).join("");
      el.innerHTML = `<div class="res-rotulo">Entorno · ${num(c.raio_m / 1000, 1)} km${ix ? ` <span class="chip" title="${esc(ix.explicacao)}">conveniência ${ix.valor}/100 · ${esc(ix.classificacao)}</span>` : ""}</div>
        <ul class="entorno-lista">${linhas}</ul><p class="nota">${esc(c.fonte)}</p>`;
    });
  }

  // ---------------------------------------------------------------- mapa da avaliação
  let mapaAvaliar = null, marcador = null, popupAval = null, pins = [], camadaAvaliar = "ambos";
  function moverMarcador(lat, lon) {
    if (!mapaAvaliar) return;
    if (!marcador) {
      const el = document.createElement("div");
      el.className = "marcador-imovel";
      el.style.zIndex = "5";
      marcador = new maplibregl.Marker({ element: el }).setLngLat([lon, lat]).addTo(mapaAvaliar.m);
    } else marcador.setLngLat([lon, lat]);
  }
  function popupAvaliacao(d, payload) {
    if (!mapaAvaliar) return;
    if (popupAval) popupAval.remove();
    const fx = d.faixa_provavel_usd || {};
    popupAval = new maplibregl.Popup({ maxWidth: "280px", offset: 20 })
      .setLngLat([payload.longitude, payload.latitude])
      .setHTML(`<span class="pop-sub">Valor estimado · CEP ${esc(payload.cep)}</span><span class="pop-preco">${usd.format(d.preco_estimado_usd)}</span><span class="pop-sub">Faixa: ${usd.format(fx.minimo)} – ${usd.format(fx.maximo)}</span>`)
      .addTo(mapaAvaliar.m);
  }
  // ---------------------------------------------------------------- endereço (OpenStreetMap, com cache no servidor e aqui)
  const enderecos = new Map();
  const chaveCoord = (lat, lng) => `${Number(lat).toFixed(5)},${Number(lng).toFixed(5)}`;
  function enderecoDe(lat, lng) {
    const k = chaveCoord(lat, lng);
    if (!enderecos.has(k)) {
      enderecos.set(k, api(`/v1/endereco?lat=${encodeURIComponent(lat)}&lng=${encodeURIComponent(lng)}`)
        .then((r) => (r.ok && r.dados && r.dados.disponivel ? r.dados : (enderecos.delete(k), null)))
        .catch(() => (enderecos.delete(k), null)));
    }
    return enderecos.get(k);
  }
  const ABREVIA = [[/\bNortheast\b/g, "NE"], [/\bNorthwest\b/g, "NW"], [/\bSoutheast\b/g, "SE"], [/\bSouthwest\b/g, "SW"],
    [/\bNorth\b/g, "N"], [/\bSouth\b/g, "S"], [/\bEast\b/g, "E"], [/\bWest\b/g, "W"], [/\bStreet\b/g, "St"], [/\bAvenue\b/g, "Ave"],
    [/\bPlace\b/g, "Pl"], [/\bBoulevard\b/g, "Blvd"], [/\bDrive\b/g, "Dr"], [/\bRoad\b/g, "Rd"], [/\bLane\b/g, "Ln"], [/\bCourt\b/g, "Ct"]];
  const ruaCurta = (e) => ABREVIA.reduce((s, [re, ab]) => s.replace(re, ab), [e.numero, e.rua].filter(Boolean).join(" "));
  // Preenche o elemento quando o endereço chega, se ele ainda for do mesmo ponto
  function mostrarEndereco(el, lat, lng, formato) {
    if (!el) return;
    const k = chaveCoord(lat, lng);
    el.dataset.coord = k;
    enderecoDe(lat, lng).then((e) => { if (e && el.dataset.coord === k) { el.textContent = formato(e); el.hidden = false; el.title = `${e.endereco} · ${e.fonte}`; } });
  }
  function atualizarChips() {
    const v = estado.imovel;
    const preco = resultadoAtual() ? `<span class="preco">${usd.format(estado.ultimoResultado.dados.preco_estimado_usd)}</span>` : "";
    $("#chips-imovel").innerHTML = `${preco}<span>${num(v.area_util_m2)} m²</span><span>${v.quartos} quartos</span><span>${num(v.banheiros, v.banheiros % 1 ? 2 : 0)} banheiros</span><span id="chip-endereco" hidden></span><span>CEP ${esc(v.cep)}</span>`;
    mostrarEndereco($("#chip-endereco"), v.latitude, v.longitude, ruaCurta);
  }
  ouvir(atualizarChips);
  function legendaAvaliar() {
    const el = $("#legenda-avaliar");
    if (!cache.regioes) { el.innerHTML = ""; return; }
    if (camadaAvaliar === "precos") { el.innerHTML = "<b>Preço mediano de venda por CEP</b><span class=\"nota\">Clique num preço para avaliar o imóvel ali.</span>"; return; }
    const f = faixasEscala();
    el.innerHTML = `<b>US$/m² mediano por CEP</b><div class="legenda-barra" style="background:linear-gradient(90deg, ${ESCALA.join(", ")})"></div><div class="legenda-valores"><span>${usd.format(f.min)}</span><span>${usd.format(f.max)}</span></div>`;
  }
  function criarPins() {
    if (!mapaAvaliar || !cache.regioes || pins.length) return;
    pins = cache.regioes.map((g) => {
      const el = document.createElement("button");
      el.type = "button";
      el.className = "pin-preco";
      el.textContent = curto(g.preco_mediano_usd);
      el.title = `CEP ${g.cep} · mediana de venda ${usd.format(g.preco_mediano_usd)} · ${num(g.vendas)} vendas`;
      el.style.zIndex = "1";
      el.addEventListener("click", (ev) => { ev.stopPropagation(); avaliarNoCep(g); });
      const mk = new maplibregl.Marker({ element: el, anchor: "bottom", offset: [0, -7] }).setLngLat([g.longitude, g.latitude]).addTo(mapaAvaliar.m);
      return { g, el, mk, w: el.textContent.length * 7.6 + 26 };
    });
    marcarPinAtivo();
    arrumarPins();
  }
  function marcarPinAtivo() {
    pins.forEach((p) => { const a = p.g.cep === estado.cep; p.el.classList.toggle("ativo", a); p.el.style.zIndex = a ? "3" : "1"; });
  }
  /** Esconde os preços que se sobrepõem; o CEP ativo e os com mais vendas têm prioridade. */
  function arrumarPins() {
    if (!mapaAvaliar || !pins.length) return;
    const m = mapaAvaliar.m, ocupadas = [];
    const ordem = pins.slice().sort((a, b) => (b.g.cep === estado.cep) - (a.g.cep === estado.cep) || b.g.vendas - a.g.vendas);
    ordem.forEach((p) => {
      if (camadaAvaliar === "valor" || mapaAvaliar.tres) { p.el.style.display = "none"; return; }
      const pt = m.project([p.g.longitude, p.g.latitude]);
      const caixa = { x: pt.x - p.w / 2 - 3, y: pt.y - 40, w: p.w + 6, h: 36 };
      const bate = ocupadas.some((o) => caixa.x < o.x + o.w && o.x < caixa.x + caixa.w && caixa.y < o.y + o.h && o.y < caixa.y + caixa.h);
      p.el.style.display = bate ? "none" : "";
      if (!bate) ocupadas.push(caixa);
    });
  }
  function aplicarCamada() {
    $$('[data-controle="camada"] button').forEach((b) => b.classList.toggle("ativo", b.dataset.v === camadaAvaliar));
    if (mapaAvaliar && mapaAvaliar.m.getLayer("ceps")) mapaAvaliar.m.setLayoutProperty("ceps", "visibility", camadaAvaliar === "precos" ? "none" : "visible");
    arrumarPins();
    legendaAvaliar();
  }
  $('[data-controle="camada"]').addEventListener("click", (ev) => {
    const b = ev.target.closest("button");
    if (!b) return;
    camadaAvaliar = b.dataset.v;
    aplicarCamada();
  });
  let cepMarcadoAvaliar = null;
  function camadasAvaliar() {
    if (!mapaAvaliar) return;
    if (adicionarCeps(mapaAvaliar.m, camadaAvaliar !== "precos")) {
      cepMarcadoAvaliar = null;
      marcarCep(mapaAvaliar.m, null, estado.cep);
      cepMarcadoAvaliar = estado.cep;
    }
  }
  function avaliarNoCep(g) {
    estado.cenarioAplicado = null;
    atualizarEstado({ cep: g.cep, latitude: arred(g.latitude), longitude: arred(g.longitude) }, "mapa-avaliar");
    moverMarcador(estado.imovel.latitude, estado.imovel.longitude);
    avaliarEstado(true);
  }
  async function initAvaliar() {
    sincronizarFormulario();
    atualizarChips();
    carregarModelo();
    if (temMapa()) {
      mapaAvaliar = criarMapa("avaliar", [estado.imovel.longitude, estado.imovel.latitude], 11.2, camadasAvaliar);
      moverMarcador(estado.imovel.latitude, estado.imovel.longitude);
      mapaAvaliar.m.on("moveend", arrumarPins);
      iniciar3DAvaliar();
      mapaAvaliar.m.on("click", (e) => {
        const lat = arred(e.lngLat.lat), lon = arred(e.lngLat.lng);
        if (!dentroDaArea(lat, lon)) { toast(AVISO_AREA); return; }
        const g = cepMaisProximo(lat, lon);
        estado.cenarioAplicado = null;
        atualizarEstado({ latitude: lat, longitude: lon, ...(g ? { cep: g.cep } : {}) }, "mapa-avaliar");
        moverMarcador(lat, lon);
        avaliarEstado(true);
      });
    } else {
      $("#mapa-avaliar").innerHTML = '<div class="vazio">Mapa indisponível sem conexão com a internet.</div>';
    }
    const regioes = await carregarRegioes();
    const sel = form.elements.cep;
    if (regioes && regioes.length) {
      sel.innerHTML = regioes.slice().sort((a, b) => a.cep.localeCompare(b.cep))
        .map((g) => `<option value="${esc(g.cep)}">${esc(g.cep)} · mediana ${usd.format(g.preco_mediano_usd)}</option>`).join("");
      sincronizarFormulario();
      if (mapaAvaliar) {
        criarPins();
        if (mapaAvaliar.m.isStyleLoaded()) camadasAvaliar();
      }
      legendaAvaliar();
    }
    if (estado.ultimoResultado) mostrarResultado(estado.ultimoResultado.dados, estado.ultimoResultado.payload);
    atualizarChips();
  }
  ouvir((origem) => {
    marcarPinAtivo();
    if (mapaAvaliar && estado.cep !== cepMarcadoAvaliar) { marcarCep(mapaAvaliar.m, cepMarcadoAvaliar, estado.cep); cepMarcadoAvaliar = estado.cep; }
    if (origem === "mapa-avaliar") return;
    moverMarcador(estado.imovel.latitude, estado.imovel.longitude);
    if (popupAval && origem !== "abrir-avaliacao") { popupAval.remove(); popupAval = null; }
  });

  // ---------------------------------------------------------------- simulador
  const graficos = {};
  let ultimaSimulacao = null;
  function cenarios(base) {
    return [
      { nome: "Imóvel atual", dados: { ...base } },
      { nome: "Reformar (2015, +1 conservação)", dados: { ...base, ano_reforma: 2015, condicao: Math.min(5, base.condicao + 1) } },
      { nome: "+1 banheiro", dados: { ...base, banheiros: Math.min(10, base.banheiros + 1) } },
      { nome: "+20 % de área útil", dados: { ...base, area_util_m2: Math.min(1300, Math.round(base.area_util_m2 * 1.2)) } },
      { nome: "Padrão construtivo +1", dados: { ...base, padrao_construtivo: Math.min(13, base.padrao_construtivo + 1) } },
      { nome: "Vista +1", dados: { ...base, vista: Math.min(4, base.vista + 1) } },
    ];
  }
  function atualizarBaseSimulador() {
    const b = estado.imovel;
    const ref = ultimaSimulacao && estado.cenarioAplicado === null && JSON.stringify(ultimaSimulacao[0].dados) === JSON.stringify(b) ? ` · hoje ${usd.format(ultimaSimulacao[0].preco)}` : "";
    $("#sim-base").textContent = `${num(b.area_util_m2)} m² · ${b.quartos} quartos · ${num(b.banheiros, b.banheiros % 1 ? 2 : 0)} banheiros · padrão ${b.padrao_construtivo} · CEP ${b.cep}${ref}`;
  }
  ouvir(atualizarBaseSimulador);
  function initSimulador() {
    $("#btn-simular").addEventListener("click", () => { estado.cenarioAplicado = null; simular(); });
    $("#sim-cartoes").addEventListener("click", (ev) => {
      const c = ev.target.closest("[data-cenario]");
      if (c) aplicarCenario(Number(c.dataset.cenario));
    });
    simular();
  }
  async function simular() {
    atualizarBaseSimulador();
    const btn = $("#btn-simular");
    btn.disabled = true;
    btn.innerHTML = '<span class="carregando"></span> Simulando…';
    const lista = cenarios({ ...estado.imovel });
    const r = await api("/v1/predict/lote", { metodo: "POST", corpo: { imoveis: lista.map((c) => c.dados) }, headers: ORIGEM });
    btn.disabled = false;
    btn.textContent = "Simular cenários";
    if (!r.ok || !r.dados || !Array.isArray(r.dados.previsoes)) {
      $("#sim-cartoes").innerHTML = "";
      $("#sim-tabela").innerHTML = alertaHTML(r.status ? `Não foi possível simular (${r.status})` : "Sem conexão", r.status === 0 ? "API indisponível. Inicie o servidor e tente de novo." : mensagemErro(r), detalhesErro(r.dados), "aviso");
      return;
    }
    const precos = r.dados.previsoes.map((p) => Number(p.preco_estimado_usd));
    ultimaSimulacao = lista.map((c, i) => ({ nome: c.nome, dados: c.dados, previsao: r.dados.previsoes[i], preco: precos[i], delta: precos[i] - precos[0], rel: precos[i] / precos[0] - 1 }));
    atualizarBaseSimulador();
    desenharSimulacao(ultimaSimulacao);
  }
  function aplicarCenario(i) {
    const c = ultimaSimulacao && ultimaSimulacao[i];
    if (!c || i === 0) return;
    atualizarEstado({ ...c.dados }, "simulador");
    estado.cenarioAplicado = i;
    estado.ultimoResultado = { dados: c.previsao, payload: { ...c.dados } };
    mostrarResultado(c.previsao, c.dados);
    atualizarChips();
    desenharSimulacao(ultimaSimulacao);
    toast(`Cenário "${c.nome}" aplicado ao formulário de avaliação`);
  }
  function desenharSimulacao(res) {
    if (!res) return;
    const itens = res.slice(1);
    const ativo = estado.cenarioAplicado;
    const maxAbs = Math.max(1, ...itens.map((x) => Math.abs(x.delta)));
    $("#sim-cartoes").innerHTML = itens.map((x, k) => `
      <button type="button" class="sim-c${ativo === k + 1 ? " ativo" : ""}" data-cenario="${k + 1}">
        <small>${esc(x.nome)}</small>
        <strong class="${x.delta >= 0 ? "pos" : "neg"}">${x.delta >= 0 ? "+" : "−"}${usd.format(Math.abs(x.delta))}</strong>
        <span>${sinal(x.rel * 100)} · ${usd.format(x.preco)}</span>
        <div class="barra"><i style="width:${(Math.abs(x.delta) / maxAbs) * 100}%"></i></div>
        <div class="acao">${ativo === k + 1 ? "✓ Aplicado à avaliação" : "Clique para aplicar"}</div>
      </button>`).join("");
    if (temGrafico()) {
      const corPos = cssVar("--accent"), corNeg = cssVar("--bad"), texto = cssVar("--muted"), linha = cssVar("--line"), borda = cssVar("--text");
      if (graficos.sim) graficos.sim.destroy();
      graficos.sim = new Chart($("#graf-sim"), {
        type: "bar",
        data: {
          labels: itens.map((x, i) => (ativo === i + 1 ? "✓ " : "") + x.nome),
          datasets: [{
            data: itens.map((x) => Math.round(x.delta)),
            backgroundColor: itens.map((x, i) => (ativo === i + 1 ? DESTAQUE : x.delta >= 0 ? corPos : corNeg)),
            borderColor: itens.map((x, i) => (ativo === i + 1 ? borda : "transparent")),
            borderWidth: itens.map((x, i) => (ativo === i + 1 ? 2 : 0)),
            borderRadius: 10, maxBarThickness: 42,
          }],
        },
        options: {
          indexAxis: "y", responsive: true, maintainAspectRatio: false,
          // Adia o redesenho: destruir o gráfico dentro do próprio evento de clique quebra o Chart.js.
          onClick: (ev, els) => { if (els.length) { const i = els[0].index + 1; setTimeout(() => aplicarCenario(i), 0); } },
          onHover: (ev, els) => { ev.native.target.style.cursor = els.length ? "pointer" : "default"; },
          plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${usd.format(c.raw)} (${sinal(itens[c.dataIndex].rel * 100)}) · clique para aplicar` } } },
          scales: { x: { ticks: { color: texto, callback: (v) => usd.format(v), maxTicksLimit: 5 }, grid: { color: linha } }, y: { ticks: { color: texto, font: { family: "Urbanist" } }, grid: { display: false } } },
        },
      });
    }
    $("#sim-tabela").innerHTML = `<table class="tabela"><thead><tr><th>Cenário</th><th>Preço estimado</th><th>Variação</th></tr></thead><tbody>${res.map((x, i) => `
      <tr class="${ativo === i ? "ativo" : ""}"><td>${esc(x.nome)}${ativo === i ? " · aplicado" : ""}</td><td>${usd.format(x.preco)}</td><td class="${i === 0 ? "" : x.delta >= 0 ? "pos" : "neg"}">${i === 0 ? "referência" : `${x.delta >= 0 ? "+" : "−"}${usd.format(Math.abs(x.delta))} (${sinal(x.rel * 100)})`}</td></tr>`).join("")}</tbody></table>`;
  }

  // ---------------------------------------------------------------- mapa de valor + ranking
  let mapaValor = null, cepDestacado = null, popupValor = null, rankingOrdem = [], rankingHover = null;
  function legendaValor() {
    const f = faixasEscala();
    const faixas = [f.min, ...f.cortes, f.max];
    $("#legenda-mapa").innerHTML = "<b>US$/m² mediano:</b>" + ESCALA.map((c, i) => `<span><i style="background:${c}"></i>${usd.format(faixas[i])}–${usd.format(faixas[i + 1])}</span>`).join("") + `<span><i style="background:transparent;border:3px solid ${DESTAQUE}"></i>CEP selecionado</span>`;
  }
  function destacarCep(cep, { voar = false, origem = "" } = {}) {
    cep = cep ? String(cep) : null;
    if (mapaValor) {
      marcarCep(mapaValor.m, cepDestacado, cep);
      const g = regiaoDoCep(cep);
      if (voar && g) mapaValor.m.flyTo({ center: [g.longitude, g.latitude], zoom: Math.max(mapaValor.m.getZoom(), 11.5), speed: 1.2 });
    }
    cepDestacado = cep;
    $("#cep-ativo").textContent = cep ? `CEP ${cep}` : "CEP —";
    if (graficos.ranking) {
      desenharRanking();
      const i = rankingOrdem.findIndex((g) => g.cep === cep);
      const sc = $("#ranking-scroll");
      if (i >= 0 && origem !== "ranking") sc.scrollTo({ top: Math.max(0, i * 22 - sc.clientHeight / 2), behavior: "smooth" });
    }
  }
  function popupCep(g, lngLat) {
    if (popupValor) popupValor.remove();
    popupValor = new maplibregl.Popup({ maxWidth: "260px", offset: 10 }).setLngLat(lngLat || [g.longitude, g.latitude])
      .setHTML(`<span class="pop-sub">CEP ${esc(g.cep)} · ${num(g.vendas)} vendas</span><span class="pop-preco">${usd.format(g.preco_mediano_usd)}</span><span class="pop-sub">preço mediano · ${usd.format(g.preco_m2_mediano_usd)}/m²</span>`)
      .addTo(mapaValor.m);
  }
  function selecionarCepNoMapa(cep, voar, origem) {
    const g = regiaoDoCep(cep);
    if (!g) return;
    atualizarEstado({ cep: g.cep, latitude: arred(g.latitude), longitude: arred(g.longitude) }, "mapa-valor");
    destacarCep(g.cep, { voar, origem });
    if (mapaValor) popupCep(g);
  }
  async function estimarNoPonto(lngLat) {
    const lat = arred(lngLat.lat), lon = arred(lngLat.lng);
    const g = cepMaisProximo(lat, lon);
    if (!g) return;
    if (!dentroDaArea(lat, lon)) {
      if (popupValor) popupValor.remove();
      popupValor = new maplibregl.Popup({ maxWidth: "260px", offset: 10 }).setLngLat([lon, lat]).setHTML(`<b>Fora da área atendida</b><br><span class="pop-sub">${esc(AVISO_AREA)}</span>`).addTo(mapaValor.m);
      return;
    }
    const payload = { ...estado.imovel, latitude: lat, longitude: lon, cep: g.cep };
    if (popupValor) popupValor.remove();
    const pop = new maplibregl.Popup({ maxWidth: "280px", offset: 10 }).setLngLat([lon, lat]).setHTML('<span class="pop-sub"><span class="carregando"></span> Estimando…</span>').addTo(mapaValor.m);
    popupValor = pop;
    const r = await prever(payload);
    if (popupValor !== pop) return;
    if (!r.ok || !r.dados) {
      pop.setHTML(`<b>${esc(r.status ? tituloErro(r.status) : "API indisponível")}</b><br><span class="pop-sub">${esc(mensagemErro(r))}</span>`);
      return;
    }
    const d = r.dados, fx = d.faixa_provavel_usd || {};
    pop.setHTML(`<span class="pop-sub">Imóvel do formulário neste local · CEP ${esc(g.cep)}</span><span class="pop-preco">${usd.format(d.preco_estimado_usd)}</span><span class="pop-sub">Faixa: ${usd.format(fx.minimo)} – ${usd.format(fx.maximo)}</span><button class="pop-btn" type="button">Abrir na avaliação</button>`);
    destacarCep(g.cep, { origem: "ponto" });
    pop.getElement().querySelector(".pop-btn").addEventListener("click", () => {
      pop.remove();
      popupValor = null;
      estado.cenarioAplicado = null;
      atualizarEstado({ latitude: lat, longitude: lon, cep: g.cep }, "abrir-avaliacao");
      estado.ultimoResultado = { dados: d, payload };
      irPara("avaliar");
      setTimeout(() => {
        mostrarResultado(d, payload);
        atualizarChips();
        if (mapaAvaliar) { mapaAvaliar.m.jumpTo({ center: [lon, lat], zoom: 12.5 }); popupAvaliacao(d, payload); arrumarPins(); }
      }, 250);
    });
  }
  function camadasValor() {
    if (!mapaValor || !adicionarCeps(mapaValor.m, true)) return;
    const atual = cepDestacado;
    cepDestacado = null;
    destacarCep(atual || estado.cep, {});
  }
  async function initMapa() {
    const regioes = await carregarRegioes();
    if (!regioes || !regioes.length) { $("#legenda-mapa").textContent = "Dados de regiões indisponíveis: verifique se a API está no ar."; return; }
    legendaValor();
    desenharRanking();
    destacarCep(estado.cep, {});
    if (!temMapa()) { $("#mapa-valor").innerHTML = '<div class="vazio">Mapa indisponível sem conexão com a internet.</div>'; return; }
    mapaValor = criarMapa("valor", [-122.2, 47.5], 9.4, camadasValor);
    const m = mapaValor.m;
    let hover = null;
    m.on("mousemove", "ceps", (e) => {
      m.getCanvas().style.cursor = "pointer";
      const id = e.features[0].properties.cep;
      if (hover && hover !== id) m.setFeatureState({ source: "ceps", id: hover }, { hover: false });
      hover = id;
      m.setFeatureState({ source: "ceps", id }, { hover: true });
      if (graficos.ranking && rankingHover !== id) { rankingHover = id; desenharRanking(); }
    });
    m.on("mouseleave", "ceps", () => {
      m.getCanvas().style.cursor = "";
      if (hover) m.setFeatureState({ source: "ceps", id: hover }, { hover: false });
      hover = null;
      if (graficos.ranking) { rankingHover = null; desenharRanking(); }
    });
    m.on("click", (e) => {
      const f = m.getLayer("ceps") ? m.queryRenderedFeatures(e.point, { layers: ["ceps"] }) : [];
      if (f.length) selecionarCepNoMapa(f[0].properties.cep, false, "mapa");
      else estimarNoPonto(e.lngLat);
    });
  }
  function desenharRanking() {
    if (!temGrafico() || !cache.regioes) return;
    rankingOrdem = cache.regioes.slice().sort((a, b) => b.preco_m2_mediano_usd - a.preco_m2_mediano_usd);
    $("#ranking-alto").style.height = `${rankingOrdem.length * 22 + 40}px`;
    const f = faixasEscala();
    const cor = (v) => ESCALA[f.cortes.filter((c) => v > c).length];
    const texto = cssVar("--muted"), linha = cssVar("--line"), forte = cssVar("--text");
    const dados = {
      labels: rankingOrdem.map((g) => g.cep),
      datasets: [{
        data: rankingOrdem.map((g) => Math.round(g.preco_m2_mediano_usd)),
        backgroundColor: rankingOrdem.map((g) => (g.cep === cepDestacado ? DESTAQUE : cor(g.preco_m2_mediano_usd))),
        borderColor: rankingOrdem.map((g) => (g.cep === cepDestacado || g.cep === rankingHover ? forte : "transparent")),
        borderWidth: rankingOrdem.map((g) => (g.cep === cepDestacado ? 2 : g.cep === rankingHover ? 1.5 : 0)),
        borderRadius: 5, barThickness: 14,
      }],
    };
    if (graficos.ranking) {
      const o = graficos.ranking.options.scales;
      graficos.ranking.data = dados; o.x.ticks.color = texto; o.y.ticks.color = texto; o.x.grid.color = linha;
      graficos.ranking.update("none");
      return;
    }
    graficos.ranking = new Chart($("#graf-ranking"), {
      type: "bar", data: dados,
      options: {
        indexAxis: "y", responsive: true, maintainAspectRatio: false, animation: false,
        onClick: (ev, els) => { if (els.length) { const cep = rankingOrdem[els[0].index].cep; setTimeout(() => selecionarCepNoMapa(cep, true, "ranking"), 0); } },
        onHover: (ev, els) => {
          ev.native.target.style.cursor = els.length ? "pointer" : "default";
          const id = els.length ? rankingOrdem[els[0].index].cep : null;
          if (mapaValor && mapaValor.m.getSource("ceps") && id !== rankingHover) {
            if (rankingHover) mapaValor.m.setFeatureState({ source: "ceps", id: rankingHover }, { hover: false });
            if (id) mapaValor.m.setFeatureState({ source: "ceps", id }, { hover: true });
          }
          rankingHover = id;
        },
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${usd.format(c.raw)}/m² · ${num(rankingOrdem[c.dataIndex].vendas)} vendas` } } },
        scales: {
          x: { position: "top", ticks: { color: texto, callback: (v) => usd.format(v), maxTicksLimit: 4 }, grid: { color: linha } },
          y: { ticks: { color: texto, autoSkip: false, font: { size: 11 } }, grid: { display: false } },
        },
      },
    });
  }
  ouvir((origem) => {
    if (origem === "mapa-valor") return;
    if (estado.cep !== cepDestacado && (mapaValor || graficos.ranking)) destacarCep(estado.cep, {});
  });

  // ---------------------------------------------------------------- modelo
  const CAMPO_DA_VARIAVEL = {
    latitude: "latitude", longitude: "longitude", "area util": "area_util_m2", "padrao construtivo": "padrao_construtivo",
    "area do terreno": "area_terreno_m2", vista: "vista", "frente para a agua": "frente_agua", cep: "cep",
    "ano de construcao": "ano_construcao", banheiros: "banheiros", condicao: "condicao", conservacao: "condicao",
    "area do porao": "area_porao_m2", "ano da reforma": "ano_reforma", andares: "andares", quartos: "quartos",
    "area util dos vizinhos": "area_util_m2", "terreno dos vizinhos": "area_terreno_m2",
    lat: "latitude", long: "longitude", sqft_living: "area_util_m2", grade: "padrao_construtivo", zipcode: "cep", view: "vista",
    waterfront: "frente_agua", condition: "condicao", bathrooms: "banheiros", bedrooms: "quartos", floors: "andares",
  };
  const normalizar = (s) => String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();
  function irParaCampo(variavel) {
    const campo = CAMPO_DA_VARIAVEL[normalizar(variavel)];
    if (!campo) { toast(`"${variavel}" é calculada pela API a partir dos outros campos`); return; }
    irPara("avaliar", true);
    setTimeout(() => {
      const el = form.elements[campo];
      const alvo = (el instanceof RadioNodeList ? el[0] : el).closest(".campo");
      const det = alvo.closest("details");
      if (det) det.open = true;
      alvo.scrollIntoView({ behavior: "smooth", block: "center" });
      alvo.classList.remove("pulsar");
      void alvo.offsetWidth;
      alvo.classList.add("pulsar");
      const foco = el instanceof RadioNodeList ? [...el].find((r) => r.checked) || el[0] : el;
      setTimeout(() => foco.focus({ preventScroll: true }), 400);
      toast(`Campo "${variavel}" no formulário`);
    }, 200);
  }
  function blocoMetricas(titulo, m, extra, destaque) {
    if (!m) return "";
    const v = (k) => (m[k] === undefined ? "—" : k === "R2" ? num(m[k], 3) : k === "MAPE" ? pct(m[k]) : usd.format(m[k]));
    return `<div class="metrica-cartao${destaque ? " destaque" : ""}"><h3>${esc(titulo)} <span>${esc(extra || "")}</span></h3>
      <div class="metrica-linhas"><div><small>R²</small><b>${v("R2")}</b></div><div><small>MAPE</small><b>${v("MAPE")}</b></div>
      <div><small>MAE</small><b>${v("MAE")}</b></div><div><small>RMSE</small><b>${v("RMSE")}</b></div></div></div>`;
  }
  async function initModelo() {
    $("#btn-medir").addEventListener("click", medirEndpoints);
    medirEndpoints();
    const m = await carregarModelo();
    if (!m) { $("#metricas-cartoes").innerHTML = alertaHTML("Métricas indisponíveis", "Não foi possível ler /v1/modelo. Confirme que a API está no ar.", [], "aviso"); return; }
    const met = m.metricas || {};
    const teste = met.teste || {};
    const base = m.baseline && m.baseline.R2 === undefined ? (m.baseline.teste || m.baseline.validacao) : m.baseline;
    const div = m.divisao || {};
    $("#modelo-sub").textContent = `${m.algoritmo || "Modelo"} · versão ${m.versao || "—"}${m.treinado_em ? " · treinado em " + new Date(m.treinado_em).toLocaleDateString("pt-BR") : ""}. Métricas calculadas em dados que o modelo nunca viu durante o treino.`;
    if (div.teste) $("#b-teste-n").textContent = `${num(div.teste)} imóveis`;
    if (teste.R2 !== undefined) {
      const g = $("#gauge-r2");
      g.querySelector("strong").textContent = num(teste.R2, 3);
      requestAnimationFrame(() => { g.querySelector(".g-valor").style.strokeDashoffset = String(314.16 * (1 - Math.max(0, Math.min(1, teste.R2)))); });
      $("#gauge-texto").textContent = `O modelo explica ${pct(teste.R2, 1)} da variação de preço em ${num(div.teste || 0)} imóveis que nunca viu.${base && base.R2 !== undefined ? ` O baseline pela média fica em ${num(base.R2, 3)}.` : ""}`;
    }
    const ganho = base && base.RMSE ? 1 - teste.RMSE / base.RMSE : null;
    $("#metricas-teste").innerHTML = `<div><small>MAPE</small><b>${teste.MAPE !== undefined ? pct(teste.MAPE) : "—"}</b></div>
      <div><small>MAE</small><b>${teste.MAE !== undefined ? usd.format(teste.MAE) : "—"}</b></div>
      <div><small>RMSE</small><b>${teste.RMSE !== undefined ? usd.format(teste.RMSE) : "—"}</b></div>
      <div><small>RMSE vs. baseline</small><b class="pos">${ganho !== null ? "−" + num(ganho * 100, 1) + " %" : "—"}</b></div>`;
    $("#metricas-cartoes").innerHTML = blocoMetricas("Validação", met.validacao, div.validacao ? `${num(div.validacao)} imóveis` : "", false)
      + blocoMetricas("Teste (prova final)", met.teste, div.teste ? `${num(div.teste)} imóveis` : "", true)
      + blocoMetricas("Baseline pela média", base, "referência mínima", false);
    const total = (Number(div.treino) || 0) + (Number(div.validacao) || 0) + (Number(div.teste) || 0);
    if (total) {
      const partes = [["Treino", div.treino, "#4b22b5"], ["Validação", div.validacao, "#703bf7"], ["Teste", div.teste, "#9b7bf9"]];
      $("#modelo-divisao").innerHTML = partes.map(([n, q, c]) => `<div style="width:${(q / total) * 100}%;background:${c}" title="${n}: ${num(q)} imóveis">${n} ${num((q / total) * 100, 0)}%</div>`).join("");
    }
    if (m.faixa_erro && m.faixa_erro.p10 !== undefined) {
      $("#modelo-faixa").textContent = `Divisão por imóvel${div.criterio ? " (" + div.criterio + ")" : ""}. Faixa provável: 80 % dos imóveis de validação ficaram entre ${sinal(relativo(m.faixa_erro.p10))} e ${sinal(relativo(m.faixa_erro.p90))} do preço estimado.`;
    }
    desenharImportancia(m);
    carregarArtefato();
  }

  // Artefato registrado: arquivo .joblib em disco + cópia versionada (BLOB) no SQLite
  const artefatoEstado = { atual: null };
  const tamanhoLegivel = (b) => (b >= 1048576 ? num(b / 1048576, 2) + " MB" : num(b / 1024, 1) + " KB");
  async function carregarArtefato() {
    const caixa = $("#artefato-info"), btn = $("#btn-verificar-artefato");
    if (!caixa || !btn) return;
    if (!btn.dataset.ligado) {
      btn.dataset.ligado = "1";
      btn.addEventListener("click", verificarArtefato);
      caixa.addEventListener("click", async (ev) => {
        if (!ev.target.closest("[data-copiar-sha]") || !artefatoEstado.atual) return;
        try { await navigator.clipboard.writeText(artefatoEstado.atual.sha256); toast("SHA-256 copiado"); }
        catch (e) { toast("Não foi possível copiar automaticamente"); }
      });
    }
    const r = await api("/v1/modelo/artefatos");
    const lista = r.ok && Array.isArray(r.dados) ? r.dados : [];
    const a = lista.find((x) => x.ativo) || lista[0];
    artefatoEstado.atual = a || null;
    if (!a) { caixa.innerHTML = alertaHTML("Registro indisponível", "Não foi possível ler /v1/modelo/artefatos.", [], "aviso"); btn.disabled = true; return; }
    const sha = String(a.sha256 || "");
    caixa.innerHTML = `<div><small>Versão</small><b>${esc(a.versao)}</b> <span class="chip">${a.ativo ? "ativo" : "anterior"}</span></div>
      <div><small>SHA-256</small><div class="artefato-sha"><code title="${esc(sha)}">${esc(sha.slice(0, 12))}…${esc(sha.slice(-6))}</code><button type="button" class="btn-mini" data-copiar-sha>Copiar</button></div></div>
      <div><small>Tamanho</small><b>${tamanhoLegivel(Number(a.tamanho_bytes) || 0)}</b> <span class="nota">(${num(a.tamanho_bytes)} bytes · ${esc(a.formato)})</span></div>
      <div><small>Onde está</small><code>${esc(String(a.nome_arquivo || "").replace(/^modulo2_api\//, ""))}</code><br><span class="nota">SQLite · tabela <code>modelos</code>, registro #${esc(a.id)}</span></div>`
      + (lista.length > 1 ? `<p class="nota">${num(lista.length)} artefatos registrados no total.</p>` : "");
    btn.disabled = false;
  }
  async function verificarArtefato() {
    const btn = $("#btn-verificar-artefato"), saida = $("#artefato-verificacao"), a = artefatoEstado.atual;
    if (!a) return;
    btn.disabled = true;
    saida.className = "artefato-verificacao";
    saida.innerHTML = '<p class="nota"><span class="carregando"></span> Restaurando o BLOB e prevendo o imóvel de exemplo…</p>';
    const r = await api(`/v1/modelo/artefatos/${encodeURIComponent(a.id)}/verificar`, { timeout: 20000, headers: cabAdmin() });
    btn.disabled = false;
    const v = r.dados;
    if (!r.ok || !v) { saida.className = "artefato-verificacao falha"; saida.innerHTML = '<span class="selo-int">Não foi possível verificar</span>'; return; }
    const hashes = v.sha256_blob === v.sha256_disco && v.sha256_blob === v.sha256_carregado;
    saida.className = "artefato-verificacao " + (v.integro ? "ok" : "falha");
    saida.innerHTML = `<span class="selo-int">${v.integro ? "✓ Íntegro" : "✗ Divergente"}</span>
      <p class="nota">SHA-256 do BLOB ${hashes ? "igual" : "diferente"} ao do arquivo em disco e ao do artefato carregado na subida${v.erro ? " · " + esc(v.erro) : ""}.</p>
      <div class="artefato-prev"><div><small>Previsão do modelo restaurado do SQLite</small><b>${v.previsao_restaurada != null ? usd.format(v.previsao_restaurada) : "—"}</b></div>
      <div><small>Previsão do modelo em memória</small><b>${v.previsao_em_memoria != null ? usd.format(v.previsao_em_memoria) : "—"}</b></div></div>
      <p class="nota">Imóvel de exemplo: ${esc(v.imovel_exemplo.quartos)} quartos, ${num(v.imovel_exemplo.area_util_m2)} m², CEP ${esc(v.imovel_exemplo.cep)}. Verificado às ${new Date().toLocaleTimeString("pt-BR")}.</p>`;
  }
  const ENDPOINTS = [
    { metodo: "GET", rota: "/health" },
    { metodo: "GET", rota: "/v1/modelo" },
    { metodo: "GET", rota: "/v1/regioes" },
    { metodo: "POST", rota: "/v1/predict", corpo: () => ({ ...PADRAO }) },
    { metodo: "POST", rota: "/v1/predict/lote", corpo: () => ({ imoveis: cenarios({ ...PADRAO }).map((c) => c.dados) }) },
  ];
  async function medirEndpoints() {
    const caixa = $("#endpoints-status"), btn = $("#btn-medir");
    btn.disabled = true;
    if (!caixa.children.length) caixa.innerHTML = '<p class="nota"><span class="carregando"></span> Medindo…</p>';
    const res = [];
    for (const e of ENDPOINTS) {
      const r = await api(e.rota, { metodo: e.metodo, corpo: e.corpo ? e.corpo() : undefined, headers: e.corpo ? ORIGEM : undefined, timeout: 8000 });
      res.push({ ...e, status: r.status, ms: r.ms });
    }
    const maxMs = Math.max(20, ...res.map((x) => x.ms));
    caixa.innerHTML = res.map((x) => {
      const cls = x.status >= 200 && x.status < 300 ? "ok" : x.status >= 500 || x.status === 0 ? "erro" : "aviso";
      return `<div class="ep"><span class="metodo ${x.metodo.toLowerCase()}">${x.metodo}</span>
        <div class="ep-rota"><code>${x.rota}</code><span class="cod ${cls}">${x.status || "sem resposta"}</span></div>
        <div class="lat-barra"><i style="width:${Math.max(4, (x.ms / maxMs) * 100)}%;${cls !== "ok" ? "background:var(--bad)" : ""}"></i></div>
        <span class="lat">${num(x.ms, 0)} ms</span></div>`;
    }).join("") + `<p class="nota">Medido às ${new Date().toLocaleTimeString("pt-BR")}: ida e volta completas, incluindo a inferência.</p>`;
    btn.disabled = false;
  }
  function desenharImportancia(m) {
    const imp = (m.importancia || []).slice().sort((a, b) => b.importancia - a.importancia).slice(0, 12);
    if (!imp.length || !temGrafico()) return;
    if (graficos.imp) graficos.imp.destroy();
    const texto = cssVar("--muted"), linha = cssVar("--line"), cor = cssVar("--accent"), cor2 = cssVar("--accent-3");
    graficos.imp = new Chart($("#graf-imp"), {
      type: "bar",
      data: { labels: imp.map((x) => x.variavel), datasets: [{ data: imp.map((x) => x.importancia), backgroundColor: imp.map((x, i) => (i < 3 ? cor : cor2)), borderRadius: 8, maxBarThickness: 22 }] },
      options: {
        indexAxis: "y", responsive: true, maintainAspectRatio: false,
        onClick: (ev, els) => {
          if (els.length) { irParaCampo(imp[els[0].index].variavel); return; }
          // Clique no rótulo do eixo: descobre a barra pela posição vertical.
          const y = graficos.imp.scales.y, idx = y.getValueForPixel(ev.y);
          if (ev.x < y.right && idx >= 0 && idx < imp.length) irParaCampo(imp[Math.round(idx)].variavel);
        },
        onHover: (ev, els) => { const y = graficos.imp.scales.y; ev.native.target.style.cursor = els.length || ev.x < y.right ? "pointer" : "default"; },
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${num(c.raw, 4)} · clique para ir ao campo` } } },
        scales: { x: { ticks: { color: texto }, grid: { color: linha } }, y: { ticks: { color: texto }, grid: { display: false } } },
      },
    });
  }

  // ---------------------------------------------------------------- desenvolvedores
  function initDev() {
    const exemplo = { ...PADRAO };
    const json = JSON.stringify(exemplo, null, 2);
    const base = location.origin;
    $("#cod-json").textContent = json;
    $("#cod-curl").textContent = `# X-API-Key é opcional: com ela, o consumo conta no plano do cliente\ncurl -X POST "${base}/v1/predict" \\\n  -H "Content-Type: application/json" \\\n  -H "X-API-Key: SUA_CHAVE" \\\n  -d '${JSON.stringify(exemplo)}'\n\n# Salvar a avaliação e abrir o laudo\ncurl -X POST "${base}/v1/avaliacoes" \\\n  -H "Content-Type: application/json" \\\n  -d '{"titulo": "Casa de exemplo", "imovel": ${JSON.stringify(exemplo)}}'\n\n# Relatório de mercado por quartos\ncurl "${base}/v1/relatorios/mercado?dimensao=quartos"`;
    $("#cod-py").textContent = `import requests\n\nimovel = ${json.replace(/\btrue\b/g, "True").replace(/\bfalse\b/g, "False").replace(/\bnull\b/g, "None")}\n\ncabecalhos = {"X-API-Key": "SUA_CHAVE"}  # opcional: conta no plano do cliente\n\nresposta = requests.post("${base}/v1/predict", json=imovel, headers=cabecalhos, timeout=10)\nresposta.raise_for_status()\nprint(resposta.json()["preco_estimado_usd"])\n\n# Histórico de avaliações com filtros\nlista = requests.get("${base}/v1/avaliacoes", params={"cep": "98103", "limite": 20}, timeout=10).json()\nprint(lista["total"])`;
    $$("[data-copiar]").forEach((b) => b.addEventListener("click", async () => {
      const texto = $("#" + b.dataset.copiar).textContent;
      try { await navigator.clipboard.writeText(texto); toast("Copiado para a área de transferência"); }
      catch (e) { toast("Não foi possível copiar automaticamente"); }
    }));
    carregarMlflow();
  }
  // MLflow local: resumo lido pela API do banco do MLflow e atalhos para a interface dele
  async function carregarMlflow() {
    const r = await api("/v1/modelo/mlflow");
    const corpo = $("#mlflow-corpo"), status = $("#mlflow-status");
    if (!corpo) return;
    if (!r.ok || !r.dados) { corpo.innerHTML = avisoRota(r, "O resumo do MLflow"); status.textContent = "indisponível"; return; }
    const d = r.dados, m = d.metricas || {};
    $("#bt-mlflow-topo").href = d.ui_url;
    status.textContent = d.ui_no_ar ? "interface no ar" : "interface parada";
    status.className = d.ui_no_ar ? "chip ok" : "chip";
    const comandos = `<pre><code>${esc(d.comando_registrar)}\n${esc(d.comando_ui)}</code></pre>`;
    if (!d.disponivel) {
      corpo.innerHTML = `<p class="nota">Nenhum modelo registrado ainda. Na raiz do projeto, com o <code>requirements.txt</code> instalado:</p>${comandos}`;
      return;
    }
    const metrica = (k, rotulo, fmt) => (m[k] != null ? `<div class="res-item"><small>${rotulo}</small><b>${fmt(m[k])}</b></div>` : "");
    corpo.innerHTML = `
      <p>Modelo <b>${esc(d.modelo)}</b> · versão <b>${d.versao}</b> com o alias <span class="chip">@${esc(d.alias)}</span> · run <code>${esc(d.run_nome || d.run_id)}</code>${d.registrado_em ? ` · registrado em ${new Date(d.registrado_em).toLocaleString("pt-BR")}` : ""}</p>
      <div class="res-grade">
        ${metrica("teste_R2", "R² no teste", (v) => num(v, 4))}
        ${metrica("teste_MAE", "MAE no teste", (v) => usd.format(v))}
        ${metrica("teste_RMSE", "RMSE no teste", (v) => usd.format(v))}
        ${metrica("teste_MAPE", "MAPE no teste", (v) => pct(v))}
      </div>
      <div class="acoes">
        <a class="btn btn-pri" href="${esc(d.link_run)}" target="_blank" rel="noopener">Abrir o run no MLflow</a>
        <a class="btn btn-borda" href="${esc(d.link_modelo)}" target="_blank" rel="noopener">Ver no Model Registry</a>
        <a class="btn btn-borda" href="${esc(d.ui_url)}" target="_blank" rel="noopener">Interface do MLflow</a>
      </div>
      ${d.ui_no_ar ? "" : `<p class="nota">A interface do MLflow está parada. Para abrir os atalhos, suba-a na raiz do projeto:</p>${comandos}`}
      <p class="nota">A API serve o <code>.joblib</code> carregado uma vez na subida; o MLflow rastreia e versiona o mesmo artefato (métricas de <code>metricas_v2.json</code>, assinatura de entrada e sha256).</p>`;
  }

  // ---------------------------------------------------------------- utilidades da aplicação
  /** Lê o primeiro campo preenchido entre vários nomes possíveis (aceita caminhos "a.b"). */
  const campo = (o, ...ks) => {
    for (const k of ks) {
      const v = k.split(".").reduce((a, p) => (a == null ? a : a[p]), o);
      if (v !== undefined && v !== null && v !== "") return v;
    }
    return null;
  };
  const lista = (d, ...ks) => (Array.isArray(d) ? d : (d && ks.map((k) => d[k]).find(Array.isArray)) || []);
  const dataHora = (v) => { if (!v) return "—"; const d = new Date(v); return isNaN(d) ? esc(v) : d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }); };
  const qs = (o) => Object.entries(o).filter(([, v]) => v !== "" && v !== null && v !== undefined).map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&");
  const visivel = (view) => viewAtual === view && !document.hidden;
  /** Mensagem amigável para rota ainda não publicada ou API fora do ar. */
  function avisoRota(r, modulo) {
    if (r.status === 404) return alertaHTML(`${modulo} ainda não está ativo`, "Esta versão da API ainda não publicou a rota. A tela volta a funcionar sozinha assim que ela estiver no ar.", [], "aviso");
    if (r.status === 0) return alertaHTML("API indisponível", "Não foi possível falar com o servidor. Confirme que a API está rodando e tente de novo.", [], "aviso");
    if (r.status === 401 || r.status === 403) return alertaHTML(`Acesso negado (${r.status})`, (r.dados && r.dados.mensagem) || "Informe um token de administrador válido em Administrador, no cabeçalho.", [], "aviso");
    return alertaHTML(`Erro ${r.status}`, mensagemErro(r), detalhesErro(r.dados), r.status >= 500 ? "" : "aviso");
  }
  function baixar(url) {
    const a = document.createElement("a");
    a.href = url;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }
  function desenharGrafico(chave, canvas, config) {
    if (!temGrafico()) return;
    if (graficos[chave]) graficos[chave].destroy();
    graficos[chave] = new Chart(canvas, config);
  }
  /** Converte {rótulo: valor} ou [{...}] em pares [rótulo, valor]. */
  function pares(d, rotulos, valores) {
    if (!d) return [];
    if (Array.isArray(d)) return d.map((x) => [String(campo(x, ...rotulos) ?? "—"), Number(campo(x, ...valores)) || 0]);
    return Object.entries(d).map(([k, v]) => [k, Number(typeof v === "object" ? campo(v, ...valores) : v) || 0]);
  }
  const eixos = () => ({ texto: cssVar("--muted"), linha: cssVar("--line") });

  // ---------------------------------------------------------------- menu lateral, busca e modais
  function fecharMenu() {
    $("#app").classList.remove("menu-aberto");
    $("#veu").hidden = true;
    $("#btn-menu").setAttribute("aria-expanded", "false");
  }
  $("#btn-menu").addEventListener("click", () => {
    const abrir = !$("#app").classList.contains("menu-aberto");
    $("#app").classList.toggle("menu-aberto", abrir);
    $("#veu").hidden = !abrir;
    $("#btn-menu").setAttribute("aria-expanded", String(abrir));
  });
  $("#veu").addEventListener("click", fecharMenu);
  const TELAS = $$(".menu a[data-nav], .lateral-rodape a[data-nav]").map((a) => ({ nome: a.textContent.trim(), view: a.dataset.nav }));
  $("#busca-telas").innerHTML = TELAS.map((t) => `<option value="${esc(t.nome)}">`).join("");
  $("#busca").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const q = $("#busca-q").value.trim();
    if (!q) return;
    const tela = TELAS.find((t) => normalizar(t.nome) === normalizar(q)) || TELAS.find((t) => normalizar(t.nome).startsWith(normalizar(q)));
    if (tela) { irPara(tela.view); $("#busca-q").value = ""; return; }
    const f = $("#filtros-av");
    f.reset();
    if (/^\d{5}$/.test(q)) { garantirOpcao(f.elements.cep, q); f.elements.cep.value = q; } else f.elements.busca.value = q;
    filtrosAv.pagina = 1;
    irPara("avaliacoes");
    if (inicializadas.has("avaliacoes")) carregarAvaliacoes();
  });
  function abrirModal(id) { const m = $("#" + id); m.hidden = false; const f = m.querySelector("input"); if (f) setTimeout(() => f.focus(), 30); }
  function fecharModal(m) { m.hidden = true; if (m.id === "modal") $("#modal-iframe").srcdoc = ""; if (m.id === "modal-cliente") limparGestao(); }
  $$(".modal").forEach((m) => m.addEventListener("click", (ev) => { if (ev.target === m || ev.target.closest("[data-fechar-modal]") || ev.target.id === "modal-fechar") fecharModal(m); }));
  // Esc fecha só a janela de cima (o e-mail aberto de dentro da gestão do cliente fecha antes dela)
  document.addEventListener("keydown", (ev) => { if (ev.key !== "Escape") return; const abertos = $$(".modal:not([hidden])"); if (abertos.length) fecharModal(abertos[abertos.length - 1]); });
  document.addEventListener("click", (ev) => { if (ev.target.closest("[data-abrir-admin]")) abrirModal("modal-admin"); });
  function garantirOpcao(sel, v) { if (![...sel.options].some((o) => o.value === String(v))) sel.add(new Option(String(v), String(v))); }

  // ---------------------------------------------------------------- administrador (token só na sessão)
  const CHAVE_ADMIN = "ai-admin";
  function tokenAdmin() { try { return sessionStorage.getItem(CHAVE_ADMIN) || ""; } catch (e) { return memoriaAdmin; } }
  let memoriaAdmin = "";
  function gravarToken(t) { memoriaAdmin = t; try { if (t) sessionStorage.setItem(CHAVE_ADMIN, t); else sessionStorage.removeItem(CHAVE_ADMIN); } catch (e) {} atualizarAdmin(); }
  // Acesso com senha + 2FA: quando o servidor exige, a sessão substitui o token no cabeçalho
  const CHAVE_SESSAO = "ai-sessao-2fa";
  const acesso = { exige: false };
  let memoriaSessao = "";
  // localStorage (e não sessionStorage): a sessão vale nas outras abas do portal, como a da Visão 3D; expira no servidor em 8 h
  function sessaoAdmin() { try { return localStorage.getItem(CHAVE_SESSAO) || ""; } catch (e) { return memoriaSessao; } }
  function gravarSessao(s) { memoriaSessao = s; try { if (s) localStorage.setItem(CHAVE_SESSAO, s); else localStorage.removeItem(CHAVE_SESSAO); } catch (e) {} atualizarAdmin(); }
  const cabAdmin = () => (sessaoAdmin() ? { "X-Admin-Sessao": sessaoAdmin() } : tokenAdmin() ? { "X-Admin-Token": tokenAdmin() } : {});
  // Console liberado: sessão 2FA quando o servidor exige; senão, o token de administrador
  const temAdmin = () => (acesso.exige ? !!sessaoAdmin() : !!tokenAdmin());
  function pedirAdmin() { if (acesso.exige) mostrarEntrada("Entre com a senha e o código do autenticador.", "info"); else abrirModal("modal-admin"); }
  function atualizarAdmin() {
    const campoCodigo = $("#campo-senha-conta");
    if (campoCodigo) campoCodigo.hidden = !acesso.exige;
    if (acesso.exige) {
      const tem2 = !!sessaoAdmin();
      $("#admin-rotulo").textContent = tem2 ? "administrador · sessão ativa" : "administrador · sem sessão";
      $$(".btn-admin").forEach((b) => b.classList.toggle("ativo", tem2));
      $("#admin-token").hidden = true;
      $("#admin-2fa").hidden = false;
      const chip2 = $("#adm-estado");
      chip2.textContent = tem2 ? "Sessão 2FA ativa" : "Sem sessão";
      chip2.className = "chip " + (tem2 ? "ok" : "ruim");
      return;
    }
    const tem = !!tokenAdmin();
    $("#admin-rotulo").textContent = tem ? "administrador · token ativo" : "administrador · sem token";
    $$(".btn-admin").forEach((b) => b.classList.toggle("ativo", tem));
    const chip = $("#adm-estado");
    chip.textContent = tem ? "Token informado" : "Sem token";
    chip.className = "chip " + (tem ? "ok" : "ruim");
    $("#adm-token").value = "";
    $("#adm-token").placeholder = tem ? "Token guardado nesta sessão (oculto)" : "Cole o token de administrador";
  }
  $("#adm-usar").addEventListener("click", () => {
    const t = $("#adm-token").value.trim();
    if (!t) { toast("Cole o token de administrador"); return; }
    gravarToken(t);
    fecharModal($("#modal-admin"));
    toast("Token de administrador ativo nesta sessão");
    if (inicializadas.has("comercial")) carregarClientes();
  });
  $("#adm-token").addEventListener("keydown", (ev) => { if (ev.key === "Enter") $("#adm-usar").click(); });
  $("#adm-esquecer").addEventListener("click", () => { gravarToken(""); toast("Token esquecido"); if (inicializadas.has("comercial")) carregarClientes(); });

  // ---------------------------------------------------------------- entrada com senha e segundo fator
  function mostrarEntrada(msg, tipo) {
    $("#tela-entrar").hidden = false;
    $("#app").setAttribute("aria-hidden", "true");
    const erro = $("#entrar-erro");
    erro.hidden = !msg;
    erro.classList.toggle("info", tipo === "info");
    erro.textContent = msg || "";
    setTimeout(() => $("#en-senha").focus(), 30);
  }
  function esconderEntrada() {
    $("#tela-entrar").hidden = true;
    $("#app").removeAttribute("aria-hidden");
    $("#en-senha").value = "";
    $("#en-codigo").value = "";
  }
  $("#en-codigo").addEventListener("input", (ev) => { ev.target.value = ev.target.value.replace(/\D/g, "").slice(0, 6); });
  $("#form-entrar").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const senha = $("#en-senha").value, codigo = $("#en-codigo").value.trim();
    if (!senha || !/^\d{6}$/.test(codigo)) { mostrarEntrada("Informe a senha e o código de 6 dígitos do autenticador."); return; }
    const btn = $("#en-entrar");
    btn.disabled = true;
    btn.textContent = "Conferindo…";
    const r = await api("/v1/acesso/entrar", { metodo: "POST", corpo: { senha, codigo } });
    btn.disabled = false;
    btn.textContent = "Entrar";
    if (r.ok && r.dados && r.dados.sessao) {
      gravarSessao(r.dados.sessao);
      if (inicializadas.has("banco") && window.TelaBanco) window.TelaBanco.atualizar();
      esconderEntrada();
      toast("Acesso liberado por 8 horas");
      if (inicializadas.has("comercial")) carregarClientes();
      return;
    }
    $("#en-codigo").value = "";
    mostrarEntrada(r.status === 0 ? "API indisponível. Confira se o servidor está no ar." : (r.dados && r.dados.mensagem) || "Não foi possível entrar.");
  });
  $("#adm-sair").addEventListener("click", async () => {
    await api("/v1/acesso/sair", { metodo: "POST", headers: cabAdmin() });
    gravarSessao("");
    fecharModal($("#modal-admin"));
    mostrarEntrada("Sessão encerrada.", "info");
  });
  // Sessão que expira no servidor (8 h ou reinício da API) volta para a tela de entrada
  function conferirSessao(r) {
    if (acesso.exige && r && r.status === 401 && sessaoAdmin() && !(r.dados && r.dados.erro === "acesso_negado")) { gravarSessao(""); mostrarEntrada("A sessão expirou. Entre de novo.", "info"); }
    return r;
  }
  async function iniciarAcesso() {
    // Entrada de contingência (comando "avaliador direto"): a sessão chega no fragmento, que não vai ao servidor
    const direta = /^#entrar=([\w-]+)$/.exec(location.hash);
    if (direta) { gravarSessao(direta[1]); history.replaceState(null, "", location.pathname + "#painel"); }
    const r = await api("/v1/acesso/estado");
    acesso.exige = !!(r.ok && r.dados && r.dados.exige_2fa);
    atualizarAdmin();
    if (acesso.exige && !sessaoAdmin()) mostrarEntrada();
  }

  // ---------------------------------------------------------------- painel
  async function carregarResumo() {
    const r = await api("/v1/relatorios/resumo");
    return r.ok && r.dados ? { ok: true, d: r.dados } : { ok: false, r };
  }
  function graficoDia(chave, canvas, porDia) {
    const pp = pares(porDia, ["dia", "data", "date"], ["total", "quantidade", "predicoes", "n"]);
    const { texto, linha } = eixos();
    desenharGrafico(chave, canvas, {
      type: "bar",
      data: { labels: pp.map((x) => x[0]), datasets: [{ data: pp.map((x) => x[1]), backgroundColor: cssVar("--accent"), borderRadius: 6, maxBarThickness: 34 }] },
      options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { display: false } },
        scales: { x: { ticks: { color: texto, maxRotation: 0, autoSkip: true }, grid: { display: false } }, y: { beginAtZero: true, ticks: { color: texto, precision: 0 }, grid: { color: linha } } } },
    });
  }
  function itemUltima(it) {
    const preco = campo(it, "preco_estimado_usd", "resultado.preco_estimado_usd");
    return `<button type="button" class="item-ultima" data-avaliacao="${esc(campo(it, "id"))}"><b>${esc(campo(it, "titulo") || "Avaliação #" + campo(it, "id"))}</b><strong>${preco != null ? usd.format(preco) : "—"}</strong>
      <small>${esc(campo(it, "cidade") || "")}${campo(it, "cep") ? " · CEP " + esc(campo(it, "cep", "imovel.cep")) : ""} · <span class="origem ${esc(campo(it, "origem") || "")}">${esc(campo(it, "origem") || "—")}</span></small><small>${dataHora(campo(it, "criado_em", "criada_em"))}</small></button>`;
  }
  document.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-avaliacao]");
    if (!b) return;
    abrirAvaliacao(b.dataset.avaliacao);
  });
  async function atualizarPainel() {
    const [res, av, rs] = await Promise.all([carregarResumo(), api("/v1/avaliacoes?" + qs({ limite: 6, pagina: 1, ordenacao: "recentes" })), carregarRegioes()]);
    const d = res.ok ? res.d : {};
    const set = (id, v) => { $(id).textContent = v; };
    const totalAv = av.ok && av.dados ? campo(av.dados, "total") : campo(d, "avaliacoes", "total_avaliacoes");
    set("#pn-avaliacoes", totalAv != null ? num(totalAv) : "—");
    const vendas = campo(d, "vendas_historicas", "total_vendas") ?? (rs ? rs.reduce((s, g) => s + (Number(g.vendas) || 0), 0) : null);
    set("#pn-vendas", vendas != null ? num(vendas) : "—");
    set("#pn-clientes", campo(d, "clientes") != null ? num(d.clientes) : "—");
    set("#pn-chaves", campo(d, "chaves_ativas") != null ? num(d.chaves_ativas) : "—");
    set("#pn-hoje", campo(d, "predicoes_hoje") != null ? num(d.predicoes_hoje) : "—");
    set("#pn-lat", campo(d, "latencia_mediana_ms") != null ? `${num(d.latencia_mediana_ms, 1)} ms` : "—");
    $("#pn-aviso").innerHTML = res.ok ? "" : avisoRota(res.r, "O banco de relatórios");
    if (res.ok) graficoDia("painel", $("#graf-painel"), d.por_dia);
    $("#pn-atualizado").textContent = "atualizado às " + new Date().toLocaleTimeString("pt-BR");
    const itens = av.ok ? lista(av.dados, "itens", "avaliacoes") : [];
    $("#pn-ultimas").innerHTML = av.ok ? (itens.length ? itens.map(itemUltima).join("") : '<p class="nota">Nenhuma avaliação salva ainda. Use <b>Nova avaliação</b> e <b>Salvar e gerar laudo</b>.</p>') : avisoRota(av, "O histórico de avaliações");
  }
  function initPainel() {
    atualizarPainel();
    setInterval(() => { if (visivel("painel")) atualizarPainel(); }, 15000);
  }

  // ---------------------------------------------------------------- salvar avaliação e laudo
  $("#btn-salvar").addEventListener("click", () => {
    const v = estado.imovel;
    $("#salvar-resumo").textContent = `${num(v.area_util_m2)} m² · ${v.quartos} quartos · ${num(v.banheiros, v.banheiros % 1 ? 2 : 0)} banheiros · CEP ${v.cep}${resultadoAtual() ? " · " + usd.format(estado.ultimoResultado.dados.preco_estimado_usd) : ""}`;
    $("#salvar-erro").innerHTML = "";
    const t = $("#sv-titulo");
    if (!t.value) t.value = `Imóvel no CEP ${v.cep} · ${num(v.area_util_m2)} m²`;
    abrirModal("modal-salvar");
  });
  $("#form-salvar").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const f = ev.target.elements, titulo = f.titulo.value.trim();
    $$(".erro", ev.target).forEach((e) => { e.textContent = ""; });
    if (!titulo) { $('.erro[data-erro="titulo"]', ev.target).textContent = "Informe um título"; return; }
    const btn = $("#sv-confirmar");
    btn.disabled = true;
    btn.innerHTML = '<span class="carregando"></span> Salvando…';
    const corpo = { titulo, responsavel: f.responsavel.value.trim() || null, imovel: { ...estado.imovel } };
    const r = await api("/v1/avaliacoes", { metodo: "POST", corpo, headers: ORIGEM });
    btn.disabled = false;
    btn.textContent = "Salvar avaliação";
    if (!r.ok || !r.dados) {
      const det = detalhesErro(r.dados);
      det.forEach((d) => { const e = $(`.erro[data-erro="${d.campo}"]`, ev.target); if (e) e.textContent = d.mensagem; });
      $("#salvar-erro").innerHTML = r.status === 404 ? avisoRota(r, "O registro de avaliações") : alertaHTML(r.status ? tituloErro(r.status) : "API indisponível", mensagemErro(r), det, "aviso");
      return;
    }
    fecharModal($("#modal-salvar"));
    const id = campo(r.dados, "id", "avaliacao_id", "avaliacao.id");
    const res = campo(r.dados, "resultado") || r.dados;
    if (campo(res, "preco_estimado_usd") != null) {
      estado.ultimoResultado = { dados: { ...res, faixa_provavel_usd: campo(res, "faixa_provavel_usd") || estado.ultimoResultado?.dados?.faixa_provavel_usd }, payload: { ...estado.imovel } };
      if (!$("#resultado .res-preco")) mostrarResultado(estado.ultimoResultado.dados, estado.ultimoResultado.payload);
    }
    if (!$("#resultado .res-preco") && !resultadoAtual()) await avaliarEstado(false);
    const caixa = document.createElement("div");
    caixa.className = "salvo";
    caixa.innerHTML = `<b>✓ Avaliação #${esc(id)} salva</b> · ${esc(titulo)}<div class="laudo-acoes"><a class="btn btn-pri" href="/v1/avaliacoes/${encodeURIComponent(id)}/laudo" target="_blank" rel="noopener">Abrir laudo</a><button type="button" class="btn btn-borda" data-avaliacao="${esc(id)}">Ver na lista</button></div>`;
    $$("#resultado .salvo").forEach((x) => x.remove());
    $("#resultado").appendChild(caixa);
    $("#sv-titulo").value = "";
    toast(`Avaliação #${id} salva`);
  });

  // ---------------------------------------------------------------- avaliações (histórico)
  const filtrosAv = { pagina: 1, limite: 15, selecionada: null };
  let ultimasAv = [];
  function paramsAv() {
    const f = $("#filtros-av").elements;
    return { busca: f.busca.value.trim(), cidade: f.cidade.value, cep: f.cep.value, quartos: f.quartos.value, faixa_preco: f.faixa_preco.value, origem: f.origem.value, preco_min: f.preco_min.value, preco_max: f.preco_max.value, ordenacao: f.ordenacao.value };
  }
  let opcoesPreenchidas = null;
  function preencherCidades() {
    if (opcoesPreenchidas) return opcoesPreenchidas;
    opcoesPreenchidas = Promise.all(["cidade", "faixa_preco"].map((dim) => api("/v1/relatorios/mercado?dimensao=" + dim))).then(([rc, rf]) => {
      const cidades = rc.ok ? lista(rc.dados, "linhas").map((l) => String(campo(l, "grupo"))).filter(Boolean).sort((a, b) => a.localeCompare(b)) : [];
      ["#fa-cidade", "#fm-cidade"].forEach((sel) => cidades.forEach((c) => garantirOpcao($(sel), c)));
      const faixas = rf.ok ? lista(rf.dados, "linhas").map((l) => String(campo(l, "grupo"))).filter(Boolean) : [];
      ["#fa-faixa", "#fm-faixa"].forEach((sel) => faixas.forEach((c) => garantirOpcao($(sel), c)));
      if (!rc.ok) opcoesPreenchidas = null;
    });
    return opcoesPreenchidas;
  }
  async function carregarAvaliacoes() {
    const caixa = $("#tabela-avaliacoes");
    if (!caixa.children.length) caixa.innerHTML = '<p class="nota"><span class="carregando"></span> Carregando…</p>';
    const r = await api("/v1/avaliacoes?" + qs({ ...paramsAv(), pagina: filtrosAv.pagina, limite: filtrosAv.limite }));
    if (!r.ok || !r.dados) { caixa.innerHTML = avisoRota(r, "O histórico de avaliações"); $("#paginacao").innerHTML = ""; $("#fa-total").textContent = "—"; return; }
    const d = r.dados, itens = lista(d, "itens", "avaliacoes");
    ultimasAv = itens;
    const total = Number(campo(d, "total")) || itens.length, limite = Number(campo(d, "limite")) || filtrosAv.limite, pagina = Number(campo(d, "pagina")) || filtrosAv.pagina;
    const paginas = Math.max(1, Math.ceil(total / limite));
    $("#fa-total").textContent = `${num(total)} ${total === 1 ? "avaliação encontrada" : "avaliações encontradas"}`;
    caixa.innerHTML = itens.length ? `<table class="tabela"><thead><tr><th>#</th><th>Título</th><th>Origem</th><th>Local</th><th class="num">Área</th><th class="num">Quartos</th><th class="num">Valor estimado</th><th>Data</th></tr></thead><tbody>${itens.map((it) => {
      const id = campo(it, "id");
      const preco = campo(it, "preco_estimado_usd", "resultado.preco_estimado_usd");
      return `<tr class="clicavel${String(id) === String(filtrosAv.selecionada) ? " selecionada" : ""}" data-linha="${esc(id)}" tabindex="0">
        <td>${esc(id)}</td><td>${esc(campo(it, "titulo") || "—")}</td><td><span class="origem ${esc(campo(it, "origem") || "")}">${esc(campo(it, "origem") || "—")}</span></td>
        <td>${esc(campo(it, "cidade") || "")}${campo(it, "cep", "imovel.cep") ? " · " + esc(campo(it, "cep", "imovel.cep")) : ""}</td>
        <td class="num">${campo(it, "area_util_m2", "imovel.area_util_m2") != null ? num(campo(it, "area_util_m2", "imovel.area_util_m2")) + " m²" : "—"}</td>
        <td class="num">${esc(campo(it, "quartos", "imovel.quartos") ?? "—")}</td>
        <td class="num"><b>${preco != null ? usd.format(preco) : "—"}</b></td><td>${dataHora(campo(it, "criado_em", "criada_em"))}</td></tr>`;
    }).join("")}</tbody></table>` : '<div class="vazio">Nenhuma avaliação com estes filtros.</div>';
    $("#paginacao").innerHTML = `<span class="nota">Página ${pagina} de ${paginas}</span><div><button type="button" class="btn-mini" data-pag="-1" ${pagina <= 1 ? "disabled" : ""}>← Anterior</button><button type="button" class="btn-mini" data-pag="1" ${pagina >= paginas ? "disabled" : ""}>Próxima →</button></div>`;
  }
  function itemDaLista(id) { return ultimasAv.find((x) => String(campo(x, "id")) === String(id)); }
  async function abrirAvaliacao(id) {
    filtrosAv.selecionada = id;
    if (viewAtual !== "avaliacoes") irPara("avaliacoes");
    if (!inicializadas.has("avaliacoes")) return; // o init carrega a lista e mostra o detalhe
    if (!itemDaLista(id)) await carregarAvaliacoes();
    $$("#tabela-avaliacoes tr[data-linha]").forEach((tr) => tr.classList.toggle("selecionada", tr.dataset.linha === String(id)));
    let it = itemDaLista(id);
    const r = await api(`/v1/avaliacoes/${encodeURIComponent(id)}`);
    if (r.ok && r.dados) it = { ...(it || {}), ...r.dados };
    if (!it) { $("#det-corpo").innerHTML = avisoRota(r, "O detalhe da avaliação"); return; }
    mostrarDetalhe(it);
  }
  let mapaDetalhe = null, marcadorDetalhe = null;
  function mostrarDetalhe(it) {
    const id = campo(it, "id");
    const preco = Number(campo(it, "preco_estimado_usd", "resultado.preco_estimado_usd"));
    const min = Number(campo(it, "faixa_min", "faixa_min_usd", "faixa_provavel_usd.minimo") ?? NaN);
    const max = Number(campo(it, "faixa_max", "faixa_max_usd", "faixa_provavel_usd.maximo") ?? NaN);
    const real = campo(it, "preco_real_usd", "preco_venda_usd", "preco_real");
    let erro = campo(it, "erro_pct", "erro_percentual");
    if (erro == null && real) erro = (preco / Number(real) - 1) * 100;
    const lat = Number(campo(it, "latitude", "imovel.latitude")), lon = Number(campo(it, "longitude", "imovel.longitude"));
    const pos = max > min ? Math.min(100, Math.max(0, ((preco - min) / (max - min)) * 100)) : 50;
    $("#det-topo").innerHTML = `<div class="res-topo"><div><h3 class="res-titulo">${esc(campo(it, "titulo") || "Avaliação #" + id)}</h3><p class="res-local">#${esc(id)} · ${dataHora(campo(it, "criado_em", "criada_em"))}${campo(it, "responsavel") ? " · " + esc(it.responsavel) : ""}</p></div><span class="origem ${esc(campo(it, "origem") || "")}">${esc(campo(it, "origem") || "—")}</span></div>`;
    $("#det-mapa-area").hidden = !(Number.isFinite(lat) && Number.isFinite(lon) && temMapa());
    if (!$("#det-mapa-area").hidden) {
      if (!mapaDetalhe) {
        mapaDetalhe = criarMapa("detalhe", [lon, lat], 13.5);
        const el = document.createElement("div");
        el.className = "marcador-imovel";
        el.style.zIndex = "5";
        marcadorDetalhe = new maplibregl.Marker({ element: el }).setLngLat([lon, lat]).addTo(mapaDetalhe.m);
        montarControles3D(mapaDetalhe, $("#det-mapa-area"), () => mapaDetalhe.centro);
      } else {
        desligar3D(mapaDetalhe, true);
        mapaDetalhe.m.jumpTo({ center: [lon, lat], zoom: 13.5 });
        marcadorDetalhe.setLngLat([lon, lat]);
      }
      mapaDetalhe.centro = [lon, lat];
      mapaDetalhe.valor = { v: preco, min, max };
      setTimeout(() => mapaDetalhe.m.resize(), 30);
    }
    $("#det-corpo").innerHTML = `
      <div class="res-rotulo">Valor estimado</div>
      <div class="res-preco"><small>US$</small>${Number.isFinite(preco) ? num(preco) : "—"}</div>
      ${Number.isFinite(min) && Number.isFinite(max) ? `<div class="faixa-barra"><div class="faixa-ponto" style="left:${pos}%"></div></div><div class="faixa-valores"><span>mín. <b>${usd.format(min)}</b></span><span>máx. <b>${usd.format(max)}</b></span></div>` : ""}
      <div class="res-grade">
        <div class="res-item"><small>Local</small><b>${esc(campo(it, "cidade") || "—")}</b><small>CEP ${esc(campo(it, "cep", "imovel.cep") || "—")}</small></div>
        <div class="res-item"><small>Imóvel</small><b>${campo(it, "area_util_m2", "imovel.area_util_m2") != null ? num(campo(it, "area_util_m2", "imovel.area_util_m2")) + " m²" : "—"}</b><small>${esc(campo(it, "quartos", "imovel.quartos") ?? "—")} quartos</small></div>
        <div class="res-item"><small>${real ? "Preço real" : "US$/m²"}</small><b>${real ? usd.format(real) : campo(it, "preco_m2_usd", "preco_por_m2_usd") ? usd.format(campo(it, "preco_m2_usd", "preco_por_m2_usd")) : "—"}</b>${erro != null ? `<small class="${Math.abs(erro) <= 12 ? "pos" : "neg"}">erro ${sinal(Number(erro))}</small>` : ""}</div>
      </div>
      <div class="laudo-acoes"><a class="btn btn-pri" href="/v1/avaliacoes/${encodeURIComponent(id)}/laudo" target="_blank" rel="noopener">Laudo</a><button type="button" class="btn btn-borda" data-reavaliar="${esc(id)}">Abrir na avaliação</button></div>`;
  }
  async function initAvaliacoes() {
    const aside = $("#detalhe-avaliacao");
    aside.innerHTML = `<div id="det-topo"><div class="vazio"><span class="ic-grande">☰</span><p>Clique numa avaliação para ver o detalhe, o mapa e o laudo.</p></div></div>
      <div class="mapa-mini" id="det-mapa-area" hidden><div id="mapa-detalhe" class="mapa"></div></div><div id="det-corpo"></div>`;
    const f = $("#filtros-av");
    let t = null;
    const recarregar = () => { clearTimeout(t); t = setTimeout(() => { filtrosAv.pagina = 1; carregarAvaliacoes(); }, 300); };
    f.addEventListener("input", recarregar);
    f.addEventListener("change", recarregar);
    f.addEventListener("reset", () => setTimeout(recarregar, 0));
    f.addEventListener("submit", (ev) => ev.preventDefault());
    $("#paginacao").addEventListener("click", (ev) => { const b = ev.target.closest("[data-pag]"); if (!b) return; filtrosAv.pagina = Math.max(1, filtrosAv.pagina + Number(b.dataset.pag)); carregarAvaliacoes(); });
    $("#tabela-avaliacoes").addEventListener("click", (ev) => { const tr = ev.target.closest("tr[data-linha]"); if (tr) abrirAvaliacao(tr.dataset.linha); });
    $("#tabela-avaliacoes").addEventListener("keydown", (ev) => { const tr = ev.target.closest("tr[data-linha]"); if (tr && ev.key === "Enter") abrirAvaliacao(tr.dataset.linha); });
    $$("[data-exportar]").forEach((b) => b.addEventListener("click", async () => {
      const url = "/v1/avaliacoes/exportar?" + qs({ formato: b.dataset.exportar, ...paramsAv() });
      const r = await api(url, { texto: true });
      if (!r.ok) { toast(r.status === 404 ? "Exportação ainda não está ativa nesta API" : `Não foi possível exportar (${r.status})`); return; }
      baixar(url);
    }));
    document.addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-reavaliar]");
      if (!b) return;
      const it = itemDaLista(b.dataset.reavaliar);
      const im = it && (campo(it, "imovel") || it);
      if (!im) return;
      const parcial = {};
      Object.keys(PADRAO).forEach((k) => { if (im[k] !== undefined && im[k] !== null) parcial[k] = im[k]; else if (k === "ano_reforma") parcial[k] = null; });
      parcial.cep = String(parcial.cep || estado.imovel.cep);
      estado.cenarioAplicado = null;
      atualizarEstado(parcial, "historico");
      irPara("avaliar");
      setTimeout(() => { avaliarEstado(true); if (mapaAvaliar) mapaAvaliar.m.jumpTo({ center: [estado.imovel.longitude, estado.imovel.latitude], zoom: 12.5 }); }, 300);
    });
    const rs = await carregarRegioes();
    if (rs) rs.slice().sort((a, b) => a.cep.localeCompare(b.cep)).forEach((g) => garantirOpcao($("#fa-cep"), g.cep));
    preencherCidades();
    await carregarAvaliacoes();
    if (filtrosAv.selecionada) abrirAvaliacao(filtrosAv.selecionada);
  }

  // ---------------------------------------------------------------- relatórios de mercado
  const mercado = { dim: "quartos", linhas: [], ordem: null, dir: -1 };
  const NOMES_DIM = { quartos: "quartos", cidade: "cidade/bairro", cep: "CEP", faixa_preco: "faixa de preço", padrao: "padrão construtivo", ano_venda: "ano da venda" };
  function paramsMercado() {
    const f = $("#filtros-mercado").elements;
    return { dimensao: mercado.dim, cidade: f.cidade.value, quartos: f.quartos.value, faixa_preco: f.faixa_preco.value };
  }
  async function carregarMercado() {
    $("#mercado-titulo").textContent = `Preço por ${NOMES_DIM[mercado.dim] || mercado.dim}`;
    const r = await api("/v1/relatorios/mercado?" + qs(paramsMercado()));
    if (!r.ok || !r.dados) { $("#mercado-aviso").innerHTML = avisoRota(r, "O relatório de mercado"); mercado.linhas = []; $("#tabela-mercado").innerHTML = ""; if (graficos.mercado) { graficos.mercado.destroy(); graficos.mercado = null; } return; }
    $("#mercado-aviso").innerHTML = "";
    mercado.linhas = lista(r.dados, "linhas");
    desenharMercado();
    tabelaMercado();
  }
  function desenharMercado() {
    const ls = mercado.linhas;
    $("#mercado-alto").style.height = `${Math.max(300, ls.length * 26 + 70)}px`;
    const { texto, linha } = eixos();
    desenharGrafico("mercado", $("#graf-mercado"), {
      type: "bar",
      data: {
        labels: ls.map((l) => String(l.grupo)),
        datasets: [
          { label: "p25–p75", data: ls.map((l) => [Number(l.p25_usd), Number(l.p75_usd)]), backgroundColor: cssVar("--accent-bg").replace(/[\d.]+\)$/, ".55)"), borderColor: cssVar("--accent"), borderWidth: 1.5, borderRadius: 6, borderSkipped: false, barThickness: 16 },
          { label: "Mediana", type: "line", indexAxis: "y", data: ls.map((l) => Number(l.preco_mediano_usd)), showLine: false, pointRadius: 5, pointHoverRadius: 7, pointBackgroundColor: DESTAQUE, pointBorderColor: cssVar("--bg2"), pointBorderWidth: 2 },
        ],
      },
      options: {
        indexAxis: "y", responsive: true, maintainAspectRatio: false, animation: false,
        onClick: (ev, els) => { if (els.length) { const l = ls[els[0].index]; setTimeout(() => irParaGrupo(l), 0); } },
        onHover: (ev, els) => { ev.native.target.style.cursor = els.length ? "pointer" : "default"; },
        plugins: { legend: { labels: { color: texto, usePointStyle: true } }, tooltip: { callbacks: { label: (c) => { const l = ls[c.dataIndex]; return c.datasetIndex === 0 ? `p25 ${usd.format(l.p25_usd)} · p75 ${usd.format(l.p75_usd)}` : `mediana ${usd.format(l.preco_mediano_usd)} · ${num(l.vendas)} vendas`; } } } },
        scales: { x: { position: "top", ticks: { color: texto, callback: (v) => curto(v), maxTicksLimit: 6 }, grid: { color: linha } }, y: { ticks: { color: texto, autoSkip: false, font: { size: 12 } }, grid: { display: false } } },
      },
    });
  }
  const COLS_MERCADO = [["grupo", "Grupo"], ["vendas", "Vendas"], ["preco_mediano_usd", "Mediana"], ["preco_medio_usd", "Média"], ["p25_usd", "p25"], ["p75_usd", "p75"], ["preco_m2_mediano_usd", "US$/m²"]];
  function tabelaMercado() {
    const ls = mercado.linhas.slice();
    if (mercado.ordem) ls.sort((a, b) => { const x = a[mercado.ordem], y = b[mercado.ordem]; return (typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y), "pt-BR", { numeric: true })) * mercado.dir; });
    $("#tabela-mercado").innerHTML = `<table class="tabela"><thead><tr>${COLS_MERCADO.map(([k, n]) => `<th class="ordenavel${k === "grupo" ? "" : " num"}" data-ordenar="${k}">${n}${mercado.ordem === k ? (mercado.dir > 0 ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead><tbody>${ls.map((l) => `<tr class="clicavel" data-grupo="${esc(l.grupo)}">${COLS_MERCADO.map(([k]) => `<td class="${k === "grupo" ? "" : "num"}">${k === "grupo" ? `<b>${esc(l.grupo)}</b>` : k === "vendas" ? num(l[k]) : l[k] != null ? usd.format(l[k]) : "—"}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  }
  function irParaGrupo(l) {
    const g = String(l.grupo);
    if (mercado.dim === "cep") {
      irPara("mapa");
      setTimeout(() => selecionarCepNoMapa(g, true, "mercado"), inicializadas.has("mapa") && mapaValor ? 100 : 1500);
      return;
    }
    const f = $("#filtros-av");
    if (mercado.dim === "cidade") { f.reset(); garantirOpcao(f.elements.cidade, g); f.elements.cidade.value = g; }
    else if (mercado.dim === "quartos") { f.reset(); const q = String(parseInt(g, 10)); garantirOpcao(f.elements.quartos, q); f.elements.quartos.value = q; }
    else if (mercado.dim === "faixa_preco") { f.reset(); garantirOpcao(f.elements.faixa_preco, g); f.elements.faixa_preco.value = g; }
    else { toast("Filtro direto disponível para quartos, cidade, faixa de preço e CEP"); return; }
    filtrosAv.pagina = 1;
    irPara("avaliacoes");
    if (inicializadas.has("avaliacoes")) carregarAvaliacoes();
    toast(`Avaliações filtradas por ${NOMES_DIM[mercado.dim]}: ${g}`);
  }
  function initMercado() {
    $("#dimensoes").addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-dim]");
      if (!b) return;
      mercado.dim = b.dataset.dim;
      mercado.ordem = null;
      $$("#dimensoes button").forEach((x) => x.classList.toggle("ativo", x === b));
      carregarMercado();
    });
    let t = null;
    const f = $("#filtros-mercado");
    const rec = () => { clearTimeout(t); t = setTimeout(carregarMercado, 300); };
    f.addEventListener("input", rec);
    f.addEventListener("change", rec);
    f.addEventListener("submit", (ev) => ev.preventDefault());
    $("#tabela-mercado").addEventListener("click", (ev) => {
      const th = ev.target.closest("[data-ordenar]");
      if (th) { const k = th.dataset.ordenar; mercado.dir = mercado.ordem === k ? -mercado.dir : k === "grupo" ? 1 : -1; mercado.ordem = k; tabelaMercado(); return; }
      const tr = ev.target.closest("tr[data-grupo]");
      if (tr) { const l = mercado.linhas.find((x) => String(x.grupo) === tr.dataset.grupo); if (l) irParaGrupo(l); }
    });
    $$("[data-exportar-mercado]").forEach((b) => b.addEventListener("click", async () => {
      const url = "/v1/relatorios/mercado/exportar?" + qs({ formato: b.dataset.exportarMercado, ...paramsMercado() });
      const r = await api(url, { texto: true });
      if (!r.ok) { toast(r.status === 404 ? "Exportação ainda não está ativa nesta API" : `Não foi possível exportar (${r.status})`); return; }
      baixar(url);
    }));
    $("#btn-imprimir").addEventListener("click", () => window.print());
    preencherCidades();
    carregarMercado();
  }

  // ---------------------------------------------------------------- comercial (chaves de API)
  let ultimaChave = null;
  function initComercial() {
    atualizarAdmin();
    $("#form-chave").addEventListener("submit", gerarChave);
    $("#btn-clientes").addEventListener("click", carregarClientes);
    $("#tabela-clientes").addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-gerenciar]");
      if (b) abrirCliente(b.dataset.gerenciar);
    });
    $("#faturamento").addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-abrir-cliente]");
      if (b) abrirCliente(b.dataset.abrirCliente, "consumo");
    });
    $("#cli-busca").addEventListener("input", desenharClientes);
    $("#cli-situacao").addEventListener("change", desenharClientes);
    $("#cli-plano").addEventListener("change", desenharClientes);
    $("#gc-abas").addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-aba]");
      if (b) { gestao.aba = b.dataset.aba; gestao.painel = null; desenharGestao(); }
    });
    $("#gc-corpo").addEventListener("click", acaoGestao);
    $("#gc-corpo").addEventListener("submit", (ev) => { ev.preventDefault(); if (ev.target.id === "gc-form-dados") salvarDados(ev.target); });
    $("#gc-corpo").addEventListener("input", (ev) => {
      if (ev.target.id !== "gc-conf-prefixo") return;
      const b = $("[data-acao='revogar-confirmar']", $("#gc-corpo"));
      if (b) b.disabled = ev.target.value.trim() !== b.dataset.prefixo;
    });
    $("#btn-uso").addEventListener("click", verUso);
    $("#btn-avaliar-chave").addEventListener("click", avaliarComChave);
    $("#chave-resultado").addEventListener("click", async (ev) => {
      if (ev.target.closest("[data-copiar-chave]")) {
        try { await navigator.clipboard.writeText(ultimaChave || ""); toast("Chave copiada"); } catch (e) { toast("Não foi possível copiar automaticamente"); }
      } else if (ev.target.closest("[data-usar-chave]")) {
        $("#teste-chave").value = ultimaChave || "";
        $("#teste-chave").scrollIntoView({ behavior: "smooth", block: "center" });
      } else if (ev.target.closest("[data-ver-email]")) verEmail(ev.target.closest("[data-ver-email]").dataset.verEmail);
    });
    carregarClientes();
  }
  async function gerarChave(ev) {
    ev.preventDefault();
    const f = ev.target.elements;
    $$(".erro", ev.target).forEach((e) => { e.textContent = ""; });
    $$(".campo.invalido", ev.target).forEach((c) => c.classList.remove("invalido"));
    const marcar = (c, m) => { const e = $(`.erro[data-erro="${c}"]`, ev.target); if (e) { e.textContent = m; const cc = e.closest(".campo"); if (cc) cc.classList.add("invalido"); } };
    const corpo = { nome: f.nome.value.trim(), email: f.email.value.trim(), empresa: f.empresa.value.trim() || null, plano: f.plano.value };
    let ok = true;
    if (!corpo.nome) { marcar("nome", "Informe o nome"); ok = false; }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(corpo.email)) { marcar("email", "E-mail inválido"); ok = false; }
    const senhaConta = f.senhaconta ? f.senhaconta.value : "";
    if (acesso.exige && !senhaConta) { marcar("senhaconta", "Digite a senha da conta para confirmar"); ok = false; }
    if (!ok) return;
    if (!temAdmin()) {
      $("#chave-resultado").innerHTML = acesso.exige
        ? alertaHTML("Entre na plataforma", "Entre com a senha e o código do autenticador para emitir chaves.", [], "aviso")
        : alertaHTML("Token de administrador necessário", "Informe o token em Administrador, no cabeçalho, para emitir chaves.", [], "aviso");
      pedirAdmin();
      return;
    }
    const btn = $("#btn-gerar");
    btn.disabled = true;
    btn.innerHTML = '<span class="carregando"></span> Gerando…';
    const r = conferirSessao(await api("/v1/comercial/chaves", { metodo: "POST", corpo, headers: { ...cabAdmin(), ...(acesso.exige ? { "X-Senha-Conta": senhaConta } : {}) } }));
    btn.disabled = false;
    btn.textContent = "Gerar chave e enviar e-mail";
    if (!r.ok && r.dados && r.dados.erro === "acesso_negado") { marcar("senhaconta", r.dados.mensagem); f.senhaconta.value = ""; return; }
    if (r.status === 429) { marcar("senhaconta", (r.dados && r.dados.mensagem) || "Muitas tentativas. Aguarde 5 min."); return; }
    if (!r.ok || !r.dados) {
      const det = detalhesErro(r.dados);
      det.forEach((d) => marcar(d.campo, d.mensagem));
      $("#chave-resultado").innerHTML = r.status === 422 ? alertaHTML(tituloErro(422), mensagemErro(r), det, "aviso") : avisoRota(r, "O módulo comercial");
      return;
    }
    const d = r.dados, em = d.email || {};
    ultimaChave = d.chave;
    const selo = em.modo === "smtp" ? `<span class="selo-email smtp">✓ E-mail enviado para ${esc(em.destinatario)}</span>`
      : em.modo === "arquivo" ? '<span class="selo-email arquivo">✉ E-mail salvo localmente (SMTP não configurado)</span>'
        : `<span class="selo-email">${esc(em.mensagem || "E-mail não enviado")}</span>`;
    $("#chave-resultado").innerHTML = `
      <div class="res-topo"><div><h3 class="res-titulo">Chave emitida</h3><p class="res-local">Cliente #${esc(d.cliente_id)} · chave #${esc(d.chave_id)} · plano ${esc(NOME_PLANO[d.plano] || d.plano)}</p></div><span class="chip ok">${num(d.limite_mensal)}/mês · ${d.preco_mensal_usd != null ? usd.format(d.preco_mensal_usd) : ""}</span></div>
      <p class="guarde">⚠ Guarde agora: esta chave não será mostrada de novo. O banco guarda só o hash.</p>
      <div class="chave-caixa"><code id="chave-texto">${esc(d.chave)}</code><button type="button" class="btn-mini" data-copiar-chave>Copiar</button></div>
      ${selo}
      <dl class="lista-dados"><dt>Prefixo</dt><dd><code>${esc(d.prefixo)}</code></dd><dt>Destinatário</dt><dd>${esc(em.destinatario || corpo.email)}</dd>${em.mensagem ? `<dt>Envio</dt><dd>${esc(em.mensagem)}</dd>` : ""}</dl>
      <div class="laudo-acoes">${em.envio_id != null ? `<button type="button" class="btn btn-borda" data-ver-email="${esc(em.envio_id)}">Ver e-mail</button>` : ""}<button type="button" class="btn btn-pri" data-usar-chave>Usar no testador</button></div>`;
    ev.target.reset();
    carregarClientes();
  }
  async function verEmail(id) {
    const r = conferirSessao(await api(`/v1/comercial/emails/${encodeURIComponent(id)}`, { headers: cabAdmin(), texto: true }));
    if (!r.ok || !r.dados) { toast(r.status === 404 ? "E-mail não encontrado ou rota ainda inativa" : `Não foi possível abrir o e-mail (${r.status})`); return; }
    $("#modal-iframe").srcdoc = r.dados;
    abrirModal("modal");
  }
  const NOME_PLANO = { basico: "Básico", profissional: "Profissional", empresarial: "Empresarial" };
  const ORDEM_PLANO = ["basico", "profissional", "empresarial"];
  // Valores do módulo comercial com centavos, no padrão do portal (US$ 1.490,00)
  const usd2 = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const moeda = (v) => (v === null || v === undefined || v === "" || isNaN(Number(v)) ? "—" : usd2.format(Number(v)));
  const diaCurto = (s) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s || "")); return m ? `${m[3]}/${m[2]}` : String(s || ""); };
  // Catálogo de reserva (o mesmo de services/planos.py) enquanto GET /v1/comercial/planos não responde
  const PLANOS_PADRAO = [
    { plano: "basico", nome: "Básico", limite_mensal: 100, preco_mensal_usd: 29, preco_por_predicao_usd: 0.29 },
    { plano: "profissional", nome: "Profissional", limite_mensal: 1000, preco_mensal_usd: 199, preco_por_predicao_usd: 0.199 },
    { plano: "empresarial", nome: "Empresarial", limite_mensal: 10000, preco_mensal_usd: 1490, preco_por_predicao_usd: 0.149 },
  ];
  let planosCatalogo = null;
  async function carregarPlanos() {
    if (planosCatalogo) return planosCatalogo;
    const r = await api("/v1/comercial/planos");
    const l = r.ok ? lista(r.dados, "planos", "itens") : [];
    planosCatalogo = l.length ? l.map((p) => ({ ...p, plano: campo(p, "plano", "codigo", "id") })) : PLANOS_PADRAO;
    return planosCatalogo;
  }
  const planoDo = (codigo) => (planosCatalogo || PLANOS_PADRAO).find((p) => p.plano === codigo) || PLANOS_PADRAO.find((p) => p.plano === codigo) || null;
  const nomePlano = (codigo) => NOME_PLANO[codigo] || (planoDo(codigo) || {}).nome || codigo || "—";

  // Situação da chave: ativa (cobra e responde), suspensa (pausa reversível), revogada (definitiva)
  const SITUACOES = { ativa: ["ativa", "ok"], suspensa: ["suspensa", "aviso"], revogada: ["revogada", "ruim"] };
  function situacaoDe(c) {
    const s = String(campo(c, "situacao") || "").toLowerCase();
    if (SITUACOES[s]) return s;
    return campo(c, "ativa") === false || campo(c, "revogada_em") ? "revogada" : "ativa";
  }
  const chipSituacao = (s) => { const [t, cl] = SITUACOES[s] || [s || "—", ""]; return `<span class="chip ${cl}">${esc(t)}</span>`; };
  /** Fração do limite do mês já consumida: uso ÷ limite; `consumo_pct` (0–100) só como reserva. */
  function fracConsumo(o) {
    const uso = Number(campo(o, "uso_mes")) || 0, lim = Number(campo(o, "limite_mensal")) || 0;
    if (lim > 0) return uso / lim;
    const p = Number(campo(o, "consumo_pct"));
    return isFinite(p) ? (p > 1 ? p / 100 : p) : 0;
  }
  const barraConsumo = (fr) => `<div class="barra barra-uso"><i class="${fr >= 1 ? "cheio" : fr >= 0.8 ? "alto" : ""}" style="width:${Math.max(2, Math.min(1, fr) * 100)}%"></i></div>`;
  function seloEmail(em, destino) {
    em = em || {};
    return em.modo === "smtp" ? `<span class="selo-email smtp">✓ E-mail enviado para ${esc(em.destinatario || destino || "")}</span>`
      : em.modo === "arquivo" ? '<span class="selo-email arquivo">✉ E-mail salvo localmente (SMTP não configurado)</span>'
        : `<span class="selo-email">${esc(em.mensagem || "E-mail não enviado")}</span>`;
  }

  // ---- faturamento (faixa do topo)
  const comercial = { clientes: [], fat: null };
  /** Reserva quando GET /v1/comercial/faturamento não responde: os mesmos números a partir da lista. */
  function faturamentoLocal(cs) {
    const ativas = cs.filter((c) => situacaoDe(c) === "ativa");
    const soma = (l, k) => l.reduce((s, c) => s + (Number(c[k]) || 0), 0);
    const receita = soma(ativas, "preco_mensal_usd");
    return {
      local: true,
      receita_mensal_usd: receita,
      receita_anual_prevista_usd: receita * 12,
      ticket_medio_usd: ativas.length ? receita / ativas.length : 0,
      chaves_ativas: ativas.length,
      chaves_suspensas: cs.filter((c) => situacaoDe(c) === "suspensa").length,
      chaves_revogadas: cs.filter((c) => situacaoDe(c) === "revogada").length,
      predicoes_mes: soma(cs, "uso_mes"),
      por_plano: ORDEM_PLANO.map((p) => {
        const l = ativas.filter((c) => c.plano === p);
        return { plano: p, nome: NOME_PLANO[p], chaves_ativas: l.length, receita_mensal_usd: soma(l, "preco_mensal_usd"), predicoes_mes: soma(cs.filter((c) => c.plano === p), "uso_mes") };
      }),
      perto_do_limite: ativas.filter((c) => fracConsumo(c) >= 0.8).map((c) => ({ ...c, consumo_pct: fracConsumo(c) * 100 })).sort((a, b) => b.consumo_pct - a.consumo_pct),
    };
  }
  function faturamentoHTML(f) {
    const n = (k) => Number(campo(f, k)) || 0;
    const pp = lista(f.por_plano);
    const maxRec = Math.max(1, ...pp.map((p) => Number(p.receita_mensal_usd) || 0));
    const perto = lista(f.perto_do_limite).slice().sort((a, b) => fracConsumo(b) - fracConsumo(a));
    const planos = pp.length ? pp.map((p) => {
      const rec = Number(p.receita_mensal_usd) || 0, nk = Number(p.chaves_ativas) || 0;
      return `<li><div class="fp-topo"><b>${esc(p.nome || nomePlano(p.plano))}</b><span>${moeda(rec)}<small>/mês</small></span></div>
        <div class="fp-barra"><i class="fp-${esc(p.plano)}" style="width:${rec ? Math.max(3, (rec / maxRec) * 100) : 0}%"></i></div>
        <small class="nota">${num(nk)} ${nk === 1 ? "chave ativa" : "chaves ativas"} · ${num(p.predicoes_mes)} predições no mês</small></li>`;
    }).join("") : '<li class="nota">Sem chaves ativas.</li>';
    const alerta = perto.length ? `<ul class="limite-lista">${perto.map((c) => {
      const fr = fracConsumo(c);
      return `<li><button type="button" class="limite-item" data-abrir-cliente="${esc(c.cliente_id)}" title="Gerenciar ${esc(c.nome || "")}">
        <span class="li-nome"><b>${esc(c.nome || "Cliente #" + c.cliente_id)}</b><small>${esc(nomePlano(c.plano))} · ${num(c.uso_mes)} de ${num(c.limite_mensal)}</small></span>
        <span class="li-pct ${fr >= 1 ? "cheio" : ""}">${num(fr * 100, 0)} %</span>${barraConsumo(fr)}</button></li>`;
    }).join("")}</ul>` : '<p class="nota fat-ok">✓ Nenhum cliente com 80 % ou mais do limite do plano.</p>';
    return `<div class="kpis fat-kpis">
        <div class="stat fat-mrr"><strong>${moeda(n("receita_mensal_usd"))}</strong><span>Receita mensal (MRR)</span><em>só chaves ativas</em></div>
        <div class="stat"><strong>${moeda(n("receita_anual_prevista_usd"))}</strong><span>Receita anual prevista</span><em>MRR × 12</em></div>
        <div class="stat"><strong>${moeda(n("ticket_medio_usd"))}</strong><span>Ticket médio</span><em>mensalidade média</em></div>
        <div class="stat"><strong>${num(n("chaves_ativas"))}</strong><span>Chaves ativas</span><em><i class="pt aviso"></i>${num(n("chaves_suspensas"))} suspensas · <i class="pt ruim"></i>${num(n("chaves_revogadas"))} revogadas</em></div>
        <div class="stat"><strong>${num(n("predicoes_mes"))}</strong><span>Predições no mês</span><em>todas as chaves</em></div>
      </div>${cartoesFaturas(f.faturas)}
      <div class="fat-grade">
        <div class="cartao"><h3 class="cartao-titulo">Receita por plano</h3><ul class="fat-planos">${planos}</ul></div>
        <div class="cartao${perto.length ? " fat-alerta" : ""}"><h3 class="cartao-titulo">${perto.length ? `⚠ ${num(perto.length)} ${perto.length === 1 ? "cliente perto" : "clientes perto"} do limite` : "Consumo dos planos"}</h3>
          ${perto.length ? '<p class="nota">80 % ou mais do limite do mês. Clique para abrir o cliente e avaliar um upgrade.</p>' : ""}${alerta}</div>
      </div>${f.local ? '<p class="nota fat-nota">Números calculados no portal a partir da lista de clientes: a rota de faturamento não respondeu.</p>' : ""}`;
  }

  // ---- faturas (cobrança das mensalidades)
  const MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
  const competencia = (s) => { const m = /^(\d{4})-(\d{2})/.exec(String(s || "")); return m ? `${MESES[Number(m[2]) - 1] || m[2]}/${m[1]}` : String(s || "—"); };
  const dataCurta = (v) => { const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(v || "")); return m ? `${m[3]}/${m[2]}/${m[1]}` : dataHora(v); };
  const STATUS_FATURA = { paga: ["paga", "ok"], em_aberto: ["em aberto", "aviso"], vencida: ["vencida", "ruim"], cancelada: ["cancelada", "neutro"] };
  const chipFatura = (s) => { const [t, cl] = STATUS_FATURA[s] || [String(s || "—").replace(/_/g, " "), "neutro"]; return `<span class="chip ${cl}">${esc(t)}</span>`; };
  /** Cartões de cobrança da faixa de faturamento; somem se o backend ainda não manda o bloco `faturas`. */
  function cartoesFaturas(fx) {
    if (!fx || typeof fx !== "object" || Array.isArray(fx)) return "";
    const v = (k) => Number(fx[k]) || 0, qv = v("qtd_vencidas");
    return `<div class="kpis fat-kpis fat-cobranca">
        <div class="stat cob-ok"><strong>${moeda(v("recebido_mes_usd"))}</strong><span>Recebido no mês</span><em>faturas pagas</em></div>
        <div class="stat cob-aberto"><strong>${moeda(v("em_aberto_usd"))}</strong><span>Em aberto</span><em>a vencer</em></div>
        <div class="stat cob-vencido${qv ? " alerta-on" : ""}"><strong>${moeda(v("vencido_usd"))}</strong><span>Vencido</span><em>${qv ? `${num(qv)} ${qv === 1 ? "fatura vencida" : "faturas vencidas"}` : "nenhuma fatura vencida"}</em></div>
      </div>`;
  }

  // ---- tabela de clientes
  async function carregarClientes() {
    const caixa = $("#tabela-clientes");
    if (!temAdmin()) {
      caixa.innerHTML = `<p class="nota">${acesso.exige ? "Entre com a senha e o código do autenticador" : "Informe o token de administrador"} para listar os clientes.</p>`;
      $("#faturamento").innerHTML = "";
      $("#cli-contagem").textContent = "";
      return;
    }
    const [r, rf] = await Promise.all([
      api("/v1/comercial/clientes", { headers: cabAdmin() }),
      api("/v1/comercial/faturamento", { headers: cabAdmin() }),
    ]);
    conferirSessao(r);
    if (!r.ok || !r.dados) { caixa.innerHTML = avisoRota(r, "O módulo comercial"); $("#faturamento").innerHTML = ""; return; }
    comercial.clientes = lista(r.dados, "clientes", "itens");
    comercial.fat = rf.ok && rf.dados && typeof rf.dados === "object" && !Array.isArray(rf.dados) ? rf.dados : faturamentoLocal(comercial.clientes);
    $("#faturamento").innerHTML = faturamentoHTML(comercial.fat);
    desenharClientes();
  }
  function desenharClientes() {
    const caixa = $("#tabela-clientes"), cs = comercial.clientes;
    if (!temAdmin()) return;
    const q = normalizar($("#cli-busca").value), s = $("#cli-situacao").value, p = $("#cli-plano").value;
    const vis = cs.filter((c) => (!s || situacaoDe(c) === s) && (!p || campo(c, "plano") === p)
      && (!q || normalizar(`${c.nome || ""} ${c.email || ""} ${c.empresa || ""} ${c.prefixo || ""}`).includes(q)));
    $("#cli-contagem").textContent = !cs.length ? "" : vis.length === cs.length ? `${num(cs.length)} ${cs.length === 1 ? "chave" : "chaves"}` : `${num(vis.length)} de ${num(cs.length)} chaves`;
    if (!cs.length) { caixa.innerHTML = '<p class="nota">Nenhum cliente cadastrado ainda.</p>'; return; }
    if (!vis.length) { caixa.innerHTML = '<p class="nota">Nenhum cliente com esses filtros.</p>'; return; }
    caixa.innerHTML = `<table class="tabela tabela-clientes"><thead><tr><th>Cliente</th><th>Prefixo</th><th>Plano</th><th class="num">Mensalidade</th><th>Uso no mês</th><th>Situação</th><th>Criada em</th><th></th></tr></thead><tbody>${vis.map((c) => {
      const uso = Number(campo(c, "uso_mes")) || 0, lim = Number(campo(c, "limite_mensal")) || 0, fr = fracConsumo(c), sit = situacaoDe(c);
      const id = campo(c, "cliente_id");
      return `<tr class="sit-${sit}"><td><b>${esc(campo(c, "nome") || "—")}</b><br><small class="nota">${esc(campo(c, "email") || "")}${campo(c, "empresa") ? " · " + esc(c.empresa) : ""}</small></td>
        <td><code>${esc(campo(c, "prefixo") || "—")}</code></td><td>${esc(nomePlano(campo(c, "plano")))}</td>
        <td class="num">${moeda(c.preco_mensal_usd)}</td>
        <td><div class="uso"><small>${num(uso)} de ${num(lim)} · ${num(fr * 100, 0)} %</small>${barraConsumo(fr)}</div></td>
        <td>${chipSituacao(sit)}</td><td>${dataHora(campo(c, "criado_em", "criada_em"))}</td>
        <td>${id != null ? `<button type="button" class="btn-mini btn-gerenciar" data-gerenciar="${esc(id)}">Gerenciar</button>` : ""}</td></tr>`;
    }).join("")}</tbody></table>`;
  }

  // ---- janela "Gerenciar cliente"
  const gestao = { id: null, d: null, aba: "dados", painel: null, novaChave: null, ocupado: false };
  function limparGestao() {
    Object.assign(gestao, { id: null, d: null, painel: null, novaChave: null, ocupado: false });
    $("#gc-corpo").innerHTML = "";
    $("#gc-aviso").innerHTML = "";
  }
  async function abrirCliente(id, aba) {
    if (id === null || id === undefined || id === "") return;
    Object.assign(gestao, { id, d: null, aba: aba || "dados", painel: null, novaChave: null, ocupado: false });
    $("#gc-topo").innerHTML = `<h3 class="cartao-titulo" id="gc-titulo">Cliente #${esc(id)}</h3>`;
    $("#gc-aviso").innerHTML = "";
    $("#gc-corpo").innerHTML = '<p class="nota"><span class="carregando"></span> Carregando a ficha do cliente…</p>';
    marcarAbas();
    $("#modal-cliente").hidden = false;
    await Promise.all([carregarPlanos(), carregarDetalhe()]);
    const fechar = $("#modal-cliente [data-fechar-modal]");
    if (fechar && !$("#modal-cliente").hidden) fechar.focus();
  }
  async function carregarDetalhe() {
    const id = gestao.id;
    if (id === null) return;
    const r = conferirSessao(await api(`/v1/comercial/clientes/${encodeURIComponent(id)}`, { headers: cabAdmin() }));
    if (String(gestao.id) !== String(id)) return;
    if (!r.ok || !r.dados) {
      $("#gc-corpo").innerHTML = r.status === 404 && r.dados && r.dados.mensagem ? alertaHTML("Cliente não encontrado", r.dados.mensagem, [], "aviso") : avisoRota(r, "A ficha do cliente");
      return;
    }
    gestao.d = r.dados;
    desenharGestao();
  }
  const recarregarTudo = () => Promise.all([carregarDetalhe(), carregarClientes()]);
  const chavesDo = (d) => lista(d && d.chaves).map((k) => ({ ...k, situacao: situacaoDe(k) }));
  const maisRecente = (a, b) => String(b.criada_em || b.criado_em || "").localeCompare(String(a.criada_em || a.criado_em || "")) || (Number(b.chave_id) || 0) - (Number(a.chave_id) || 0);
  /** Chave que responde pelo cliente: a mais recente não revogada (ou a última, se todas foram revogadas). */
  function chavePrincipal(d) {
    const ks = chavesDo(d).sort(maisRecente);
    return ks.find((k) => k.situacao !== "revogada") || ks[0] || null;
  }
  function marcarAbas() {
    const d = gestao.d, nk = d ? lista(d.chaves).length : 0;
    const pend = d ? lista(d.faturas).filter((f) => f.status === "em_aberto" || f.status === "vencida").length : 0;
    const cont = { historico: d ? lista(d.eventos).length : 0, emails: d ? lista(d.emails).length : 0, chave: nk > 1 ? nk : 0, faturas: pend };
    $$("#gc-abas [data-aba]").forEach((b) => {
      const sel = b.dataset.aba === gestao.aba;
      b.classList.toggle("ativa", sel);
      b.setAttribute("aria-selected", String(sel));
      let s = b.querySelector("small");
      const n = cont[b.dataset.aba];
      if (n) { if (!s) { s = document.createElement("small"); b.appendChild(s); } s.textContent = String(n); } else if (s) s.remove();
    });
  }
  function desenharGestao() {
    const d = gestao.d;
    marcarAbas();
    if (!d) return;
    const k = chavePrincipal(d), sit = k ? k.situacao : "revogada";
    const plano = (k && k.plano) || d.plano;
    const preco = k && k.preco_mensal_usd !== null && k.preco_mensal_usd !== undefined ? k.preco_mensal_usd : d.preco_mensal_usd;
    $("#gc-topo").innerHTML = `<div class="gc-id"><span class="gc-avatar" aria-hidden="true">${esc(String(d.nome || "?").trim().charAt(0).toUpperCase())}</span><div>
        <h3 class="cartao-titulo" id="gc-titulo">${esc(d.nome || "Cliente #" + d.cliente_id)}</h3>
        <p class="nota">${d.empresa ? `<b>${esc(d.empresa)}</b> · ` : ""}${esc(d.email || "")} · cliente #${esc(d.cliente_id)} desde ${dataHora(d.criado_em)}</p></div></div>
      <div class="gc-selos"><span class="chip">${esc(nomePlano(plano))} · ${moeda(preco)}/mês</span>${chipSituacao(sit)}</div>`;
    const abas = { dados: abaDados, plano: abaPlano, chave: abaChave, consumo: abaConsumo, faturas: abaFaturas, historico: abaHistorico, emails: abaEmails };
    $("#gc-corpo").innerHTML = (abas[gestao.aba] || abaDados)(d, k);
  }
  function erroGestao(r, padrao) {
    const msg = r.status === 0 ? "API indisponível. Confira se o servidor está no ar."
      : (r.dados && (r.dados.mensagem || (typeof r.dados.detail === "string" ? r.dados.detail : ""))) || `${padrao} (${r.status}).`;
    const titulo = r.status === 400 ? "Regra de negócio" : r.status === 404 ? "Não encontrado" : r.status === 422 ? "Dados inválidos" : padrao;
    $("#gc-aviso").innerHTML = alertaHTML(titulo, msg, detalhesErro(r.dados), "aviso");
    toast(msg);
  }
  /** Executa uma ação da gestão: botão ocupado, erro do backend visível, recarga de ficha, tabela e faturamento. */
  async function executar(b, rotulo, chamada, sucesso, falha) {
    if (gestao.ocupado) return;
    gestao.ocupado = true;
    const txt = b.innerHTML;
    b.disabled = true;
    b.innerHTML = `<span class="carregando"></span> ${esc(rotulo)}`;
    $("#gc-aviso").innerHTML = "";
    const r = conferirSessao(await chamada());
    gestao.ocupado = false;
    if (!r.ok) {
      if (b.isConnected) { b.disabled = false; b.innerHTML = txt; }
      if (!(falha && falha(r))) erroGestao(r, "Não foi possível concluir");
      return;
    }
    gestao.painel = null;
    sucesso(r.dados || {});
    await recarregarTudo();
  }

  function abaDados(d) {
    const ks = chavesDo(d);
    return `<form id="gc-form-dados" class="gc-secao" novalidate>
      <h4 class="gc-sub">Dados do cliente</h4>
      <div class="campos-2">
        <div class="campo"><label for="gc-nome">Nome</label><input id="gc-nome" name="nome" type="text" maxlength="120" autocomplete="off" value="${esc(d.nome || "")}"><small class="erro" data-erro="nome"></small></div>
        <div class="campo"><label for="gc-email">E-mail</label><input id="gc-email" name="email" type="email" maxlength="160" autocomplete="off" value="${esc(d.email || "")}"><small class="erro" data-erro="email"></small></div>
      </div>
      <div class="campo"><label for="gc-empresa">Empresa <span class="nota">opcional</span></label><input id="gc-empresa" name="empresa" type="text" maxlength="120" autocomplete="off" value="${esc(d.empresa || "")}"><small class="erro" data-erro="empresa"></small></div>
      <div class="acoes"><button type="submit" class="btn btn-pri" id="gc-salvar">Salvar alterações</button></div>
      <dl class="lista-dados gc-resumo"><dt>Cliente</dt><dd>#${esc(d.cliente_id)} · cadastrado em ${dataHora(d.criado_em)}</dd>
        <dt>Plano</dt><dd>${esc(d.plano_nome || nomePlano(d.plano))} · ${moeda(d.preco_mensal_usd)}/mês · ${num(d.limite_mensal)} predições/mês</dd>
        <dt>Chaves</dt><dd>${num(ks.length)} no total · ${num(ks.filter((k) => k.situacao === "ativa").length)} ativa(s) · ${num(ks.filter((k) => k.situacao === "suspensa").length)} suspensa(s)</dd></dl>
    </form>`;
  }
  async function salvarDados(f) {
    const el = f.elements;
    $$(".erro", f).forEach((e) => { e.textContent = ""; });
    $$(".campo.invalido", f).forEach((c) => c.classList.remove("invalido"));
    const marcar = (c, m) => { const e = $(`.erro[data-erro="${c}"]`, f); if (e) { e.textContent = m; const cc = e.closest(".campo"); if (cc) cc.classList.add("invalido"); } };
    const novo = { nome: el.nome.value.trim(), email: el.email.value.trim(), empresa: el.empresa.value.trim() || null };
    let ok = true;
    if (!novo.nome) { marcar("nome", "Informe o nome"); ok = false; }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(novo.email)) { marcar("email", "E-mail inválido"); ok = false; }
    if (!ok) return;
    const d = gestao.d || {}, corpo = {};
    ["nome", "email", "empresa"].forEach((k) => { if ((novo[k] || null) !== (d[k] || null)) corpo[k] = novo[k]; });
    if (!Object.keys(corpo).length) { toast("Nenhuma alteração para salvar"); return; }
    await executar($("#gc-salvar"), "Salvando…",
      () => api(`/v1/comercial/clientes/${encodeURIComponent(gestao.id)}`, { metodo: "PATCH", corpo, headers: cabAdmin() }),
      () => toast("Dados do cliente atualizados"),
      (r) => { detalhesErro(r.dados).forEach((x) => marcar(x.campo, x.mensagem)); return false; });
  }

  function abaPlano(d, k) {
    const cat = planosCatalogo || PLANOS_PADRAO;
    const atual = (k && k.plano) || d.plano;
    const pode = !!k && k.situacao !== "revogada";
    const p = gestao.painel && gestao.painel.tipo === "plano" ? gestao.painel : null;
    let conf = "";
    if (p && k) {
      const de = planoDo(atual) || {}, para = planoDo(p.plano) || {};
      const dif = (Number(para.preco_mensal_usd) || 0) - (Number(de.preco_mensal_usd) || 0);
      const up = dif > 0 || (dif === 0 && (Number(para.limite_mensal) || 0) > (Number(de.limite_mensal) || 0));
      const uso = Number(k.uso_mes) || 0, sinalD = dif >= 0 ? "+" : "−";
      conf = `<div class="confirmar-caixa ${up ? "sobe" : "desce"}" id="gc-confirmar">
        <h4>${up ? "↑ Upgrade" : "↓ Downgrade"}: ${esc(nomePlano(atual))} → ${esc(nomePlano(p.plano))}</h4>
        <dl class="lista-dados"><dt>Mensalidade</dt><dd>${moeda(de.preco_mensal_usd)} → <b>${moeda(para.preco_mensal_usd)}</b> <span class="${dif >= 0 ? "pos" : "neg"}">(${sinalD}${moeda(Math.abs(dif))}/mês)</span></dd>
          <dt>Receita anual</dt><dd class="${dif >= 0 ? "pos" : "neg"}">${sinalD}${moeda(Math.abs(dif * 12))}/ano</dd>
          <dt>Limite</dt><dd>${num(de.limite_mensal)} → <b>${num(para.limite_mensal)}</b> predições por mês</dd>
          <dt>Chave</dt><dd><code>${esc(k.prefixo || "#" + k.chave_id)}</code> · a mesma chave continua valendo</dd></dl>
        ${!up && uso > (Number(para.limite_mensal) || 0) ? `<p class="guarde">⚠ O uso deste mês (${num(uso)}) já passa do novo limite: as próximas chamadas recebem 429 até o mês virar.</p>` : ""}
        <div class="acoes"><button type="button" class="btn btn-pri" data-acao="plano-confirmar" data-plano="${esc(p.plano)}">Confirmar ${up ? "upgrade" : "downgrade"}</button><button type="button" class="btn btn-borda" data-acao="cancelar">Cancelar</button></div></div>`;
    }
    const cards = cat.map((pl) => {
      const eh = pl.plano === atual, nome = pl.nome || nomePlano(pl.plano);
      return `<div class="plano-card${eh ? " atual" : ""}${p && p.plano === pl.plano ? " escolhido" : ""}"><small>${esc(nome)}</small><b>${num(pl.limite_mensal)}</b><i>predições por mês</i>
        <em>${moeda(pl.preco_mensal_usd)}<small>/mês</small></em><u>${moeda(pl.preco_por_predicao_usd)} por predição</u>
        ${eh ? '<span class="chip ok">Plano atual</span>' : `<button type="button" class="btn-mini" data-acao="plano" data-plano="${esc(pl.plano)}"${pode ? "" : " disabled"}>Mudar para ${esc(nome)}</button>`}</div>`;
    }).join("");
    return `<div class="gc-secao"><h4 class="gc-sub">Plano ${k ? `da chave <code>${esc(k.prefixo || "#" + k.chave_id)}</code>` : ""}</h4>
      ${pode ? "" : '<p class="nota">Sem chave ativa ou suspensa: emita uma nova chave para escolher o plano.</p>'}
      <div class="planos-gc">${cards}</div>${conf}</div>`;
  }

  function painelChave(c) {
    const p = gestao.painel && String(gestao.painel.chave) === String(c.chave_id) ? gestao.painel : null;
    if (!p) return "";
    const id = esc(c.chave_id);
    if (p.tipo === "suspender") return `<div class="confirmar-caixa desce">
      <h4>Suspender a chave <code>${esc(c.prefixo || "#" + c.chave_id)}</code></h4>
      <p class="nota">As chamadas com ela passam a receber 403 e a mensalidade sai da receita até a reativação. A chave não muda.</p>
      <div class="campo"><label for="gc-motivo">Motivo <span class="nota">opcional, fica no histórico</span></label><input id="gc-motivo" type="text" maxlength="200" autocomplete="off" placeholder="Ex.: pagamento em atraso"></div>
      <div class="acoes"><button type="button" class="btn btn-pri" data-acao="suspender-confirmar" data-chave="${id}">Confirmar suspensão</button><button type="button" class="btn btn-borda" data-acao="cancelar">Cancelar</button></div></div>`;
    if (p.tipo === "trocar") return `<div class="confirmar-caixa">
      <h4>Trocar a chave <code>${esc(c.prefixo || "#" + c.chave_id)}</code></h4>
      <p class="nota">Uma chave nova é emitida no mesmo plano e enviada ao cliente por e-mail; a atual deixa de funcionar. A nova aparece aqui <b>uma única vez</b>.</p>
      ${acesso.exige ? `<div class="campo"><label for="gc-senha">Senha da conta <span class="nota">confirma a troca</span></label><input id="gc-senha" type="password" autocomplete="current-password" maxlength="128"><small class="erro" data-erro="gc-senha"></small></div>` : '<p class="nota">Com o token de administrador a troca não pede a senha da conta.</p>'}
      <div class="acoes"><button type="button" class="btn btn-pri" data-acao="trocar-confirmar" data-chave="${id}">Emitir a nova chave</button><button type="button" class="btn btn-borda" data-acao="cancelar">Cancelar</button></div></div>`;
    if (p.tipo === "revogar") {
      const alvo = c.prefixo || "REVOGAR";
      return `<div class="confirmar-caixa perigo">
      <h4>Revogar a chave definitivamente</h4>
      <p class="nota">A revogação <b>não pode ser desfeita</b>: as próximas chamadas recebem 403 e a mensalidade sai da receita. Para suspender por um tempo, use Suspender.</p>
      <div class="campo"><label for="gc-conf-prefixo">Digite <code>${esc(alvo)}</code> para confirmar</label><input id="gc-conf-prefixo" type="text" autocomplete="off" spellcheck="false"></div>
      <div class="acoes"><button type="button" class="btn btn-perigo-forte" data-acao="revogar-confirmar" data-chave="${id}" data-prefixo="${esc(alvo)}" disabled>Revogar definitivamente</button><button type="button" class="btn btn-borda" data-acao="cancelar">Cancelar</button></div></div>`;
    }
    return "";
  }
  function novaChaveHTML(x) {
    const em = x.email || {};
    return `<div class="nova-chave">
      <div class="res-topo"><div><h4 class="gc-sub">Nova chave emitida</h4><p class="nota">Chave #${esc(x.chave_id)}${x.chave_anterior_id != null ? ` substitui a #${esc(x.chave_anterior_id)}` : ""} · plano ${esc(nomePlano(x.plano))}</p></div>
        <span class="chip ok">${num(x.limite_mensal)}/mês · ${moeda(x.preco_mensal_usd)}</span></div>
      <p class="guarde">⚠ Guarde agora: esta chave não será mostrada de novo. O banco guarda só o hash.</p>
      <div class="chave-caixa"><code>${esc(x.chave)}</code><button type="button" class="btn-mini" data-acao="copiar-chave">Copiar</button></div>
      ${seloEmail(em, (gestao.d || {}).email)}
      <div class="acoes nc-acoes">${em.envio_id != null ? `<button type="button" class="btn-mini" data-acao="ver-email" data-envio="${esc(em.envio_id)}">Ver e-mail</button>` : ""}<button type="button" class="btn-mini" data-acao="esconder-chave">Já guardei, esconder</button></div></div>`;
  }
  function abaChave(d) {
    const ks = chavesDo(d).sort((a, b) => (a.situacao === "revogada") - (b.situacao === "revogada") || maisRecente(a, b));
    const itens = ks.map((c) => {
      const fr = fracConsumo(c), id = esc(c.chave_id), s = c.situacao;
      const botoes = s === "revogada" ? '<span class="nota">Revogada: não aceita mais chamadas.</span>'
        : `${s === "ativa" ? `<button type="button" class="btn-mini" data-acao="suspender" data-chave="${id}">Suspender</button>` : `<button type="button" class="btn-mini btn-ok" data-acao="reativar" data-chave="${id}">Reativar</button>`}
          <button type="button" class="btn-mini" data-acao="trocar" data-chave="${id}">Trocar chave</button>
          <button type="button" class="btn-mini btn-perigo" data-acao="revogar" data-chave="${id}">Revogar</button>`;
      return `<article class="chave-item sit-${s}">
        <div class="ci-topo"><div><code class="ci-prefixo">${esc(c.prefixo || "—")}</code><small class="nota">chave #${id} · criada em ${dataHora(c.criada_em || c.criado_em)}</small></div>${chipSituacao(s)}</div>
        <dl class="lista-dados"><dt>Plano</dt><dd>${esc(nomePlano(c.plano))} · ${moeda(c.preco_mensal_usd)}/mês</dd>
          <dt>Uso no mês</dt><dd><div class="uso"><small>${num(c.uso_mes)} de ${num(c.limite_mensal)} · ${num(fr * 100, 0)} %</small>${barraConsumo(fr)}</div></dd></dl>
        <div class="acoes ci-acoes">${botoes}</div>${painelChave(c)}</article>`;
    }).join("");
    return `<div class="gc-secao">${gestao.novaChave ? novaChaveHTML(gestao.novaChave) : ""}<h4 class="gc-sub">Chaves do cliente</h4>${itens || '<p class="nota">Nenhuma chave emitida.</p>'}</div>`;
  }

  function abaConsumo(d, k) {
    const base = Number(d.limite_mensal) ? d : k || d;
    const uso = Number(base.uso_mes) || 0, lim = Number(base.limite_mensal) || 0, fr = fracConsumo(base), rest = Math.max(0, lim - uso);
    const dias = lista(d.uso_por_dia).map((x) => ({ dia: campo(x, "dia", "data"), total: Number(campo(x, "total", "quantidade")) || 0 }));
    const max = Math.max(1, ...dias.map((x) => x.total)), tot = dias.reduce((s, x) => s + x.total, 0);
    const passo = Math.max(1, Math.ceil(dias.length / 10));
    const preco = Number(k && k.preco_mensal_usd != null ? k.preco_mensal_usd : d.preco_mensal_usd) || 0;
    const barras = dias.length ? `<div class="dias" role="img" aria-label="Predições por dia">${dias.map((x, i) => `<div class="dia" title="${esc(diaCurto(x.dia))}: ${num(x.total)} predições">
        <b>${x.total ? num(x.total) : ""}</b><i style="height:${x.total ? Math.max(3, (x.total / max) * 100) : 0}%"></i><small>${i % passo === 0 || i === dias.length - 1 ? esc(diaCurto(x.dia)) : ""}</small></div>`).join("")}</div>`
      : '<p class="nota">Nenhuma predição registrada no período.</p>';
    const aviso = fr >= 1 ? "Limite atingido: novas chamadas recebem 429 até o próximo mês ou um upgrade."
      : fr >= 0.8 ? `Restam ${num(rest)} predições: bom momento para oferecer upgrade.` : `Restam ${num(rest)} predições neste mês.`;
    return `<div class="gc-secao">
      <h4 class="gc-sub">Consumo do mês</h4>
      <div class="consumo-mes ${fr >= 1 ? "cheio" : fr >= 0.8 ? "alto" : ""}"><div class="cm-num"><b>${num(uso)}</b><span>de ${num(lim)} predições · ${num(fr * 100, 0)} % do limite</span></div>${barraConsumo(fr)}<small class="nota">${aviso}</small></div>
      <div class="kpis gc-kpis">
        <div class="stat"><strong>${num(tot)}</strong><span>predições no período</span></div>
        <div class="stat"><strong>${num(dias.length ? tot / dias.length : 0, 1)}</strong><span>média por dia</span></div>
        <div class="stat"><strong>${num(dias.length ? Math.max(...dias.map((x) => x.total)) : 0)}</strong><span>pico diário</span></div>
        <div class="stat"><strong>${uso ? moeda(preco / uso) : "—"}</strong><span>custo efetivo por predição</span></div>
      </div>
      <h4 class="gc-sub">Uso por dia</h4>${barras}</div>`;
  }

  function abaFaturas(d) {
    if (!Array.isArray(d.faturas)) return '<div class="gc-secao"><p class="nota">As faturas deste cliente ainda não estão disponíveis nesta versão da API.</p></div>';
    const fs = d.faturas.slice().sort((a, b) => String(b.competencia || "").localeCompare(String(a.competencia || "")) || (Number(b.id) || 0) - (Number(a.id) || 0));
    if (!fs.length) return '<div class="gc-secao"><p class="nota">Nenhuma fatura emitida para este cliente.</p></div>';
    const soma = (st) => fs.filter((f) => f.status === st).reduce((s, f) => s + (Number(f.valor_usd) || 0), 0);
    const p = gestao.painel && gestao.painel.tipo === "baixa" ? gestao.painel : null;
    const linhas = fs.map((f) => {
      const pode = f.status === "em_aberto" || f.status === "vencida", conf = p && String(p.fatura) === String(f.id);
      const acao = !pode ? "" : conf
        ? `<span class="baixa-conf"><button type="button" class="btn-mini btn-ok" data-acao="baixa-confirmar" data-fatura="${esc(f.id)}">Confirmar baixa de ${moeda(f.valor_usd)}</button><button type="button" class="btn-mini" data-acao="cancelar">Cancelar</button></span>`
        : `<button type="button" class="btn-mini" data-acao="baixa" data-fatura="${esc(f.id)}">Dar baixa</button>`;
      return `<tr class="fat-${esc(f.status || "")}"><td><b>${esc(competencia(f.competencia))}</b><br><small class="nota">fatura #${esc(f.id)}</small></td>
        <td>${esc(nomePlano(f.plano))}</td><td class="num">${num(f.predicoes)}</td><td class="num"><b>${moeda(f.valor_usd)}</b></td>
        <td>${f.vencimento ? dataCurta(f.vencimento) : "—"}</td><td>${chipFatura(f.status)}${f.paga_em ? `<br><small class="nota">paga em ${dataCurta(f.paga_em)}</small>` : ""}</td><td class="fat-acao">${acao}</td></tr>`;
    }).join("");
    return `<div class="gc-secao"><h4 class="gc-sub">Faturas do cliente</h4>
      <div class="kpis gc-kpis gc-fat">
        <div class="stat"><strong class="pos">${moeda(soma("paga"))}</strong><span>pago</span></div>
        <div class="stat"><strong>${moeda(soma("em_aberto"))}</strong><span>em aberto</span></div>
        <div class="stat"><strong class="${soma("vencida") ? "neg" : ""}">${moeda(soma("vencida"))}</strong><span>vencido</span></div>
        <div class="stat"><strong>${num(fs.length)}</strong><span>faturas</span></div>
      </div>
      <div class="tabela-wrap"><table class="tabela tabela-faturas"><thead><tr><th>Competência</th><th>Plano</th><th class="num">Predições</th><th class="num">Valor</th><th>Vencimento</th><th>Status</th><th></th></tr></thead><tbody>${linhas}</tbody></table></div></div>`;
  }

  const EVENTOS = {
    emissao: ["⚿", "Chave emitida", "ok"], troca_plano: ["⇅", "Troca de plano", ""], suspensao: ["❚❚", "Chave suspensa", "aviso"],
    reativacao: ["▶", "Chave reativada", "ok"], rotacao: ["↻", "Chave trocada", ""], revogacao: ["✕", "Chave revogada", "ruim"], edicao: ["✎", "Dados editados", ""],
  };
  function abaHistorico(d) {
    const ev = lista(d.eventos).slice().sort((a, b) => String(b.criado_em || "").localeCompare(String(a.criado_em || "")));
    if (!ev.length) return '<div class="gc-secao"><p class="nota">Nenhum evento registrado para este cliente.</p></div>';
    return `<div class="gc-secao"><h4 class="gc-sub">Linha do tempo</h4><ol class="linha-tempo">${ev.map((e) => {
      const [ic, nome, cl] = EVENTOS[e.tipo] || ["•", e.tipo || "Evento", ""];
      return `<li class="${cl}"><span class="lt-ic" aria-hidden="true">${ic}</span><div class="lt-txt"><div class="lt-topo"><b>${esc(nome)}</b>${e.chave_id != null ? `<small class="nota">chave #${esc(e.chave_id)}</small>` : ""}<time datetime="${esc(e.criado_em || "")}">${dataHora(e.criado_em)}</time></div>${e.detalhe ? `<p>${esc(e.detalhe)}</p>` : ""}</div></li>`;
    }).join("")}</ol></div>`;
  }
  const MODO_EMAIL = { smtp: "enviado por SMTP", arquivo: "salvo localmente" };
  function abaEmails(d) {
    const es = lista(d.emails).slice().sort((a, b) => String(b.criado_em || "").localeCompare(String(a.criado_em || "")));
    if (!es.length) return '<div class="gc-secao"><p class="nota">Nenhum e-mail enviado a este cliente.</p></div>';
    return `<div class="gc-secao"><h4 class="gc-sub">E-mails enviados</h4><ul class="lista-emails">${es.map((e) => `<li>
      <div class="le-txt"><b>${esc(e.assunto || "E-mail")}</b><small class="nota">${dataHora(e.criado_em)}${e.envio_id != null ? ` · envio #${esc(e.envio_id)}` : ""}</small></div>
      <span class="selo-email ${e.modo === "smtp" ? "smtp" : e.modo === "arquivo" ? "arquivo" : ""}">${esc(MODO_EMAIL[e.modo] || e.modo || "—")}${e.status ? " · " + esc(e.status) : ""}</span>
      ${e.envio_id != null ? `<button type="button" class="btn-mini" data-acao="ver-email" data-envio="${esc(e.envio_id)}">Ver e-mail</button>` : ""}</li>`).join("")}</ul></div>`;
  }

  async function acaoGestao(ev) {
    const b = ev.target.closest("[data-acao]");
    if (!b || b.disabled || !gestao.d) return;
    const a = b.dataset.acao, chave = b.dataset.chave, cid = encodeURIComponent(chave || "");
    const abrirPainel = (painel, foco) => {
      gestao.painel = painel;
      $("#gc-aviso").innerHTML = "";
      desenharGestao();
      const caixa = $("#gc-confirmar") || $(".confirmar-caixa", $("#gc-corpo"));
      if (caixa) caixa.scrollIntoView({ behavior: "smooth", block: "nearest" });
      const f = foco && $(foco);
      if (f) setTimeout(() => f.focus(), 30);
    };
    if (a === "cancelar") { gestao.painel = null; desenharGestao(); return; }
    if (a === "plano") { const k = chavePrincipal(gestao.d); abrirPainel({ tipo: "plano", plano: b.dataset.plano, chave: k && k.chave_id }); return; }
    if (a === "suspender") { abrirPainel({ tipo: a, chave }, "#gc-motivo"); return; }
    if (a === "trocar") { abrirPainel({ tipo: a, chave }, "#gc-senha"); return; }
    if (a === "revogar") { abrirPainel({ tipo: a, chave }, "#gc-conf-prefixo"); return; }
    if (a === "baixa") { gestao.painel = { tipo: "baixa", fatura: b.dataset.fatura }; $("#gc-aviso").innerHTML = ""; desenharGestao(); return; }
    if (a === "baixa-confirmar") {
      await executar(b, "Dando baixa…",
        () => api(`/v1/admin/banco/faturas/${encodeURIComponent(b.dataset.fatura)}`, { metodo: "PATCH", corpo: { status: "paga" }, headers: cabAdmin() }),
        () => toast(`Baixa registrada: fatura #${b.dataset.fatura} paga`));
      return;
    }
    if (a === "ver-email") { verEmail(b.dataset.envio); return; }
    if (a === "esconder-chave") { gestao.novaChave = null; desenharGestao(); return; }
    if (a === "copiar-chave") {
      try { await navigator.clipboard.writeText((gestao.novaChave && gestao.novaChave.chave) || ""); toast("Chave copiada"); } catch (e) { toast("Não foi possível copiar automaticamente"); }
      return;
    }
    if (a === "plano-confirmar") {
      const p = gestao.painel || {}, plano = b.dataset.plano;
      await executar(b, "Mudando o plano…",
        () => api(`/v1/comercial/chaves/${encodeURIComponent(p.chave)}/plano`, { metodo: "PATCH", corpo: { plano }, headers: cabAdmin() }),
        (x) => toast(`${x.movimento === "downgrade" ? "Downgrade" : "Upgrade"} para ${nomePlano(x.plano || plano)}: ${moeda(x.preco_mensal_usd)}/mês, ${num(x.limite_mensal)} predições`));
      return;
    }
    if (a === "suspender-confirmar") {
      const motivo = (($("#gc-motivo") || {}).value || "").trim();
      await executar(b, "Suspendendo…",
        () => api(`/v1/comercial/chaves/${cid}/suspender`, { metodo: "POST", corpo: motivo ? { motivo } : {}, headers: cabAdmin() }),
        () => toast("Chave suspensa: as chamadas com ela recebem 403 até a reativação"));
      return;
    }
    if (a === "reativar") {
      await executar(b, "Reativando…",
        () => api(`/v1/comercial/chaves/${cid}/reativar`, { metodo: "POST", headers: cabAdmin() }),
        () => toast("Chave reativada: volta a responder e a cobrar"));
      return;
    }
    if (a === "trocar-confirmar") {
      const campoSenha = $("#gc-senha"), senha = campoSenha ? campoSenha.value : "";
      const erroSenha = (m) => { const e = $('.erro[data-erro="gc-senha"]', $("#gc-corpo")); if (e) { e.textContent = m; e.closest(".campo").classList.add("invalido"); } };
      if (acesso.exige && !senha) { erroSenha("Digite a senha da conta para confirmar"); return; }
      await executar(b, "Emitindo…",
        () => api(`/v1/comercial/chaves/${cid}/rotacionar`, { metodo: "POST", headers: { ...cabAdmin(), ...(acesso.exige ? { "X-Senha-Conta": senha } : {}) } }),
        (x) => { gestao.novaChave = x; gestao.aba = "chave"; toast("Chave trocada: guarde a nova chave agora"); },
        (r) => {
          if ((r.status === 401 || r.status === 403 || r.status === 429) && campoSenha && r.dados && (r.dados.erro === "acesso_negado" || r.status === 429)) {
            campoSenha.value = "";
            erroSenha(r.dados.mensagem || "Senha da conta incorreta");
            toast(r.dados.mensagem || "Senha da conta incorreta");
            return true;
          }
          return false;
        });
      return;
    }
    if (a === "revogar-confirmar") {
      const conf = $("#gc-conf-prefixo");
      if (!conf || conf.value.trim() !== b.dataset.prefixo) return;
      await executar(b, "Revogando…",
        () => api(`/v1/comercial/chaves/${cid}/revogar`, { metodo: "POST", headers: cabAdmin() }),
        () => toast("Chave revogada: as próximas chamadas com ela recebem 403"));
    }
  }
  const ERROS_CHAVE = {
    401: ["Chave inválida", "A chave não existe ou foi digitada errada (chave_invalida)."],
    403: ["Chave revogada", "Esta chave foi revogada pelo administrador e não aceita mais chamadas (chave_revogada)."],
    429: ["Limite do plano atingido", "O consumo do mês chegou ao limite do plano (limite_excedido). Faça upgrade ou aguarde o próximo mês."],
  };
  function erroChave(r) {
    const e = ERROS_CHAVE[r.status];
    if (!e) return avisoRota(r, "O controle de chaves");
    return `<div class="alerta aviso"><h4><span class="cod aviso">${r.status}</span> ${e[0]}</h4><p>${esc((r.dados && r.dados.mensagem) || e[1])}</p>${r.dados && r.dados.erro ? `<p class="nota">código: <code>${esc(r.dados.erro)}</code></p>` : ""}</div>`;
  }
  async function verUso() {
    const k = $("#teste-chave").value.trim();
    if (!k) { toast("Cole uma chave de API"); return; }
    const r = await api("/v1/comercial/uso", { headers: { "X-API-Key": k } });
    if (!r.ok || !r.dados) { $("#teste-resultado").innerHTML = erroChave(r); return; }
    const d = r.dados, uso = Number(campo(d, "usadas_mes", "uso_mes")) || 0, lim = Number(campo(d, "limite_mensal")) || 0;
    $("#teste-resultado").innerHTML = `<div class="resposta-chave">
      <div class="res-item"><small>${esc(campo(d, "cliente") || "Cliente")} · plano</small><b>${esc(campo(d, "plano") || "—")}</b></div>
      <div class="res-item"><small>Uso no mês</small><b>${num(uso)}</b></div>
      <div class="res-item"><small>Limite mensal</small><b>${num(lim)}</b></div>
      <div class="res-item"><small>Restante</small><b class="pos">${num(campo(d, "restantes", "restante") ?? Math.max(0, lim - uso))}</b></div></div>`;
  }
  async function avaliarComChave() {
    const k = $("#teste-chave").value.trim();
    if (!k) { toast("Cole uma chave de API"); return; }
    const r = await api("/v1/predict", { metodo: "POST", corpo: { ...estado.imovel }, headers: { "X-API-Key": k } });
    if (!r.ok || !r.dados) { $("#teste-resultado").innerHTML = erroChave(r); return; }
    const d = r.dados, fx = d.faixa_provavel_usd || {};
    $("#teste-resultado").innerHTML = `<div class="salvo"><b>200 · avaliação aceita com a chave</b> · ${usd.format(d.preco_estimado_usd)} (faixa ${usd.format(fx.minimo)} – ${usd.format(fx.maximo)}) · ${num(estado.imovel.area_util_m2)} m², CEP ${esc(estado.imovel.cep)}</div>`;
  }

  // ---------------------------------------------------------------- banco de dados (documentação e uso)
  async function atualizarUso() {
    const res = await carregarResumo();
    $("#rel-aviso").innerHTML = res.ok ? "" : avisoRota(res.r, "O banco de relatórios");
    if (res.ok) {
      const d = res.d, set = (id, v) => { $(id).textContent = v; };
      set("#rel-total", campo(d, "total_predicoes") != null ? num(d.total_predicoes) : "—");
      set("#rel-hoje", campo(d, "predicoes_hoje") != null ? num(d.predicoes_hoje) : "—");
      set("#rel-clientes", campo(d, "clientes") != null ? num(d.clientes) : "—");
      set("#rel-chaves", campo(d, "chaves_ativas") != null ? num(d.chaves_ativas) : "—");
      set("#rel-lat", campo(d, "latencia_mediana_ms") != null ? `${num(d.latencia_mediana_ms, 1)} ms` : "—");
      set("#rel-preco", campo(d, "preco_medio_usd") != null ? usd.format(d.preco_medio_usd) : "—");
      graficoDia("dia", $("#graf-dia"), d.por_dia);
      const { texto, linha } = eixos();
      const po = pares(d.por_origem, ["origem"], ["total", "quantidade", "n"]);
      desenharGrafico("origem", $("#graf-origem"), {
        type: "doughnut",
        data: { labels: po.map((x) => x[0]), datasets: [{ data: po.map((x) => x[1]), backgroundColor: ["#703bf7", "#a685fa", "#1baf7a", "#ff9f0a", "#4b22b5"], borderColor: cssVar("--card"), borderWidth: 3 }] },
        options: { responsive: true, maintainAspectRatio: false, animation: false, cutout: "62%", plugins: { legend: { position: "bottom", labels: { color: texto } } } },
      });
      const pst = pares(d.por_status, ["status_http", "status"], ["total", "quantidade", "n"]);
      desenharGrafico("status", $("#graf-status"), {
        type: "bar",
        data: { labels: pst.map((x) => x[0]), datasets: [{ data: pst.map((x) => x[1]), backgroundColor: pst.map((x) => (String(x[0]).startsWith("2") ? "#1baf7a" : String(x[0]).startsWith("5") ? "#ff5d5d" : "#ff9f0a")), borderRadius: 6, maxBarThickness: 40 }] },
        options: { responsive: true, maintainAspectRatio: false, animation: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { color: texto }, grid: { display: false } }, y: { beginAtZero: true, ticks: { color: texto, precision: 0 }, grid: { color: linha } } } },
      });
    }
    const r = await api("/v1/relatorios/predicoes?limite=20");
    const caixa = $("#tabela-predicoes");
    if (!r.ok || !r.dados) { caixa.innerHTML = res.ok ? avisoRota(r, "A lista de predições") : ""; return; }
    const ps = lista(r.dados, "predicoes", "itens");
    caixa.innerHTML = ps.length ? `<table class="tabela"><thead><tr><th>#</th><th>Data</th><th>Origem</th><th>Cliente</th><th>CEP</th><th class="num">Área</th><th class="num">Preço estimado</th><th class="num">Latência</th><th>Status</th></tr></thead><tbody>${ps.map((x) => {
      const st = Number(x.status_http), cls = st >= 200 && st < 300 ? "ok" : st >= 500 ? "erro" : "aviso";
      return `<tr><td>${esc(x.id)}</td><td>${dataHora(x.criado_em)}</td><td><span class="origem ${esc(x.origem || "")}">${esc(x.origem || "—")}</span></td><td>${esc(campo(x, "cliente", "cliente_nome") || "—")}</td><td>${esc(x.cep || "—")}</td>
        <td class="num">${x.area_util_m2 != null ? num(x.area_util_m2) + " m²" : "—"}</td><td class="num">${x.preco_estimado_usd != null ? usd.format(x.preco_estimado_usd) : "—"}</td>
        <td class="num">${x.latencia_ms != null ? num(x.latencia_ms, 1) + " ms" : "—"}</td><td><span class="cod ${cls}">${esc(x.status_http)}</span></td></tr>`;
    }).join("")}</tbody></table>` : '<p class="nota">Nenhuma predição registrada ainda.</p>';
    $("#rel-atualizado").textContent = "atualizado às " + new Date().toLocaleTimeString("pt-BR");
  }
  const POS_TABELAS = { clientes: [0, 0], chaves: [1, 0], predicoes: [2, 0], envios_email: [0, 1], avaliacoes: [1, 1], vendas_historicas: [2, 1] };
  const ALVO_FK = { cliente_id: "clientes", chave_id: "chaves", predicao_id: "predicoes", venda_id: "vendas_historicas", avaliacao_id: "avaliacoes", envio_id: "envios_email" };
  function desenharDiagrama(tabelas) {
    const W = 230, LIN = 17, TOPO = 30, MAXC = 8, GX = 70, GY = 56;
    const nomes = tabelas.map((t) => t.nome);
    Object.keys(POS_TABELAS).forEach((n) => { if (!nomes.includes(n)) tabelas.push({ nome: n, colunas: [], linhas: null, ausente: true }); });
    let extra = 0;
    const caixas = {};
    tabelas.forEach((t) => {
      const pos = POS_TABELAS[t.nome] || [extra % 3, 2 + Math.floor(extra++ / 3)];
      const cols = (t.colunas || []).slice(0, MAXC);
      caixas[t.nome] = { t, cols, x: 10 + pos[0] * (W + GX), col: pos[0], row: pos[1], h: TOPO + Math.max(1, cols.length + ((t.colunas || []).length > MAXC ? 1 : 0)) * LIN + 10 };
    });
    const alturaLinha = {};
    Object.values(caixas).forEach((c) => { alturaLinha[c.row] = Math.max(alturaLinha[c.row] || 0, c.h); });
    const yLinha = (r) => 10 + Object.keys(alturaLinha).filter((k) => k < r).reduce((s, k) => s + alturaLinha[k] + GY, 0);
    Object.values(caixas).forEach((c) => { c.y = yLinha(c.row); });
    const largura = 20 + 3 * W + 2 * GX, altura = Math.max(...Object.values(caixas).map((c) => c.y + c.h)) + 10;
    const rels = [];
    Object.values(caixas).forEach((c) => (c.t.colunas || []).forEach((col, i) => {
      const alvo = col.referencia || col.fk || ALVO_FK[col.nome];
      const nomeAlvo = typeof alvo === "string" ? alvo.split(".")[0] : null;
      if (nomeAlvo && caixas[nomeAlvo] && nomeAlvo !== c.t.nome) rels.push({ de: c, ate: caixas[nomeAlvo], col: col.nome, i: Math.min(i, MAXC) });
    }));
    const caminho = ({ de, ate, i }) => {
      const y1 = de.y + TOPO + i * LIN + 6;
      if (de.row === ate.row) {
        const dir = ate.x < de.x;
        const x1 = dir ? de.x : de.x + W, x2 = dir ? ate.x + W : ate.x, y2 = ate.y + TOPO / 2;
        return `M${x1},${y1} C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2},${y2}`;
      }
      const x1 = de.x + (ate.x > de.x ? W : 0), x2 = ate.x + W / 2, y2 = ate.y + ate.h;
      return `M${x1},${y1} C${x1 + (ate.x > de.x ? 40 : -40)},${y1} ${x2},${y2 + 40} ${x2},${y2}`;
    };
    $("#diagrama").innerHTML = `<svg viewBox="0 0 ${largura} ${altura}" role="img" aria-label="Diagrama das relações entre as tabelas do banco">
      <defs><marker id="seta" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="${cssVar("--accent-3")}"/></marker></defs>
      ${rels.map((r) => `<path class="t-rel" d="${caminho(r)}" marker-end="url(#seta)"><title>${esc(r.de.t.nome)}.${esc(r.col)} → ${esc(r.ate.t.nome)}.id</title></path>`).join("")}
      ${Object.values(caixas).map((c) => `<g>
        <rect class="t-caixa" x="${c.x}" y="${c.y}" width="${W}" height="${c.h}" rx="10"${c.t.ausente ? ' stroke-dasharray="5 4"' : ""}/>
        <path class="t-topo" d="M${c.x},${c.y + 10} a10,10 0 0 1 10,-10 h${W - 20} a10,10 0 0 1 10,10 v${TOPO - 10} h-${W} z"${c.t.ausente ? ' opacity=".45"' : ""}/>
        <text class="t-nome" x="${c.x + 12}" y="${c.y + 20}">${esc(c.t.nome)}</text>
        <text class="t-linhas" x="${c.x + W - 12}" y="${c.y + 20}" text-anchor="end">${c.t.ausente ? "ainda não criada" : c.t.linhas != null ? num(c.t.linhas) + " linhas" : ""}</text>
        ${c.cols.map((col, i) => `<text class="t-col${col.nome === "id" || ALVO_FK[col.nome] ? " t-chave" : ""}" x="${c.x + 12}" y="${c.y + TOPO + 12 + i * LIN}">${col.nome === "id" ? "🔑 " : ALVO_FK[col.nome] ? "↗ " : ""}${esc(col.nome)}<tspan fill="${cssVar("--muted")}"> ${esc(col.tipo || "")}</tspan></text>`).join("")}
        ${(c.t.colunas || []).length > MAXC ? `<text class="t-col" x="${c.x + 12}" y="${c.y + TOPO + 12 + MAXC * LIN}">+ ${c.t.colunas.length - MAXC} colunas</text>` : ""}
      </g>`).join("")}
    </svg>`;
  }
  async function carregarEsquema() {
    const r = await api("/v1/relatorios/esquema");
    if (!r.ok || !r.dados) { $("#esquema-cartoes").innerHTML = avisoRota(r, "A documentação do banco"); desenharDiagrama([]); return; }
    const d = r.dados, ts = lista(d, "tabelas");
    $("#esquema-info").textContent = `${d.banco || "SQLite"}${d.arquivo ? " · arquivo " + d.arquivo : ""} · ${ts.length} tabelas · ${num(ts.reduce((s, t) => s + (Number(t.linhas) || 0), 0))} linhas no total.`;
    desenharDiagrama(ts.map((t) => ({ ...t })));
    $("#esquema-cartoes").innerHTML = ts.map((t) => {
      const idx = lista(t, "indices");
      return `<div class="cartao esquema-cartao"><h3>${esc(t.nome)} <span>${num(t.linhas)} linhas</span></h3><p>${esc(t.descricao || "")}</p>
      <ul class="colunas">${(t.colunas || []).map((c) => `<li><code>${esc(c.nome)}</code><em>${esc(c.tipo || "")}</em>${c.descricao ? `<small>${esc(c.descricao)}</small>` : ""}</li>`).join("")}</ul>
      ${idx.length ? `<div class="indices">${idx.map((i) => `<code title="${esc(typeof i === "object" ? (i.colunas || []).join(", ") : "")}">${esc(typeof i === "object" ? i.nome : i)}</code>`).join("")}</div>` : ""}</div>`;
    }).join("");
  }
  function initBanco() {
    atualizarUso();
    carregarEsquema();
    if (window.TelaBanco) window.TelaBanco.iniciar($('.view[data-view="banco"]'));
    setInterval(() => { if (visivel("banco")) atualizarUso(); }, 10000);
  }

  // ---------------------------------------------------------------- visão 3D (prédios do OpenFreeMap + voo orbital)
  function adicionarPredios(reg) {
    const m = reg.m;
    if (m.getLayer("predios-3d") || !m.getSource("openmaptiles")) return;
    m.addLayer({
      id: "predios-3d", type: "fill-extrusion", source: "openmaptiles", "source-layer": "building", minzoom: 13,
      layout: { visibility: reg.tres ? "visible" : "none" },
      paint: {
        "fill-extrusion-color": ["interpolate", ["linear"], ["coalesce", ["get", "render_height"], 0], 0, "#4b22b5", 30, "#8254f8", 90, "#c2acfc"],
        "fill-extrusion-height": ["coalesce", ["get", "render_height"], 6],
        "fill-extrusion-base": ["coalesce", ["get", "render_min_height"], 0],
        "fill-extrusion-opacity": 0.88,
      },
    });
  }
  function pararOrbita(reg) {
    if (reg.raf) cancelAnimationFrame(reg.raf);
    reg.raf = null;
    if (reg.ui) reg.ui.parar.textContent = "Girar 360°";
  }
  function orbitar(reg) {
    pararOrbita(reg);
    const m = reg.m, ini = performance.now(), b0 = m.getBearing(), DUR = 12000;
    if (reg.ui) reg.ui.parar.textContent = "Parar voo";
    const passo = (t) => {
      const f = Math.min(1, (t - ini) / DUR);
      m.setBearing(b0 + 360 * f);
      if (f < 1 && reg.tres) reg.raf = requestAnimationFrame(passo);
      else pararOrbita(reg);
    };
    reg.raf = requestAnimationFrame(passo);
  }
  function ligar3D(reg, centro) {
    const m = reg.m;
    reg.tres = true;
    if (m.getLayer("predios-3d")) m.setLayoutProperty("predios-3d", "visibility", "visible");
    if (reg.ui) { reg.ui.btn.classList.add("ativo"); reg.ui.btn.textContent = "Sair do 3D"; reg.ui.ctrl.classList.add("on"); }
    if (reg === mapaAvaliar) arrumarPins();
    m.easeTo({ center: centro || m.getCenter(), pitch: 60, zoom: Math.max(m.getZoom(), reg === mapaAvaliar ? 16 : 15.5), bearing: m.getBearing() - 20, duration: 1800 });
    m.once("moveend", () => { if (reg.tres) orbitar(reg); });
  }
  function desligar3D(reg, imediato) {
    if (!reg.tres) return;
    pararOrbita(reg);
    reg.tres = false;
    const m = reg.m;
    if (m.getLayer("predios-3d")) m.setLayoutProperty("predios-3d", "visibility", "none");
    if (reg.ui) { reg.ui.btn.classList.remove("ativo"); reg.ui.btn.textContent = "Visão 3D"; reg.ui.ctrl.classList.remove("on"); }
    if (imediato) m.jumpTo({ pitch: 0, bearing: 0 });
    else m.easeTo({ pitch: 0, bearing: 0, duration: 900 });
    if (reg === mapaAvaliar) setTimeout(arrumarPins, 950);
  }
  function definirBase(reg, base) {
    basePreferida[reg.chave] = base;
    if (reg.m.getLayer("satelite")) reg.m.setLayoutProperty("satelite", "visibility", base === "satelite" ? "visible" : "none");
    $$(`[data-controle="base"][data-mapa="${reg.chave}"] button`).forEach((x) => x.classList.toggle("ativo", x.dataset.v === base));
    if (reg.ui) reg.ui.sat.classList.toggle("ativo", base === "satelite");
  }
  function montarControles3D(reg, area, centroFn) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-borda btn-3d";
    btn.textContent = "Visão 3D";
    const ctrl = document.createElement("div");
    ctrl.className = "ctrl-3d";
    ctrl.innerHTML = '<button type="button" class="btn-mini" data-3d="parar">Parar voo</button><button type="button" class="btn-mini" data-3d="sat">Satélite 3D</button><button type="button" class="btn-mini" data-3d="foto" title="Voo 360° com imagens 3D fotorrealistas (requer chave própria no .env local)">Voo fotorrealista</button>';
    area.append(btn, ctrl);
    reg.ui = { btn, ctrl, parar: ctrl.querySelector('[data-3d="parar"]'), sat: ctrl.querySelector('[data-3d="sat"]') };
    // Abre a página de voo 360° no ponto atual, levando o valor da última avaliação
    ctrl.querySelector('[data-3d="foto"]').addEventListener("click", () => {
      const [lng, lat] = centroFn(), d = estado.ultimoResultado && estado.ultimoResultado.dados;
      const val = reg.valor || (d && { v: d.preco_estimado_usd, min: d.faixa_provavel_usd?.minimo, max: d.faixa_provavel_usd?.maximo });
      const q = new URLSearchParams({ lat: lat.toFixed(6), lng: lng.toFixed(6), titulo: "Entorno do imóvel avaliado" });
      if (val && Number.isFinite(val.v)) {
        q.set("valor", Math.round(val.v));
        if (Number.isFinite(val.min) && Number.isFinite(val.max)) { q.set("faixa_min", Math.round(val.min)); q.set("faixa_max", Math.round(val.max)); }
      }
      window.open(`/visao3d?${q}`, "_blank", "noopener");
    });
    btn.addEventListener("click", () => (reg.tres ? desligar3D(reg) : ligar3D(reg, centroFn())));
    reg.ui.parar.addEventListener("click", () => (reg.raf ? pararOrbita(reg) : orbitar(reg)));
    reg.ui.sat.addEventListener("click", () => definirBase(reg, basePreferida[reg.chave] === "satelite" ? "mapa" : "satelite"));
  }
  function iniciar3DAvaliar() {
    if (!mapaAvaliar) return;
    montarControles3D(mapaAvaliar, $("#mapa-avaliar").parentElement, () => [estado.imovel.longitude, estado.imovel.latitude]);
    mapaAvaliar.ui.btn.addEventListener("click", () => { if (mapaAvaliar.tres && !resultadoAtual()) avaliarEstado(true); else if (mapaAvaliar.tres && estado.ultimoResultado && !popupAval) popupAvaliacao(estado.ultimoResultado.dados, estado.ultimoResultado.payload); });
  }

  // ---------------------------------------------------------------- partida
  window.addEventListener("resize", () => arrumarPins());
  sincronizarFormulario();
  atualizarBaseSimulador();
  atualizarChips();
  carregarRegioes();
  verificarSaude();
  setInterval(verificarSaude, 15000);
  atualizarAdmin();
  iniciarAcesso();
  rotear();
})();
