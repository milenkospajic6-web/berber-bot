"""
Berber Bot - Telegram bot za zakazivanje termina
Lokacije: Novi Sad (ned-sre) i Sid (cet-ned)
"""

import logging
import os
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)
from datetime import datetime, date, timedelta
import re

from database import Database
from config import Config

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Stanja konverzacije
(
    IZBOR_AKCIJE,
    UNOS_IMENA,
    IZBOR_LOKACIJE,
    IZBOR_DATUMA,
    IZBOR_VREMENA,
    IZBOR_USLUGE,
    POTVRDA,
    OTKAZIVANJE_TERMIN,
) = range(8)

db = Database()
config = Config()


# ─── POMOCNE FUNKCIJE ───────────────────────────────────────────

def get_lokacija_za_datum(datum: date) -> str:
    """Vraca lokaciju na osnovu dana u nedelji."""
    dan = datum.weekday()  # 0=pon, 1=uto, 2=sre, 3=cet, 4=pet, 5=sub, 6=ned
    # Novi Sad: ned(6), pon(0), uto(1), sre(2)
    # Sid: cet(3), pet(4), sub(5), ned(6)
    # Nedelja je i NS i Sid — u ovom slucaju NS ima prednost, ali moze da se konfigurisu
    if dan in [0, 1, 2]:
        return "Novi Sad"
    elif dan in [3, 4, 5]:
        return "Sid"
    else:  # nedelja
        return "Novi Sad"  # nedelja = Novi Sad po defaultu

def format_datum(d: date) -> str:
    dani = ["Ponedeljak", "Utorak", "Sreda", "Cetvrtak", "Petak", "Subota", "Nedelja"]
    meseci = ["jan", "feb", "mar", "apr", "maj", "jun", "jul", "avg", "sep", "okt", "nov", "dec"]
    return f"{dani[d.weekday()]}, {d.day}. {meseci[d.month-1]} {d.year}"

def get_sledeci_radni_dani(n=7):
    """Vraca sledecih N radnih dana kao listu."""
    dani = []
    d = date.today()
    for _ in range(n * 2):
        dani.append(d)
        d += timedelta(days=1)
        if len(dani) == n:
            break
    return dani

def parse_vreme(tekst: str) -> str | None:
    """Parsira vreme iz teksta korisnika."""
    tekst = tekst.strip().replace("h", ":00").replace("H", ":00")
    # Format: "14", "14:00", "14:30"
    m = re.match(r'^(\d{1,2})(?::(\d{2}))?$', tekst)
    if m:
        sat = int(m.group(1))
        minut = int(m.group(2) or 0)
        if 8 <= sat <= 19 and minut in [0, 30]:
            return f"{sat:02d}:{minut:02d}"
    return None

def get_slobodni_termini(datum: date) -> list[str]:
    """Vraca listu slobodnih termina za dati datum."""
    zauzeti = db.get_termini_za_datum(datum)
    zauzeta_vremena = {t['vreme'] for t in zauzeti}
    fiksni = db.get_fiksni_termini_za_dan(datum.weekday())
    zauzeta_vremena.update({f['vreme'] for f in fiksni})

    slobodni = []
    for sat in range(8, 20):
        for minut in [0, 30]:
            v = f"{sat:02d}:{minut:02d}"
            if v not in zauzeta_vremena:
                slobodni.append(v)
    return slobodni

def keyboard_dani():
    """Pravi keyboard sa sledecih 7 dana."""
    dani = get_sledeci_radni_dani(7)
    buttons = []
    row = []
    for d in dani:
        label = f"{format_datum(d)[:3]} {d.day}.{d.month}"
        row.append(label)
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append(["Otkazi"])
    return buttons, dani

def keyboard_termini(slobodni: list[str]):
    """Pravi keyboard sa slobodnim terminima."""
    buttons = []
    row = []
    for v in slobodni:
        row.append(v)
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append(["Otkazi"])
    return buttons


# ─── HANDLERS ───────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pocetna poruka."""
    ime = update.effective_user.first_name or "druze"
    keyboard = [
        ["✂️ Zakazi termin"],
        ["❌ Otkazi termin"],
        ["📅 Moji termini"],
        ["ℹ️ Radno vreme"],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        f"Zdravo {ime}! 👋\n\n"
        "Dobrodosao u berberski salon.\n"
        "Sta zelite da uradite?",
        reply_markup=reply_markup
    )
    return IZBOR_AKCIJE


