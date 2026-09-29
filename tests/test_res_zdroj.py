"""Testy zpracování zdrojů RES, které nepotřebují databázi ani síť."""

import hashlib
import tempfile
import unittest
from datetime import date
from pathlib import Path

from firemni_databaze import res_zdroj as z


def metadata(soubor: str, datumove: set[str] | None = None, sloupce=None) -> dict:
    datumove = z.SLOUPCE_DATUM[soubor] if datumove is None else datumove
    return {"tableSchema": {"columns": [
        {"name": s, "datatype": "date" if s in datumove else "string"}
        for s in (sloupce or z.SLOUPCE[soubor])
    ]}}


class TestSouhrnSouboru(unittest.TestCase):
    def test_pocet_radku_a_otisk(self):
        # CRLF, čárka a zdvojená uvozovka v textu, prázdné "" a zalomení řádku v uvozovkách
        obsah = (
            'ICO,FIRMA,TEXTADR,DATPLAT\r\n'
            '00000078,"Lesní správa Lány","",2026-09-15\r\n'
            '00000123,"TECHNOMAT, státní podnik ""v likvidaci""","",2026-09-15\r\n'
            '00000124,"Dva\r\nřádky","Ulice 1, Obec",2026-09-15\r\n'
            '00000125,,,2026-09-15\r\n'
        ).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp:
            cesta = Path(tmp) / "x.csv"
            cesta.write_bytes(obsah)
            s = z.souhrn_souboru(cesta)
        self.assertEqual(s.pocet_radku, 4)
        self.assertEqual(s.hlavicka, ["ICO", "FIRMA", "TEXTADR", "DATPLAT"])
        self.assertEqual(s.sha256, hashlib.sha256(obsah).hexdigest())
        self.assertEqual(s.velikost_bajtu, len(obsah))

    def test_prazdny_soubor_jen_s_hlavickou(self):
        with tempfile.TemporaryDirectory() as tmp:
            cesta = Path(tmp) / "x.csv"
            cesta.write_bytes(b"ICO,DATPLAT\r\n")
            self.assertEqual(z.souhrn_souboru(cesta).pocet_radku, 0)


class TestStruktura(unittest.TestCase):
    def test_spravna_struktura(self):
        for soubor in z.SLOUPCE:
            z.over_strukturu(soubor, list(z.SLOUPCE[soubor]), metadata(soubor))

    def test_jina_hlavicka(self):
        hlavicka = list(z.SLOUPCE["res_data.csv"])[:-1]
        with self.assertRaises(ValueError):
            z.over_strukturu("res_data.csv", hlavicka, metadata("res_data.csv"))

    def test_novy_sloupec_v_metadatech(self):
        sloupce = z.SLOUPCE["res_data.csv"] + ("NOVY",)
        with self.assertRaises(ValueError):
            z.over_strukturu("res_data.csv", list(sloupce), metadata("res_data.csv", sloupce=sloupce))

    def test_zmena_datoveho_typu(self):
        with self.assertRaises(ValueError):
            z.over_strukturu("res_data.csv", list(z.SLOUPCE["res_data.csv"]),
                             metadata("res_data.csv", datumove={"DATPLAT"}))

    def test_nazvy_souboru(self):
        self.assertEqual(z.soubor_metadat("res_pf_nace.csv"), "res_pf_nace-metadata.json")
        self.assertTrue(z.url_souboru("res_data.csv").startswith("https://opendata.csu.gov.cz/"))


def polozka(kod, uroven, nadvaz, text="x"):
    return {"chodnota": kod, "uroven": str(uroven), "nadvaz": nadvaz, "text": text, "zkrtext": text,
            "admplod": "2008-01-01", "admnepo": "9999-09-09"}


