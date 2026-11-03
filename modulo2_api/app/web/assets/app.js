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

  /** Chamada HTTP com tempo-limite; devolve {ok, status, dados} e nunca lança. */
  async function api(caminho, opcoes = {}) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), opcoes.timeout || 12000);
    try {
      const resp = await fetch(caminho, {
        method: opcoes.metodo || "GET",
        headers: opcoes.corpo ? { "Content-Type": "application/json" } : undefined,
        body: opcoes.corpo ? JSON.stringify(opcoes.corpo) : undefined,
        signal: ctrl.signal,
      });
      let dados = null;
      try { dados = await resp.json(); } catch (e) { dados = null; }
      return { ok: resp.ok, status: resp.status, dados };
    } catch (e) {
      return { ok: false, status: 0, dados: null };
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
  async function carregarRegioes() {
    if (cache.regioes) return cache.regioes;
    const r = await api("/v1/regioes");
    const lista = r.ok ? (Array.isArray(r.dados) ? r.dados : r.dados && r.dados.regioes) : null;
    if (Array.isArray(lista)) cache.regioes = lista.map((g) => ({ ...g, cep: String(g.cep), latitude: Number(g.latitude), longitude: Number(g.longitude) }));
    return cache.regioes;
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

  // ---------------------------------------------------------------- tema
  function temaAtual() {
    try { return localStorage.getItem("ai-tema") || "auto"; } catch (e) { return "auto"; }
  }
  function escuroAtivo() {
    const t = document.documentElement.getAttribute("data-theme");
    if (t === "dark") return true;
    if (t === "light") return false;
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  }
  function aplicarTema(t) {
    if (t === "light" || t === "dark") document.documentElement.setAttribute("data-theme", t);
    else document.documentElement.removeAttribute("data-theme");
    try { localStorage.setItem("ai-tema", t); } catch (e) {}
    $$(".tema button").forEach((b) => b.classList.toggle("ativo", b.dataset.tema === t));
    aoMudarTema();
  }
  $$(".tema button").forEach((b) => b.addEventListener("click", () => aplicarTema(b.dataset.tema)));
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (temaAtual() === "auto") aoMudarTema(); });
  $$(".tema button").forEach((b) => b.classList.toggle("ativo", b.dataset.tema === temaAtual()));

  function aoMudarTema() {
    mapas.forEach(pintarBase);
    if (mapaValor && mapaValor.getLayer("ceps")) pintarCirculos();
    if (graficos.sim) desenharSimulacao(ultimaSimulacao);
    if (graficos.imp && cache.modelo) desenharImportancia(cache.modelo);
    if (graficos.ranking) desenharRanking();
  }

  // ---------------------------------------------------------------- mapas (MapLibre)
  // Base raster do OpenStreetMap, sem chave. No tema escuro a própria camada raster
  // é invertida pelas propriedades de pintura, sem afetar círculos e marcadores.
  const mapas = [];
  function estiloBase() {
    return {
      version: 8,
      sources: { base: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, maxzoom: 19, attribution: "© OpenStreetMap" } },
      layers: [{ id: "base", type: "raster", source: "base", paint: pinturaBase() }],
    };
  }
  function pinturaBase() {
    return escuroAtivo()
      ? { "raster-brightness-min": 1, "raster-brightness-max": 0.08, "raster-hue-rotate": 180, "raster-saturation": -0.55, "raster-contrast": 0.05 }
      : { "raster-brightness-min": 0, "raster-brightness-max": 1, "raster-hue-rotate": 0, "raster-saturation": -0.2, "raster-contrast": 0 };
  }
  function pintarBase(m) {
    if (!m.getLayer("base")) return;
    Object.entries(pinturaBase()).forEach(([k, v]) => m.setPaintProperty("base", k, v));
  }
  function criarMapa(id, centro, zoom) {
    const m = new maplibregl.Map({ container: id, style: estiloBase(), center: centro, zoom, attributionControl: { compact: true } });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
    mapas.push(m);
    return m;
  }
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

  // ---------------------------------------------------------------- roteamento
  const inicializadas = new Set();
  function rotear() {
    const nome = (location.hash || "#inicio").slice(1) || "inicio";
    const alvo = $(`.view[data-view="${nome}"]`) ? nome : "inicio";
    $$(".view").forEach((v) => { v.hidden = v.dataset.view !== alvo; });
    $$(".nav a").forEach((a) => a.classList.toggle("ativo", a.dataset.nav === alvo));
    const ativo = $(`.nav a[data-nav="${alvo}"]`);
    if (ativo && ativo.scrollIntoView) ativo.scrollIntoView({ block: "nearest", inline: "center" });
    if (!rotear.semRolagem) window.scrollTo({ top: 0 });
    rotear.semRolagem = false;
    const init = { avaliar: initAvaliar, simulador: initSimulador, mapa: initMapa, modelo: initModelo, dev: initDev, inicio: initInicio }[alvo];
    if (!inicializadas.has(alvo)) { inicializadas.add(alvo); init && init(); }
    setTimeout(() => mapas.forEach((m) => m.resize()), 60);
  }
  window.addEventListener("hashchange", rotear);
  function irPara(view, semRolagem) {
    rotear.semRolagem = !!semRolagem;
    if (location.hash === "#" + view) rotear();
    else location.hash = "#" + view;
  }

  // ---------------------------------------------------------------- saúde da API
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
      selo.querySelector("span").textContent = `API no ar · modelo ${d.versao_modelo || ""} na memória`;
    } else if (r.ok) {
      selo.className = "selo off";
      selo.querySelector("span").textContent = "API no ar · modelo não carregado";
    } else {
      selo.className = "selo off";
      selo.querySelector("span").textContent = "API indisponível";
    }
    if (d.uptime_s !== undefined) $("#kpi-uptime").textContent = fmtUptime(d.uptime_s);
    if (d.versao_modelo) $("#kpi-versao").textContent = d.versao_modelo;
  }

  async function initInicio() {
    verificarSaude();
    setInterval(verificarSaude, 15000);
    const m = await carregarModelo();
    if (!m) return;
    const teste = (m.metricas && m.metricas.teste) || {};
    if (teste.R2 !== undefined) $("#kpi-r2").textContent = num(teste.R2, 3);
    if (teste.MAPE !== undefined) $("#kpi-mape").textContent = pct(teste.MAPE);
    if (m.versao) $("#kpi-versao").textContent = m.versao;
    if (m.algoritmo) $("#kpi-algoritmo").textContent = m.algoritmo;
  }

  // ---------------------------------------------------------------- formulário (espelho do estado)
  const form = $("#form-imovel");
  function atualizarSaidas() {
    $$("output[data-out]", form).forEach((o) => {
      const v = form.elements[o.dataset.out].value;
      o.textContent = o.dataset.out.endsWith("_m2") ? `${num(v)} m²` : v;
    });
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
  ouvir((origem) => { if (!String(origem).startsWith("form")) sincronizarFormulario(); });

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
  async function prever(payload) {
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
      return;
    }
    const lista = detalhesErro(r.dados);
    marcarErros(lista);
    caixa.innerHTML = alertaHTML(r.status ? tituloErro(r.status) : "API indisponível", mensagemErro(r), lista, r.status >= 500 ? "" : "aviso");
    if (comPopup && popupAval) popupAval.remove();
  }
  form.addEventListener("submit", (ev) => { ev.preventDefault(); avaliarEstado(true); });

  function comparativoCep(d, payload) {
    const regiao = regiaoDoCep(payload.cep);
    if (!regiao || !regiao.preco_m2_mediano_usd || !d.preco_por_m2_usd) return { texto: "—", classe: "" };
    const dif = Number(d.preco_por_m2_usd) / Number(regiao.preco_m2_mediano_usd) - 1;
    return { texto: `${dif >= 0 ? "+" : ""}${num(dif * 100, 1)} %`, classe: dif >= 0 ? "pos" : "neg", regiao };
  }
  function mostrarResultado(d, payload) {
    const preco = Number(d.preco_estimado_usd);
    const fx = d.faixa_provavel_usd || {};
    const min = Number(fx.minimo ?? preco), max = Number(fx.maximo ?? preco);
    const pos = max > min ? Math.min(100, Math.max(0, ((preco - min) / (max - min)) * 100)) : 50;
    const comp = comparativoCep(d, payload);
    $("#resultado").innerHTML = `
      <div class="res-rotulo">VALOR ESTIMADO</div>
      <div class="res-preco">${usd.format(preco)}</div>
      <div class="res-sub">${esc(payload.area_util_m2)} m² · ${esc(payload.quartos)} quartos · CEP ${esc(payload.cep)}</div>
      <div class="faixa">
        <div class="res-rotulo">FAIXA PROVÁVEL</div>
        <div class="faixa-barra"><div class="faixa-ponto" style="left:${pos}%"></div></div>
        <div class="faixa-valores"><span>${usd.format(min)}</span><span>${usd.format(max)}</span></div>
      </div>
      <div class="res-grade">
        <div class="res-item"><small>US$ por m²</small><b>${d.preco_por_m2_usd ? usd.format(d.preco_por_m2_usd) : "—"}</b></div>
        <div class="res-item"><small>vs. mediana do CEP ${esc(payload.cep)}${comp.regiao ? " (" + usd.format(comp.regiao.preco_m2_mediano_usd) + "/m²)" : ""}</small><b class="${comp.classe}">${comp.texto}</b></div>
        <div class="res-item"><small>Tempo de resposta</small><b>${d.latencia_ms !== undefined ? num(d.latencia_ms, 1) + " ms" : "—"}</b></div>
      </div>
      <p class="ref">${esc(d.referencia_mercado || "")}${d.versao_modelo ? " · modelo " + esc(d.versao_modelo) : ""}</p>`;
  }

  // ---------------------------------------------------------------- mapa da avaliação
  let mapaAvaliar = null, marcador = null, popupAval = null;
  function moverMarcador(lat, lon) {
    if (!mapaAvaliar) return;
    if (!marcador) {
      const el = document.createElement("div");
      el.className = "marcador-imovel";
      marcador = new maplibregl.Marker({ element: el }).setLngLat([lon, lat]).addTo(mapaAvaliar);
    } else marcador.setLngLat([lon, lat]);
  }
  function popupAvaliacao(d, payload) {
    if (!mapaAvaliar) return;
    if (popupAval) popupAval.remove();
    const fx = d.faixa_provavel_usd || {};
    popupAval = new maplibregl.Popup({ maxWidth: "280px", offset: 16 })
      .setLngLat([payload.longitude, payload.latitude])
      .setHTML(`<span class="pop-sub">Valor estimado · CEP ${esc(payload.cep)}</span><span class="pop-preco">${usd.format(d.preco_estimado_usd)}</span><span class="pop-sub">Faixa: ${usd.format(fx.minimo)} – ${usd.format(fx.maximo)}</span>`)
      .addTo(mapaAvaliar);
  }
  async function initAvaliar() {
    sincronizarFormulario();
    if (temMapa()) {
      mapaAvaliar = criarMapa("mapa-avaliar", [estado.imovel.longitude, estado.imovel.latitude], 11);
      moverMarcador(estado.imovel.latitude, estado.imovel.longitude);
      mapaAvaliar.on("click", (e) => {
        const lat = arred(e.lngLat.lat), lon = arred(e.lngLat.lng);
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
    }
    if (estado.ultimoResultado) mostrarResultado(estado.ultimoResultado.dados, estado.ultimoResultado.payload);
  }
  ouvir((origem) => {
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
    $("#sim-base").textContent = `${b.area_util_m2} m² · ${b.quartos} quartos · ${b.banheiros} banheiros · padrão ${b.padrao_construtivo} · CEP ${b.cep}`;
  }
  ouvir(atualizarBaseSimulador);
  function initSimulador() {
    $("#btn-simular").addEventListener("click", () => { estado.cenarioAplicado = null; simular(); });
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
      $("#sim-tabela").innerHTML = alertaHTML(r.status ? `Não foi possível simular (${r.status})` : "Sem conexão", r.status === 0 ? "API indisponível. Inicie o servidor e tente de novo." : mensagemErro(r), detalhesErro(r.dados), "aviso");
      return;
    }
    const precos = r.dados.previsoes.map((p) => Number(p.preco_estimado_usd));
    ultimaSimulacao = lista.map((c, i) => ({ nome: c.nome, dados: c.dados, previsao: r.dados.previsoes[i], preco: precos[i], delta: precos[i] - precos[0], rel: precos[i] / precos[0] - 1 }));
    desenharSimulacao(ultimaSimulacao);
  }
  function aplicarCenario(i) {
    const c = ultimaSimulacao && ultimaSimulacao[i];
    if (!c || i === 0) return;
    atualizarEstado({ ...c.dados }, "simulador");
    estado.cenarioAplicado = i;
    estado.ultimoResultado = { dados: c.previsao, payload: { ...c.dados } };
    mostrarResultado(c.previsao, c.dados);
    desenharSimulacao(ultimaSimulacao);
    toast(`Cenário "${c.nome}" aplicado ao formulário de avaliação`);
  }
  function desenharSimulacao(res) {
    if (!res) return;
    const itens = res.slice(1);
    const ativo = estado.cenarioAplicado;
    if (temGrafico()) {
      const corPos = cssVar("--accent-2"), corNeg = cssVar("--bad"), corAtiva = cssVar("--accent"), texto = cssVar("--muted"), linha = cssVar("--line"), borda = cssVar("--text");
      if (graficos.sim) graficos.sim.destroy();
      graficos.sim = new Chart($("#graf-sim"), {
        type: "bar",
        data: {
          labels: itens.map((x, i) => (ativo === i + 1 ? "✓ " : "") + x.nome),
          datasets: [{
            data: itens.map((x) => Math.round(x.delta)),
            backgroundColor: itens.map((x, i) => (ativo === i + 1 ? corAtiva : x.delta >= 0 ? corPos : corNeg)),
            borderColor: itens.map((x, i) => (ativo === i + 1 ? borda : "transparent")),
            borderWidth: itens.map((x, i) => (ativo === i + 1 ? 2 : 0)),
            borderRadius: 10, maxBarThickness: 46,
          }],
        },
        options: {
          indexAxis: "y", responsive: true, maintainAspectRatio: false,
          // Adia o redesenho: destruir o gráfico dentro do próprio evento de clique quebra o Chart.js.
          onClick: (ev, els) => { if (els.length) { const i = els[0].index + 1; setTimeout(() => aplicarCenario(i), 0); } },
          onHover: (ev, els) => { ev.native.target.style.cursor = els.length ? "pointer" : "default"; },
          plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${usd.format(c.raw)} (${num(itens[c.dataIndex].rel * 100, 1)} %) · clique para aplicar` } } },
          scales: { x: { ticks: { color: texto, callback: (v) => usd.format(v) }, grid: { color: linha } }, y: { ticks: { color: texto }, grid: { display: false } } },
        },
      });
    }
    $("#sim-tabela").innerHTML = `<table class="tabela"><thead><tr><th>Cenário</th><th>Preço estimado</th><th>Variação</th></tr></thead><tbody>${res.map((x, i) => `
      <tr class="${ativo === i ? "ativo" : ""}"><td>${esc(x.nome)}${ativo === i ? " · aplicado ao formulário" : ""}</td><td>${usd.format(x.preco)}</td><td class="${i === 0 ? "" : x.delta >= 0 ? "pos" : "neg"}">${i === 0 ? "referência" : `${x.delta >= 0 ? "+" : ""}${usd.format(x.delta)} (${num(x.rel * 100, 1)} %)`}</td></tr>`).join("")}</tbody></table>`;
  }

  // ---------------------------------------------------------------- mapa de valor + ranking
  let mapaValor = null, cepDestacado = null, popupValor = null, rankingOrdem = [];
  const ESCALA = ["#c9f2f6", "#8ce1ea", "#3fc3d3", "#1a93a6", "#0f5f73"];
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
  function pintarCirculos() {
    const vals = cache.regioes.map((g) => Number(g.preco_m2_mediano_usd));
    const cortes = quantis(vals, ESCALA.length);
    const passos = ["step", ["get", "pm2"], ESCALA[0]];
    cortes.forEach((c, i) => passos.push(c, ESCALA[i + 1]));
    const maxV = Math.max(...cache.regioes.map((g) => Number(g.vendas) || 1));
    const borda = escuroAtivo() ? "rgba(255,255,255,0.55)" : "rgba(15,76,100,0.55)";
    const destaque = "#ff9f0a";
    mapaValor.setPaintProperty("ceps", "circle-color", passos);
    mapaValor.setPaintProperty("ceps", "circle-radius", ["interpolate", ["linear"], ["sqrt", ["/", ["get", "vendas"], maxV]], 0, 6, 1, 20]);
    mapaValor.setPaintProperty("ceps", "circle-stroke-color", ["case", ["boolean", ["feature-state", "destaque"], false], destaque, borda]);
    mapaValor.setPaintProperty("ceps", "circle-stroke-width", ["case", ["boolean", ["feature-state", "destaque"], false], 4, ["boolean", ["feature-state", "hover"], false], 2.5, 1]);
    const faixas = [Math.min(...vals), ...cortes, Math.max(...vals)];
    $("#legenda-mapa").innerHTML = "<b>US$/m² mediano:</b>" + ESCALA.map((c, i) => `<span><i style="background:${c}"></i>${usd.format(faixas[i])}–${usd.format(faixas[i + 1])}</span>`).join("");
  }
  function destacarCep(cep, { voar = false, origem = "" } = {}) {
    cep = cep ? String(cep) : null;
    if (mapaValor && mapaValor.getSource("ceps")) {
      if (cepDestacado) mapaValor.setFeatureState({ source: "ceps", id: cepDestacado }, { destaque: false });
      if (cep) mapaValor.setFeatureState({ source: "ceps", id: cep }, { destaque: true });
      const g = regiaoDoCep(cep);
      if (voar && g) mapaValor.flyTo({ center: [g.longitude, g.latitude], zoom: Math.max(mapaValor.getZoom(), 11.5), speed: 1.2 });
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
      .setHTML(`<b>CEP ${esc(g.cep)}</b><br>Preço mediano: ${usd.format(g.preco_mediano_usd)}<br>Mediana por m²: ${usd.format(g.preco_m2_mediano_usd)}<br>Vendas: ${num(g.vendas)}`)
      .addTo(mapaValor);
  }
  function selecionarCepNoMapa(cep, voar, origem) {
    const g = regiaoDoCep(cep);
    if (!g) return;
    atualizarEstado({ cep: g.cep, latitude: arred(g.latitude), longitude: arred(g.longitude) }, "mapa-valor");
    destacarCep(g.cep, { voar, origem });
    popupCep(g);
  }
  async function estimarNoPonto(lngLat) {
    const lat = arred(lngLat.lat), lon = arred(lngLat.lng);
    const g = cepMaisProximo(lat, lon);
    if (!g) return;
    const payload = { ...estado.imovel, latitude: lat, longitude: lon, cep: g.cep };
    if (popupValor) popupValor.remove();
    popupValor = new maplibregl.Popup({ maxWidth: "280px", offset: 10 }).setLngLat([lon, lat]).setHTML('<span class="pop-sub"><span class="carregando"></span> Estimando…</span>').addTo(mapaValor);
    const r = await prever(payload);
    if (!popupValor) return;
    if (!r.ok || !r.dados) {
      popupValor.setHTML(`<b>${esc(r.status ? tituloErro(r.status) : "API indisponível")}</b><br><span class="pop-sub">${esc(mensagemErro(r))}</span>`);
      return;
    }
    const d = r.dados, fx = d.faixa_provavel_usd || {};
    popupValor.setHTML(`<span class="pop-sub">Imóvel do formulário neste local · CEP ${esc(g.cep)}</span><span class="pop-preco">${usd.format(d.preco_estimado_usd)}</span><span class="pop-sub">Faixa: ${usd.format(fx.minimo)} – ${usd.format(fx.maximo)}</span><br><button class="pop-btn" type="button">Abrir na avaliação</button>`);
    destacarCep(g.cep, { origem: "ponto" });
    const btn = popupValor.getElement().querySelector(".pop-btn");
    btn.addEventListener("click", () => {
      popupValor.remove();
      popupValor = null;
      estado.cenarioAplicado = null;
      atualizarEstado({ latitude: lat, longitude: lon, cep: g.cep }, "abrir-avaliacao");
      estado.ultimoResultado = { dados: d, payload };
      irPara("avaliar");
      setTimeout(() => {
        mostrarResultado(d, payload);
        if (mapaAvaliar) { mapaAvaliar.jumpTo({ center: [lon, lat], zoom: 12 }); popupAvaliacao(d, payload); }
      }, 250);
    });
  }
  async function initMapa() {
    const regioes = await carregarRegioes();
    if (!regioes || !regioes.length) { $("#legenda-mapa").textContent = "Dados de regiões indisponíveis: verifique se a API está no ar."; return; }
    desenharRanking();
    destacarCep(estado.cep, {});
    if (!temMapa()) { $("#mapa-valor").innerHTML = '<div class="vazio">Mapa indisponível sem conexão com a internet.</div>'; return; }
    mapaValor = criarMapa("mapa-valor", [-122.2, 47.5], 9.4);
    mapaValor.on("load", () => {
      mapaValor.addSource("ceps", { type: "geojson", data: geojsonCeps(regioes), promoteId: "cep" });
      mapaValor.addLayer({ id: "ceps", type: "circle", source: "ceps", paint: { "circle-opacity": 0.85 } });
      pintarCirculos();
      destacarCep(estado.cep, {});
      let hover = null;
      mapaValor.on("mousemove", "ceps", (e) => {
        mapaValor.getCanvas().style.cursor = "pointer";
        const id = e.features[0].properties.cep;
        if (hover && hover !== id) mapaValor.setFeatureState({ source: "ceps", id: hover }, { hover: false });
        hover = id;
        mapaValor.setFeatureState({ source: "ceps", id }, { hover: true });
        if (graficos.ranking) { rankingHover = id; desenharRanking(); }
      });
      mapaValor.on("mouseleave", "ceps", () => {
        mapaValor.getCanvas().style.cursor = "";
        if (hover) mapaValor.setFeatureState({ source: "ceps", id: hover }, { hover: false });
        hover = null;
        if (graficos.ranking) { rankingHover = null; desenharRanking(); }
      });
      mapaValor.on("click", (e) => {
        const f = mapaValor.queryRenderedFeatures(e.point, { layers: ["ceps"] });
        if (f.length) selecionarCepNoMapa(f[0].properties.cep, false, "mapa");
        else estimarNoPonto(e.lngLat);
      });
    });
  }
  let rankingHover = null;
  function desenharRanking() {
    if (!temGrafico() || !cache.regioes) return;
    rankingOrdem = cache.regioes.slice().sort((a, b) => b.preco_m2_mediano_usd - a.preco_m2_mediano_usd);
    $("#ranking-alto").style.height = `${rankingOrdem.length * 22 + 40}px`;
    const vals = cache.regioes.map((g) => Number(g.preco_m2_mediano_usd));
    const cortes = quantis(vals, ESCALA.length);
    const cor = (v) => ESCALA[cortes.filter((c) => v > c).length];
    const texto = cssVar("--muted"), linha = cssVar("--line"), forte = cssVar("--text");
    const dados = {
      labels: rankingOrdem.map((g) => g.cep),
      datasets: [{
        data: rankingOrdem.map((g) => Math.round(g.preco_m2_mediano_usd)),
        backgroundColor: rankingOrdem.map((g) => (g.cep === cepDestacado ? "#ff9f0a" : cor(g.preco_m2_mediano_usd))),
        borderColor: rankingOrdem.map((g) => (g.cep === cepDestacado || g.cep === rankingHover ? forte : "transparent")),
        borderWidth: rankingOrdem.map((g) => (g.cep === cepDestacado ? 2 : g.cep === rankingHover ? 1.5 : 0)),
        borderRadius: 5, barThickness: 14,
      }],
    };
    if (graficos.ranking) { graficos.ranking.data = dados; graficos.ranking.options.scales.x.ticks.color = texto; graficos.ranking.options.scales.y.ticks.color = texto; graficos.ranking.options.scales.x.grid.color = linha; graficos.ranking.update("none"); return; }
    graficos.ranking = new Chart($("#graf-ranking"), {
      type: "bar", data: dados,
      options: {
        indexAxis: "y", responsive: true, maintainAspectRatio: false, animation: false,
        onClick: (ev, els) => { if (els.length) selecionarCepNoMapa(rankingOrdem[els[0].index].cep, true, "ranking"); },
        onHover: (ev, els) => {
          ev.native.target.style.cursor = els.length ? "pointer" : "default";
          const id = els.length ? rankingOrdem[els[0].index].cep : null;
          if (mapaValor && mapaValor.getSource("ceps") && id !== rankingHover) {
            if (rankingHover) mapaValor.setFeatureState({ source: "ceps", id: rankingHover }, { hover: false });
            if (id) mapaValor.setFeatureState({ source: "ceps", id }, { hover: true });
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
    return `<div class="cartao metrica-cartao${destaque ? " destaque" : ""}"><h3>${esc(titulo)} <span>${esc(extra || "")}</span></h3>
      <div class="metrica-linhas"><div><small>R²</small><b>${v("R2")}</b></div><div><small>MAPE</small><b>${v("MAPE")}</b></div>
      <div><small>MAE</small><b>${v("MAE")}</b></div><div><small>RMSE</small><b>${v("RMSE")}</b></div></div></div>`;
  }
  function relativo(v) {
    v = Number(v);
    return v > 0.3 && v < 3 ? (v - 1) * 100 : v * 100;
  }
  async function initModelo() {
    const m = await carregarModelo();
    if (!m) { $("#metricas-cartoes").innerHTML = `<div class="cartao">${alertaHTML("Métricas indisponíveis", "Não foi possível ler /v1/modelo. Confirme que a API está no ar.", [], "aviso")}</div>`; return; }
    const met = m.metricas || {};
    const base = m.baseline && m.baseline.R2 === undefined ? (m.baseline.teste || m.baseline.validacao) : m.baseline;
    const div = m.divisao || {};
    $("#modelo-sub").textContent = `${m.algoritmo || "Modelo"} · versão ${m.versao || "—"}${m.treinado_em ? " · treinado em " + new Date(m.treinado_em).toLocaleDateString("pt-BR") : ""}. Métricas calculadas em dados que o modelo nunca viu durante o treino.`;
    $("#metricas-cartoes").innerHTML = blocoMetricas("Validação", met.validacao, div.validacao ? `${num(div.validacao)} imóveis` : "", false)
      + blocoMetricas("Teste (prova final)", met.teste, div.teste ? `${num(div.teste)} imóveis` : "", true)
      + blocoMetricas("Baseline pela média", base, "referência mínima", false);
    const total = (Number(div.treino) || 0) + (Number(div.validacao) || 0) + (Number(div.teste) || 0);
    if (total) {
      const partes = [["Treino", div.treino, "#0f4c64"], ["Validação", div.validacao, "#1a93a6"], ["Teste", div.teste, "#1baf7a"]];
      $("#modelo-divisao").innerHTML = partes.map(([n, q, c]) => `<div style="width:${(q / total) * 100}%;background:${c}">${n} ${num((q / total) * 100, 0)}%</div>`).join("");
    }
    if (m.faixa_erro && m.faixa_erro.p10 !== undefined) {
      const a = relativo(m.faixa_erro.p10), b = relativo(m.faixa_erro.p90);
      $("#modelo-faixa").textContent = `Faixa provável: 80 % dos imóveis de validação ficaram entre ${a >= 0 ? "+" : ""}${num(a, 1)} % e ${b >= 0 ? "+" : ""}${num(b, 1)} % do preço estimado.`;
    }
    desenharImportancia(m);
  }
  function desenharImportancia(m) {
    const imp = (m.importancia || []).slice().sort((a, b) => b.importancia - a.importancia).slice(0, 12);
    if (!imp.length || !temGrafico()) return;
    if (graficos.imp) graficos.imp.destroy();
    const texto = cssVar("--muted"), linha = cssVar("--line"), cor = cssVar("--accent");
    graficos.imp = new Chart($("#graf-imp"), {
      type: "bar",
      data: { labels: imp.map((x) => x.variavel), datasets: [{ data: imp.map((x) => x.importancia), backgroundColor: cor, borderRadius: 8, maxBarThickness: 24 }] },
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
  sincronizarFormulario();
  atualizarBaseSimulador();
  carregarRegioes();
  if (!inicializadas.has("inicio")) { inicializadas.add("inicio"); initInicio(); }
  rotear();
})();
