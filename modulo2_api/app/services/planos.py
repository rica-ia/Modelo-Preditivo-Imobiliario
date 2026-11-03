"""
# Catálogo dos planos comerciais

Fonte única de nome, limite mensal e preço de cada plano, usada pela emissão de chaves,
pelo e-mail ao cliente, pela rota pública `GET /v1/comercial/planos` e pelo portal.
Preços em dólares americanos, a mesma moeda das avaliações; o custo por predição cai
conforme o volume contratado.
"""

PLANOS = {
    "basico": {"nome": "Básico", "limite_mensal": 100, "preco_mensal_usd": 29.0},
    "profissional": {"nome": "Profissional", "limite_mensal": 1_000, "preco_mensal_usd": 199.0},
    "empresarial": {"nome": "Empresarial", "limite_mensal": 10_000, "preco_mensal_usd": 1_490.0},
}

LIMITES = {codigo: p["limite_mensal"] for codigo, p in PLANOS.items()}
PRECOS_USD = {codigo: p["preco_mensal_usd"] for codigo, p in PLANOS.items()}
NOMES_PLANOS = {codigo: p["nome"] for codigo, p in PLANOS.items()}


def catalogo() -> list[dict]:
    return [
        {"plano": codigo, **p, "preco_por_predicao_usd": round(p["preco_mensal_usd"] / p["limite_mensal"], 4)}
        for codigo, p in PLANOS.items()
    ]


def formatar_usd(valor: float) -> str:
    """US$ no padrão brasileiro de separadores (US$ 1.490,00), como no restante do portal."""
    return "US$ " + f"{valor:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
