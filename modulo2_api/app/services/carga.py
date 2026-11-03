"""
# Carga inicial do banco

1. `vendas_historicas`: as vendas reais do CSV, limpas pelo Módulo 1, com cidade
   (pelo CEP), preço por m² e faixa de preço (quartis da própria base).
2. `avaliacoes`: amostra de cerca de 300 imóveis reais do conjunto de TESTE do
   modelo (mesma divisão por id e random_state do treino), estratificada por
   quartos e faixa de preço, avaliados pelo modelo com o preço real ao lado.

Cada etapa só roda com a tabela vazia, então reiniciar a API não duplica dados.
"""

import json
import logging

import numpy as np
import pandas as pd
from pydantic import ValidationError

from ..config import ARQUIVO_CEPS, M2_POR_SQFT, RAIZ_REPOSITORIO
from ..schemas.imovel import ImovelEntrada
from .banco import Banco, agora
from .excecoes import RegraDeNegocioError
from .modelo import ServicoModelo

log = logging.getLogger("avaliador")

DADOS_BRUTOS = RAIZ_REPOSITORIO / "data" / "raw" / "kc_house_data.csv"
TAMANHO_AMOSTRA = 300


def mapa_de_cidades() -> dict:
    return json.loads(ARQUIVO_CEPS.read_text(encoding="utf-8"))["ceps"]


def _mil(valor: float) -> str:
    return f"US$ {valor / 1000:,.0f} mil".replace(",", ".")


def rotulos_de_faixa(limites: list[float]) -> list[str]:
    q1, q2, q3 = limites
    return [f"até {_mil(q1)}", f"{_mil(q1)} a {_mil(q2)[4:]}", f"{_mil(q2)} a {_mil(q3)[4:]}", f"acima de {_mil(q3)}"]


def classificar(preco: float, limites: list[float]) -> str:
    return rotulos_de_faixa(limites)[int(np.searchsorted(limites, preco, side="left"))]


def _base_limpa() -> pd.DataFrame:
    from src.features import limpar_dados  # Módulo 1

    limpo, _ = limpar_dados(pd.read_csv(DADOS_BRUTOS))
    return limpo


def carregar_vendas(banco: Banco, base: pd.DataFrame) -> int:
    if banco.um("SELECT COUNT(*) AS n FROM vendas_historicas")["n"]:
        return 0
    cidades = mapa_de_cidades()
    limites = np.quantile(base["price"], [0.25, 0.50, 0.75]).tolist()
    area = base["sqft_living"] * M2_POR_SQFT
    tabela = pd.DataFrame(
        {
            "id_imovel": base["id"].astype(int),
            "data_venda": base["date"].dt.strftime("%Y-%m-%d"),
            "preco_usd": base["price"].astype(float),
            "quartos": base["bedrooms"].astype(int),
            "banheiros": base["bathrooms"].astype(float),
            "area_util_m2": area.round(1),
            "area_terreno_m2": (base["sqft_lot"] * M2_POR_SQFT).round(1),
            "padrao": base["grade"].astype(int),
            "condicao": base["condition"].astype(int),
            "vista": base["view"].astype(int),
            "frente_agua": base["waterfront"].astype(int),
            "ano_construcao": base["yr_built"].astype(int),
            "ano_reforma": base["yr_renovated"].where(base["yr_renovated"] > 0).astype("Int64"),
            "cep": base["zipcode"].astype(str),
            "cidade": base["zipcode"].astype(str).map(cidades).fillna("King County"),
            "latitude": base["lat"].astype(float),
            "longitude": base["long"].astype(float),
            "preco_m2_usd": (base["price"] / area).round(2),
            "faixa_preco": [classificar(p, limites) for p in base["price"]],
        }
    )
    registros = [
        tuple(None if pd.isna(v) else (int(v) if isinstance(v, np.integer) else v) for v in linha)
        for linha in tabela.itertuples(index=False, name=None)
    ]
    colunas = ", ".join(tabela.columns)
    marcadores = ", ".join("?" * len(tabela.columns))
    with banco.conexao() as con:
        con.executemany(f"INSERT INTO vendas_historicas ({colunas}) VALUES ({marcadores})", registros)
    return len(registros)


def limites_de_faixa(banco: Banco) -> list[float]:
    precos = [linha["preco_usd"] for linha in banco.consultar("SELECT preco_usd FROM vendas_historicas")]
    return np.quantile(precos, [0.25, 0.50, 0.75]).tolist() if precos else [322_000.0, 450_000.0, 645_000.0]


