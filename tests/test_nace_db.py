"""Schéma obor proti databázi: stráž kódů z RES, kontrola číselníku, rozhraní.

Potřebuje PostgreSQL podle .env s nasazeným schématem obor a načtenými kódy
(python -m firemni_databaze.nace_firmy vse), jinak se přeskočí.
"""

import json
import unittest
from datetime import date

from firemni_databaze import nace_firmy as nf
from firemni_databaze.db import get_engine


def pripojeni():
    try:
        conn = get_engine().raw_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('obor.firma_nace') IS NOT NULL")
            if not cur.fetchone()[0]:
                conn.close()
                return None
            cur.execute("SELECT EXISTS (SELECT 1 FROM obor.firma_nace WHERE zdroj = 'RES')")
            if not cur.fetchone()[0]:
                conn.close()
                return None
        conn.rollback()
        return conn
    except Exception:  # noqa: BLE001 – bez databáze se testy přeskočí
        return None


CONN = pripojeni()


@unittest.skipIf(CONN is None, "databáze se schématem obor a načtenými kódy není dostupná")
class TestObor(unittest.TestCase):
    def tearDown(self):
        CONN.rollback()

    def dotaz(self, sql, *parametry):
        with CONN.cursor() as cur:
            cur.execute(sql, parametry)
            return cur.fetchall()

    def test_kody_res_nejde_smazat_ani_zmenit(self):
        with CONN.cursor() as cur:
            cur.execute("SELECT id FROM obor.firma_nace WHERE zdroj = 'RES' AND verze = 2008 LIMIT 1")
            id_ = cur.fetchone()[0]
            with self.assertRaises(Exception):
                cur.execute("DELETE FROM obor.firma_nace WHERE id = %s", (id_,))
        CONN.rollback()
        with CONN.cursor() as cur, self.assertRaises(Exception):
            cur.execute("UPDATE obor.firma_nace SET kod = 'F' WHERE id = %s", (id_,))

    def test_kody_jsou_v_ciselniku_sve_verze(self):
        self.assertEqual(self.dotaz("SELECT * FROM obor.v_firma_nace_mimo_ciselnik"), [])

    def test_rozhrani_jeden_radek_na_ico(self):
        (pocet, ruznych), = self.dotaz("SELECT count(*), count(DISTINCT ico) FROM obor.v_firma_obor_aktualni")
        self.assertEqual(pocet, ruznych)

    def test_odvozene_maji_jistotu_nebo_priznak(self):
        self.assertEqual(self.dotaz(
            "SELECT count(*) FROM obor.firma_nace WHERE zdroj = 'odvozeno' "
            "AND NOT ((kod IS NOT NULL AND jistota BETWEEN 0 AND 1) OR (kod IS NULL AND priznak = 'nejednoznacne'))"
        ), [(0,)])

    def test_res_ma_prednost_pred_odvozenim(self):
        self.assertEqual(self.dotaz(
            "SELECT count(*) FROM obor.v_firma_obor_aktualni v WHERE v.zdroj = 'odvozeno' AND EXISTS ("
            "SELECT 1 FROM obor.firma_nace f WHERE f.ico = v.ico AND f.verze = 2025 AND f.zdroj = 'RES' "
            "AND f.typ = 'hlavni')"
        ), [(0,)])

    def test_6_zadny_kod_2025_z_res_nezacina_pred_2025(self):
        self.assertEqual(self.dotaz("SELECT count(*) FROM obor.firma_nace WHERE zdroj = 'RES' AND verze = 2025 "
                                    "AND platnost_od < DATE '2025-01-01'"), [(0,)])
        self.assertEqual(self.dotaz("SELECT obor.zacatek_2025(DATE '2023-06-29'), obor.konec_2025(DATE '2024-03-01'), "
                                    "obor.konec_2025(DATE '2026-02-01')"),
                         [(date(2025, 1, 1), date(2025, 1, 1), date(2026, 2, 1))])

    def test_6_straz_povoli_jen_posun_na_1_1_2025(self):
        with CONN.cursor() as cur, self.assertRaises(Exception):
            cur.execute("UPDATE obor.firma_nace SET platnost_od = DATE '2025-03-01' WHERE id = "
                        "(SELECT min(id) FROM obor.firma_nace WHERE zdroj = 'RES' AND verze = 2025)")

    def test_2_rozpory_jsou_zapsane(self):
        rozpory = dict(((k, u), (cp, ce)) for k, u, cp, ce in self.dotaz(
            "SELECT kod_2008, uroven, cil_prevodnik, cil_empirie FROM obor.nace_rozpory_prevodnik "
            "WHERE zaklad_k = (SELECT max(zaklad_k) FROM obor.nace_rozpory_prevodnik)"))
        self.assertEqual(rozpory.get(("9609", 4)), ("9699", "9691"))
        metody = dict(self.dotaz(
            "SELECT kod_2008, metoda FROM obor.nace_odvozeni WHERE uroven = 4 AND kod_2008 = '9609' "
            "AND zaklad_k = (SELECT max(zaklad_k) FROM obor.nace_odvozeni)"))
        self.assertEqual(metody, {"9609": "empiricky_rozpor"})

    def test_7_konec_dvojiho_kodovani_se_simulovanym_datem(self):
        # záznam ARES (endpoint ekonomicke-subjekty-res) ze surových dat, dnešek posunutý za 31. 12. 2028
        radky = self.dotaz("SELECT ico, raw FROM dev.import_surova_data WHERE endpoint = 'ekonomicke-subjekty-res' "
                           "AND ico IN (SELECT ico FROM obor.firma_nace WHERE verze = 2008 AND zdroj = 'RES' "
                           "AND platnost_do IS NULL) ORDER BY id DESC LIMIT 1")
        if not radky:
            self.skipTest("chybí surová odpověď ARES ekonomicke-subjekty-res")
        ico, raw = radky[0]
        raw = raw if isinstance(raw, dict) else json.loads(raw)
        zaznam = next(z for z in raw["zaznamy"] if z.get("primarniZaznam"))
        pred = self.dotaz("SELECT count(*) FROM obor.firma_nace WHERE ico = %s AND verze = 2025 "
                          "AND platnost_do IS NULL", ico)
        with CONN.cursor() as cur:
            nf.zapis_ares(cur, ico, zaznam, None, dnes=date(2029, 1, 15))
            self.assertEqual(nf.uzavri_kody_2008(cur, ico), 0)          # podruhé už nic
        self.assertEqual(self.dotaz(
            "SELECT DISTINCT platnost_do, duvod_uzavreni FROM obor.firma_nace WHERE ico = %s AND verze = 2008 "
            "AND zdroj = 'RES' AND platnost_do >= DATE '2028-12-31'", ico),
            [(date(2028, 12, 31), "konec dvojího kódování")])
        self.assertEqual(self.dotaz("SELECT count(*) FROM obor.firma_nace WHERE ico = %s AND verze = 2008 "
                                    "AND zdroj = 'RES' AND platnost_do IS NULL", ico), [(0,)])
        # kódy 2025 zůstávají otevřené; nic se nesmazalo (tearDown vrátí transakci)
        self.assertEqual(self.dotaz("SELECT count(*) FROM obor.firma_nace WHERE ico = %s AND verze = 2025 "
                                    "AND platnost_do IS NULL", ico), pred)


if __name__ == "__main__":
    unittest.main()
