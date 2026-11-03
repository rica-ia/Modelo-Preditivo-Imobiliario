"""
# Endereço a partir das coordenadas (geocodificação reversa)

O dataset de King County traz latitude, longitude e CEP, mas não a rua. O endereço vem do
Nominatim, o geocodificador aberto do OpenStreetMap: sem chave e sem custo, com a política
de uso respeitada (identificação no User-Agent, no máximo 1 consulta por segundo e cache).

- Cada coordenada (arredondada a 5 casas, cerca de 1 m) é consultada uma única vez por execução.
- Falha de rede não derruba nada: a resposta volta com `disponivel = false` e o portal mantém o CEP.
- `AVALIADOR_GEOCODIFICAR=0` desliga a consulta (usado nos testes, que rodam sem rede).
"""

import json
import threading
import time
import urllib.parse
import urllib.request

from ..config import obter

URL_NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
AGENTE = "AvaliadorImobiliario/2.0 (avaliadorimobiliario.api@gmail.com)"
INTERVALO_S = 1.1
FONTE = "© OpenStreetMap (Nominatim)"


def _consultar_nominatim(lat: float, lng: float) -> dict:
    parametros = urllib.parse.urlencode({"format": "jsonv2", "lat": lat, "lon": lng, "zoom": 18, "addressdetails": 1})
    pedido = urllib.request.Request(f"{URL_NOMINATIM}?{parametros}",
                                    headers={"User-Agent": AGENTE, "Accept-Language": "en"})
    with urllib.request.urlopen(pedido, timeout=6) as resposta:
        return json.load(resposta)


def montar_endereco(bruto: dict) -> dict:
    """Converte a resposta do Nominatim nos campos que o portal mostra."""
    a = bruto.get("address") or {}
    rua = a.get("road") or a.get("pedestrian") or a.get("footway") or a.get("residential")
    numero = a.get("house_number")
    bairro = a.get("neighbourhood") or a.get("suburb") or a.get("quarter") or a.get("hamlet")
    cidade = a.get("city") or a.get("town") or a.get("village") or a.get("municipality")
    cep = (a.get("postcode") or "").split("-")[0] or None
    linha1 = " ".join(p for p in (numero, rua) if p) or None
    partes = [linha1, bairro, ", ".join(p for p in (cidade, f"WA {cep}" if cep else "WA") if p)]
    return {
        "disponivel": bool(rua or cidade),
        "endereco": ", ".join(p for p in partes if p) or None,
        "rua": rua, "numero": numero, "bairro": bairro, "cidade": cidade, "cep": cep,
        "fonte": FONTE,
    }


class ServicoEndereco:
    def __init__(self, consultar=_consultar_nominatim):
        self._consultar = consultar
        self._cache: dict[tuple[float, float], dict] = {}
        self._trava = threading.Lock()
        self._ultima = 0.0

    def endereco(self, lat: float, lng: float) -> dict:
        chave = (round(lat, 5), round(lng, 5))
        if chave in self._cache:
            return self._cache[chave]
        if obter("AVALIADOR_GEOCODIFICAR", "1").strip() == "0":
            return {"disponivel": False, "endereco": None, "fonte": FONTE}
        with self._trava:  # uma consulta por vez, com o intervalo da política de uso
            if chave in self._cache:
                return self._cache[chave]
            espera = self._ultima + INTERVALO_S - time.monotonic()
            if espera > 0:
                time.sleep(espera)
            try:
                resultado = montar_endereco(self._consultar(*chave))
            except Exception:
                return {"disponivel": False, "endereco": None, "fonte": FONTE}  # sem cache: tenta de novo depois
            finally:
                self._ultima = time.monotonic()
            self._cache[chave] = resultado
            return resultado
