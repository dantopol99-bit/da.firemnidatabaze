"""Detektor zjištění a čeština reportu (Blok 4) – bez databáze, nad vzorovým výstupem."""

import json
import unittest
from pathlib import Path

import yaml

from firemni_databaze.report_cestina import TABULKA, lokativ, tabulka
from firemni_databaze.report_kontrola import ZAKAZANA_SLOVA, cisla_v_textu, povolena_cisla
from firemni_databaze.report_zjisteni import PRAH_ZJISTENI, detekuj, srovnej

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
        self.assertEqual([z["id"] for z in self.zjisteni], [f"Z{i:02d}" for i in range(1, len(sily) + 1)])

    def test_zadny_rozdil_pod_3_procenta(self):
        for z in self.zjisteni:
            if z["rozdil_pct"] is not None:
                self.assertGreaterEqual(z["rozdil_pct"], 3.0, z["popis"])

    def test_struktura_zjisteni(self):
        for z in self.zjisteni:
            self.assertIn(z["typ"], ("odchylka_od_cr", "zmena_trendu", "rozdily_uvnitr_uzemi", "aktivita_oboru",
                                     "divergence_poradi"))
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
            self.assertIsNone(ZAKAZANA_SLOVA.search(z["popis"]), z["popis"])
            self.assertNotRegex(z["popis"], r"[Vv] území ")

    def test_bez_interpretace(self):
        for z in self.zjisteni:
            for slovo in ("protože", "kvůli", "díky", "proto", "znamená", "doporuč", "Hypotéza"):
                self.assertNotIn(slovo, z["popis"])


if __name__ == "__main__":
    unittest.main()
