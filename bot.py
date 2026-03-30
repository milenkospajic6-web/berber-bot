import logging
import os
import re
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, ConversationHandler, ContextTypes, filters
from datetime import date, timedelta
from database import Database
from config import Config

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

AKCIJA, IME, DATUM, VREME, USLUGA, POTVRDA, OTKAZI = range(7)

db = Database()
config = Config()

def lokacija(d):
    dan = d.weekday()
    if dan in [0,1,2]: return "Novi Sad"
    if dan in [3,4,5]: return "Sid"
    return None

def fdatum(d):
    dani = ["Pon","Uto","Sre","Cet","Pet","Sub","Ned"]
    mes = ["jan","feb","mar","apr","maj","jun","jul","avg","sep","okt","nov","dec"]
    return f"{dani[d.weekday()]} {d.day}.{d.month}."

def fdatum_pun(d):
    dani = ["Ponedeljak","Utorak","Sreda","Cetvrtak","Petak","Subota","Nedelja"]
    mes = ["jan","feb","mar","apr","maj","jun","jul","avg","sep","okt","nov","dec"]
    return f"{dani[d.weekday()]}, {d.day}. {mes[d.month-1]}"

def radni_dani():
    dani = []
    d = date.today() + timedelta(days=1)
    while len(dani) < 14:
        if d.weekday() != 6:  # nije nedelja
            dani.append(d)
        d += timedelta(days=1)
    return dani

def termini_za_dan(d):
    t = []
    if d.weekday() in [0,1,2]:  # Novi Sad 15-20
        for s in range(15,20):
            for m in [0,30]: t.append(f"{s:02d}:{m:02d}")
    elif d.weekday() in [3,4,5]:  # Sid 9-13 i 15-21
        for s in range(9,13):
            for m in [0,30]: t.append(f"{s:02d}:{m:02d}")
        for s in range(15,21):
            for m in [0,30]: t.append(f"{s:02d}:{m:02d}")
    return t

def slobodni(d):
    svi = termini_za_dan(d)
    zauzeti = {x['vreme'] for x in db.get_termini_za_datum(d)}
    zauzeti.update({x['vreme'] for x in db.get_fiksni_termini_za_dan(d.weekday())})
    return [v for v in svi if v not in zauzeti]

def meni():
    return ReplyKeyboardMarkup([
        ["✂️ Zakazi termin"],
        ["❌ Otkazi termin", "📅 Moji termini"],
        ["ℹ️ Info i cene"],
    ], resize_keyboard=True)

async def start(update, context):
    context.user_data.clear()
    ime = update.effective_user.first_name or "druze"
    await update.message.reply_text(
        f"Zdravo {ime}! 👋\nDobrodosao u berberski salon Ivan.\nIzaberi opciju:",
        reply_markup=meni()
    )
    return AKCIJA

