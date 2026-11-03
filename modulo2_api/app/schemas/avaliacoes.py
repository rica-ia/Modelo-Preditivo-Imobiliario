"""Contratos dos laudos de avaliação e dos relatórios de mercado."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .imovel import EXEMPLO_IMOVEL, ImovelEntrada

Origem = Literal["portal", "api", "amostra_base"]
Ordenacao = Literal["recentes", "antigas", "preco_desc", "preco_asc"]
Dimensao = Literal["quartos", "cidade", "cep", "faixa_preco", "padrao", "ano_venda"]
Formato = Literal["csv", "json"]


class AvaliacaoEntrada(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"examples": [{"titulo": "Casa em Redmond · cliente Silva", "responsavel": "Ricardo",
                                          "imovel": EXEMPLO_IMOVEL}]},
    )

    titulo: str = Field(..., min_length=3, max_length=120, description="Título do laudo.")
    responsavel: str | None = Field(None, max_length=80, description="Responsável pela avaliação.")
    imovel: ImovelEntrada = Field(..., description="Imóvel avaliado; o preço é recalculado no servidor.")


class AvaliacaoSaida(BaseModel):
    id: int
    criado_em: str
    titulo: str
    responsavel: str | None
    cliente_chave_id: int | None
    origem: Origem
    imovel: dict = Field(..., description="JSON completo enviado ao modelo.")
    quartos: int
    banheiros: float
    area_util_m2: float
    padrao: int
    cep: str
    cidade: str
    latitude: float
    longitude: float
    preco_estimado_usd: float = Field(..., ge=0)
    faixa_min: float
    faixa_max: float
    preco_m2_usd: float
    faixa_preco: str
    preco_real_usd: float | None = Field(None, description="Preço real de venda (só na amostra da base).")
    versao_modelo: str
    latencia_ms: float


class ListaAvaliacoesSaida(BaseModel):
    total: int = Field(..., ge=0)
    pagina: int = Field(..., ge=1)
    limite: int = Field(..., ge=1, le=100)
    itens: list[AvaliacaoSaida]


class LinhaMercado(BaseModel):
    grupo: str
    vendas: int = Field(..., ge=0)
    preco_mediano_usd: float
    preco_medio_usd: float
    p25_usd: float
    p75_usd: float
    preco_m2_mediano_usd: float


class MercadoSaida(BaseModel):
    dimensao: Dimensao
    linhas: list[LinhaMercado]
