"""
# Vídeo 360° do entorno de um imóvel (imagens fotorrealistas do Google)

Gera, quadro a quadro, uma volta completa da câmera em torno do imóvel sobre o
Google Photorealistic 3D Tiles e codifica o resultado em MP4 (H.264) no próprio
navegador. Não há imagem sintética: cada quadro é a cena 3D real vista de um
rumo diferente (0° a 360°), e os quadros são juntados num vídeo contínuo.

Como funciona:
1. Pede a avaliação do imóvel à API (`POST /v1/predict`, porta 8020).
2. Abre `visao3d.html?modo=captura` no Microsoft Edge sem tela, numa porta de
   depuração exclusiva, e conduz a página pelo protocolo de depuração (CDP).
3. Aquece o cache dos blocos 3D numa volta rápida; depois, para cada quadro,
   posiciona a câmera, espera os blocos carregarem e codifica o quadro composto
   (cena + ficha com o valor estimado + créditos do Google).
4. Grava o vídeo em `modulo2_api/saida/videos/` (fora do Git: os termos do
   Google não permitem redistribuir imagens exportadas) e fecha o Edge pelo PID.

A chave vem de `GOOGLE_MAPS_API_KEY` no `.env` (nunca é impressa nem gravada).

Uso, a partir da raiz do repositório, com a API no ar:
    python -m modulo2_api.ferramentas.gerar_video_360
    python -m modulo2_api.ferramentas.gerar_video_360 --quadros 240 --copia "C:/caminho/video.mp4"
"""

import argparse
import base64
import functools
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from websockets.sync.client import connect

from modulo2_api.app.config import PASTA_MODULO2, PASTA_WEB, obter

API = "http://127.0.0.1:8020"
PASTA_SAIDA = PASTA_MODULO2 / "saida" / "videos"
EDGES = [
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
]

# Caso real da base (King County, vendas de 2014-2015): id 1814800060, CEP 98103,
# vendido por US$ 965.000 em fev/2015. As coordenadas da base têm 3 a 4 casas
# decimais, então a câmera orbita a quadra do imóvel.
IMOVEL_REAL = {
    "quartos": 4, "banheiros": 3.5, "area_util_m2": 305.6, "area_terreno_m2": 516.4, "andares": 1.5,
    "frente_agua": False, "vista": 0, "condicao": 3, "padrao_construtivo": 8, "area_porao_m2": 92.9,
    "ano_construcao": 1906, "ano_reforma": 2004, "cep": "98103", "latitude": 47.6788, "longitude": -122.346,
    "area_util_vizinhos_m2": 166.3, "area_terreno_vizinhos_m2": 557.4,
}
TITULO_REAL = "Casa junto ao Green Lake, Seattle · CEP 98103"


def registrar(*partes):
    print(time.strftime("%H:%M:%S"), *partes, flush=True)


# ## Avaliação pela API
def avaliar(imovel: dict) -> dict:
    corpo = json.dumps(imovel).encode("utf-8")
    pedido = urllib.request.Request(f"{API}/v1/predict", data=corpo, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(pedido, timeout=30) as resposta:
        return json.loads(resposta.read())


# ## Página: servida pela API ou, se a rota ainda não existir, por um servidor local da pasta web
def endereco_pagina() -> tuple[str, ThreadingHTTPServer | None]:
    try:
        with urllib.request.urlopen(f"{API}/visao3d.html", timeout=10) as r:
            if r.status == 200:
                return API, None
    except urllib.error.URLError:
        pass
    porta = porta_livre()
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), functools.partial(Silencioso, directory=str(PASTA_WEB)))
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{porta}", servidor