async def akcija(update, context):
    t = update.message.text
    if "Zakazi" in t:
        await update.message.reply_text("Kako se zovete?\nUnesite ime i prezime:",
            reply_markup=ReplyKeyboardMarkup([["🏠 Meni"]], resize_keyboard=True))
        return IME
    if "Otkazi" in t:
        termini = db.get_termini_korisnika(update.effective_user.id)
        if not termini:
            await update.message.reply_text("Nemate zakazanih termina.", reply_markup=meni())
            return AKCIJA
        odg = "Vasi termini:\n\n"
        btns = []
        for i,x in enumerate(termini,1):
            d = date.fromisoformat(x['datum'])
            odg += f"{i}. {fdatum_pun(d)} u {x['vreme']} — {x['usluga']}\n"
            btns.append([f"#{i} {fdatum(d)} {x['vreme']}"])
        btns.append(["🏠 Meni"])
        context.user_data['termini'] = termini
        await update.message.reply_text(odg+"\nIzaberite termin za otkazivanje:",
            reply_markup=ReplyKeyboardMarkup(btns, resize_keyboard=True))
        return OTKAZI
    if "Moji" in t:
        termini = db.get_termini_korisnika(update.effective_user.id)
        if not termini:
            await update.message.reply_text("Nemate zakazanih termina.", reply_markup=meni())
        else:
            odg = "📅 Vasi termini:\n\n"
            for x in termini:
                d = date.fromisoformat(x['datum'])
                odg += f"• {fdatum_pun(d)} u {x['vreme']}\n  📍 {x['lokacija']} | ✂️ {x['usluga']}\n\n"
            await update.message.reply_text(odg, reply_markup=meni())
        return AKCIJA
    if "Info" in t:
        await update.message.reply_text(
            "💈 Berber Ivan\n\n"
            "📍 Novi Sad — Pon, Uto, Sre\n⏰ 15:00 – 20:00\n\n"
            "📍 Sid — Cet, Pet, Sub\n⏰ 09:00–13:00 i 15:00–21:00\n\n"
            "🚫 Nedelja — Neradna\n\n"
            "💰 Cenovnik:\n✂️ Sisanje — 1000 din\n🪒 Brada — 500 din\n✂️🪒 Sisanje + brada — 1500 din",
            reply_markup=meni())
        return AKCIJA
    if "Meni" in t or "🏠" in t:
        return await start(update, context)
    return AKCIJA

async def ime_handler(update, context):
    t = update.message.text.strip()
    if "Meni" in t or "🏠" in t:
        return await start(update, context)
    if len(t) < 2:
        await update.message.reply_text("Unesite ime i prezime:")
        return IME
    context.user_data['ime'] = t
    dani = radni_dani()
    context.user_data['dani'] = [d.isoformat() for d in dani]
    btns = []
    row = []
    for i,d in enumerate(dani):
        row.append(f"{i+1}. {fdatum(d)}")
        if len(row) == 2:
            btns.append(row); row = []
    if row: btns.append(row)
    btns.append(["🏠 Meni"])
    await update.message.reply_text(
        f"Hvala, {t}! 👋\n\n📅 Izaberite datum:\n(Pon-Sre = Novi Sad | Cet-Sub = Sid)",
        reply_markup=ReplyKeyboardMarkup(btns, resize_keyboard=True))
    return DATUM

async def datum_handler(update, context):
    t = update.message.text.strip()
    if "Meni" in t or "🏠" in t:
        return await start(update, context)
    dani = [date.fromisoformat(x) for x in context.user_data.get('dani', [])]
    idx = None
    try:
        idx = int(t.split('.')[0]) - 1
        if not (0 <= idx < len(dani)): idx = None
    except: pass
    if idx is None:
        for i,d in enumerate(dani):
            if f"{i+1}. {fdatum(d)}" in t or t in f"{i+1}. {fdatum(d)}":
                idx = i; break
    if idx is None:
        await update.message.reply_text("Izaberite datum sa liste.")
        return DATUM
    d = dani[idx]
    lok = lokacija(d)
    sl = slobodni(d)
    if not sl:
        await update.message.reply_text(f"Nema slobodnih termina za {fdatum_pun(d)}. Izaberite drugi datum.")
        return DATUM
    context.user_data['datum'] = d.isoformat()
    context.user_data['lokacija'] = lok
    context.user_data['slobodni'] = sl
    btns = []
    row = []
    for v in sl:
        row.append(v)
        if len(row) == 4: btns.append(row); row = []
    if row: btns.append(row)
    btns.append(["🏠 Meni"])
    radno = "15:00–20:00" if lok == "Novi Sad" else "09:00–13:00 i 15:00–21:00"
    await update.message.reply_text(
        f"📅 {fdatum_pun(d)}\n📍 {lok}\n⏰ {radno}\n\nIzaberite vreme:",
        reply_markup=ReplyKeyboardMarkup(btns, resize_keyboard=True))
    return VREME

