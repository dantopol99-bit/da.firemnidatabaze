"""Sazba PDF (Blok 3): knihovna grafů, výklad, kontrola čísel v PDF.

Testy bez databáze běží nad vzorovým výstupem v reporty/vystupy; sazba potřebuje
typst v PATH a databázi se snímkem RES, jinak se přeskočí.
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from firemni_databaze import report_grafy, report_vyklad
from firemni_databaze.report_kontrola import cisla_v_textu, povolena_cisla, text_pdf, zkontroluj_pdf
from firemni_databaze.report_vyklad import Vstup, cz
from tests.test_res_import_db import CONN, SNIMKY

KOREN = Path(__file__).resolve().parents[1]
VZOR = KOREN / "reporty" / "vystupy" / "F__CZ051__2026-09-15"
TYPST = shutil.which("typst")


class TestBezDatabaze(unittest.TestCase):
    def test_knihovna_nejvys_8_typu(self):
        self.assertLessEqual(len(report_grafy.GRAFY), 8)

    def test_format_cisla_beze_zmeny_hodnoty(self):
        self.assertEqual(cz(14799), "14 799")
        self.assertEqual(cz(4.35), "4,35")
        self.assertEqual(cz(100.0), "100")
        self.assertEqual(cz(1.0), "1")
        self.assertEqual(cz(2947143), "2 947 143")

    def test_cisla_v_textu(self):
        self.assertEqual(cisla_v_textu("Na 1 000 obyvatel 32,99; strana 3 z 13"), {"1000", "32.99"})

    @unittest.skipUnless((VZOR / "vysledek.json").exists(), "vzorový výstup chybí")
    def test_vyklad_jen_cisla_z_json_a_xlsx(self):
        vysledek = json.loads((VZOR / "vysledek.json").read_text(encoding="utf-8"))
        povolena = povolena_cisla(VZOR)
        v = Vstup(vysledek)
        L = {k: "tab. A" for k in ("T01", "T02", "T03", "T05", "T06", "T10", "T11", "T12")}
        L |= {k: "graf A" for k in ("g_dyn", "g_hustota", "g_lq", "g_miry", "g_vek", "g_vel_fo", "g_vel_po")}
        texty = report_vyklad.shrnuti(v, L)
        for f in (report_vyklad.postaveni, report_vyklad.struktura, report_vyklad.dynamika):
            texty += [b["text"] for b in f(v, L)]
        for t in texty:
            self.assertEqual(cisla_v_textu(t) - povolena, set(), t)
            self.assertNotRegex(t.lower(), r"\bfirm|\baktivn(?!\w*\s+podnik)")

    @unittest.skipUnless((VZOR / "vysledek.json").exists(), "vzorový výstup chybí")
    def test_hypotezy_jsou_oznacene_a_druhy_ve_strukture(self):
        v = Vstup(json.loads((VZOR / "vysledek.json").read_text(encoding="utf-8")))
        L = {k: "x" for k in ("T01", "T02", "T03", "T05", "T06", "T10", "T11", "T12", "g_dyn", "g_hustota", "g_lq",
                              "g_miry", "g_vek", "g_vel_fo", "g_vel_po")}
        for f in (report_vyklad.postaveni, report_vyklad.struktura, report_vyklad.dynamika):
            bloky = f(v, L)
            druhy = [b["druh"] for b in bloky]
            self.assertEqual(druhy, sorted(druhy, key=["vidět", "proč", "plyne"].index), f.__name__)
            self.assertIn("vidět", druhy)
            self.assertIn("plyne", druhy)
            self.assertTrue(any(b["hypoteza"] for b in bloky), f"{f.__name__}: chybí označená hypotéza")


@unittest.skipIf(TYPST is None, "typst není v PATH")
class TestKontrolaPdf(unittest.TestCase):
    @unittest.skipUnless((VZOR / "vysledek.json").exists(), "vzorový výstup chybí")
    def test_cislo_mimo_json_v_pdf_se_odhali(self):
        with tempfile.TemporaryDirectory() as tmp:
            typ = Path(tmp) / "x.typ"
            typ.write_text("Registrované subjekty: 14 799. Vymyšlené číslo: 987 654.", encoding="utf-8")
            subprocess.run([TYPST, "compile", str(typ)], check=True)
            chyby = zkontroluj_pdf(Path(tmp) / "x.pdf", VZOR)
        self.assertEqual(len(chyby), 1)
        self.assertIn("987654", chyby[0])


@unittest.skipIf(TYPST is None or CONN is None or not SNIMKY, "chybí typst nebo databáze se snímkem RES")
class TestSazba(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from firemni_databaze.report import Zadani, spocitej, uloz
        cls.tmp = Path(tempfile.mkdtemp(prefix="sazba_test_"))
        vysledek, interni = spocitej(CONN, Zadani(["F"], "CZ051", srovnani=["CZ052", "CZ041"]))
        CONN.rollback()
        cls.vystup = uloz(vysledek, interni, cls.tmp)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_sazba_projde_kontrolou(self):
        from firemni_databaze.report_pdf import vysazej
        pdf = vysazej(self.vystup, self.tmp / "pdf")
        self.assertTrue(pdf.exists())
        self.assertEqual(zkontroluj_pdf(pdf, self.vystup), [])
        text = text_pdf(pdf)
        self.assertIn("KONCEPT", text)
        for kapitola in ("Shrnutí klíčových zjištění", "Postavení území", "Struktura", "Dynamika území a kontext ČR",
                         "Metodika, omezení a zdroje", "Příloha: odchylky od osnovy"):
            self.assertIn(kapitola, text)
        self.assertIn("CC BY 4.0", text)
        self.assertIn("Odvozené údaje, nejde o oficiální statistiku ČSÚ", text)

    def test_schvaleny_vyklad_bez_konceptu(self):
        from firemni_databaze.report_pdf import vysazej
        pdf = vysazej(self.vystup, self.tmp / "schvaleno", koncept=False)
        self.assertNotIn("KONCEPT", text_pdf(pdf))

    def test_nesoulad_zastavi_sazbu(self):
        from firemni_databaze.report_pdf import ChybaSazby, vysazej
        puvodni = report_vyklad.shrnuti
        with mock.patch.object(report_vyklad, "shrnuti", lambda v, L: puvodni(v, L) + ["Vymyšlených 987 654."]):
            with self.assertRaises(ChybaSazby):
                vysazej(self.vystup, self.tmp / "spatne")
        self.assertFalse((self.tmp / "spatne" / "report.pdf").exists())


if __name__ == "__main__":
    unittest.main()
