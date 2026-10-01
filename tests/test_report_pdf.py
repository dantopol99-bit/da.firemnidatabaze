"""Sazba PDF (Bloky 3 a 4): knihovna grafů, dvouvrstvý výklad, kontrola čísel v PDF.

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
L_VSE = {f"T{i:02d}": "tab. A" for i in range(1, 20)} | {
    k: "graf A" for k in ("g_dyn", "g_fopo", "g_hustota", "g_lq", "g_miry", "g_vek", "g_vel_fo", "g_vel_po", "g_zanik")}
VYKLAD_HOTOVY = """# Výklad analytika

<!-- pokyn pro analytika se do sazby nedostane -->

## Shrnutí

Kraj má 14 799 registrovaných subjektů oboru.

Druhý bod shrnutí analytika.

## Postavení území

### Proč to tak může být

První odstavec bez čísel.

Hypotéza: obor sídlí jinde, než působí.

### Co z toho plyne

Srovnávat podle hustoty.

## Struktura

### Proč to tak může být

Text.

### Co z toho plyne

Text.

## Dynamika území a kontext ČR

### Proč to tak může být

Text.

### Co z toho plyne

Text.
"""


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

    def texty_stroje(self, L):
        v = Vstup(json.loads((VZOR / "vysledek.json").read_text(encoding="utf-8")))
        texty = report_vyklad.zjisteni_priloha(v, L)
        bloky = []
        for f in (report_vyklad.postaveni, report_vyklad.struktura, report_vyklad.dynamika):
            bloky += f(v, L)
        return texty + [b["text"] for b in bloky], bloky

    @unittest.skipUnless((VZOR / "vysledek.json").exists(), "vzorový výstup chybí")
    def test_vyklad_jen_cisla_z_json_a_xlsx(self):
        povolena = povolena_cisla(VZOR)
        texty, _ = self.texty_stroje(L_VSE)
        for t in texty:
            self.assertEqual(cisla_v_textu(t) - povolena, set(), t)
            self.assertNotRegex(t.lower(), r"\bfirm|\baktivn(?!\w*\s+podnik)")

    @unittest.skipUnless((VZOR / "vysledek.json").exists(), "vzorový výstup chybí")
    def test_stroj_pise_jen_co_je_videt_a_zjisteni(self):
        """Rozhodnutí 12: „proč“ a „co z toho plyne“ ani hypotézy stroj nepíše."""
        texty, bloky = self.texty_stroje(L_VSE)
        self.assertEqual({b["druh"] for b in bloky}, {"vidět", "zjištění"})
        self.assertFalse(any(b["hypoteza"] for b in bloky))
        for t in texty:
            self.assertNotIn("Hypotéza", t)
            self.assertNotIn("U PO je u", t)
            self.assertNotRegex(t, r"[Vv] území [A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]")

    @unittest.skipUnless((VZOR / "vysledek.json").exists(), "vzorový výstup chybí")
    def test_priloha_obsahuje_vsechna_zjisteni(self):
        v = Vstup(json.loads((VZOR / "vysledek.json").read_text(encoding="utf-8")))
        priloha = report_vyklad.zjisteni_priloha(v, L_VSE)
        self.assertEqual(len(priloha), len(v.zjisteni))
        for z, b in zip(v.zjisteni, priloha):
            self.assertTrue(b.startswith(z["id"]), b)

    def test_mezery_mezi_cislicemi_jsou_oddelovac_tisicu(self):
        self.assertEqual(report_vyklad.tisice("na 1 000 obyvatel, 14 799 subjektů"),
                         "na 1\u202f000 obyvatel, 14\u202f799 subjektů")
        self.assertEqual(report_vyklad.tisice("1. 1.–15. 9. 2026"), "1. 1.–15. 9. 2026")
        self.assertEqual(cisla_v_textu(report_vyklad.tisice("na 1 000 obyvatel")), {"1000"})

    @unittest.skipUnless((VZOR / "vysledek.json").exists(), "vzorový výstup chybí")
    def test_spatne_tisicove_cislo_kontrola_zachyti(self):
        """Bez převodu by „14 798“ prošlo jako „14“ a „798“; s převodem je to číslo 14798, které v datech není."""
        povolena = povolena_cisla(VZOR)
        with tempfile.TemporaryDirectory() as tmp:
            cesta = Path(tmp) / "X.md"
            cesta.write_text(VYKLAD_HOTOVY.replace("14 799", "14 798"), encoding="utf-8")
            _, bloky = report_vyklad.nacti_vyklad_analytika(cesta)
        self.assertEqual(cisla_v_textu(bloky["shrnuti"][0]["text"]) - povolena, {"14798"})
        dobre = report_vyklad.tisice("Kraj má 14 799 registrovaných subjektů oboru.")
        self.assertEqual(cisla_v_textu(dobre) - povolena, set())

    def test_vyklad_analytika(self):
        with tempfile.TemporaryDirectory() as tmp:
            cesta = Path(tmp) / "X.md"
            self.assertEqual(report_vyklad.nacti_vyklad_analytika(cesta)[0], "chybi")
            cesta.write_text(report_vyklad.sablona_vykladu({"meta": {
                "obor_popis": "F", "uzemi": {"nazev": "Liberecký kraj"}, "zadani": {"datum_snimku": "2026-09-15"}}},
                "X"), encoding="utf-8")
            self.assertEqual(report_vyklad.nacti_vyklad_analytika(cesta)[0], "zastupny")
            cesta.write_text(VYKLAD_HOTOVY, encoding="utf-8")
            stav, bloky = report_vyklad.nacti_vyklad_analytika(cesta)
        self.assertEqual(stav, "hotovy")
        self.assertEqual([b["druh"] for b in bloky["shrnuti"]], ["shrnutí", "shrnutí"])
        self.assertEqual([b["druh"] for b in bloky["postaveni"]], ["proč", "proč", "plyne"])
        self.assertTrue(bloky["postaveni"][1]["hypoteza"])
        self.assertFalse(bloky["postaveni"][1]["text"].startswith("Hypotéza"))

    def test_chybejici_nebo_zastupne_shrnuti_blokuje_schvaleni(self):
        with tempfile.TemporaryDirectory() as tmp:
            cesta = Path(tmp) / "X.md"
            cesta.write_text(VYKLAD_HOTOVY.replace("## Shrnutí", "## Něco jiného"), encoding="utf-8")
            self.assertEqual(report_vyklad.nacti_vyklad_analytika(cesta)[0], "zastupny")
            cesta.write_text(VYKLAD_HOTOVY.replace("Druhý bod shrnutí analytika.", "ZÁSTUPNÝ TEXT – doplní analytik."),
                             encoding="utf-8")
            self.assertEqual(report_vyklad.nacti_vyklad_analytika(cesta)[0], "zastupny")

    def test_pilotni_vyklad_je_hotovy(self):
        soubor = KOREN / "reporty" / "vyklad" / "F__CZ051__2026-09-15.md"
        stav, bloky = report_vyklad.nacti_vyklad_analytika(soubor)
        self.assertEqual(stav, "hotovy")
        self.assertEqual(set(bloky), {"shrnuti", "postaveni", "struktura", "dynamika"})


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

    def vyklady(self, text: str | None) -> Path:
        adresar = Path(tempfile.mkdtemp(prefix="vyklad_", dir=self.tmp))
        if text is not None:
            (adresar / f"{self.vystup.name}.md").write_text(text, encoding="utf-8")
        return adresar

    def test_schvaleny_vyklad_bez_konceptu(self):
        from firemni_databaze.report_pdf import vysazej
        pdf = vysazej(self.vystup, self.tmp / "schvaleno", koncept=False, adresar_vykladu=self.vyklady(VYKLAD_HOTOVY))
        text = text_pdf(pdf)
        self.assertNotIn("KONCEPT", text)
        self.assertIn("obor sídlí jinde, než působí", text)
        self.assertIn("Druhý bod shrnutí analytika", text)
        self.assertIn("Příloha: zjištění detektoru", text)
        self.assertNotIn("pokyn pro analytika", text)
        self.assertEqual(zkontroluj_pdf(pdf, self.vystup), [])

    def test_schvaleni_blokuje_chybejici_a_zastupny_vyklad(self):
        from firemni_databaze.report_pdf import ChybaSazby, vysazej
        from firemni_databaze.report_vyklad import sablona_vykladu
        vysledek = json.loads((self.vystup / "vysledek.json").read_text(encoding="utf-8"))
        bez_shrnuti = VYKLAD_HOTOVY.replace("## Shrnutí", "## Něco jiného")
        for text in (None, sablona_vykladu(vysledek, self.vystup.name), bez_shrnuti):
            with self.assertRaises(ChybaSazby):
                vysazej(self.vystup, self.tmp / "neschvaleno", koncept=False, adresar_vykladu=self.vyklady(text))
            # jako KONCEPT se vysázet dá
            pdf = vysazej(self.vystup, self.tmp / "koncept", koncept=True, adresar_vykladu=self.vyklady(text))
            self.assertIn("KONCEPT", text_pdf(pdf))

    def test_kontrola_cisel_plati_i_na_vyklad_analytika(self):
        from firemni_databaze.report_pdf import ChybaSazby, vysazej
        spatny = VYKLAD_HOTOVY.replace("Srovnávat podle hustoty.", "Obor vzroste o 987 654 subjektů.")
        with self.assertRaises(ChybaSazby):
            vysazej(self.vystup, self.tmp / "spatny_vyklad", koncept=False, adresar_vykladu=self.vyklady(spatny))
        zakazany = VYKLAD_HOTOVY.replace("Srovnávat podle hustoty.", "Aktivních firem je málo.")
        with self.assertRaises(ChybaSazby):
            vysazej(self.vystup, self.tmp / "spatny_vyklad", koncept=False, adresar_vykladu=self.vyklady(zakazany))

    def test_pdf_bez_v_uzemi_nazev(self):
        from firemni_databaze.report_cestina import tabulka as lokativy
        from firemni_databaze.report_pdf import vysazej
        text = text_pdf(vysazej(self.vystup, self.tmp / "cestina")).lower().replace("\n", " ")
        for z in lokativy().values():
            self.assertNotIn(f"v území {z['nazev']}".lower(), text)
        self.assertIn("v libereckém kraji", text)
        self.assertNotIn("u po je u", text)

    def test_nesoulad_zastavi_sazbu(self):
        from firemni_databaze.report_pdf import ChybaSazby, vysazej
        puvodni = report_vyklad.zjisteni_priloha
        with mock.patch.object(report_vyklad, "zjisteni_priloha", lambda v, L: puvodni(v, L) + ["Vymyšlených 987 654."]):
            with self.assertRaises(ChybaSazby):
                vysazej(self.vystup, self.tmp / "spatne")
        self.assertFalse((self.tmp / "spatne" / "report.pdf").exists())


if __name__ == "__main__":
    unittest.main()
