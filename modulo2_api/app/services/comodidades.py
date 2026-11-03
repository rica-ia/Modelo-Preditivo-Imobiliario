"""
# Comodidades perto do imóvel (escolas, saúde, mercados, transporte, parques, alimentação e bancos)

Os pontos de interesse vêm da Overpass API, a consulta pública e gratuita do OpenStreetMap,
sem chave e sem custo. Uma única consulta por coordenada traz as sete categorias num raio de
1,5 km; a distância é calculada pela fórmula de haversine (linha reta) e os tempos são estimados.

- Tempo a pé: distância em linha reta × 1,3 (fator de sinuosidade das ruas) ÷ 80 m/min.
- Tempo de carro: a mesma distância de rota ÷ 500 m/min (30 km/h, média urbana com semáforos).
- Índice de conveniência (0 a 100): média ponderada da proximidade do item mais próximo de cada
  categoria (100 até 400 m, cai em linha reta até 0 na borda do raio); pesos em `CATEGORIAS`.
- Cada coordenada (arredondada a 4 casas, cerca de 11 m) é consultada uma única vez por execução.
- Servidor principal `overpass-api.de`; se ele recusar por carga (429/502/504), tenta o espelho público,
  com 8 s por tentativa e 12 s no total. `AVALIADOR_OVERPASS_URL` aceita outra lista, separada por vírgula.
- Falha de rede não derruba nada: a resposta volta com `disponivel = false`, e por 60 s o serviço
  não tenta de novo (o laudo não fica esperando a cada abertura).
- `AVALIADOR_COMODIDADES=0` desliga a consulta (usado nos testes, que rodam sem rede).
"""

import json
import math
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from ..config import obter
from .endereco import AGENTE

URLS_OVERPASS = ("https://overpass-api.de/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter")
RAIO_M = 1500
TIMEOUT_S = 8
PRAZO_TOTAL_S = 12
ESPERA_APOS_FALHA_S = 60
FATOR_ROTA = 1.3
A_PE_M_MIN = 80.0
CARRO_M_MIN = 500.0
PERTO_M = 400
MAIS_PROXIMOS = 3
FONTE = "© OpenStreetMap contributors (Overpass API, ODbL)"
METODO = (
    "Distância em linha reta (haversine) a partir das coordenadas do imóvel. Tempos estimados sobre a distância"
    " × 1,3 (sinuosidade das ruas): a pé a 80 m/min e de carro a 30 km/h, sem trânsito nem estacionamento."
)

# ## Categorias: chave, nome, peso no índice, filtros da Overpass e rótulos dos tipos
CATEGORIAS = [
    {"chave": "escolas", "nome": "Escolas e educação", "peso": 15,
     "filtros": ['["amenity"~"^(school|kindergarten|college|university)$"]']},
    {"chave": "saude", "nome": "Saúde (hospitais, clínicas e farmácias)", "peso": 15,
     "filtros": ['["amenity"~"^(hospital|clinic|doctors|pharmacy)$"]', '["shop"="chemist"]']},
    {"chave": "mercados", "nome": "Supermercados e mercados", "peso": 20,
     "filtros": ['["shop"~"^(supermarket|convenience|greengrocer)$"]', '["amenity"="marketplace"]']},
    {"chave": "transporte", "nome": "Transporte público", "peso": 20,
     "filtros": ['["highway"="bus_stop"]', '["railway"~"^(station|halt|tram_stop)$"]']},
    {"chave": "parques", "nome": "Parques e lazer", "peso": 10,
     "filtros": ['["leisure"~"^(park|playground|nature_reserve)$"]']},
    {"chave": "alimentacao", "nome": "Restaurantes e cafés", "peso": 10,
     "filtros": ['["amenity"~"^(restaurant|cafe|fast_food)$"]']},
    {"chave": "bancos", "nome": "Bancos", "peso": 10,
     "filtros": ['["amenity"="bank"]']},
]

