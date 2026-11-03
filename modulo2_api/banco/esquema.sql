-- Banco de documentação do Avaliador Imobiliário (SQLite)
-- Criado e migrado automaticamente no lifespan da API.

CREATE TABLE IF NOT EXISTS clientes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nome       TEXT NOT NULL,
    email      TEXT NOT NULL,
    empresa    TEXT,
    plano      TEXT NOT NULL CHECK (plano IN ('basico', 'profissional', 'empresarial')),
    criado_em  TEXT NOT NULL,
    sintetico  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chaves (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id     INTEGER NOT NULL REFERENCES clientes (id),
    prefixo        TEXT NOT NULL,
    hash_sha256    TEXT NOT NULL UNIQUE,
    limite_mensal  INTEGER NOT NULL,
    criada_em      TEXT NOT NULL,
    revogada_em    TEXT,
    suspensa_em    TEXT
);

-- Trilha de auditoria do console comercial: cada emissão, troca de plano, suspensão,
-- reativação, troca de chave, revogação e edição de cadastro.
CREATE TABLE IF NOT EXISTS eventos_comerciais (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id  INTEGER NOT NULL REFERENCES clientes (id),
    chave_id    INTEGER REFERENCES chaves (id),
    tipo        TEXT NOT NULL CHECK (tipo IN ('emissao', 'troca_plano', 'suspensao', 'reativacao', 'rotacao', 'revogacao', 'edicao')),
    detalhe     TEXT,
    criado_em   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_eventos_cliente ON eventos_comerciais (cliente_id, criado_em);

CREATE TABLE IF NOT EXISTS predicoes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    criado_em           TEXT NOT NULL,
    chave_id            INTEGER REFERENCES chaves (id),
    origem              TEXT NOT NULL,
    cep                 TEXT,
    area_util_m2        REAL,
    preco_estimado_usd  REAL,
    latencia_ms         REAL,
    status_http         INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS envios_email (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id    INTEGER NOT NULL REFERENCES clientes (id),
    destinatario  TEXT NOT NULL,
    assunto       TEXT NOT NULL,
    modo          TEXT NOT NULL,
    status        TEXT NOT NULL,
    criado_em     TEXT NOT NULL,
    arquivo       TEXT
);

-- Faturamento mensal por cliente (uma fatura por competência). Na carga de exemplo,
-- as faturas são fictícias e pertencem a clientes com sintetico = 1.
CREATE TABLE IF NOT EXISTS faturas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id   INTEGER NOT NULL REFERENCES clientes (id),
    chave_id     INTEGER REFERENCES chaves (id),
    competencia  TEXT NOT NULL,              -- 'AAAA-MM'
    plano        TEXT NOT NULL,
    valor_usd    REAL NOT NULL,
    predicoes    INTEGER NOT NULL DEFAULT 0,
    status       TEXT NOT NULL CHECK (status IN ('paga', 'em_aberto', 'vencida', 'cancelada')),
    emitida_em   TEXT NOT NULL,
    vencimento   TEXT NOT NULL,
    paga_em      TEXT
);

CREATE INDEX IF NOT EXISTS idx_faturas_cliente_competencia ON faturas (cliente_id, competencia);
CREATE INDEX IF NOT EXISTS idx_faturas_status ON faturas (status);

CREATE INDEX IF NOT EXISTS idx_predicoes_chave_data ON predicoes (chave_id, criado_em);
CREATE INDEX IF NOT EXISTS idx_predicoes_data ON predicoes (criado_em);