async def vreme_handler(update, context):
    t = update.message.text.strip()
    if "Meni" in t or "🏠" in t:
        return await start(update, context)
    sl = context.user_data.get('slobodni', [])
    if t not in sl:
        await update.message.reply_text("Izaberite vreme sa liste.")
        return VREME
    d = date.fromisoformat(context.user_data['datum'])
    if db.je_termin_zauzet(d, t):
        novi = slobodni(d)
        context.user_data['slobodni'] = novi
        btns = []
        row = []
        for v in novi:
            row.append(v)
            if len(row) == 4: btns.append(row); row = []
        if row: btns.append(row)
        btns.append(["🏠 Meni"])
        await update.message.reply_text("⚠️ Taj termin je upravo zauzet! Izaberite drugi:",
            reply_markup=ReplyKeyboardMarkup(btns, resize_keyboard=True))
        return VREME
    context.user_data['vreme'] = t
    btns = [["✂️ Sisanje — 1000 din"],["🪒 Brada — 500 din"],["✂️🪒 Sisanje + brada — 1500 din"],["🏠 Meni"]]
    await update.message.reply_text("Koja usluga?", reply_markup=ReplyKeyboardMarkup(btns, resize_keyboard=True))
    return USLUGA

async def usluga_handler(update, context):
    t = update.message.text.strip()
    if "Meni" in t or "🏠" in t:
        return await start(update, context)
    if "brada" in t.lower() and "sisan" in t.lower():
        usluga, cena = "Sisanje + brada", "1500 din"
    elif "brada" in t.lower():
        usluga, cena = "Brada", "500 din"
    elif "sisan" in t.lower():
        usluga, cena = "Sisanje", "1000 din"
    else:
        await update.message.reply_text("Izaberite uslugu sa liste.")
        return USLUGA
    context.user_data['usluga'] = usluga
    context.user_data['cena'] = cena
    d = date.fromisoformat(context.user_data['datum'])
    btns = [["✅ Potvrdi"], ["🏠 Meni"]]
    await update.message.reply_text(
        f"Proverite podatke:\n\n"
        f"👤 {context.user_data['ime']}\n"
        f"📅 {fdatum_pun(d)}\n"
        f"⏰ {context.user_data['vreme']}\n"
        f"📍 {context.user_data['lokacija']}\n"
        f"✂️ {usluga}\n"
        f"💰 {cena}\n\n"
        f"Da li je sve tacno?",
        reply_markup=ReplyKeyboardMarkup(btns, resize_keyboard=True))
    return POTVRDA

async def potvrda_handler(update, context):
    t = update.message.text.strip()
    if "Meni" in t or "🏠" in t:
        return await start(update, context)
    if "Potvrdi" not in t:
        return POTVRDA
    d = date.fromisoformat(context.user_data['datum'])
    if db.je_termin_zauzet(d, context.user_data['vreme']):
        await update.message.reply_text("⚠️ Neko je zauzeo taj termin! Pokrenite ponovo.", reply_markup=meni())
        return await start(update, context)
    db.dodaj_termin(
        user_id=update.effective_user.id,
        ime=context.user_data['ime'],
        datum=d.isoformat(),
        vreme=context.user_data['vreme'],
        lokacija=context.user_data['lokacija'],
        usluga=context.user_data['usluga']
    )
    await update.message.reply_text(
        f"✅ Termin zakazan!\n\n"
        f"📅 {fdatum_pun(d)} u {context.user_data['vreme']}\n"
        f"📍 {context.user_data['lokacija']}\n"
        f"✂️ {context.user_data['usluga']}\n"
        f"💰 {context.user_data['cena']}\n\n"
        f"Vidimo se! 💈",
        reply_markup=meni())
    if config.VLASNIK_TELEGRAM_ID:
        try:
            await context.bot.send_message(chat_id=config.VLASNIK_TELEGRAM_ID,
                text=f"🔔 NOVO ZAKAZIVANJE\n\n👤 {context.user_data['ime']}\n📅 {fdatum_pun(d)} u {context.user_data['vreme']}\n📍 {context.user_data['lokacija']}\n✂️ {context.user_data['usluga']} — {context.user_data['cena']}")
        except: pass
    context.user_data.clear()
    return AKCIJA