class TestCiselniky(unittest.TestCase):
    def test_hierarchie_nace(self):
        polozky = [
            polozka("F", 1, None, "Stavebnictví"), polozka("41", 2, "F"), polozka("412", 3, "41"),
            polozka("4120", 4, "412"), polozka("41201", 5, "4120"),
            polozka("Y", 1, None), polozka("00", 2, "Y"),
        ]
        radky = {r["kod"]: r for r in z.radky_nace(polozky, 80004)}
        self.assertEqual(
            (radky["41201"]["sekce"], radky["41201"]["oddil"], radky["41201"]["skupina"], radky["41201"]["trida"]),
            ("F", "41", "412", "4120"),
        )
        self.assertEqual((radky["412"]["sekce"], radky["412"]["trida"]), ("F", None))
        self.assertEqual(radky["F"]["sekce"], "F")
        self.assertFalse(radky["41201"]["je_pseudokod"])
        self.assertTrue(radky["00"]["je_pseudokod"])

    def test_nace_bez_predka(self):
        with self.assertRaises(ValueError):
            z.radky_nace([polozka("41", 2, "F")], 80004)

    def test_nace_duplicita(self):
        with self.assertRaises(ValueError):
            z.radky_nace([polozka("F", 1, None), polozka("F", 1, None)], 80004)

    def test_okres_potrebuje_vazbu_na_kraj(self):
        okresy = [{"chodnota": "CZ0513", "text": "Liberec", "admplod": None, "admnepo": None}]
        vazba = {"kodcis1": "109", "chodnota1": "CZ0513", "kodcis2": "108", "chodnota2": "CZ051"}
        self.assertEqual(z.radky_okres(okresy, [vazba])[0]["kraj_kod"], "CZ051")
        with self.assertRaises(ValueError):
            z.radky_okres(okresy, [])

    def test_kraj_s_kodem_ruian(self):
        r = z.radky_kraj([{"chodnota": "3077", "cznuts": "CZ051", "text": "Liberecký kraj", "zkrkraj": "LBK",
                           "kod_ruian": "78", "admplod": "2001-03-01", "admnepo": "9999-09-09"}])[0]
        self.assertEqual((r["kod"], r["kod_csu"], r["kod_ruian"]), ("CZ051", 3077, 78))

    def test_csv_ciselniku_prazdne_hodnoty(self):
        obsah = '﻿"KODJAZ","CHODNOTA","NADVAZ"\n"CS","A",\n'.encode("utf-8")
        self.assertEqual(z.nacti_csv(obsah), [{"kodjaz": "CS", "chodnota": "A", "nadvaz": None}])

    def test_url_exportu(self):
        url = z.url_ciselniku(109, date(2026, 9, 15), "108_210")
        self.assertIn("kodcis=109", url)
        self.assertIn("typdat=1", url)
        self.assertIn("datpohl=15.09.2026", url)


class TestAgregaty(unittest.TestCase):
    def test_radky_agregatu(self):
        definice = {"vyber": {
            "kod": "RES02QT1",
            "ukazatele": [{"kod": "4958_reg", "nazev": "Počet ekonomických subjektů celkem"}],
            "variantyDimenze": [
                {"kod": "Uz02A", "typDimenzeKod": "VUZEMI", "nazev": "ČR, kraje"},
                {"kod": "CZNACERES0", "typDimenzeKod": "CZNACE", "nazev": "Odvětví ekonomické činnosti CZ-NACE"},
                {"kod": "CasQ", "typDimenzeKod": "REF_CAS", "nazev": "Čtvrtletí"},
            ],
        }}
        csv_text = (
            '"Ukazatel","ČR, kraje","Uz02A.Polozka","Odvětví ekonomické činnosti CZ-NACE",'
            '"CZNACERES0.Polozka","Čtvrtletí","CasQ.Polozka","Hodnota"\n'
            '"Počet ekonomických subjektů celkem","Liberecký kraj","CZ051","F Stavebnictví","F",'
            '"2. čtvrtletí 2026","2026-Q2","12345.0"\n'
        )
        r = z.radky_agregatu(csv_text.encode("utf-8"), definice)[0]
        self.assertEqual((r["ukazatel_kod"], r["uzemi_kod"], r["nace_kod"], r["obdobi"], r["hodnota"]),
                         ("4958_reg", "CZ051", "F", "2026-Q2", 12345.0))


if __name__ == "__main__":
    unittest.main()
