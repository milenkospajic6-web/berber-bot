"""
Berber Bot - Telegram bot za zakazivanje termina
Novi Sad: Pon-Sre 15:00-20:00
Sid: Cet-Sub 09:00-13:00 i 15:00-21:00
Nedelja: Neradna
"""

import logging
import os
import re
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)
from datetime import datetime, date, timedelta

from database import Database
from config import Config

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

(
    IZBOR_AKCIJE,
    UNOS_IMENA,
    IZBOR_DATUMA,
    IZBOR_VREMENA,
    IZBOR_USLUGE,
    POTVRDA,
    OTKAZIVANJE_TERMIN,
) = range(7)

db = Database()
config = Config()


# ─── POMOCNE FUNKCIJE ───────────────────────────────────────────

def get_lokacija(datum: date) -> str:
    dan = datum.weekday()
    if dan in [0, 1, 2]: return "Novi Sad"
    elif dan in [3, 4, 5]: return "Sid"
    else: return None  # Nedelja neradna

def je_radni_dan(datum: date) -> bool:
    return datum.weekday() in [0, 1, 2, 3, 4, 5]

def fmt_datum(d: date) -> str:
    dani = ["Pon","Uto","Sre","Cet","Pet","Sub","Ned"]
    meseci = ["jan","feb","mar","apr","maj","jun","jul","avg","sep","okt","nov","dec"]
    return f"{dani[d.weekday()]} {d.day}. {meseci[d.month-1]}"

def fmt_datum_pun(d: date) -> str:
    dani = ["Ponedeljak","Utorak","Sreda","Cetvrtak","Petak","Subota","Nedelja"]
    meseci = ["jan","feb","mar","apr","maj","jun","jul","avg","sep","okt","nov","dec"]
    return f"{dani[d.weekday()]}, {d.day}. {meseci[d.month-1]}"

def get_termine_za_dan(datum: date) -> list:
    """Vraca sve termine za dati dan prema radnom vremenu."""
    dan = datum.weekday()
    termini = []

    if dan in [0, 1, 2]:
        # Novi Sad: 15:00 - 20:00
        for sat in range(15, 20):
            for minut in [0, 30]:
                termini.append(f"{sat:02d}:{minut:02d}")

    elif dan in [3, 4, 5]:
        # Sid: 09:00-13:00 i 15:00-21:00 (pauza 13-15h)
        for sat in range(9, 13):
            for minut in [0, 30]:
                termini.append(f"{sat:02d}:{minut:02d}")
        for sat in range(15, 21):
            for minut in [0, 30]:
                termini.append(f"{sat:02d}:{minut:02d}")

    return termini

def get_slobodne_termine(datum: date) -> list:
    svi_termini = get_termine_za_dan(datum)
    zauzeti = db.get_termini_za_datum(datum)
    zauzeta = {t['vreme'] for t in zauzeti}
    fiksni = db.get_fiksni_termini_za_dan(datum.weekday())
    zauzeta.update({f['vreme'] for f in fiksni})
    return [v for v in svi_termini if v not in zauzeta]

def get_sledecih_14_radnih_dana() -> list:
    dani = []
    d = date.today()
    while len(dani) < 14:
        if je_radni_dan(d):
            dani.append(d)
        d += timedelta(days=1)
    return dani

def glavni_meni_keyboard():
    return ReplyKeyboardMarkup([
        ["✂️ Zakazi termin"],
        ["❌ Otkazi termin", "📅 Moji termini"],
        ["ℹ️ Info i cene"],
    ], resize_keyboard=True)


# ─── HANDLERS ───────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    ime = update.effective_user.first_name or "druze"
    await update.message.reply_text(
        f"Zdravo {ime}! 👋\n\n"
        "Dobrodosao u berberski salon Ivan.\n"
        "Izaberi opciju:",
        reply_markup=glavni_meni_keyboard()
    )
    return IZBOR_AKCIJE


