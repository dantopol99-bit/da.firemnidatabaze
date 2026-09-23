"""Nasadí SQL skripty ze složky sql/<schema>/ do databáze (v abecedním pořadí).

Spuštění:  python -m firemni_databaze.nasad_sql dev

Skripty jsou idempotentní, takže je lze spouštět opakovaně.
Každý soubor běží v samostatné transakci – při chybě se soubor celý vrátí.
"""

import argparse
import sys
from pathlib import Path

from firemni_databaze.db import get_engine

SQL_DIR = Path(__file__).resolve().parents[2] / "sql"
POVOLENA_SCHEMATA = ("dev",)  # test a prod zatím nenasazujeme


def sql_soubory(schema: str) -> list[Path]:
    return sorted((SQL_DIR / schema).glob("*.sql"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("schema", choices=POVOLENA_SCHEMATA)
    args = parser.parse_args()

    soubory = sql_soubory(args.schema)
    if not soubory:
        print(f"Ve složce {SQL_DIR / args.schema} nejsou žádné .sql soubory.")
        return 1

    engine = get_engine()
    for soubor in soubory:
        print(f"-> {soubor.name}")
        raw = engine.raw_connection()
        try:
            with raw.cursor() as cur:
                cur.execute(soubor.read_text(encoding="utf-8"))
            raw.commit()
        except Exception as exc:  # noqa: BLE001 – srozumitelná hláška
            raw.rollback()
            print(f"CHYBA v {soubor.name}: {exc}")
            return 1
        finally:
            raw.close()

    print(f"Hotovo – nasazeno {len(soubory)} skriptů do schématu '{args.schema}'.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