TIPOS = {
    ("amenity", "school"): ("escolas", "Escola"),
    ("amenity", "kindergarten"): ("escolas", "Educação infantil"),
    ("amenity", "college"): ("escolas", "Faculdade"),
    ("amenity", "university"): ("escolas", "Universidade"),
    ("amenity", "hospital"): ("saude", "Hospital"),
    ("amenity", "clinic"): ("saude", "Clínica"),
    ("amenity", "doctors"): ("saude", "Consultório médico"),
    ("amenity", "pharmacy"): ("saude", "Farmácia"),
    ("shop", "chemist"): ("saude", "Farmácia"),
    ("shop", "supermarket"): ("mercados", "Supermercado"),
    ("shop", "convenience"): ("mercados", "Loja de conveniência"),
    ("shop", "greengrocer"): ("mercados", "Hortifrúti"),
    ("amenity", "marketplace"): ("mercados", "Feira"),
    ("highway", "bus_stop"): ("transporte", "Ponto de ônibus"),
    ("railway", "station"): ("transporte", "Estação"),
    ("railway", "halt"): ("transporte", "Parada de trem"),
    ("railway", "tram_stop"): ("transporte", "Parada de bonde"),
    ("leisure", "park"): ("parques", "Parque"),
    ("leisure", "playground"): ("parques", "Playground"),
    ("leisure", "nature_reserve"): ("parques", "Reserva natural"),
    ("amenity", "restaurant"): ("alimentacao", "Restaurante"),
    ("amenity", "cafe"): ("alimentacao", "Café"),
    ("amenity", "fast_food"): ("alimentacao", "Lanchonete"),
    ("amenity", "bank"): ("bancos", "Banco"),
}


def consulta_overpass(lat: float, lng: float, raio_m: int = RAIO_M) -> str:
    """Texto da consulta Overpass QL: todas as categorias num só pedido, com o centro das áreas."""
    partes = "".join(
        f"nwr{filtro}(around:{raio_m},{lat},{lng});" for categoria in CATEGORIAS for filtro in categoria["filtros"]
    )
    return f"[out:json][timeout:{TIMEOUT_S}];({partes});out tags center;"


