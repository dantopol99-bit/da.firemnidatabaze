"""Výpočetní vrstva Oborově-regionálního reportu (v0, bez PDF).

Spuštění:
    python -m firemni_databaze.report --obor F --uzemi CZ051
    python -m firemni_databaze.report --obor 10 --uzemi "Kraj Vysočina" --srovnani CZ052,CZ053
    python -m firemni_databaze.report --obor 62 --uzemi CZ0714 --datum 2026-09-15
    python -m firemni_databaze.report --obor 41,42,43 --uzemi CZ

Obor = kódy CZ-NACE Rev. 2 (sekce, oddíl, skupina nebo třída, i seznam).
Území = ČR (CZ), kraj (CZ-NUTS 3 nebo název) nebo okres (kód z číselníku 109
nebo název). Srovnávací kraje zadává člověk (--srovnani); automaticky se
srovnává jen s ČR a pořadím mezi všemi kraji.

Výstup do reporty/vystupy/<obor>__<území>__<datum>/:
    vysledek.json   strukturovaný výsledek (jen zveřejnitelná čísla)
    vysledek.md     tytéž tabulky pro čtení
    priloha.xlsx    datová příloha (tabulky, Metodika, Zdroj a licence)
    _interni/kontrola.json  proměnné a vztahy pro kontrolu dopočtu – NEZVEŘEJŇOVAT
Pravidla prahu a slučování (report_potlaceni) jsou ve výstupu už aplikovaná.
"""

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from firemni_databaze.db import get_engine
from firemni_databaze.report_potlaceni import PRAH, Bunka, Potlaceni, dopocitatelne, potlac

KOREN = Path(__file__).resolve().parents[2]
KATALOG = KOREN / "reporty" / "katalog_ukazatelu.yaml"
VYSTUPY = KOREN / "reporty" / "vystupy"

KLASIFIKACE = 80004                      # rozhodnutí 5: v0 = CZ-NACE Rev. 2 (sloupec NACE)
FO_FORMY = frozenset({"101", "102", "103", "104", "105", "106", "107", "108", "424", "425"})
PASMA_VEKU = (            # (od, do (bez), kód, název)
    (0, 3, "0-2", "méně než 3 roky"),
    (3, 6, "3-5", "3–5 let"),
    (6, 11, "6-10", "6–10 let"),
    (11, 21, "11-20", "11–20 let"),
    (21, 31, "21-30", "21–30 let"),
    (31, None, "31+", "31 a více let"),
)
PASMA_VELIKOSTI = (       # (kód, název, kódy KATPO 579)
    ("110", "bez zaměstnanců", {"110"}),
    ("1-9", "1–9 zaměstnanců", {"120", "130"}),
    ("10-49", "10–49 zaměstnanců", {"210", "220", "230"}),
    ("50-249", "50–249 zaměstnanců", {"240", "310", "320"}),
    ("250+", "250 a více zaměstnanců", {"330", "340", "410", "420", "430", "440", "450", "460", "470", "510"}),
    ("000", "Neuvedeno", {"000"}),
)
ZANIKY_OD_ROKU = 2023     # rozhodnutí 4
MIN_ROZSAH = 100          # rozhodnutí 8: pod 100 registrovanými subjekty se report nevydá
PRAH_SPOLEHLIVOSTI = 25.0 # rozhodnutí 9: podíl „jen do sekce“ nad 25 % = varování
ODVETVI_DEMOGRAFIE = {    # sekce CZ-NACE → položka RESDP00 (jen kde existuje)
    **{k: k for k in "BCDEFGHIJLMNPQR"}, "K": "64660002", "S": "95960001",
}
DEMOGRAFIE_CELKEM = "05960003"
LICENCE_URL = "https://csu.gov.cz/podminky_pro_vyuzivani_a_dalsi_zverejnovani_statistickych_udaju_csu"
OZNACENI = "Odvozené údaje, nejde o oficiální statistiku ČSÚ."


def citace(datum_snimku: date) -> str:
    return (f"Zdroj: Český statistický úřad, Registr ekonomických subjektů (RES) – otevřená data, "
            f"stav k {datum_snimku.day}. {datum_snimku.month}. {datum_snimku.year}; licence CC BY 4.0 "
            f"({LICENCE_URL}); vlastní výpočet.")


# ---------------------------------------------------------------------------
# Zadání, obor, území
# ---------------------------------------------------------------------------

@dataclass
class Zadani:
    obor: list[str]
    uzemi: str
    datum: date | None = None
    srovnani: list[str] = field(default_factory=list)
    prah: int = PRAH
    min_rozsah: int = MIN_ROZSAH


class MalyRozsah(ValueError):
    """Rozhodnutí 8: obor × území má méně než MIN_ROZSAH subjektů – report se nevydá."""

    def __init__(self, zadani: str, pocet: int, min_rozsah: int, navrhy: list[dict]):
        self.zadani, self.pocet, self.min_rozsah, self.navrhy = zadani, pocet, min_rozsah, navrhy
        super().__init__(f"{zadani}: {pocet} registrovaných subjektů, méně než {min_rozsah} – report se nevydá")

    def vypis(self) -> str:
        radky = [str(self), "Návrh vyšší úrovně:"]
        for n in self.navrhy:
            znak = "✔" if n["pocet"] >= self.min_rozsah else "✘"
            radky.append(f"  {znak} {n['popis']}: {n['pocet']} subjektů"
                         f"   (python -m firemni_databaze.report --obor {','.join(n['obor'])} --uzemi {n['uzemi']})")
        return "\n".join(radky)


@dataclass
class Uzemi:
    typ: str              # CR / KRAJ / OKRES
    kod: str
    nazev: str
    kraj_kod: str | None  # u okresu jeho kraj, u kraje on sám

    @property
    def promenna(self) -> str:
        return {"CR": "obor@CZ", "KRAJ": f"obor@kraj:{self.kod}", "OKRES": f"obor@okres:{self.kod}"}[self.typ]


def nacti_uzemi(cur) -> tuple[dict, dict]:
    cur.execute("SELECT kod, nazev, kod_ruian FROM res.cis_kraj WHERE kod_ruian IS NOT NULL ORDER BY kod")
    kraje = {k: {"nazev": n, "kod_ruian": r} for k, n, r in cur.fetchall()}
    cur.execute("SELECT kod, nazev, kraj_kod FROM res.cis_okres WHERE kraj_kod = ANY(%s) ORDER BY kod", (list(kraje),))
    okresy = {k: {"nazev": n, "kraj_kod": kr} for k, n, kr in cur.fetchall()}
    return kraje, okresy


def urci_uzemi(text: str, kraje: dict, okresy: dict) -> Uzemi:
    t = text.strip()
    if t.upper() in ("CZ", "ČR", "CR", "ČESKO"):
        return Uzemi("CR", "CZ", "Česko", None)
    for kod, k in kraje.items():
        if t.upper() == kod or t.lower() == k["nazev"].lower():
            return Uzemi("KRAJ", kod, k["nazev"], kod)
    nalezene = [(kod, o) for kod, o in okresy.items() if t.upper() == kod or t.lower() == o["nazev"].lower()]
    if len(nalezene) == 1:
        kod, o = nalezene[0]
        return Uzemi("OKRES", kod, o["nazev"], o["kraj_kod"])
    raise ValueError(f"neznámé nebo nejednoznačné území: {text!r} (použij kód CZ, CZ-NUTS 3 kraje nebo kód okresu)")


def urci_obor(cur, kody: list[str]) -> list[dict]:
    """Kódy CZ-NACE Rev. 2 → položky číselníku s úrovní a předky."""
    obor = []
    for kod in kody:
        cur.execute(
            "SELECT kod, uroven, nazev, sekce, oddil, skupina, trida, je_pseudokod FROM res.cis_nace "
            "WHERE klasifikace = %s AND kod = %s", (KLASIFIKACE, kod.strip().upper()))
        r = cur.fetchone()
        if r is None:
            raise ValueError(f"kód {kod!r} není v CZ-NACE Rev. 2 (CZ_NACE_RES)")
        k, uroven, nazev, sekce, oddil, skupina, trida, pseudo = r
        if pseudo:
            raise ValueError(f"{k} je pseudokód RES, ne obor")
        if uroven > 4:
            raise ValueError(f"{k}: obor lze zadat do úrovně třídy (4 číslice), ne podtřídy")
        predci = [p for p in (sekce, oddil, skupina, trida)[:uroven - 1] if p]
        obor.append({"kod": k, "uroven": uroven, "nazev": nazev, "sekce": sekce, "predci": predci})
    kody_oboru = {o["kod"] for o in obor}
    for o in obor:
        prekryv = kody_oboru & set(o["predci"])
        if prekryv:
            raise ValueError(f"obor {o['kod']} je už obsažen v {sorted(prekryv)} – zadej jen jeden z nich")
    return obor


