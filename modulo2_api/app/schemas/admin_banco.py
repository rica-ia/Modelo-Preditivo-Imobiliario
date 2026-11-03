"""Contratos da administração do banco SQLite (seções, listagem, registro, faturas, saúde)."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Secao = Literal["clientes", "chaves", "faturas", "envios_email", "eventos_comerciais", "avaliacoes", "predicoes",
                "vendas_historicas"]
StatusFatura = Literal["paga", "em_aberto", "vencida", "cancelada"]
Direcao = Literal["asc", "desc"]
FormatoExportacao = Literal["csv", "json"]


class SecaoSaida(BaseModel):
    secao: str = Field(..., description="Identificador da seção, usado nas rotas.", examples=["clientes"])
    titulo: str = Field(..., description="Nome exibido no console.", examples=["Clientes"])
    descricao: str = Field(..., description="O que a seção guarda.")
    tabela: str = Field(..., description="Tabela do SQLite por trás da seção.", examples=["clientes"])
    total: int = Field(..., ge=0, description="Registros na tabela.")
    colunas: list[str] = Field(..., description="Colunas da listagem, na ordem de exibição.")
    colunas_busca: list[str] = Field(..., description="Colunas consultadas pelo parâmetro `busca`.")
    rotulos: dict[str, str] = Field(default_factory=dict, description="Descrição de cada coluna da listagem.")
    pode_excluir: bool = Field(..., description="Se o console pode excluir registros desta seção.")
    pode_editar: bool = Field(..., description="Se o console pode alterar registros (baixa de fatura).")


class ListagemSaida(BaseModel):
    secao: str
    titulo: str
    total: int = Field(..., ge=0, description="Registros que atendem à busca.")
    pagina: int = Field(..., ge=1)
    por_pagina: int = Field(..., ge=1, le=100)
    paginas: int = Field(..., ge=1, description="Total de páginas (mínimo 1).")
    colunas: list[str] = Field(..., description="Colunas presentes em cada linha.")
    linhas: list[dict[str, Any]] = Field(..., description="Registros da página.")


class RegistroSaida(BaseModel):
    secao: str
    registro: dict[str, Any] = Field(..., description="Todas as colunas do registro, mais as legíveis via JOIN.")


class BaixaFaturaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"status": "paga"}]})

    status: StatusFatura = Field(..., description="paga (preenche paga_em), em_aberto, vencida ou cancelada "
                                                  "(as três limpam paga_em).")


class ExclusaoSaida(BaseModel):
    secao: str
    id: int
    excluido: bool = Field(..., description="Verdadeiro quando o registro foi apagado.")


class TabelaLinhas(BaseModel):
    nome: str
    linhas: int = Field(..., ge=0)


class SinteticosSaida(BaseModel):
    clientes: int = Field(..., ge=0, description="Clientes de demonstração (sintetico = 1).")


class SaudeBancoSaida(BaseModel):
    arquivo: str = Field(..., description="Caminho do arquivo SQLite.")
    tamanho_bytes: int = Field(..., ge=0)
    integridade: str = Field(..., description="Resultado do PRAGMA integrity_check (ok quando íntegro).",
                             examples=["ok"])
    tabelas: list[TabelaLinhas]
    sinteticos: SinteticosSaida