def _consultar_overpass(lat: float, lng: float) -> dict:
    """Tenta o servidor principal e, se ele recusar por excesso de carga, o espelho, dentro de `PRAZO_TOTAL_S`."""
    corpo = urllib.parse.urlencode({"data": consulta_overpass(lat, lng)}).encode("utf-8")
    enderecos = [u.strip() for u in obter("AVALIADOR_OVERPASS_URL", ",".join(URLS_OVERPASS)).split(",") if u.strip()]
    limite = time.monotonic() + PRAZO_TOTAL_S
    erro: Exception = TimeoutError("Overpass sem resposta")
    for url in enderecos:
        restante = limite - time.monotonic()
        if restante < 1:
            break
        pedido = urllib.request.Request(url, data=corpo, headers={"User-Agent": AGENTE})
        try:
            with urllib.request.urlopen(pedido, timeout=min(TIMEOUT_S, restante)) as resposta:
                return json.load(resposta)
        except urllib.error.HTTPError as falha:  # 429/502/504: servidor ocupado, vale tentar o próximo
            erro = falha
    raise erro


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Distância em metros entre dois pontos sobre a esfera terrestre (raio médio de 6.371 km)."""
    f1, f2 = math.radians(lat1), math.radians(lat2)
    df, dl = f2 - f1, math.radians(lng2 - lng1)
    a = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


def tempos(distancia_m: float) -> tuple[int, int]:
    """Minutos estimados a pé e de carro (no mínimo 1), sobre a distância de rota."""
    rota = distancia_m * FATOR_ROTA
    return max(1, math.ceil(rota / A_PE_M_MIN)), max(1, math.ceil(rota / CARRO_M_MIN))


def _classificar(tags: dict) -> tuple[str, str] | None:
    for (chave, valor), destino in TIPOS.items():
        if tags.get(chave) == valor:
            return destino
    return None


def indice_conveniencia(categorias: list[dict]) -> dict:
    """Nota de 0 a 100 pela proximidade do item mais próximo de cada categoria, com os pesos de `CATEGORIAS`."""
    pesos = {c["chave"]: c["peso"] for c in CATEGORIAS}
    soma = 0.0
    for categoria in categorias:
        if not categoria["mais_proximos"]:
            continue
        d = categoria["mais_proximos"][0]["distancia_m"]
        proximidade = 1.0 if d <= PERTO_M else max(0.0, (RAIO_M - d) / (RAIO_M - PERTO_M))
        soma += pesos.get(categoria["chave"], 0) * proximidade
    valor = round(100 * soma / sum(pesos.values()))
    classificacao = "Excelente" if valor >= 80 else "Boa" if valor >= 60 else "Regular" if valor >= 40 else "Limitada"
    return {
        "valor": valor,
        "classificacao": classificacao,
        "explicacao": (
            "Média ponderada da proximidade do item mais próximo de cada categoria: 100 quando está a até 400 m"
            " (cerca de 7 min a pé), caindo em linha reta até 0 a 1,5 km. Pesos: mercados e transporte 20;"
            " escolas e saúde 15; parques, alimentação e bancos 10."
        ),
    }


def montar_comodidades(bruto: dict, lat: float, lng: float, raio_m: int = RAIO_M) -> dict:
    """Converte a resposta da Overpass em contagem por categoria, os 3 mais próximos e o índice."""
    grupos: dict[str, list[dict]] = {c["chave"]: [] for c in CATEGORIAS}
    for elemento in bruto.get("elements") or []:
        tags = elemento.get("tags") or {}
        destino = _classificar(tags)
        plat = elemento.get("lat", (elemento.get("center") or {}).get("lat"))
        plng = elemento.get("lon", (elemento.get("center") or {}).get("lon"))
        if destino is None or plat is None or plng is None:
            continue
        distancia = haversine_m(lat, lng, plat, plng)
        if distancia > raio_m * 1.05:  # áreas grandes cujo centro fica fora do raio
            continue
        chave, tipo = destino
        grupos[chave].append({"nome": tags.get("name") or tags.get("brand") or tipo, "tipo": tipo,
                              "distancia_m": distancia, "latitude": plat, "longitude": plng})

    categorias = []
    for categoria in CATEGORIAS:
        itens = sorted(grupos[categoria["chave"]], key=lambda i: i["distancia_m"])
        proximos, vistos = [], set()
        for item in itens:  # nomes distintos: as várias plataformas de uma estação contam como um item
            if item["nome"].casefold() in vistos:
                continue
            vistos.add(item["nome"].casefold())
            a_pe, carro = tempos(item["distancia_m"])
            proximos.append({**item, "distancia_m": round(item["distancia_m"]), "a_pe_min": a_pe, "carro_min": carro,
                             "latitude": round(item["latitude"], 6), "longitude": round(item["longitude"], 6)})
            if len(proximos) == MAIS_PROXIMOS:
                break
        categorias.append({"chave": categoria["chave"], "nome": categoria["nome"], "quantidade": len(itens),
                           "mais_proximos": proximos})

    return {
        "disponivel": True,
        "latitude": lat, "longitude": lng, "raio_m": raio_m,
        "categorias": categorias,
        "indice_conveniencia": indice_conveniencia(categorias),
        "metodo": METODO,
        "fonte": FONTE,
        "consultado_em": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def indisponivel(lat: float, lng: float) -> dict:
    return {"disponivel": False, "latitude": lat, "longitude": lng, "raio_m": RAIO_M, "categorias": [],
            "indice_conveniencia": None, "metodo": METODO, "fonte": FONTE, "consultado_em": None}


class ServicoComodidades:
    def __init__(self, consultar=_consultar_overpass):
        self._consultar = consultar
        self._cache: dict[tuple[float, float], dict] = {}
        self._trava = threading.Lock()
        self._falhou_em = -math.inf

    def comodidades(self, lat: float, lng: float) -> dict:
        chave = (round(lat, 4), round(lng, 4))
        if chave in self._cache:
            return self._cache[chave]
        if obter("AVALIADOR_COMODIDADES", "1").strip() == "0":
            return indisponivel(*chave)
        with self._trava:  # uma consulta por vez: a Overpass pública limita pedidos simultâneos
            if chave in self._cache:
                return self._cache[chave]
            if time.monotonic() - self._falhou_em < ESPERA_APOS_FALHA_S:
                return indisponivel(*chave)
            try:
                resultado = montar_comodidades(self._consultar(*chave), *chave)
            except Exception:
                self._falhou_em = time.monotonic()
                return indisponivel(*chave)  # sem cache: tenta de novo depois da espera
            self._cache[chave] = resultado
            return resultado
