"""Detektor zjištění a čeština reportu (Blok 4) – bez databáze, nad vzorovým výstupem."""

import json
import unittest
from pathlib import Path

import yaml

from firemni_databaze.report_cestina import TABULKA, lokativ, tabulka
from firemni_databaze.report_kontrola import cisla_v_textu, povolena_cisla, zakazana_slova
from firemni_databaze.report_zjisteni import PODIL_JEVU_UZEMI, PRAH_ZJISTENI, detekuj, srovnej

KOREN = Path(__file__).resolve().parents[1]
VZOR = KOREN / "reporty" / "vystupy" / "F__CZ051__2026-09-15"


class TestCestina(unittest.TestCase):
    def test_tabulka_lokativu_je_uplna(self):
        data = yaml.safe_load(TABULKA.read_text(encoding="utf-8"))
        self.assertEqual(len(data["kraje"]), 14)
        self.assertEqual(len(data["okresy"]), 77)
        kody = [z["kod"] for s in ("cr", "kraje", "okresy") for z in data[s]]
        self.assertEqual(len(kody), len(set(kody)))
        for z in tabulka().values():
            self.assertRegex(z["v"], r"^(v|ve) \S")
            self.assertNotIn("území", z["v"])

    def test_tvary(self):
        self.assertEqual(lokativ("CZ051"), "v Libereckém kraji")
        self.assertEqual(lokativ("CZ0512"), "v okrese Jablonec nad Nisou")
        self.assertEqual(lokativ("CZ020"), "ve Středočeském kraji")
        self.assertEqual(lokativ("CZ063"), "v Kraji Vysočina")
        self.assertEqual(lokativ("CZ010"), "v hlavním městě Praze")
        self.assertEqual(lokativ("CZ"), "v Česku")
        with self.assertRaises(KeyError):
            lokativ("CZ999")

    def test_nazvy_odpovidaji_ciselniku(self):
        from tests.test_res_import_db import CONN
        if CONN is None:
            self.skipTest("databáze není dostupná")
        with CONN.cursor() as cur:
            cur.execute("SELECT kod, nazev FROM res.cis_kraj WHERE kod_ruian IS NOT NULL UNION ALL "
                        "SELECT o.kod, o.nazev FROM res.cis_okres o JOIN res.cis_kraj k ON k.kod = o.kraj_kod "
                        "WHERE k.kod_ruian IS NOT NULL")
            ciselnik = dict(cur.fetchall())
        CONN.rollback()
        t = tabulka()
        self.assertEqual(set(ciselnik), set(t) - {"CZ"})
        for kod, nazev in ciselnik.items():
            self.assertEqual(t[kod]["nazev"], nazev, kod)


class TestSrovnani(unittest.TestCase):
    def test_prah_3_procenta(self):
        self.assertEqual(srovnej(102.9, 100), "srovnatelné")
        self.assertEqual(srovnej(97.1, 100), "srovnatelné")
        self.assertEqual(srovnej(103, 100), "vyšší")
        self.assertEqual(srovnej(96.9, 100), "nižší")
        self.assertIsNone(srovnej(None, 100))


