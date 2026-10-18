"""Schéma obor proti databázi: stráž kódů z RES, kontrola číselníku, rozhraní.

Potřebuje PostgreSQL podle .env s nasazeným schématem obor a načtenými kódy
(python -m firemni_databaze.nace_firmy vse), jinak se přeskočí.
"""

import unittest

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


if __name__ == "__main__":
    unittest.main()
