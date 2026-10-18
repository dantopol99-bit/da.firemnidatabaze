"""CZ-NACE 2008 / 2025: číselníky, převodník, pravidla odvození, SQL schématu obor (bez databáze)."""

import csv
import re
import unittest

from firemni_databaze import nace_ciselniky as nc
from firemni_databaze.nace_firmy import MIN_ZAKLAD, pravidlo
from firemni_databaze.nasad_sql import sql_soubory


def nacti(soubor):
    with open(nc.ADRESAR / soubor, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


class TestNormalizace(unittest.TestCase):
    def test_kody_bez_tecek(self):
        self.assertEqual(nc.normalizuj_kod("01.47.0 (částečně)"), ("01470", True))
        self.assertEqual(nc.normalizuj_kod("24.10.3\n(částečně)"), ("24103", True))
        self.assertEqual(nc.normalizuj_kod("41.2"), ("412", False))
        self.assertEqual(nc.normalizuj_kod("F"), ("F", False))


class TestCiselnik(unittest.TestCase):
    def test_hierarchie_a_pseudokody(self):
        polozky = [
            {"chodnota": "F", "uroven": "1", "nadvaz": None, "text": "Stavebnictví"},
            {"chodnota": "41", "uroven": "2", "nadvaz": "F", "text": "Výstavba budov"},
            {"chodnota": "412", "uroven": "3", "nadvaz": "41", "text": "x"},
            {"chodnota": "4120", "uroven": "4", "nadvaz": "412", "text": "x"},
            {"chodnota": "41201", "uroven": "5", "nadvaz": "4120", "text": "x"},
        ]
        radky = {r["kod"]: r for r in nc.radky_ciselniku(polozky, 2008, "test")}
        self.assertEqual((radky["41201"]["sekce"], radky["41201"]["oddil"], radky["41201"]["trida"]),
                         ("F", "41", "4120"))
        self.assertEqual(radky["41"]["oddil"], "41")
        self.assertTrue(radky["00"]["je_pseudokod"])
        self.assertEqual(radky["00"]["sekce"], "Y")
        self.assertEqual(radky["04"]["sekce"], "X")
        self.assertFalse(radky["F"]["je_pseudokod"])

    def test_neznamy_predek(self):
        with self.assertRaises(ValueError):
            nc.radky_ciselniku([{"chodnota": "41", "uroven": "2", "nadvaz": "Q", "text": "x"}], 2025, "test")

    def test_csv_v_repozitari(self):
        radky = nacti(nc.SOUBOR_CISELNIK)
        for verze, sekci in (("2008", 21), ("2025", 22)):
            sekce = {r["kod"] for r in radky if r["verze"] == verze and r["uroven"] == "1" and r["je_pseudokod"] == "false"}
            self.assertEqual(len(sekce), sekci, verze)
            for uroven in "12345":
                self.assertTrue(any(r["verze"] == verze and r["uroven"] == uroven for r in radky), (verze, uroven))
        # kód podle délky (bez teček), verze výslovně
        for r in radky:
            self.assertRegex(r["kod"], r"^([A-Z]|[0-9]{2,5})$")
            if r["kod"].isdigit():
                self.assertEqual(len(r["kod"]), int(r["uroven"]), r)


class TestPrevodnik(unittest.TestCase):
    def test_typy_vazby(self):
        pary = [nc.Par("a", "x", 4, False, "t"), nc.Par("b", "y", 4, False, "t"), nc.Par("b", "z", 4, False, "t"),
                nc.Par("c", "w", 4, False, "t"), nc.Par("d", "w", 4, False, "t"),
                nc.Par("e", "v", 4, False, "t"), nc.Par("e", "u", 4, False, "t"), nc.Par("f", "u", 4, False, "t")]
        typy = {(r["kod_2008"], r["kod_2025"]): r["typ_vazby"] for r in nc.typy_vazby(pary)}
        self.assertEqual(typy[("a", "x")], "1:1")
        self.assertEqual(typy[("b", "y")], "1:N")
        self.assertEqual(typy[("c", "w")], "N:1")
        self.assertEqual(typy[("e", "u")], "N:M")
        self.assertEqual(typy[("e", "v")], "1:N")

    def test_csv_odpovida_ciselniku(self):
        ciselnik = [{**r, "verze": int(r["verze"]), "uroven": int(r["uroven"])} for r in nacti(nc.SOUBOR_CISELNIK)]
        prevodnik = [{**r, "uroven": int(r["uroven"])} for r in nacti(nc.SOUBOR_PREVODNIK)]
        self.assertEqual(nc.over_prevodnik(prevodnik, ciselnik), [])
        # každá třída obou verzí (kromě 2025 46.89 bez předchůdce) má v převodníku vazbu
        tridy08 = {r["kod"] for r in ciselnik if r["verze"] == 2008 and r["uroven"] == 4}
        tridy25 = {r["kod"] for r in ciselnik if r["verze"] == 2025 and r["uroven"] == 4}
        self.assertEqual(tridy08 - {r["kod_2008"] for r in prevodnik if r["uroven"] == 4}, set())
        self.assertEqual(tridy25 - {r["kod_2025"] for r in prevodnik if r["uroven"] == 4}, {"4689"})

    def test_a10(self):
        from firemni_databaze.report import SKUPINY_A10

        a10 = nacti(nc.SOUBOR_A10)
        sekce25 = {r["kod"] for r in nacti(nc.SOUBOR_CISELNIK)
                   if r["verze"] == "2025" and r["uroven"] == "1" and r["je_pseudokod"] == "false"}
        self.assertEqual({r["sekce_2025"] for r in a10}, sekce25)
        for r in a10:
            # skupina A*10 sedí s tou, kterou report používá pro odpovídající sekci Rev. 2
            self.assertEqual(SKUPINY_A10[r["sekce_rev2"]][0], r["a10_rev2"], r)


class TestPravidlo(unittest.TestCase):
    def setUp(self):
        def c(verze, kod, uroven, sekce, oddil=None, skupina=None, trida=None):
            return (verze, kod), {"verze": verze, "kod": kod, "uroven": uroven, "sekce": sekce, "oddil": oddil,
                                  "skupina": skupina, "trida": trida}

        self.ciselnik = dict([
            c(2008, "F", 1, "F"), c(2008, "41", 2, "F", "41"), c(2008, "4120", 4, "F", "41", "412", "4120"),
            c(2008, "J", 1, "J"), c(2008, "62", 2, "J", "62"), c(2008, "6201", 4, "J", "62", "620", "6201"),
            c(2008, "6209", 4, "J", "62", "620", "6209"),
            c(2025, "F", 1, "F"), c(2025, "41", 2, "F", "41"), c(2025, "4100", 4, "F", "41", "410", "4100"),
            c(2025, "43", 2, "F", "43"), c(2025, "4399", 4, "F", "43", "439", "4399"),
            c(2025, "K", 1, "K"), c(2025, "62", 2, "K", "62"), c(2025, "6210", 4, "K", "62", "621", "6210"),
            c(2025, "6290", 4, "K", "62", "629", "6290"),
        ])
        self.prevodnik = {"4120": [("4100", "1:N"), ("4399", "N:M")], "6201": [("6210", "1:1")],
                          "6209": [("6210", "N:M"), ("6290", "N:M")], "F": [("F", "N:M")], "J": [("K", "N:M")],
                          "41": [("41", "1:N"), ("43", "N:M")]}

    def test_vazba_1_1(self):
        p = pravidlo("6201", 4, self.ciselnik, self.prevodnik, {})
        self.assertEqual((p.kod_2025, p.jistota, p.metoda), ("6210", 1.0, "prevodnik_1:1"))
        p = pravidlo("6201", 1, self.ciselnik, self.prevodnik, {})       # předek cíle 1:1
        self.assertEqual((p.kod_2025, p.metoda), ("K", "prevodnik_1:1"))

    def test_jediny_cil_na_vyssi_urovni(self):
        # 6209 se dělí na dvě třídy, ale obě jsou v oddílu 62 → oddíl je jistý
        p = pravidlo("6209", 2, self.ciselnik, self.prevodnik, {})
        self.assertEqual((p.kod_2025, p.jistota, p.metoda), ("62", 1.0, "prevodnik_jediny_cil"))

    def test_empiricky(self):
        matice = {("4120", 4): ("4100", 90, 100)}
        p = pravidlo("4120", 4, self.ciselnik, self.prevodnik, matice)
        self.assertEqual((p.kod_2025, p.jistota, p.metoda, p.zaklad), ("4100", 0.9, "empiricky", 100))

    def test_maly_zaklad_je_nejednoznacny(self):
        matice = {("4120", 4): ("4100", MIN_ZAKLAD - 2, MIN_ZAKLAD - 1)}
        p = pravidlo("4120", 4, self.ciselnik, self.prevodnik, matice)
        self.assertIsNone(p.kod_2025)
        self.assertEqual((p.metoda, p.kandidati), ("nejednoznacne", ("4100", "4399")))
        p = pravidlo("4120", 1, self.ciselnik, self.prevodnik, matice)   # sekce je ale jistá
        self.assertEqual((p.kod_2025, p.metoda), ("F", "prevodnik_jediny_cil"))


def bez_komentaru(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


class TestSqlObor(unittest.TestCase):
    def setUp(self):
        self.soubory = sql_soubory("obor")
        self.sql = {s.name: bez_komentaru(s.read_text(encoding="utf-8")).lower() for s in self.soubory}

    def test_skripty_jsou_cislovane_a_idempotentni(self):
        self.assertGreater(len(self.soubory), 0)
        for nazev, sql in self.sql.items():
            self.assertRegex(nazev, r"^\d{2}_[a-z_]+\.sql$")
            for prikaz in re.findall(r"\bcreate\s+(?!or\s+replace)(?!temp)(\w+(?:\s+\w+)?)", sql):
                self.assertRegex(prikaz, r"^(schema|table|unique index|index)", nazev)
            self.assertNotRegex(sql, r"\bcreate\s+(schema|table|unique\s+index|index)\s+(?!if\s+not\s+exists)", nazev)

    def test_nemaze_ani_nemeni_jine_schema(self):
        zakazane = re.compile(r"\b(drop|truncate|delete\s+from|insert\s+into|update)\s+(dev|res)\.|\bdrop\s+table\b")
        for nazev, sql in self.sql.items():
            self.assertIsNone(zakazane.search(sql), nazev)


if __name__ == "__main__":
    unittest.main()
