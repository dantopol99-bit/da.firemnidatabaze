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
PILOT_2025 = KOREN / "reporty" / "vystupy" / "F__CZ051__2026-10-15"
L_VSE = {f"T{i:02d}": "tab. 1" for i in range(1, 29)} | {
    k: "graf 1" for k in ("g_dyn", "g_ekon", "g_fopo", "g_hustota", "g_lq", "g_miry", "g_mzdy", "g_vek", "g_vel_fo", "g_vel_po",
                          "g_zanik")}
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

## Ekonomický profil

### Proč to tak může být

Text.

### Co z toho plyne

Text.

## Modelové odhady

### Proč to tak může být

Text.

### Co z toho plyne

Text.

## Zaměstnanost a mzdy

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


class TestZakazanaSlova(unittest.TestCase):
    """Rozhodnutí 1: žádný tvar slova „firma“ ani „aktivní“ (i uvnitř slova); interní kódy se nehlídají."""

    def test_vsechny_tvary_slova_firma(self):
        from firemni_databaze.report_kontrola import zakazana_slova

        for slovo in ("firma", "firmy", "firem", "firmám", "firmách", "firmou", "Firemní", "firemních", "nefiremní"):
            self.assertEqual(zakazana_slova(f"Text o {slovo} v kraji."), [slovo], slovo)

    def test_aktivni_i_uvnitr_slova(self):
        from firemni_databaze.report_kontrola import zakazana_slova

        for slovo in ("aktivní", "aktivních", "Aktivně", "neaktivní", "neaktivních", "nejaktivnější"):
            self.assertEqual(zakazana_slova(f"Výmazy {slovo} společností."), [slovo], slovo)

    def test_povolene_vyjimky(self):
        from firemni_databaze.report_kontrola import zakazana_slova

        for text in ("Ukazatel AKTIVNI_PODIL_KRAJ a AKTIVNI_PODIL_SEKCE_KRAJ.",      # interní kódy
                     "python -m firemni_databaze.report",                            # název balíčku
                     "Míra vzniků: aktivní podniky ČSÚ, aktivních podniků přibylo.",  # upřesnění rozhodnutí 1
                     "Podíl subjektů se zjištěnou aktivitou je 58,8 %."):             # „aktivita“ není „aktivní“
            self.assertEqual(zakazana_slova(text), [], text)
        # kód v textu nesmí zakrýt skutečné zakázané slovo vedle něj
        self.assertEqual(zakazana_slova("AKTIVNI_PODIL_KRAJ: aktivní subjekty"), ["aktivní"])

    @unittest.skipUnless((PILOT_2025 / "_interni" / "kontrola.json").exists(),
                         "chybí interní podklady pilotu (_interni se necommituje; vznikne výpočtem reportu)")
    def test_kontrola_vystupu_hlida_i_strojove_texty(self):
        from firemni_databaze.report_kontrola import zkontroluj

        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "vystup"
            shutil.copytree(PILOT_2025, a)
            v = json.loads((a / "vysledek.json").read_text(encoding="utf-8"))
            v["tabulky"][0]["poznamky"].append("Podíl neaktivních subjektů.")
            (a / "vysledek.json").write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
            self.assertTrue(any("neaktivních" in c for c in zkontroluj(a)))

    @unittest.skipUnless((PILOT_2025 / "vysledek.json").exists(), "pilot v CZ-NACE 2025 chybí")
    def test_texty_sazby_pilotu_bez_zakazanych_slov(self):
        from firemni_databaze.report_kontrola import zakazana_slova
        from firemni_databaze.report_pdf import sestav_data, texty_dat

        v = json.loads((PILOT_2025 / "vysledek.json").read_text(encoding="utf-8"))
        _, analytik = report_vyklad.nacti_vyklad_analytika(report_vyklad.soubor_vykladu("F__CZ051__2026-10-15"))
        with tempfile.TemporaryDirectory() as tmp:
            data = sestav_data(v, Path(tmp), koncept=True, vyklad_analytika=analytik)
        self.assertEqual([(s, x[:60]) for x in texty_dat(data) for s in zakazana_slova(x)], [])


