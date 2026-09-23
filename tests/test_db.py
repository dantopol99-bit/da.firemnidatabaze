"""Testy, které nepotřebují běžící databázi.

Spuštění:  python -m unittest discover -s tests
"""

import unittest

from firemni_databaze.db import db_url


class TestDbUrl(unittest.TestCase):
    def test_sestavi_url_z_promennych(self):
        url = db_url(
            {
                "POSTGRES_USER": "u",
                "POSTGRES_PASSWORD": "tajne@heslo",
                "POSTGRES_HOST": "localhost",
                "POSTGRES_PORT": "5433",
                "POSTGRES_DB": "db",
            }
        )
        self.assertEqual(url.drivername, "postgresql+psycopg2")
        self.assertEqual(url.port, 5433)
        self.assertEqual(url.database, "db")
        # heslo se speciálními znaky musí zůstat nepoškozené
        self.assertEqual(url.password, "tajne@heslo")

    def test_vychozi_hodnoty(self):
        url = db_url({})
        self.assertEqual(url.host, "localhost")
        self.assertEqual(url.port, 5432)


if __name__ == "__main__":
    unittest.main()
