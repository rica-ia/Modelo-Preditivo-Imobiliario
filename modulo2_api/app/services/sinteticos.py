"""
# Dados sintéticos de exemplo

Carga de demonstração para o banco não aparecer vazio: 20 clientes fictícios do
mercado imobiliário (King County/Seattle e Brasil), uma chave por cliente, o e-mail
de boas-vindas, a trilha de eventos comerciais, algumas centenas de predições,
20 laudos e as faturas mensais.

- **Tudo é fictício** e fica marcado: `clientes.sintetico = 1` e `avaliacoes.sintetico = 1`;
  e-mails só no domínio reservado `exemplo.com`; envios com status `exemplo_sintetico`.
  O resto (chaves, eventos, predições, envios, faturas) pertence a esses clientes.
- **Determinístico**: `random.Random(42)`; as datas são relativas a hoje (últimos ~90 dias).
- **Chaves inutilizáveis**: o hash é de um texto aleatório do sistema (`secrets`), nunca
  exibido nem gravado; só o prefixo vem da semente. Ninguém consegue usar essas chaves.
- **Idempotente**: carregar de novo não duplica; remover apaga só o sintético, na ordem
  das chaves estrangeiras.
- Preços e CEPs das predições e laudos vêm das vendas reais de `vendas_historicas`.

Ligada por `AVALIADOR_DADOS_SINTETICOS` (padrão "1": carrega no lifespan se ainda não houver).
"""

import hashlib
import random
import secrets
import string
import unicodedata
from datetime import date, datetime, timedelta

from ..config import obter
from .banco import Banco
from .planos import LIMITES, NOMES_PLANOS, PRECOS_USD

SEMENTE = 42
DIAS_DE_HISTORICO = 90
STATUS_ENVIO = "exemplo_sintetico"
DOMINIO = "exemplo.com"
TOTAL_LAUDOS = 20

# (nome, empresa ou None para pessoa física, plano atual, cenário)
# Cenário: situacao (ativa, suspensa, revogada, reativada), plano_anterior, edicao, uso_mes (perto do limite).
CLIENTES = [
    ("Megan Holloway", "Northlake Pine Realty Group", "empresarial", {}),
    ("Daniel Okafor", "Elliott Bay Home Appraisals", "profissional", {}),
    ("Priya Raman", "Cedar Loop Construction", "profissional", {}),
    ("Thomas Whitfield", "Sammamish Ridge Developers", "empresarial", {"edicao": "email"}),
    ("Laura Kessler", "Bellevue Crossing Brokers", "profissional", {"situacao": "reativada"}),
    ("Kevin Nakamura", "Green Lake Housing Fund", "empresarial", {"plano_anterior": "profissional"}),
    ("Rachel Moreno", "Kirkland Shoreline Mortgage", "profissional", {"situacao": "suspensa"}),
    ("Brian Castellano", None, "basico", {"uso_mes": 100}),
    ("Emily Sorensen", None, "basico", {"situacao": "revogada"}),
    ("Steven Lindqvist", "Redmond Valley Appraisers", "basico", {"situacao": "suspensa"}),
    ("Olivia Brandt", "Renton Gateway Properties", "basico", {"uso_mes": 84}),
    ("Ana Paula Ribeiro", "Imobiliária Ipê Dourado", "profissional", {"plano_anterior": "basico"}),
    ("Marcelo Tavares", "Construtora Serra Alta", "empresarial", {}),
    ("Juliana Campos", "Incorporadora Vale do Sol", "profissional", {"edicao": "empresa"}),
    ("Rafael Monteiro", "Fundo Imobiliário Atlântico Sul", "empresarial", {}),
    ("Camila Nogueira", "Banco Aurora de Crédito Imobiliário", "profissional", {}),
    ("Fernando Albuquerque", "Avalia Mais Engenharia de Avaliações", "basico", {"situacao": "revogada"}),
    ("Patrícia Lacerda", "Corretora Morada Nova", "basico", {"situacao": "suspensa", "plano_anterior": "profissional"}),
    ("Gustavo Prado", None, "basico", {}),
    ("Beatriz Fontes", None, "profissional", {}),
]

