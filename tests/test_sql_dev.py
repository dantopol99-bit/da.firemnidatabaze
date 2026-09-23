"""Kontroly SQL skriptů schématu dev, které nepotřebují databázi."""

import re
import unittest

from firemni_databaze.nasad_sql import sql_soubory


def bez_komentaru(sql: str) -> str:
    return re.sub(r"--[^\n]*", "", sql)


class TestSqlDev(unittest.TestCase):
    def setUp(self):
        self.soubory = sql_soubory("dev")

    def test_skripty_existuji_a_jsou_cislovane(self):
        self.assertGreater(len(self.soubory), 0)
        for soubor in self.soubory:
            self.assertRegex(soubor.name, r"^\d{2}_[a-z_]+\.sql$")

    def test_pouze_schema_dev(self):
        # Skripty v sql/dev nesmí sahat do test ani prod
        for soubor in self.soubory:
            sql = bez_komentaru(soubor.read_text(encoding="utf-8")).lower()
            self.assertNotRegex(sql, r"\b(test|prod)\.", soubor.name)

    def test_zadni_skutecni_majitele(self):
        # Rozsah produktu: vazby jen do úrovně obchodního rejstříku
        for soubor in self.soubory:
            sql = bez_komentaru(soubor.read_text(encoding="utf-8")).lower()
            self.assertNotIn("majitel", sql, soubor.name)
            self.assertNotIn("beneficial", sql, soubor.name)


if __name__ == "__main__":
    unittest.main()
