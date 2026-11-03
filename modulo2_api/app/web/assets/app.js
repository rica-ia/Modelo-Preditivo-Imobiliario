/* Avaliador Imobiliário — lógica do portal (SPA por hash, sem framework).
   Toda chamada é same-origin para a própria API FastAPI. */
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

  function toast(msg) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.add("on");
    clearTimeout(toast.t);
    toast.t = setTimeout(() => el.classList.remove("on"), 2600);
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
    if (r.ok && Array.isArray(r.dados)) cache.regioes = r.dados;
    else if (r.ok && r.dados && Array.isArray(r.dados.regioes)) cache.regioes = r.dados.regioes;
    return cache.regioes;
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

  const camadasBase = [];
  // Tiles do OpenStreetMap; no tema escuro o CSS inverte as cores do mapa.
  function urlTiles() {
    return "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  }
  function aoMudarTema() {
    camadasBase.forEach((c) => c.setUrl(urlTiles()));
    if (graficos.sim) desenharSimulacao(ultimaSimulacao);
    if (graficos.imp && cache.modelo) desenharImportancia(cache.modelo);
    if (mapaValor && cache.regioes) desenharMapaValor(cache.regioes);
  }

  // ---------------------------------------------------------------- roteamento
  const inicializadas = new Set();
  function rotear() {
    const nome = (location.hash || "#inicio").slice(1) || "inicio";
    const alvo = $(`.view[data-view="${nome}"]`) ? nome : "inicio";
    $$(".view").forEach((v) => { v.hidden = v.dataset.view !== alvo; });
    $$(".nav a").forEach((a) => a.classList.toggle("ativo", a.dataset.nav === alvo));
    const ativo = $(`.nav a[data-nav="${alvo}"]`);
    if (ativo && ativo.scrollIntoView) ativo.scrollIntoView({ block: "nearest", inline: "center" });
    window.scrollTo({ top: 0 });
    const init = { avaliar: initAvaliar, simulador: initSimulador, mapa: initMapa, modelo: initModelo, dev: initDev, inicio: initInicio }[alvo];
    if (!inicializadas.has(alvo)) { inicializadas.add(alvo); init && init(); }
    else if (alvo === "simulador") atualizarBaseSimulador();
    setTimeout(() => {
      if (alvo === "avaliar" && mapaAvaliar) mapaAvaliar.invalidateSize();
      if (alvo === "mapa" && mapaValor) mapaValor.invalidateSize();
    }, 60);
  }
  window.addEventListener("hashchange", rotear);

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

  // ---------------------------------------------------------------- início
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

  // ---------------------------------------------------------------- formulário
  const form = $("#form-imovel");
  const PADRAO = {
    quartos: 3, banheiros: 2, area_util_m2: 170, area_terreno_m2: 700, andares: "1", area_porao_m2: 0,
    ano_construcao: 1990, ano_reforma: "", padrao_construtivo: 7, condicao: "3", vista: "0", frente_agua: false,
    cep: "98103", latitude: 47.67, longitude: -122.34,
  };

  function atualizarSaidas() {
    $$("output[data-out]", form).forEach((o) => {
      const v = form.elements[o.dataset.out].value;
      o.textContent = o.dataset.out.endsWith("_m2") ? `${num(v)} m²` : v;
    });
  }
  function definirValores(v) {
    Object.entries(v).forEach(([k, val]) => {
      const el = form.elements[k];
      if (!el) return;
      if (el instanceof RadioNodeList) { el.value = String(val); return; }
      if (el.type === "checkbox") el.checked = !!val;
      else el.value = val;
    });
    atualizarSaidas();
  }
  function lerPayload() {
    const f = form.elements;
    const n = (k) => Number(f[k].value);
    const reforma = f.ano_reforma.value.trim();
    return {
      quartos: n("quartos"),
      banheiros: n("banheiros"),
      area_util_m2: n("area_util_m2"),
      area_terreno_m2: n("area_terreno_m2"),
      andares: n("andares"),
      frente_agua: f.frente_agua.checked,
      vista: Number(f.vista.value),
      condicao: Number(f.condicao.value),
      padrao_construtivo: n("padrao_construtivo"),
      area_porao_m2: n("area_porao_m2"),
      ano_construcao: n("ano_construcao"),
      ano_reforma: reforma === "" ? null : Number(reforma),
      cep: String(f.cep.value),
      latitude: n("latitude"),
      longitude: n("longitude"),
    };
  }
  form.addEventListener("input", atualizarSaidas);
  $$(".stepper button", form).forEach((b) => b.addEventListener("click", () => {
    const el = form.elements[b.dataset.alvo];
    const passo = Number(b.dataset.step);
    const v = Math.min(Number(el.max), Math.max(Number(el.min), (Number(el.value) || 0) + passo));
    el.value = Math.round(v * 100) / 100;
  }));
  $("#btn-padrao").addEventListener("click", () => {
    definirValores(PADRAO);
    limparErros();
    moverMarcador(PADRAO.latitude, PADRAO.longitude, false);
  });

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
    const primeiro = $(".campo.invalido", form);
    if (primeiro) primeiro.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  // ---------------------------------------------------------------- mapa da avaliação
  let mapaAvaliar = null, marcador = null;
  function criarMapa(id, centro, zoom) {
    const m = L.map(id, { zoomControl: true, attributionControl: true }).setView(centro, zoom);
    const base = L.tileLayer(urlTiles(), {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(m);
    camadasBase.push(base);
    return m;
  }
  function distancia(a, b, c, d) {
    const r = Math.PI / 180, x = (d - b) * r * Math.cos(((a + c) / 2) * r), y = (c - a) * r;
    return Math.sqrt(x * x + y * y);
  }
  function cepMaisProximo(lat, lon) {
    if (!cache.regioes || !cache.regioes.length) return null;
    let melhor = null, dMin = Infinity;
    cache.regioes.forEach((g) => {
      const dd = distancia(lat, lon, Number(g.latitude), Number(g.longitude));
      if (dd < dMin) { dMin = dd; melhor = g; }
    });
    return melhor;
  }
  function moverMarcador(lat, lon, ajustarCep = true) {
    if (!mapaAvaliar) return;
    if (!marcador) {
      const icone = L.divIcon({ className: "", html: '<div style="width:22px;height:22px;border-radius:50%;background:var(--accent);border:4px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.35)"></div>', iconSize: [22, 22], iconAnchor: [11, 11] });
      marcador = L.marker([lat, lon], { icon: icone, keyboard: false }).addTo(mapaAvaliar);
    } else marcador.setLatLng([lat, lon]);
    mapaAvaliar.panTo([lat, lon]);
    if (ajustarCep) {
      const g = cepMaisProximo(lat, lon);
      if (g) form.elements.cep.value = String(g.cep);
    }
  }

  async function initAvaliar() {
    definirValores(PADRAO);
    try {
      mapaAvaliar = criarMapa("mapa-avaliar", [PADRAO.latitude, PADRAO.longitude], 11);
      mapaAvaliar.on("click", (e) => {
        const lat = Math.round(e.latlng.lat * 10000) / 10000, lon = Math.round(e.latlng.lng * 10000) / 10000;
        form.elements.latitude.value = lat;
        form.elements.longitude.value = lon;
        moverMarcador(lat, lon, true);
      });
      moverMarcador(PADRAO.latitude, PADRAO.longitude, false);
    } catch (e) {
      $("#mapa-avaliar").innerHTML = '<div class="vazio">Mapa indisponível sem conexão com a internet.</div>';
    }
    const regioes = await carregarRegioes();
    const sel = form.elements.cep;
    if (regioes && regioes.length) {
      const atual = sel.value || PADRAO.cep;
      sel.innerHTML = regioes.slice().sort((a, b) => String(a.cep).localeCompare(String(b.cep)))
        .map((g) => `<option value="${esc(g.cep)}">${esc(g.cep)} · mediana ${usd.format(g.preco_mediano_usd)}</option>`).join("");
      sel.value = atual;
    }
    sel.addEventListener("change", () => {
      const g = (cache.regioes || []).find((x) => String(x.cep) === sel.value);
      if (!g) return;
      form.elements.latitude.value = Math.round(g.latitude * 10000) / 10000;
      form.elements.longitude.value = Math.round(g.longitude * 10000) / 10000;
      moverMarcador(Number(g.latitude), Number(g.longitude), false);
    });
    ["latitude", "longitude"].forEach((k) => form.elements[k].addEventListener("change", () => {
      const lat = Number(form.elements.latitude.value), lon = Number(form.elements.longitude.value);
      if (Number.isFinite(lat) && Number.isFinite(lon)) moverMarcador(lat, lon, true);
    }));
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    limparErros();
    const btn = $("#btn-avaliar");
    btn.disabled = true;
    btn.innerHTML = '<span class="carregando"></span> Avaliando…';
    const payload = lerPayload();
    const r = await api("/v1/predict", { metodo: "POST", corpo: payload });
    btn.disabled = false;
    btn.textContent = "Avaliar imóvel";
    const caixa = $("#resultado");
    if (r.ok && r.dados) { mostrarResultado(r.dados, payload); return; }
    if (r.status === 0) {
      caixa.innerHTML = alertaHTML("API indisponível", "Não foi possível falar com o servidor. Confirme que a API está rodando (uvicorn) e tente de novo.", [], "aviso");
      return;
    }
    const lista = detalhesErro(r.dados);
    marcarErros(lista);
    const titulo = r.status === 422 ? "Dados inválidos (422)" : r.status === 400 ? "Regra de negócio violada (400)" : r.status === 503 ? "Modelo indisponível (503)" : `Erro ${r.status}`;
    const msg = (r.dados && (r.dados.mensagem || (typeof r.dados.detail === "string" ? r.dados.detail : ""))) || "Revise os campos destacados.";
    caixa.innerHTML = alertaHTML(titulo, msg, lista, r.status >= 500 ? "" : "aviso");
  });

  function alertaHTML(titulo, msg, lista, tipo) {
    const itens = lista.length ? `<ul>${lista.map((d) => `<li><b>${esc(d.campo)}</b>: ${esc(d.mensagem)}</li>`).join("")}</ul>` : "";
    return `<div class="alerta ${tipo}"><h4>${esc(titulo)}</h4><p>${esc(msg)}</p>${itens}</div>`;
  }

  function mostrarResultado(d, payload) {
    const preco = Number(d.preco_estimado_usd);
    const fx = d.faixa_provavel_usd || {};
    const min = Number(fx.minimo ?? preco), max = Number(fx.maximo ?? preco);
    const pos = max > min ? Math.min(100, Math.max(0, ((preco - min) / (max - min)) * 100)) : 50;
    const regiao = (cache.regioes || []).find((g) => String(g.cep) === String(payload.cep));
    let comp = "—", classe = "";
    if (regiao && regiao.preco_m2_mediano_usd && d.preco_por_m2_usd) {
      const dif = Number(d.preco_por_m2_usd) / Number(regiao.preco_m2_mediano_usd) - 1;
      comp = `${dif >= 0 ? "+" : ""}${num(dif * 100, 1)} %`;
      classe = dif >= 0 ? "pos" : "neg";
    }
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
        <div class="res-item"><small>vs. mediana do CEP</small><b class="${classe}">${comp}</b></div>
        <div class="res-item"><small>Tempo de resposta</small><b>${d.latencia_ms !== undefined ? num(d.latencia_ms, 1) + " ms" : "—"}</b></div>
      </div>
      <p class="ref">${esc(d.referencia_mercado || "")}${d.versao_modelo ? " · modelo " + esc(d.versao_modelo) : ""}</p>`;
    $("#resultado").scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  // ---------------------------------------------------------------- simulador
  const graficos = {};
  let ultimaSimulacao = null;
  function cenarios(base) {
    const lista = [
      { nome: "Imóvel atual", dados: { ...base } },
      { nome: "Reformar (2015, +1 conservação)", dados: { ...base, ano_reforma: 2015, condicao: Math.min(5, base.condicao + 1) } },
      { nome: "+1 banheiro", dados: { ...base, banheiros: Math.min(10, base.banheiros + 1) } },
      { nome: "+20 % de área útil", dados: { ...base, area_util_m2: Math.round(base.area_util_m2 * 1.2) } },
      { nome: "Padrão construtivo +1", dados: { ...base, padrao_construtivo: Math.min(13, base.padrao_construtivo + 1) } },
      { nome: "Vista +1", dados: { ...base, vista: Math.min(4, base.vista + 1) } },
    ];
    return lista;
  }
  function payloadBase() {
    // Garante o formulário com valores padrão caso o usuário venha direto ao simulador.
    if (!inicializadas.has("avaliar")) definirValores(PADRAO);
    return lerPayload();
  }
  function atualizarBaseSimulador() {
    const b = payloadBase();
    $("#sim-base").textContent = `${b.area_util_m2} m² · ${b.quartos} quartos · ${b.banheiros} banheiros · padrão ${b.padrao_construtivo} · CEP ${b.cep}`;
  }
  function initSimulador() {
    atualizarBaseSimulador();
    $("#btn-simular").addEventListener("click", simular);
    simular();
  }
  async function simular() {
    atualizarBaseSimulador();
    const btn = $("#btn-simular");
    btn.disabled = true;
    btn.innerHTML = '<span class="carregando"></span> Simulando…';
    const lista = cenarios(payloadBase());
    const r = await api("/v1/predict/lote", { metodo: "POST", corpo: { imoveis: lista.map((c) => c.dados) } });
    btn.disabled = false;
    btn.textContent = "Simular cenários";
    if (!r.ok || !r.dados || !Array.isArray(r.dados.previsoes)) {
      const lista2 = detalhesErro(r.dados);
      const msg = r.status === 0 ? "API indisponível. Inicie o servidor e tente de novo." : ((r.dados && r.dados.mensagem) || "Ajuste o imóvel no módulo Avaliar e simule de novo.");
      $("#sim-tabela").innerHTML = alertaHTML(r.status ? `Não foi possível simular (${r.status})` : "Sem conexão", msg, lista2, "aviso");
      return;
    }
    const precos = r.dados.previsoes.map((p) => Number(p.preco_estimado_usd));
    ultimaSimulacao = lista.map((c, i) => ({ nome: c.nome, preco: precos[i], delta: precos[i] - precos[0], rel: precos[i] / precos[0] - 1 }));
    desenharSimulacao(ultimaSimulacao);
  }
  function desenharSimulacao(res) {
    if (!res || typeof Chart === "undefined") return;
    const itens = res.slice(1);
    const corPos = cssVar("--accent-2"), corNeg = cssVar("--bad"), texto = cssVar("--muted"), linha = cssVar("--line");
    if (graficos.sim) graficos.sim.destroy();
    graficos.sim = new Chart($("#graf-sim"), {
      type: "bar",
      data: { labels: itens.map((x) => x.nome), datasets: [{ data: itens.map((x) => Math.round(x.delta)), backgroundColor: itens.map((x) => (x.delta >= 0 ? corPos : corNeg)), borderRadius: 10, maxBarThickness: 46 }] },
      options: {
        indexAxis: "y", responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${usd.format(c.raw)} (${num(itens[c.dataIndex].rel * 100, 1)} %)` } } },
        scales: {
          x: { ticks: { color: texto, callback: (v) => usd.format(v) }, grid: { color: linha } },
          y: { ticks: { color: texto }, grid: { display: false } },
        },
      },
    });
    $("#sim-tabela").innerHTML = `<table class="tabela"><thead><tr><th>Cenário</th><th>Preço estimado</th><th>Variação</th></tr></thead><tbody>${res.map((x, i) => `
      <tr><td>${esc(x.nome)}</td><td>${usd.format(x.preco)}</td><td class="${i === 0 ? "" : x.delta >= 0 ? "pos" : "neg"}">${i === 0 ? "referência" : `${x.delta >= 0 ? "+" : ""}${usd.format(x.delta)} (${num(x.rel * 100, 1)} %)`}</td></tr>`).join("")}</tbody></table>`;
  }

  // ---------------------------------------------------------------- mapa de valor
  let mapaValor = null, camadaCirculos = null;
  const ESCALA = ["#c9f2f6", "#8ce1ea", "#3fc3d3", "#1a93a6", "#0f5f73"];
  function quantis(valores, n) {
    const v = valores.slice().sort((a, b) => a - b);
    return Array.from({ length: n - 1 }, (_, i) => v[Math.floor(((i + 1) / n) * (v.length - 1))]);
  }
  async function initMapa() {
    try { mapaValor = criarMapa("mapa-valor", [47.5, -122.2], 10); }
    catch (e) { $("#mapa-valor").innerHTML = '<div class="vazio">Mapa indisponível sem conexão com a internet.</div>'; return; }
    const regioes = await carregarRegioes();
    if (!regioes || !regioes.length) { $("#legenda-mapa").textContent = "Dados de regiões indisponíveis: verifique se a API está no ar."; return; }
    desenharMapaValor(regioes);
  }
  function desenharMapaValor(regioes) {
    if (!mapaValor) return;
    if (camadaCirculos) camadaCirculos.remove();
    const vals = regioes.map((g) => Number(g.preco_m2_mediano_usd));
    const cortes = quantis(vals, ESCALA.length);
    const cor = (v) => ESCALA[cortes.filter((c) => v > c).length];
    const maxV = Math.max(...regioes.map((g) => Number(g.vendas) || 1));
    const borda = escuroAtivo() ? "rgba(255,255,255,.55)" : "rgba(15,76,100,.55)";
    camadaCirculos = L.layerGroup(regioes.map((g) => L.circleMarker([g.latitude, g.longitude], {
      radius: 6 + 14 * Math.sqrt((Number(g.vendas) || 1) / maxV), color: borda, weight: 1, fillColor: cor(Number(g.preco_m2_mediano_usd)), fillOpacity: 0.82,
    }).bindPopup(`<b>CEP ${esc(g.cep)}</b><br>Preço mediano: ${usd.format(g.preco_mediano_usd)}<br>Mediana por m²: ${usd.format(g.preco_m2_mediano_usd)}<br>Vendas: ${num(g.vendas)}`))).addTo(mapaValor);
    const faixas = [Math.min(...vals), ...cortes, Math.max(...vals)];
    $("#legenda-mapa").innerHTML = "<b>US$/m² mediano:</b>" + ESCALA.map((c, i) => `<span><i style="background:${c}"></i>${usd.format(faixas[i])}–${usd.format(faixas[i + 1])}</span>`).join("");
  }

  // ---------------------------------------------------------------- modelo
  const ROTULOS = {
    grade: "Padrão construtivo", padrao_construtivo: "Padrão construtivo", lat: "Latitude", latitude: "Latitude",
    long: "Longitude", longitude: "Longitude", sqft_living: "Área útil", area_util_m2: "Área útil", zipcode: "CEP", cep: "CEP",
    sqft_living15: "Área útil dos vizinhos", view: "Vista", vista: "Vista", waterfront: "Frente para a água", frente_agua: "Frente para a água",
    condition: "Conservação", condicao: "Conservação", idade_imovel: "Idade do imóvel", bathrooms: "Banheiros", banheiros: "Banheiros",
    bedrooms: "Quartos", quartos: "Quartos", floors: "Andares", andares: "Andares", sqft_basement: "Porão", log_sqft_lot: "Terreno (log)",
    foi_reformado: "Foi reformado", tem_porao: "Tem porão", mes_venda: "Mês da venda", ano_venda: "Ano da venda",
  };
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
      $("#modelo-faixa").textContent = `Faixa provável: 80 % dos imóveis de validação ficaram entre ${num(relativo(m.faixa_erro.p10), 1)} % e +${num(relativo(m.faixa_erro.p90), 1)} % do preço estimado.`;
    }
    desenharImportancia(m);
  }
  function desenharImportancia(m) {
    const imp = (m.importancia || []).slice().sort((a, b) => b.importancia - a.importancia).slice(0, 10);
    if (!imp.length || typeof Chart === "undefined") return;
    if (graficos.imp) graficos.imp.destroy();
    const texto = cssVar("--muted"), linha = cssVar("--line"), cor = cssVar("--accent");
    graficos.imp = new Chart($("#graf-imp"), {
      type: "bar",
      data: { labels: imp.map((x) => ROTULOS[x.variavel] || x.variavel), datasets: [{ data: imp.map((x) => x.importancia), backgroundColor: cor, borderRadius: 8, maxBarThickness: 26 }] },
      options: {
        indexAxis: "y", responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => num(c.raw, 4) } } },
        scales: { x: { ticks: { color: texto }, grid: { color: linha } }, y: { ticks: { color: texto }, grid: { display: false } } },
      },
    });
  }

  // ---------------------------------------------------------------- desenvolvedores
  function initDev() {
    const exemplo = { ...PADRAO, andares: 1, condicao: 3, vista: 0, ano_reforma: null };
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
  if (!inicializadas.has("inicio")) { inicializadas.add("inicio"); initInicio(); }
  rotear();
})();