@unittest.skipUnless((VZOR / "vysledek.json").exists(), "vzorový výstup chybí")
class TestDetektor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vysledek = json.loads((VZOR / "vysledek.json").read_text(encoding="utf-8"))
        cls.zjisteni = detekuj(cls.vysledek)

    def test_shoda_s_ulozenym_vystupem(self):
        ulozeno = json.loads((VZOR / "zjisteni.json").read_text(encoding="utf-8"))["zjisteni"]
        self.assertEqual(self.zjisteni, ulozeno)

    def test_razeni_a_prah(self):
        sily = [z["sila"] for z in self.zjisteni]
        self.assertEqual(sily, sorted(sily, reverse=True))
        self.assertTrue(all(s >= PRAH_ZJISTENI for s in sily))
        self.assertEqual([z["poradi"] for z in self.zjisteni], list(range(1, len(sily) + 1)))

    def test_stala_id(self):
        """ID se neodvozuje z pořadí: je jedinečné, bez číslic a nezmění se, přibude-li silnější zjištění."""
        import copy, re
        from firemni_databaze.report_zjisteni import stale_id
        ids = [z["id"] for z in self.zjisteni]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(re.fullmatch(r"Z[A-Z]{2}-[A-Z]{4}", i) for i in ids))
        vysledek = copy.deepcopy(self.vysledek)
        t02 = next(t for t in vysledek["tabulky"] if t["kod"] == "T02_srovnani")
        uz = next(r for r in t02["radky"] if r["popis"].endswith("(zkoumané území)"))
        uz["hodnoty"]["lq"] = 9.99                          # zesílí jedno zjištění → změní pořadí
        nova = {z["id"]: z for z in detekuj(vysledek)}
        for z in self.zjisteni:
            self.assertIn(z["id"], nova)
            self.assertEqual(nova[z["id"]]["podtyp"], z["podtyp"])
        self.assertEqual(stale_id(self.zjisteni[0]), self.zjisteni[0]["id"])

    def test_odkazy_ve_vykladu_existuji(self):
        """Každý odkaz na zjištění v textu analytika existuje v zjisteni.json; žádné staré číselné ID."""
        import re
        soubor = KOREN / "reporty" / "vyklad" / "F__CZ051__2026-09-15.md"
        text = re.sub(r"<!--.*?-->", "", soubor.read_text(encoding="utf-8"), flags=re.S)
        ids = {z["id"] for z in json.loads((VZOR / "zjisteni.json").read_text(encoding="utf-8"))["zjisteni"]}
        odkazy = re.findall(r"\bZ[A-Z]{2}-[A-Z]{4}\b", text)
        self.assertTrue(odkazy)
        self.assertEqual(set(odkazy) - ids, set())
        self.assertEqual(re.findall(r"\bZ\d{2}\b", text), [])

    def test_zadny_rozdil_pod_3_procenta(self):
        for z in self.zjisteni:
            if z["rozdil_pct"] is not None:
                self.assertGreaterEqual(z["rozdil_pct"], 3.0, z["popis"])

    def test_struktura_zjisteni(self):
        for z in self.zjisteni:
            self.assertIn(z["typ"], ("odchylka_od_cr", "zmena_trendu", "rozdily_uvnitr_uzemi", "aktivita_oboru",
                                     "divergence_poradi", "mzdy_zamestnanost",
                                     "ekonomika"))
            self.assertIsInstance(z["sila"], float)
            self.assertTrue(z["cisla"])
            self.assertTrue(all(c["tabulka"] for c in z["cisla"]))
            # jedna věta: končí tečkou a uvnitř nezačíná další věta
            self.assertTrue(z["popis"].endswith("."))
            self.assertNotRegex(z["popis"][:-1], r"\.\s+[A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ]", z["popis"])

    def test_aktivita_oboru_neni_prehlizena(self):
        z = next(z for z in self.zjisteni if z["typ"] == "aktivita_oboru")
        self.assertEqual((z["hodnota"], z["srovnani"], z["smer"]), (62.8, 59.1, "vyšší"))

    def test_popisy_jen_povolena_cisla_a_slova(self):
        povolena = povolena_cisla(VZOR)
        for z in self.zjisteni:
            self.assertEqual(cisla_v_textu(z["popis"]) - povolena, set(), z["popis"])
            self.assertEqual(zakazana_slova(z["popis"]), [], z["popis"])
            self.assertNotRegex(z["popis"], r"[Vv] území ")

    def test_bez_interpretace(self):
        for z in self.zjisteni:
            for slovo in ("protože", "kvůli", "díky", "proto", "znamená", "doporuč", "Hypotéza"):
                self.assertNotIn(slovo, z["popis"])


if __name__ == "__main__":
    unittest.main()


def _vysledek_trend(obor_uz, obor_cr, ost_uz=None, ost_cr=None, typ="KRAJ", kod="CZ051") -> dict:
    """Minimální výstup s mírou zániku PO oboru (T18) a ostatních oborů (T30) za roky 2023–2025."""
    nazev = {"CZ051": "Liberecký kraj", "CZ": "Česko"}

    def radky(hodnoty, uzemi, skupina=None):
        out = []
        for rok, h in zip((2023, 2024, 2025), hodnoty):
            r = {"popis": f"{nazev[uzemi]} – {rok}", "typ": "polozka", "uzemi": uzemi, "rok": rok,
                 "hodnoty": {"mira": h, "mira_obd": None}}
            if skupina:
                r["popis"] = ("Obor – " if skupina == "obor" else "Ostatní obory – ") + r["popis"]
                r["skupina"] = skupina
            out.append(r)
        return out

    tabulky = [{"kod": "T18_mira_zaniku_po", "zverejneno": True, "obdobi": "1. 1.–15. 10.",
                "radky": radky(obor_uz, kod) + (radky(obor_cr, "CZ") if kod != "CZ" else [])}]
    if ost_uz is not None:
        tabulky.append({"kod": "T30_mira_zaniku_ostatni", "zverejneno": True,
                        "radky": radky(ost_uz, kod, "ostatni") + (radky(ost_cr, "CZ", "ostatni") if kod != "CZ" else [])})
    return {"meta": {"uzemi": {"typ": typ, "kod": kod, "nazev": nazev[kod], "kraj": kod if typ == "KRAJ" else None},
                     "obor": [{"kod": "F"}]}, "tabulky": tabulky}


