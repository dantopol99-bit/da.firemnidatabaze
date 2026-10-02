"""Modelové odhady (Blok 8) – jednotkové testy bez databáze."""

import unittest

from firemni_databaze import report_model as m

SBS = {("ENT_NR", "0-9"): 1000, ("ENT_NR", "10-19"): 100, ("ENT_NR", "20-49"): 50, ("ENT_NR", "50-249"): 10,
       ("ENT_NR", "GE250"): 1,
       ("AV_MEUR", "0-9"): 100, ("AV_MEUR", "10-19"): 50, ("AV_MEUR", "20-49"): 60, ("AV_MEUR", "50-249"): 80,
       ("AV_MEUR", "GE250"): 40,
       ("NETTUR_MEUR", "0-9"): 400, ("NETTUR_MEUR", "10-19"): 200, ("NETTUR_MEUR", "20-49"): 250,
       ("NETTUR_MEUR", "50-249"): 320, ("NETTUR_MEUR", "GE250"): 200}


class TestModel(unittest.TestCase):
    def test_katpo_na_tridy(self):
        self.assertEqual(m.trida_katpo("110"), "0-9")
        self.assertEqual(m.trida_katpo("210"), "10-19")
        self.assertEqual(m.trida_katpo("230"), "20-49")
        self.assertEqual(m.trida_katpo("320"), "50-249")
        self.assertEqual(m.trida_katpo("410"), "GE250")
        self.assertIsNone(m.trida_katpo("000"))

    def test_varianty_neuvedeno(self):
        subj = [("101", "000")] * 10 + [("112", "000")] * 10 + [("112", "210")] * 10 + [("112", "120")] * 10
        z = m.pocty_trid(subj, "zakladni")
        self.assertEqual(z["0-9"], 30)                  # Neuvedeno FO i PO do nejmenší třídy
        p = m.pocty_trid(subj, "pomerna")
        self.assertEqual(p["10-19"], 15)                # PO Neuvedeno poměrně 1 : 1
        self.assertEqual(sum(z.values()), sum(p.values()))

    def test_soucet_trid_je_celek(self):
        pocty = {"0-9": 500, "10-19": 30, "20-49": 15, "50-249": 4, "GE250": 1}
        r = m.rozpocet(pocty, 0.6, 12345.0, SBS)
        self.assertAlmostEqual(sum(r["hph"].values()), 12345.0, places=6)
        self.assertAlmostEqual(r["obrat"]["0-9"] / r["hph"]["0-9"], 4.0)
        self.assertGreater(r["hph_podil_10"], r["hph_podil_50"])

    def test_model_na_celostatnich_poctech_vrati_sbs(self):
        """Vnitřní konzistence: s počty podniků SBS vrátí model přesně podíly SBS."""
        pocty = {t: SBS[("ENT_NR", t)] for t in m.TRIDY}
        r = m.rozpocet(pocty, 1.0, 330.0, SBS)
        for t in m.TRIDY:
            self.assertAlmostEqual(r["hph"][t], SBS[("AV_MEUR", t)], places=6)
            self.assertAlmostEqual(r["obrat"][t], SBS[("NETTUR_MEUR", t)], places=6)

    def test_slucovani_trid_pod_prahem(self):
        sk = m.skupiny_publikace({"0-9": 500, "10-19": 30, "20-49": 15, "50-249": 12, "GE250": 3})
        self.assertEqual([t for _, t in sk], [("0-9",), ("10-19",), ("20-49",), ("50-249", "GE250")])
        self.assertEqual(sk[-1][0], "50 a více osob")
        sk = m.skupiny_publikace({"0-9": 500, "10-19": 5, "20-49": 4, "50-249": 0, "GE250": 0})
        # třídy nad 9 osob mají dohromady 9 subjektů (pod prahem) → sloučí se dolů, zbyde jen celek
        self.assertEqual([t for _, t in sk], [("0-9", "10-19", "20-49", "50-249", "GE250")])


if __name__ == "__main__":
    unittest.main()
