"""
# Camada de serviço do modelo

Concentra a carga do artefato serializado e a inferência. Não conhece HTTP:
recebe objetos Python e devolve objetos Python, o que facilita testes e reuso.

## Decisão técnica (Fase 3)
O `joblib.load` só acontece em `carregar()`, chamado uma única vez pelo
`lifespan` na subida da aplicação. As rotas usam o pipeline que já está na
memória RAM; nenhuma requisição lê o disco.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import joblib


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
        self.carregado_em = datetime.now(timezone.utc)

    def descarregar(self) -> None:
        self.modelo = None
