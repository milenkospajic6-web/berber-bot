"""
Konfiguracija Berber Bota.

VAZNO: Ne stavljaj BOT_TOKEN u ovaj fajl!
Postavi ga kao environment varijablu na Railway:
  BOT_TOKEN = tvoj_token_ovde
  VLASNIK_ID = tvoj_telegram_id
"""

import os


class Config:
    # ─── OBAVEZNO PODESITI ───────────────────────────────────────

    # Tvoj Telegram BOT token (od @BotFather)
    # Postavi kao environment varijablu BOT_TOKEN na Railway
    BOT_TOKEN: str = os.environ.get("BOT_TOKEN", "")

    # Tvoj licni Telegram ID (da dobijes notifikacije)
    # Kako da nadjes svoj ID: pisi @userinfobot u Telegramu
    VLASNIK_TELEGRAM_ID: int = int(os.environ.get("VLASNIK_ID", "0"))

    # ─── LOKACIJE ────────────────────────────────────────────────

    # Koji dani si u kojoj lokaciji
    # 0=pon, 1=uto, 2=sre, 3=cet, 4=pet, 5=sub, 6=ned
    LOKACIJE = {
        0: "Novi Sad",   # Ponedeljak
        1: "Novi Sad",   # Utorak
        2: "Novi Sad",   # Sreda
        3: "Sid",        # Cetvrtak
        4: "Sid",        # Petak
        5: "Sid",        # Subota
        6: "Novi Sad",   # Nedelja (moze se promeniti)
    }

    # ─── RADNO VREME ─────────────────────────────────────────────

    # Pocetak radnog vremena (sat)
    RADNO_OD: int = 8

    # Kraj radnog vremena — poslednji termin u HH:MM
    RADNO_DO: int = 20  # Do 19:30 (poslednji termin)

    # Trajanje termina u minutima
    TRAJANJE_MIN: int = 30

    # ─── USLUGE ──────────────────────────────────────────────────

    USLUGE = [
        "Sisanje",
        "Brada",
        "Sisanje + brada",
    ]

    # ─── PORUKE ──────────────────────────────────────────────────

    DOBRODOSLI = (
        "Dobrodosao! Izaberi akciju 👇"
    )