-- Vendas reais de King County (data/raw/kc_house_data.csv), limpas pelas regras
-- do Módulo 1. Carregadas no lifespan só quando a tabela está vazia (< 5 s).
-- faixa_preco usa os quartis do preço da própria base.
CREATE TABLE IF NOT EXISTS vendas_historicas (
    id_venda         INTEGER PRIMARY KEY AUTOINCREMENT,
    id_imovel        INTEGER NOT NULL,
    data_venda       TEXT NOT NULL,
    preco_usd        REAL NOT NULL,
    quartos          INTEGER NOT NULL,
    banheiros        REAL NOT NULL,
    area_util_m2     REAL NOT NULL,
    area_terreno_m2  REAL NOT NULL,
    padrao           INTEGER NOT NULL,
    condicao         INTEGER NOT NULL,
    vista            INTEGER NOT NULL,
    frente_agua      INTEGER NOT NULL,
    ano_construcao   INTEGER NOT NULL,
    ano_reforma      INTEGER,
    cep              TEXT NOT NULL,
    cidade           TEXT NOT NULL,
    latitude         REAL NOT NULL,
    longitude        REAL NOT NULL,
    preco_m2_usd     REAL NOT NULL,
    faixa_preco      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_vendas_cep ON vendas_historicas (cep);
CREATE INDEX IF NOT EXISTS idx_vendas_quartos ON vendas_historicas (quartos);
CREATE INDEX IF NOT EXISTS idx_vendas_faixa ON vendas_historicas (faixa_preco);
CREATE INDEX IF NOT EXISTS idx_vendas_cidade ON vendas_historicas (cidade);
CREATE INDEX IF NOT EXISTS idx_vendas_data ON vendas_historicas (data_venda);

-- Laudos de avaliação. A amostra inicial ("amostra_base") são imóveis reais do
-- conjunto de TESTE do modelo (mesma divisão por id, random_state 42),
-- estratificados por quartos e faixa de preço, com o preço real ao lado.
CREATE TABLE IF NOT EXISTS avaliacoes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    criado_em           TEXT NOT NULL,
    titulo              TEXT NOT NULL,
    responsavel         TEXT,
    cliente_chave_id    INTEGER REFERENCES chaves (id),
    origem              TEXT NOT NULL CHECK (origem IN ('portal', 'api', 'amostra_base')),
    entrada_json        TEXT NOT NULL,
    quartos             INTEGER NOT NULL,
    banheiros           REAL NOT NULL,
    area_util_m2        REAL NOT NULL,
    padrao              INTEGER NOT NULL,
    cep                 TEXT NOT NULL,
    cidade              TEXT NOT NULL,
    latitude            REAL NOT NULL,
    longitude           REAL NOT NULL,
    preco_estimado_usd  REAL NOT NULL,
    faixa_min           REAL NOT NULL,
    faixa_max           REAL NOT NULL,
    preco_m2_usd        REAL NOT NULL,
    faixa_preco         TEXT NOT NULL,
    preco_real_usd      REAL,
    versao_modelo       TEXT NOT NULL,
    latencia_ms         REAL NOT NULL,
    sintetico           INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_avaliacoes_cep ON avaliacoes (cep);
CREATE INDEX IF NOT EXISTS idx_avaliacoes_quartos ON avaliacoes (quartos);
CREATE INDEX IF NOT EXISTS idx_avaliacoes_data ON avaliacoes (criado_em);
CREATE INDEX IF NOT EXISTS idx_avaliacoes_origem ON avaliacoes (origem);

-- Registro versionado do artefato do modelo: o mesmo .joblib que a API carrega do
-- disco, guardado aqui como BLOB, com sha256, métricas e a marca do artefato ativo.
-- Inserido no lifespan só quando o sha256 ainda não consta (idempotente).
CREATE TABLE IF NOT EXISTS modelos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    versao         TEXT NOT NULL,
    nome_arquivo   TEXT NOT NULL,
    sha256         TEXT NOT NULL UNIQUE,
    tamanho_bytes  INTEGER NOT NULL,
    formato        TEXT NOT NULL DEFAULT 'joblib' CHECK (formato IN ('joblib')),
    estimador      TEXT,
    metricas_json  TEXT,
    treinado_em    TEXT,
    registrado_em  TEXT NOT NULL,
    ativo          INTEGER NOT NULL DEFAULT 0,
    artefato       BLOB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_modelos_ativo ON modelos (ativo);
