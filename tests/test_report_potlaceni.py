"""Pravidla prahu a slučování (rozhodnutí 3) a kontrola dopočtu – bez databáze."""

import random
import unittest

from firemni_databaze.report_potlaceni import Bunka, dopocitatelne, potlac


def B(kod, hodnota):
    return Bunka(kod, kod, hodnota)


def invarianty(test, bunky, p, prah=10):
    """Obecné vlastnosti každého výsledku potlačení."""
    nenulove = [b for b in bunky if b.hodnota > 0]
    test.assertEqual(p.celkem, sum(b.hodnota for b in nenulove))
    if p.cele_skryte:
        test.assertLess(p.celkem, prah)
        return
    test.assertEqual(sorted(b.kod for b in p.zverejnene + p.ostatni), sorted(b.kod for b in nenulove))
    for b in p.zverejnene:
        test.assertGreaterEqual(b.hodnota, prah)
    if p.ostatni:
        test.assertGreaterEqual(p.ostatni_hodnota, prah)
        test.assertGreaterEqual(len(p.ostatni), 2, "„ostatní“ s jedinou položkou by ji prozradilo")
    # ze zveřejněných čísel (součet, položky, „ostatní“) nejde nic dopočítat
    rovnice = [("T", [b.kod for b in nenulove])] + ([("O", [b.kod for b in p.ostatni])] if p.ostatni else [])
    zverejnene = {"T"} | {b.kod for b in p.zverejnene} | ({"O"} if p.ostatni else set())
    test.assertEqual(dopocitatelne(rovnice, zverejnene, {b.kod for b in p.ostatni}), [])


class TestPotlac(unittest.TestCase):
    def test_nic_pod_prahem(self):
        bunky = [B("a", 50), B("b", 10), B("c", 12)]
        p = potlac(bunky)
        self.assertEqual(p.ostatni, [])
        self.assertEqual([b.kod for b in p.zverejnene], ["a", "c", "b"])   # podle počtu sestupně
        invarianty(self, bunky, p)

    def test_jedna_skryta_bunka_pritahne_dalsi_nejmensi(self):
        # samotné b=7 by šlo dopočítat z celku → přidá se nejmenší další (d=12)
        bunky = [B("a", 100), B("b", 7), B("c", 30), B("d", 12)]
        p = potlac(bunky)
        self.assertEqual(sorted(b.kod for b in p.ostatni), ["b", "d"])
        self.assertEqual(p.ostatni_hodnota, 19)
        self.assertEqual(p.sekundarni, ["d"])
        invarianty(self, bunky, p)

    def test_ostatni_z_vice_malych_nad_prahem(self):
        bunky = [B("a", 100), B("b", 6), B("c", 5), B("d", 40)]
        p = potlac(bunky)
        self.assertEqual(sorted(b.kod for b in p.ostatni), ["b", "c"])
        self.assertEqual(p.sekundarni, [])
        invarianty(self, bunky, p)

    def test_ostatni_pod_prahem_z_vice_malych(self):
        # b+c = 5 < 10 → přidá se další nejmenší (e=11); stále se neprozradí ani b, ani c
        bunky = [B("a", 100), B("b", 3), B("c", 2), B("e", 11), B("f", 25)]
        p = potlac(bunky)
        self.assertEqual(sorted(b.kod for b in p.ostatni), ["b", "c", "e"])
        self.assertEqual(p.ostatni_hodnota, 16)
        invarianty(self, bunky, p)

    def test_cele_uzemi_pod_prahem(self):
        bunky = [B("a", 4), B("b", 3)]
        p = potlac(bunky)
        self.assertTrue(p.cele_skryte)
        self.assertEqual(p.skryte, {"a", "b"})
        invarianty(self, bunky, p)

    def test_vsechny_pod_prahem_ale_celek_nad(self):
        bunky = [B("a", 5), B("b", 6), B("c", 1)]
        p = potlac(bunky)
        self.assertFalse(p.cele_skryte)
        self.assertEqual(p.zverejnene, [])
        self.assertEqual(p.ostatni_hodnota, 12)
        invarianty(self, bunky, p)

    def test_chranena_bunka_se_preskoci(self):
        bunky = [B("a", 100), B("b", 7), B("c", 30), B("d", 12)]
        p = potlac(bunky, chranene={"d"})
        self.assertEqual(sorted(b.kod for b in p.ostatni), ["b", "c"])
        self.assertTrue(p.je_zverejnena("d"))
        invarianty(self, bunky, p)

    def test_chranena_se_obetuje_jen_kdyz_neni_jina(self):
        bunky = [B("a", 7), B("d", 12)]
        p = potlac(bunky, chranene={"d"})
        self.assertEqual(sorted(b.kod for b in p.ostatni), ["a", "d"])
        invarianty(self, bunky, p)

    def test_nuly_se_nezarazuji(self):
        bunky = [B("a", 20), B("b", 0), B("c", 15)]
        p = potlac(bunky)
        self.assertNotIn("b", {x.kod for x in p.zverejnene + p.ostatni})
        invarianty(self, bunky, p)

    def test_vlastni_prah(self):
        p = potlac([B("a", 20), B("b", 3), B("c", 4)], prah=5)
        self.assertEqual(sorted(b.kod for b in p.ostatni), ["b", "c"])

    def test_nahodna_cleneni(self):
        rnd = random.Random(20260930)
        for _ in range(2000):
            bunky = [B(f"k{i}", rnd.choice([0, 1, 2, 5, 9, 10, 11, rnd.randint(0, 300)])) for i in range(rnd.randint(1, 8))]
            invarianty(self, bunky, potlac(bunky))


class TestDopocet(unittest.TestCase):
    def test_osamocena_skryta_bunka_jde_dopocitat(self):
        self.assertEqual(dopocitatelne([("T", ["a", "b"])], {"T", "a"}, {"b"}), ["b"])

    def test_sloucene_ostatni_nejde_rozdelit(self):
        self.assertEqual(dopocitatelne([("T", ["a", "b", "c"]), ("O", ["b", "c"])], {"T", "a", "O"}, {"b", "c"}), [])

    def test_krizove_mezi_tabulkami(self):
        # FO/PO zveřejněno, formy sloučené PŘES skupiny → dopočitatelné (proto se slučuje v rámci FO a PO)
        rovnice = [("T", ["FO", "PO"]), ("FO", ["f1", "f2"]), ("PO", ["p1", "p2"]), ("O", ["f2", "p1"])]
        self.assertEqual(dopocitatelne(rovnice, {"T", "FO", "PO", "f1", "p2", "O"}, {"f2", "p1"}), ["f2", "p1"])

    def test_v_ramci_skupin_bezpecne(self):
        rovnice = [("T", ["FO", "PO"]), ("FO", ["f1", "f2", "f3"]), ("PO", ["p1", "p2"]),
                   ("OF", ["f2", "f3"])]
        self.assertEqual(dopocitatelne(rovnice, {"T", "FO", "PO", "f1", "OF", "p1", "p2"}, {"f2", "f3"}), [])

    def test_skryty_celek_z_jine_tabulky(self):
        # kraj skrytý v pořadí krajů, ale jeho okresy zveřejněné → dopočitatelný
        rovnice = [("CR", ["K1", "K2", "K3"]), ("O", ["K2", "K3"]), ("K2", ["o1", "o2"])]
        self.assertEqual(dopocitatelne(rovnice, {"CR", "K1", "O", "o1", "o2"}, {"K2", "K3"}), ["K2", "K3"])


if __name__ == "__main__":
    unittest.main()
