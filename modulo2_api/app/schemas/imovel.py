"""
# Contratos de dados do imóvel (Fase 4)

`ImovelEntrada` define exatamente o JSON aceito por `/v1/predict`. Tipos e
faixas (ge, le, pattern, multiple_of) seguem os limites observados na base de
treino: o Pydantic recusa com HTTP 422, antes do modelo, texto em campo
numérico, valor fora da faixa, campo ausente ou campo desconhecido.
"""

from pydantic import BaseModel, ConfigDict, Field

EXEMPLO_IMOVEL = {
    "quartos": 3,
    "banheiros": 2.25,
    "area_util_m2": 190.0,
    "area_terreno_m2": 670.0,
    "andares": 2.0,
    "frente_agua": False,
    "vista": 0,
    "condicao": 3,
    "padrao_construtivo": 8,
    "area_porao_m2": 40.0,
    "ano_construcao": 1995,
    "ano_reforma": None,
    "cep": "98052",
    "latitude": 47.6768,
    "longitude": -122.1185,
}


class ImovelEntrada(BaseModel):
    """Características do imóvel a ser avaliado (áreas em m²)."""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [EXEMPLO_IMOVEL]})

    quartos: int = Field(..., ge=0, le=15, description="Número de quartos.", examples=[3])
    banheiros: float = Field(
        ..., ge=0, le=10, multiple_of=0.25,
        description="Banheiros (0,25 = lavabo; 0,5 = meio banheiro).", examples=[2.25],
    )
    area_util_m2: float = Field(..., ge=25, le=1300, description="Área útil construída, em m².", examples=[190.0])
    area_terreno_m2: float = Field(..., ge=50, le=160000, description="Área do terreno, em m².", examples=[670.0])
    andares: float = Field(..., ge=1, le=3.5, multiple_of=0.5, description="Número de pavimentos.", examples=[2.0])
    frente_agua: bool = Field(..., description="Imóvel com frente para a água.", examples=[False])
    vista: int = Field(..., ge=0, le=4, description="Qualidade da vista, de 0 (nenhuma) a 4 (excelente).", examples=[0])
    condicao: int = Field(..., ge=1, le=5, description="Estado de conservação, de 1 a 5.", examples=[3])
    padrao_construtivo: int = Field(
        ..., ge=1, le=13, description="Padrão construtivo do condado (grade), de 1 a 13.", examples=[8],
    )
    area_porao_m2: float = Field(0.0, ge=0, le=500, description="Área do porão, em m² (0 se não houver).", examples=[40.0])
    ano_construcao: int = Field(..., ge=1900, le=2015, description="Ano de construção.", examples=[1995])
    ano_reforma: int | None = Field(
        None, ge=1900, le=2100, description="Ano da última reforma (vazio se nunca reformado).", examples=[None],
    )
    cep: str = Field(..., pattern=r"^98\d{3}$", description="CEP (zipcode) de King County, 5 dígitos.", examples=["98052"])
    latitude: float = Field(..., ge=47.15, le=47.78, description="Latitude do imóvel.", examples=[47.6768])
    longitude: float = Field(..., ge=-122.52, le=-121.31, description="Longitude do imóvel.", examples=[-122.1185])
    area_util_vizinhos_m2: float | None = Field(
        None, ge=25, le=1300, description="Área útil média dos 15 vizinhos (padrão: a do próprio imóvel).",
    )
    area_terreno_vizinhos_m2: float | None = Field(
        None, ge=50, le=160000, description="Terreno médio dos 15 vizinhos (padrão: o do próprio imóvel).",
    )


class FaixaPreco(BaseModel):
    minimo: float = Field(..., description="Limite inferior provável (quantil 10 % do erro), em USD.")
    maximo: float = Field(..., description="Limite superior provável (quantil 90 % do erro), em USD.")


class PrevisaoSaida(BaseModel):
    """Resposta de uma avaliação."""

    preco_estimado_usd: float = Field(..., ge=0, description="Preço estimado, em dólares.")
    faixa_provavel_usd: FaixaPreco
    preco_por_m2_usd: float = Field(..., ge=0, description="Preço estimado dividido pela área útil.")
    moeda: str = Field("USD", description="Moeda da estimativa.")
    referencia_mercado: str = Field(..., description="Mercado e período que o modelo representa.")
    versao_modelo: str = Field(..., description="Versão do artefato usado.")
    latencia_ms: float = Field(..., ge=0, description="Tempo de inferência, em milissegundos.")


class LoteEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")

    imoveis: list[ImovelEntrada] = Field(
        ..., min_length=1, max_length=20, description="De 1 a 20 imóveis (usado no simulador de cenários).",
    )


class LoteSaida(BaseModel):
    previsoes: list[PrevisaoSaida]
