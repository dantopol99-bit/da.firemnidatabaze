"""Ochrana malých buněk v reportu (schválené rozhodnutí č. 3, docs/report_metodika.md).

1. V každém členění se buňky pod prahem (výchozí 10) slučují do „ostatní“.
2. Je-li „ostatní“ samo pod prahem, přidá se k němu další nejmenší buňka
   (a další, dokud není „ostatní“ aspoň na prahu). Chráněné buňky (zkoumané
   území, zadané srovnávací kraje) se přeskočí, pokud je z čeho vybírat.
3. Je-li pod prahem celé členění, nezveřejní se z něj nic.
4. Skryté číslo nesmí jít dopočítat odečtem od součtu ani z jiné tabulky:
   ověřuje to `dopocitatelne()` nad soustavou lineárních vztahů mezi
   tabulkami (součty, podskupiny, sloučené „ostatní“).

Buňky s nulou se do členění vůbec nezařazují (nejsou zveřejněny ani sloučeny).
"""

from dataclasses import dataclass, field
from fractions import Fraction

PRAH = 10


@dataclass(frozen=True)
class Bunka:
    kod: str          # jednoznačná proměnná, např. 'forma:101', 'obor@kraj:CZ051'
    nazev: str
    hodnota: int


@dataclass
class Potlaceni:
    celkem: int
    zverejnene: list[Bunka] = field(default_factory=list)
    ostatni: list[Bunka] = field(default_factory=list)   # členové sloučené buňky „ostatní“
    sekundarni: list[str] = field(default_factory=list)  # kódy přidané pravidlem „další nejmenší“
    cele_skryte: bool = False                             # celé členění pod prahem

    @property
    def ostatni_hodnota(self) -> int | None:
        return sum(b.hodnota for b in self.ostatni) if self.ostatni else None

    @property
    def skryte(self) -> set[str]:
        return {b.kod for b in self.ostatni} | (
            {b.kod for b in self.zverejnene} if self.cele_skryte else set())

    def je_zverejnena(self, kod: str) -> bool:
        return not self.cele_skryte and any(b.kod == kod for b in self.zverejnene)


def potlac(bunky: list[Bunka], prah: int = PRAH, chranene: frozenset[str] | set[str] = frozenset()) -> Potlaceni:
    """Použije pravidla 1–3 na jedno členění. Vrací, co se zveřejní a co se sloučí."""
    nenulove = [b for b in bunky if b.hodnota > 0]
    celkem = sum(b.hodnota for b in nenulove)
    if celkem < prah:
        return Potlaceni(celkem, zverejnene=nenulove, cele_skryte=True)

    ostatni = [b for b in nenulove if b.hodnota < prah]
    zbyle = sorted((b for b in nenulove if b.hodnota >= prah), key=lambda b: (b.hodnota, b.kod))
    sekundarni: list[str] = []
    while ostatni and sum(b.hodnota for b in ostatni) < prah:
        kandidat = next((b for b in zbyle if b.kod not in chranene), None) or (zbyle[0] if zbyle else None)
        if kandidat is None:
            break  # nemůže nastat: celkem >= prah
        zbyle.remove(kandidat)
        ostatni.append(kandidat)
        sekundarni.append(kandidat.kod)
    zverejnene = sorted(zbyle, key=lambda b: (-b.hodnota, b.kod))
    return Potlaceni(celkem, zverejnene, ostatni, sekundarni)


# ---------------------------------------------------------------------------
# Kontrola dopočtu: je skrytá proměnná jednoznačně určena zveřejněnými čísly?
# ---------------------------------------------------------------------------

def _redukuj(radek: dict[str, Fraction], baze: list[tuple[str, dict[str, Fraction]]]) -> dict[str, Fraction]:
    radek = dict(radek)
    for pivot, b in baze:
        k = radek.get(pivot)
        if k:
            for v, c in b.items():
                radek[v] = radek.get(v, Fraction(0)) - k * c
                if radek[v] == 0:
                    del radek[v]
    return radek


def dopocitatelne(rovnice: list[tuple[str, list[str]]], zverejnene: set[str], skryte: set[str]) -> list[str]:
    """Vrátí skryté proměnné, které jdou ze zveřejněných čísel dopočítat.

    rovnice: (celek, [části]) znamená celek = součet částí (např. součet
    tabulky, podskupina FO/PO, sloučené „ostatní“). Proměnná je dopočitatelná,
    právě když její jednotkový vektor leží v řádkovém prostoru soustavy
    rovnic doplněné o zveřejněné proměnné (Gaussova eliminace nad zlomky).
    Meze plynoucí z nezápornosti (intervaly) se neposuzují.
    """
    radky: list[dict[str, Fraction]] = []
    for celek, casti in rovnice:
        r: dict[str, Fraction] = {celek: Fraction(1)}
        for c in casti:
            r[c] = r.get(c, Fraction(0)) - 1
        radky.append({k: v for k, v in r.items() if v != 0})
    radky += [{v: Fraction(1)} for v in zverejnene]

    baze: list[tuple[str, dict[str, Fraction]]] = []
    for r in radky:
        r = _redukuj(r, baze)
        if not r:
            continue
        pivot = min(r)
        k = r[pivot]
        r = {v: c / k for v, c in r.items()}
        # udržovat bázi redukovanou i ve starších řádcích
        baze = [(p, _redukuj(b, [(pivot, r)])) for p, b in baze]
        baze.append((pivot, r))
    return sorted(v for v in skryte if not _redukuj({v: Fraction(1)}, baze))