class TestNezlomitelnaProcenta(unittest.TestCase):
    def test_mezera_pred_procentem_je_nezlomitelna(self):
        from firemni_databaze.report_pdf import nezlomitelna_procenta

        data = {"text": "proti 82,7 % v ČR a 5 %", "seznam": ["11,6 % (ZOD-SXHQ)"], "soubor": "/tmp/1 %.svg"}
        vysledek = nezlomitelna_procenta(data)
        self.assertEqual(vysledek["text"], "proti 82,7\u00a0% v ČR a 5\u00a0%")
        self.assertEqual(vysledek["seznam"], ["11,6\u00a0% (ZOD-SXHQ)"])
        self.assertEqual(vysledek["soubor"], "/tmp/1 %.svg")              # cesty k souborům beze změny
        self.assertEqual(vysledek["text"].replace("\u00a0", " "), data["text"])   # slova beze změny

    @unittest.skipUnless((PILOT_2025 / "vysledek.json").exists(), "pilot v CZ-NACE 2025 chybí")
    def test_v_sazbe_pilotu_neni_zlomitelna_mezera_pred_procentem(self):
        import re

        from firemni_databaze.report_pdf import sestav_data, texty_dat

        v = json.loads((PILOT_2025 / "vysledek.json").read_text(encoding="utf-8"))
        _, analytik = report_vyklad.nacti_vyklad_analytika(report_vyklad.soubor_vykladu("F__CZ051__2026-10-15"))
        with tempfile.TemporaryDirectory() as tmp:
            data = sestav_data(v, Path(tmp), koncept=True, vyklad_analytika=analytik)
        spatne = [x for x in texty_dat(data) if re.search(r"\d[ \t]+%", x)]
        self.assertEqual(spatne, [])
        self.assertTrue(any("82,7\u00a0%" in x for x in texty_dat(data)))