class TestJevUzemi(unittest.TestCase):
    """Pravidlo jev_uzemi: změna trendu oboru, kterou ostatní obory území zopakují stejným směrem
    a srovnatelně, je jev celého kraje – nižší síla, věta v popisu, stálé ID beze změny."""

    OBOR_UZ, OBOR_CR = (2.0, 2.0, 6.0), (2.5, 2.5, 2.5)

    def test_skok_celeho_kraje(self):
        bez = {z["id"]: z for z in detekuj(_vysledek_trend(self.OBOR_UZ, self.OBOR_CR))}
        s = {z["id"]: z for z in detekuj(_vysledek_trend(self.OBOR_UZ, self.OBOR_CR, (2.0, 2.0, 5.0), (2.5, 2.5, 2.5)))}
        self.assertEqual(set(bez), set(s))                      # čísla ostatních oborů ID nemění
        self.assertEqual(len(s), 3)
        for i, z in s.items():
            self.assertTrue(z["jev_uzemi"], z["podtyp"])
            self.assertEqual(z["sila_puvodni"], bez[i]["sila"])
            self.assertLess(z["sila"], z["sila_puvodni"])
            self.assertTrue(z["popis"].endswith("– jev celého kraje, ne oboru."), z["popis"])
            self.assertTrue(any(c.get("ucel") == "jev_uzemi" for c in z["cisla"]))
        proti_cr = next(z for z in s.values() if z["podtyp"] == "míra zániku PO za rok: proti ČR")
        self.assertAlmostEqual(proti_cr["sila"], round(abs((6.0 / 2.5) / (5.0 / 2.5) - 1), 4))   # 0,2
        serazena = detekuj(_vysledek_trend(self.OBOR_UZ, self.OBOR_CR, (2.0, 2.0, 5.0), (2.5, 2.5, 2.5)))
        self.assertEqual([z["sila"] for z in serazena], sorted((z["sila"] for z in serazena), reverse=True))

    def test_ostatni_obory_beze_zmeny_jev_oboru(self):
        for z in detekuj(_vysledek_trend(self.OBOR_UZ, self.OBOR_CR, (2.0, 2.0, 2.04), (2.5, 2.5, 2.5))):
            self.assertNotIn("jev_uzemi", z)
            self.assertFalse(z["ostatni"]["srovnatelne"])
            self.assertNotIn("jev celého", z["popis"])

    def test_hranice_poloviny_a_smeru(self):
        # obor +200 % proti průměru; ostatní +100 % (= polovina) je jev kraje, +90 % už ne, opačný směr ne
        for ost, ocekavano in ((4.0, True), (3.8, False), (1.5, False)):
            z = next(z for z in detekuj(_vysledek_trend(self.OBOR_UZ, self.OBOR_CR, (2.0, 2.0, ost), (2.0, 2.0, ost)))
                     if z["podtyp"] == "míra zániku PO za rok: poslední rok proti předchozím")
            self.assertEqual(z.get("jev_uzemi", False), ocekavano, ost)
        self.assertEqual(PODIL_JEVU_UZEMI, 0.5)

    def test_sila_se_nikdy_nezvysi(self):
        # ostatní obory se posunuly mnohem víc než obor: jev kraje, síla nejvýš původní
        for z in detekuj(_vysledek_trend((2.0, 2.0, 2.4), self.OBOR_CR, (2.0, 2.0, 8.0), (2.5, 2.5, 2.5))):
            if z.get("jev_uzemi"):
                self.assertLessEqual(z["sila"], z["sila_puvodni"])

    def test_okres_a_cr_maji_vlastni_vetu(self):
        z = detekuj(_vysledek_trend(self.OBOR_UZ, self.OBOR_CR, (2.0, 2.0, 5.0), (2.0, 2.0, 5.0), typ="CR", kod="CZ"))
        self.assertTrue(z and all(x["popis"].endswith("– jev všech oborů v Česku, ne oboru.") for x in z))
