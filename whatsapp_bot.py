"""
WhatsApp Bot za berbernicu - Green API
Radi paralelno sa Telegram botom, ista baza podataka.
"""

import os
import json
import logging
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import date, timedelta
import re
import threading

from database import Database
from config import Config

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

db = Database()
config = Config()

GREEN_API_URL = os.environ.get("GREEN_API_URL", "https://7107.api.greenapi.com")
INSTANCE_ID   = os.environ.get("INSTANCE_ID", "")
API_TOKEN     = os.environ.get("API_TOKEN", "")

# Stanje konverzacije po broju
sesije = {}


# ─── POMOCNE FUNKCIJE ───────────────────────────────────────────

def get_lokacija_za_datum(datum: date) -> str:
    dan = datum.weekday()
    if dan in [0, 1, 2]:
        return "Novi Sad"
    elif dan in [3, 4, 5]:
        return "Sid"
    else:
        return "Novi Sad"

def format_datum(d: date) -> str:
    dani = ["Ponedeljak", "Utorak", "Sreda", "Cetvrtak", "Petak", "Subota", "Nedelja"]
    meseci = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "avg", "sep", "okt", "nov", "dec"]
    return f"{dani[d.weekday()]}, {d.day}. {meseci[d.month-1]}"

def get_sledeci_dani(n=7):
    dani = []
    d = date.today()
    for _ in range(n):
        dani.append(d)
        d += timedelta(days=1)
    return dani

def parse_vreme(tekst: str):
    tekst = tekst.strip().replace("h", ":00").replace("H", ":00")
    m = re.match(r'^(\d{1,2})(?::(\d{2}))?$', tekst)
    if m:
        sat = int(m.group(1))
        minut = int(m.group(2) or 0)
        if 8 <= sat <= 19 and minut in [0, 30]:
            return f"{sat:02d}:{minut:02d}"
    return None

def get_slobodni_termini(datum: date):
    zauzeti = db.get_termini_za_datum(datum)
    zauzeta = {t['vreme'] for t in zauzeti}
    fiksni = db.get_fiksni_termini_za_dan(datum.weekday())
    zauzeta.update({f['vreme'] for f in fiksni})
    slobodni = []
    for sat in range(8, 20):
        for minut in [0, 30]:
            v = f"{sat:02d}:{minut:02d}"
            if v not in zauzeta:
                slobodni.append(v)
    return slobodni


# ─── GREEN API SLANJE ────────────────────────────────────────────