def _imovel_da_venda(linha) -> dict:
    return {
        "quartos": int(linha.bedrooms),
        "banheiros": float(linha.bathrooms),
        "area_util_m2": round(float(linha.sqft_living) * M2_POR_SQFT, 1),
        "area_terreno_m2": round(float(linha.sqft_lot) * M2_POR_SQFT, 1),
        "andares": float(linha.floors),
        "frente_agua": bool(linha.waterfront),
        "vista": int(linha.view),
        "condicao": int(linha.condition),
        "padrao_construtivo": int(linha.grade),
        "area_porao_m2": round(float(linha.sqft_basement) * M2_POR_SQFT, 1),
        "ano_construcao": int(linha.yr_built),
        "ano_reforma": int(linha.yr_renovated) if linha.yr_renovated > 0 else None,
        "cep": str(linha.zipcode),
        "latitude": float(linha.lat),
        "longitude": float(linha.long),
        "area_util_vizinhos_m2": round(float(linha.sqft_living15) * M2_POR_SQFT, 1),
        "area_terreno_vizinhos_m2": round(float(linha.sqft_lot15) * M2_POR_SQFT, 1),
    }


def semear_avaliacoes(banco: Banco, base: pd.DataFrame, servico: ServicoModelo, limites: list[float]) -> int:
    if not servico.carregado or banco.um("SELECT COUNT(*) AS n FROM avaliacoes WHERE origem = 'amostra_base'")["n"]:
        return 0
    from ...treinamento.treinar_modelo import dividir  # mesma divisão do treino

    _, _, grupos_teste = dividir(base)["teste"]
    teste = base.loc[grupos_teste.index]

    # Estratos: quartos (até 2, 3, 4, 5 ou mais) x faixa de preço (quartis).
    estrato = pd.cut(teste["bedrooms"], [-1, 2, 3, 4, 99]).astype(str) + "|" + pd.cut(
        teste["price"], [-np.inf, *limites, np.inf]
    ).astype(str)
    fracao = TAMANHO_AMOSTRA / len(teste)
    amostra = teste.groupby(estrato, group_keys=False).sample(frac=fracao, random_state=42)

    validos, linhas = [], []
    for linha in amostra.itertuples():
        try:
            imovel = ImovelEntrada(**_imovel_da_venda(linha))
            servico._validar_regras(imovel)
        except (ValidationError, RegraDeNegocioError):
            continue
        validos.append(imovel)
        linhas.append(linha)

    previsoes = servico.prever(validos)
    cidades = mapa_de_cidades()
    registros = []
    for imovel, linha, previsao in zip(validos, linhas, previsoes):
        cidade = cidades.get(imovel.cep, "King County")
        registros.append(
            (
                agora(), f"Amostra da base · venda {int(linha.id)} · {cidade}", "Base de teste do modelo", None,
                "amostra_base", imovel.model_dump_json(), imovel.quartos, imovel.banheiros, imovel.area_util_m2,
                imovel.padrao_construtivo, imovel.cep, cidade, imovel.latitude, imovel.longitude,
                previsao.preco_estimado_usd, previsao.faixa_provavel_usd.minimo, previsao.faixa_provavel_usd.maximo,
                previsao.preco_por_m2_usd, classificar(previsao.preco_estimado_usd, limites), float(linha.price),
                previsao.versao_modelo, previsao.latencia_ms,
            )
        )
    with banco.conexao() as con:
        con.executemany(
            "INSERT INTO avaliacoes (criado_em, titulo, responsavel, cliente_chave_id, origem, entrada_json, quartos,"
            " banheiros, area_util_m2, padrao, cep, cidade, latitude, longitude, preco_estimado_usd, faixa_min,"
            " faixa_max, preco_m2_usd, faixa_preco, preco_real_usd, versao_modelo, latencia_ms)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            registros,
        )
    return len(registros)


def carga_inicial(banco: Banco, servico: ServicoModelo) -> dict:
    """Popula as tabelas de referência se estiverem vazias; devolve o que foi inserido."""
    vazias = not banco.um("SELECT COUNT(*) AS n FROM vendas_historicas")["n"] or (
        servico.carregado and not banco.um("SELECT COUNT(*) AS n FROM avaliacoes WHERE origem = 'amostra_base'")["n"]
    )
    if not vazias:
        return {"vendas": 0, "avaliacoes": 0}
    base = _base_limpa()
    vendas = carregar_vendas(banco, base)
    avaliacoes = semear_avaliacoes(banco, base, servico, limites_de_faixa(banco))
    return {"vendas": vendas, "avaliacoes": avaliacoes}