class Silencioso(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def porta_livre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ## Navegador sem tela, conduzido pelo protocolo de depuração
class Navegador:
    def __init__(self, largura: int, altura: int):
        edge = next((e for e in EDGES if e.exists()), None)
        if edge is None:
            sys.exit("Microsoft Edge não encontrado.")
        self.perfil = tempfile.mkdtemp(prefix="visao3d_edge_")
        self.porta = porta_livre()
        self.proc = subprocess.Popen([
            str(edge), "--headless=new", f"--remote-debugging-port={self.porta}", f"--user-data-dir={self.perfil}",
            f"--window-size={largura},{altura}", "--force-device-scale-factor=1", "--hide-scrollbars", "--mute-audio",
            "--no-first-run", "--no-default-browser-check", "--disable-extensions", "--ignore-gpu-blocklist",
            "--enable-unsafe-swiftshader", "--disable-background-timer-throttling", "--disable-renderer-backgrounding",
            "about:blank",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.ws = None
        self.n = 0

    def conectar(self):
        fim = time.time() + 30
        while time.time() < fim:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{self.porta}/json/list", timeout=3) as r:
                    alvo = next(t for t in json.loads(r.read()) if t.get("type") == "page")
                self._conexao = connect(alvo["webSocketDebuggerUrl"], max_size=None, open_timeout=30)
                self.ws = self._conexao.__enter__()
                return
            except (urllib.error.URLError, ConnectionError, StopIteration, OSError):
                time.sleep(0.5)
        raise RuntimeError("o Edge não abriu a porta de depuração")

    def comando(self, metodo: str, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": metodo, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(f"{metodo}: {msg['error'].get('message')}")
                return msg.get("result", {})

    def avaliar_js(self, expressao: str, timeout_s: float = 600):
        r = self.comando("Runtime.evaluate", expression=expressao, awaitPromise=True, returnByValue=True,
                         timeout=int(timeout_s * 1000))
        if "exceptionDetails" in r:
            detalhe = r["exceptionDetails"].get("exception", {}).get("description") or r["exceptionDetails"].get("text")
            raise RuntimeError(f"erro na página: {str(detalhe)[:300]}")
        return r.get("result", {}).get("value")

    def fechar(self):
        try:
            if self.ws:
                self.ws.close()
        finally:
            # encerra o Edge e os processos filhos pelo PID (nunca por nome)
            subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], capture_output=True)
            time.sleep(1)
            shutil.rmtree(self.perfil, ignore_errors=True)


# ## Geração
def gerar(args) -> Path:
    imovel = json.loads(Path(args.imovel).read_text(encoding="utf-8")) if args.imovel else IMOVEL_REAL
    titulo = args.titulo or (TITULO_REAL if not args.imovel else f"Imóvel no CEP {imovel['cep']}")
    chave = obter("GOOGLE_MAPS_API_KEY").strip()
    if not chave:
        sys.exit("GOOGLE_MAPS_API_KEY ausente no .env: a volta 360° com imagens fotorrealistas precisa da chave.")

    avaliacao = avaliar(imovel)
    faixa = avaliacao["faixa_provavel_usd"]
    registrar("valor estimado", f"US$ {avaliacao['preco_estimado_usd']:,.0f}",
              f"(faixa {faixa['minimo']:,.0f} a {faixa['maximo']:,.0f})")

    base, servidor = endereco_pagina()
    url = (f"{base}/visao3d.html?modo=captura&lat={imovel['latitude']}&lng={imovel['longitude']}"
           f"&dist={args.distancia}&incl={args.inclinacao}")
    nav = Navegador(args.largura, args.altura)
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    destino = PASTA_SAIDA / f"volta360_{imovel['cep']}_{time.strftime('%Y%m%d_%H%M')}.mp4"
    try:
        nav.conectar()
        nav.comando("Page.enable")
        nav.comando("Emulation.setDeviceMetricsOverride", width=args.largura, height=args.altura,
                    deviceScaleFactor=1, mobile=False)
        nav.comando("Page.navigate", url=url)
        nav.avaliar_js("new Promise(ok => { const t = setInterval(() => { if (window.__visao3d && window.Cesium) "
                       "{ clearInterval(t); ok(true); } }, 200); })", 90)
        cfg = {"chave": chave, "titulo": titulo, "valor": avaliacao["preco_estimado_usd"],
               "faixaMin": faixa["minimo"], "faixaMax": faixa["maximo"]}
        if not nav.avaliar_js(f"window.__visao3d.iniciar({json.dumps(cfg)})", 180):
            raise RuntimeError("a página não carregou as imagens 3D (chave recusada ou sem WebGL)")
        registrar("cena 3D pronta; aquecendo o cache dos blocos")
        ok = nav.avaliar_js(f"window.__visao3d.aquecer({args.aquecimento}, 30000)", 1800)
        registrar("aquecimento", f"{ok}/{args.aquecimento} rumos completos")

        nav.avaliar_js("window.__visao3d.quadro(0, 30000)", 60)
        cod = nav.avaliar_js(f"window.__visao3d.abrirCodificador({args.fps})", 60)
        if not cod:
            raise RuntimeError("o navegador não tem codificador de vídeo (H.264/VP9)")
        registrar("codificador", cod["codec"], f"{cod['W']}x{cod['H']}")

        incompletos, t0 = 0, time.time()
        for i in range(args.quadros):
            rumo = args.rumo0 + i * 360 / args.quadros
            if not nav.avaliar_js(f"window.__visao3d.quadro({rumo}, {args.teto_quadro * 1000})", args.teto_quadro + 30):
                incompletos += 1
            erro = nav.avaliar_js("window.__visao3d.codificar()", 60)
            if erro:
                raise RuntimeError(f"codificador: {erro}")
            if i == args.quadros // 8:
                quadro = nav.avaliar_js("window.__visao3d.jpeg(0.92)", 60)
                destino.with_suffix(".jpg").write_bytes(base64.b64decode(quadro.split(",", 1)[1]))
            if i % 60 == 0:
                registrar("quadro", f"{i}/{args.quadros}", f"{time.time() - t0:.0f}s")

        info = nav.avaliar_js("window.__visao3d.fechar()", 300)
        if info["formato"] != "mp4":
            destino = destino.with_suffix(".webm")
        with destino.open("wb") as arq:
            for o in range(0, info["bytes"], 3_000_000):
                arq.write(base64.b64decode(nav.avaliar_js(f"window.__visao3d.parte({o}, 3000000)", 60)))
        registrar("vídeo", destino.name, f"{info['bytes'] / 1e6:.1f} MB", f"{info['quadros']} quadros",
                  f"{info['quadros'] / args.fps:.0f} s", f"{incompletos} com blocos ainda carregando",
                  f"{time.time() - t0:.0f}s de render")
    finally:
        nav.fechar()
        if servidor:
            servidor.shutdown()

    if args.copia:
        copia = Path(args.copia)
        copia.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(destino, copia)
        if destino.with_suffix(".jpg").exists():
            shutil.copy2(destino.with_suffix(".jpg"), copia.with_suffix(".jpg"))
        registrar("cópia", str(copia))
    return destino


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap =argparse.ArgumentParser(description="Vídeo 360° do entorno do imóvel sobre as imagens 3D do Google.")
    ap.add_argument("--imovel", help="JSON com os campos de POST /v1/predict (padrão: caso real do CEP 98103).")
    ap.add_argument("--titulo", help="Título exibido no vídeo.")
    ap.add_argument("--quadros", type=int, default=720, help="Quadros da volta (720 = 24 s a 30 quadros/s).")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--largura", type=int, default=1280)
    ap.add_argument("--altura", type=int, default=720)
    ap.add_argument("--distancia", type=float, default=240, help="Distância da câmera ao imóvel, em metros.")
    ap.add_argument("--inclinacao", type=float, default=-32, help="Inclinação da câmera, em graus (negativo = olhando para baixo).")
    ap.add_argument("--rumo0", type=float, default=0, help="Rumo inicial da câmera, em graus.")
    ap.add_argument("--aquecimento", type=int, default=24, help="Rumos visitados antes da gravação, para encher o cache.")
    ap.add_argument("--teto-quadro", type=int, default=15, help="Espera máxima pelos blocos em cada quadro, em segundos.")
    ap.add_argument("--copia", help="Caminho extra onde copiar o vídeo pronto.")
    gerar(ap.parse_args())


if __name__ == "__main__":
    main()
