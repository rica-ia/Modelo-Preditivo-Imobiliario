"""
# Relatórios de mercado sobre as vendas reais

Agrupa `vendas_historicas` por uma dimensão (quartos, cidade, CEP, faixa de
preço, padrão ou ano da venda) e calcula vendas, mediana, média, quartis e
mediana do preço por m².
"""

import json
from collections import defaultdict
from datetime import datetime

import numpy as np

from .avaliacoes import exportar_csv
from .banco import Banco

DIMENSOES = {
    "quartos": "quartos",
    "cidade": "cidade",
    "cep": "cep",
    "faixa_preco": "faixa_preco",
    "padrao": "padrao",
    "ano_venda": "substr(data_venda, 1, 4)",
}
COLUNAS = ["grupo", "vendas", "preco_mediano_usd", "preco_medio_usd", "p25_usd", "p75_usd", "preco_m2_mediano_usd"]


def relatorio(banco: Banco, dimensao: str, filtros: dict, ordem_faixas: list[str]) -> dict:
    condicoes, valores = [], []
    for campo in ("cidade", "quartos", "faixa_preco"):
        if filtros.get(campo) is not None:
            condicoes.append(f"{campo} = ?")
            valores.append(filtros[campo])
    onde = (" WHERE " + " AND ".join(condicoes)) if condicoes else ""
    vendas = banco.consultar(
        f"SELECT {DIMENSOES[dimensao]} AS grupo, preco_usd, preco_m2_usd FROM vendas_historicas{onde}", tuple(valores)
    )
    grupos = defaultdict(lambda: ([], []))
    for v in vendas:
        grupos[str(v["grupo"])][0].append(v["preco_usd"])
        grupos[str(v["grupo"])][1].append(v["preco_m2_usd"])

    linhas = []
    for grupo, (precos, precos_m2) in grupos.items():
        p = np.asarray(precos)
        linhas.append(
            {
                "grupo": grupo,
                "vendas": int(p.size),
                "preco_mediano_usd": round(float(np.median(p)), 2),
                "preco_medio_usd": round(float(p.mean()), 2),
                "p25_usd": round(float(np.quantile(p, 0.25)), 2),
                "p75_usd": round(float(np.quantile(p, 0.75)), 2),
                "preco_m2_mediano_usd": round(float(np.median(precos_m2)), 2),
            }
        )

    if dimensao in ("quartos", "padrao", "ano_venda", "cep"):
        linhas.sort(key=lambda linha: int(linha["grupo"]))
    elif dimensao == "faixa_preco":
        linhas.sort(key=lambda linha: ordem_faixas.index(linha["grupo"]) if linha["grupo"] in ordem_faixas else 99)
    else:
        linhas.sort(key=lambda linha: -linha["vendas"])
    return {"dimensao": dimensao, "linhas": linhas}


def exportar(dados: dict, formato: str) -> tuple[bytes, str, str]:
    carimbo = datetime.now().strftime("%Y%m%d-%H%M")
    nome = f"mercado_{dados['dimensao']}_{carimbo}"
    if formato == "json":
        return json.dumps(dados, ensure_ascii=False, indent=2).encode("utf-8"), "application/json; charset=utf-8", f"{nome}.json"
    return exportar_csv(dados["linhas"], COLUNAS), "text/csv; charset=utf-8", f"{nome}.csv"
