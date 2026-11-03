"""Contratos do console comercial (clientes, chaves e e-mail) e dos relatórios."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Plano = Literal["basico", "profissional", "empresarial"]


class NovaChaveEntrada(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"nome": "Maria Souza", "email": "cliente@exemplo.com",
                                          "empresa": "Imobiliária Exemplo", "plano": "profissional"}]},
    )

    nome: str = Field(..., min_length=2, max_length=80, description="Nome do responsável.")
    email: str = Field(
        ..., max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", description="E-mail que recebe a chave.",
    )
    empresa: str | None = Field(None, max_length=80, description="Empresa (opcional).")
    plano: Plano = Field(..., description="basico (100/mês), profissional (1.000) ou empresarial (10.000).")


class EnvioEmailSaida(BaseModel):
    enviado: bool
    modo: Literal["smtp", "arquivo"]
    destinatario: str
    mensagem: str
    envio_id: int


class NovaChaveSaida(BaseModel):
    cliente_id: int
    chave_id: int
    prefixo: str
    chave: str = Field(..., description="Chave completa; exibida só nesta resposta.")
    plano: Plano
    limite_mensal: int
    email: EnvioEmailSaida


class ClienteSaida(BaseModel):
    cliente_id: int
    chave_id: int
    nome: str
    email: str
    empresa: str | None
    prefixo: str
    plano: Plano
    uso_mes: int = Field(..., ge=0)
    limite_mensal: int
    ativa: bool
    criado_em: str


class RevogacaoSaida(BaseModel):
    chave_id: int
    revogada_em: str


class UsoSaida(BaseModel):
    cliente: str
    plano: Plano
    limite_mensal: int
    usadas_mes: int = Field(..., ge=0)
    restantes: int = Field(..., ge=0)


class ContagemDia(BaseModel):
    dia: str
    total: int


class ContagemOrigem(BaseModel):
    origem: str
    total: int


class ContagemStatus(BaseModel):
    status: int
    total: int


class ResumoSaida(BaseModel):
    total_predicoes: int
    predicoes_hoje: int
    clientes: int
    chaves_ativas: int
    latencia_mediana_ms: float = Field(..., description="Mediana da latência das 200 últimas predições bem-sucedidas, em ms.")
    preco_medio_usd: float
    por_dia: list[ContagemDia]
    por_origem: list[ContagemOrigem]
    por_status: list[ContagemStatus]


class PredicaoRegistrada(BaseModel):
    id: int
    criado_em: str
    origem: str
    cliente: str
    cep: str | None
    area_util_m2: float | None
    preco_estimado_usd: float | None
    latencia_ms: float | None
    status_http: int


class ColunaDoc(BaseModel):
    nome: str
    tipo: str
    descricao: str


class IndiceDoc(BaseModel):
    nome: str
    colunas: list[str]
    unico: bool


class TabelaDoc(BaseModel):
    nome: str
    descricao: str
    linhas: int
    colunas: list[ColunaDoc]
    indices: list[IndiceDoc] = []


class EsquemaSaida(BaseModel):
    banco: str
    arquivo: str
    tabelas: list[TabelaDoc]