# Predições esperadas por dia, conforme o plano (fora os clientes perto do limite).
RITMO_DIARIO = {"basico": 0.3, "profissional": 0.6, "empresarial": 0.9}

# Competências recentes faturadas por cliente (as suspensas têm ao menos 2: a vencida e a do mês).
COMPETENCIAS_POR_PLANO = {"basico": 1, "profissional": 2, "empresarial": 3}

# Reserva caso `vendas_historicas` ainda esteja vazia: (cep, área útil m², preço USD).
VENDAS_RESERVA = [("98004", 260.0, 1_450_000.0), ("98052", 190.0, 640_000.0), ("98103", 140.0, 560_000.0),
                  ("98033", 210.0, 890_000.0), ("98059", 175.0, 470_000.0), ("98115", 160.0, 610_000.0)]


def _iso(momento: datetime) -> str:
    return momento.isoformat(timespec="seconds")


def _email(nome: str) -> str:
    simples = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower().split()
    return f"{simples[0]}.{simples[-1]}@{DOMINIO}"


def _mes(momento: datetime | date) -> str:
    return f"{momento.year:04d}-{momento.month:02d}"


def _meses_recentes(agora: datetime, quantidade: int = 3) -> list[str]:
    ano, mes, meses = agora.year, agora.month, []
    for _ in range(quantidade):
        meses.append(f"{ano:04d}-{mes:02d}")
        ano, mes = (ano - 1, 12) if mes == 1 else (ano, mes - 1)
    return sorted(meses)


def _inicio_do_mes(competencia: str, referencia: datetime) -> datetime:
    ano, mes = map(int, competencia.split("-"))
    return referencia.replace(year=ano, month=mes, day=1, hour=8, minute=0, second=0)


def ha_sinteticos(banco: Banco) -> bool:
    return bool(banco.um("SELECT 1 AS existe FROM clientes WHERE sintetico = 1 LIMIT 1"))


def _vendas(banco: Banco) -> list[dict]:
    return banco.consultar(
        "SELECT cep, cidade, quartos, banheiros, area_util_m2, area_terreno_m2, padrao, condicao, vista, frente_agua,"
        " ano_construcao, ano_reforma, latitude, longitude, preco_usd FROM vendas_historicas ORDER BY id_venda"
    )


def _momento_entre(rng: random.Random, inicio: datetime, fim: datetime) -> datetime:
    segundos = max(int((fim - inicio).total_seconds()), 1)
    return inicio + timedelta(seconds=rng.randrange(segundos))


