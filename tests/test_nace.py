"""CZ-NACE 2008 / 2025: číselníky, převodník, pravidla odvození, SQL schématu obor (bez databáze)."""

import csv
import re
import unittest

from firemni_databaze import nace_ciselniky as nc
from datetime import date

from firemni_databaze import nace_firmy as nf
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

    def test_podtridy_bez_narodniho_cleneni_maji_prevod_trid(self):
        # regrese: 16.29.0 (2008) býval jen dílčím zdrojem 15.20.9 (2025) a přišel o převod na 16.26–16.28
        ciselnik = nacti(nc.SOUBOR_CISELNIK)
        l5 = {v: {r["kod"] for r in ciselnik if r["verze"] == v and r["uroven"] == "5"} for v in ("2008", "2025")}
        pary = {(r["kod_2008"], r["kod_2025"]) for r in nacti(nc.SOUBOR_PREVODNIK)}
        for r in nacti(nc.SOUBOR_PREVODNIK):
            if r["uroven"] == "4" and r["kod_2008"] + "0" in l5["2008"] and r["kod_2025"] + "0" in l5["2025"]:
                self.assertIn((r["kod_2008"] + "0", r["kod_2025"] + "0"), pary, r)
        self.assertTrue({("16290", "16280"), ("16290", "15209")} <= pary)

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


class TestRozhodnuti(unittest.TestCase):
    """Rozhodnutí z 19. 10. 2026 (docs/cz-nace-2025.md, kap. 1)."""

    def setUp(self):
        def c(verze, kod, uroven, sekce, oddil=None, skupina=None, trida=None):
            return (verze, kod), {"verze": verze, "kod": kod, "uroven": uroven, "sekce": sekce, "oddil": oddil,
                                  "skupina": skupina, "trida": trida}

        self.ciselnik = dict([
            c(2008, "S", 1, "S"), c(2008, "96", 2, "S", "96"), c(2008, "9609", 4, "S", "96", "960", "9609"),
            c(2008, "9601", 4, "S", "96", "960", "9601"), c(2008, "9602", 4, "S", "96", "960", "9602"),
            c(2025, "T", 1, "T"), c(2025, "96", 2, "T", "96"), c(2025, "9699", 4, "T", "96", "969", "9699"),
            c(2025, "9691", 4, "T", "96", "969", "9691"), c(2025, "9610", 4, "T", "96", "961", "9610"),
        ])
        # 9601 a 9602 se slučují do 9610 (vazba N:1); 9609 → 9699 je vazba 1:1
        self.prevodnik = {"9601": [("9610", "N:1")], "9602": [("9610", "N:1")], "9609": [("9699", "1:1")]}

    def test_1_vazba_n_1_ma_jistotu_1(self):
        p = pravidlo("9601", 4, self.ciselnik, self.prevodnik, {})
        self.assertEqual((p.kod_2025, p.jistota, p.metoda), ("9610", 1.0, "prevodnik_jediny_cil"))
        # i když empirie ukazuje 85 % (pod prahem rozporu), platí převodník
        p = pravidlo("9601", 4, self.ciselnik, self.prevodnik, {("9601", 4): ("9699", 85, 100)})
        self.assertEqual((p.kod_2025, p.jistota), ("9610", 1.0))

    def test_2_rozpor_rozhoduje_empirie(self):
        matice = {("9609", 4): ("9691", 14_536, 14_653)}
        p = pravidlo("9609", 4, self.ciselnik, self.prevodnik, matice)
        self.assertEqual((p.kod_2025, p.metoda, p.cil_prevodnik), ("9691", "empiricky_rozpor", "9699"))
        self.assertAlmostEqual(p.jistota, 0.992, places=3)

    def test_2_rozpor_jen_nad_prahy(self):
        # podíl pod 0,9 → převodník
        p = pravidlo("9609", 4, self.ciselnik, self.prevodnik, {("9609", 4): ("9691", 89, 100)})
        self.assertEqual((p.kod_2025, p.metoda), ("9699", "prevodnik_1:1"))
        # základ pod 20 → převodník
        p = pravidlo("9609", 4, self.ciselnik, self.prevodnik, {("9609", 4): ("9691", MIN_ZAKLAD - 1, MIN_ZAKLAD - 1)})
        self.assertEqual((p.kod_2025, p.metoda), ("9699", "prevodnik_1:1"))
        # empirie se shoduje s převodníkem → žádný rozpor
        p = pravidlo("9609", 4, self.ciselnik, self.prevodnik, {("9609", 4): ("9699", 99, 100)})
        self.assertEqual((p.metoda, p.cil_prevodnik), ("prevodnik_1:1", None))

    def test_6_kod_2025_nejdriv_od_1_1_2025(self):
        self.assertEqual(nf._nejdriv_2025("2023-06-29"), "2025-01-01")
        self.assertEqual(nf._nejdriv_2025("2026-01-15"), "2026-01-15")
        self.assertIsNone(nf._nejdriv_2025(None))

    def test_7_konec_dvojiho_kodovani(self):
        self.assertFalse(nf.je_konec_dvojiho_kodovani(date(2026, 10, 15), 3_038_940))
        self.assertFalse(nf.je_konec_dvojiho_kodovani(date(2028, 12, 31), 1))
        self.assertTrue(nf.je_konec_dvojiho_kodovani(date(2029, 1, 15), 3_000_000))   # po 31. 12. 2028
        self.assertTrue(nf.je_konec_dvojiho_kodovani(date(2027, 6, 30), 0))           # zdroj přestal dodávat


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
            for prikaz in re.findall(r"\bcreate\s+(?!or\s+replace)(?!temp)(\w+(?:\s+[\w.]+)?)", sql):
                if prikaz.startswith("view "):
                    # pohled bez OR REPLACE jen po DROP VIEW IF EXISTS téhož pohledu (nedrží data)
                    self.assertIn(f"drop view if exists {prikaz[5:]};", sql, nazev)
                    continue
                self.assertRegex(prikaz, r"^(schema|table|unique index|index|materialized view)", nazev)
            self.assertNotRegex(
                sql, r"\bcreate\s+(schema|table|unique\s+index|index|materialized\s+view)\s+(?!if\s+not\s+exists)", nazev)
            self.assertNotRegex(sql, r"\bdrop\s+(table|materialized\s+view)\b", nazev)

    def test_nemaze_ani_nemeni_jine_schema(self):
        zakazane = re.compile(r"\b(drop|truncate|delete\s+from|insert\s+into|update)\s+(dev|res)\.|\bdrop\s+table\b")
        for nazev, sql in self.sql.items():
            self.assertIsNone(zakazane.search(sql), nazev)


if __name__ == "__main__":
    unittest.main()
