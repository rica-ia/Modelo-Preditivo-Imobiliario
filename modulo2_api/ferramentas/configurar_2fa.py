"""
# Configuração do segundo fator (2FA) do console

Gera o segredo TOTP, grava `AVALIADOR_TOTP_SEGREDO` no `.env` da raiz e mostra no
terminal (PowerShell ou WSL) o QR Code para cadastrar no app autenticador do celular
(Google Authenticator, Microsoft Authenticator, Authy etc.). Sem custo e sem serviço
externo: o código de 6 dígitos é calculado no próprio celular e conferido pela API.

Uso, na raiz do repositório:
    python -m modulo2_api.ferramentas.configurar_2fa              # primeira configuração
    python -m modulo2_api.ferramentas.configurar_2fa --novo       # troca o segredo (o celular precisa ler de novo)
    python -m modulo2_api.ferramentas.configurar_2fa --testar     # confere um código do app
    python -m modulo2_api.ferramentas.configurar_2fa --mostrar-qr # mostra de novo o QR do segredo atual

Depois de configurar, reinicie a API para que ela leia o `.env`.
"""

import argparse
import os
import re
import sys
from pathlib import Path

from modulo2_api.app.config import ARQUIVO_ENV, PASTA_MODULO2
from modulo2_api.app.services.acesso import codigo_confere, gerar_segredo, uri_autenticador

VARIAVEL = "AVALIADOR_TOTP_SEGREDO"
PASTA_SAIDA = PASTA_MODULO2 / "saida"


def ler_segredo(env: Path) -> str:
    if not env.exists():
        return ""
    achado = re.search(rf"(?m)^{VARIAVEL}=([^\r\n]*)", env.read_text(encoding="utf-8-sig"))
    return achado.group(1).strip() if achado else ""


def gravar_segredo(env: Path, segredo: str) -> None:
    """Troca (ou acrescenta) só a linha do segredo, preservando as demais e as quebras de linha."""
    texto = env.read_text(encoding="utf-8-sig") if env.exists() else ""
    quebra = "\r\n" if "\r\n" in texto else "\n"
    linha = f"{VARIAVEL}={segredo}"
    if re.search(rf"(?m)^{VARIAVEL}=", texto):
        texto = re.sub(rf"(?m)^{VARIAVEL}=[^\r\n]*", lambda _: linha, texto)
    else:
        texto = texto.rstrip("\r\n") + (quebra if texto else "") + linha + quebra
    env.write_bytes(texto.encode("utf-8"))  # UTF-8 sem BOM


def mostrar_qr(segredo: str, mostrar_chave: bool) -> Path:
    import qrcode
    import qrcode.image.svg

    uri = uri_autenticador(segredo)
    qr = qrcode.QRCode(border=2, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(uri)
    qr.make(fit=True)
    print("\nLeia este QR Code no app autenticador do celular:\n")
    qr.print_ascii(invert=True)
    PASTA_SAIDA.mkdir(parents=True, exist_ok=True)
    svg = PASTA_SAIDA / "qr_2fa_avaliador.svg"
    qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, border=2).save(str(svg))
    print(f"\nSe o QR não couber no terminal, abra a imagem: {svg}")
    print("(a pasta modulo2_api/saida/ fica fora do git; apague a imagem depois de ler)")
    if mostrar_chave:
        print(f"Chave para digitar no app, se preferir: {segredo}")
    return svg


def testar(segredo: str) -> bool:
    codigo = input("\nDigite o código de 6 dígitos que aparece no app: ").strip()
    ok = codigo_confere(segredo, codigo)
    print("Código confere: o segundo fator está funcionando." if ok
          else "Código não confere. Verifique se o relógio do celular está no horário automático.")
    return ok


def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        if hasattr(fluxo, "reconfigure"):
            fluxo.reconfigure(encoding="utf-8")
    if os.name == "nt":
        os.system("")  # liga as sequências de cor/caractere no console do Windows

    parser = argparse.ArgumentParser(description="Configura o segundo fator (2FA) do console do Avaliador Imobiliário.")
    parser.add_argument("--novo", action="store_true", help="gera um segredo novo, substituindo o atual")
    parser.add_argument("--testar", action="store_true", help="confere um código de 6 dígitos do app")
    parser.add_argument("--mostrar-qr", action="store_true", help="mostra o QR do segredo atual")
    parser.add_argument("--mostrar-chave", action="store_true", help="mostra também a chave para digitar no app")
    parser.add_argument("--env", type=Path, default=ARQUIVO_ENV, help="arquivo .env (padrão: .env da raiz)")
    args = parser.parse_args(argv)

    atual = ler_segredo(args.env)
    if args.testar and not (args.novo or args.mostrar_qr):
        if not atual:
            print("O 2FA ainda não está configurado. Rode o comando sem --testar primeiro.")
            return 1
        return 0 if testar(atual) else 1
    if args.mostrar_qr and not args.novo:
        if not atual:
            print("O 2FA ainda não está configurado. Rode o comando sem opções primeiro.")
            return 1
        mostrar_qr(atual, args.mostrar_chave)
        return 0
    if atual and not args.novo:
        print("O 2FA já está configurado neste .env. Use --mostrar-qr para ver o QR de novo,"
              " --testar para conferir um código ou --novo para trocar o segredo.")
        return 1

    segredo = gerar_segredo()
    gravar_segredo(args.env, segredo)
    print(f"Segredo do 2FA gravado em {args.env.name} ({VARIAVEL}).")
    mostrar_qr(segredo, args.mostrar_chave)
    print("\nPróximos passos:")
    print("  1. No app autenticador, toque em '+' e leia o QR Code.")
    print("  2. Reinicie a API para ela ler o .env.")
    print("  3. No portal, entre com a senha de acesso e o código de 6 dígitos do app.")
    if args.testar:
        testar(segredo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