async def otkazi_handler(update, context):
    t = update.message.text.strip()
    if "Meni" in t or "🏠" in t:
        return await start(update, context)
    termini = context.user_data.get('termini', [])
    odabran = None
    for i,x in enumerate(termini,1):
        d = date.fromisoformat(x['datum'])
        if f"#{i} {fdatum(d)} {x['vreme']}" in t:
            odabran = x; break
    if not odabran:
        await update.message.reply_text("Izaberite termin sa liste.")
        return OTKAZI
    db.otkazi_termin(odabran['id'])
    d = date.fromisoformat(odabran['datum'])
    await update.message.reply_text(
        f"✅ Termin otkazan.\n\n📅 {fdatum_pun(d)} u {odabran['vreme']}\n\nHvala! 🙏",
        reply_markup=meni())
    if config.VLASNIK_TELEGRAM_ID:
        try:
            await context.bot.send_message(chat_id=config.VLASNIK_TELEGRAM_ID,
                text=f"⚠️ OTKAZIVANJE\n\n👤 {odabran['ime']}\n📅 {fdatum_pun(d)} u {odabran['vreme']}\n📍 {odabran['lokacija']}")
        except: pass
    return AKCIJA

async def danas_cmd(update, context):
    if update.effective_user.id != config.VLASNIK_TELEGRAM_ID: return
    d = date.today()
    if d.weekday() == 6:
        await update.message.reply_text("Danas je neradna nedelja."); return
    termini = db.get_termini_za_datum(d)
    fiksni = db.get_fiksni_termini_za_dan(d.weekday())
    svi = sorted([(x['vreme'],x['ime'],x['usluga'],False) for x in termini] +
                 [(x['vreme'],x['ime'],x['usluga'],True) for x in fiksni])
    odg = f"📅 {fdatum_pun(d)} — {lokacija(d)}\n\n"
    odg += "\n".join([f"{'🔒' if f else '✅'} {v} — {i} ({u})" for v,i,u,f in svi]) if svi else "Nema termina."
    await update.message.reply_text(odg)

async def sutra_cmd(update, context):
    if update.effective_user.id != config.VLASNIK_TELEGRAM_ID: return
    d = date.today() + timedelta(days=1)
    if d.weekday() == 6:
        await update.message.reply_text("Sutra je neradna nedelja."); return
    termini = db.get_termini_za_datum(d)
    fiksni = db.get_fiksni_termini_za_dan(d.weekday())
    svi = sorted([(x['vreme'],x['ime'],x['usluga'],False) for x in termini] +
                 [(x['vreme'],x['ime'],x['usluga'],True) for x in fiksni])
    odg = f"📅 {fdatum_pun(d)} — {lokacija(d)}\n\n"
    odg += "\n".join([f"{'🔒' if f else '✅'} {v} — {i} ({u})" for v,i,u,f in svi]) if svi else "Nema termina."
    await update.message.reply_text(odg)

async def fiksni_cmd(update, context):
    if update.effective_user.id != config.VLASNIK_TELEGRAM_ID: return
    fiksni = db.get_svi_fiksni_termini()
    dani = ["Pon","Uto","Sre","Cet","Pet","Sub","Ned"]
    if not fiksni:
        await update.message.reply_text("Nema fiksnih termina."); return
    odg = "🔒 Fiksni termini:\n\n"
    for f in fiksni:
        odg += f"#{f['id']} {dani[f['dan_nedelje']]} {f['vreme']} — {f['ime']} ({f['lokacija']})\n"
    odg += "\n/dodaj_fiksni ime dan vreme usluga\n/obrisi_fiksni ID"
    await update.message.reply_text(odg)