async def izbor_akcije(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tekst = update.message.text

    if "Zakazi" in tekst:
        await update.message.reply_text(
            "Kako se zovete?\nUnesite ime i prezime:",
            reply_markup=ReplyKeyboardMarkup([["🏠 Pocetni meni"]], resize_keyboard=True)
        )
        return UNOS_IMENA

    elif "Otkazi" in tekst:
        user_id = update.effective_user.id
        termini = db.get_termini_korisnika(user_id)
        if not termini:
            await update.message.reply_text(
                "Nemate zakazanih termina. 📭",
                reply_markup=glavni_meni_keyboard()
            )
            return IZBOR_AKCIJE

        odgovor = "Vasi termini:\n\n"
        buttons = []
        for i, t in enumerate(termini, 1):
            d = date.fromisoformat(t['datum'])
            odgovor += f"{i}. {fmt_datum_pun(d)} u {t['vreme']} — {t['usluga']} ({t['lokacija']})\n"
            buttons.append([f"Otkazi: {fmt_datum(d)} {t['vreme']}"])
        buttons.append(["🏠 Pocetni meni"])

        context.user_data['termini_za_otkazivanje'] = termini
        await update.message.reply_text(
            odgovor + "\nKoji termin otkazujete?",
            reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
        )
        return OTKAZIVANJE_TERMIN

    elif "Moji" in tekst:
        user_id = update.effective_user.id
        termini = db.get_termini_korisnika(user_id)
        if not termini:
            await update.message.reply_text(
                "Nemate zakazanih termina. 📭",
                reply_markup=glavni_meni_keyboard()
            )
        else:
            odgovor = "📅 Vasi nadolazeci termini:\n\n"
            for t in termini:
                d = date.fromisoformat(t['datum'])
                odgovor += f"• {fmt_datum_pun(d)} u {t['vreme']}\n"
                odgovor += f"  📍 {t['lokacija']} | ✂️ {t['usluga']}\n\n"
            await update.message.reply_text(odgovor, reply_markup=glavni_meni_keyboard())
        return IZBOR_AKCIJE

    elif "Info" in tekst:
        await update.message.reply_text(
            "💈 Berber Ivan\n\n"
            "📍 Novi Sad — Pon, Uto, Sre\n"
            "⏰ 15:00 – 20:00\n\n"
            "📍 Sid — Cet, Pet, Sub\n"
            "⏰ 09:00 – 13:00 i 15:00 – 21:00\n\n"
            "🚫 Nedelja — Neradna\n\n"
            "💰 Cenovnik:\n"
            "✂️ Sisanje — 1000 din\n"
            "🪒 Brada — 500 din\n"
            "✂️🪒 Sisanje + brada — 1500 din",
            reply_markup=glavni_meni_keyboard()
        )
        return IZBOR_AKCIJE

    elif "Pocetni" in tekst or "🏠" in tekst:
        return await start(update, context)

    return IZBOR_AKCIJE


async def unos_imena(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tekst = update.message.text.strip()

    if "Pocetni" in tekst or "🏠" in tekst:
        return await start(update, context)

    if len(tekst) < 3:
        await update.message.reply_text("Unesite ime i prezime (minimum 3 karaktera):")
        return UNOS_IMENA

    context.user_data['ime'] = tekst
    dani = get_sledecih_14_radnih_dana()
    context.user_data['dani_lista'] = [d.isoformat() for d in dani]

    buttons = []
    row = []
    for i, d in enumerate(dani):
        lok = get_lokacija(d)
        label = f"{i+1}. {fmt_datum(d)}"
        row.append(label)
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append(["🏠 Pocetni meni"])

    await update.message.reply_text(
        f"Hvala, {tekst}! 👋\n\n"
        "📅 Izaberite datum:\n\n"
        "📍 Pon-Sre = Novi Sad\n"
        "📍 Cet-Sub = Sid",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )
    return IZBOR_DATUMA


async def izbor_datuma(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tekst = update.message.text.strip()

    if "Pocetni" in tekst or "🏠" in tekst:
        return await start(update, context)

    dani_iso = context.user_data.get('dani_lista', [])
    dani = [date.fromisoformat(d) for d in dani_iso]

    odabrani_idx = None

    try:
        idx = int(tekst.split('.')[0]) - 1
        if 0 <= idx < len(dani):
            odabrani_idx = idx
    except (ValueError, IndexError):
        pass

    if odabrani_idx is None:
        for i, d in enumerate(dani):
            lbl = f"{i+1}. {fmt_datum(d)}"
            if tekst == lbl or tekst in lbl or lbl in tekst:
                odabrani_idx = i
                break

    if odabrani_idx is None:
        await update.message.reply_text("Molimo izaberite datum sa liste.")
        return IZBOR_DATUMA

    odabrani_datum = dani[odabrani_idx]
    lokacija = get_lokacija(odabrani_datum)
    context.user_data['datum'] = odabrani_datum.isoformat()
    context.user_data['lokacija'] = lokacija

    slobodni = get_slobodne_termine(odabrani_datum)
    if not slobodni:
        await update.message.reply_text(
            f"Nema slobodnih termina za {fmt_datum_pun(odabrani_datum)}.\n"
            "Izaberite drugi datum."
        )
        return IZBOR_DATUMA

    context.user_data['slobodni'] = slobodni

    buttons = []
    row = []
    for v in slobodni:
        row.append(v)
        if len(row) == 4:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append(["🏠 Pocetni meni"])

    # Prikaz radnog vremena za izabrani dan
    if lokacija == "Novi Sad":
        radno = "15:00 – 20:00"
    else:
        radno = "09:00 – 13:00 i 15:00 – 21:00"

    await update.message.reply_text(
        f"📅 {fmt_datum_pun(odabrani_datum)}\n"
        f"📍 {lokacija}\n"
        f"⏰ {radno}\n"
        f"🕐 Slobodnih termina: {len(slobodni)}\n\n"
        "Izaberite vreme:",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )
    return IZBOR_VREMENA


async def izbor_vremena(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tekst = update.message.text.strip()

    if "Pocetni" in tekst or "🏠" in tekst:
        return await start(update, context)

    m = re.match(r'^(\d{1,2}):(\d{2})$', tekst)
    if not m:
        await update.message.reply_text("Izaberite vreme sa liste.")
        return IZBOR_VREMENA

    slobodni = context.user_data.get('slobodni', [])
    if tekst not in slobodni:
        await update.message.reply_text("To vreme nije dostupno. Izaberite sa liste.")
        return IZBOR_VREMENA

    datum = date.fromisoformat(context.user_data['datum'])
    if db.je_termin_zauzet(datum, tekst):
        slobodni_novi = get_slobodne_termine(datum)
        context.user_data['slobodni'] = slobodni_novi
        buttons = []
        row = []
        for v in slobodni_novi:
            row.append(v)
            if len(row) == 4:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)
        buttons.append(["🏠 Pocetni meni"])
        await update.message.reply_text(
            f"⚠️ Termin {tekst} je upravo zauzet!\nIzaberite drugi termin:",
            reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
        )
        return IZBOR_VREMENA

    context.user_data['vreme'] = tekst

    usluge = [
        ["✂️ Sisanje — 1000 din"],
        ["🪒 Brada — 500 din"],
        ["✂️🪒 Sisanje + brada — 1500 din"],
        ["🏠 Pocetni meni"]
    ]
    await update.message.reply_text(
        "Koja usluga?",
        reply_markup=ReplyKeyboardMarkup(usluge, resize_keyboard=True)
    )
    return IZBOR_USLUGE


async def izbor_usluge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tekst = update.message.text.strip()

    if "Pocetni" in tekst or "🏠" in tekst:
        return await start(update, context)

    usluga = None
    cena = None
    if "Sisanje + brada" in tekst or ("brada" in tekst.lower() and "sisan" in tekst.lower()):
        usluga = "Sisanje + brada"
        cena = "1500 din"
    elif "Brada" in tekst or "brada" in tekst.lower():
        usluga = "Brada"
        cena = "500 din"
    elif "Sisanje" in tekst or "sisan" in tekst.lower():
        usluga = "Sisanje"
        cena = "1000 din"

    if not usluga:
        await update.message.reply_text("Molimo izaberite uslugu sa liste.")
        return IZBOR_USLUGE

    context.user_data['usluga'] = usluga
    context.user_data['cena'] = cena

    datum = date.fromisoformat(context.user_data['datum'])
    ime = context.user_data['ime']
    vreme = context.user_data['vreme']
    lokacija = context.user_data['lokacija']

    buttons = [["✅ Potvrdi"], ["🏠 Pocetni meni"]]
    await update.message.reply_text(
        f"Proverite podatke:\n\n"
        f"👤 {ime}\n"
        f"📅 {fmt_datum_pun(datum)}\n"
        f"⏰ {vreme}\n"
        f"📍 {lokacija}\n"
        f"✂️ {usluga}\n"
        f"💰 {cena}\n\n"
        f"Da li je sve tacno?",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )
    return POTVRDA


async def potvrda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tekst = update.message.text.strip()

    if "Pocetni" in tekst or "🏠" in tekst:
        return await start(update, context)

    if "Potvrdi" not in tekst and "✅" not in tekst:
        return POTVRDA

    user_id = update.effective_user.id
    datum = date.fromisoformat(context.user_data['datum'])
    ime = context.user_data['ime']
    vreme = context.user_data['vreme']
    lokacija = context.user_data['lokacija']
    usluga = context.user_data['usluga']
    cena = context.user_data.get('cena', '')

    if db.je_termin_zauzet(datum, vreme):
        await update.message.reply_text(
            "⚠️ Neko je upravo zauzeo taj termin!\n"
            "Pokrenite zakazivanje ponovo.",
            reply_markup=glavni_meni_keyboard()
        )
        return await start(update, context)

    db.dodaj_termin(
        user_id=user_id,
        ime=ime,
        datum=datum.isoformat(),
        vreme=vreme,
        lokacija=lokacija,
        usluga=usluga
    )

    await update.message.reply_text(
        f"✅ Termin zakazan!\n\n"
        f"📅 {fmt_datum_pun(datum)} u {vreme}\n"
        f"📍 {lokacija}\n"
        f"✂️ {usluga}\n"
        f"💰 {cena}\n\n"
        f"Vidimo se! 💈",
        reply_markup=glavni_meni_keyboard()
    )

    await posalji_notifikaciju_vlasniku(
        context,
        f"🔔 NOVO ZAKAZIVANJE\n\n"
        f"👤 {ime}\n"
        f"📅 {fmt_datum_pun(datum)} u {vreme}\n"
        f"📍 {lokacija}\n"
        f"✂️ {usluga} — {cena}"
    )

    context.user_data.clear()
    return IZBOR_AKCIJE


async def otkazivanje_termin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tekst = update.message.text.strip()

    if "Pocetni" in tekst or "🏠" in tekst:
        return await start(update, context)

    termini = context.user_data.get('termini_za_otkazivanje', [])
    odabrani = None
    for t in termini:
        d = date.fromisoformat(t['datum'])
        label = f"Otkazi: {fmt_datum(d)} {t['vreme']}"
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
        f"📅 {fmt_datum_pun(d)} u {odabrani['vreme']}\n\n"
        "Hvala na javljanju! 🙏",
        reply_markup=glavni_meni_keyboard()
    )

    await posalji_notifikaciju_vlasniku(
        context,
        f"⚠️ OTKAZIVANJE!\n\n"
        f"👤 {odabrani['ime']}\n"
        f"📅 {fmt_datum_pun(d)} u {odabrani['vreme']}\n"
        f"📍 {odabrani['lokacija']}\n"
        f"Termin je sada slobodan."
    )

    return IZBOR_AKCIJE


async def posalji_notifikaciju_vlasniku(context, poruka):
    vlasnik_id = config.VLASNIK_TELEGRAM_ID
    if vlasnik_id:
        try:
            await context.bot.send_message(chat_id=vlasnik_id, text=poruka)
        except Exception as e:
            logger.error(f"Greska notifikacije: {e}")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    return await start(update, context)


# ─── ADMIN KOMANDE ───────────────────────────────────────────────

async def admin_danas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.VLASNIK_TELEGRAM_ID:
        return
    danas = date.today()
    if not je_radni_dan(danas):
        await update.message.reply_text("Danas je neradna nedelja.")
        return

    termini = db.get_termini_za_datum(danas)
    fiksni = db.get_fiksni_termini_za_dan(danas.weekday())
    odgovor = f"📅 Danas — {fmt_datum_pun(danas)}\n📍 {get_lokacija(danas)}\n\n"
    svi = [(t['vreme'], t['ime'], t['usluga'], False) for t in termini]
    svi += [(f['vreme'], f['ime'], f['usluga'], True) for f in fiksni]
    svi.sort(key=lambda x: x[0])
    if not svi:
        odgovor += "Nema zakazanih termina."
    else:
        for vreme, ime, usluga, je_fiksni in svi:
            marker = "🔒" if je_fiksni else "✅"
            odgovor += f"{marker} {vreme} — {ime} ({usluga})\n"
    await update.message.reply_text(odgovor)


async def admin_sutra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.VLASNIK_TELEGRAM_ID:
        return
    sutra = date.today() + timedelta(days=1)
    if not je_radni_dan(sutra):
        await update.message.reply_text("Sutra je neradna nedelja.")
        return

    termini = db.get_termini_za_datum(sutra)
    fiksni = db.get_fiksni_termini_za_dan(sutra.weekday())
    odgovor = f"📅 Sutra — {fmt_datum_pun(sutra)}\n📍 {get_lokacija(sutra)}\n\n"
    svi = [(t['vreme'], t['ime'], t['usluga'], False) for t in termini]
    svi += [(f['vreme'], f['ime'], f['usluga'], True) for f in fiksni]
    svi.sort(key=lambda x: x[0])
    if not svi:
        odgovor += "Nema zakazanih termina."
    else:
        for vreme, ime, usluga, je_fiksni in svi:
            marker = "🔒" if je_fiksni else "✅"
            odgovor += f"{marker} {vreme} — {ime} ({usluga})\n"
    await update.message.reply_text(odgovor)


async def admin_fiksni(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.VLASNIK_TELEGRAM_ID:
        return
    fiksni = db.get_svi_fiksni_termini()
    dani_names = ["Ponedeljak","Utorak","Sreda","Cetvrtak","Petak","Subota","Nedelja"]
    if not fiksni:
        await update.message.reply_text("Nema fiksnih termina.")
        return
    odgovor = "🔒 Fiksni termini:\n\n"
    for f in fiksni:
        odgovor += f"#{f['id']} {dani_names[f['dan_nedelje']]} {f['vreme']} — {f['ime']} ({f['lokacija']}) | {f['usluga']}\n"
    odgovor += "\n/dodaj_fiksni <ime> <dan> <vreme> <usluga>\n/obrisi_fiksni <ID>"
    await update.message.reply_text(odgovor)


async def admin_dodaj_fiksni(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.VLASNIK_TELEGRAM_ID:
        return
    args = context.args
    if len(args) < 4:
        await update.message.reply_text(
            "Upotreba: /dodaj_fiksni <ime> <dan> <vreme> <usluga>\n"
            "Primer: /dodaj_fiksni 'Pera Peric' ponedeljak 16:00 sisanje"
        )
        return
    ime = args[0]
    dan_tekst = args[1].lower()
    vreme_tekst = args[2]
    usluga = " ".join(args[3:])
    dani_map = {"ponedeljak":0,"utorak":1,"sreda":2,"cetvrtak":3,"petak":4,"subota":5}
    dan_idx = dani_map.get(dan_tekst)
    if dan_idx is None:
        await update.message.reply_text(f"Nepoznat dan: {dan_tekst} (nedelja je neradna)")
        return
    m = re.match(r'^(\d{1,2}):(\d{2})$', vreme_tekst)
    if not m:
        await update.message.reply_text(f"Neispravno vreme: {vreme_tekst}")
        return
    temp = date.today()
    while temp.weekday() != dan_idx:
        temp += timedelta(days=1)
    lokacija = get_lokacija(temp)
    db.dodaj_fiksni_termin(ime=ime, dan_nedelje=dan_idx, vreme=vreme_tekst, lokacija=lokacija, usluga=usluga)
    dani_names = ["Ponedeljak","Utorak","Sreda","Cetvrtak","Petak","Subota"]
    await update.message.reply_text(
        f"✅ Fiksni termin dodat!\n\n"
        f"👤 {ime}\n"
        f"📅 Svaki {dani_names[dan_idx]} u {vreme_tekst}\n"
        f"📍 {lokacija} | ✂️ {usluga}"
    )


async def admin_obrisi_fiksni(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != config.VLASNIK_TELEGRAM_ID:
        return
    if not context.args:
        await update.message.reply_text("Upotreba: /obrisi_fiksni <ID>")
        return
    try:
        fiksni_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID mora biti broj.")
        return
    db.obrisi_fiksni_termin(fiksni_id)
    await update.message.reply_text(f"✅ Fiksni termin #{fiksni_id} obrisan.")


async def admin_otkazi(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    try:
        await context.bot.send_message(
            chat_id=termin['user_id'],
            text=(
                f"⚠️ Vas termin je otkazan.\n\n"
                f"📅 {fmt_datum_pun(d)} u {termin['vreme']}\n"
                f"📍 {termin['lokacija']}\n\n"
                "Izvinjavamo se! Mozete zakazati novi termin. 🙏"
            )
        )
    except Exception:
        pass
    await update.message.reply_text(f"✅ Termin #{termin_id} otkazan, musterija obavestena.")


async def pomoc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    je_vlasnik = update.effective_user.id == config.VLASNIK_TELEGRAM_ID
    tekst = "/start — Pocetni meni\n/pomoc — Komande\n"
    if je_vlasnik:
        tekst += (
            "\n👑 Admin:\n"
            "/danas — Termini danas\n"
            "/sutra — Termini sutra\n"
            "/fiksni — Fiksni termini\n"
            "/dodaj_fiksni <ime> <dan> <vreme> <usluga>\n"
            "/obrisi_fiksni <ID>\n"
            "/otkazi_admin <ID>\n"
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
            MessageHandler(filters.TEXT & ~filters.COMMAND, izbor_akcije),
        ],
        states={
            IZBOR_AKCIJE: [MessageHandler(filters.TEXT & ~filters.COMMAND, izbor_akcije)],
            UNOS_IMENA: [MessageHandler(filters.TEXT & ~filters.COMMAND, unos_imena)],
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
    app.add_handler(CommandHandler("danas", admin_danas))
    app.add_handler(CommandHandler("sutra", admin_sutra))
    app.add_handler(CommandHandler("fiksni", admin_fiksni))
    app.add_handler(CommandHandler("dodaj_fiksni", admin_dodaj_fiksni))
    app.add_handler(CommandHandler("obrisi_fiksni", admin_obrisi_fiksni))
    app.add_handler(CommandHandler("otkazi_admin", admin_otkazi))
    app.add_handler(CommandHandler("pomoc", pomoc))

    logger.info("Bot pokrenut!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
