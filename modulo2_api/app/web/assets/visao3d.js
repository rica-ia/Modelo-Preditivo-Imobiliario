/* Visão 3D do entorno do imóvel: órbita de 360° sobre as imagens fotorrealistas do Google (Photorealistic 3D Tiles, via
   CesiumJS). Sem chave configurada, cai para a visão 3D simplificada do MapLibre (prédios em volume, sem chave).
   Parâmetros da URL: lat, lng, titulo, valor, faixa_min, faixa_max, dist (m), incl (graus), duracao (s), modo=captura.
   No modo captura a página não busca a configuração: quem a abre (modulo2_api/ferramentas/gerar_video_360.py) chama
   window.__visao3d.iniciar() e conduz a câmera quadro a quadro. */
"use strict";
(() => {
  const $ = (s) => document.querySelector(s);
  const q = new URLSearchParams(location.search);
  const num = (k, padrao) => { const v = parseFloat(q.get(k)); return Number.isFinite(v) ? v : padrao; };
  const P = {
    lat: num("lat", 47.6788), lng: num("lng", -122.346), titulo: q.get("titulo") || "Entorno do imóvel",
    valor: num("valor", NaN), faixaMin: num("faixa_min", NaN), faixaMax: num("faixa_max", NaN),
    dist: num("dist", 240), incl: num("incl", -32), duracao: num("duracao", 24), captura: q.get("modo") === "captura",
  };
  const usd = (v) => v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  const estado = (txt, ok) => { $("#estado").textContent = txt; $("#ponto").classList.toggle("ok", !!ok); };

  // ---------------------------------------------------------------- ficha do imóvel
  function preencherFicha() {
    $("#titulo").textContent = P.titulo;
    $("#coords").textContent = `${P.lat.toFixed(4)}, ${P.lng.toFixed(4)} · King County (WA)`;
    // Endereço completo (OpenStreetMap, via API); as coordenadas ficam embaixo, menores
    fetch(`/v1/endereco?lat=${P.lat}&lng=${P.lng}`).then((r) => (r.ok ? r.json() : null)).then((e) => {
      if (!e || !e.disponivel || !e.endereco) return;
      const sub = $("#coords");
      sub.textContent = e.endereco;
      const c = document.createElement("span");
      c.className = "coord";
      c.textContent = `${P.lat.toFixed(4)}, ${P.lng.toFixed(4)} · ${e.fonte}`;
      sub.append(c);
    }).catch(() => {});
    if (Number.isFinite(P.valor)) {
      $("#bloco-valor").hidden = false;
      $("#valor").textContent = usd(P.valor);
      $("#faixa").textContent = Number.isFinite(P.faixaMin) && Number.isFinite(P.faixaMax)
        ? `Faixa provável: ${usd(P.faixaMin)} a ${usd(P.faixaMax)}` : "";
    }
  }
  if (P.captura) document.body.classList.add("captura");

  // Seta discreta para recolher e expandir a ficha (a escolha fica guardada neste navegador)
  function recolherFicha(recolher) {
    $("#ficha").classList.toggle("recolhida", recolher);
    const b = $("#bt-recolher");
    b.setAttribute("aria-expanded", String(!recolher));
    b.title = recolher ? "Expandir" : "Recolher";
    b.setAttribute("aria-label", recolher ? "Expandir a ficha" : "Recolher a ficha");
    try { localStorage.setItem("ai-ficha-3d", recolher ? "1" : "0"); } catch (e) {}
  }
  $("#bt-recolher").addEventListener("click", () => recolherFicha(!$("#ficha").classList.contains("recolhida")));
  try { if (localStorage.getItem("ai-ficha-3d") === "1") recolherFicha(true); } catch (e) {}

  // ---------------------------------------------------------------- cena: Google 3D (Cesium) ou MapLibre
  const cena = { tipo: null, canvas: null, rumo: 0, voando: false, ultimo: 0, creditos: "Imagens © Google" };
  let viewer = null, tileset = null, mapa = null, alvo = null;

  async function iniciarGoogle(chave) {
    const C = window.Cesium;
    C.GoogleMaps.defaultApiKey = chave;
    viewer = new C.Viewer("cena", {
      baseLayer: false, baseLayerPicker: false, geocoder: false, homeButton: false, sceneModePicker: false,
      navigationHelpButton: false, animation: false, timeline: false, fullscreenButton: false, infoBox: false,
      selectionIndicator: false, requestRenderMode: false, contextOptions: { webgl: { preserveDrawingBuffer: true } },
    });
    viewer.scene.globe.show = false;
    viewer.scene.skyAtmosphere.show = true;
    tileset = viewer.scene.primitives.add(await C.createGooglePhotorealistic3DTileset(undefined, { showCreditsOnScreen: true }));
    tileset.maximumScreenSpaceError = 12;
    // teto de memória dos blocos: o suficiente para a volta inteira ficar no cache sem pressionar a máquina
    tileset.cacheBytes = 384 * 1024 * 1024;
    tileset.maximumCacheOverflowBytes = 128 * 1024 * 1024;
    viewer.camera.setView({ destination: C.Cartesian3.fromDegrees(P.lng, P.lat, 900) });
    // altura do chão no ponto (as alturas dos blocos são elipsoidais): mira a câmera um pouco acima dele
    let chao = null;
    try {
      const amostra = await Promise.race([
        viewer.scene.sampleHeightMostDetailed([C.Cartographic.fromDegrees(P.lng, P.lat)]),
        new Promise((r) => setTimeout(() => r(null), 30000)),
      ]);
      chao = amostra && amostra[0] && Number.isFinite(amostra[0].height) ? amostra[0].height : null;
    } catch (_) { chao = null; }
    const z = chao ?? 40;
    alvo = C.Cartesian3.fromDegrees(P.lng, P.lat, z + 6);
    // pino do imóvel: haste vertical e ponto violeta, sempre à frente da cena
    viewer.entities.add({ polyline: { positions: C.Cartesian3.fromDegreesArrayHeights([P.lng, P.lat, z, P.lng, P.lat, z + 28]),
      width: 3, material: C.Color.fromCssColorString("#703BF7"), depthFailMaterial: C.Color.fromCssColorString("#703BF7").withAlpha(0.6) } });
    viewer.entities.add({ position: C.Cartesian3.fromDegrees(P.lng, P.lat, z + 28),
      point: { pixelSize: 16, color: C.Color.fromCssColorString("#703BF7"), outlineColor: C.Color.WHITE, outlineWidth: 3,
        disableDepthTestDistance: Number.POSITIVE_INFINITY } });
    cena.tipo = "google";
    cena.canvas = viewer.scene.canvas;
    mirar(0);
    viewer.scene.postRender.addEventListener(() => { lerCreditos(); if (gravacao.ativa) desenharComposto(); });
  }

  function lerCreditos() {
    const el = document.querySelector(".cesium-widget-credits");
    const txt = el ? el.innerText.replace(/\s+/g, " ").replace(/^[^\p{L}\p{N}]+/u, "").trim() : "";
    cena.creditos = txt ? `Imagens © Google · ${txt}` : "Imagens © Google";
    $("#credito").textContent = cena.creditos;
  }

  function iniciarAlternativa(motivo) {
    if (motivo) $("#aviso-texto").textContent = motivo;
    $("#cena").style.display = "none";
    $("#cena-alt").style.display = "block";
    mapa = new maplibregl.Map({
      container: "cena-alt", style: "https://tiles.openfreemap.org/styles/liberty", center: [P.lng, P.lat],
      zoom: 17, pitch: 62, bearing: 0, attributionControl: { compact: true }, preserveDrawingBuffer: true,
    });
    mapa.on("load", () => {
      mapa.addSource("satelite", { type: "raster", tileSize: 256, maxzoom: 19,
        tiles: ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"] });
      const primeira = mapa.getStyle().layers.find((l) => l.type !== "background");
      mapa.addLayer({ id: "satelite", type: "raster", source: "satelite", paint: { "raster-opacity": 0.9 } }, primeira && primeira.id);
      new maplibregl.Marker({ color: "#703BF7" }).setLngLat([P.lng, P.lat]).addTo(mapa);
      cena.tipo = "maplibre";
      cena.canvas = mapa.getCanvas();
      cena.creditos = "Satélite © Esri · Mapa © OpenFreeMap / OpenStreetMap";
      $("#credito").textContent = cena.creditos;
      habilitar();
      estado("Visão 3D simplificada (sem chave)", true);
    });
    mapa.on("render", () => { if (gravacao.ativa) desenharComposto(); });
  }

  function mirar(rumo) {
    cena.rumo = rumo;
    if (cena.tipo === "google") {
      const C = window.Cesium;
      viewer.camera.lookAt(alvo, new C.HeadingPitchRange(C.Math.toRadians(rumo), C.Math.toRadians(P.incl), P.dist));
    } else if (mapa) {
      mapa.jumpTo({ bearing: rumo });
    }
  }

  // ---------------------------------------------------------------- voo 360° (interativo)
  function passo(t) {
    if (!cena.voando) return;
    const dt = cena.ultimo ? (t - cena.ultimo) / 1000 : 0;
    cena.ultimo = t;
    const novo = cena.rumo + (360 * dt) / P.duracao;
    if (gravacao.ativa && novo - gravacao.rumo0 >= 360) { mirar(gravacao.rumo0 + 360); pararGravacao(); }
    else mirar(novo);
    requestAnimationFrame(passo);
  }
  function voar() {
    if (cena.voando) return;
    cena.voando = true; cena.ultimo = 0;
    $("#bt-voo").textContent = "Voo 360° em curso";
    requestAnimationFrame(passo);
  }
  function pausar() {
    cena.voando = false;
    $("#bt-voo").textContent = "Iniciar voo 360°";
  }

  // ---------------------------------------------------------------- composição (vídeo = cena + ficha + créditos)
  const comp = document.createElement("canvas");
  const ctx = comp.getContext("2d");
  function desenharComposto() {
    const src = cena.canvas;
    if (!src) return comp;
    const W = src.width, H = src.height;
    if (comp.width !== W || comp.height !== H) { comp.width = W; comp.height = H; }
    ctx.drawImage(src, 0, 0, W, H);
    const k = H / 720;                                  // escala do texto: referência 720p
    const f = (peso, tam) => `${peso} ${Math.round(tam * k)}px Urbanist, Segoe UI, sans-serif`;
    // ficha no alto, à esquerda
    const x = 24 * k, y = 24 * k, w = 420 * k, h = (Number.isFinite(P.valor) ? 186 : 100) * k;
    ctx.fillStyle = "rgba(20, 20, 20, .82)";
    ctx.beginPath(); ctx.roundRect(x, y, w, h, 16 * k); ctx.fill();
    ctx.strokeStyle = "#333333"; ctx.lineWidth = Math.max(1, k); ctx.stroke();
    ctx.fillStyle = "#703BF7"; ctx.beginPath(); ctx.arc(x + 26 * k, y + 28 * k, 7 * k, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = "#bfbfbf"; ctx.font = f(700, 14); ctx.textBaseline = "middle";
    ctx.fillText("Avaliador Imobiliário · Visão 3D", x + 42 * k, y + 28 * k);
    let tam = 19;                                       // título inteiro: reduz a fonte até caber no cartão
    do { ctx.font = f(700, tam); } while (ctx.measureText(P.titulo).width > w - 40 * k && --tam > 12);
    ctx.fillStyle = "#ffffff";
    ctx.fillText(P.titulo, x + 20 * k, y + 60 * k);
    ctx.fillStyle = "#999999"; ctx.font = f(500, 12);
    ctx.fillText("Pino na coordenada da base de vendas (precisão de cerca de 50 m)", x + 20 * k, y + 82 * k);
    if (Number.isFinite(P.valor)) {
      ctx.fillStyle = "#999999"; ctx.font = f(600, 12);
      ctx.fillText("VALOR ESTIMADO PELO MODELO", x + 20 * k, y + 108 * k);
      ctx.fillStyle = "#ffffff"; ctx.font = f(800, 30);
      ctx.fillText(usd(P.valor), x + 20 * k, y + 136 * k);
      if (Number.isFinite(P.faixaMin)) {
        ctx.fillStyle = "#bfbfbf"; ctx.font = f(500, 13);
        ctx.fillText(`Faixa provável: ${usd(P.faixaMin)} a ${usd(P.faixaMax)}`, x + 20 * k, y + 164 * k);
      }
    }
    // créditos sempre visíveis, no rodapé
    ctx.font = f(600, 13);
    const cred = cena.creditos;
    const cw = ctx.measureText(cred).width + 20 * k;
    ctx.fillStyle = "rgba(0, 0, 0, .6)";
    ctx.beginPath(); ctx.roundRect(W - cw - 16 * k, H - 40 * k, cw, 26 * k, 8 * k); ctx.fill();
    ctx.fillStyle = "#ffffff"; ctx.fillText(cred, W - cw - 6 * k, H - 27 * k);
    return comp;
  }

  // ---------------------------------------------------------------- gravação no navegador (MediaRecorder → .webm)
  const gravacao = { ativa: false, rec: null, partes: [], rumo0: 0 };
  function gravar() {
    if (gravacao.ativa) { pararGravacao(); return; }
    desenharComposto();
    const tipo = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"].find((t) => MediaRecorder.isTypeSupported(t));
    gravacao.partes = [];
    gravacao.rec = new MediaRecorder(comp.captureStream(30), { mimeType: tipo, videoBitsPerSecond: 12e6 });
    gravacao.rec.ondataavailable = (e) => { if (e.data.size) gravacao.partes.push(e.data); };
    gravacao.rec.onstop = () => {
      const url = URL.createObjectURL(new Blob(gravacao.partes, { type: "video/webm" }));
      const a = Object.assign(document.createElement("a"), { href: url, download: `visao3d_${P.lat.toFixed(4)}_${P.lng.toFixed(4)}.webm` });
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    };
    gravacao.ativa = true; gravacao.rumo0 = cena.rumo;
    gravacao.rec.start(500);
    $("#bt-gravar").textContent = "Parar gravação"; $("#bt-gravar").classList.add("gravando");
    pausar(); voar();                                    // uma volta completa e para sozinho
  }
  function pararGravacao() {
    if (!gravacao.ativa) return;
    gravacao.ativa = false;
    gravacao.rec.stop();
    pausar();
    $("#bt-gravar").textContent = "Gravar vídeo"; $("#bt-gravar").classList.remove("gravando");
  }

  function habilitar() {
    ["#bt-voo", "#bt-pausa", "#bt-gravar"].forEach((s) => { $(s).disabled = false; });
  }
  $("#bt-voo").addEventListener("click", voar);
  $("#bt-pausa").addEventListener("click", pausar);
  $("#bt-gravar").addEventListener("click", gravar);
  $("#bt-alt").addEventListener("click", () => { $("#aviso").style.display = "none"; iniciarAlternativa(); });

  // ---------------------------------------------------------------- partida
  async function iniciar(cfg) {
    if (cfg && typeof cfg === "object") {
      for (const k of ["titulo", "valor", "faixaMin", "faixaMax", "dist", "incl"]) if (cfg[k] != null) P[k] = cfg[k];
    }
    preencherFicha();
    if (!cfg || !cfg.chave || !window.Cesium) {
      $("#aviso").style.display = "block";
      estado("Sem imagens fotorrealistas neste acesso");
      return false;
    }
    try {
      estado("Carregando as imagens 3D do Google…");
      await iniciarGoogle(cfg.chave);
      habilitar();
      estado("Imagens fotorrealistas carregadas", true);
      return true;
    } catch (e) {
      $("#aviso").style.display = "block";
      $("#aviso-texto").textContent = "O Google recusou a chave ou as imagens 3D não carregaram neste acesso. A visão simplificada segue disponível.";
      estado("Imagens 3D indisponíveis");
      return false;
    }
  }

  // ---------------------------------------------------------------- interface de captura (gerador de vídeo)
  const espera = (ms) => new Promise((r) => setTimeout(r, ms));
  async function estavel(teto, minimo) {
    const t0 = performance.now(); let n = 0;
    while (performance.now() - t0 < teto) {
      await espera(120);
      n = tileset && tileset.tilesLoaded ? n + 1 : 0;
      if (n >= minimo) return true;
    }
    return false;
  }
  const codif = { enc: null, mux: null, fps: 30, i: 0, erro: null, bytes: null, formato: null };
  function carregarScript(src) {
    return new Promise((ok, falha) => { const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = falha; document.head.appendChild(s); });
  }
  window.__visao3d = {
    iniciar,
    tipo: () => cena.tipo,
    async aquecer(passos, teto) {                       // passa pelos rumos uma vez para os blocos ficarem no cache
      let ok = 0;
      for (let i = 0; i < passos; i++) { mirar((i * 360) / passos); if (await estavel(teto, 5)) ok++; }
      return ok;
    },
    async quadro(rumo, teto) {                          // posiciona, espera os blocos e desenha o composto
      mirar(rumo);
      const completo = await estavel(teto, 2);
      if (viewer) viewer.render();
      lerCreditos();
      desenharComposto();
      return completo;
    },
    jpeg: (qualidade) => comp.toDataURL("image/jpeg", qualidade || 0.92),
    async abrirCodificador(fps) {
      codif.fps = fps; codif.i = 0;
      const W = comp.width, H = comp.height;
      await carregarScript("https://cdn.jsdelivr.net/npm/mp4-muxer@5.1.3/build/mp4-muxer.js");
      for (const codec of ["avc1.640028", "avc1.4d4028", "avc1.42e028"]) {
        const c = { codec, width: W, height: H, bitrate: 10e6, framerate: fps, latencyMode: "quality" };
        if ((await VideoEncoder.isConfigSupported(c)).supported) {
          const { Muxer, ArrayBufferTarget } = window.Mp4Muxer;
          codif.mux = new Muxer({ target: new ArrayBufferTarget(), video: { codec: "avc", width: W, height: H, frameRate: fps }, fastStart: "in-memory" });
          codif.enc = new VideoEncoder({ output: (ch, meta) => codif.mux.addVideoChunk(ch, meta), error: (e) => { codif.erro = String(e); } });
          codif.enc.configure(c);
          codif.formato = "mp4";
          return { codec, W, H };
        }
      }
      await carregarScript("https://cdn.jsdelivr.net/npm/webm-muxer@5.0.3/build/webm-muxer.js");
      for (const codec of ["vp09.00.40.08", "vp8"]) {
        const c = { codec, width: W, height: H, bitrate: 10e6, framerate: fps, latencyMode: "quality" };
        if ((await VideoEncoder.isConfigSupported(c)).supported) {
          const { Muxer, ArrayBufferTarget } = window.WebMMuxer;
          codif.mux = new Muxer({ target: new ArrayBufferTarget(), video: { codec: codec.startsWith("vp09") ? "V_VP9" : "V_VP8", width: W, height: H, frameRate: fps } });
          codif.enc = new VideoEncoder({ output: (ch, meta) => codif.mux.addVideoChunk(ch, meta), error: (e) => { codif.erro = String(e); } });
          codif.enc.configure(c);
          codif.formato = "webm";
          return { codec, W, H };
        }
      }
      return null;
    },
    async codificar() {                                 // codifica o composto atual com carimbo de tempo exato
      const f = new VideoFrame(comp, { timestamp: Math.round((codif.i * 1e6) / codif.fps), duration: Math.round(1e6 / codif.fps) });
      codif.enc.encode(f, { keyFrame: codif.i % (codif.fps * 2) === 0 });
      f.close(); codif.i++;
      while (codif.enc.encodeQueueSize > 4) await espera(5);
      return codif.erro;
    },
    async fechar() {
      await codif.enc.flush(); codif.mux.finalize();
      codif.bytes = new Uint8Array(codif.mux.target.buffer);
      return { bytes: codif.bytes.length, formato: codif.formato, quadros: codif.i, erro: codif.erro };
    },
    parte(o, n) {                                       // devolve o vídeo em partes (base64), para o gerador gravar em disco
      const s = codif.bytes.subarray(o, o + n); let t = "";
      for (let k = 0; k < s.length; k += 0x8000) t += String.fromCharCode.apply(null, s.subarray(k, k + 0x8000));
      return btoa(t);
    },
  };

  preencherFicha();
  if (!P.captura) {
    fetch("/v1/config/mapa3d").then((r) => (r.ok ? r.json() : null)).catch(() => null)
      .then((cfg) => iniciar(cfg && cfg.disponivel ? { chave: cfg.chave } : null));
  }
})();
