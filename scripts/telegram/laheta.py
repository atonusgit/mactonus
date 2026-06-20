#!/usr/bin/env python3
# Lähettää viestin Telegramiin. Tarkoitettu cron-jobien putken loppupääksi:
#   python3 /root/scripts/<jobi>.py | python3 /root/scripts/telegram/laheta.py
# tai suoraan argumentilla:
#   python3 laheta.py "Viesti" [--chat <id>] [--raaka]
#
# Token ja sallitut chatit periytetään kontin pääprosessilta (cron ei peri
# konttiympäristöä) — mitään salaisuutta ei kirjoiteta levylle. Näin yksittäisen
# cron-jobin ei tarvitse käsitellä tokenia tai chat-id:tä itse.

import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from telegram_api import peri_kontin_ymparisto, laheta_viesti, riisu_markdown


def main():
    # Täydennä ympäristö kontin pääprosessilta (cron-konteksti); ei ylikirjoita
    # mahdollisesti jo asetettuja arvoja (esim. interaktiivinen ajo).
    peri_kontin_ymparisto()

    p = argparse.ArgumentParser(description="Lähetä viesti Telegramiin.")
    p.add_argument("viesti", nargs="?",
                   help="Lähetettävä teksti. Jätä pois -> luetaan stdinistä.")
    p.add_argument("--chat", action="append", dest="chatit", metavar="CHAT_ID",
                   help="Kohde-chat-id (voi toistaa). Oletus: TELEGRAM_SALLITUT_CHATIT.")
    p.add_argument("--raaka", action="store_true",
                   help="Älä riisu markdownia ennen lähetystä.")
    args = p.parse_args()

    if not os.environ.get("TELEGRAM_BOT_TOKEN", "").strip():
        sys.exit("TELEGRAM_BOT_TOKEN puuttuu ympäristöstä.")

    teksti = args.viesti if args.viesti is not None else sys.stdin.read()
    teksti = (teksti or "").strip()
    if not teksti:
        sys.exit("Ei lähetettävää tekstiä.")
    if not args.raaka:
        teksti = riisu_markdown(teksti)

    chatit = args.chatit or [
        c.strip() for c in os.environ.get("TELEGRAM_SALLITUT_CHATIT", "").split(",") if c.strip()
    ]
    if not chatit:
        sys.exit("Ei kohde-chatteja (anna --chat tai aseta TELEGRAM_SALLITUT_CHATIT).")

    for chat_id in chatit:
        laheta_viesti(chat_id, teksti)


if __name__ == "__main__":
    main()
