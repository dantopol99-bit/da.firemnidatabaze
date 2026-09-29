"""Testy importu RES proti databázi (schéma res).

Potřebují běžící PostgreSQL podle .env s nasazeným schématem res; testy
nad daty potřebují načtený snímek. Jinak se přeskočí.
Máš-li surové soubory snímku lokálně, nastav RES_ADRESAR=<adresář> –
pak se počet řádků a SHA-256 ověří i přímo proti souborům.

Spuštění:  python -m unittest tests.test_res_import_db
"""

import os
import tempfile
import unittest
from pathlib import Path

from firemni_databaze import res_zdroj as z
from firemni_databaze.db import get_engine
from firemni_databaze.res_import import copy_do_stagingu


def pripojeni():
    try:
        conn = get_engine().raw_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('res.snimek') IS NOT NULL")
            if not cur.fetchone()[0]:
                conn.close()
                return None
        conn.rollback()
        return conn
    except Exception:  # noqa: BLE001 – bez databáze se testy přeskočí
        return None


CONN = pripojeni()


@unittest.skipIf(CONN is None, "databáze se schématem res není dostupná")
class TestCopy(unittest.TestCase):
    """COPY načte přesně tolik řádků, kolik jich napočítá CSV parser – i v okrajových případech."""

    def tearDown(self):
        CONN.rollback()

    def test_copy_okrajove_pripady(self):
        hlavicka = ",".join(z.SLOUPCE["res_data.csv"])
        prazdne = "," * 11
        radky = [
            # uvozovky, čárka a zdvojená uvozovka v názvu, prázdné "" v TEXTADR
            f'00000123,CZ0100,1990-01-01,,,2026-01-15,301,301,000,702,70200,500178,'
            f'"TECHNOMAT, státní podnik ""v likvidaci""",11001,1,"",16000,Praha,Dejvice,X,1,1,1,2026-09-15,Z',
            # zaniklá FO: jen IČO a datum zániku
            f"00000124,,,2024-05-31,,,,,,,,,{prazdne}2026-09-15,",
            # zalomení řádku uvnitř uvozovek
            f'00000125,CZ0513,2001-02-03,,,2026-01-15,112,112,110,4120,41000,563889,'
            f'"Dva\r\nřádky s.r.o.",11002,2,"",46001,Liberec,Liberec I,Y,1,2,,2026-09-15,',
        ]
        with tempfile.TemporaryDirectory() as tmp:
            cesta = Path(tmp) / "res_data.csv"
            cesta.write_bytes(("\r\n".join([hlavicka, *radky]) + "\r\n").encode("utf-8"))
            souhrn = z.souhrn_souboru(cesta)
            with CONN.cursor() as cur:
                nacteno, pocet_dat, datplat = copy_do_stagingu(cur, "res_data.csv", cesta)
                cur.execute('SELECT "FIRMA", "TEXTADR", "OKRESLAU" FROM stg_res ORDER BY "ICO"')
                obsah = cur.fetchall()
        self.assertEqual(souhrn.pocet_radku, 3)
        self.assertEqual(nacteno, souhrn.pocet_radku)
        self.assertEqual((pocet_dat, datplat), (1, "2026-09-15"))
        self.assertEqual(obsah[0], ('TECHNOMAT, státní podnik "v likvidaci"', None, "CZ0100"))
        self.assertEqual(obsah[1], (None, None, None))
        self.assertEqual(obsah[2][0], "Dva\r\nřádky s.r.o.")

    def test_copy_odmitne_jinou_hlavicku(self):
        with tempfile.TemporaryDirectory() as tmp:
            cesta = Path(tmp) / "res_data.csv"
            cesta.write_bytes(b"ICO,DATPLAT\r\n00000123,2026-09-15\r\n")
            with CONN.cursor() as cur, self.assertRaises(Exception):
                copy_do_stagingu(cur, "res_data.csv", cesta)


def snimky():
    if CONN is None:
        return []
    with CONN.cursor() as cur:
        cur.execute("SELECT id, datum_snimku, soubor, pocet_radku, sha256 FROM res.snimek ORDER BY id")
        vysledek = cur.fetchall()
    CONN.rollback()
    return vysledek


