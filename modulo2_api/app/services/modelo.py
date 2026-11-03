"""
# Camada de serviço do modelo

Concentra a carga do artefato serializado e a inferência. Não conhece HTTP:
recebe objetos Python e devolve objetos Python, o que facilita testes e reuso.

## Decisão técnica (Fase 3)
O `joblib.load` só acontece em `carregar()`, chamado uma única vez pelo
`lifespan` na subida da aplicação. As rotas usam o pipeline que já está na
memória RAM; nenhuma requisição lê o disco.

## Regras de negócio (Fase 5)
Dados que passam no Pydantic, mas são incoerentes (porão maior que a área útil,
reforma antes da construção ou depois da base, CEP fora da região de treino),
geram `RegraDeNegocioError`, que o main.py traduz em HTTP 400.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd

from ..config import M2_POR_SQFT, REFERENCIA_MERCADO
from ..schemas.imovel import EXEMPLO_IMOVEL, FaixaPreco, ImovelEntrada, PrevisaoSaida
from .excecoes import ModeloIndisponivelError, RegraDeNegocioError

ANO_LIMITE_BASE = 2015


class ServicoModelo:
    def __init__(self, caminho_modelo: Path, caminho_metricas: Path, caminho_regioes: Path):
        self.caminho_modelo = Path(caminho_modelo)
        self.caminho_metricas = Path(caminho_metricas)
        self.caminho_regioes = Path(caminho_regioes)
        self.modelo = None
        self.metricas: dict = {}
        self.regioes: list[dict] = []
        self.carregado_em: datetime | None = None
        self.iniciado_em = time.monotonic()

    @property
    def carregado(self) -> bool:
        return self.modelo is not None

    @property
    def versao(self) -> str:
        return self.metricas.get("versao", "v2")

    @property
    def uptime_s(self) -> float:
        return round(time.monotonic() - self.iniciado_em, 1)

    def carregar(self) -> None:
        """Lê o pipeline e os metadados do disco (uma vez, na inicialização)."""
        self.modelo = joblib.load(self.caminho_modelo)
        self.metricas = json.loads(self.caminho_metricas.read_text(encoding="utf-8"))
        self.regioes = json.loads(self.caminho_regioes.read_text(encoding="utf-8"))
        self._ceps = set(self.metricas["ceps_conhecidos"])
        self.carregado_em = datetime.now(timezone.utc)

    def aquecer(self) -> None:
        """Faz uma predição de exemplo na subida, para a 1ª requisição real não pagar a inicialização."""
        self.prever([ImovelEntrada(**EXEMPLO_IMOVEL)])

    def descarregar(self) -> None:
        self.modelo = None

    # ## Regras de negócio
    def _validar_regras(self, imovel: ImovelEntrada, prefixo: str = "") -> None:
        problema = None
        if imovel.area_porao_m2 >= imovel.area_util_m2:
            problema = "a área do porão deve ser menor que a área útil."
        elif imovel.ano_reforma is not None and imovel.ano_reforma < imovel.ano_construcao:
            problema = "o ano da reforma é anterior ao ano de construção."
        elif imovel.ano_reforma is not None and imovel.ano_reforma > ANO_LIMITE_BASE:
            problema = f"o ano da reforma passa de {ANO_LIMITE_BASE}, último ano da base de treino."
        elif imovel.cep not in self._ceps:
            problema = f"o CEP {imovel.cep} não pertence à região de King County usada no treino."
        if problema:
            mensagem = f"{prefixo}{problema}"
            raise RegraDeNegocioError(mensagem[0].upper() + mensagem[1:])

    # ## Conversão do contrato da API para as colunas brutas do pipeline
    def _para_colunas_do_modelo(self, imovel: ImovelEntrada) -> dict:
        area_util = imovel.area_util_m2 / M2_POR_SQFT
        porao = imovel.area_porao_m2 / M2_POR_SQFT
        terreno = imovel.area_terreno_m2 / M2_POR_SQFT
        return {
            "date": self.metricas["data_referencia"],
            "bedrooms": imovel.quartos,
            "bathrooms": imovel.banheiros,
            "sqft_living": area_util,
            "sqft_lot": terreno,
            "floors": imovel.andares,
            "waterfront": int(imovel.frente_agua),
            "view": imovel.vista,
            "condition": imovel.condicao,
            "grade": imovel.padrao_construtivo,
            "sqft_above": area_util - porao,
            "sqft_basement": porao,
            "yr_built": imovel.ano_construcao,
            "yr_renovated": imovel.ano_reforma or 0,
            "zipcode": int(imovel.cep),
            "lat": imovel.latitude,
            "long": imovel.longitude,
            "sqft_living15": (imovel.area_util_vizinhos_m2 or imovel.area_util_m2) / M2_POR_SQFT,
            "sqft_lot15": (imovel.area_terreno_vizinhos_m2 or imovel.area_terreno_m2) / M2_POR_SQFT,
        }

    # ## Inferência (usa o pipeline que já está na RAM)
    def prever(self, imoveis: list[ImovelEntrada]) -> list[PrevisaoSaida]:
        if not self.carregado:
            raise ModeloIndisponivelError("O modelo não está carregado na memória.")
        for posicao, imovel in enumerate(imoveis, start=1):
            self._validar_regras(imovel, f"Imóvel {posicao}: " if len(imoveis) > 1 else "")

        inicio = time.perf_counter()
        entrada = pd.DataFrame([self._para_colunas_do_modelo(imovel) for imovel in imoveis])
        precos = self.modelo.predict(entrada)
        latencia_ms = round((time.perf_counter() - inicio) * 1000, 2)

        faixa = self.metricas["faixa_erro"]
        return [
            PrevisaoSaida(
                preco_estimado_usd=round(float(preco), 2),
                faixa_provavel_usd=FaixaPreco(
                    minimo=round(float(preco) * faixa["p10"], 2),
                    maximo=round(float(preco) * faixa["p90"], 2),
                ),
                preco_por_m2_usd=round(float(preco) / imovel.area_util_m2, 2),
                moeda="USD",
                referencia_mercado=REFERENCIA_MERCADO,
                versao_modelo=self.versao,
                latencia_ms=latencia_ms,
            )
            for preco, imovel in zip(precos, imoveis)
        ]
