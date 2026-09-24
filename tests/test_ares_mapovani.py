"""Testy převodu odpovědí ARES na řádky jádra (bez databáze, syntetická data)."""

import unittest
from datetime import date
from decimal import Decimal

from firemni_databaze.ares_mapovani import adresa, cislo, mapuj, podil_procento, role


def zakl(**navic):
    data = {
        "ico": "12345678",
        "obchodniJmeno": "Vzor s.r.o.",
        "pravniForma": "112",
        "datumVzniku": "2010-01-01",
        "datumAktualizace": "2026-01-01",
        "dic": "CZ12345678",
        "czNace": ["62", "47"],
        "sidlo": {"kodAdresnihoMista": 1, "textovaAdresa": "Ulice 1, 10000 Obec", "kodStatu": "CZ"},
        "adresaDorucovaci": {"radekAdresy1": "Ulice 1", "radekAdresy2": "10000 Obec"},
        "seznamRegistraci": {"stavZdrojeIr": "NEEXISTUJICI"},
    }
    data.update(navic)
    return data


def fo(prijmeni, jmeno="JANA", narozeni="1980-01-01"):
    return {"jmeno": jmeno, "prijmeni": prijmeni, "datumNarozeni": narozeni, "statniObcanstvi": "CZ"}


def vr(**zaznam):
    z = {
        "primarniZaznam": True,
        "obchodniJmeno": [{"datumZapisu": "2010-01-01", "hodnota": "Vzor s.r.o."}],
        "pravniForma": [{"datumZapisu": "2010-01-01", "hodnota": "112"}],
        "adresy": [{"typAdresy": "SIDLO", "datumZapisu": "2010-01-01",
                    "adresa": {"kodAdresnihoMista": 1, "textovaAdresa": "Ulice 1, 10000 Obec", "kodStatu": "CZ"}}],
    }
    z.update(zaznam)
    return {"icoId": "12345678", "zaznamy": [z]}


class TestPrevody(unittest.TestCase):
    def test_cislo_se_strednikem(self):
        self.assertEqual(cislo("8000;00"), Decimal("8000.00"))
        self.assertIsNone(cislo("nevím"))

    def test_podil_jen_spolehlive(self):
        self.assertEqual(podil_procento({"typObnos": "TEXT", "hodnota": "4/5"}), Decimal("80.0000"))
        self.assertEqual(podil_procento({"typObnos": "TEXT", "hodnota": "10 %"}), Decimal("10.0000"))
        self.assertEqual(podil_procento({"typObnos": "ZLOMEK", "hodnota": "1;3"}), Decimal("33.3333"))
        self.assertEqual(podil_procento({"typObnos": "PROCENTA", "hodnota": "100;00"}), Decimal("100.0000"))
        for text in ("padesát procent", "60 % (10 podílů)", "10000", "3/2"):
            self.assertIsNone(podil_procento({"typObnos": "TEXT", "hodnota": text}), text)

    def test_cislo_evidencni(self):
        a = adresa({"cisloDomovni": 12, "typCisloDomovni": 2, "psc": 1234, "cisloOrientacni": 5,
                    "cisloOrientacniPismeno": "a"})
        self.assertEqual((a["cislo_popisne"], a["cislo_evidencni"]), (None, "12"))
        self.assertEqual(a["psc"], "01234")
        self.assertEqual(a["cislo_orientacni"], "5a")


class TestRole(unittest.TestCase):
    def test_predstavenstvo(self):
        o = "Statutární orgán - představenstvo"
        self.assertEqual(role("STATUTARNI_ORGAN", o, "člen představenstva", "121"), "CLEN_PREDSTAVENSTVA")
        self.assertEqual(role("STATUTARNI_ORGAN", o, "předs. předst. a gen. ředitel", "121"),
                         "PREDSEDA_PREDSTAVENSTVA")
        self.assertEqual(role("STATUTARNI_ORGAN", o, "1. místopředseda představenstva", "121"),
                         "MISTOPREDSEDA_PREDSTAVENSTVA")
        self.assertIsNone(role("STATUTARNI_ORGAN", o, "generální ředitel a.s.", "121"))

    def test_ostatni_organy(self):
        self.assertEqual(role("STATUTARNI_ORGAN", "Statutární orgán", None, "112"), "JEDNATEL")
        self.assertEqual(role("DOZORCI_RADA", "Dozorčí rada", "místopředseda dozorčí rady", "121"),
                         "MISTOPREDSEDA_DOZORCI_RADY")
        self.assertEqual(role("KONTROLNI_KOMISE", None, "předseda kontrolní komise", "205"),
                         "PREDSEDA_KONTROLNI_KOMISE")
        self.assertEqual(role("STATUTARNI_ORGAN", "Statutární orgán", "předseda družstva", "205"),
                         "PREDSEDA_DRUZSTVA")
        self.assertEqual(role("STATUTARNI_ORGAN", "Statutární ředitel", None, "121"), "STATUTARNI_REDITEL")
        self.assertEqual(role("STATUTARNI_ORGAN", "Správní rada", "předseda správní rady", "121"),
                         "PREDSEDA_SPRAVNI_RADY")
        self.assertIsNone(role("STATUTARNI_ORGAN", "Statutární orgán", "ředitel družstva", "205"))