async def izbor_akcije(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tekst = update.message.text

    if "Zakazi" in tekst:
        await update.message.reply_text(
            "Kako se zovete? Unesite ime i prezime:",
            reply_markup=ReplyKeyboardRemove()
        )
        return UNOS_IMENA

    elif "Otkazi" in tekst:
        user_id = update.effective_user.id
        termini = db.get_termini_korisnika(user_id)
        if not termini:
            await update.message.reply_text(
                "Nemate zakazanih termina.",
                reply_markup=ReplyKeyboardMarkup([["Pocetni meni"]], resize_keyboard=True)
            )
            return IZBOR_AKCIJE

        tekst_termina = "Vasi zakazani termini:\n\n"
        buttons = []
        for i, t in enumerate(termini, 1):
            d = date.fromisoformat(t['datum'])
            tekst_termina += f"{i}. {format_datum(d)} u {t['vreme']} ({t['lokacija']}) — {t['usluga']}\n"
            buttons.append([f"Otkazi: {format_datum(d)} {t['vreme']}"])
        buttons.append(["Nazad"])

        context.user_data['termini_za_otkazivanje'] = termini
        await update.message.reply_text(
            tekst_termina + "\nKoji termin zelite da otkazete?",
            reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
        )
        return OTKAZIVANJE_TERMIN

    elif "Moji termini" in tekst:
        user_id = update.effective_user.id
        termini = db.get_termini_korisnika(user_id)
        if not termini:
            await update.message.reply_text("Nemate zakazanih termina. 📭")
        else:
            odgovor = "📅 Vasi nadolazeci termini:\n\n"
            for t in termini:
                d = date.fromisoformat(t['datum'])
                odgovor += f"• {format_datum(d)} u {t['vreme']}\n"
                odgovor += f"  📍 {t['lokacija']} | ✂️ {t['usluga']}\n\n"
            await update.message.reply_text(odgovor)
        return IZBOR_AKCIJE

    elif "Radno vreme" in tekst:
        await update.message.reply_text(
            "🕐 Radno vreme:\n\n"
            "📍 Novi Sad — Nedelja do Sreda\n"
            "📍 Sid — Cetvrtak do Nedelja\n\n"
            "⏰ Termini: 08:00 – 19:30\n"
            "⏱️ Trajanje: 30 minuta\n\n"
            "Za zakazivanje koristite dugme ispod. 👇"
        )
        return IZBOR_AKCIJE

    elif "Pocetni" in tekst:
        return await start(update, context)

    return IZBOR_AKCIJE


async def unos_imena(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ime = update.message.text.strip()
    if len(ime) < 3:
        await update.message.reply_text("Molimo unesite ime i prezime (min 3 karaktera):")
        return UNOS_IMENA

    context.user_data['ime'] = ime

    # Prikaz sledecih 7 dana sa lokacijom
    dani = get_sledeci_radni_dani(7)
    buttons = []
    row = []
    for d in dani:
        lok = get_lokacija_za_datum(d)
        label = f"{d.day}.{d.month}. ({lok[:2]})"
        row.append(label)
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append(["❌ Otkazi"])

    # Cuvamo dane za referencu
    context.user_data['dani_lista'] = [d.isoformat() for d in dani]
    context.user_data['dani_labels'] = [f"{d.day}.{d.month}. ({get_lokacija_za_datum(d)[:2]})" for d in dani]

    legenda = "NS = Novi Sad | Si = Sid\n\n"
    await update.message.reply_text(
        f"Hvala, {ime}! 👋\n\n"
        f"{legenda}"
        "Izaberite datum:",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )
    return IZBOR_DATUMA


async def izbor_datuma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tekst = update.message.text.strip()

    if "Otkazi" in tekst:
        return await start(update, context)

    # Pronadji koji datum je izabran
    labels = context.user_data.get('dani_labels', [])
    dani_iso = context.user_data.get('dani_lista', [])

    odabrani_idx = None
    for i, lbl in enumerate(labels):
        if lbl in tekst or tekst in lbl:
            odabrani_idx = i
            break

    if odabrani_idx is None:
        await update.message.reply_text("Molimo izaberite datum sa liste.")
        return IZBOR_DATUMA

    odabrani_datum = date.fromisoformat(dani_iso[odabrani_idx])
    context.user_data['datum'] = odabrani_datum.isoformat()
    lokacija = get_lokacija_za_datum(odabrani_datum)
    context.user_data['lokacija'] = lokacija

    slobodni = get_slobodni_termini(odabrani_datum)
    if not slobodni:
        await update.message.reply_text(
            f"Nema slobodnih termina za {format_datum(odabrani_datum)}. 😕\n"
            "Izaberite drugi datum."
        )
        return IZBOR_DATUMA

    buttons = keyboard_termini(slobodni)
    await update.message.reply_text(
        f"📅 {format_datum(odabrani_datum)}\n"
        f"📍 Lokacija: {lokacija}\n\n"
        f"Slobodni termini ({len(slobodni)}):\n"
        "Izaberite vreme:",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )
    return IZBOR_VREMENA


async def izbor_vremena(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tekst = update.message.text.strip()

    if "Otkazi" in tekst:
        return await start(update, context)

    vreme = parse_vreme(tekst)
    if not vreme:
        await update.message.reply_text("Molimo izaberite vreme sa liste.")
        return IZBOR_VREMENA

    # Provjeri jos jednom da nije zauzeto (race condition)
    datum = date.fromisoformat(context.user_data['datum'])
    if db.je_termin_zauzet(datum, vreme):
        slobodni = get_slobodni_termini(datum)
        buttons = keyboard_termini(slobodni)
        await update.message.reply_text(
            f"⚠️ Termin {vreme} je upravo zauzet!\n\n"
            "Izaberite drugi termin:",
            reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
        )
        return IZBOR_VREMENA

    context.user_data['vreme'] = vreme

    usluge = [["✂️ Sisanje", "🪒 Brada"],
              ["✂️🪒 Sisanje + brada"],
              ["❌ Otkazi"]]
    await update.message.reply_text(
        "Koja usluga?",
        reply_markup=ReplyKeyboardMarkup(usluge, resize_keyboard=True)
    )
    return IZBOR_USLUGE


async def izbor_usluge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tekst = update.message.text.strip()

    if "Otkazi" in tekst:
        return await start(update, context)

    usluga_map = {
        "Sisanje": "Sisanje",
        "Brada": "Brada",
        "Sisanje + brada": "Sisanje + brada",
    }
    usluga = None
    for k, v in usluga_map.items():
        if k in tekst:
            usluga = v
            break

    if not usluga:
        await update.message.reply_text("Molimo izaberite uslugu sa liste.")
        return IZBOR_USLUGE

    context.user_data['usluga'] = usluga

    datum = date.fromisoformat(context.user_data['datum'])
    ime = context.user_data['ime']
    vreme = context.user_data['vreme']
    lokacija = context.user_data['lokacija']

    potvrda_text = (
        f"Proverite podatke:\n\n"
        f"👤 Ime: {ime}\n"
        f"📅 Datum: {format_datum(datum)}\n"
        f"⏰ Vreme: {vreme}\n"
        f"📍 Lokacija: {lokacija}\n"
        f"✂️ Usluga: {usluga}\n\n"
        "Da li je sve tacno?"
    )

    buttons = [["✅ Potvrdi"], ["❌ Otkazi"]]
    await update.message.reply_text(
        potvrda_text,
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )
    return POTVRDA


async def potvrda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tekst = update.message.text.strip()

    if "Otkazi" in tekst or "❌" in tekst:
        await update.message.reply_text("Zakazivanje otkazano.")
        return await start(update, context)

    if "Potvrdi" not in tekst and "✅" not in tekst:
        return POTVRDA

    user_id = update.effective_user.id
    datum = date.fromisoformat(context.user_data['datum'])
    ime = context.user_data['ime']
    vreme = context.user_data['vreme']
    lokacija = context.user_data['lokacija']
    usluga = context.user_data['usluga']

    # Finalna provjera duplikata
    if db.je_termin_zauzet(datum, vreme):
        slobodni = get_slobodni_termini(datum)
        await update.message.reply_text(
            f"⚠️ Neko je upravo zauzeo termin {vreme}!\n"
            "Molimo pokrenite zakazivanje ponovo i izaberite drugi termin."
        )
        return await start(update, context)

    # Sacuvaj termin
    db.dodaj_termin(
        user_id=user_id,
        ime=ime,
        datum=datum.isoformat(),
        vreme=vreme,
        lokacija=lokacija,
        usluga=usluga
    )

    # Potvrda korisniku
    await update.message.reply_text(
        f"✅ Termin zakazan!\n\n"
        f"📅 {format_datum(datum)} u {vreme}\n"
        f"📍 {lokacija}\n"
        f"✂️ {usluga}\n\n"
        f"Vidimo se! Ako treba da otkazete, javite bar dan ranije. 💈",
        reply_markup=ReplyKeyboardMarkup([["📅 Moji termini"], ["✂️ Zakazi termin"]], resize_keyboard=True)
    )

    # Notifikacija vlasniku
    await posalji_notifikaciju_vlasniku(
        context,
        f"🔔 NOVO ZAKAZIVANJE\n\n"
        f"👤 {ime}\n"
        f"📅 {format_datum(datum)} u {vreme}\n"
        f"📍 {lokacija}\n"
        f"✂️ {usluga}"
    )

    context.user_data.clear()
    return IZBOR_AKCIJE


async def otkazivanje_termin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tekst = update.message.text.strip()

    if "Nazad" in tekst:
        return await start(update, context)

    termini = context.user_data.get('termini_za_otkazivanje', [])
    odabrani = None
    for t in termini:
        d = date.fromisoformat(t['datum'])
        label = f"Otkazi: {format_datum(d)} {t['vreme']}"
        if label in tekst:
            odabrani = t
            break

    if not odabrani:
        await update.message.reply_text("Molimo izaberite termin sa liste.")
        return OTKAZIVANJE_TERMIN

    db.otkazi_termin(odabrani['id'])

    d = date.fromisoformat(odabrani['datum'])
    await update.message.reply_text(
        f"✅ Termin otkazan.\n\n"
        f"📅 {format_datum(d)} u {odabrani['vreme']} ({odabrani['lokacija']})\n\n"
        "Hvala na javljanju! 🙏",
        reply_markup=ReplyKeyboardMarkup([["✂️ Zakazi termin"], ["📅 Moji termini"]], resize_keyboard=True)
    )

    # Notifikacija vlasniku
    await posalji_notifikaciju_vlasniku(
        context,
        f"⚠️ OTKAZIVANJE!\n\n"
        f"👤 {odabrani['ime']}\n"
        f"📅 {format_datum(d)} u {odabrani['vreme']}\n"
        f"📍 {odabrani['lokacija']}\n"
        f"Termin je sada slobodan."
    )

    return IZBOR_AKCIJE


async def posalji_notifikaciju_vlasniku(context, poruka: str):
    """Salje notifikaciju vlasniku na njegov Telegram ID."""
    vlasnik_id = config.VLASNIK_TELEGRAM_ID
    if vlasnik_id:
        try:
            await context.bot.send_message(chat_id=vlasnik_id, text=poruka)
        except Exception as e:
            logger.error(f"Greska pri slanju notifikacije vlasniku: {e}")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Akcija otkazana.")
    return await start(update, context)


async def admin_pregled(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin komanda — samo za vlasnika."""
    if update.effective_user.id != config.VLASNIK_TELEGRAM_ID:
        await update.message.reply_text("Nemate pristup ovoj komandi.")
        return

    danas = date.today()
    termini = db.get_termini_za_datum(danas)
    fiksni = db.get_fiksni_termini_za_dan(danas.weekday())

    if not termini and not fiksni:
        await update.message.reply_text(f"📅 Danas ({format_datum(danas)}) nema zakazanih termina.")
        return

    odgovor = f"📅 Termini za danas — {format_datum(danas)}\n"
    odgovor += f"📍 Lokacija: {get_lokacija_za_datum(danas)}\n\n"

    svi = []
    for t in termini:
        svi.append((t['vreme'], t['ime'], t['usluga'], False))
    for f in fiksni:
        svi.append((f['vreme'], f['ime'], f['usluga'], True))
    svi.sort(key=lambda x: x[0])

    for vreme, ime, usluga, je_fiksni in svi:
        marker = "🔒" if je_fiksni else "✅"
        odgovor += f"{marker} {vreme} — {ime} ({usluga})\n"

    await update.message.reply_text(odgovor)


async def admin_sutra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pregled sutra — samo za vlasnika."""
    if update.effective_user.id != config.VLASNIK_TELEGRAM_ID:
        return

    sutra = date.today() + timedelta(days=1)
    termini = db.get_termini_za_datum(sutra)
    fiksni = db.get_fiksni_termini_za_dan(sutra.weekday())

    odgovor = f"📅 Termini za sutra — {format_datum(sutra)}\n"
    odgovor += f"📍 Lokacija: {get_lokacija_za_datum(sutra)}\n\n"

    svi = []
    for t in termini:
        svi.append((t['vreme'], t['ime'], t['usluga'], False))
    for f in fiksni:
        svi.append((f['vreme'], f['ime'], f['usluga'], True))
    svi.sort(key=lambda x: x[0])

    if not svi:
        odgovor += "Nema zakazanih termina."
    else:
        for vreme, ime, usluga, je_fiksni in svi:
            marker = "🔒" if je_fiksni else "✅"
            odgovor += f"{marker} {vreme} — {ime} ({usluga})\n"

    await update.message.reply_text(odgovor)


async def admin_fiksni(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pregled svih fiksnih termina."""
    if update.effective_user.id != config.VLASNIK_TELEGRAM_ID:
        return

    fiksni = db.get_svi_fiksni_termini()
    dani_names = ["Ponedeljak", "Utorak", "Sreda", "Cetvrtak", "Petak", "Subota", "Nedelja"]

    if not fiksni:
        await update.message.reply_text("Nema fiksnih termina.")
        return

    odgovor = "🔒 Fiksni termini:\n\n"
    for f in fiksni:
        odgovor += f"• {dani_names[f['dan_nedelje']]} {f['vreme']} — {f['ime']} ({f['lokacija']}) | {f['usluga']}\n"
        odgovor += f"  ID: {f['id']}\n"

    odgovor += "\nDa dodas fiksni: /dodaj_fiksni\nDa obrises: /obrisi_fiksni [ID]"
    await update.message.reply_text(odgovor)


async def admin_dodaj_fiksni(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Dodaje fiksni termin. Upotreba: /dodaj_fiksni Ime Prezime ponedeljak 10:00 sisanje"""
    if update.effective_user.id != config.VLASNIK_TELEGRAM_ID:
        return

    args = context.args
    if len(args) < 4:
        await update.message.reply_text(
            "Upotreba: /dodaj_fiksni <ime> <dan> <vreme> <usluga>\n\n"
            "Primer: /dodaj_fiksni 'Pera Peric' ponedeljak 10:00 sisanje\n"
            "Dani: ponedeljak, utorak, sreda, cetvrtak, petak, subota, nedelja"
        )
        return

    ime = args[0]
    dan_tekst = args[1].lower()
    vreme_tekst = args[2]
    usluga = " ".join(args[3:])

    dani_map = {
        "ponedeljak": 0, "utorak": 1, "sreda": 2,
        "cetvrtak": 3, "petak": 4, "subota": 5, "nedelja": 6
    }

    dan_idx = dani_map.get(dan_tekst)
    if dan_idx is None:
        await update.message.reply_text(f"Nepoznat dan: {dan_tekst}")
        return

    vreme = parse_vreme(vreme_tekst)
    if not vreme:
        await update.message.reply_text(f"Neispravno vreme: {vreme_tekst} (npr. 10:00 ili 10:30)")
        return

    # Lokacija se odredjuje automatski po danu
    temp_datum = date.today()
    while temp_datum.weekday() != dan_idx:
        temp_datum += timedelta(days=1)
    lokacija = get_lokacija_za_datum(temp_datum)

    db.dodaj_fiksni_termin(ime=ime, dan_nedelje=dan_idx, vreme=vreme, lokacija=lokacija, usluga=usluga)

    dani_names = ["Ponedeljak", "Utorak", "Sreda", "Cetvrtak", "Petak", "Subota", "Nedelja"]
    await update.message.reply_text(
        f"✅ Fiksni termin dodat!\n\n"
        f"👤 {ime}\n"
        f"📅 Svaki {dani_names[dan_idx]} u {vreme}\n"
        f"📍 {lokacija}\n"
        f"✂️ {usluga}"
    )


async def admin_obrisi_fiksni(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Brise fiksni termin po ID-u. Upotreba: /obrisi_fiksni 3"""
    if update.effective_user.id != config.VLASNIK_TELEGRAM_ID:
        return

    if not context.args:
        await update.message.reply_text("Upotreba: /obrisi_fiksni <ID>\nID vidis u /fiksni")
        return

    try:
        fiksni_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID mora biti broj.")
        return

    db.obrisi_fiksni_termin(fiksni_id)
    await update.message.reply_text(f"✅ Fiksni termin #{fiksni_id} obrisan.")


async def admin_otkazi_termin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin otkazuje termin po ID-u. Upotreba: /otkazi_admin 5"""
    if update.effective_user.id != config.VLASNIK_TELEGRAM_ID:
        return

    if not context.args:
        await update.message.reply_text("Upotreba: /otkazi_admin <ID>")
        return

    try:
        termin_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID mora biti broj.")
        return

    termin = db.get_termin_po_id(termin_id)
    if not termin:
        await update.message.reply_text(f"Termin #{termin_id} nije nadjen.")
        return

    db.otkazi_termin(termin_id)
    d = date.fromisoformat(termin['datum'])

    # Obavesti musturiju
    try:
        await context.bot.send_message(
            chat_id=termin['user_id'],
            text=(
                f"⚠️ Vas termin je otkazan od strane berbera.\n\n"
                f"📅 {format_datum(d)} u {termin['vreme']}\n"
                f"📍 {termin['lokacija']}\n\n"
                "Izvinjavamo se na neugodnosti. Mozete zakazati novi termin. 🙏"
            )
        )
    except Exception:
        pass

    await update.message.reply_text(
        f"✅ Termin #{termin_id} otkazan.\n"
        f"Musterija ({termin['ime']}) je obavestena."
    )


async def pomoc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prikaz komandi."""
    je_vlasnik = update.effective_user.id == config.VLASNIK_TELEGRAM_ID
    tekst = (
        "📋 Dostupne komande:\n\n"
        "/start — Pocetni meni\n"
        "/pomoc — Ova poruka\n\n"
    )
    if je_vlasnik:
        tekst += (
            "👑 Admin komande:\n"
            "/danas — Termini za danas\n"
            "/sutra — Termini za sutra\n"
            "/fiksni — Svi fiksni termini\n"
            "/dodaj_fiksni <ime> <dan> <vreme> <usluga>\n"
            "/obrisi_fiksni <ID>\n"
            "/otkazi_admin <ID> — Otkazi termin i obavesti musteriju\n"
        )
    await update.message.reply_text(tekst)


# ─── MAIN ───────────────────────────────────────────────────────

def main():
    token = os.environ.get("BOT_TOKEN") or config.BOT_TOKEN
    if not token:
        raise ValueError("BOT_TOKEN nije postavljen!")

    app = Application.builder().token(token).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            MessageHandler(filters.Regex("^(✂️ Zakazi|📅 Moji|❌ Otkazi|ℹ️ Radno|Pocetni)"), izbor_akcije),
        ],
        states={
            IZBOR_AKCIJE: [MessageHandler(filters.TEXT & ~filters.COMMAND, izbor_akcije)],
            UNOS_IMENA: [MessageHandler(filters.TEXT & ~filters.COMMAND, unos_imena)],
            IZBOR_LOKACIJE: [MessageHandler(filters.TEXT & ~filters.COMMAND, izbor_datuma)],
            IZBOR_DATUMA: [MessageHandler(filters.TEXT & ~filters.COMMAND, izbor_datuma)],
            IZBOR_VREMENA: [MessageHandler(filters.TEXT & ~filters.COMMAND, izbor_vremena)],
            IZBOR_USLUGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, izbor_usluge)],
            POTVRDA: [MessageHandler(filters.TEXT & ~filters.COMMAND, potvrda)],
            OTKAZIVANJE_TERMIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, otkazivanje_termin)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)

    # Admin komande
    app.add_handler(CommandHandler("danas", admin_pregled))
    app.add_handler(CommandHandler("sutra", admin_sutra))
    app.add_handler(CommandHandler("fiksni", admin_fiksni))
    app.add_handler(CommandHandler("dodaj_fiksni", admin_dodaj_fiksni))
    app.add_handler(CommandHandler("obrisi_fiksni", admin_obrisi_fiksni))
    app.add_handler(CommandHandler("otkazi_admin", admin_otkazi_termin))
    app.add_handler(CommandHandler("pomoc", pomoc))

    logger.info("Bot pokrenut!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
