"""Contratos das rotas de monitoramento, do modelo e das respostas de erro."""

from pydantic import BaseModel, Field


class SaudeSaida(BaseModel):
    status: str = Field(..., description="Valor ok quando o serviço responde.", examples=["ok"])
    modelo_carregado: bool = Field(..., description="Indica se o pipeline está na memória RAM.")
    versao_modelo: str = Field(..., examples=["v2"])
    carregado_em: str | None = Field(None, description="Momento (UTC) em que o modelo foi carregado.")
    uptime_s: float = Field(..., ge=0, description="Segundos desde a subida da API.")


class Metricas(BaseModel):
    MAE: float
    MSE: float
    RMSE: float
    R2: float
    MAPE: float


class MetricasPorConjunto(BaseModel):
    validacao: Metricas
    teste: Metricas


class Divisao(BaseModel):
    treino: int
    validacao: int
    teste: int
    criterio: str


class Baseline(BaseModel):
    modelo: str
    teste: Metricas


class Importancia(BaseModel):
    variavel: str
    coluna: str
    importancia: float


class FaixaErro(BaseModel):
    p10: float
    p90: float


class ModeloInfoSaida(BaseModel):
    versao: str
    algoritmo: str
    treinado_em: str
    divisao: Divisao
    metricas: MetricasPorConjunto
    baseline: Baseline
    importancia: list[Importancia]
    faixa_erro: FaixaErro


class RegiaoSaida(BaseModel):
    cep: str
    latitude: float
    longitude: float
    vendas: int
    preco_mediano_usd: float
    preco_m2_mediano_usd: float


class DetalheErro(BaseModel):
    campo: str
    mensagem: str


class ErroSaida(BaseModel):
    erro: str = Field(..., examples=["dados_invalidos"])
    mensagem: str
    detalhes: list[DetalheErro] | None = None


class ArtefatoSaida(BaseModel):
    """Artefato registrado na tabela `modelos` (o BLOB nunca sai em JSON)."""

    id: int
    versao: str = Field(..., examples=["v2"])
    nome_arquivo: str = Field(..., examples=["modulo2_api/models/modelo_imobiliario_v2.joblib"])
    sha256: str = Field(..., min_length=64, max_length=64)
    tamanho_bytes: int = Field(..., ge=0)
    formato: str = Field(..., examples=["joblib"])
    estimador: str | None = None
    metricas: dict = Field(default_factory=dict, description="Métricas de validação e teste no registro.")
    treinado_em: str | None = None
    registrado_em: str
    ativo: bool = Field(..., description="Artefato que a API está servindo.")


class VerificacaoArtefatoSaida(BaseModel):
    id: int
    integro: bool = Field(..., description="Hashes iguais e a mesma previsão do modelo em memória.")
    sha256_registrado: str
    sha256_blob: str
    sha256_disco: str | None
    sha256_carregado: str | None = Field(None, description="Hash do arquivo lido na subida da API.")
    tamanho_bytes: int
    previsao_restaurada: float | None
    previsao_em_memoria: float | None
    imovel_exemplo: dict
    erro: str | None = None