async def dodaj_fiksni_cmd(update, context):
    if update.effective_user.id != config.VLASNIK_TELEGRAM_ID: return
    args = context.args
    if len(args) < 4:
        await update.message.reply_text("Primer: /dodaj_fiksni 'Pera' ponedeljak 16:00 sisanje"); return
    dani_map = {"ponedeljak":0,"utorak":1,"sreda":2,"cetvrtak":3,"petak":4,"subota":5}
    dan_idx = dani_map.get(args[1].lower())
    if dan_idx is None:
        await update.message.reply_text("Nepoznat dan (nedelja je neradna)."); return
    temp = date.today()
    while temp.weekday() != dan_idx: temp += timedelta(days=1)
    db.dodaj_fiksni_termin(ime=args[0], dan_nedelje=dan_idx, vreme=args[2], lokacija=lokacija(temp), usluga=" ".join(args[3:]))
    await update.message.reply_text(f"✅ Dodat fiksni termin za {args[0]}!")

async def obrisi_fiksni_cmd(update, context):
    if update.effective_user.id != config.VLASNIK_TELEGRAM_ID: return
    if not context.args:
        await update.message.reply_text("Upotreba: /obrisi_fiksni ID"); return
    db.obrisi_fiksni_termin(int(context.args[0]))
    await update.message.reply_text(f"✅ Fiksni termin #{context.args[0]} obrisan.")

async def otkazi_admin_cmd(update, context):
    if update.effective_user.id != config.VLASNIK_TELEGRAM_ID: return
    if not context.args:
        await update.message.reply_text("Upotreba: /otkazi_admin ID"); return
    termin = db.get_termin_po_id(int(context.args[0]))
    if not termin:
        await update.message.reply_text("Termin nije nadjen."); return
    db.otkazi_termin(termin['id'])
    d = date.fromisoformat(termin['datum'])
    try:
        await context.bot.send_message(chat_id=termin['user_id'],
            text=f"⚠️ Vas termin je otkazan.\n📅 {fdatum_pun(d)} u {termin['vreme']}\nIzvinjavamo se! 🙏")
    except: pass
    await update.message.reply_text("✅ Termin otkazan, musterija obavestena.")

def main():
    token = os.environ.get("BOT_TOKEN") or config.BOT_TOKEN
    if not token: raise ValueError("BOT_TOKEN nije postavljen!")
    app = Application.builder().token(token).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start), MessageHandler(filters.TEXT & ~filters.COMMAND, akcija)],
        states={
            AKCIJA: [MessageHandler(filters.TEXT & ~filters.COMMAND, akcija)],
            IME: [MessageHandler(filters.TEXT & ~filters.COMMAND, ime_handler)],
            DATUM: [MessageHandler(filters.TEXT & ~filters.COMMAND, datum_handler)],
            VREME: [MessageHandler(filters.TEXT & ~filters.COMMAND, vreme_handler)],
            USLUGA: [MessageHandler(filters.TEXT & ~filters.COMMAND, usluga_handler)],
            POTVRDA: [MessageHandler(filters.TEXT & ~filters.COMMAND, potvrda_handler)],
            OTKAZI: [MessageHandler(filters.TEXT & ~filters.COMMAND, otkazi_handler)],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("danas", danas_cmd))
    app.add_handler(CommandHandler("sutra", sutra_cmd))
    app.add_handler(CommandHandler("fiksni", fiksni_cmd))
    app.add_handler(CommandHandler("dodaj_fiksni", dodaj_fiksni_cmd))
    app.add_handler(CommandHandler("obrisi_fiksni", obrisi_fiksni_cmd))
    app.add_handler(CommandHandler("otkazi_admin", otkazi_admin_cmd))
    logger.info("Bot pokrenut!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