def popis_oboru(obor: list[dict]) -> str:
    return "; ".join(f"{o['kod']} {o['nazev']}" for o in obor)


# ---------------------------------------------------------------------------
# Data z databáze
# ---------------------------------------------------------------------------

def nacti_data(cur, obor: list[dict], datum: date) -> dict:
    podle_urovne = {u: [o["kod"] for o in obor if o["uroven"] == u] for u in (1, 2, 3, 4)}
    parametry = {"d": datum, "s1": podle_urovne[1], "s2": podle_urovne[2], "s3": podle_urovne[3], "s4": podle_urovne[4]}
    podminka = ("NOT n.je_pseudokod AND (n.sekce = ANY(%(s1)s) OR n.oddil = ANY(%(s2)s) "
                "OR n.skupina = ANY(%(s3)s) OR n.trida = ANY(%(s4)s))")
    cur.execute(
        "SELECT s.okreslau, s.forma, s.katpo, s.ddatvzn FROM res.subjekt s "
        "JOIN res.cis_nace n ON n.klasifikace = 80004 AND n.kod = s.nace "
        f"WHERE s.datum_snimku = %(d)s AND s.ddatzan IS NULL AND {podminka}", parametry)
    subjekty = cur.fetchall()
    cur.execute(
        "SELECT s.okreslau, extract(year FROM s.ddatzan)::int FROM res.subjekt s "
        "JOIN res.cis_nace n ON n.klasifikace = 80004 AND n.kod = s.nace "
        f"WHERE s.datum_snimku = %(d)s AND s.ddatzan >= make_date({ZANIKY_OD_ROKU}, 1, 1) "
        f"AND s.forma IS NOT NULL AND NOT (s.forma = ANY(%(fo)s)) AND {podminka}",
        {**parametry, "fo": sorted(FO_FORMY)})
    zaniky_po = cur.fetchall()
    cur.execute("SELECT okreslau, count(*) FROM res.subjekt WHERE datum_snimku = %s AND ddatzan IS NULL "
                "GROUP BY okreslau", (datum,))
    vse_okres = dict(cur.fetchall())
    predci = sorted({p for o in obor for p in o["predci"]})
    cur.execute("SELECT nace, okreslau, count(*) FROM res.subjekt WHERE datum_snimku = %s AND ddatzan IS NULL "
                "AND nace = ANY(%s) GROUP BY nace, okreslau", (datum, predci + ["00"]))
    doplnky = cur.fetchall()
    cur.execute("SELECT kod, nazev FROM res.cis_nace WHERE klasifikace = 80004 AND kod = ANY(%s)", (predci,))
    nazvy_predku = dict(cur.fetchall())
    cur.execute("SELECT kod, nazev FROM res.cis_pravni_forma WHERE ciselnik = 56")
    formy = dict(cur.fetchall())
    cur.execute("SELECT uzemi_kod, hodnota, rok FROM res.csu_obyvatelstvo WHERE ukazatel_kod = '2406K2' "
                "AND rok = (SELECT max(rok) FROM res.csu_obyvatelstvo WHERE ukazatel_kod = '2406K2')")
    obyv = cur.fetchall()
    cur.execute("SELECT max(obdobi) FROM res.csu_agregat WHERE vyber = 'RES02QT1'")
    obdobi_akt = cur.fetchone()[0]
    cur.execute("SELECT uzemi_kod, nace_kod, ukazatel_kod, hodnota FROM res.csu_agregat "
                "WHERE vyber = 'RES02QT1' AND obdobi = %s", (obdobi_akt,))
    aktivita = {}
    for u, n, k, h in cur.fetchall():
        aktivita.setdefault((u, n), {})[k] = float(h)
    return {
        "subjekty": subjekty, "zaniky_po": zaniky_po, "vse_okres": vse_okres, "doplnky": doplnky,
        "nazvy_predku": nazvy_predku, "formy": formy,
        "obyvatele": {u: float(h) for u, h, _ in obyv}, "rok_obyvatel": obyv[0][2] if obyv else None,
        "aktivita": aktivita, "obdobi_aktivity": obdobi_akt,
    }


def pocet_oboru(cur, obor: list[dict], uz: "Uzemi", datum: date) -> int:
    """Počet registrovaných subjektů oboru v území (pro návrhy vyšší úrovně)."""
    podle_urovne = {u: [o["kod"] for o in obor if o["uroven"] == u] for u in (1, 2, 3, 4)}
    cur.execute(
        "SELECT count(*) FROM res.subjekt s JOIN res.cis_nace n ON n.klasifikace = 80004 AND n.kod = s.nace "
        "JOIN res.cis_okres o ON o.kod = s.okreslau "
        "WHERE s.datum_snimku = %(d)s AND s.ddatzan IS NULL AND NOT n.je_pseudokod "
        "AND (n.sekce = ANY(%(s1)s) OR n.oddil = ANY(%(s2)s) OR n.skupina = ANY(%(s3)s) OR n.trida = ANY(%(s4)s)) "
        "AND (%(typ)s = 'CR' OR (%(typ)s = 'KRAJ' AND o.kraj_kod = %(kod)s) OR (%(typ)s = 'OKRES' AND o.kod = %(kod)s))",
        {"d": datum, "s1": podle_urovne[1], "s2": podle_urovne[2], "s3": podle_urovne[3], "s4": podle_urovne[4],
         "typ": uz.typ, "kod": uz.kod})
    return cur.fetchone()[0]


def navrhy_vyssi_urovne(cur, obor: list[dict], uz: "Uzemi", kraje: dict, datum: date) -> list[dict]:
    """Rozhodnutí 8: okres → kraj, třída/skupina → oddíl → sekce (i kombinace), s počty."""
    oddily = sorted({o["predci"][1] if o["uroven"] > 2 else o["kod"] for o in obor if o["uroven"] >= 2})
    sekce = sorted({o["sekce"] for o in obor})
    urovne_oboru = [(obor, popis_oboru(obor))]
    if any(o["uroven"] > 2 for o in obor):
        o2 = urci_obor(cur, oddily) + [o for o in obor if o["uroven"] == 1]
        urovne_oboru.append((o2, popis_oboru(o2)))
    if any(o["uroven"] > 1 for o in obor):
        o1 = urci_obor(cur, sekce)
        urovne_oboru.append((o1, popis_oboru(o1)))
    uzemi = [uz]
    if uz.typ == "OKRES":
        uzemi.append(Uzemi("KRAJ", uz.kraj_kod, kraje[uz.kraj_kod]["nazev"], uz.kraj_kod))
    navrhy = []
    for o, popis in urovne_oboru:
        for u in uzemi:
            if o is obor and u is uz:
                continue
            navrhy.append({"obor": [x["kod"] for x in o], "uzemi": u.kod,
                           "popis": f"{popis} × {u.nazev}", "pocet": pocet_oboru(cur, o, u, datum)})
    return navrhy


def nacti_demografii(cur, sekce: str | None) -> list[tuple]:
    kody = [DEMOGRAFIE_CELKEM] + ([ODVETVI_DEMOGRAFIE[sekce]] if sekce in ODVETVI_DEMOGRAFIE else [])
    cur.execute("SELECT odvetvi_kod, odvetvi, forma_kod, rok, ukazatel_kod, hodnota, predbezna "
                "FROM res.csu_demografie WHERE odvetvi_kod = ANY(%s) ORDER BY rok", (kody,))
    return cur.fetchall()


def nacti_dynamiku(cur, uzemi_kod: str) -> list[tuple]:
    cur.execute("SELECT forma_kod, obdobi, ukazatel_kod, hodnota FROM res.csu_vznik_zanik WHERE uzemi_kod = %s "
                "AND obdobi >= %s ORDER BY obdobi", (uzemi_kod, f"{ZANIKY_OD_ROKU}-Q1"))
    return cur.fetchall()


# ---------------------------------------------------------------------------
# Sestava: tabulky + proměnné + lineární vztahy (pro kontrolu dopočtu)
# ---------------------------------------------------------------------------

