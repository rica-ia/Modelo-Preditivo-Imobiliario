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
      const resp = await fetch(caminho, {
        method: opcoes.metodo || "GET",
        headers: opcoes.corpo ? { "Content-Type": "application/json" } : undefined,
        body: opcoes.corpo ? JSON.stringify(opcoes.corpo) : undefined,
        cache: "no-store",
        signal: ctrl.signal,
      });
      let dados = null;
      try { dados = await resp.json(); } catch (e) { dados = null; }
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
  const basePreferida = { avaliar: "mapa", valor: "mapa" };
  window.__errosMapa = [];
  function criarMapa(chave, centro, zoom, depoisDoEstilo) {
    const m = new maplibregl.Map({
      container: "mapa-" + chave, style: estiloUrl(), center: centro, zoom,
      attributionControl: { compact: true }, dragRotate: false, pitchWithRotate: false, maxBounds: LIMITE_MAPA,
    });
    m.touchZoomRotate.disableRotation();
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");
    const reg = { m, chave, tema: escuroAtivo(), depoisDoEstilo };
    m.on("style.load", () => { adicionarSatelite(reg); if (reg.depoisDoEstilo) reg.depoisDoEstilo(); });
    m.on("error", (e) => { window.__errosMapa.push(String((e && e.error && e.error.message) || e)); });
    // Alguns estilos citam padrões de preenchimento ausentes do sprite: um pixel transparente evita o aviso.
    m.on("styleimagemissing", (e) => { if (!m.hasImage(e.id)) m.addImage(e.id, { width: 1, height: 1, data: new Uint8Array(4) }); });
    mapas.push(reg);
    return reg;
  }
  function adicionarSatelite(reg) {
    const m = reg.m;
    if (!m.getSource("satelite")) m.addSource("satelite", { type: "raster", tiles: [ESRI], tileSize: 256, maxzoom: 19, attribution: "Imagens: Esri, Maxar, Earthstar Geographics" });
    const rotulos = (m.getStyle().layers || []).find((l) => l.type === "symbol");
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
    if (reg && reg.m.getLayer("satelite")) reg.m.setLayoutProperty("satelite", "visibility", b.dataset.v === "satelite" ? "visible" : "none");
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
  function rotear() {
    const nome = (location.hash || "#inicio").slice(1) || "inicio";
    const alvo = $(`.view[data-view="${nome}"]`) ? nome : "inicio";
    $$(".view").forEach((v) => { v.hidden = v.dataset.view !== alvo; });
    $$(".nav a").forEach((a) => a.classList.toggle("ativo", a.dataset.nav === alvo));
    const ativo = $(`.nav a[data-nav="${alvo}"]`);
    if (ativo && ativo.scrollIntoView && window.innerWidth <= 720) ativo.scrollIntoView({ block: "nearest", inline: "center" });
    if (!rotear.semRolagem) window.scrollTo({ top: 0 });
    rotear.semRolagem = false;
    const init = { avaliar: initAvaliar, simulador: initSimulador, mapa: initMapa, modelo: initModelo, dev: initDev, inicio: initInicio }[alvo];
    if (!inicializadas.has(alvo)) { inicializadas.add(alvo); init && init(); }
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
      selo.querySelector("span").textContent = `API no ar · modelo ${d.versao_modelo || ""} na memória${d.uptime_s !== undefined ? " há " + fmtUptime(d.uptime_s) : ""}`;
    } else if (r.ok) {
      selo.className = "selo off";
      selo.querySelector("span").textContent = "API no ar · modelo não carregado";
    } else {
      selo.className = "selo off";
      selo.querySelector("span").textContent = "API indisponível";
    }
  }
  async function initInicio() {
    verificarSaude();
    setInterval(verificarSaude, 15000);
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
  function prever(payload) {
    return api("/v1/predict", { metodo: "POST", corpo: payload });
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
        <p class="res-local">${esc(num(payload.area_util_m2))} m² · ${esc(payload.quartos)} quartos · CEP ${esc(payload.cep)} · ${num(payload.latitude, 4)}, ${num(payload.longitude, 4)}</p></div>
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
      <p class="ref">${esc(d.referencia_mercado || "")}</p>`;
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
  function atualizarChips() {
    const v = estado.imovel;
    const preco = resultadoAtual() ? `<span class="preco">${usd.format(estado.ultimoResultado.dados.preco_estimado_usd)}</span>` : "";
    $("#chips-imovel").innerHTML = `${preco}<span>${num(v.area_util_m2)} m²</span><span>${v.quartos} quartos</span><span>${num(v.banheiros, v.banheiros % 1 ? 2 : 0)} banheiros</span><span>CEP ${esc(v.cep)}</span>`;
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
      if (camadaAvaliar === "valor") { p.el.style.display = "none"; return; }
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
    const r = await api("/v1/predict/lote", { metodo: "POST", corpo: { imoveis: lista.map((c) => c.dados) } });
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
      const r = await api(e.rota, { metodo: e.metodo, corpo: e.corpo ? e.corpo() : undefined, timeout: 8000 });
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
    $("#cod-curl").textContent = `curl -X POST "${base}/v1/predict" \\\n  -H "Content-Type: application/json" \\\n  -d '${JSON.stringify(exemplo)}'`;
    $("#cod-py").textContent = `import requests\n\nimovel = ${json.replace(/\btrue\b/g, "True").replace(/\bfalse\b/g, "False").replace(/\bnull\b/g, "None")}\n\nresposta = requests.post("${base}/v1/predict", json=imovel, timeout=10)\nresposta.raise_for_status()\nprint(resposta.json()["preco_estimado_usd"])`;
    $$("[data-copiar]").forEach((b) => b.addEventListener("click", async () => {
      const texto = $("#" + b.dataset.copiar).textContent;
      try { await navigator.clipboard.writeText(texto); toast("Copiado para a área de transferência"); }
      catch (e) { toast("Não foi possível copiar automaticamente"); }
    }));
  }

  // ---------------------------------------------------------------- partida
  window.addEventListener("resize", () => arrumarPins());
  sincronizarFormulario();
  atualizarBaseSimulador();
  atualizarChips();
  carregarRegioes();
  if (!inicializadas.has("inicio")) { inicializadas.add("inicio"); initInicio(); }
  rotear();
})();
