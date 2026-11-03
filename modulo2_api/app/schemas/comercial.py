"""Contratos do console comercial (clientes, chaves e e-mail) e dos relatórios."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Plano = Literal["basico", "profissional", "empresarial"]
Situacao = Literal["ativa", "suspensa", "revogada"]


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
    plano: Plano = Field(..., description="basico (100/mês, US$ 29), profissional (1.000, US$ 199) ou empresarial (10.000, US$ 1.490).")


class PlanoSaida(BaseModel):
    plano: Plano
    nome: str
    limite_mensal: int = Field(..., description="Predições atendidas (HTTP 200) por mês.")
    preco_mensal_usd: float = Field(..., description="Mensalidade, em dólares americanos.")
    preco_por_predicao_usd: float = Field(..., description="Mensalidade dividida pelo limite.")


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
    preco_mensal_usd: float = Field(..., description="Mensalidade do plano, em dólares americanos.")
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
    preco_mensal_usd: float
    ativa: bool
    situacao: Situacao = Field(..., description="ativa, suspensa (temporária, sem cobrança) ou revogada (definitiva).")
    criado_em: str


class RevogacaoSaida(BaseModel):
    chave_id: int
    revogada_em: str
    email: EnvioEmailSaida | None = Field(None, description="Aviso de revogação enviado ao cliente; nulo se a chave já estava revogada.")


class TrocaPlanoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"plano": "profissional"}]})

    plano: Plano = Field(..., description="Novo plano; o limite mensal muda na hora, e o consumo do mês é mantido.")


class TrocaPlanoSaida(BaseModel):
    chave_id: int
    plano_anterior: Plano
    plano: Plano
    movimento: Literal["upgrade", "downgrade"]
    limite_mensal: int
    preco_mensal_usd: float


class SuspensaoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"motivo": "Fatura em atraso"}]})

    motivo: str | None = Field(None, max_length=120, description="Motivo, registrado no histórico do cliente.")


class SituacaoSaida(BaseModel):
    chave_id: int
    situacao: Situacao
    em: str


class RotacaoSaida(NovaChaveSaida):
    chave_anterior_id: int = Field(..., description="Chave substituída, agora revogada.")


class EdicaoClienteEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"empresa": "Imobiliária Exemplo Ltda."}]})

    nome: str | None = Field(None, min_length=2, max_length=80)
    email: str | None = Field(None, max_length=120, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    empresa: str | None = Field(None, max_length=80)


class ChaveDoCliente(BaseModel):
    chave_id: int
    prefixo: str
    plano: Plano
    limite_mensal: int
    uso_mes: int
    preco_mensal_usd: float
    ativa: bool
    situacao: Situacao
    criada_em: str


class EventoComercial(BaseModel):
    tipo: Literal["emissao", "troca_plano", "suspensao", "reativacao", "rotacao", "revogacao", "edicao"]
    detalhe: str | None
    chave_id: int | None
    criado_em: str


class UsoDia(BaseModel):
    dia: str
    total: int


class FaturaDoCliente(BaseModel):
    id: int
    competencia: str = Field(..., description="Mês de referência, AAAA-MM.")
    plano: str
    valor_usd: float
    predicoes: int
    status: Literal["paga", "em_aberto", "vencida", "cancelada"]
    vencimento: str
    paga_em: str | None


class ResumoFaturas(BaseModel):
    recebido_mes_usd: float = 0.0
    em_aberto_usd: float = 0.0
    vencido_usd: float = 0.0
    qtd_vencidas: int = 0


class EmailDoCliente(BaseModel):
    envio_id: int
    assunto: str
    modo: str
    status: str
    criado_em: str


class DetalheClienteSaida(BaseModel):
    cliente_id: int
    nome: str
    email: str
    empresa: str | None
    plano: Plano
    plano_nome: str
    criado_em: str
    limite_mensal: int
    preco_mensal_usd: float
    uso_mes: int
    consumo_pct: float = Field(..., description="Uso do mês sobre o limite do plano, em %.")
    chaves: list[ChaveDoCliente]
    eventos: list[EventoComercial] = Field(..., description="Histórico de auditoria, do mais recente ao mais antigo.")
    uso_por_dia: list[UsoDia]
    emails: list[EmailDoCliente]
    faturas: list[FaturaDoCliente] = []


class ReceitaPlano(BaseModel):
    plano: Plano
    nome: str
    chaves_ativas: int
    receita_mensal_usd: float
    predicoes_mes: int


class ConsumoAlto(BaseModel):
    cliente_id: int
    chave_id: int
    nome: str
    plano: Plano
    uso_mes: int
    limite_mensal: int
    consumo_pct: float


class FaturamentoSaida(BaseModel):
    receita_mensal_usd: float = Field(..., description="Receita recorrente mensal (MRR) das chaves ativas.")
    receita_anual_prevista_usd: float = Field(..., description="MRR × 12.")
    ticket_medio_usd: float
    chaves_ativas: int
    chaves_suspensas: int
    chaves_revogadas: int
    predicoes_mes: int
    por_plano: list[ReceitaPlano]
    perto_do_limite: list[ConsumoAlto] = Field(..., description="Chaves com 80 % ou mais do limite: candidatas a upgrade.")
    faturas: ResumoFaturas = Field(default_factory=ResumoFaturas, description="Contas a receber: recebido no mês, em aberto e vencido.")


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