class TestOdkazy(unittest.TestCase):
    """Tabulky a grafy se číslují (tab. 1, graf 1, …) průběžně přes report; odkaz nesmí být prázdný,
    nedokončený („tab. [“) ani mířit na neexistující tabulku nebo graf."""

    @staticmethod
    def data(texty: list[str], tabulek: int = 2, grafu: int = 1) -> dict:
        obsah = ([{"typ": "tabulka", "cislo": str(i)} for i in range(1, tabulek + 1)]
                 + [{"typ": "graf", "cislo": str(i)} for i in range(1, grafu + 1)])
        return {"kapitoly": [{"obsah": obsah, "vyklad": [{"druh": "vidět", "text": t} for t in texty]}]}

    def test_cislovani_pokracuje_za_26(self):
        from firemni_databaze.report_pdf import Sestava

        s = Sestava(Path(tempfile.gettempdir()))
        cisla = [s.cislo_tab(f"T{i:02d}") for i in range(1, 31)]
        self.assertEqual(cisla[26], "27")
        self.assertEqual(s.L["T27"], "tab. 27")
        self.assertEqual(s.cislo_graf("g_dyn"), "1")          # grafy mají vlastní řadu
        self.assertEqual(s.L["g_dyn"], "graf 1")

    def test_spravne_odkazy_projdou(self):
        from firemni_databaze.report_pdf import kontrola_odkazu

        self.assertEqual(kontrola_odkazu(self.data(["Text (tab. 1, graf 1).", "Viz tab. 2; graf 1."])), [])

    def test_nedokonceny_a_prazdny_odkaz_se_odhali(self):
        from firemni_databaze.report_pdf import kontrola_odkazu

        for text in ("kontext ČR (graf K, tab. [).", "(tab. )", "viz tab.", "(graf)", "(tab. A)"):
            self.assertTrue(kontrola_odkazu(self.data([text])), text)

    def test_odkaz_na_neexistujici_tabulku_nebo_graf_se_odhali(self):
        from firemni_databaze.report_pdf import kontrola_odkazu

        self.assertTrue(kontrola_odkazu(self.data(["(tab. 3)"], tabulek=2)))
        self.assertTrue(kontrola_odkazu(self.data(["(graf 2)"], grafu=1)))

    def test_odkaz_neni_cislo_z_dat(self):
        self.assertEqual(cisla_v_textu("V kraji je 14\u202f799 subjektů (tab. 27, graf 11). Tabulka 3: Kraje"), {"14799"})

    @unittest.skipUnless((PILOT_2025 / "vysledek.json").exists(), "pilot v CZ-NACE 2025 chybí")
    def test_vsechny_odkazy_pilotu_miri_na_existujici_tabulky_a_grafy(self):
        from firemni_databaze.report_pdf import kontrola_odkazu, sestav_data, texty_dat

        v = json.loads((PILOT_2025 / "vysledek.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            data = sestav_data(v, Path(tmp), koncept=True, vyklad_analytika=None)
        self.assertEqual(kontrola_odkazu(data), [])
        for druh in ("tabulka", "graf"):
            cisla = [o["cislo"] for k in data["kapitoly"] for o in k["obsah"] if o["typ"] == druh]
            self.assertEqual(cisla, [str(i) for i in range(1, len(cisla) + 1)], druh)   # průběžně 1, 2, …
        self.assertGreater(len([1 for k in data["kapitoly"] for o in k["obsah"] if o["typ"] == "tabulka"]), 26)
        self.assertFalse(any("tab. [" in x for x in texty_dat(data)))


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
        for f in (report_vyklad.postaveni, report_vyklad.struktura, report_vyklad.ekonomika,
                  report_vyklad.modelove_odhady, report_vyklad.zamestnanost, report_vyklad.dynamika):
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
        """Pilot má text analytika ve všech oddílech a žádný zástupný text (lze ho vysázet jako schválený)."""
        soubor = KOREN / "reporty" / "vyklad" / "F__CZ051__2026-09-15.md"
        stav, bloky = report_vyklad.nacti_vyklad_analytika(soubor)
        self.assertEqual(stav, "hotovy")
        self.assertEqual(set(bloky), {"shrnuti", "postaveni", "struktura", "ekonomicky_profil", "modelove_odhady",
                                      "zamestnanost", "dynamika"})
        for oddil, b in bloky.items():
            self.assertTrue(b, oddil)
            self.assertFalse(any(report_vyklad.ZASTUPNY_TEXT in x["text"] for x in b), oddil)


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

    def test_pevne_kapitoly_v_poradi_osnovy(self):
        from pypdf import PdfReader
        from firemni_databaze.report_pdf import NEDOSTUPNE_KAPITOLY, vysazej
        pdf = vysazej(self.vystup, self.tmp / "osnova")
        poradi = ["Shrnutí klíčových zjištění", "Postavení území", "Struktura", "Ekonomický profil",
                  "Zaměstnanost a mzdy", "Dynamika území a kontext ČR", "Rizikový profil (insolvence)",
                  "Veřejné zakázky a dotace", "Metodika, omezení a zdroje", "Příloha: zjištění detektoru",
                  "Příloha: odchylky od osnovy"]
        # nadpis kapitoly je první řádek strany pod záhlavím (každá kapitola začíná na nové straně)
        nadpisy = [s.extract_text().splitlines()[1] for s in PdfReader(pdf).pages[1:]]
        self.assertEqual([n for n in nadpisy if n in poradi], poradi)
        text = " ".join(text_pdf(pdf).split())
        self.assertEqual(text.count("Stav: zatím nedostupné"), len(NEDOSTUPNE_KAPITOLY) + 1)   # + pododdíl koncentrace
        self.assertIn("Koncentrace a ukazatele z účetních závěrek", text)
        for n in NEDOSTUPNE_KAPITOLY.values():
            self.assertIn(" ".join(n["zdroj"].split()), text)

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
