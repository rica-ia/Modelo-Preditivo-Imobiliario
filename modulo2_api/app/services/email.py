"""
# E-mail de boas-vindas com a chave de API

Monta a mensagem (texto e HTML, em pt-BR) e envia pelo Gmail com STARTTLS,
usando SMTP_USUARIO e SMTP_SENHA_APP do .env. Sem SMTP configurado, ou se o envio
falhar, a mensagem é salva como .eml para entrega manual. A senha nunca aparece
em log, resposta ou banco.
"""

import copy
import html
import logging
import smtplib
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

from ..config import PASTA_WEB, obter
from .planos import NOMES_PLANOS, PRECOS_USD, formatar_usd

log = logging.getLogger("avaliador")


def _url_base() -> str:
    return obter("AVALIADOR_URL_PUBLICA", "http://127.0.0.1:8020").rstrip("/")


def montar_email(nome: str, destinatario: str, chave: str, plano: str, limite: int) -> EmailMessage:
    base = _url_base()
    plano_nome = NOMES_PLANOS.get(plano, plano)
    limite_txt = f"{limite:,}".replace(",", ".")
    preco_txt = f"{formatar_usd(PRECOS_USD[plano])} por mês" if plano in PRECOS_USD else "—"
    curl = (
        f'curl -X POST {base}/v1/predict \\\n'
        f'  -H "Content-Type: application/json" \\\n'
        f'  -H "X-API-Key: {chave}" \\\n'
        "  -d '{\"quartos\":3,\"banheiros\":2,\"area_util_m2\":170,\"area_terreno_m2\":700,"
        "\"andares\":1,\"frente_agua\":false,\"vista\":0,\"condicao\":3,\"padrao_construtivo\":7,"
        "\"ano_construcao\":1990,\"cep\":\"98103\",\"latitude\":47.67,\"longitude\":-122.34}'"
    )
    remetente_nome = obter("SMTP_REMETENTE_NOME", "Avaliador Imobiliário")
    remetente = obter("SMTP_USUARIO") or "nao-responda@avaliador.local"

    msg = EmailMessage()
    msg["Subject"] = f"Sua chave de API do Avaliador Imobiliário · plano {plano_nome}"
    msg["From"] = formataddr((remetente_nome, remetente))
    msg["To"] = destinatario
    msg["Message-ID"] = make_msgid(domain="avaliador.local")

    texto = f"""Olá, {nome}!

Sua chave de API do Avaliador Imobiliário está pronta.

Chave: {chave}
Plano: {plano_nome} · até {limite_txt} predições por mês · {preco_txt}

Como usar
1. Envie a chave no cabeçalho X-API-Key de cada requisição.
2. Exemplo:

{curl}

3. Documentação interativa: {base}/docs
4. Consumo do mês: GET {base}/v1/comercial/uso (com o mesmo cabeçalho)

Guarde a chave com segurança: ela é exibida só uma vez e não fica gravada em
nossos servidores (guardamos apenas um hash). Em caso de vazamento, peça a
revogação e uma nova chave.

Equipe Avaliador Imobiliário
by Ricardo Pasquali dos Reis
"""
    e = html.escape
    emitida = datetime.now().strftime("%d/%m/%Y às %Hh%M")
    cid_logo = make_msgid(domain="avaliador.local")
    corpo_html = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#eeeef2;font-family:Urbanist,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1d1d1f">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eeeef2"><tr><td align="center" style="padding:32px 12px">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;border-radius:20px;overflow:hidden;background:#ffffff;box-shadow:0 6px 24px rgba(20,20,20,.10)">
  <tr><td style="background:#141414;padding:26px 32px">
    <table role="presentation" cellpadding="0" cellspacing="0"><tr>
      <td style="vertical-align:middle"><img src="cid:{cid_logo[1:-1]}" width="52" height="52" alt="Avaliador Imobiliário" style="display:block;border:0;border-radius:14px"></td>
      <td style="vertical-align:middle;padding-left:14px">
        <div style="font-size:20px;font-weight:700;color:#ffffff;letter-spacing:.01em">Avaliador Imobiliário</div>
        <div style="font-size:13px;color:#a685fa;margin-top:2px">Plataforma de gestão e análise · API preditiva</div>
      </td></tr></table>
    <div style="margin-top:14px;padding-top:12px;border-top:1px solid #2a2a2a;text-align:right;font-family:Georgia,'Times New Roman',serif;font-style:italic;font-size:14px;letter-spacing:.03em;color:#c2acfc">by Ricardo Pasquali dos Reis</div>
  </td></tr>
  <tr><td style="height:4px;background:#703bf7;line-height:4px;font-size:0">&nbsp;</td></tr>
  <tr><td style="padding:32px 32px 8px">
    <p style="margin:0 0 6px;font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:#703bf7;font-weight:700">Chave de API emitida</p>
    <h1 style="margin:0 0 12px;font-size:26px;line-height:1.25;color:#141414">Olá, {e(nome)}!</h1>
    <p style="margin:0;font-size:16px;line-height:1.6;color:#3a3a3c">Sua chave de acesso à API do Avaliador Imobiliário está ativa. Com ela, seus sistemas recebem em milissegundos o preço estimado de um imóvel, com a faixa provável de valor e o preço por m².</p>
  </td></tr>
  <tr><td style="padding:20px 32px 4px">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border:2px solid #703bf7;border-radius:14px;background:#f6f2ff">
      <tr><td style="padding:16px 18px">
        <div style="font-size:12px;color:#5b2fd1;font-weight:700;text-transform:uppercase;letter-spacing:.08em">Sua chave · cabeçalho X-API-Key</div>
        <div style="font-family:Consolas,Menlo,monospace;font-size:15px;color:#141414;word-break:break-all;margin-top:8px">{e(chave)}</div>
      </td></tr>
    </table>
  </td></tr>
  <tr><td style="padding:16px 32px 4px">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:14px;color:#3a3a3c;border-collapse:collapse">
      <tr><td style="padding:9px 0;border-bottom:1px solid #ececf0;color:#6e6e73">Plano</td><td align="right" style="padding:9px 0;border-bottom:1px solid #ececf0;font-weight:700;color:#141414">{e(plano_nome)}</td></tr>
      <tr><td style="padding:9px 0;border-bottom:1px solid #ececf0;color:#6e6e73">Limite mensal</td><td align="right" style="padding:9px 0;border-bottom:1px solid #ececf0;font-weight:700;color:#141414">{limite_txt} predições</td></tr>
      <tr><td style="padding:9px 0;border-bottom:1px solid #ececf0;color:#6e6e73">Valor mensal</td><td align="right" style="padding:9px 0;border-bottom:1px solid #ececf0;font-weight:700;color:#141414">{preco_txt}</td></tr>
      <tr><td style="padding:9px 0;border-bottom:1px solid #ececf0;color:#6e6e73">Emitida em</td><td align="right" style="padding:9px 0;border-bottom:1px solid #ececf0;color:#141414">{emitida}</td></tr>
      <tr><td style="padding:9px 0;color:#6e6e73">Cobertura</td><td align="right" style="padding:9px 0;color:#141414">King County (WA) · modelo v2</td></tr>
    </table>
  </td></tr>
  <tr><td style="padding:24px 32px 0">
    <h2 style="margin:0 0 10px;font-size:18px;color:#141414">Como usar em 3 passos</h2>
    <ol style="margin:0;padding-left:20px;font-size:15px;line-height:1.7;color:#3a3a3c">
      <li>Envie a chave no cabeçalho <b>X-API-Key</b> de cada requisição.</li>
      <li>Chame <b>POST /v1/predict</b> com os dados do imóvel, como no exemplo abaixo.</li>
      <li>Acompanhe o consumo do mês em <b>GET /v1/comercial/uso</b>, com o mesmo cabeçalho.</li>
    </ol>
  </td></tr>
  <tr><td style="padding:14px 32px 0">
    <pre style="margin:0;background:#141414;color:#e9e3ff;border-radius:12px;padding:16px;font-family:Consolas,Menlo,monospace;font-size:12px;line-height:1.5;white-space:pre-wrap;word-break:break-all">{e(curl)}</pre>
  </td></tr>
  <tr><td align="center" style="padding:26px 32px 6px">
    <a href="{e(base)}/docs" style="display:inline-block;background:#703bf7;color:#ffffff;text-decoration:none;font-weight:700;font-size:15px;padding:13px 28px;border-radius:12px">Abrir a documentação interativa</a>
  </td></tr>
  <tr><td style="padding:20px 32px 30px">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#fff6e8;border-radius:12px"><tr><td style="padding:14px 16px;font-size:13px;line-height:1.55;color:#8a4b00">
      <b>Segurança.</b> A chave é exibida uma única vez e não fica gravada em nossos servidores: guardamos apenas o hash SHA-256. Não a compartilhe nem a publique em código. Em caso de vazamento, solicite a revogação e uma nova chave.
    </td></tr></table>
  </td></tr>
  <tr><td style="background:#f6f6f8;padding:18px 32px;border-top:1px solid #ececf0">
    <p style="margin:0;font-size:12px;line-height:1.6;color:#86868b">Equipe Avaliador Imobiliário · Avaliação automatizada de imóveis em King County (WA), com base em 21.613 vendas reais.<br>Mensagem automática enviada na emissão da chave. Valores em dólares americanos (USD).</p>
    <p style="margin:10px 0 0;font-family:Georgia,'Times New Roman',serif;font-style:italic;font-size:13px;color:#6e6e73">© 2026 Ricardo Pasquali dos Reis · todos os direitos reservados</p>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""
    msg.set_content(texto)
    msg.add_alternative(corpo_html, subtype="html")
    # Logo embutido no próprio e-mail (Content-ID): aparece mesmo com imagens externas bloqueadas
    logo = PASTA_WEB / "assets" / "logo_email.png"
    if logo.exists():
        msg.get_payload()[1].add_related(logo.read_bytes(), maintype="image", subtype="png",
                                         cid=cid_logo, filename="logo.png")
    return msg


