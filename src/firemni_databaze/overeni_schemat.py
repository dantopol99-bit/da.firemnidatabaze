"""Ověří, že se lze připojit k databázi a že existují schémata dev, test a prod.

Spuštění:  python -m firemni_databaze.overeni_schemat
"""

import sys

from sqlalchemy import text

from firemni_databaze.db import get_engine

OCEKAVANA_SCHEMATA = ("dev", "test", "prod")


def main() -> int:
    engine = get_engine()
    try:
        with engine.connect() as conn:
            verze = conn.execute(text("SELECT version()")).scalar()
            nalezena = set(
                conn.execute(
                    text("SELECT schema_name FROM information_schema.schemata")
                ).scalars()
            )
    except Exception as exc:  # noqa: BLE001 – chceme srozumitelnou hlášku
        print(f"CHYBA: nepodařilo se připojit k databázi: {exc}")
        return 1

    print(f"Připojeno: {verze}")
    chybi = []
    for schema in OCEKAVANA_SCHEMATA:
        if schema in nalezena:
            print(f"  [OK]    schéma '{schema}' existuje")
        else:
            print(f"  [CHYBÍ] schéma '{schema}' neexistuje")
            chybi.append(schema)

    if chybi:
        print("Některá schémata chybí – viz README, sekce Řešení problémů.")
        return 1
    print("Vše v pořádku.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