class Sestava:
    def __init__(self, prah: int):
        self.prah = prah
        self.tabulky: list[dict] = []
        self.promenne: dict[str, dict] = {}   # kód → {hodnota, zverejneno}
        self.rovnice: list[tuple[str, list[str]]] = []

    def promenna(self, kod: str, hodnota: int, zverejneno: bool) -> None:
        stara = self.promenne.get(kod)
        if stara and stara["hodnota"] != hodnota:
            raise AssertionError(f"proměnná {kod} má dvě hodnoty: {stara['hodnota']} a {hodnota}")
        self.promenne[kod] = {"hodnota": hodnota, "zverejneno": zverejneno or bool(stara and stara["zverejneno"])}

    def zverejnena(self, kod: str) -> bool:
        return self.promenne.get(kod, {}).get("zverejneno", False)

    def rovnice_souctu(self, celek: str, casti: list[str]) -> None:
        self.rovnice.append((celek, list(casti)))

    def zaznamenej_potlaceni(self, p: Potlaceni, celek: str, ostatni_kod: str | None) -> None:
        if celek not in self.promenne:
            # nulový součet není citlivé malé číslo – je známý (členění je prázdné)
            self.promenna(celek, p.celkem, not p.cele_skryte or p.celkem == 0)
        for b in p.zverejnene:
            self.promenna(b.kod, b.hodnota, not p.cele_skryte)
        for b in p.ostatni:
            self.promenna(b.kod, b.hodnota, False)
        self.rovnice_souctu(celek, [b.kod for b in p.zverejnene + p.ostatni])
        if p.ostatni and ostatni_kod:
            self.promenna(ostatni_kod, p.ostatni_hodnota, not p.cele_skryte)
            self.rovnice_souctu(ostatni_kod, [b.kod for b in p.ostatni])

    def kontrola_dopoctu(self) -> list[str]:
        zverejnene = {k for k, v in self.promenne.items() if v["zverejneno"]}
        skryte = {k for k, v in self.promenne.items() if not v["zverejneno"]}
        return dopocitatelne(self.rovnice, zverejnene, skryte)


def _pct(a: float, b: float, mista: int = 1) -> float | None:
    return round(100 * a / b, mista) if b else None


def _poradi(hodnoty: dict[str, float]) -> dict[str, int]:
    """Pořadí 1 = nejvyšší; shodné hodnoty mají stejné pořadí."""
    serazene = sorted(hodnoty.values(), reverse=True)
    return {k: serazene.index(v) + 1 for k, v in hodnoty.items()}


def tabulka_cleneni(s: Sestava, kod: str, nazev: str, p: Potlaceni, celek: str, uk_pocet: str, uk_podil: str,
                    ostatni_nazev: str = "ostatní (sloučené malé položky)", poznamky=(), skupina: str | None = None,
                    radky_navic: list[dict] | None = None, poradi: list[str] | None = None) -> dict:
    """Tabulka jednoho členění (počet + podíl) s aplikovaným potlačením.
    poradi = pevné pořadí položek (pásma, roky); jinak podle počtu sestupně."""
    ostatni_kod = f"ostatni:{kod}" + (f":{skupina}" if skupina else "")
    s.zaznamenej_potlaceni(p, celek, ostatni_kod)
    radky = []
    if not p.cele_skryte:
        polozky = sorted(p.zverejnene, key=lambda b: poradi.index(b.kod)) if poradi else p.zverejnene
        for b in polozky:
            radky.append({"popis": b.nazev, "typ": "polozka", "promenna": b.kod,
                          "hodnoty": {"pocet": b.hodnota, "podil": _pct(b.hodnota, p.celkem)}})
        if p.ostatni:
            radky.append({"popis": ostatni_nazev, "typ": "ostatni", "promenna": ostatni_kod,
                          "hodnoty": {"pocet": p.ostatni_hodnota, "podil": _pct(p.ostatni_hodnota, p.celkem)}})
        radky.append({"popis": "celkem", "typ": "celkem", "promenna": celek,
                      "hodnoty": {"pocet": p.celkem, "podil": 100.0}})
    if radky and not p.zverejnene and not radky_navic:
        # všechno sloučeno do „ostatní“ = součet: tabulka by nic neříkala
        radky, duvod = [], "všechny položky pod prahem – zůstal by jen součet"
    else:
        duvod = ("v území žádné" if p.celkem == 0 else "celé členění pod prahem") if p.cele_skryte else None
    return {
        "kod": kod, "nazev": nazev,
        "sloupce": [{"kod": "pocet", "nazev": "Počet registrovaných subjektů", "ukazatel": uk_pocet},
                    {"kod": "podil", "nazev": "Podíl (%)", "ukazatel": uk_podil}],
        "radky": (radky_navic or []) + radky,
        "zverejneno": bool(radky) or bool(radky_navic),
        "duvod": duvod,
        "poznamky": list(poznamky),
    }


def tabulka_nezverejnena(kod: str, nazev: str, duvod: str, sloupce: list[dict]) -> dict:
    return {"kod": kod, "nazev": nazev, "sloupce": sloupce, "radky": [], "zverejneno": False,
            "duvod": duvod, "poznamky": []}


# ---------------------------------------------------------------------------
# Výpočet
# ---------------------------------------------------------------------------

