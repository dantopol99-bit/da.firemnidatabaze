"""Kontroly SQL skriptů schématu res, které nepotřebují databázi."""

import re
import unittest

from firemni_databaze import res_zdroj as z
from firemni_databaze.nasad_sql import sql_soubory


def bez_komentaru(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


class TestSqlRes(unittest.TestCase):
    def setUp(self):
        self.soubory = sql_soubory("res")
        self.sql = {s.name: bez_komentaru(s.read_text(encoding="utf-8")).lower() for s in self.soubory}

    def test_skripty_existuji_a_jsou_cislovane(self):
        self.assertGreater(len(self.soubory), 0)
        for soubor in self.soubory:
            self.assertRegex(soubor.name, r"^\d{2}_[a-z_]+\.sql$")

    def test_nemeni_identitni_jadro(self):
        # schéma res smí z dev jen číst (a psát do import_davka přes importér)
        zakazane = re.compile(
            r"\b(create|alter|drop|comment\s+on)\s+(or\s+replace\s+)?"
            r"(table|view|function|trigger|index|domain|column)\s+(if\s+(not\s+)?exists\s+)?dev\.|"
            r"\b(insert\s+into|update|delete\s+from|truncate)\s+dev\."
        )
        for nazev, sql in self.sql.items():
            self.assertIsNone(zakazane.search(sql), nazev)

    def test_jen_schemata_res_a_dev(self):
        for nazev, sql in self.sql.items():
            self.assertNotRegex(sql, r"\b(test|prod)\.", nazev)

    def test_sloupce_tabulek_odpovidaji_souborum(self):
        # každý sloupec ze souboru ČSÚ má v tabulce sloupec stejného jména
        sql = self.sql["03_subjekt.sql"]
        for soubor, tabulka in z.TABULKY.items():
            definice = re.search(rf"create table if not exists res\.{tabulka} \((.*?)\n\);", sql, re.S).group(1)
            sloupce = re.findall(r"^\s{4}([a-z_0-9]+)\s", definice, re.M)
            for s in z.SLOUPCE[soubor]:
                self.assertIn(s.lower(), sloupce, f"{tabulka}: chybí {s}")
            for s in z.SLOUPCE_DATUM[soubor]:
                self.assertRegex(definice, rf"\n\s+{s.lower()}\s+date", f"{tabulka}.{s.lower()} má být date")


if __name__ == "__main__":
    unittest.main()
