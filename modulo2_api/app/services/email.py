"""
# E-mail de boas-vindas com a chave de API

Monta a mensagem (texto e HTML, em pt-BR) e envia pelo Gmail com STARTTLS,
usando SMTP_USUARIO e SMTP_SENHA_APP do .env. Sem SMTP configurado, ou se o envio
falhar, a mensagem é salva como .eml para entrega manual. A senha nunca aparece
em log, resposta ou banco.
"""

import html
import logging
import smtplib
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

from ..config import obter

log = logging.getLogger("avaliador")

NOMES_PLANOS = {"basico": "Básico", "profissional": "Profissional", "empresarial": "Empresarial"}


def _url_base() -> str:
    return obter("AVALIADOR_URL_PUBLICA", "http://127.0.0.1:8020").rstrip("/")


def montar_email(nome: str, destinatario: str, chave: str, plano: str, limite: int) -> EmailMessage:
    base = _url_base()
    plano_nome = NOMES_PLANOS.get(plano, plano)
    limite_txt = f"{limite:,}".replace(",", ".")
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
Plano: {plano_nome} · até {limite_txt} predições por mês

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
"""
    e = html.escape
    corpo_html = f"""<!doctype html>
<html lang="pt-BR"><body style="margin:0;background:#f5f5f7;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#1d1d1f">
<div style="max-width:620px;margin:0 auto;padding:32px 20px">
  <div style="background:#fff;border-radius:18px;padding:32px;box-shadow:0 2px 12px rgba(0,0,0,.06)">
    <p style="font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#6e6e73;margin:0 0 8px">Avaliador Imobiliário · API preditiva</p>
    <h1 style="font-size:26px;margin:0 0 16px">Olá, {e(nome)}!</h1>
    <p style="font-size:16px;line-height:1.5">Sua chave de API está pronta. Plano <b>{e(plano_nome)}</b>, com até <b>{limite_txt}</b> predições por mês.</p>
    <div style="background:#f5f5f7;border-radius:12px;padding:16px;margin:20px 0">
      <p style="margin:0 0 6px;font-size:12px;color:#6e6e73">Sua chave (X-API-Key)</p>
      <code style="font-size:15px;word-break:break-all">{e(chave)}</code>
    </div>
    <h2 style="font-size:18px;margin:24px 0 8px">Como usar</h2>
    <ol style="font-size:15px;line-height:1.6;padding-left:20px">
      <li>Envie a chave no cabeçalho <code>X-API-Key</code> de cada requisição.</li>
      <li>Exemplo de chamada:</li>
    </ol>
    <pre style="background:#1d1d1f;color:#f5f5f7;border-radius:12px;padding:16px;font-size:12px;white-space:pre-wrap;word-break:break-all">{e(curl)}</pre>
    <p style="font-size:15px;line-height:1.6">Documentação interativa: <a href="{e(base)}/docs">{e(base)}/docs</a><br>
    Consumo do mês: <code>GET {e(base)}/v1/comercial/uso</code> com o mesmo cabeçalho.</p>
    <p style="font-size:14px;line-height:1.5;background:#fff4e5;border-radius:12px;padding:14px;color:#8a4b00">
      Guarde a chave com segurança: ela é exibida só uma vez e não fica gravada em nossos servidores (guardamos apenas um hash). Em caso de vazamento, peça a revogação e uma nova chave.</p>
  </div>
  <p style="text-align:center;font-size:12px;color:#86868b;margin-top:16px">Avaliador Imobiliário · King County (WA)</p>
</div></body></html>"""
    msg.set_content(texto)
    msg.add_alternative(corpo_html, subtype="html")
    return msg


def _salvar_eml(msg: EmailMessage, pasta: Path, sufixo: str) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{datetime.now():%Y%m%d-%H%M%S}-{sufixo}.eml"
    arquivo.write_bytes(bytes(msg))
    return arquivo


def _copia_mascarada(msg: EmailMessage, chave: str, prefixo: str) -> EmailMessage:
    """Cópia do e-mail para o disco: a chave completa nunca é gravada, só o prefixo."""
    copia = EmailMessage()
    for cabecalho in ("Subject", "From", "To", "Message-ID"):
        if msg[cabecalho]:
            copia[cabecalho] = msg[cabecalho]
    for parte in msg.iter_parts():
        conteudo = parte.get_content().replace(chave, f"{prefixo}… (oculta)")
        if parte.get_content_subtype() == "html":
            copia.add_alternative(conteudo, subtype="html")
        else:
            copia.set_content(conteudo)
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
