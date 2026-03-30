"""
Baza podataka za Berber Bot.
Koristi SQLite — bez instalacije, radi svuda.
Fajl se cuvaj lokalno kao berber.db
"""

import sqlite3
import os
from datetime import date, datetime

DB_PATH = os.environ.get("DB_PATH", "berber.db")


class Database:
    def __init__(self):
        self.db_path = DB_PATH
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Kreira tabele ako ne postoje."""
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS termini (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id     INTEGER NOT NULL,
                    ime         TEXT NOT NULL,
                    datum       TEXT NOT NULL,
                    vreme       TEXT NOT NULL,
                    lokacija    TEXT NOT NULL,
                    usluga      TEXT NOT NULL,
                    status      TEXT NOT NULL DEFAULT 'aktivan',
                    telefon     TEXT DEFAULT '',
                    kreirano    TEXT NOT NULL DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS fiksni_termini (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    ime         TEXT NOT NULL,
                    dan_nedelje INTEGER NOT NULL,
                    vreme       TEXT NOT NULL,
                    lokacija    TEXT NOT NULL,
                    usluga      TEXT NOT NULL DEFAULT 'Sisanje',
                    aktivan     INTEGER NOT NULL DEFAULT 1
                );

                CREATE INDEX IF NOT EXISTS idx_termini_datum
                    ON termini(datum, status);
                CREATE INDEX IF NOT EXISTS idx_termini_user
                    ON termini(user_id, status);
                CREATE INDEX IF NOT EXISTS idx_fiksni_dan
                    ON fiksni_termini(dan_nedelje, aktivan);
            """)

    # ─── TERMINI ────────────────────────────────────────────────

    def dodaj_termin(self, user_id, ime, datum, vreme, lokacija, usluga, telefon=""):
        with self._get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO termini (user_id, ime, datum, vreme, lokacija, usluga, telefon)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, ime, datum, vreme, lokacija, usluga, telefon)
            )
            return cur.lastrowid

    def get_termini_korisnika_telefon(self, telefon):
        danas = date.today().isoformat()
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM termini
                   WHERE telefon = ? AND datum >= ? AND status = 'aktivan'
                   ORDER BY datum, vreme""",
                (telefon, danas)
            ).fetchall()
            return [dict(r) for r in rows]

    def je_termin_zauzet(self, datum: date, vreme: str) -> bool:
        """Provjerava da li je termin zauzet (ukljucujuci fiksne)."""
        datum_str = datum.isoformat()
        with self._get_conn() as conn:
            # Provjeri regularne termine
            row = conn.execute(
                """SELECT id FROM termini
                   WHERE datum = ? AND vreme = ? AND status = 'aktivan'
                   LIMIT 1""",
                (datum_str, vreme)
            ).fetchone()
            if row:
                return True

            # Provjeri fiksne termine
            dan = datum.weekday()
            row = conn.execute(
                """SELECT id FROM fiksni_termini
                   WHERE dan_nedelje = ? AND vreme = ? AND aktivan = 1
                   LIMIT 1""",
                (dan, vreme)
            ).fetchone()
            return row is not None

    def get_termini_za_datum(self, datum: date) -> list[dict]:
        datum_str = datum.isoformat()
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM termini
                   WHERE datum = ? AND status = 'aktivan'
                   ORDER BY vreme""",
                (datum_str,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_termini_korisnika(self, user_id: int) -> list[dict]:
        """Vraca nadolazece termine korisnika."""
        danas = date.today().isoformat()
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM termini
                   WHERE user_id = ? AND datum >= ? AND status = 'aktivan'
                   ORDER BY datum, vreme""",
                (user_id, danas)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_termin_po_id(self, termin_id: int) -> dict | None:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM termini WHERE id = ?", (termin_id,)
            ).fetchone()
            return dict(row) if row else None

    def otkazi_termin(self, termin_id: int):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE termini SET status = 'otkazan' WHERE id = ?",
                (termin_id,)
            )

    # ─── FIKSNI TERMINI ─────────────────────────────────────────

    def dodaj_fiksni_termin(self, ime: str, dan_nedelje: int,
                             vreme: str, lokacija: str, usluga: str) -> int:
        with self._get_conn() as conn:
            cur = conn.execute(
                """INSERT INTO fiksni_termini (ime, dan_nedelje, vreme, lokacija, usluga)
                   VALUES (?, ?, ?, ?, ?)""",
                (ime, dan_nedelje, vreme, lokacija, usluga)
            )
            return cur.lastrowid

    def obrisi_fiksni_termin(self, fiksni_id: int):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE fiksni_termini SET aktivan = 0 WHERE id = ?",
                (fiksni_id,)
            )

    def get_fiksni_termini_za_dan(self, dan_nedelje: int) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM fiksni_termini
                   WHERE dan_nedelje = ? AND aktivan = 1
                   ORDER BY vreme""",
                (dan_nedelje,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_svi_fiksni_termini(self) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT * FROM fiksni_termini
                   WHERE aktivan = 1
                   ORDER BY dan_nedelje, vreme"""
            ).fetchall()
            return [dict(r) for r in rows]

    # ─── STATISTIKA ─────────────────────────────────────────────

    def get_statistika(self) -> dict:
        with self._get_conn() as conn:
            ukupno = conn.execute(
                "SELECT COUNT(*) FROM termini WHERE status = 'aktivan'"
            ).fetchone()[0]
            ovaj_mesec = conn.execute(
                """SELECT COUNT(*) FROM termini
                   WHERE status = 'aktivan'
                   AND strftime('%Y-%m', datum) = strftime('%Y-%m', 'now')"""
            ).fetchone()[0]
            return {"ukupno_aktivnih": ukupno, "ovaj_mesec": ovaj_mesec}