class TestMapuj(unittest.TestCase):
    def test_bez_ico_se_odmitne(self):
        with self.assertRaises(ValueError):
            mapuj({"icoId": "ARES_00000001", "obchodniJmeno": "JZD"}, None)

    def test_zmena_jmena_dela_dve_verze(self):
        m = mapuj(zakl(), vr(obchodniJmeno=[
            {"datumZapisu": "2010-01-01", "datumVymazu": "2015-06-01", "hodnota": "Starý s.r.o."},
            {"datumZapisu": "2015-06-01", "hodnota": "Vzor s.r.o."},
        ]))
        self.assertEqual([(v["nazev"], v["platnost_od"], v["platnost_do"]) for v in m.verze], [
            ("Starý s.r.o.", date(2010, 1, 1), date(2015, 6, 1)),
            ("Vzor s.r.o.", date(2015, 6, 1), None),
        ])
        # jen aktuálně známé údaje patří jen do poslední verze
        self.assertIsNone(m.verze[0]["dic"])
        self.assertIsNone(m.verze[0]["je_v_insolvenci"])
        self.assertEqual(m.verze[1]["dic"], "CZ12345678")
        self.assertFalse(m.verze[1]["je_v_insolvenci"])

    def test_likvidace_a_insolvence_zaroven(self):
        m = mapuj(
            zakl(seznamRegistraci={"stavZdrojeIr": "AKTIVNI"}),
            vr(statutarniOrgany=[{"typOrganu": "LIKVIDATOR", "nazevOrganu": "Likvidátor",
                                  "clenoveOrganu": [{"datumZapisu": "2020-01-01", "fyzickaOsoba": fo("NOVÁ")}]}]),
        )
        posledni = m.verze[-1]
        self.assertEqual(posledni["stav_kod"], "AKTIVNI")
        self.assertTrue(posledni["je_v_likvidaci"])
        self.assertTrue(posledni["je_v_insolvenci"])
        self.assertFalse(m.verze[0]["je_v_likvidaci"])

    def test_dorucovaci_kopie_sidla_se_neuklada(self):
        m = mapuj(zakl(), None)
        self.assertEqual([a["typ"] for a in m.adresy], ["SIDLO"])

    def test_prepsany_clen_se_slouci_a_platnost_je_dle_funkce(self):
        jednatel = {"clenstvi": {"funkce": {"vznikFunkce": "2010-01-01", "nazev": "jednatel"}},
                    "fyzickaOsoba": fo("NOVÁ")}
        m = mapuj(zakl(), vr(statutarniOrgany=[{
            "typOrganu": "STATUTARNI_ORGAN", "nazevOrganu": "Statutární orgán",
            "clenoveOrganu": [
                {**jednatel, "datumZapisu": "2010-03-01", "datumVymazu": "2020-01-01"},
                {**jednatel, "datumZapisu": "2020-01-01"},
            ]}]))
        self.assertEqual(len(m.vazby), 1)
        v = m.vazby[0]
        self.assertEqual((v["platnost_od"], v["platnost_do"]), (date(2010, 1, 1), None))
        self.assertEqual((v["datum_zapisu_or"], v["datum_vymazu_or"]), (date(2010, 3, 1), None))

    def test_zahranicni_po_bez_ico(self):
        akcionar = {"datumZapisu": "2012-01-01", "clenoveOrganu": [
            {"datumZapisu": "2012-01-01",
             "pravnickaOsoba": {"obchodniJmeno": "FOREIGN LTD", "adresa": {"kodStatu": "CY"}}},
            {"datumZapisu": "2011-01-01", "datumVymazu": "2012-01-01",
             "pravnickaOsoba": {"obchodniJmeno": "BEZ STATU LTD", "adresa": {"textovaAdresa": "?"}}},
        ], "typOrganu": "AKCIONAR"}
        m = mapuj(zakl(pravniForma="121"), vr(akcionari=[akcionar]))
        self.assertEqual(len(m.vazby), 1)
        self.assertEqual(m.vazby[0]["clen"], {"typ": "POJMENOVANY", "nazev": "FOREIGN LTD", "stat": "CY"})
        self.assertEqual(m.vazby[0]["role_kod"], "JEDINY_AKCIONAR")
        self.assertEqual(m.preskoceno[0][0], "PO bez IČO a bez názvu/státu")

    def test_podil_spolecnika(self):
        m = mapuj(zakl(), vr(spolecnici=[{"typOrganu": "SPOLECNIK", "nazevOrganu": "Společníci", "spolecnik": [{
            "datumZapisu": "2010-01-01",
            "osoba": {"datumZapisu": "2010-01-01", "fyzickaOsoba": fo("NOVÁ")},
            "podil": [{"datumZapisu": "2010-01-01",
                       "vklad": {"typObnos": "KORUNY", "hodnota": "8000;00"},
                       "velikostPodilu": {"typObnos": "TEXT", "hodnota": "padesát procent"},
                       "splaceni": {"typObnos": "PROCENTA", "hodnota": "100"}}],
        }]}]))
        v = m.vazby[0]
        self.assertEqual((v["vklad"], v["vklad_mena"]), (Decimal("8000.00"), "CZK"))
        self.assertEqual(v["podil_text"], "padesát procent")
        self.assertIsNone(v["podil_procento"])
        self.assertEqual(v["splaceno_procento"], Decimal("100"))


if __name__ == "__main__":
    unittest.main()
