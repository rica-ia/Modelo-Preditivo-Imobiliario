/* Avaliador Imobiliário — tela Banco de dados: explorador por seções, administração e diagrama das 9 tabelas.
   Arquivo independente de app.js: lê a mesma sessão de administrador (2FA ou token) e expõe window.TelaBanco. */
(function () {
  "use strict";

  // ---------------------------------------------------------------- utilidades
  const $ = (sel, raiz = document) => raiz.querySelector(sel);
  const $$ = (sel, raiz = document) => Array.from(raiz.querySelectorAll(sel));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (v, d = 0) => Number(v).toLocaleString("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d });
  const moeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const usd = (v) => moeda.format(Number(v)).replace(/ /g, " ");
  const cssVar = (nome) => getComputedStyle(document.documentElement).getPropertyValue(nome).trim();
  const RE_DATA = /^(\d{4})-(\d{2})-(\d{2})$/;
  const RE_DATA_HORA = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/;
  function dataBR(v) {
    if (v == null || v === "") return "—";
    const s = String(v), m = RE_DATA.exec(s);
    if (m) return `${m[3]}/${m[2]}/${m[1]}`;
    const d = new Date(s);
    return isNaN(d) ? s : d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  }
  const competencia = (v) => { const m = /^(\d{4})-(\d{2})$/.exec(String(v || "")); return m ? `${m[2]}/${m[1]}` : String(v ?? "—"); };
  const bytes = (b) => { const n = Number(b) || 0; return n >= 1048576 ? `${num(n / 1048576, 1)} MB` : n >= 1024 ? `${num(n / 1024, 0)} KB` : `${num(n)} B`; };

  function toast(msg) {
    const el = $("#toast");
    if (!el) return;
    el.textContent = msg;
    el.classList.add("on");
    clearTimeout(toast.t);
    toast.t = setTimeout(() => el.classList.remove("on"), 2800);
  }

  // ---------------------------------------------------------------- acesso de administrador (mesma regra de app.js)
  // Sessão 2FA no localStorage ("ai-sessao-2fa") tem prioridade; senão, o token guardado na sessão do navegador ("ai-admin").
  function cabAdmin() {
    let sessao = "", token = "";
    try { sessao = localStorage.getItem("ai-sessao-2fa") || ""; } catch (e) { /* armazenamento bloqueado */ }
    try { token = sessionStorage.getItem("ai-admin") || ""; } catch (e) { /* armazenamento bloqueado */ }
    return sessao ? { "X-Admin-Sessao": sessao } : token ? { "X-Admin-Token": token } : {};
  }

  /** Chamada HTTP com tempo-limite; devolve {ok, status, dados} e nunca lança. */
  async function api(caminho, opcoes = {}) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), opcoes.timeout || 15000);
    try {
      const cab = { ...cabAdmin(), ...(opcoes.corpo ? { "Content-Type": "application/json" } : {}) };
      const resp = await fetch(caminho, {
        method: opcoes.metodo || "GET",
        headers: cab,
        body: opcoes.corpo ? JSON.stringify(opcoes.corpo) : undefined,
        cache: "no-store",
        signal: ctrl.signal,
      });
      if (opcoes.blob) return { ok: resp.ok, status: resp.status, resp, dados: resp.ok ? await resp.blob() : await resp.json().catch(() => null) };
      let dados = null;
      try { dados = await resp.json(); } catch (e) { dados = null; }
      return { ok: resp.ok, status: resp.status, dados };
    } catch (e) {
      return { ok: false, status: 0, dados: null };
    } finally {
      clearTimeout(t);
    }
  }

  function mensagem(r) {
    if (r.status === 0) return "Não foi possível falar com o servidor. Confirme que a API está no ar e tente de novo.";
    const d = r.dados || {};
    if (typeof d.mensagem === "string") return d.mensagem;
    if (typeof d.detail === "string") return d.detail;
    return `A API respondeu com o código ${r.status}.`;
  }
  function aviso(r, modulo) {
    let titulo, texto;
    if (r.status === 404) { titulo = `${modulo} ainda não está ativo`; texto = "Esta versão da API ainda não publicou a rota. A tela volta a funcionar sozinha assim que ela estiver no ar."; }
    else if (r.status === 0) { titulo = "API indisponível"; texto = mensagem(r); }
    else if (r.status === 401 || r.status === 403) { titulo = `Acesso negado (${r.status})`; texto = (r.dados && r.dados.mensagem) || "Entre como administrador (senha e código do autenticador, ou token) para consultar o banco."; }
    else if (r.status === 400) { titulo = "Regra de negócio (400)"; texto = mensagem(r); }
    else { titulo = `Erro ${r.status}`; texto = mensagem(r); }
    return `<div class="alerta aviso"><h4>${esc(titulo)}</h4><p>${esc(texto)}</p></div>`;
  }

  /** Download autenticado: o cabeçalho de administrador não cabe num <a href>, então baixa como Blob. */
  async function baixarAutenticado(caminho, nomePadrao, botao) {
    const rotulo = botao ? botao.textContent : "";
    if (botao) { botao.disabled = true; botao.textContent = "Preparando…"; }
    const r = await api(caminho, { blob: true, timeout: 60000 });
    if (botao) { botao.disabled = false; botao.textContent = rotulo; }
    if (!r.ok) { toast(r.status === 404 ? "Rota ainda não publicada nesta versão da API" : mensagem(r)); return false; }
    const disp = (r.resp && r.resp.headers.get("Content-Disposition")) || "";
    const m = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(disp);
    const nome = m ? decodeURIComponent(m[1] || m[2]) : nomePadrao;
    const url = URL.createObjectURL(r.dados);
    const a = document.createElement("a");
    a.href = url;
    a.download = nome;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
    toast(`Download iniciado: ${nome}`);
    return true;
  }

  // ---------------------------------------------------------------- rótulos e formatação das células
  const TITULOS = {
    clientes: "Clientes", chaves: "Chaves de API emitidas", faturas: "Faturamento", envios_email: "E-mails enviados",
    eventos_comerciais: "Histórico comercial", avaliacoes: "Laudos de avaliação", predicoes: "Uso da API", vendas_historicas: "Vendas reais",
    modelos: "Modelos (artefatos)",
  };
  const ROTULOS = {
    id: "#", id_venda: "#", cliente_id: "Cliente (id)", cliente_nome: "Cliente", chave_id: "Chave (id)", nome: "Nome", email: "E-mail", empresa: "Empresa",
    plano: "Plano", criado_em: "Criado em", criada_em: "Criada em", revogada_em: "Revogada em", suspensa_em: "Suspensa em", prefixo: "Prefixo",
    limite_mensal: "Limite mensal", situacao: "Situação", status: "Status", competencia: "Competência", valor_usd: "Valor", predicoes: "Predições",
    emitida_em: "Emitida em", vencimento: "Vencimento", paga_em: "Paga em", destinatario: "Destinatário", assunto: "Assunto", modo: "Modo",
    tipo: "Tipo", detalhe: "Detalhe", titulo: "Título", responsavel: "Responsável", origem: "Origem", cep: "CEP", cidade: "Cidade",
    quartos: "Quartos", banheiros: "Banheiros", area_util_m2: "Área útil (m²)", preco_estimado_usd: "Preço estimado", preco_real_usd: "Preço real",
    preco_usd: "Preço", preco_m2_usd: "Preço por m²", latencia_ms: "Latência (ms)", status_http: "HTTP", data_venda: "Data da venda", faixa_preco: "Faixa de preço",
    chave_prefixo: "Chave", chaves: "Chaves", sintetico: "Exemplo", cliente_chave_id: "Chave do cliente", id_imovel: "Imóvel", versao_modelo: "Versão do modelo",
    faixa_min: "Faixa mínima", faixa_max: "Faixa máxima", area_terreno_m2: "Terreno (m²)", padrao: "Padrão", condicao: "Conservação", vista: "Vista",
    frente_agua: "Frente para a água", ano_construcao: "Ano de construção", ano_reforma: "Ano da reforma", arquivo: "Arquivo", entrada_json: "Entrada (JSON)",
    hash_sha256: "Hash SHA-256", sha256: "SHA-256", versao: "Versão", nome_arquivo: "Arquivo", tamanho_bytes: "Tamanho (bytes)", formato: "Formato",
    estimador: "Estimador", treinado_em: "Treinado em", registrado_em: "Registrado em", ativo: "Ativo",
  };
  const rotulo = (c) => ROTULOS[c] || (c.charAt(0).toUpperCase() + c.slice(1)).replace(/_/g, " ");
  const nomeCol = (c) => (typeof c === "string" ? c : (c && (c.nome || c.coluna || c.name)) || "");
  const rotuloCol = (c) => (typeof c === "object" && c && (c.rotulo || c.titulo)) || rotulo(nomeCol(c));

  // Situações com chip de cor (verde, laranja, vermelho)
  const COR_SITUACAO = { ativa: "ok", ativo: "ok", paga: "ok", enviado: "ok", enviada: "ok", suspensa: "aviso", em_aberto: "aviso", vencida: "ruim", cancelada: "ruim", revogada: "ruim", erro: "ruim", falha: "ruim" };
  const textoSituacao = (v) => String(v).replace(/_/g, " ");
  const chipSituacao = (v) => `<span class="chip ${COR_SITUACAO[String(v).toLowerCase()] || ""} bd-chip-situacao">${esc(textoSituacao(v))}</span>`;
  const FILTROS = {
    chaves: { coluna: "situacao", valores: ["ativa", "suspensa", "revogada"] },
    faturas: { coluna: "status", valores: ["paga", "em_aberto", "vencida", "cancelada"] },
  };

  const CRU = /^(id|id_.*|.*_id|cep|ano_.*|latitude|longitude|prefixo|status_http|zipcode)$/;
  function celula(col, v) {
    if (v === null || v === undefined || v === "") return '<span class="bd-vazio">—</span>';
    if (col === "status" || col === "situacao") return chipSituacao(v);
    if (col === "sintetico" || col === "frente_agua") return Number(v) ? (col === "sintetico" ? '<span class="chip aviso bd-chip-situacao">sintético</span>' : "Sim") : "Não";
    if (/_usd$/.test(col) || col === "valor") return Number.isFinite(Number(v)) ? usd(v) : esc(v);
    if (col === "competencia") return esc(competencia(v));
    if (typeof v === "string" && (RE_DATA.test(v) || RE_DATA_HORA.test(v)) && /(_em$|^data|vencimento)/.test(col)) return esc(dataBR(v));
    if (typeof v === "number" && !CRU.test(col)) return num(v, Number.isInteger(v) ? 0 : 2);
    if (typeof v === "object") return `<code>${esc(JSON.stringify(v).slice(0, 80))}</code>`;
    const s = String(v);
    return s.length > 70 ? `<span title="${esc(s)}">${esc(s.slice(0, 68))}…</span>` : esc(s);
  }
  const ehNumerica = (col) => /_usd$|_m2$|_ms$|^quartos$|^banheiros$|^predicoes$|^limite_mensal$|^linhas$|^chaves$/.test(col);
  const maiuscula = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  const idDe = (linha, cols) => (linha.id ?? linha.id_venda ?? linha[nomeCol(cols[0])]);

  // ---------------------------------------------------------------- estado
  const estado = {
    raiz: null, secoes: [], secao: null, busca: "", pagina: 1, porPagina: 20, ordem: "", direcao: "desc", filtro: "",
    pedido: 0, linhas: [], colunas: [], esquema: null, historicoAberto: false, iniciado: false,
  };
  const secaoAtual = () => estado.secoes.find((s) => s.secao === estado.secao) || null;

  // ---------------------------------------------------------------- janelas (registro e confirmação)
  function garantirJanelas() {
    if ($("#bd-modal")) return;
    const div = document.createElement("div");
    div.innerHTML = `
      <div class="modal bd-modal" id="bd-modal" hidden role="dialog" aria-modal="true" aria-labelledby="bd-modal-titulo">
        <div class="modal-caixa bd-modal-caixa">
          <div class="codigo-topo"><h3 class="cartao-titulo" id="bd-modal-titulo">Registro</h3><button type="button" class="btn-mini" data-bd-fechar>Fechar</button></div>
          <div id="bd-modal-aviso" aria-live="polite"></div>
          <div class="bd-modal-corpo" id="bd-modal-corpo"></div>
          <div class="bd-modal-acoes" id="bd-modal-acoes"></div>
        </div>
      </div>
      <div class="modal bd-modal" id="bd-confirmar" hidden role="alertdialog" aria-modal="true" aria-labelledby="bd-conf-titulo">
        <div class="modal-caixa modal-pequeno">
          <div class="confirmar-caixa perigo">
            <h4 id="bd-conf-titulo">Confirmar</h4>
            <p class="nota" id="bd-conf-texto"></p>
            <div class="acoes"><button type="button" class="btn btn-pri" id="bd-conf-sim">Confirmar</button><button type="button" class="btn btn-borda" id="bd-conf-nao">Cancelar</button></div>
          </div>
        </div>
      </div>`;
    while (div.firstElementChild) document.body.appendChild(div.firstElementChild);
    const modal = $("#bd-modal"), conf = $("#bd-confirmar");
    modal.addEventListener("click", (ev) => { if (ev.target === modal || ev.target.closest("[data-bd-fechar]")) modal.hidden = true; });
    modal.addEventListener("click", acaoRegistro);
    conf.addEventListener("click", (ev) => {
      if (ev.target.id === "bd-conf-sim") responderConfirmacao(true);
      else if (ev.target === conf || ev.target.id === "bd-conf-nao") responderConfirmacao(false);
    });
    // Esc (tratado por app.js para toda .modal) apenas esconde: a confirmação pendente vira "não"
    new MutationObserver(() => { if (conf.hidden) responderConfirmacao(false); }).observe(conf, { attributes: true, attributeFilter: ["hidden"] });
    // Esc fecha só a janela de cima destas duas; a fase de captura evita que app.js feche outra junto
    window.addEventListener("keydown", (ev) => {
      if (ev.key !== "Escape" || (conf.hidden && modal.hidden)) return;
      ev.stopPropagation();
      if (!conf.hidden) conf.hidden = true; else modal.hidden = true;
    }, true);
  }
  let resolverConfirmacao = null;
  function responderConfirmacao(sim) {
    const conf = $("#bd-confirmar");
    if (conf && !conf.hidden) conf.hidden = true;
    const r = resolverConfirmacao;
    resolverConfirmacao = null;
    if (r) r(sim);
  }
  function confirmar(titulo, texto, rotuloSim) {
    garantirJanelas();
    if (resolverConfirmacao) responderConfirmacao(false);
    $("#bd-conf-titulo").textContent = titulo;
    $("#bd-conf-texto").textContent = texto;
    $("#bd-conf-sim").textContent = rotuloSim || "Confirmar";
    $("#bd-confirmar").hidden = false;
    setTimeout(() => $("#bd-conf-nao").focus(), 30);
    return new Promise((ok) => { resolverConfirmacao = ok; });
  }

  // ---------------------------------------------------------------- marcação da tela
  function montar(container) {
    const raiz = document.createElement("div");
    raiz.className = "bd-raiz";
    raiz.id = "bd-raiz";
    raiz.innerHTML = `
      <div class="secao-titulo bloco"><div><h2>Explorador do banco</h2><p>Consulte cada seção com busca, filtros, ordenação por coluna e exportação em CSV. Clique numa linha para abrir o registro completo.</p></div></div>
      <div class="cartao bloco bd-explorador">
        <div class="abas bd-abas" id="bd-abas" role="tablist" aria-label="Seções do banco"></div>
        <p class="nota bd-descricao" id="bd-descricao"></p>
        <div class="bd-barra">
          <label class="bd-busca"><span class="bd-sr">Buscar nesta seção</span><input type="search" id="bd-busca" placeholder="Buscar nesta seção" autocomplete="off"></label>
          <div class="bd-chips" id="bd-chips" role="group" aria-label="Filtrar por situação"></div>
          <button type="button" class="btn-mini" id="bd-exportar">Exportar CSV</button>
        </div>
        <div id="bd-aviso" aria-live="polite"></div>
        <div class="tabela-wrap bd-tabela" id="bd-tabela"><p class="nota">Carregando seções…</p></div>
        <div class="paginacao" id="bd-paginacao"></div>
      </div>
      <div class="secao-titulo bloco"><div><h2>Administração do banco</h2><p>Saúde do arquivo SQLite, cópia de segurança e dados de exemplo para demonstração.</p></div></div>
      <div class="bd-admin bloco">
        <div class="cartao bd-saude" id="bd-saude">
          <div class="codigo-topo"><h3 class="cartao-titulo">Saúde do banco</h3><button type="button" class="btn-mini" id="bd-saude-atualizar">Atualizar</button></div>
          <div id="bd-saude-corpo"><p class="nota">Lendo o banco…</p></div>
        </div>
        <div class="cartao bd-manutencao">
          <h3 class="cartao-titulo">Manutenção</h3>
          <div class="bd-bloco-acao">
            <div><b>Cópia de segurança</b><p class="nota">Baixa o arquivo .db completo, como está agora.</p></div>
            <button type="button" class="btn btn-borda" id="bd-backup">Baixar cópia de segurança</button>
          </div>
          <div class="bd-bloco-acao">
            <div><b>Dados de exemplo</b><p class="nota">Clientes, chaves, faturas e e-mails fictícios para demonstrar as telas.</p></div>
            <div class="acoes"><button type="button" class="btn btn-borda" id="bd-sint-carregar">Carregar dados de exemplo</button><button type="button" class="btn btn-borda" id="bd-sint-remover">Remover dados de exemplo</button></div>
          </div>
          <div class="alerta aviso bd-aviso-sint"><h4>Dados sintéticos</h4><p>Os dados de exemplo são gerados artificialmente: não representam clientes, cobranças ou e-mails reais. Remova-os antes de usar o banco em produção.</p></div>
          <div id="bd-manutencao-aviso" aria-live="polite"></div>
        </div>
      </div>`;
    // Entra antes da documentação do banco (quando existir); senão, no fim da tela
    const doc = $("#esquema-info", container);
    const antes = doc ? doc.closest(".secao-titulo") : null;
    if (antes && antes.parentNode) antes.parentNode.insertBefore(raiz, antes);
    else container.appendChild(raiz);
    estado.raiz = raiz;

    $("#bd-abas", raiz).addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-secao]");
      if (b && b.dataset.secao !== estado.secao) trocarSecao(b.dataset.secao);
    });
    $("#bd-abas", raiz).addEventListener("keydown", (ev) => {
      if (ev.key !== "ArrowRight" && ev.key !== "ArrowLeft") return;
      const bs = $$("[data-secao]", ev.currentTarget), i = bs.findIndex((b) => b.dataset.secao === estado.secao);
      const prox = bs[(i + (ev.key === "ArrowRight" ? 1 : bs.length - 1)) % bs.length];
      if (prox) { trocarSecao(prox.dataset.secao); prox.focus(); }
    });
    let espera = 0;
    $("#bd-busca", raiz).addEventListener("input", (ev) => {
      clearTimeout(espera);
      espera = setTimeout(() => { estado.busca = ev.target.value.trim(); estado.pagina = 1; carregarPagina(); }, 350);
    });
    $("#bd-chips", raiz).addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-filtro]");
      if (!b) return;
      estado.filtro = estado.filtro === b.dataset.filtro ? "" : b.dataset.filtro;
      estado.pagina = 1;
      desenharChips();
      carregarPagina();
    });
    $("#bd-exportar", raiz).addEventListener("click", (ev) => {
      const s = secaoAtual();
      if (!s) return;
      const q = parametrosBusca(s);
      q.set("formato", "csv");
      if (modoFiltro(s) === "local") toast("O CSV sai com a busca atual; o filtro de situação desta seção não vai para o arquivo");
      baixarAutenticado(`/v1/admin/banco/${encodeURIComponent(s.secao)}/exportar?${q}`, `${s.secao}.csv`, ev.currentTarget);
    });
    $("#bd-tabela", raiz).addEventListener("click", cliqueTabela);
    $("#bd-tabela", raiz).addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && ev.target.matches("tr[data-id]")) abrirRegistro(ev.target.dataset.id);
    });
    $("#bd-paginacao", raiz).addEventListener("click", (ev) => {
      const b = ev.target.closest("[data-pagina]");
      if (!b || b.disabled) return;
      estado.pagina = Number(b.dataset.pagina);
      carregarPagina();
    });
    $("#bd-paginacao", raiz).addEventListener("change", (ev) => {
      if (ev.target.id !== "bd-por-pagina") return;
      estado.porPagina = Number(ev.target.value) || 20;
      estado.pagina = 1;
      carregarPagina();
    });
    $("#bd-saude-atualizar", raiz).addEventListener("click", carregarSaude);
    $("#bd-backup", raiz).addEventListener("click", (ev) => {
      const d = new Date(), p = (n) => String(n).padStart(2, "0");
      baixarAutenticado("/v1/admin/banco/backup", `banco_${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}_${p(d.getHours())}${p(d.getMinutes())}.db`, ev.currentTarget);
    });
    $("#bd-sint-carregar", raiz).addEventListener("click", (ev) => sinteticos("POST", ev.currentTarget));
    $("#bd-sint-remover", raiz).addEventListener("click", (ev) => sinteticos("DELETE", ev.currentTarget));
  }

  // ---------------------------------------------------------------- seções
  async function carregarSecoes() {
    const r = await api("/v1/admin/banco/secoes");
    const lista = r.ok ? (Array.isArray(r.dados) ? r.dados : (r.dados && (r.dados.secoes || r.dados.itens)) || null) : null;
    if (!Array.isArray(lista)) {
      $("#bd-abas", estado.raiz).innerHTML = "";
      $("#bd-tabela", estado.raiz).innerHTML = "";
      $("#bd-paginacao", estado.raiz).innerHTML = "";
      $("#bd-aviso", estado.raiz).innerHTML = aviso(r, "O explorador do banco");
      return false;
    }
    estado.secoes = lista.map((s) => ({ ...s, secao: s.secao || s.tabela, titulo: s.titulo || TITULOS[s.secao || s.tabela] || rotulo(s.secao || s.tabela || "") }));
    if (!estado.secoes.some((s) => s.secao === estado.secao)) estado.secao = estado.secoes.length ? estado.secoes[0].secao : null;
    desenharAbas();
    return true;
  }
  function desenharAbas() {
    $("#bd-abas", estado.raiz).innerHTML = estado.secoes.map((s) => {
      const ativa = s.secao === estado.secao;
      return `<button type="button" role="tab" data-secao="${esc(s.secao)}" aria-selected="${ativa}" tabindex="${ativa ? 0 : -1}" class="${ativa ? "ativa" : ""}" title="${esc(s.descricao || "")}">${esc(s.titulo)}<small>${s.total != null ? num(s.total) : "—"}</small></button>`;
    }).join("");
    const s = secaoAtual();
    $("#bd-descricao", estado.raiz).textContent = s ? `${s.descricao || ""}${s.tabela ? (s.descricao ? " · " : "") + "tabela " + s.tabela : ""}` : "";
    desenharChips();
  }
  function desenharChips() {
    const s = secaoAtual(), f = s && FILTROS[s.secao], caixa = $("#bd-chips", estado.raiz);
    if (!f) { caixa.innerHTML = ""; caixa.hidden = true; return; }
    caixa.hidden = false;
    caixa.innerHTML = `<button type="button" class="bd-filtro${estado.filtro ? "" : " ativo"}" data-filtro="" aria-pressed="${!estado.filtro}">Todas</button>` +
      f.valores.map((v) => `<button type="button" class="bd-filtro ${COR_SITUACAO[v] || ""}${estado.filtro === v ? " ativo" : ""}" data-filtro="${esc(v)}" aria-pressed="${estado.filtro === v}">${esc(maiuscula(textoSituacao(v)))}</button>`).join("");
  }
  function trocarSecao(secao) {
    estado.secao = secao;
    estado.pagina = 1;
    estado.ordem = "";
    estado.direcao = "desc";
    estado.filtro = "";
    estado.busca = "";
    $("#bd-busca", estado.raiz).value = "";
    desenharAbas();
    carregarPagina();
  }

  // ---------------------------------------------------------------- página da tabela
  async function carregarPagina() {
    const s = secaoAtual();
    if (!s) { $("#bd-tabela", estado.raiz).innerHTML = '<p class="nota">Nenhuma seção disponível.</p>'; return; }
    const pedido = ++estado.pedido;
    const f = FILTROS[s.secao], modo = modoFiltro(s);
    const q = parametrosBusca(s);
    // Filtro sem apoio do servidor (situação das chaves): traz o máximo de uma vez e filtra aqui
    q.set("pagina", modo === "local" ? 1 : estado.pagina);
    q.set("por_pagina", modo === "local" ? 100 : estado.porPagina);
    $("#bd-tabela", estado.raiz).classList.add("carregando");
    const r = await api(`/v1/admin/banco/${encodeURIComponent(s.secao)}?${q}`);
    if (pedido !== estado.pedido) return; // resposta de uma busca antiga
    $("#bd-tabela", estado.raiz).classList.remove("carregando");
    if (!r.ok || !r.dados) {
      $("#bd-aviso", estado.raiz).innerHTML = aviso(r, `A seção ${s.titulo}`);
      $("#bd-tabela", estado.raiz).innerHTML = "";
      $("#bd-paginacao", estado.raiz).innerHTML = "";
      return;
    }
    $("#bd-aviso", estado.raiz).innerHTML = "";
    const d = r.dados;
    let linhas = Array.isArray(d.linhas) ? d.linhas : Array.isArray(d.itens) ? d.itens : [];
    // A busca por texto pode casar o termo em outra coluna: a situação exata é conferida aqui
    if (modo) linhas = linhas.filter((l) => String(l[f.coluna]) === estado.filtro);
    const filtroLocal = modo === "local";
    estado.linhas = linhas;
    estado.rotulos = (d.rotulos && typeof d.rotulos === "object" ? d.rotulos : s.rotulos) || {};
    estado.colunas = (Array.isArray(d.colunas) && d.colunas.length ? d.colunas : s.colunas && s.colunas.length ? s.colunas : Object.keys(linhas[0] || {}));
    if (d.total != null && !estado.busca && !estado.filtro && s.total !== d.total) { s.total = d.total; desenharAbas(); }
    desenharTabela(s, filtroLocal);
    if (filtroLocal) desenharPaginacao({ pagina: 1, paginas: 1, total: linhas.length }, linhas.length, Number(d.total) > linhas.length && Number(d.paginas) > 1);
    else if (modo === "servidor" && linhas.length < (Array.isArray(d.linhas) ? d.linhas.length : 0)) desenharPaginacao({ ...d, total: null }, linhas.length);
    else desenharPaginacao(d, linhas.length);
  }
  /** "servidor": a situação entra como termo de busca (coluna pesquisável); "local": filtra no navegador; "": sem filtro. */
  function modoFiltro(s) {
    const f = FILTROS[s.secao];
    if (!f || !estado.filtro) return "";
    return !estado.busca && (s.colunas_busca || []).includes(f.coluna) ? "servidor" : "local";
  }
  function parametrosBusca(s) {
    const q = new URLSearchParams();
    const termo = estado.busca || (modoFiltro(s) === "servidor" ? estado.filtro : "");
    if (termo) q.set("busca", termo);
    if (estado.ordem) { q.set("ordem", estado.ordem); q.set("direcao", estado.direcao); }
    return q;
  }
  function desenharTabela(s, filtroLocal) {
    const cols = estado.colunas, caixa = $("#bd-tabela", estado.raiz);
    if (!estado.linhas.length) {
      caixa.innerHTML = `<p class="nota bd-nada">${estado.busca || estado.filtro ? "Nenhum registro encontrado com esses critérios." : "Esta seção ainda não tem registros."}</p>`;
      return;
    }
    const comAcoes = s.secao === "faturas" && s.pode_editar !== false;
    const legendas = estado.rotulos || {};
    const cab = cols.map((c) => {
      const n = nomeCol(c), ativa = estado.ordem === n, seta = ativa ? (estado.direcao === "asc" ? " ▲" : " ▼") : "";
      return `<th class="ordenavel${ehNumerica(n) ? " num" : ""}" data-ordem="${esc(n)}" title="${esc(legendas[n] ? legendas[n] + " · " : "")}Ordenar por ${esc(rotuloCol(c))}" aria-sort="${ativa ? (estado.direcao === "asc" ? "ascending" : "descending") : "none"}" tabindex="0">${esc(rotuloCol(c))}${seta}</th>`;
    }).join("") + (comAcoes ? "<th>Ações</th>" : "");
    const corpo = estado.linhas.map((l) => {
      const id = idDe(l, cols);
      const tds = cols.map((c) => { const n = nomeCol(c); return `<td class="${ehNumerica(n) ? "num" : ""}">${celula(n, l[n])}</td>`; }).join("");
      const acao = comAcoes ? `<td>${l.status === "em_aberto" || l.status === "vencida" ? `<button type="button" class="btn-mini" data-baixa="${esc(id)}">Dar baixa</button>` : ""}</td>` : "";
      return `<tr class="clicavel" data-id="${esc(id)}" tabindex="0">${tds}${acao}</tr>`;
    }).join("");
    caixa.innerHTML = `${filtroLocal ? '<p class="nota bd-nota-filtro">Situação filtrada entre os 100 registros mais recentes desta seção.</p>' : ""}<table class="tabela bd-tabela-dados"><thead><tr>${cab}</tr></thead><tbody>${corpo}</tbody></table>`;
    $$("th[data-ordem]", caixa).forEach((th) => th.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); th.click(); } }));
  }
  function desenharPaginacao(d, n, truncado) {
    const pag = Number(d.pagina) || estado.pagina, paginas = Math.max(1, Number(d.paginas) || 1), total = d.total != null ? Number(d.total) : n;
    const resumo = d.total == null ? `${num(n)} nesta página com a situação escolhida` : `${num(total)} ${total === 1 ? "registro" : "registros"}${truncado ? " entre os 100 mais recentes" : ""}`;
    $("#bd-paginacao", estado.raiz).innerHTML = `<span class="nota">${resumo} · página ${num(pag)} de ${num(paginas)}</span>
      <div><label class="bd-por-pagina"><span class="nota">por página</span><select id="bd-por-pagina">${[10, 20, 50, 100].map((v) => `<option value="${v}"${v === estado.porPagina ? " selected" : ""}>${v}</option>`).join("")}</select></label>
      <button type="button" class="btn-mini" data-pagina="1"${pag <= 1 ? " disabled" : ""} aria-label="Primeira página">«</button>
      <button type="button" class="btn-mini" data-pagina="${pag - 1}"${pag <= 1 ? " disabled" : ""}>Anterior</button>
      <button type="button" class="btn-mini" data-pagina="${pag + 1}"${pag >= paginas ? " disabled" : ""}>Próxima</button>
      <button type="button" class="btn-mini" data-pagina="${paginas}"${pag >= paginas ? " disabled" : ""} aria-label="Última página">»</button></div>`;
  }
  function cliqueTabela(ev) {
    const th = ev.target.closest("th[data-ordem]");
    if (th) {
      const c = th.dataset.ordem;
      if (estado.ordem === c) estado.direcao = estado.direcao === "asc" ? "desc" : "asc";
      else { estado.ordem = c; estado.direcao = "asc"; }
      estado.pagina = 1;
      carregarPagina();
      return;
    }
    const baixa = ev.target.closest("[data-baixa]");
    if (baixa) { ev.stopPropagation(); darBaixa(baixa.dataset.baixa, baixa); return; }
    const tr = ev.target.closest("tr[data-id]");
    if (tr) abrirRegistro(tr.dataset.id);
  }

  // ---------------------------------------------------------------- registro completo
  let registroAtual = null;
  async function abrirRegistro(id) {
    const s = secaoAtual();
    if (!s || id == null || id === "") return;
    garantirJanelas();
    const modal = $("#bd-modal");
    $("#bd-modal-titulo").textContent = `${s.titulo} · registro #${id}`;
    $("#bd-modal-aviso").innerHTML = "";
    $("#bd-modal-corpo").innerHTML = '<p class="nota">Carregando registro…</p>';
    $("#bd-modal-acoes").innerHTML = "";
    modal.hidden = false;
    const r = await api(`/v1/admin/banco/${encodeURIComponent(s.secao)}/${encodeURIComponent(id)}`);
    if (!r.ok || !r.dados) {
      // Sem a rota de detalhe, mostra a linha que já está na tabela
      const linha = estado.linhas.find((l) => String(idDe(l, estado.colunas)) === String(id));
      if (linha && r.status === 404) { registroAtual = { secao: s, id, reg: linha }; desenharRegistro(); $("#bd-modal-aviso").innerHTML = '<p class="nota">Detalhe completo indisponível nesta versão da API; exibindo as colunas da tabela.</p>'; return; }
      $("#bd-modal-corpo").innerHTML = aviso(r, "O registro");
      return;
    }
    registroAtual = { secao: s, id, reg: r.dados.registro || r.dados };
    desenharRegistro();
  }
  function valorCompleto(k, v) {
    if (v === null || v === undefined || v === "") return '<span class="bd-vazio">—</span>';
    if (typeof v === "object") return `<pre class="bd-json">${esc(JSON.stringify(v, null, 2))}</pre>`;
    if (typeof v === "string" && /^\s*[[{]/.test(v)) {
      try { return `<pre class="bd-json">${esc(JSON.stringify(JSON.parse(v), null, 2))}</pre>`; } catch (e) { /* texto comum */ }
    }
    if (typeof v === "string" && v.length > 70) return `<span class="bd-texto-longo">${esc(v)}</span>`;
    return celula(k, v);
  }
  function desenharRegistro() {
    const { secao: s, id, reg } = registroAtual;
    const legendas = estado.rotulos || {};
    $("#bd-modal-corpo").innerHTML = `<dl class="bd-registro">${Object.keys(reg).map((k) => `<dt title="${esc(legendas[k] || "")}">${esc(rotulo(k))}<code>${esc(k)}</code></dt><dd>${valorCompleto(k, reg[k])}</dd>`).join("")}</dl>`;
    const acoes = [];
    if (s.secao === "faturas" && s.pode_editar !== false) {
      const st = String(reg.status || "");
      acoes.push(`<div class="bd-status-edicao"><label for="bd-novo-status" class="nota">Status da fatura</label>
        <select id="bd-novo-status">${FILTROS.faturas.valores.map((v) => `<option value="${v}"${v === st ? " selected" : ""}>${esc(maiuscula(textoSituacao(v)))}</option>`).join("")}</select>
        <button type="button" class="btn-mini" data-reg-acao="status">Salvar status</button>
        ${st !== "paga" ? `<button type="button" class="btn btn-pri bd-btn-baixa" data-reg-acao="baixa">Dar baixa (paga)</button>` : ""}</div>`);
    }
    if (s.pode_excluir) acoes.push(`<button type="button" class="btn btn-borda bd-btn-excluir" data-reg-acao="excluir">Excluir registro #${esc(id)}</button>`);
    $("#bd-modal-acoes").innerHTML = acoes.join("");
  }
  async function acaoRegistro(ev) {
    const b = ev.target.closest("[data-reg-acao]");
    if (!b || !registroAtual || b.disabled) return;
    const { secao: s, id } = registroAtual, a = b.dataset.regAcao;
    if (a === "baixa") { await mudarStatus(id, "paga", b); return; }
    if (a === "status") { await mudarStatus(id, $("#bd-novo-status").value, b); return; }
    if (a === "excluir") {
      const ok = await confirmar(`Excluir o registro #${id}?`, `O registro #${id} de ${s.titulo} será apagado do banco. Esta ação não pode ser desfeita.`, "Excluir");
      if (!ok) return;
      b.disabled = true;
      const r = await api(`/v1/admin/banco/${encodeURIComponent(s.secao)}/${encodeURIComponent(id)}`, { metodo: "DELETE" });
      b.disabled = false;
      if (!r.ok) { $("#bd-modal-aviso").innerHTML = aviso(r, "A exclusão"); return; }
      $("#bd-modal").hidden = true;
      toast(`Registro #${id} excluído de ${s.titulo}`);
      atualizarTudo();
    }
  }
  async function mudarStatus(id, status, botao) {
    const rot = botao.textContent;
    botao.disabled = true;
    botao.textContent = "Salvando…";
    const r = await api(`/v1/admin/banco/faturas/${encodeURIComponent(id)}`, { metodo: "PATCH", corpo: { status } });
    botao.disabled = false;
    botao.textContent = rot;
    const modalAberto = !$("#bd-modal").hidden && registroAtual && String(registroAtual.id) === String(id);
    if (!r.ok) {
      if (modalAberto) $("#bd-modal-aviso").innerHTML = aviso(r, "A alteração da fatura");
      else toast(mensagem(r));
      return false;
    }
    toast(status === "paga" ? `Baixa registrada: fatura #${id} paga` : `Fatura #${id}: status alterado para ${textoSituacao(status)}`);
    if (modalAberto) {
      const novo = r.dados && (r.dados.registro || r.dados);
      registroAtual.reg = novo && typeof novo === "object" && Object.keys(novo).length ? novo : { ...registroAtual.reg, status };
      $("#bd-modal-aviso").innerHTML = "";
      desenharRegistro();
    }
    atualizarTudo();
    return true;
  }
  function darBaixa(id, botao) { return mudarStatus(id, "paga", botao); }

  // ---------------------------------------------------------------- saúde e manutenção
  async function carregarSaude() {
    const corpo = $("#bd-saude-corpo", estado.raiz);
    const r = await api("/v1/admin/banco/saude");
    if (!r.ok || !r.dados) { corpo.innerHTML = aviso(r, "O diagnóstico do banco"); return; }
    const d = r.dados, integ = String(d.integridade ?? "—"), ok = /^ok$/i.test(integ) || d.integridade === true;
    const tabelas = Array.isArray(d.tabelas) ? d.tabelas : [];
    const totalLinhas = tabelas.reduce((s, t) => s + (Number(t.linhas) || 0), 0);
    const maior = Math.max(1, ...tabelas.map((t) => Number(t.linhas) || 0));
    const sint = d.sinteticos && d.sinteticos.clientes != null ? Number(d.sinteticos.clientes) : null;
    corpo.innerHTML = `
      <div class="bd-saude-kpis">
        <div class="stat"><strong><span class="chip ${ok ? "ok" : "ruim"}">${ok ? "íntegro" : esc(integ)}</span></strong><span>integridade</span></div>
        <div class="stat"><strong>${d.tamanho_bytes != null ? bytes(d.tamanho_bytes) : "—"}</strong><span>tamanho do arquivo</span></div>
        <div class="stat"><strong>${num(totalLinhas)}</strong><span>linhas em ${num(tabelas.length)} tabelas</span></div>
        <div class="stat"><strong>${sint != null ? num(sint) : "—"}</strong><span>clientes sintéticos</span></div>
      </div>
      ${d.arquivo ? `<p class="nota bd-arquivo">Arquivo: <code>${esc(d.arquivo)}</code></p>` : ""}
      <ul class="bd-linhas-tabela">${tabelas.map((t) => `<li><code>${esc(t.nome)}</code><span class="bd-barra-linhas"><i style="width:${Math.max(2, Math.round((Number(t.linhas) || 0) / maior * 100))}%"></i></span><b>${num(Number(t.linhas) || 0)}</b></li>`).join("")}</ul>
      <p class="nota">lido às ${new Date().toLocaleTimeString("pt-BR")}</p>`;
    const rem = $("#bd-sint-remover", estado.raiz);
    if (rem) rem.disabled = sint === 0;
  }
  function resumoContagens(d) {
    if (!d || typeof d !== "object") return "";
    const fonte = d.contagens || d.removidos || d.inseridos || d.criados || d;
    const NOMES = { envios_email: "e-mails", eventos_comerciais: "eventos comerciais", avaliacoes: "laudos", predicoes: "predições", vendas_historicas: "vendas" };
    const partes = Object.entries(fonte).filter(([, v]) => typeof v === "number").map(([k, v]) => `${num(v)} ${NOMES[k] || rotulo(k).toLowerCase()}`);
    return partes.join(", ");
  }
  async function sinteticos(metodo, botao) {
    const carregar = metodo === "POST";
    const ok = await confirmar(
      carregar ? "Carregar dados de exemplo?" : "Remover dados de exemplo?",
      carregar
        ? "Serão criados clientes, chaves, faturas, e-mails e eventos fictícios, marcados como sintéticos. Eles servem só para demonstrar as telas e não representam pessoas ou cobranças reais."
        : "Todos os registros marcados como sintéticos (clientes de exemplo e o que depende deles) serão apagados. Os dados reais não são tocados.",
      carregar ? "Carregar" : "Remover");
    if (!ok) return;
    const rot = botao.textContent;
    botao.disabled = true;
    botao.textContent = carregar ? "Carregando…" : "Removendo…";
    const r = await api("/v1/admin/banco/sinteticos", { metodo, timeout: 60000 });
    botao.disabled = false;
    botao.textContent = rot;
    const caixa = $("#bd-manutencao-aviso", estado.raiz);
    if (!r.ok) { caixa.innerHTML = aviso(r, carregar ? "A carga de dados de exemplo" : "A remoção de dados de exemplo"); return; }
    const resumo = resumoContagens(r.dados);
    caixa.innerHTML = "";
    toast(`${carregar ? "Dados de exemplo carregados" : "Dados de exemplo removidos"}${resumo ? ": " + resumo : ""}`);
    atualizarTudo();
  }

  async function atualizarTudo() {
    const ok = await carregarSecoes();
    if (ok) carregarPagina();
    carregarSaude();
  }

  // ---------------------------------------------------------------- históricos: só as 5 mais recentes à vista
  const LIMITE_HISTORICO = 5;
  function recolherHistorico(caixa) {
    if (!caixa || caixa.querySelector(".bd-historico")) return;
    const tabela = caixa.querySelector("table");
    const tbody = tabela && tabela.tBodies[0];
    if (!tbody || tbody.rows.length <= LIMITE_HISTORICO) return;
    const resto = Array.from(tbody.rows).slice(LIMITE_HISTORICO);
    const det = document.createElement("details");
    det.className = "bd-historico";
    det.open = estado.historicoAberto;
    const sum = document.createElement("summary");
    sum.innerHTML = `Históricos anteriores <span class="chip">${num(resto.length)}</span>`;
    const wrap = document.createElement("div");
    wrap.className = "tabela-wrap";
    const t2 = tabela.cloneNode(false);
    if (tabela.tHead) t2.appendChild(tabela.tHead.cloneNode(true));
    const tb2 = document.createElement("tbody");
    resto.forEach((tr) => tb2.appendChild(tr));
    t2.appendChild(tb2);
    wrap.appendChild(t2);
    det.append(sum, wrap);
    det.addEventListener("toggle", () => { estado.historicoAberto = det.open; });
    caixa.appendChild(det);
  }
  function vigiarHistoricos(container) {
    ["#tabela-predicoes"].forEach((sel) => {
      const caixa = $(sel, container) || $(sel);
      if (!caixa || caixa.dataset.bdVigiado) return;
      caixa.dataset.bdVigiado = "1";
      recolherHistorico(caixa);
      new MutationObserver(() => recolherHistorico(caixa)).observe(caixa, { childList: true });
    });
  }

  // ---------------------------------------------------------------- diagrama com as 9 tabelas
  const POS_TABELAS = {
    clientes: [0, 0], chaves: [1, 0], predicoes: [2, 0], vendas_historicas: [3, 0],
    envios_email: [0, 1], eventos_comerciais: [1, 1], faturas: [2, 1], avaliacoes: [3, 1],
    modelos: [0, 2],
  };
  const DESCRICOES = {
    modelos: "Artefatos do modelo: o .joblib carregado pela API, guardado como BLOB com versão, sha256, tamanho, métricas e a marca do ativo.",
    eventos_comerciais: "Trilha de auditoria do console comercial: emissão, troca de plano, suspensão, reativação, rotação, revogação e edição.",
    faturas: "Faturas mensais por cliente e chave: competência, plano, valor, predições cobradas, status, emissão, vencimento e pagamento.",
  };
  const ALVO_FK = { cliente_id: "clientes", chave_id: "chaves", cliente_chave_id: "chaves", predicao_id: "predicoes", venda_id: "vendas_historicas", avaliacao_id: "avaliacoes", envio_id: "envios_email", fatura_id: "faturas" };
  function desenharDiagrama(tabelasOrig) {
    const alvo = $("#diagrama");
    if (!alvo) return;
    const tabelas = tabelasOrig.map((t) => ({ ...t }));
    const W = 230, LIN = 17, TOPO = 30, MAXC = 8, GX = 60, GY = 56, NCOL = 4;
    const nomes = tabelas.map((t) => t.nome);
    Object.keys(POS_TABELAS).forEach((n) => { if (!nomes.includes(n)) tabelas.push({ nome: n, colunas: [], linhas: null, ausente: true }); });
    let extra = 0;
    const caixas = {};
    tabelas.forEach((t) => {
      const pos = POS_TABELAS[t.nome] || [extra % NCOL, 2 + Math.floor(extra++ / NCOL)];
      const cols = (t.colunas || []).slice(0, MAXC);
      caixas[t.nome] = { t, cols, x: 10 + pos[0] * (W + GX), col: pos[0], row: pos[1], h: TOPO + Math.max(1, cols.length + ((t.colunas || []).length > MAXC ? 1 : 0)) * LIN + 10 };
    });
    const alturaLinha = {};
    Object.values(caixas).forEach((c) => { alturaLinha[c.row] = Math.max(alturaLinha[c.row] || 0, c.h); });
    const yLinha = (r) => 10 + Object.keys(alturaLinha).filter((k) => Number(k) < r).reduce((s, k) => s + alturaLinha[k] + GY, 0);
    Object.values(caixas).forEach((c) => { c.y = yLinha(c.row); });
    const largura = 20 + NCOL * W + (NCOL - 1) * GX, altura = Math.max(...Object.values(caixas).map((c) => c.y + c.h)) + 10;
    const rels = [];
    Object.values(caixas).forEach((c) => (c.t.colunas || []).forEach((col, i) => {
      const ref = col.referencia || col.fk || ALVO_FK[col.nome];
      const nomeAlvo = typeof ref === "string" ? ref.split(".")[0] : null;
      if (nomeAlvo && caixas[nomeAlvo] && nomeAlvo !== c.t.nome) rels.push({ de: c, ate: caixas[nomeAlvo], col: col.nome, i: Math.min(i, MAXC) });
    }));
    const caminho = ({ de, ate, i }) => {
      const y1 = de.y + TOPO + i * LIN + 6;
      if (de.row === ate.row) {
        const esq = ate.x < de.x;
        const x1 = esq ? de.x : de.x + W, x2 = esq ? ate.x + W : ate.x, y2 = ate.y + TOPO / 2;
        return `M${x1},${y1} C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2},${y2}`;
      }
      const dir = ate.x > de.x, x1 = de.x + (dir ? W : 0), x2 = ate.x + W / 2 + (ate.x === de.x ? -W / 4 : 0), y2 = ate.y + ate.h;
      return `M${x1},${y1} C${x1 + (dir ? 40 : -40)},${y1} ${x2},${y2 + 40} ${x2},${y2}`;
    };
    const ehChave = (n) => n === "id" || n === "id_venda" || ALVO_FK[n];
    alvo.innerHTML = `<svg data-bd-diagrama="1" viewBox="0 0 ${largura} ${altura}" role="img" aria-label="Diagrama das relações entre as ${Object.keys(caixas).length} tabelas do banco">
      <defs><marker id="bd-seta" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="${cssVar("--accent-3") || "#a685fa"}"/></marker></defs>
      ${rels.map((r) => `<path class="t-rel" d="${caminho(r)}" marker-end="url(#bd-seta)"><title>${esc(r.de.t.nome)}.${esc(r.col)} → ${esc(r.ate.t.nome)}.id</title></path>`).join("")}
      ${Object.values(caixas).map((c) => `<g>
        <rect class="t-caixa" x="${c.x}" y="${c.y}" width="${W}" height="${c.h}" rx="10"${c.t.ausente ? ' stroke-dasharray="5 4"' : ""}/>
        <path class="t-topo" d="M${c.x},${c.y + 10} a10,10 0 0 1 10,-10 h${W - 20} a10,10 0 0 1 10,10 v${TOPO - 10} h-${W} z"${c.t.ausente ? ' opacity=".45"' : ""}/>
        <text class="t-nome" x="${c.x + 12}" y="${c.y + 20}">${esc(c.t.nome)}</text>
        <text class="t-linhas" x="${c.x + W - 12}" y="${c.y + 20}" text-anchor="end">${c.t.ausente ? "ainda não criada" : c.t.linhas != null ? num(c.t.linhas) + " linhas" : ""}</text>
        ${c.cols.map((col, i) => `<text class="t-col${ehChave(col.nome) ? " t-chave" : ""}" x="${c.x + 12}" y="${c.y + TOPO + 12 + i * LIN}">${col.nome === "id" || col.nome === "id_venda" ? "🔑 " : ALVO_FK[col.nome] ? "↗ " : ""}${esc(col.nome)}<tspan fill="${cssVar("--muted") || "#999"}"> ${esc(col.tipo || "")}</tspan></text>`).join("")}
        ${(c.t.colunas || []).length > MAXC ? `<text class="t-col" x="${c.x + 12}" y="${c.y + TOPO + 12 + MAXC * LIN}">+ ${c.t.colunas.length - MAXC} colunas</text>` : ""}
      </g>`).join("")}
    </svg>`;
  }
  // Cartões para as tabelas que o esquema ainda não traz (eventos_comerciais e faturas em bancos antigos)
  function completarCartoes() {
    const caixa = $("#esquema-cartoes");
    if (!caixa || !estado.esquema || caixa.querySelector(".alerta")) return;
    const presentes = new Set(estado.esquema.map((t) => t.nome));
    Object.keys(POS_TABELAS).forEach((n) => {
      if (presentes.has(n) || caixa.querySelector(`[data-bd-cartao="${n}"]`)) return;
      const div = document.createElement("div");
      div.className = "cartao esquema-cartao bd-cartao-ausente";
      div.dataset.bdCartao = n;
      div.innerHTML = `<h3>${esc(n)} <span>ainda não criada</span></h3><p>${esc(DESCRICOES[n] || "Tabela prevista no esquema; aparece aqui assim que a API criá-la.")}</p>`;
      caixa.appendChild(div);
    });
  }
  async function carregarEsquema() {
    const r = await api("/v1/relatorios/esquema");
    const ts = r.ok && r.dados ? (Array.isArray(r.dados) ? r.dados : r.dados.tabelas) : null;
    estado.esquema = Array.isArray(ts) ? ts : [];
    desenharDiagrama(estado.esquema);
    completarCartoes();
  }
  function vigiarEsquema() {
    // app.js redesenha o diagrama no formato de 6 tabelas: substitui pelo de 9 sempre que isso acontecer
    const diag = $("#diagrama"), cartoes = $("#esquema-cartoes");
    if (diag && !diag.dataset.bdVigiado) {
      diag.dataset.bdVigiado = "1";
      new MutationObserver(() => { if (estado.esquema && !diag.querySelector("svg[data-bd-diagrama]")) desenharDiagrama(estado.esquema); }).observe(diag, { childList: true });
    }
    if (cartoes && !cartoes.dataset.bdVigiado) {
      cartoes.dataset.bdVigiado = "1";
      new MutationObserver(() => completarCartoes()).observe(cartoes, { childList: true });
    }
  }

  // ---------------------------------------------------------------- entrada pública
  function iniciar(container) {
    const alvo = (typeof container === "string" ? $(container) : container) || $('[data-view="banco"]') || document.body;
    if (estado.iniciado && estado.raiz && document.body.contains(estado.raiz)) { atualizarTudo(); return; }
    estado.iniciado = true;
    garantirJanelas();
    montar(alvo);
    vigiarHistoricos(alvo);
    vigiarEsquema();
    carregarEsquema();
    carregarSecoes().then((ok) => { if (ok) carregarPagina(); });
    carregarSaude();
  }

  window.TelaBanco = { iniciar, atualizar: atualizarTudo };
})();
