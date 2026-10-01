"""Čeština reportu: tvary územních názvů v 6. pádě z ručně psané tabulky.

Tabulka reporty/cestina/lokativ.yaml je ruční a verzovaná (14 krajů, 77 okresů, ČR).
Text reportu nikdy nepoužije náhradní tvar „v území <název>“: chybí-li území
v tabulce, je to chyba.
"""

from functools import lru_cache
from pathlib import Path

import yaml

TABULKA = Path(__file__).resolve().parents[2] / "reporty" / "cestina" / "lokativ.yaml"


@lru_cache(maxsize=1)
def tabulka() -> dict[str, dict]:
    data = yaml.safe_load(TABULKA.read_text(encoding="utf-8"))
    return {z["kod"]: z for skupina in ("cr", "kraje", "okresy") for z in data[skupina]}


def lokativ(kod: str) -> str:
    """„v Libereckém kraji“, „v okrese Jablonec nad Nisou“, „v Česku“."""
    try:
        return tabulka()[kod]["v"]
    except KeyError:
        raise KeyError(f"území {kod} nemá tvar v 6. pádě v {TABULKA.name}") from None


def velke(text: str) -> str:
    """Jen první písmeno velké (capitalize() by zmenšil názvy krajů)."""
    return text[:1].upper() + text[1:]
