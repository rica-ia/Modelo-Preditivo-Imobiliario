-- Banco de documentação do Avaliador Imobiliário (SQLite)
-- Criado e migrado automaticamente no lifespan da API.

CREATE TABLE IF NOT EXISTS clientes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    nome       TEXT NOT NULL,
    email      TEXT NOT NULL,
    empresa    TEXT,
    plano      TEXT NOT NULL CHECK (plano IN ('basico', 'profissional', 'empresarial')),
    criado_em  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chaves (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    cliente_id     INTEGER NOT NULL REFERENCES clientes (id),
    prefixo        TEXT NOT NULL,
    hash_sha256    TEXT NOT NULL UNIQUE,
    limite_mensal  INTEGER NOT NULL,
    criada_em      TEXT NOT NULL,
    revogada_em    TEXT
);

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

CREATE INDEX IF NOT EXISTS idx_predicoes_chave_data ON predicoes (chave_id, criado_em);
CREATE INDEX IF NOT EXISTS idx_predicoes_data ON predicoes (criado_em);