def _linhas_do_tempo(rng: random.Random, agora: datetime) -> list[dict]:
    """Datas de cadastro, troca de plano, suspensão, reativação e revogação de cada cliente."""
    perfis = []
    for nome, empresa, plano, cenario in CLIENTES:
        criado = agora - timedelta(days=rng.randint(12, DIAS_DE_HISTORICO - 2), hours=rng.randint(0, 9),
                                   minutes=rng.randint(0, 59))
        criado = criado.replace(hour=rng.randint(8, 18))
        situacao = cenario.get("situacao", "ativa")
        perfil = {"nome": nome, "empresa": empresa, "plano": plano, "email": _email(nome),
                  "plano_inicial": cenario.get("plano_anterior", plano), "situacao": situacao,
                  "criado": criado, "edicao": cenario.get("edicao"), "uso_mes": cenario.get("uso_mes")}
        vida = (agora - criado).days
        if situacao in ("suspensa", "reativada"):
            perfil["suspensa_em"] = agora - timedelta(days=rng.randint(2, min(12, vida - 2)), minutes=rng.randint(0, 600))
            if situacao == "reativada":
                perfil["reativada_em"] = perfil["suspensa_em"] + timedelta(days=rng.randint(1, 2))
        if perfil["plano_inicial"] != plano:
            troca = criado + timedelta(days=rng.randint(max(vida // 3, 3), max(vida - 3, 4)), minutes=rng.randint(0, 600))
            if perfil.get("suspensa_em"):
                troca = min(troca, perfil["suspensa_em"] - timedelta(days=1))
            perfil["troca_em"] = troca
        if situacao == "revogada":
            perfil["revogada_em"] = agora - timedelta(days=rng.randint(4, min(25, vida - 5)), minutes=rng.randint(0, 600))
        if perfil["edicao"]:
            perfil["editado_em"] = criado + timedelta(days=rng.randint(1, max(vida // 2, 2)), minutes=rng.randint(0, 600))
        perfil["fim_uso"] = perfil.get("revogada_em") or (
            perfil["suspensa_em"] if situacao == "suspensa" else agora
        )
        perfis.append(perfil)
    return perfis


def _gerar_predicoes(rng: random.Random, perfil: dict, vendas: list, agora: datetime) -> list[dict]:
    inicio, fim = perfil["criado"] + timedelta(minutes=5), perfil["fim_uso"]
    inicio_mes = agora.replace(day=1, hour=0, minute=0, second=0)
    linhas = []

    def nova(momento: datetime, status: int) -> dict:
        cep, area, preco = vendas[rng.randrange(len(vendas))]
        return {
            "criado_em": momento, "origem": "api", "cep": cep, "area_util_m2": area,
            "preco_estimado_usd": round(preco * (1 + rng.gauss(0, 0.08)), 0) if status == 200 else None,
            "latencia_ms": round(rng.uniform(6, 38), 1) if status == 200 else round(rng.uniform(0.8, 3.5), 1),
            "status_http": status,
        }

    alvo = perfil["uso_mes"]
    ritmo = RITMO_DIARIO[perfil["plano"]]
    dia = inicio.replace(hour=0, minute=0, second=0)
    while dia < fim:
        if alvo is not None and dia >= inicio_mes:
            break  # o mês corrente dos clientes perto do limite é gerado abaixo, com volume fixo
        de, ate = max(dia, inicio), min(dia + timedelta(days=1), fim)
        for _ in range(3):
            if rng.random() < ritmo / 3 and ate > de:
                linhas.append(nova(_momento_entre(rng, de, ate), 422 if rng.random() < 0.07 else 200))
        dia += timedelta(days=1)
    if alvo is not None:
        de = max(inicio_mes, inicio)
        momentos = sorted(_momento_entre(rng, de, agora) for _ in range(alvo + 10))
        atendidas = 0
        for momento in momentos:
            if atendidas >= LIMITES[perfil["plano"]]:
                linhas.append(nova(momento, 429))
            elif rng.random() < 0.04:
                linhas.append(nova(momento, 422))
            else:
                linhas.append(nova(momento, 200))
                atendidas += 1
            if atendidas >= alvo and atendidas < LIMITES[perfil["plano"]]:
                break
    return linhas


def _imovel_de_venda(venda: dict) -> dict:
    area = float(venda["area_util_m2"])
    return {
        "quartos": int(venda["quartos"]), "banheiros": float(venda["banheiros"]), "area_util_m2": area,
        "area_terreno_m2": float(venda["area_terreno_m2"]), "andares": 1.0 if area < 140 else 2.0,
        "frente_agua": bool(venda["frente_agua"]), "vista": int(venda["vista"]), "condicao": int(venda["condicao"]),
        "padrao_construtivo": int(venda["padrao"]), "area_porao_m2": 0.0, "ano_construcao": int(venda["ano_construcao"]),
        "ano_reforma": int(venda["ano_reforma"]) if venda["ano_reforma"] else None, "cep": str(venda["cep"]),
        "latitude": float(venda["latitude"]), "longitude": float(venda["longitude"]),
        "area_util_vizinhos_m2": area, "area_terreno_vizinhos_m2": float(venda["area_terreno_m2"]),
    }


def _tipo_de_imovel(venda: dict) -> str:
    if venda["frente_agua"]:
        return "Residência à beira d'água"
    if venda["padrao"] >= 10:
        return "Residência de alto padrão"
    if venda["quartos"] <= 2:
        return "Casa compacta"
    return "Sobrado" if venda["area_util_m2"] >= 140 else "Residência"


def _laudos(rng: random.Random, banco: Banco, vendas: list[dict], perfis: list[dict], chaves: list[int],
            servico, agora: datetime) -> list[tuple]:
    from pydantic import ValidationError

    from ..schemas.imovel import ImovelEntrada
    from .carga import classificar, limites_de_faixa

    candidatos, imoveis = [], []
    for venda in rng.sample(vendas, min(len(vendas), 200)):
        try:
            imovel = ImovelEntrada(**_imovel_de_venda(venda))
        except ValidationError:
            continue
        candidatos.append(venda)
        imoveis.append(imovel)
        if len(candidatos) == TOTAL_LAUDOS:
            break
    previsoes = None
    if servico is not None and getattr(servico, "carregado", False):
        try:
            previsoes = servico.prever(imoveis)
        except Exception:
            previsoes = None
    existente = banco.um("SELECT versao_modelo FROM avaliacoes ORDER BY id LIMIT 1")
    versao = existente["versao_modelo"] if existente else getattr(servico, "versao", "v2")
    limites = limites_de_faixa(banco)
    registros = []
    for posicao, (venda, imovel) in enumerate(zip(candidatos, imoveis)):
        indice = posicao % len(perfis)  # um laudo por cliente
        perfil = perfis[indice]
        momento = _momento_entre(rng, perfil["criado"] + timedelta(hours=1), perfil["fim_uso"])
        if previsoes:
            p = previsoes[posicao]
            preco, minimo, maximo = p.preco_estimado_usd, p.faixa_provavel_usd.minimo, p.faixa_provavel_usd.maximo
            preco_m2, versao_laudo, latencia = p.preco_por_m2_usd, p.versao_modelo, p.latencia_ms
        else:
            preco = round(float(venda["preco_usd"]) * (1 + rng.gauss(0, 0.07)), 0)
            minimo, maximo = round(preco * 0.88, 0), round(preco * 1.12, 0)
            preco_m2, versao_laudo, latencia = round(preco / imovel.area_util_m2, 2), versao, round(rng.uniform(8, 35), 1)
        registros.append((
            _iso(momento), f"Laudo – {_tipo_de_imovel(venda)} em {venda['cidade']} ({venda['cep']})", perfil["nome"],
            chaves[indice], "api", imovel.model_dump_json(), imovel.quartos, imovel.banheiros, imovel.area_util_m2,
            imovel.padrao_construtivo, imovel.cep, venda["cidade"], imovel.latitude, imovel.longitude, preco, minimo,
            maximo, preco_m2, classificar(preco, limites), None, versao_laudo, latencia, 1,
        ))
    return registros


def _faturas(rng: random.Random, perfil: dict, chave_id: int, predicoes: list[dict], agora: datetime) -> list[tuple]:
    mes_criado = _mes(perfil["criado"])
    mes_revogada = _mes(perfil["revogada_em"]) if perfil.get("revogada_em") else None
    quantidade = max(COMPETENCIAS_POR_PLANO[perfil["plano"]], 2 if perfil["situacao"] == "suspensa" else 1)
    # Revogada: as competências terminam no mês da revogação, cuja fatura é cancelada
    meses = [m for m in _meses_recentes(perfil.get("revogada_em") or agora, quantidade) if m >= mes_criado]
    mes_atual = _mes(agora)
    registros = []
    for posicao, competencia in enumerate(meses):
        troca = perfil.get("troca_em")
        plano = perfil["plano"] if troca is None or competencia >= _mes(troca) else perfil["plano_inicial"]
        emitida = perfil["criado"] + timedelta(seconds=2) if competencia == mes_criado else _inicio_do_mes(competencia, agora)
        emitida = min(emitida, agora)
        vencimento = (emitida + timedelta(days=10)).date()
        uso = sum(1 for p in predicoes if p["status_http"] == 200 and _mes(p["criado_em"]) == competencia)
        paga_em = None
        if competencia == mes_revogada:
            status = "cancelada"
        elif perfil["situacao"] == "suspensa" and competencia != mes_atual and posicao == len(meses) - 2:
            status = "vencida"  # motivo da suspensão: fatura em atraso
        elif competencia == mes_atual and (perfil["situacao"] == "suspensa" or rng.random() < 0.5):
            status = "vencida" if agora.date() > vencimento else "em_aberto"
        else:
            status = "paga"
            paga_em = min(emitida + timedelta(days=rng.randint(0, 8), hours=rng.randint(1, 10)), agora)
        registros.append((competencia, plano, PRECOS_USD[plano], uso, status, _iso(emitida), vencimento.isoformat(),
                          _iso(paga_em) if paga_em else None))
    return registros


def carregar_sinteticos(banco: Banco, servico=None) -> dict:
    """Insere a carga de exemplo (se ainda não existir) e devolve quantas linhas entraram em cada tabela."""
    contagens = dict.fromkeys(("clientes", "chaves", "envios_email", "eventos_comerciais", "predicoes",
                               "avaliacoes", "faturas"), 0)
    if ha_sinteticos(banco):
        return contagens
    rng = random.Random(SEMENTE)
    agora = datetime.now().astimezone().replace(microsecond=0)
    reais = _vendas(banco)
    vendas = [(v["cep"], v["area_util_m2"], v["preco_usd"]) for v in reais] or VENDAS_RESERVA
    perfis = _linhas_do_tempo(rng, agora)
    alfabeto = string.ascii_letters + string.digits
    chaves, predicoes_por_cliente = [], []

    with banco.conexao() as con:
        def evento(cliente_id, chave_id, tipo, detalhe, momento):
            con.execute("INSERT INTO eventos_comerciais (cliente_id, chave_id, tipo, detalhe, criado_em) VALUES (?, ?, ?, ?, ?)",
                        (cliente_id, chave_id, tipo, detalhe, _iso(momento)))
            contagens["eventos_comerciais"] += 1

        for perfil in perfis:
            cliente_id = con.execute(
                "INSERT INTO clientes (nome, email, empresa, plano, criado_em, sintetico) VALUES (?, ?, ?, ?, ?, 1)",
                (perfil["nome"], perfil["email"], perfil["empresa"], perfil["plano"], _iso(perfil["criado"])),
            ).lastrowid
            perfil["cliente_id"] = cliente_id
            prefixo = "aval_" + "".join(rng.choice(alfabeto) for _ in range(7))
            segredo = prefixo + secrets.token_urlsafe(24)  # nunca exibido nem gravado: chave inutilizável
            chave_id = con.execute(
                "INSERT INTO chaves (cliente_id, prefixo, hash_sha256, limite_mensal, criada_em, revogada_em, suspensa_em)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (cliente_id, prefixo, hashlib.sha256(segredo.encode("utf-8")).hexdigest(), LIMITES[perfil["plano"]],
                 _iso(perfil["criado"] + timedelta(seconds=1)),
                 _iso(perfil["revogada_em"]) if perfil.get("revogada_em") else None,
                 _iso(perfil["suspensa_em"]) if perfil["situacao"] == "suspensa" else None),
            ).lastrowid
            chaves.append(chave_id)
            contagens["clientes"] += 1
            contagens["chaves"] += 1

            con.execute(
                "INSERT INTO envios_email (cliente_id, destinatario, assunto, modo, status, criado_em, arquivo)"
                " VALUES (?, ?, ?, 'arquivo', ?, ?, NULL)",
                (cliente_id, perfil["email"],
                 f"Sua chave de API do Avaliador Imobiliário · plano {NOMES_PLANOS[perfil['plano_inicial']]}",
                 STATUS_ENVIO, _iso(perfil["criado"] + timedelta(seconds=rng.randint(2, 6)))),
            )
            contagens["envios_email"] += 1

            evento(cliente_id, chave_id, "emissao",
                   f"plano {NOMES_PLANOS[perfil['plano_inicial']]} (dado sintético de exemplo)",
                   perfil["criado"] + timedelta(seconds=1))
            if perfil.get("editado_em"):
                evento(cliente_id, None, "edicao", f"alterado: {perfil['edicao']}", perfil["editado_em"])
            if perfil.get("troca_em"):
                anterior, atual = perfil["plano_inicial"], perfil["plano"]
                movimento = "upgrade" if PRECOS_USD[atual] > PRECOS_USD[anterior] else "downgrade"
                evento(cliente_id, chave_id, "troca_plano",
                       f"{NOMES_PLANOS[anterior]} → {NOMES_PLANOS[atual]} ({movimento})", perfil["troca_em"])
            if perfil.get("suspensa_em"):
                evento(cliente_id, chave_id, "suspensao", "Fatura em atraso", perfil["suspensa_em"])
            if perfil.get("reativada_em"):
                evento(cliente_id, chave_id, "reativacao", "acesso liberado", perfil["reativada_em"])
            if perfil.get("revogada_em"):
                evento(cliente_id, chave_id, "revogacao", "revogação definitiva", perfil["revogada_em"])

            predicoes = _gerar_predicoes(rng, perfil, vendas, agora)
            for linha in predicoes:
                linha["chave_id"] = chave_id
            predicoes_por_cliente.append(predicoes)

        todas = sorted((p for lista in predicoes_por_cliente for p in lista), key=lambda p: p["criado_em"])
        con.executemany(
            "INSERT INTO predicoes (criado_em, chave_id, origem, cep, area_util_m2, preco_estimado_usd, latencia_ms,"
            " status_http) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(_iso(p["criado_em"]), p["chave_id"], p["origem"], p["cep"], p["area_util_m2"], p["preco_estimado_usd"],
              p["latencia_ms"], p["status_http"]) for p in todas],
        )
        contagens["predicoes"] = len(todas)

        for perfil, chave_id, predicoes in zip(perfis, chaves, predicoes_por_cliente):
            for fatura in _faturas(rng, perfil, chave_id, predicoes, agora):
                con.execute(
                    "INSERT INTO faturas (cliente_id, chave_id, competencia, plano, valor_usd, predicoes, status,"
                    " emitida_em, vencimento, paga_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (perfil["cliente_id"], chave_id, *fatura),
                )
                contagens["faturas"] += 1

    if reais:
        laudos = _laudos(rng, banco, reais, perfis, chaves, servico, agora)
        with banco.conexao() as con:
            con.executemany(
                "INSERT INTO avaliacoes (criado_em, titulo, responsavel, cliente_chave_id, origem, entrada_json, quartos,"
                " banheiros, area_util_m2, padrao, cep, cidade, latitude, longitude, preco_estimado_usd, faixa_min,"
                " faixa_max, preco_m2_usd, faixa_preco, preco_real_usd, versao_modelo, latencia_ms, sintetico)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                laudos,
            )
        contagens["avaliacoes"] = len(laudos)
    return contagens


def remover_sinteticos(banco: Banco) -> dict:
    """Apaga só a carga de exemplo, dos dependentes para os clientes; devolve quantas linhas saíram."""
    clientes = "SELECT id FROM clientes WHERE sintetico = 1"
    chaves = f"SELECT id FROM chaves WHERE cliente_id IN ({clientes})"
    ordem = [
        ("predicoes", f"DELETE FROM predicoes WHERE chave_id IN ({chaves})"),
        ("avaliacoes", f"DELETE FROM avaliacoes WHERE sintetico = 1 OR cliente_chave_id IN ({chaves})"),
        ("faturas", f"DELETE FROM faturas WHERE cliente_id IN ({clientes})"),
        ("envios_email", f"DELETE FROM envios_email WHERE cliente_id IN ({clientes})"),
        ("eventos_comerciais", f"DELETE FROM eventos_comerciais WHERE cliente_id IN ({clientes})"),
        ("chaves", f"DELETE FROM chaves WHERE cliente_id IN ({clientes})"),
        ("clientes", "DELETE FROM clientes WHERE sintetico = 1"),
    ]
    contagens = {}
    with banco.conexao() as con:
        for tabela, sql in ordem:
            contagens[tabela] = con.execute(sql).rowcount
    return contagens


def carga_automatica(banco: Banco, servico=None) -> dict | None:
    """Chamada no lifespan: carrega se `AVALIADOR_DADOS_SINTETICOS` for "1" (padrão) e ainda não houver."""
    if obter("AVALIADOR_DADOS_SINTETICOS", "1").strip() != "1":
        return None
    return carregar_sinteticos(banco, servico)
