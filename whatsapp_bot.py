"""
WhatsApp Bot - Green API polling verzija
Proverava poruke svake 2 sekunde, bez webhook servera.
"""

import os
import time
import logging
import requests
from datetime import date, timedelta
import re

from database import Database
from config import Config

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

db = Database()
config = Config()

BASE_URL    = os.environ.get("GREEN_API_URL", "https://7107.api.greenapi.com")
INSTANCE    = os.environ.get("INSTANCE_ID", "")
TOKEN       = os.environ.get("API_TOKEN", "")
VLASNIK_TEL = os.environ.get("VLASNIK_TELEFON", "")

sesije = {}

def get_lok(datum):
    dan = datum.weekday()
    if dan in [0,1,2]: return "Novi Sad"
    elif dan in [3,4,5]: return "Sid"
    else: return "Novi Sad"

def fmt(d):
    dani=["Ponedeljak","Utorak","Sreda","Cetvrtak","Petak","Subota","Nedelja"]
    mes=["jan","feb","mar","apr","maj","jun","jul","avg","sep","okt","nov","dec"]
    return f"{dani[d.weekday()]}, {d.day}. {mes[d.month-1]}"

def sledeci_dani(n=7):
    dani=[]; d=date.today()
    for _ in range(n): dani.append(d); d+=timedelta(days=1)
    return dani

def parse_vreme(t):
    t=t.strip().replace("h","").replace("H","")
    m=re.match(r'^(\d{1,2})(?::(\d{2}))?$',t)
    if m:
        s=int(m.group(1)); mi=int(m.group(2) or 0)
        if 8<=s<=19 and mi in [0,30]: return f"{s:02d}:{mi:02d}"
    return None

def slobodni(datum):
    zauzeta={t['vreme'] for t in db.get_termini_za_datum(datum)}
    zauzeta.update({f['vreme'] for f in db.get_fiksni_termini_za_dan(datum.weekday())})
    return [f"{s:02d}:{m:02d}" for s in range(8,20) for m in [0,30] if f"{s:02d}:{m:02d}" not in zauzeta]

def posalji(tel, tekst):
    try:
        r=requests.post(f"{BASE_URL}/waInstance{INSTANCE}/sendMessage/{TOKEN}",
            json={"chatId":f"{tel}@c.us","message":tekst},timeout=30)
        logger.info(f"→ {tel}: {r.status_code}")
    except Exception as e: logger.error(f"Greska: {e}")

def posalji_vlasniku(tekst):
    if VLASNIK_TEL: posalji(VLASNIK_TEL, tekst)

def primi():
    try:
        r=requests.get(f"{BASE_URL}/waInstance{INSTANCE}/receiveNotification/{TOKEN}",timeout=10)
        if r.status_code==200 and r.text and r.text!="null": return r.json()
    except Exception as e: logger.error(f"Greska primanja: {e}")
    return None

def obrisi(rid):
    try: requests.delete(f"{BASE_URL}/waInstance{INSTANCE}/deleteNotification/{TOKEN}/{rid}",timeout=10)
    except: pass

def meni():
    return "✂️ Berber Ivan\n\n1 - Zakazi termin\n2 - Otkazi termin\n3 - Moji termini\n4 - Radno vreme\n\nPosaljite broj (1-4)"

