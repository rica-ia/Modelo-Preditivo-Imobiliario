"""
# Registro do artefato do modelo no SQLite

A API continua carregando o `.joblib` do disco no lifespan (Fase 3). Logo depois, este
serviço guarda uma cópia do mesmo binário na tabela `modelos` (coluna `artefato`, BLOB),
com sha256, tamanho, versão e métricas: o banco passa a ser o registro versionado do
artefato serializado.

- **Idempotente:** o sha256 é único; subir a API de novo com o mesmo arquivo não duplica.
  O artefato registrado (novo ou já existente) fica com `ativo = 1` e os demais com 0.
- **Restauração:** `restaurar()` grava o BLOB num arquivo temporário e o carrega com joblib.
- **Integridade:** `verificar()` compara o sha256 do BLOB, o do arquivo em disco e o do
  artefato lido na subida, e confere que o modelo restaurado prevê o mesmo valor que o
  modelo em memória para o imóvel de exemplo.
"""

import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path

import joblib
import pandas as pd

from ..config import RAIZ_REPOSITORIO
from ..schemas.imovel import EXEMPLO_IMOVEL, ImovelEntrada
from .banco import Banco, agora
from .excecoes import NaoEncontradoError
from .modelo import ServicoModelo

COLUNAS_LISTAGEM = (
    "id, versao, nome_arquivo, sha256, tamanho_bytes, formato, estimador, metricas_json, "
    "treinado_em, registrado_em, ativo"
)


def sha256_de(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


def _nome_relativo(caminho: Path) -> str:
    try:
        return str(Path(caminho).resolve().relative_to(RAIZ_REPOSITORIO)).replace("\\", "/")
    except ValueError:
        return Path(caminho).name


def _metricas_principais(metricas: dict) -> dict:
    """Validação e teste, que é o que importa para comparar versões."""
    return {chave: metricas.get("metricas", {}).get(chave) for chave in ("validacao", "teste")}


class ServicoRegistroModelo:
    def __init__(self, banco: Banco, servico: ServicoModelo):
        self.banco = banco
        self.servico = servico
        self.sha256_carregado: str | None = None
        self.registro_ativo: dict | None = None

    # ## Registro (chamado no lifespan, depois que o modelo já está na memória)
    def registrar(self) -> dict:
        conteudo = self.servico.caminho_modelo.read_bytes()
        sha = sha256_de(conteudo)
        self.sha256_carregado = sha
        metricas = self.servico.metricas
        novo = False
        with self.banco.conexao() as con:
            existente = con.execute("SELECT id FROM modelos WHERE sha256 = ?", (sha,)).fetchone()
            if existente is None:
                cursor = con.execute(
                    "INSERT INTO modelos (versao, nome_arquivo, sha256, tamanho_bytes, formato, estimador, "
                    "metricas_json, treinado_em, registrado_em, ativo, artefato) "
                    "VALUES (?, ?, ?, ?, 'joblib', ?, ?, ?, ?, 1, ?)",
                    (
                        self.servico.versao,
                        _nome_relativo(self.servico.caminho_modelo),
                        sha,
                        len(conteudo),
                        metricas.get("algoritmo"),
                        json.dumps(_metricas_principais(metricas), ensure_ascii=False),
                        metricas.get("treinado_em"),
                        agora(),
                        sqlite3.Binary(conteudo),
                    ),
                )
                registro_id = cursor.lastrowid
                novo = True
            else:
                registro_id = existente["id"]
            con.execute("UPDATE modelos SET ativo = CASE WHEN id = ? THEN 1 ELSE 0 END", (registro_id,))
        self.registro_ativo = {"id": registro_id, "sha256": sha, "versao": self.servico.versao, "novo": novo}
        return self.registro_ativo

    # ## Consulta (sem o BLOB)
    def listar(self) -> list[dict]:
        linhas = self.banco.consultar(f"SELECT {COLUNAS_LISTAGEM} FROM modelos ORDER BY id DESC")
        for linha in linhas:
            linha["metricas"] = json.loads(linha.pop("metricas_json") or "{}")
            linha["ativo"] = bool(linha["ativo"])
        return linhas

    def _blob(self, registro_id: int) -> dict:
        linha = self.banco.um("SELECT id, sha256, artefato FROM modelos WHERE id = ?", (registro_id,))
        if linha is None:
            raise NaoEncontradoError(f"Artefato {registro_id} não encontrado na tabela modelos.")
        return linha

    # ## Restauração: BLOB -> arquivo temporário -> joblib.load
    def restaurar(self, registro_id: int):
        conteudo = bytes(self._blob(registro_id)["artefato"])
        descritor, destino = tempfile.mkstemp(prefix="modelo-restaurado-", suffix=".joblib")
        try:
            with os.fdopen(descritor, "wb") as arquivo:
                arquivo.write(conteudo)
            return joblib.load(destino)
        finally:
            Path(destino).unlink(missing_ok=True)

    # ## Integridade: hashes iguais e a mesma previsão do modelo em memória
    def verificar(self, registro_id: int) -> dict:
        linha = self._blob(registro_id)
        conteudo = bytes(linha["artefato"])
        sha_blob = sha256_de(conteudo)
        caminho = self.servico.caminho_modelo
        sha_disco = sha256_de(caminho.read_bytes()) if caminho.exists() else None

        previsao_em_memoria = None
        previsao_restaurada = None
        erro = None
        entrada = pd.DataFrame([self.servico._para_colunas_do_modelo(ImovelEntrada(**EXEMPLO_IMOVEL))])
        if self.servico.carregado:
            previsao_em_memoria = round(float(self.servico.modelo.predict(entrada)[0]), 2)
        try:
            restaurado = self.restaurar(registro_id)
            previsao_restaurada = round(float(restaurado.predict(entrada)[0]), 2)
        except Exception as falha:  # BLOB corrompido não desserializa: a verificação responde, não quebra
            erro = f"O BLOB não pôde ser restaurado: {type(falha).__name__}."

        integro = (
            sha_blob == linha["sha256"]
            and sha_blob == sha_disco
            and sha_blob == self.sha256_carregado
            and previsao_restaurada is not None
            and previsao_restaurada == previsao_em_memoria
        )
        return {
            "id": registro_id,
            "integro": integro,
            "sha256_registrado": linha["sha256"],
            "sha256_blob": sha_blob,
            "sha256_disco": sha_disco,
            "sha256_carregado": self.sha256_carregado,
            "tamanho_bytes": len(conteudo),
            "previsao_restaurada": previsao_restaurada,
            "previsao_em_memoria": previsao_em_memoria,
            "imovel_exemplo": EXEMPLO_IMOVEL,
            "erro": erro,
        }