def spocitej(conn, zadani: Zadani) -> tuple[dict, dict]:
    """Vrátí (veřejný výsledek, interní data pro kontrolu dopočtu)."""
    katalog = {u["kod"]: u for u in yaml.safe_load(KATALOG.read_text(encoding="utf-8"))["ukazatele"]}
    with conn.cursor() as cur:
        cur.execute("SELECT max(datum_snimku) FROM res.snimek WHERE soubor = 'res_data.csv'"
                    + (" AND datum_snimku = %s" if zadani.datum else ""),
                    (zadani.datum,) if zadani.datum else ())
        datum = cur.fetchone()[0]
        if datum is None:
            raise ValueError(f"snímek RES k {zadani.datum} není načtený")
        kraje, okresy = nacti_uzemi(cur)
        uz = urci_uzemi(zadani.uzemi, kraje, okresy)
        srovnani = [urci_uzemi(k, kraje, okresy) for k in zadani.srovnani]
        for k in srovnani:
            if k.typ != "KRAJ":
                raise ValueError(f"srovnávací území musí být kraj: {k.nazev}")
        obor = urci_obor(cur, zadani.obor)
        d = nacti_data(cur, obor, datum)
        dynamika = nacti_dynamiku(cur, uz.kod)
        sekce_oboru = {o["sekce"] for o in obor}
        demografie = nacti_demografii(cur, next(iter(sekce_oboru)) if len(sekce_oboru) == 1 else None)
        n_zadani = pocet_oboru(cur, obor, uz, datum)
        if n_zadani < zadani.min_rozsah:
            raise MalyRozsah(f"{popis_oboru(obor)} × {uz.nazev}", n_zadani, zadani.min_rozsah,
                             navrhy_vyssi_urovne(cur, obor, uz, kraje, datum))
    conn.rollback()

    prah = zadani.prah
    s = Sestava(prah)
    okres_kraj = {k: o["kraj_kod"] for k, o in okresy.items()}

    # --- počty podle okresů a krajů --------------------------------------------------
    obor_okres: dict[str, int] = {}
    for okres, *_ in d["subjekty"]:
        obor_okres[okres] = obor_okres.get(okres, 0) + 1
    obor_kraj = {k: 0 for k in kraje}
    for okres, n in obor_okres.items():
        obor_kraj[okres_kraj[okres]] += n
    n_cr = sum(obor_kraj.values())
    vse_kraj = {k: 0 for k in kraje}
    for okres, n in d["vse_okres"].items():
        if okres in okres_kraj:
            vse_kraj[okres_kraj[okres]] += n
    vse_cr = sum(d["vse_okres"].values())
    obyv = dict(d["obyvatele"])
    obyv.setdefault("CZ0100", obyv.get("CZ010"))            # okres Praha = kraj Praha

    def v_uzemi(okres: str | None, u: Uzemi) -> bool:
        return (u.typ == "CR" or (u.typ == "KRAJ" and okres_kraj.get(okres) == u.kod)
                or (u.typ == "OKRES" and okres == u.kod))

    def pocet_uzemi(u: Uzemi) -> int:
        return {"CR": n_cr, "KRAJ": obor_kraj.get(u.kod, 0), "OKRES": obor_okres.get(u.kod, 0)}[u.typ]

    def vse_uzemi(u: Uzemi) -> int:
        return {"CR": vse_cr, "KRAJ": vse_kraj.get(u.kod, 0), "OKRES": d["vse_okres"].get(u.kod, 0)}[u.typ]

    def lq(u: Uzemi) -> float | None:
        a, b = pocet_uzemi(u), vse_uzemi(u)
        return round((a / b) / (n_cr / vse_cr), 2) if b and n_cr else None

    def hustota(pocet: int, uzemi_kod: str) -> float | None:
        o = obyv.get(uzemi_kod)
        return round(1000 * pocet / o, 2) if o else None

    # --- ČR (vždy zveřejněná, je-li nad prahem) -----------------------------------------
    s.promenna("obor@CZ", n_cr, n_cr >= prah)

    # --- T03 pořadí krajů ----------------------------------------------------------------
    chranene = {f"obor@kraj:{k.kod}" for k in srovnani}
    if uz.kraj_kod:
        chranene.add(f"obor@kraj:{uz.kraj_kod}")
    p_kraje = potlac([Bunka(f"obor@kraj:{k}", kraje[k]["nazev"], obor_kraj[k]) for k in kraje], prah, chranene)
    if n_cr < prah:
        p_kraje.cele_skryte = True
    s.zaznamenej_potlaceni(p_kraje, "obor@CZ", "ostatni:T03_kraje")
    hust_kraje = {k: 1000 * obor_kraj[k] / obyv[k] for k in kraje if obyv.get(k)}
    por_pocet, por_hust = _poradi({k: obor_kraj[k] for k in kraje}), _poradi(hust_kraje)
    radky = []
    if not p_kraje.cele_skryte:
        for b in p_kraje.zverejnene:
            k = b.kod.split(":")[1]
            u = Uzemi("KRAJ", k, kraje[k]["nazev"], k)
            radky.append({"popis": kraje[k]["nazev"], "typ": "polozka", "promenna": b.kod, "hodnoty": {
                "poradi_pocet": por_pocet[k], "pocet": b.hodnota, "podil_cr": _pct(b.hodnota, n_cr),
                "lq": lq(u), "hustota": hustota(b.hodnota, k), "poradi_hustota": por_hust.get(k)}})
        if p_kraje.ostatni:
            radky.append({"popis": f"ostatní kraje ({len(p_kraje.ostatni)})", "typ": "ostatni",
                          "promenna": "ostatni:T03_kraje", "hodnoty": {
                              "pocet": p_kraje.ostatni_hodnota, "podil_cr": _pct(p_kraje.ostatni_hodnota, n_cr)}})
        radky.append({"popis": "Česko", "typ": "celkem", "promenna": "obor@CZ", "hodnoty": {
            "pocet": n_cr, "podil_cr": 100.0, "lq": 1.0, "hustota": hustota(n_cr, "CZ")}})
    sloupce_uzemi = [
        {"kod": "poradi_pocet", "nazev": "Pořadí podle počtu", "ukazatel": "PORADI_POCET"},
        {"kod": "pocet", "nazev": "Počet registrovaných subjektů", "ukazatel": "REG_POCET"},
        {"kod": "podil_cr", "nazev": "Podíl na ČR (%)", "ukazatel": "REG_PODIL_CR"},
        {"kod": "lq", "nazev": "Lokalizační koeficient", "ukazatel": "LQ"},
        {"kod": "hustota", "nazev": "Na 1 000 obyvatel", "ukazatel": "HUSTOTA"},
        {"kod": "poradi_hustota", "nazev": "Pořadí podle hustoty", "ukazatel": "PORADI_HUSTOTA"},
    ]
    t03 = {"kod": "T03_kraje", "nazev": "Pořadí krajů (všech 14)", "sloupce": sloupce_uzemi, "radky": radky,
           "zverejneno": not p_kraje.cele_skryte, "duvod": "obor v ČR pod prahem" if p_kraje.cele_skryte else None,
           "poznamky": ["Pořadí je spočteno ze skutečných počtů všech 14 krajů; kraje pod prahem jsou sloučeny "
                        "do řádku „ostatní kraje“ bez pořadí."]}

    # --- T04 okresy kraje (u kraje a okresu) -------------------------------------------
    t04 = None
    if uz.kraj_kod:
        kraj_var = f"obor@kraj:{uz.kraj_kod}"
        okresy_kraje = [k for k in okresy if okresy[k]["kraj_kod"] == uz.kraj_kod]
        nazev04 = f"Okresy kraje {kraje[uz.kraj_kod]['nazev']}"
        if len(okresy_kraje) == 1:
            s.promenna(f"obor@okres:{okresy_kraje[0]}", obor_kraj[uz.kraj_kod], s.zverejnena(kraj_var))
            s.rovnice_souctu(kraj_var, [f"obor@okres:{okresy_kraje[0]}"])
        else:
            p_okresy = potlac([Bunka(f"obor@okres:{k}", okresy[k]["nazev"], obor_okres.get(k, 0)) for k in okresy_kraje],
                              prah, {uz.promenna} if uz.typ == "OKRES" else set())
            if not s.zverejnena(kraj_var):
                p_okresy.cele_skryte = True
            s.zaznamenej_potlaceni(p_okresy, kraj_var, "ostatni:T04_okresy")
            por_o = _poradi({k: obor_okres.get(k, 0) for k in okresy_kraje})
            hust_o = {k: 1000 * obor_okres.get(k, 0) / obyv[k] for k in okresy_kraje if obyv.get(k)}
            por_oh = _poradi(hust_o)
            radky = []
            if not p_okresy.cele_skryte:
                for b in p_okresy.zverejnene:
                    k = b.kod.split(":")[1]
                    radky.append({"popis": okresy[k]["nazev"], "typ": "polozka", "promenna": b.kod, "hodnoty": {
                        "poradi_pocet": por_o[k], "pocet": b.hodnota, "podil_cr": _pct(b.hodnota, n_cr),
                        "lq": lq(Uzemi("OKRES", k, "", uz.kraj_kod)), "hustota": hustota(b.hodnota, k),
                        "poradi_hustota": por_oh.get(k)}})
                if p_okresy.ostatni:
                    radky.append({"popis": f"ostatní okresy ({len(p_okresy.ostatni)})", "typ": "ostatni",
                                  "promenna": "ostatni:T04_okresy", "hodnoty": {
                                      "pocet": p_okresy.ostatni_hodnota, "podil_cr": _pct(p_okresy.ostatni_hodnota, n_cr)}})
                radky.append({"popis": kraje[uz.kraj_kod]["nazev"], "typ": "celkem", "promenna": kraj_var,
                              "hodnoty": {"pocet": obor_kraj[uz.kraj_kod], "podil_cr": _pct(obor_kraj[uz.kraj_kod], n_cr)}})
            t04 = {"kod": "T04_okresy", "nazev": nazev04, "sloupce": sloupce_uzemi, "radky": radky,
                   "zverejneno": not p_okresy.cele_skryte,
                   "duvod": "počet v kraji pod prahem" if p_okresy.cele_skryte else None,
                   "poznamky": ["Pořadí mezi okresy téhož kraje; okresy pod prahem jsou sloučeny do „ostatní okresy“."]}

    T = uz.promenna
    n_uz = pocet_uzemi(uz)
    if uz.typ == "CR":
        pass
    elif T not in s.promenne:        # okres v kraji s jediným okresem se zapsal výše
        s.promenna(T, n_uz, False)
    uz_zverejneno = s.zverejnena(T)

    # --- populace území ----------------------------------------------------------------
    pop = [(forma, katpo, vznik) for okres, forma, katpo, vznik in d["subjekty"] if v_uzemi(okres, uz)]
    assert len(pop) == n_uz

    duvod_uz = f"počet registrovaných subjektů v území je pod prahem {prah}"
    tabulky_uzemi = []
    # T05 FO/PO
    n_fo = sum(1 for f, *_ in pop if f in FO_FORMY)
    p_fopo = potlac([Bunka("fopo:FO", "fyzické osoby (FO)", n_fo), Bunka("fopo:PO", "právnické osoby a ostatní (PO)", n_uz - n_fo)], prah)
    fopo_ok = uz_zverejneno and not p_fopo.ostatni and not p_fopo.cele_skryte
    if not uz_zverejneno:
        p_fopo.cele_skryte = True
    if fopo_ok:
        tabulky_uzemi.append(tabulka_cleneni(s, "T05_fo_po", "Registrované subjekty podle typu osoby", p_fopo, T,
                                             "FOPO_POCET", "FOPO_PODIL"))
    else:
        for b in p_fopo.zverejnene + p_fopo.ostatni:
            s.promenna(b.kod, b.hodnota, False)
        s.rovnice_souctu(T, ["fopo:FO", "fopo:PO"])
        tabulky_uzemi.append(tabulka_nezverejnena(
            "T05_fo_po", "Registrované subjekty podle typu osoby",
            duvod_uz if not uz_zverejneno else "FO nebo PO pod prahem – rozdělení se nezveřejňuje",
            [{"kod": "pocet", "nazev": "Počet registrovaných subjektů", "ukazatel": "FOPO_POCET"}]))

    # T06 právní forma (v rámci FO a PO, aby skryté nešlo dopočítat ze součtů FO/PO)
    podle_formy: dict[str, int] = {}
    for f, *_ in pop:
        podle_formy[f] = podle_formy.get(f, 0) + 1
    bunky_forem = {g: [Bunka(f"forma:{f}", f"{f} {d['formy'].get(f, '(mimo číselník)')}", n)
                       for f, n in podle_formy.items() if (f in FO_FORMY) == (g == "FO")] for g in ("FO", "PO")}
    for g in ("FO", "PO"):
        s.rovnice_souctu(f"fopo:{g}", [b.kod for b in bunky_forem[g]])
    nazev06 = "Registrované subjekty podle právní formy (číselník ČSÚ 56)"
    if not uz_zverejneno:
        for b in bunky_forem["FO"] + bunky_forem["PO"]:
            s.promenna(b.kod, b.hodnota, False)
        tabulky_uzemi.append(tabulka_nezverejnena("T06_pravni_forma", nazev06, duvod_uz, []))
    elif fopo_ok:
        radky = []
        for g, nazev_g in (("FO", "FO"), ("PO", "PO")):
            if not bunky_forem[g]:
                continue
            p = potlac(bunky_forem[g], prah)
            t = tabulka_cleneni(s, "T06_pravni_forma", nazev06, p, f"fopo:{g}", "FORMA_POCET", "FORMA_PODIL",
                                ostatni_nazev=f"ostatní formy {nazev_g}", skupina=g)
            for r in t["radky"]:
                if r["typ"] == "celkem":
                    r["popis"] = f"{nazev_g} celkem"
                    r["typ"] = "mezisoucet"
                if r["hodnoty"].get("pocet") is not None:
                    r["hodnoty"]["podil"] = _pct(r["hodnoty"]["pocet"], n_uz)
            radky += t["radky"]
        radky.append({"popis": "celkem", "typ": "celkem", "promenna": T, "hodnoty": {"pocet": n_uz, "podil": 100.0}})
        t["radky"], t["duvod"], t["zverejneno"] = radky, None, True
        t["poznamky"] = ["Formy pod prahem jsou sloučeny v rámci FO a v rámci PO; podíl je z celku území."]
        tabulky_uzemi.append(t)
    else:
        p = potlac(bunky_forem["FO"] + bunky_forem["PO"], prah)
        tabulky_uzemi.append(tabulka_cleneni(
            s, "T06_pravni_forma", nazev06, p, T, "FORMA_POCET", "FORMA_PODIL",
            poznamky=["Rozdělení FO/PO je pod prahem, formy jsou proto sloučeny přes FO i PO."]))

    # T07/T08 velikostní profil zvlášť FO a PO (rozhodnutí 2)
    for g, kod_t, uk in (("FO", "T07_velikost_fo", "VEL_FO"), ("PO", "T08_velikost_po", "VEL_PO")):
        v_skupine = [kp for f, kp, _ in pop if (f in FO_FORMY) == (g == "FO")]
        bunky = [Bunka(f"vel_{g}:{kod}", nazev, sum(1 for kp in v_skupine if kp in kody))
                 for kod, nazev, kody in PASMA_VELIKOSTI]
        nazev_t = f"Velikostní profil {g} podle počtu zaměstnanců (KATPO)"
        if not fopo_ok or not v_skupine:
            for b in bunky:
                if b.hodnota:
                    s.promenna(b.kod, b.hodnota, False)
            s.rovnice_souctu(f"fopo:{g}", [b.kod for b in bunky if b.hodnota > 0])
            duvod = (duvod_uz if not uz_zverejneno else
                     f"v území nejsou žádné {g}" if not v_skupine else "FO nebo PO pod prahem – profil se nezveřejňuje")
            tabulky_uzemi.append(tabulka_nezverejnena(
                kod_t, nazev_t, duvod,
                [{"kod": "pocet", "nazev": "Počet registrovaných subjektů", "ukazatel": f"{uk}_POCET"}]))
            continue
        p = potlac(bunky, prah)
        tabulky_uzemi.append(tabulka_cleneni(
            s, kod_t, nazev_t, p, f"fopo:{g}", f"{uk}_POCET", f"{uk}_PODIL", poradi=[b.kod for b in bunky],
            poznamky=["„Neuvedeno“ (KATPO 000) je samostatný řádek, nesčítá se s „bez zaměstnanců“. "
                      "U PO se kód 110 prakticky nepoužívá."]))

    # T09 věková struktura existujících subjektů (rozhodnutí 4)
    veky = [(datum - v).days / 365.25 for *_, v in pop if v]
    def pasmo(vek: float) -> str:
        return next(k for od, do, k, _ in PASMA_VEKU if vek >= od and (do is None or vek < do))
    bunky = [Bunka(f"vek:{k}", nazev, sum(1 for v in veky if pasmo(v) == k)) for _, _, k, nazev in PASMA_VEKU]
    if len(veky) != n_uz:
        raise AssertionError("existující subjekt bez data vzniku")
    p = potlac(bunky, prah)
    if not uz_zverejneno:
        p.cele_skryte = True
    tabulky_uzemi.append(tabulka_cleneni(
        s, "T09_vekova_struktura", "Věková struktura existujících subjektů", p, T, "VEK_PASMO_POCET", "VEK_PASMO_PODIL",
        poradi=[b.kod for b in bunky], poznamky=["Věk = datum snímku − datum vzniku. Jde o strukturu dnes existujících subjektů, ne o počet vzniků "
                  "v jednotlivých letech (zaniklé subjekty nejsou zahrnuty)."]))

    # T10 zániky PO z RES od 2023
    zaniky = {}
    for okres, rok in d["zaniky_po"]:
        if v_uzemi(okres, uz):
            zaniky[rok] = zaniky.get(rok, 0) + 1
    bunky = [Bunka(f"zanik_po:{r}", str(r) + (" (do data snímku)" if r == datum.year else ""), zaniky.get(r, 0))
             for r in range(ZANIKY_OD_ROKU, datum.year + 1)]
    p = potlac(bunky, prah)
    t10 = tabulka_cleneni(s, "T10_zaniky_po", f"Zaniklé právnické osoby v oboru a území podle roku zániku (RES, od {ZANIKY_OD_ROKU})",
                          p, "zanik_po@uzemi", "ZANIK_PO_RES", "ZANIK_PO_RES", ostatni_nazev="ostatní roky",
                          poradi=[b.kod for b in bunky],
                          poznamky=["Jen PO: zaniklé FO mají v otevřených datech jen IČO a datum zániku (GDPR). "
                                    "Zaniklé subjekty jsou v RES jen 4 roky po zániku."])
    t10["sloupce"] = [{"kod": "pocet", "nazev": "Počet zaniklých PO", "ukazatel": "ZANIK_PO_RES"}]
    for r in t10["radky"]:
        r["hodnoty"].pop("podil", None)

    # T11 dynamika území podle ČSÚ (RES05) – všechny obory
    t11_radky = []
    roky = sorted({o[:4] for _, o, _, _ in dynamika})
    for rok in roky:
        ctvrtleti = sorted({o for _, o, _, _ in dynamika if o.startswith(rok)})
        for uk, uk_kod, uk_nazev in (("4962", "DYN_VZNIK_CSU", "vzniklé"), ("4963", "DYN_ZANIK_CSU", "zaniklé")):
            hodn = {f: int(sum(h for fk, o, u, h in dynamika if fk == f and u == uk and o.startswith(rok)))
                    for f in ("0", "10", "30")}
            pref = f"dyn:{rok}:{uk}"
            if hodn["0"] != hodn["10"] + hodn["30"]:
                raise AssertionError(f"RES05 {rok}/{uk}: celkem ≠ FO + PO")
            p = potlac([Bunka(f"{pref}:FO", "FO", hodn["10"]), Bunka(f"{pref}:PO", "PO", hodn["30"])], prah)
            s.promenna(f"{pref}:celkem", hodn["0"], hodn["0"] >= prah)
            s.zaznamenej_potlaceni(p, f"{pref}:celkem", None)
            hodnoty = {"fo": None, "po": None, "celkem": hodn["0"] if hodn["0"] >= prah else None}
            if not p.ostatni and not p.cele_skryte:
                hodnoty["fo"], hodnoty["po"] = hodn["10"], hodn["30"]
            poz = f"{len(ctvrtleti)} čtvrtletí" if len(ctvrtleti) < 4 else ""
            if rok == "2023" and uk == "4963":
                poz = (poz + "; " if poz else "") + "mimořádný výkyv: hromadný zánik FO v 1. čtvrtletí 2023"
            t11_radky.append({"popis": f"{rok} – {uk_nazev}", "typ": "polozka", "promenna": f"{pref}:celkem",
                              "ukazatele": {k: uk_kod for k in ("fo", "po", "celkem")},
                              "hodnoty": hodnoty, "poznamka": poz or None})
    t11 = {"kod": "T11_dynamika_csu", "nazev": f"Vznik a zánik ekonomických subjektů v území – všechny obory (ČSÚ, RES05)",
           "sloupce": [{"kod": "fo", "nazev": "FO", "ukazatel": "DYN_VZNIK_CSU"},
                       {"kod": "po", "nazev": "PO", "ukazatel": "DYN_VZNIK_CSU"},
                       {"kod": "celkem", "nazev": "Celkem", "ukazatel": "DYN_VZNIK_CSU"}],
           "radky": t11_radky, "zverejneno": bool(t11_radky), "duvod": None if t11_radky else "ČSÚ údaje nepublikuje",
           "poznamky": ["ČSÚ nepublikuje vznik a zánik v členění podle oboru (kraj × sekce); jde o celé území. "
                        "Čísla FO a PO pod prahem se nezveřejňují (zůstává jen celkem)."]}

    # --- doplňky (rozhodnutí 6) a T01 ---------------------------------------------------
    dopl: dict[str, int] = {}
    for nace, okres, n in d["doplnky"]:
        if v_uzemi(okres, uz):
            dopl[nace] = dopl.get(nace, 0) + n

    def radek(ukazatel: str, popis: str, hodnota, promenna: str | None = None, zaklad: str | None = None,
              poznamka: str | None = None) -> dict:
        r = {"popis": popis, "typ": "ukazatel", "ukazatele": {"hodnota": ukazatel}, "hodnoty": {"hodnota": hodnota}}
        if promenna:
            r["promenna"] = promenna
        if zaklad:
            r["zaklad"] = zaklad
        if poznamka:
            r["poznamka"] = poznamka
        return r

    pod_prahem = f"méně než {prah} – nezveřejňuje se"
    t01 = []
    zv = uz_zverejneno
    t01.append(radek("REG_POCET", f"Registrované subjekty v oboru – {uz.nazev}", n_uz if zv else None, T,
                     poznamka=None if zv else pod_prahem))
    t01.append(radek("REG_POCET_CR", "Registrované subjekty v oboru – Česko", n_cr if s.zverejnena("obor@CZ") else None, "obor@CZ"))
    if uz.typ != "CR":
        t01.append(radek("REG_PODIL_CR", "Podíl území na oboru v ČR (%)", _pct(n_uz, n_cr, 2) if zv else None, zaklad=T))
    s.promenna(f"vse@{uz.kod}", vse_uzemi(uz), vse_uzemi(uz) >= prah)
    t01.append(radek("REG_POCET_VSE", "Všechny registrované subjekty v území", vse_uzemi(uz) if vse_uzemi(uz) >= prah else None,
                     f"vse@{uz.kod}"))
    t01.append(radek("REG_PODIL_OBOR", "Podíl oboru na registrovaných subjektech území (%)",
                     _pct(n_uz, vse_uzemi(uz), 2) if zv else None, zaklad=T))
    if uz.typ != "CR":
        t01.append(radek("LQ", "Lokalizační koeficient", lq(uz) if zv else None, zaklad=T))
    t01.append(radek("OBYVATELE", f"Počet obyvatel k 31. 12. {d['rok_obyvatel']}", int(obyv[uz.kod]) if obyv.get(uz.kod) else None))
    t01.append(radek("HUSTOTA", "Registrované subjekty oboru na 1 000 obyvatel", hustota(n_uz, uz.kod) if zv else None, zaklad=T))
    if uz.typ == "KRAJ":
        t01.append(radek("PORADI_POCET", "Pořadí kraje mezi 14 kraji podle počtu", por_pocet[uz.kod] if zv else None, zaklad=T))
        t01.append(radek("PORADI_HUSTOTA", "Pořadí kraje mezi 14 kraji podle hustoty", por_hust.get(uz.kod) if zv else None, zaklad=T))
    if uz.typ == "OKRES":
        okresy_kraje = [k for k in okresy if okresy[k]["kraj_kod"] == uz.kraj_kod]
        por_o = _poradi({k: obor_okres.get(k, 0) for k in okresy_kraje})
        t01.append(radek("PORADI_POCET", f"Pořadí okresu mezi {len(okresy_kraje)} okresy kraje podle počtu",
                         por_o[uz.kod] if zv else None, zaklad=T))
        kraj_zv = s.zverejnena(f"obor@kraj:{uz.kraj_kod}")
        t01.append(radek("PORADI_POCET", f"Pořadí kraje ({kraje[uz.kraj_kod]['nazev']}) mezi 14 kraji podle počtu",
                         por_pocet[uz.kraj_kod] if kraj_zv else None, zaklad=f"obor@kraj:{uz.kraj_kod}"))
    if zv:
        t01.append(radek("VEK_PRUMER", "Průměrný věk existujících subjektů (roky)", round(statistics.fmean(veky), 1), zaklad=T))
        t01.append(radek("VEK_MEDIAN", "Mediánový věk existujících subjektů (roky)", round(statistics.median(veky), 1), zaklad=T))
    else:
        t01.append(radek("VEK_PRUMER", "Průměrný věk existujících subjektů (roky)", None, zaklad=T))
        t01.append(radek("VEK_MEDIAN", "Mediánový věk existujících subjektů (roky)", None, zaklad=T))
    for predek in sorted({p for o in obor for p in o["predci"]}):
        n = dopl.get(predek, 0)
        uroven = {1: "sekce", 2: "oddílu", 3: "skupiny"}.get(len(predek) if predek.isdigit() else 1, "sekce")
        var = f"dopl:jen:{predek}"
        s.promenna(var, n, n >= prah)
        t01.append(radek("DOPL_JEN_VYSSI", f"Zařazeno jen do {uroven} {predek} ({d['nazvy_predku'].get(predek, '')})",
                         n if n >= prah else None, var, poznamka=None if n >= prah else (pod_prahem if n else "žádné")))
    n00 = dopl.get("00", 0)
    s.promenna("dopl:00", n00, n00 >= prah)
    t01.append(radek("DOPL_OBOR_NEURCEN", "Obor neurčen (pseudokód 00) – v území, všechny obory", n00 if n00 >= prah else None,
                     "dopl:00", poznamka=None if n00 >= prah else pod_prahem))
    # rozhodnutí 9: spolehlivost zařazení – „jen do sekce“ (v téže sekci a území) vůči počtu oboru
    varovani = []
    sekce_jen = sorted({o["sekce"] for o in obor if o["uroven"] > 1})
    spolehlivost = None
    if sekce_jen:
        vary = [f"dopl:jen:{sk}" for sk in sekce_jen]
        jen_sekce = sum(s.promenne[v]["hodnota"] for v in vary)
        if zv and all(s.zverejnena(v) or s.promenne[v]["hodnota"] == 0 for v in vary):
            spolehlivost = _pct(jen_sekce, n_uz)
        t01.append(radek("SPOLEHLIVOST_JEN_SEKCE",
                         f"Zařazeno jen do sekce {', '.join(sekce_jen)} vůči počtu oboru (%)", spolehlivost,
                         zaklad=T, poznamka=None if spolehlivost is not None else pod_prahem))
        if spolehlivost is not None and spolehlivost > PRAH_SPOLEHLIVOSTI:
            varovani.append(
                f"Nízká spolehlivost zařazení: subjektů zařazených jen do sekce {', '.join(sekce_jen)} je v území "
                f"{_fmt_cz(spolehlivost)} % počtu oboru (práh {_fmt_cz(PRAH_SPOLEHLIVOSTI)} %). Skutečný počet "
                f"subjektů v oboru může být výrazně vyšší.")
    kraj_akt = uz.kraj_kod or "CZ"
    a = d["aktivita"].get((kraj_akt, "0"), {})
    t01.append(radek("AKTIVNI_PODIL_KRAJ",
                     f"Podíl subjektů se zjištěnou aktivitou – {kraje[kraj_akt]['nazev'] if kraj_akt != 'CZ' else 'Česko'}, "
                     f"všechny obory (ČSÚ, {d['obdobi_aktivity']}, %)",
                     _pct(a["4958_akt"], a["4958_reg"]) if a.get("4958_reg") else None,
                     poznamka="kontext: počty v reportu jsou registrované subjekty"))
    if len(obor) == 1 and obor[0]["uroven"] == 1 and obor[0]["kod"] not in ("B", "C", "D", "E"):
        a = d["aktivita"].get((kraj_akt, obor[0]["kod"]), {})
        t01.append(radek("AKTIVNI_PODIL_SEKCE_KRAJ", f"Podíl subjektů se zjištěnou aktivitou – {kraje[kraj_akt]['nazev'] if kraj_akt != 'CZ' else 'Česko'}, "
                         f"sekce {obor[0]['kod']} (ČSÚ, {d['obdobi_aktivity']}, %)",
                         _pct(a["4958_akt"], a["4958_reg"]) if a.get("4958_reg") else None))

    # --- T02 srovnání ------------------------------------------------------------------
    srovnavana = [Uzemi("CR", "CZ", "Česko", None)]
    if uz.typ == "OKRES":
        srovnavana.append(Uzemi("KRAJ", uz.kraj_kod, kraje[uz.kraj_kod]["nazev"], uz.kraj_kod))
    if uz.typ != "CR":
        srovnavana.append(uz)
    srovnavana += [k for k in srovnani if k.kod not in {x.kod for x in srovnavana}]
    t02_radky = []
    for u in srovnavana:
        var = u.promenna
        zv_u = s.zverejnena(var)
        n = pocet_uzemi(u)
        akt = d["aktivita"].get((u.kraj_kod or "CZ", "0"), {})
        t02_radky.append({"popis": u.nazev + (" (zkoumané území)" if u.kod == uz.kod else ""), "typ": "polozka",
                          "promenna": var, "hodnoty": {
                              "pocet": n if zv_u else None, "vse": vse_uzemi(u),
                              "podil_obor": _pct(n, vse_uzemi(u), 2) if zv_u else None,
                              "podil_cr": _pct(n, n_cr, 2) if zv_u else None,
                              "lq": (lq(u) if u.typ != "CR" else 1.0) if zv_u else None,
                              "obyvatele": int(obyv[u.kod]) if obyv.get(u.kod) else None,
                              "hustota": hustota(n, u.kod) if zv_u else None,
                              "aktivni_kraj": _pct(akt["4958_akt"], akt["4958_reg"]) if akt.get("4958_reg") and u.typ != "OKRES" else None},
                          "poznamka": None if zv_u else pod_prahem})
    t02 = {"kod": "T02_srovnani", "nazev": "Srovnání s ČR a se zadanými kraji",
           "sloupce": [{"kod": "pocet", "nazev": "Počet registrovaných subjektů v oboru", "ukazatel": "REG_POCET"},
                       {"kod": "vse", "nazev": "Všechny registrované subjekty", "ukazatel": "REG_POCET_VSE"},
                       {"kod": "podil_obor", "nazev": "Podíl oboru (%)", "ukazatel": "REG_PODIL_OBOR"},
                       {"kod": "podil_cr", "nazev": "Podíl na ČR (%)", "ukazatel": "REG_PODIL_CR"},
                       {"kod": "lq", "nazev": "Lokalizační koeficient", "ukazatel": "LQ"},
                       {"kod": "obyvatele", "nazev": "Obyvatelé", "ukazatel": "OBYVATELE"},
                       {"kod": "hustota", "nazev": "Na 1 000 obyvatel", "ukazatel": "HUSTOTA"},
                       {"kod": "aktivni_kraj", "nazev": "Kraj: podíl se zjištěnou aktivitou, ČSÚ (%)", "ukazatel": "AKTIVNI_PODIL_KRAJ"}],
           "radky": t02_radky, "zverejneno": True, "duvod": None,
           "poznamky": ["Srovnávací kraje zadal uživatel; automaticky se srovnává jen s ČR." if srovnani else
                        "Srovnávací kraje nebyly zadány; automaticky se srovnává jen s ČR a pořadím krajů (T03)."]}
    for u, r in zip(srovnavana, t02_radky):
        s.promenna(f"vse@{u.kod}", r["hodnoty"]["vse"], r["hodnoty"]["vse"] >= prah)

    t01_tab = {"kod": "T01_zakladni", "nazev": "Základní ukazatele",
               "sloupce": [{"kod": "hodnota", "nazev": "Hodnota", "ukazatel": None}],
               "radky": t01, "zverejneno": True, "duvod": None,
               "poznamky": ["Počty jsou registrované subjekty bez data zániku. Podíl subjektů se zjištěnou "
                            "aktivitou je jen kontext z publikace ČSÚ, na subjekty oboru se nepřepočítává."]}

    # --- T12 demografie podniků ČR (RESDP00) – kontext, jiná jednotka (rozhodnutí 10) ------
    t12_radky = []
    odvetvi = {kod: nazev for kod, nazev, *_ in demografie}
    kod_oboru = next((k for k in odvetvi if k != DEMOGRAFIE_CELKEM), None)
    uplne_roky = sorted({r for _, _, _, r, u, _, _ in demografie if u == "9506"})[-5:]
    for rok in uplne_roky:
        for fk, fn in (("10", "podniky FO"), ("30", "podniky PO")):
            def h(odv, uk):
                return next((float(x[5]) for x in demografie if x[0] == odv and x[2] == fk and x[3] == rok and x[4] == uk), None)
            hodnoty = {}
            for pref, odv in (("obor", kod_oboru), ("cr", DEMOGRAFIE_CELKEM)):
                if odv is None:
                    continue
                aktivni = h(odv, "6594_RESDP")
                hodnoty[f"{pref}_aktivni"] = int(aktivni) if aktivni is not None and aktivni >= prah else None
                # míry ČSÚ ukládá s 9 desetinnými místy; report je vede na 2 místa (stejně v JSON, XLSX i PDF)
                mv, mz = h(odv, "9507"), h(odv, "9508")
                hodnoty[f"{pref}_mira_vzniku"] = round(mv, 2) if mv is not None else None
                hodnoty[f"{pref}_mira_zaniku"] = round(mz, 2) if mz is not None else None
            predb = any(x[6] for x in demografie if x[3] == rok)
            t12_radky.append({"popis": f"{rok} – {fn}", "typ": "polozka", "hodnoty": hodnoty,
                              "poznamka": "předběžné hodnoty" if predb else None})
    sl12 = []
    if kod_oboru:
        sl12 += [{"kod": "obor_aktivni", "nazev": f"{odvetvi[kod_oboru]}: aktivní podniky", "ukazatel": "DEMOGR_AKTIVNI"},
                 {"kod": "obor_mira_vzniku", "nazev": f"{odvetvi[kod_oboru]}: míra vzniků (%)", "ukazatel": "DEMOGR_MIRA_VZNIKU"},
                 {"kod": "obor_mira_zaniku", "nazev": f"{odvetvi[kod_oboru]}: míra zániků (%)", "ukazatel": "DEMOGR_MIRA_ZANIKU"}]
    sl12 += [{"kod": "cr_aktivni", "nazev": "Všechna odvětví: aktivní podniky", "ukazatel": "DEMOGR_AKTIVNI"},
             {"kod": "cr_mira_vzniku", "nazev": "Všechna odvětví: míra vzniků (%)", "ukazatel": "DEMOGR_MIRA_VZNIKU"},
             {"kod": "cr_mira_zaniku", "nazev": "Všechna odvětví: míra zániků (%)", "ukazatel": "DEMOGR_MIRA_ZANIKU"}]
    t12 = {"kod": "T12_demografie_cr", "nazev": "Demografie podniků v ČR – kontext (ČSÚ, RESDP00; jednotka podnik)",
           "sloupce": sl12, "radky": t12_radky, "zverejneno": bool(t12_radky),
           "duvod": None if t12_radky else "ČSÚ údaje nepublikuje",
           "poznamky": ["Jiná jednotka: aktivní PODNIK ze statistiky demografie podniků, ne registrovaný ekonomický "
                        "subjekt z RES; čísla nejsou srovnatelná s ostatními tabulkami. Jen za ČR."
                        + ("" if kod_oboru else " Obor nemá v RESDP00 samostatné odvětví; uvádí se jen celek.")
                        + (" Odvětví RESDP00 je širší nebo užší než sekce oboru." if kod_oboru and kod_oboru not in "BCDEFGHIJLMNPQR" else "")]}

    tabulky = [t01_tab, t02, t03] + ([t04] if t04 else []) + tabulky_uzemi + [t10, t11, t12]
    for t in tabulky:
        for r in t["radky"]:
            for sl in t["sloupce"]:
                uk = r.get("ukazatele", {}).get(sl["kod"]) or sl["ukazatel"]
                if uk and uk not in katalog:
                    raise AssertionError(f"ukazatel {uk} není v katalogu")

    dopocet = s.kontrola_dopoctu()
    if dopocet:
        raise AssertionError(f"skrytá čísla jdou dopočítat: {dopocet}")

    meta = {
        "zadani": {"obor": [o["kod"] for o in obor], "uzemi": uz.kod, "datum_snimku": datum.isoformat(),
                   "srovnani": [k.kod for k in srovnani], "prah": prah},
        "pravidla": {"prah": prah, "min_rozsah": zadani.min_rozsah, "prah_spolehlivosti_pct": PRAH_SPOLEHLIVOSTI},
        "varovani": varovani,
        "obor": [{"kod": o["kod"], "nazev": o["nazev"], "uroven": o["uroven"]} for o in obor],
        "obor_popis": popis_oboru(obor),
        "klasifikace": "CZ-NACE Rev. 2 (klasifikace ČSÚ 80004, sloupec NACE)",
        "uzemi": {"typ": uz.typ, "kod": uz.kod, "nazev": uz.nazev, "kraj": uz.kraj_kod},
        "populace": "registrované ekonomické subjekty bez data zániku (sídlo v území, převažující činnost v oboru)",
        "citace": citace(datum),
        "oznaceni": OZNACENI,
        "dalsi_zdroje": [
            f"ČSÚ, DataStat, sada OBY02A – počet obyvatel k 31. 12. {d['rok_obyvatel']}",
            f"ČSÚ, DataStat, výběr RES02QT1 – podíl subjektů se zjištěnou aktivitou, {d['obdobi_aktivity']}",
            "ČSÚ, DataStat, sada RES05 – vznik a zánik ekonomických subjektů",
            "ČSÚ, DataStat, sada RESDP00 – demografie podniků (jednotka podnik, jen ČR)",
        ],
        "licence": {"nazev": "CC BY 4.0", "url": LICENCE_URL},
        "vygenerovano": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    pouzite = {r.get("ukazatele", {}).get(sl["kod"]) or sl["ukazatel"] for t in tabulky for r in t["radky"] for sl in t["sloupce"]}
    meta["ukazatele"] = [{k: u.get(k) for k in ("kod", "nazev", "typ", "definice", "chybejici_hodnoty", "vyklad")}
                         for kod, u in katalog.items() if kod in pouzite]
    vysledek = {"meta": meta, "tabulky": tabulky}
    interni = {"promenne": s.promenne, "rovnice": s.rovnice, "prah": prah}
    return vysledek, interni


# ---------------------------------------------------------------------------
# Výstupy
# ---------------------------------------------------------------------------

def _fmt_cz(v: float) -> str:
    return f"{v:.1f}".replace(".", ",") if v != int(v) else str(int(v))


def _fmt(v) -> str:
    if v is None:
        return "–"
    if isinstance(v, float):
        return f"{v:,.2f}".replace(",", " ").replace(".", ",").rstrip("0").rstrip(",")
    if isinstance(v, int):
        return f"{v:,}".replace(",", " ")
    return str(v)


def markdown(vysledek: dict) -> str:
    m = vysledek["meta"]
    out = [f"# {m['obor_popis']} × {m['uzemi']['nazev']}", "",
           f"Stav k {m['zadani']['datum_snimku']}. Populace: {m['populace']}. Klasifikace: {m['klasifikace']}. "
           f"Práh zveřejnění: {m['zadani']['prah']} subjektů.", "", f"*{m['citace']}* **{m['oznaceni']}**", ""]
    for t in vysledek["tabulky"]:
        out += [f"## {t['kod']}: {t['nazev']}", ""]
        if not t["zverejneno"]:
            out += [f"_Nezveřejněno: {t['duvod']}._", ""]
            continue
        hlav = ["Položka"] + [s["nazev"] for s in t["sloupce"]] + ["Poznámka"]
        out += ["| " + " | ".join(hlav) + " |", "|" + "---|" * len(hlav)]
        for r in t["radky"]:
            popis = f"**{r['popis']}**" if r["typ"] in ("celkem", "mezisoucet") else r["popis"]
            out.append("| " + " | ".join([popis] + [_fmt(r["hodnoty"].get(s["kod"])) for s in t["sloupce"]]
                                         + [r.get("poznamka") or ""]) + " |")
        out += [""] + [f"> {p}" for p in t["poznamky"]] + [""]
    return "\n".join(out)


def slug(vysledek: dict) -> str:
    z = vysledek["meta"]["zadani"]
    return f"{'-'.join(z['obor'])}__{z['uzemi']}__{z['datum_snimku']}"


def uloz(vysledek: dict, interni: dict, adresar: Path) -> Path:
    from firemni_databaze.report_xlsx import zapis_xlsx

    cil = adresar / slug(vysledek)
    (cil / "_interni").mkdir(parents=True, exist_ok=True)
    (cil / "vysledek.json").write_text(json.dumps(vysledek, ensure_ascii=False, indent=1), encoding="utf-8")
    (cil / "vysledek.md").write_text(markdown(vysledek), encoding="utf-8")
    (cil / "_interni" / "kontrola.json").write_text(json.dumps(interni, ensure_ascii=False, indent=1), encoding="utf-8")
    zapis_xlsx(vysledek, cil / "priloha.xlsx", KATALOG)
    return cil


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--obor", required=True, help="kódy CZ-NACE Rev. 2 oddělené čárkou (např. F nebo 10 nebo 41,42)")
    parser.add_argument("--uzemi", required=True, help="CZ, kraj (CZ051 / název) nebo okres (CZ0513 / název)")
    parser.add_argument("--datum", type=date.fromisoformat, help="datum snímku RES (výchozí poslední)")
    parser.add_argument("--srovnani", default="", help="srovnávací kraje oddělené čárkou (zadává člověk)")
    parser.add_argument("--prah", type=int, default=PRAH)
    parser.add_argument("--min-rozsah", type=int, default=MIN_ROZSAH, help="rozhodnutí 8 (výchozí 100)")
    parser.add_argument("--vystup", type=Path, default=VYSTUPY)
    parser.add_argument("--pdf", action="store_true", help="po výpočtu rovnou vysázet PDF (report_pdf)")
    args = parser.parse_args()
    zadani = Zadani([k for k in args.obor.split(",") if k.strip()], args.uzemi, args.datum,
                    [k for k in args.srovnani.split(",") if k.strip()], args.prah, args.min_rozsah)
    conn = get_engine().raw_connection()
    try:
        vysledek, interni = spocitej(conn, zadani)
    except MalyRozsah as exc:
        print(exc.vypis())
        return 4
    finally:
        conn.close()
    cil = uloz(vysledek, interni, args.vystup)
    print(markdown(vysledek))
    print(f"\nUloženo do {cil}")
    if args.pdf:
        from firemni_databaze.report_pdf import ChybaSazby, vysazej
        try:
            print(f"PDF: {vysazej(cil, cil)}")
        except ChybaSazby as exc:
            print(f"SAZBA ZASTAVENA: {exc}")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