def posalji_poruku(telefon: str, tekst: str):
    """Salje WhatsApp poruku korisniku."""
    url = f"{GREEN_API_URL}/waInstance{INSTANCE_ID}/sendMessage/{API_TOKEN}"
    payload = {
        "chatId": f"{telefon}@c.us",
        "message": tekst
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        logger.info(f"Poslato {telefon}: {r.status_code}")
    except Exception as e:
        logger.error(f"Greska slanja: {e}")

def posalji_vlasniku(tekst: str):
    """Salje notifikaciju vlasniku."""
    vlasnik = os.environ.get("VLASNIK_TELEFON", "")
    if vlasnik:
        posalji_poruku(vlasnik, tekst)


# ─── LOGIKA RAZGOVORA ────────────────────────────────────────────

def obradi_poruku(telefon: str, tekst: str):
    """Glavna funkcija — obradjuje svaku poruku."""
    tekst = tekst.strip()
    sesija = sesije.get(telefon, {"korak": "start"})

    # Reset uvek dostupan
    if tekst.lower() in ["meni", "start", "pocetak", "0", "/start"]:
        sesije[telefon] = {"korak": "start"}
        posalji_poruku(telefon, meni_tekst())
        return

    korak = sesija.get("korak", "start")

    if korak == "start":
        obradi_start(telefon, tekst, sesija)

    elif korak == "unos_imena":
        obradi_ime(telefon, tekst, sesija)

    elif korak == "izbor_datuma":
        obradi_datum(telefon, tekst, sesija)

    elif korak == "izbor_vremena":
        obradi_vreme(telefon, tekst, sesija)

    elif korak == "izbor_usluge":
        obradi_uslugu(telefon, tekst, sesija)

    elif korak == "potvrda":
        obradi_potvrdu(telefon, tekst, sesija)

    elif korak == "otkazivanje":
        obradi_otkazivanje(telefon, tekst, sesija)

    else:
        sesije[telefon] = {"korak": "start"}
        posalji_poruku(telefon, meni_tekst())


def meni_tekst():
    return (
        "✂️ *Berber Ivan* — Zakazivanje\n\n"
        "Izaberite opciju:\n\n"
        "1️⃣ Zakazi termin\n"
        "2️⃣ Otkazi termin\n"
        "3️⃣ Moji termini\n"
        "4️⃣ Radno vreme\n\n"
        "Posaljite broj (1-4)"
    )


def obradi_start(telefon, tekst, sesija):
    if tekst == "1" or "zakaz" in tekst.lower():
        sesije[telefon] = {"korak": "unos_imena"}
        posalji_poruku(telefon, "Kako se zovete? Unesite ime i prezime:")

    elif tekst == "2" or "otkaz" in tekst.lower():
        termini = db.get_termini_korisnika_telefon(telefon)
        if not termini:
            posalji_poruku(telefon, "Nemate zakazanih termina. 📭")
            return
        odgovor = "Vasi termini:\n\n"
        for i, t in enumerate(termini, 1):
            d = date.fromisoformat(t['datum'])
            odgovor += f"{i}. {format_datum(d)} u {t['vreme']} — {t['usluga']}\n"
        odgovor += "\nUnesite broj termina koji zelite da otkazete:"
        sesije[telefon] = {"korak": "otkazivanje", "termini": termini}
        posalji_poruku(telefon, odgovor)

    elif tekst == "3" or "moji" in tekst.lower():
        termini = db.get_termini_korisnika_telefon(telefon)
        if not termini:
            posalji_poruku(telefon, "Nemate zakazanih termina. 📭")
        else:
            odgovor = "📅 Vasi nadolazeci termini:\n\n"
            for t in termini:
                d = date.fromisoformat(t['datum'])
                odgovor += f"• {format_datum(d)} u {t['vreme']}\n"
                odgovor += f"  📍 {t['lokacija']} | ✂️ {t['usluga']}\n\n"
            posalji_poruku(telefon, odgovor)

    elif tekst == "4" or "radno" in tekst.lower():
        posalji_poruku(telefon,
            "🕐 Radno vreme:\n\n"
            "📍 Novi Sad — Nedelja do Sreda\n"
            "📍 Sid — Cetvrtak do Nedelja\n\n"
            "⏰ 08:00 – 19:30\n"
            "⏱️ Trajanje: 30 minuta"
        )
    else:
        posalji_poruku(telefon, meni_tekst())


def obradi_ime(telefon, tekst, sesija):
    if len(tekst) < 3:
        posalji_poruku(telefon, "Molimo unesite ime i prezime (min 3 karaktera):")
        return

    sesija["ime"] = tekst
    dani = get_sledeci_dani(7)
    sesija["dani"] = [d.isoformat() for d in dani]
    sesije[telefon] = {**sesija, "korak": "izbor_datuma"}

    odgovor = f"Hvala, {tekst}! 👋\n\nIzaberite datum:\n\n"
    for i, d in enumerate(dani, 1):
        lok = get_lokacija_za_datum(d)
        odgovor += f"{i}. {format_datum(d)} — 📍 {lok}\n"
    odgovor += "\nUnesite broj datuma:"
    posalji_poruku(telefon, odgovor)


def obradi_datum(telefon, tekst, sesija):
    dani_iso = sesija.get("dani", [])
    try:
        idx = int(tekst) - 1
        if idx < 0 or idx >= len(dani_iso):
            raise ValueError
    except ValueError:
        posalji_poruku(telefon, f"Molimo unesite broj od 1 do {len(dani_iso)}:")
        return

    datum = date.fromisoformat(dani_iso[idx])
    lokacija = get_lokacija_za_datum(datum)
    slobodni = get_slobodni_termini(datum)

    if not slobodni:
        posalji_poruku(telefon, f"Nema slobodnih termina za {format_datum(datum)}. Izaberite drugi datum.")
        return

    sesija["datum"] = datum.isoformat()
    sesija["lokacija"] = lokacija
    sesija["slobodni"] = slobodni
    sesije[telefon] = {**sesija, "korak": "izbor_vremena"}

    odgovor = f"📅 {format_datum(datum)}\n📍 {lokacija}\n\nSlobodni termini:\n\n"
    for i, v in enumerate(slobodni, 1):
        odgovor += f"{i}. {v}\n"
    odgovor += "\nUnesite broj termina ili direktno vreme (npr. 10:00):"
    posalji_poruku(telefon, odgovor)


def obradi_vreme(telefon, tekst, sesija):
    slobodni = sesija.get("slobodni", [])
    datum = date.fromisoformat(sesija["datum"])
    vreme = None

    # Pokusaj broj sa liste
    try:
        idx = int(tekst) - 1
        if 0 <= idx < len(slobodni):
            vreme = slobodni[idx]
    except ValueError:
        vreme = parse_vreme(tekst)

    if not vreme:
        posalji_poruku(telefon, "Molimo unesite broj ili vreme sa liste (npr. 10:00):")
        return

    if db.je_termin_zauzet(datum, vreme):
        slobodni_novi = get_slobodni_termini(datum)
        sesija["slobodni"] = slobodni_novi
        sesije[telefon] = sesija
        odgovor = f"⚠️ Termin {vreme} je upravo zauzet!\n\nSlobodni termini:\n\n"
        for i, v in enumerate(slobodni_novi, 1):
            odgovor += f"{i}. {v}\n"
        posalji_poruku(telefon, odgovor)
        return

    sesija["vreme"] = vreme
    sesije[telefon] = {**sesija, "korak": "izbor_usluge"}
    posalji_poruku(telefon,
        "Koja usluga?\n\n"
        "1. Sisanje\n"
        "2. Brada\n"
        "3. Sisanje + brada\n\n"
        "Unesite broj:"
    )


def obradi_uslugu(telefon, tekst, sesija):
    usluge = {"1": "Sisanje", "2": "Brada", "3": "Sisanje + brada"}
    usluga = usluge.get(tekst.strip())

    if not usluga:
        # Pokusaj prepoznati tekst
        t = tekst.lower()
        if "brada" in t and "sisan" in t:
            usluga = "Sisanje + brada"
        elif "brada" in t:
            usluga = "Brada"
        elif "sisan" in t:
            usluga = "Sisanje"

    if not usluga:
        posalji_poruku(telefon, "Molimo unesite 1, 2 ili 3:")
        return

    sesija["usluga"] = usluga
    sesije[telefon] = {**sesija, "korak": "potvrda"}

    datum = date.fromisoformat(sesija["datum"])
    posalji_poruku(telefon,
        f"Proverite podatke:\n\n"
        f"👤 {sesija['ime']}\n"
        f"📅 {format_datum(datum)} u {sesija['vreme']}\n"
        f"📍 {sesija['lokacija']}\n"
        f"✂️ {usluga}\n\n"
        f"Posaljite *DA* za potvrdu ili *NE* za otkaz:"
    )


def obradi_potvrdu(telefon, tekst, sesija):
    t = tekst.lower().strip()

    if t in ["ne", "n", "otkazi", "cancel"]:
        sesije[telefon] = {"korak": "start"}
        posalji_poruku(telefon, "Zakazivanje otkazano.\n\n" + meni_tekst())
        return

    if t not in ["da", "d", "yes", "y", "ok", "ок", "потврди"]:
        posalji_poruku(telefon, "Posaljite DA za potvrdu ili NE za otkaz:")
        return

    datum = date.fromisoformat(sesija["datum"])

    if db.je_termin_zauzet(datum, sesija["vreme"]):
        sesije[telefon] = {"korak": "start"}
        posalji_poruku(telefon, "⚠️ Neko je upravo zauzeo taj termin! Pokrenite zakazivanje ponovo.")
        return

    db.dodaj_termin(
        user_id=0,
        ime=sesija["ime"],
        datum=datum.isoformat(),
        vreme=sesija["vreme"],
        lokacija=sesija["lokacija"],
        usluga=sesija["usluga"],
        telefon=telefon
    )

    sesije[telefon] = {"korak": "start"}
    posalji_poruku(telefon,
        f"✅ Termin zakazan!\n\n"
        f"📅 {format_datum(datum)} u {sesija['vreme']}\n"
        f"📍 {sesija['lokacija']}\n"
        f"✂️ {sesija['usluga']}\n\n"
        f"Vidimo se! Ako treba da otkazete, javite bar dan ranije. 💈"
    )

    posalji_vlasniku(
        f"🔔 NOVO ZAKAZIVANJE (WhatsApp)\n\n"
        f"👤 {sesija['ime']}\n"
        f"📱 {telefon}\n"
        f"📅 {format_datum(datum)} u {sesija['vreme']}\n"
        f"📍 {sesija['lokacija']}\n"
        f"✂️ {sesija['usluga']}"
    )


def obradi_otkazivanje(telefon, tekst, sesija):
    termini = sesija.get("termini", [])
    try:
        idx = int(tekst) - 1
        if idx < 0 or idx >= len(termini):
            raise ValueError
    except ValueError:
        posalji_poruku(telefon, f"Unesite broj od 1 do {len(termini)}:")
        return

    t = termini[idx]
    db.otkazi_termin(t['id'])
    d = date.fromisoformat(t['datum'])

    sesije[telefon] = {"korak": "start"}
    posalji_poruku(telefon,
        f"✅ Termin otkazan.\n\n"
        f"📅 {format_datum(d)} u {t['vreme']}\n\n"
        f"Hvala na javljanju! 🙏"
    )

    posalji_vlasniku(
        f"⚠️ OTKAZIVANJE (WhatsApp)\n\n"
        f"👤 {t['ime']}\n"
        f"📱 {telefon}\n"
        f"📅 {format_datum(d)} u {t['vreme']}\n"
        f"📍 {t['lokacija']}\n"
        f"Termin je sada slobodan."
    )


# ─── WEBHOOK SERVER ──────────────────────────────────────────────

class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        self.send_response(200)
        self.end_headers()

        try:
            data = json.loads(body)
            tip = data.get("typeWebhook", "")

            if tip == "incomingMessageReceived":
                sender = data.get("senderData", {})
                poruka_data = data.get("messageData", {})
                telefon = sender.get("sender", "").replace("@c.us", "")
                tip_poruke = poruka_data.get("typeMessage", "")

                if tip_poruke == "textMessage":
                    tekst = poruka_data.get("textMessageData", {}).get("textMessage", "")
                    if tekst and telefon:
                        logger.info(f"Poruka od {telefon}: {tekst}")
                        threading.Thread(
                            target=obradi_poruku,
                            args=(telefon, tekst),
                            daemon=True
                        ).start()
        except Exception as e:
            logger.error(f"Greska webhook: {e}")

    def log_message(self, format, *args):
        pass  # Iskljuci default HTTP logove


def pokreni_webhook():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), WebhookHandler)
    logger.info(f"WhatsApp webhook server pokrenut na portu {port}")

    # Registruj webhook kod Green API
    webhook_url = os.environ.get("WEBHOOK_URL", "")
    if webhook_url:
        try:
            url = f"{GREEN_API_URL}/waInstance{INSTANCE_ID}/setSettings/{API_TOKEN}"
            requests.post(url, json={"webhookUrl": webhook_url}, timeout=10)
            logger.info(f"Webhook registrovan: {webhook_url}")
        except Exception as e:
            logger.error(f"Greska registracije webhooks: {e}")

    server.serve_forever()


if __name__ == "__main__":
    pokreni_webhook()