SNIMKY = snimky()


@unittest.skipIf(not SNIMKY, "v databázi není načtený žádný snímek RES")
class TestImportovanySnimek(unittest.TestCase):
    def tearDown(self):
        CONN.rollback()

    def dotaz(self, sql, parametry=()):
        with CONN.cursor() as cur:
            cur.execute(sql, parametry)
            return cur.fetchall()

    def test_pocty_radku_odpovidaji_souboru(self):
        adresar = os.environ.get("RES_ADRESAR")
        for snimek_id, datum, soubor, pocet_radku, sha256 in SNIMKY:
            tabulka = z.TABULKY[soubor]
            (v_tabulce,), = self.dotaz(f"SELECT count(*) FROM res.{tabulka} WHERE snimek_id = %s", (snimek_id,))
            self.assertEqual(v_tabulce, pocet_radku, f"{soubor} k {datum}")
            if adresar and (Path(adresar) / soubor).exists():
                souhrn = z.souhrn_souboru(Path(adresar) / soubor)
                if souhrn.sha256 == sha256:   # stejný soubor jako v databázi
                    self.assertEqual(souhrn.pocet_radku, pocet_radku, f"{soubor}: soubor × res.snimek")

    def test_snimek_ma_oba_soubory(self):
        podle_data = {}
        for _, datum, soubor, _, _ in SNIMKY:
            podle_data.setdefault(datum, set()).add(soubor)
        for datum, soubory in podle_data.items():
            self.assertEqual(soubory, set(z.SLOUPCE), datum)

    def test_pk_bez_duplicit(self):
        (duplicity,), = self.dotaz(
            "SELECT count(*) - count(DISTINCT (ico, datum_snimku)) FROM res.subjekt")
        self.assertEqual(duplicity, 0)
        (duplicity,), = self.dotaz(
            "SELECT count(*) - count(DISTINCT (ico, datum_snimku, coalesce(kodcis, '∅'), "
            "coalesce(zdrud, '∅'), coalesce(hodn, '∅'))) FROM res.pf_nace")
        self.assertEqual(duplicity, 0)

    def test_kazdy_okres_a_kraj_z_ciselniku(self):
        neznamy_okres = self.dotaz(
            "SELECT DISTINCT s.okreslau FROM res.subjekt s "
            "LEFT JOIN res.cis_okres o ON o.kod = s.okreslau "
            "WHERE s.okreslau IS NOT NULL AND o.kod IS NULL")
        self.assertEqual(neznamy_okres, [], "OKRESLAU mimo číselník 109")
        kraje_subjektu = self.dotaz(
            "SELECT DISTINCT o.kraj_kod FROM res.subjekt s JOIN res.cis_okres o ON o.kod = s.okreslau "
            "WHERE s.datum_snimku = res.posledni_snimek()")
        kraje_ciselniku = self.dotaz("SELECT kod FROM res.cis_kraj WHERE kod_ruian IS NOT NULL")
        self.assertEqual(len(kraje_ciselniku), 14)
        self.assertEqual(sorted(kraje_subjektu), sorted(kraje_ciselniku),
                         "subjekty musí ležet ve všech 14 krajích z číselníku a nikde jinde")

    def test_subjekt_bez_zaniku_ma_kraj(self):
        (bez_kraje,), = self.dotaz(
            "SELECT count(*) FROM res.v_subjekt WHERE datum_snimku = res.posledni_snimek() "
            "AND NOT je_zanikly AND kraj_kod IS NULL")
        self.assertEqual(bez_kraje, 0)

    def test_kvalita_ulozena(self):
        for _, datum, soubor, pocet_radku, _ in SNIMKY:
            if soubor != "res_data.csv":
                continue
            radky = self.dotaz(
                "SELECT pocet FROM res.kvalita WHERE datum_snimku = %s AND zaklad = 'vse' AND ukazatel = 'radky'",
                (datum,))
            self.assertEqual(radky, [(pocet_radku,)], datum)


if __name__ == "__main__":
    unittest.main()