def obradi(tel, tekst):
    tekst=tekst.strip()
    ses=sesije.get(tel,{"korak":"start"})
    if tekst.lower() in ["meni","start","0","/start"]:
        sesije[tel]={"korak":"start"}; posalji(tel,meni()); return
    korak=ses.get("korak","start")

    if korak=="start":
        if tekst=="1" or "zakaz" in tekst.lower():
            sesije[tel]={"korak":"unos_imena"}; posalji(tel,"Kako se zovete? Unesite ime i prezime:")
        elif tekst=="2" or "otkaz" in tekst.lower():
            tt=db.get_termini_korisnika_telefon(tel)
            if not tt: posalji(tel,"Nemate zakazanih termina."); return
            odg="Vasi termini:\n\n"
            for i,t in enumerate(tt,1):
                d=date.fromisoformat(t['datum'])
                odg+=f"{i}. {fmt(d)} u {t['vreme']} - {t['usluga']}\n"
            sesije[tel]={"korak":"otkazivanje","termini":tt}
            posalji(tel,odg+"\nUnesite broj za otkazivanje:")
        elif tekst=="3" or "moji" in tekst.lower():
            tt=db.get_termini_korisnika_telefon(tel)
            if not tt: posalji(tel,"Nemate zakazanih termina.")
            else:
                odg="Vasi termini:\n\n"
                for t in tt:
                    d=date.fromisoformat(t['datum'])
                    odg+=f"• {fmt(d)} u {t['vreme']} - {t['lokacija']} | {t['usluga']}\n"
                posalji(tel,odg)
        elif tekst=="4" or "radno" in tekst.lower():
            posalji(tel,"Radno vreme:\n\nNovi Sad - Nedelja do Sreda\nSid - Cetvrtak do Nedelja\n\n08:00 - 19:30 | 30 min termini")
        else: posalji(tel,meni())

    elif korak=="unos_imena":
        if len(tekst)<3: posalji(tel,"Unesite ime i prezime (min 3 slova):"); return
        ses["ime"]=tekst; dani=sledeci_dani(7)
        ses["dani"]=[d.isoformat() for d in dani]
        sesije[tel]={**ses,"korak":"izbor_datuma"}
        odg=f"Hvala, {tekst}!\n\nIzaberite datum:\n\n"
        for i,d in enumerate(dani,1): odg+=f"{i}. {fmt(d)} - {get_lok(d)}\n"
        posalji(tel,odg+"\nUnesite broj:")

    elif korak=="izbor_datuma":
        dani_iso=ses.get("dani",[])
        try:
            idx=int(tekst)-1
            if not(0<=idx<len(dani_iso)): raise ValueError
        except: posalji(tel,f"Unesite broj od 1 do {len(dani_iso)}:"); return
        datum=date.fromisoformat(dani_iso[idx]); lok=get_lok(datum); sl=slobodni(datum)
        if not sl: posalji(tel,f"Nema slobodnih termina za {fmt(datum)}."); return
        ses["datum"]=datum.isoformat(); ses["lokacija"]=lok; ses["slobodni"]=sl
        sesije[tel]={**ses,"korak":"izbor_vremena"}
        odg=f"{fmt(datum)} - {lok}\n\nSlobodni termini:\n\n"
        for i,v in enumerate(sl,1): odg+=f"{i}. {v}\n"
        posalji(tel,odg+"\nUnesite broj:")

    elif korak=="izbor_vremena":
        sl=ses.get("slobodni",[]); datum=date.fromisoformat(ses["datum"]); vreme=None
        try:
            idx=int(tekst)-1
            if 0<=idx<len(sl): vreme=sl[idx]
        except: vreme=parse_vreme(tekst)
        if not vreme: posalji(tel,"Unesite broj sa liste:"); return
        if db.je_termin_zauzet(datum,vreme):
            sl2=slobodni(datum); ses["slobodni"]=sl2; sesije[tel]=ses
            odg=f"Termin {vreme} je zauzet!\n\nSlobodni:\n\n"
            for i,v in enumerate(sl2,1): odg+=f"{i}. {v}\n"
            posalji(tel,odg); return
        ses["vreme"]=vreme; sesije[tel]={**ses,"korak":"izbor_usluge"}
        posalji(tel,"Koja usluga?\n\n1. Sisanje\n2. Brada\n3. Sisanje + brada\n\nUnesite broj:")

    elif korak=="izbor_usluge":
        u={"1":"Sisanje","2":"Brada","3":"Sisanje + brada"}.get(tekst.strip())
        if not u:
            t2=tekst.lower()
            if "brada" in t2 and "sisan" in t2: u="Sisanje + brada"
            elif "brada" in t2: u="Brada"
            elif "sisan" in t2: u="Sisanje"
        if not u: posalji(tel,"Unesite 1, 2 ili 3:"); return
        ses["usluga"]=u; sesije[tel]={**ses,"korak":"potvrda"}
        datum=date.fromisoformat(ses["datum"])
        posalji(tel,f"Proverite:\n\nIme: {ses['ime']}\nDatum: {fmt(datum)} u {ses['vreme']}\nLokacija: {ses['lokacija']}\nUsluga: {u}\n\nDA za potvrdu ili NE za otkaz:")

    elif korak=="potvrda":
        t2=tekst.lower().strip()
        if t2 in ["ne","n","otkazi"]:
            sesije[tel]={"korak":"start"}; posalji(tel,"Otkazano.\n\n"+meni()); return
        if t2 not in ["da","d","yes","ok"]:
            posalji(tel,"Posaljite DA ili NE:"); return
        datum=date.fromisoformat(ses["datum"])
        if db.je_termin_zauzet(datum,ses["vreme"]):
            sesije[tel]={"korak":"start"}; posalji(tel,"Neko je zauzeo taj termin! Pokrenite ponovo."); return
        db.dodaj_termin(user_id=0,ime=ses["ime"],datum=datum.isoformat(),
            vreme=ses["vreme"],lokacija=ses["lokacija"],usluga=ses["usluga"],telefon=tel)
        sesije[tel]={"korak":"start"}
        posalji(tel,f"Termin zakazan!\n\n{fmt(datum)} u {ses['vreme']}\n{ses['lokacija']} | {ses['usluga']}\n\nVidimo se! 💈")
        posalji_vlasniku(f"NOVO ZAKAZIVANJE (WhatsApp)\n\nIme: {ses['ime']}\nTel: {tel}\nDatum: {fmt(datum)} u {ses['vreme']}\nLokacija: {ses['lokacija']}\nUsluga: {ses['usluga']}")

    elif korak=="otkazivanje":
        tt=ses.get("termini",[])
        try:
            idx=int(tekst)-1
            if not(0<=idx<len(tt)): raise ValueError
        except: posalji(tel,f"Unesite broj od 1 do {len(tt)}:"); return
        t=tt[idx]; db.otkazi_termin(t['id']); d=date.fromisoformat(t['datum'])
        sesije[tel]={"korak":"start"}
        posalji(tel,f"Termin otkazan.\n\n{fmt(d)} u {t['vreme']}\n\nHvala!")
        posalji_vlasniku(f"OTKAZIVANJE (WhatsApp)\n\nIme: {t['ime']}\nTel: {tel}\nDatum: {fmt(d)} u {t['vreme']}\nLokacija: {t['lokacija']}\nSlobodan termin.")

def main():
    if not INSTANCE or not TOKEN:
        raise ValueError("INSTANCE_ID ili API_TOKEN nisu postavljeni!")
    logger.info(f"WhatsApp bot pokrenut! Instance: {INSTANCE}")
    while True:
        try:
            notif=primi()
            if notif:
                rid=notif.get("receiptId")
                body=notif.get("body",{})
                if body.get("typeWebhook")=="incomingMessageReceived":
                    sender=body.get("senderData",{})
                    pd=body.get("messageData",{})
                    tel=sender.get("sender","").replace("@c.us","")
                    if pd.get("typeMessage")=="textMessage" and tel:
                        tekst=pd.get("textMessageData",{}).get("textMessage","")
                        if tekst:
                            logger.info(f"Poruka od {tel}: {tekst}")
                            obradi(tel,tekst)
                if rid: obrisi(rid)
            else:
                time.sleep(2)
        except KeyboardInterrupt: break
        except Exception as e:
            logger.error(f"Greska: {e}"); time.sleep(5)

if __name__=="__main__":
    main()
