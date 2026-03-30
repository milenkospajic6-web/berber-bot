# Berber Bot 💈

Telegram bot za zakazivanje termina u berbernici.

## Funkcionalnosti

- Zakazivanje termina (ime, datum, vreme, usluga)
- Blokiranje duplikata — automatski
- Fiksni termini (zauvek zakazani za stalne mušterije)
- Otkazivanje termina
- Notifikacije vlasniku za svako novo zakazivanje i otkazivanje
- 2 lokacije: Novi Sad (ned-sre) i Sid (cet-ned)
- Admin komande za vlasnika

---

## Setup — Korak po korak

### Korak 1: Napravi bota na Telegramu

1. Otvori Telegram i trazi `@BotFather`
2. Posalji `/newbot`
3. Unesi naziv: npr. `BerberaNS Bot`
4. Unesi username: mora da se zavrsava na `bot`, npr. `berbera_ns_bot`
5. BotFather ce ti dati **TOKEN** — sacuvaj ga!

### Korak 2: Nadji svoj Telegram ID

1. U Telegramu trazi `@userinfobot`
2. Posalji `/start`
3. Bot ce ti reci tvoj ID broj — sacuvaj ga!

### Korak 3: Deploy na Railway (besplatno)

1. Idi na [railway.app](https://railway.app)
2. Registruj se GitHub nalogom
3. Klikni **New Project** → **Deploy from GitHub repo**
   - Ili: **New Project** → **Empty project** → dodaj fajlove rucno
4. Upload svih 5 fajlova iz ovog foldera
5. U **Variables** dodaj:
   ```
   BOT_TOKEN = tvoj_token_od_BotFathera
   VLASNIK_ID = tvoj_telegram_id_broj
   ```
6. Klikni **Deploy**

✅ Bot radi!

---

## Admin komande (samo za tebe)

| Komanda | Opis |
|---------|------|
| `/danas` | Svi termini za danas |
| `/sutra` | Svi termini za sutra |
| `/fiksni` | Lista svih fiksnih termina |
| `/dodaj_fiksni Pera Peric ponedeljak 10:00 sisanje` | Dodaj fiksni termin |
| `/obrisi_fiksni 3` | Obrisi fiksni termin po ID-u |
| `/otkazi_admin 5` | Otkazi termin i obavesti musteriju |

---

## Primeri — kako musterija zakazuje

```
Musterija: klikne "Zakazi termin"
Bot: "Kako se zovete?"
Musterija: "Marko Jovic"
Bot: prikazuje sledecih 7 dana sa lokacijom
Musterija: izabere datum
Bot: prikazuje slobodne termine (svaki slobodan slot po 30 min)
Musterija: izabere vreme npr. 10:00
Bot: pita za uslugu
Musterija: "Sisanje"
Bot: "Proverite podatke... Da li je sve tacno?"
Musterija: "Potvrdi"
Bot: "Termin zakazan! Vidimo se!"
Ti: dobijes notifikaciju odmah
```

---

## Struktura fajlova

```
berber_bot/
├── bot.py           — Glavni bot, sva logika razgovora
├── database.py      — Baza podataka (SQLite, bez instalacije)
├── config.py        — Podesavanja (lokacije, radno vreme)
├── requirements.txt — Python paketi
├── Procfile         — Za Railway hosting
└── README.md        — Ovo uputstvo
```

---

## Cesta pitanja

**Bot ne odgovara?**
Proveri da li je `BOT_TOKEN` ispravno postavljen u Railway Variables.

**Ne dobijem notifikacije?**
Proveri da li je `VLASNIK_ID` ispravno postavljen (samo broj, bez razmaka).

**Kako da promenim radno vreme?**
U `config.py` promeni `RADNO_OD` i `RADNO_DO`.

**Kako da dodam lokaciju?**
U `config.py` promeni `LOKACIJE` dictionary.

---

Napravljeno uz pomoc Claude AI 🤖