def _salvar_eml(msg: EmailMessage, pasta: Path, sufixo: str) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{datetime.now():%Y%m%d-%H%M%S}-{sufixo}.eml"
    arquivo.write_bytes(bytes(msg))
    return arquivo


def _copia_mascarada(msg: EmailMessage, chave: str, prefixo: str) -> EmailMessage:
    """Cópia do e-mail para o disco: a chave completa nunca é gravada, só o prefixo."""
    copia = copy.deepcopy(msg)
    for parte in copia.walk():
        if parte.get_content_maintype() == "text":
            parte.set_content(parte.get_content().replace(chave, f"{prefixo}… (oculta)"),
                              subtype=parte.get_content_subtype())
    return copia


def enviar(msg: EmailMessage, pasta: Path, sufixo: str, chave: str, prefixo: str) -> dict:
    """Tenta o SMTP; se não houver configuração ou falhar, salva o .eml."""
    usuario, senha = obter("SMTP_USUARIO"), obter("SMTP_SENHA_APP")
    if usuario and senha:
        try:
            with smtplib.SMTP(obter("SMTP_HOST", "smtp.gmail.com"), int(obter("SMTP_PORTA", "587")), timeout=20) as smtp:
                smtp.starttls()
                smtp.login(usuario, senha)
                smtp.send_message(msg)
            arquivo = _salvar_eml(_copia_mascarada(msg, chave, prefixo), pasta, sufixo)
            return {"enviado": True, "modo": "smtp", "status": "enviado", "arquivo": str(arquivo),
                    "mensagem": f"E-mail enviado para {msg['To']} pelo SMTP."}
        except Exception as exc:  # o motivo vai sem dados sensíveis
            motivo = type(exc).__name__
            if isinstance(exc, smtplib.SMTPResponseException):
                motivo += f" (código {exc.smtp_code})"
            log.warning("Falha no envio SMTP: %s", motivo)
            arquivo = _salvar_eml(_copia_mascarada(msg, chave, prefixo), pasta, sufixo)
            return {"enviado": False, "modo": "arquivo", "status": f"falha_smtp: {motivo}", "arquivo": str(arquivo),
                    "mensagem": f"O SMTP falhou ({motivo}); a mensagem foi salva em .eml, com a chave oculta; entregue ao cliente a chave exibida no console."}
    arquivo = _salvar_eml(_copia_mascarada(msg, chave, prefixo), pasta, sufixo)
    return {"enviado": False, "modo": "arquivo", "status": "salvo_em_arquivo", "arquivo": str(arquivo),
            "mensagem": "SMTP não configurado no .env; a mensagem foi salva em .eml, com a chave oculta; entregue ao cliente a chave exibida no console."}
