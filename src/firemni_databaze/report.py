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
        "SELECT s.okreslau, s.ddatvzn, s.ddatzan FROM res.subjekt s "
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


MZDY_ROKY = 5               # počet posledních let v tabulkách zaměstnanosti a mezd


def nacti_mzdy(cur, sekce: str | None) -> dict:
    """Zaměstnanci a mzdy ČSÚ (res.csu_mzdy): {(výběr, území, NACE, rok, ukazatel): (hodnota, předběžná)}."""
    cur.execute("SELECT to_regclass('res.csu_mzdy')")
    if cur.fetchone()[0] is None:
        return {}
    cur.execute("SELECT vyber, uzemi_kod, nace_kod, rok, ukazatel_kod, hodnota, predbezna FROM res.csu_mzdy "
                "WHERE nace_kod = ANY(%s) AND ukazatel_kod IN ('ZAM_PREP', 'MZDA_PREP')",
                (["0"] + ([sekce] if sekce else []),))
    return {(v, u, n, r, k): (float(h), p) for v, u, n, r, k, h, p in cur.fetchall()}


def tabulky_mzdy(uz: "Uzemi", srovnani: list["Uzemi"], obor: list[dict], kraje: dict, mzdy: dict) -> list[dict]:
    """T20 obor × kraj (roční zjišťování MZDCRR) a T21 nejbližší publikované úrovně pro novější roky (MZDR).

    Jen publikovaná čísla ČSÚ a poměry mezi nimi; nic se nedopočítává z jiných úrovní. Zaměstnanci
    v tis. osob (přepočtené počty) na 1 desetinné místo, mzda v Kč na celé koruny (jako ČSÚ publikuje)."""
    sekce = {o["sekce"] for o in obor}
    sl20 = [{"kod": "zam", "nazev": "Zaměstnanci v oboru (tis., přepočtené)", "ukazatel": "MZDY_ZAM_OBOR"},
            {"kod": "zam_podil_cr", "nazev": "Podíl na zaměstnancích oboru v ČR (%)", "ukazatel": "MZDY_ZAM_PODIL_CR"},
            {"kod": "zam_podil_uzemi", "nazev": "Podíl oboru na zaměstnancích území (%)", "ukazatel": "MZDY_ZAM_PODIL_UZEMI"},
            {"kod": "mzda", "nazev": "Průměrná mzda v oboru (Kč)", "ukazatel": "MZDY_MZDA_OBOR"},
            {"kod": "mzda_index_cr", "nazev": "Mzda proti oboru v ČR (ČR = 100)", "ukazatel": "MZDY_MZDA_INDEX_CR"},
            {"kod": "mzda_index_uzemi", "nazev": "Mzda proti všem odvětvím území (= 100)", "ukazatel": "MZDY_MZDA_INDEX_UZEMI"}]
    sl21 = [{"kod": "zam", "nazev": "Zaměstnanci (tis., přepočtené)", "ukazatel": "MZDY_ZAM_UROVEN"},
            {"kod": "mzda", "nazev": "Průměrná mzda (Kč)", "ukazatel": "MZDY_MZDA_UROVEN"}]
    nazev20 = "Zaměstnanci a průměrné mzdy v oboru – kraje a ČR (ČSÚ, roční zjišťování)"
    nazev21 = "Zaměstnanci a průměrné mzdy – novější roky v nejbližších publikovaných úrovních (ČSÚ, čtvrtletní zjišťování)"
    if len(sekce) != 1 or not mzdy:
        duvod = ("ČSÚ publikuje zaměstnance a mzdy jen po jednotlivých sekcích CZ-NACE; obor zasahuje do více sekcí"
                 if mzdy else "údaje ČSÚ o zaměstnancích a mzdách nejsou načtené (res_import mzdy)")
        return [tabulka_nezverejnena("T20_mzdy_obor", nazev20, duvod, sl20),
                tabulka_nezverejnena("T21_mzdy_aktualni", nazev21, duvod, sl21)]
    s = next(iter(sekce))
    jen_sekce = any(o["uroven"] > 1 for o in obor)
    kraj_uz = uz.kraj_kod                                   # u okresu jeho kraj (okresy ČSÚ nepublikuje)
    uzemi = ([("CZ", "Česko")] if uz.typ == "CR" else
             [(kraj_uz, kraje[kraj_uz]["nazev"]), ("CZ", "Česko")]
             + [(k.kod, k.nazev) for k in srovnani if k.kod != kraj_uz])

    def h(vyber, u, n, rok, uk):
        x = mzdy.get((vyber, u, n, rok, uk))
        return x[0] if x else None

    def predb(vyber, u, n, rok):
        return any(mzdy.get((vyber, u, n, rok, uk), (0, False))[1] for uk in ("ZAM_PREP", "MZDA_PREP"))

    # --- T20: obor × kraj, roční zjišťování (MZDCRRT2 kraje, MZDCRRT1 ČR) ---------------------
    roky20 = sorted({k[3] for k in mzdy if k[0] in ("MZDCRRT1", "MZDCRRT2") and k[2] == s})[-MZDY_ROKY:]
    radky20 = []
    for kod, nazev in uzemi:
        vyber = "MZDCRRT1" if kod == "CZ" else "MZDCRRT2"
        for rok in roky20:
            zam, zam_all = h(vyber, kod, s, rok, "ZAM_PREP"), h(vyber, kod, "0", rok, "ZAM_PREP")
            mzda, mzda_all = h(vyber, kod, s, rok, "MZDA_PREP"), h(vyber, kod, "0", rok, "MZDA_PREP")
            zam_cr, mzda_cr = h("MZDCRRT1", "CZ", s, rok, "ZAM_PREP"), h("MZDCRRT1", "CZ", s, rok, "MZDA_PREP")
            hod = {"zam": round(zam, 1) if zam is not None else None,
                   "zam_podil_cr": round(100 * zam / zam_cr, 2) if zam and zam_cr and kod != "CZ" else None,
                   "zam_podil_uzemi": round(100 * zam / zam_all, 2) if zam and zam_all else None,
                   "mzda": round(mzda) if mzda is not None else None,
                   "mzda_index_cr": round(100 * mzda / mzda_cr, 1) if mzda and mzda_cr and kod != "CZ" else None,
                   "mzda_index_uzemi": round(100 * mzda / mzda_all, 1) if mzda and mzda_all else None}
            radky20.append({"popis": f"{nazev} – {rok}", "typ": "polozka", "uzemi": kod, "rok": rok, "hodnoty": hod,
                            "poznamka": "předběžné hodnoty" if predb(vyber, kod, s, rok) else None})
    pozn20 = [f"Zdroj: ČSÚ, DataStat, výběry MZDCRRT2 (kraje × sekce CZ-NACE) a MZDCRRT1 (ČR × sekce) – roční "
              f"zjišťování, pracovištní metoda (kraj podle místa pracoviště). ČSÚ je publikuje za roky "
              f"{min(k[3] for k in mzdy if k[0] == 'MZDCRRT2')}–{max(k[3] for k in mzdy if k[0] == 'MZDCRRT2')}.",
              "Zaměstnanci = průměrný evidenční počet zaměstnanců přepočtený na plný úvazek; mzda = průměrná hrubá "
              "měsíční mzda na přepočtené počty. Nezahrnuje podnikající fyzické osoby bez pracovního poměru, "
              "proto se nesrovnává s počty registrovaných subjektů.",
              "Průměr, ne medián: medián mezd ČSÚ za kraje publikuje jen podle pohlaví a bez členění podle odvětví."]
    if jen_sekce:
        pozn20.insert(0, f"Nejbližší publikovaná úroveň: sekce {s} – ČSÚ zaměstnance a mzdy podle oddílů a "
                         f"nižších úrovní CZ-NACE nepublikuje.")
    if uz.typ == "OKRES":
        pozn20.insert(0, f"Nejbližší publikovaná úroveň: kraj {kraje[kraj_uz]['nazev']} – ČSÚ zaměstnance a mzdy "
                         f"za okresy nepublikuje.")
    t20 = {"kod": "T20_mzdy_obor", "nazev": nazev20 + (f" – sekce {s}" if jen_sekce else ""), "sloupce": sl20,
           "radky": radky20, "zverejneno": bool(radky20), "duvod": None if radky20 else "ČSÚ údaje nepublikuje",
           "poznamky": pozn20, "sekce": s}

    # --- T21: novější roky – kraj všechna odvětví, ČR obor (MZDRT5, MZDRT2) ------------------
    posl20 = roky20[-1] if roky20 else 0
    roky21 = sorted({k[3] for k in mzdy if k[0] in ("MZDRT5", "MZDRT2") and k[3] > posl20})
    radky21 = []
    urovne = [(f"{nazev} – všechna odvětví", "MZDRT5", kod, "0") for kod, nazev in uzemi if kod != "CZ"]
    urovne += [("Česko – všechna odvětví", "MZDRT5", "CZ", "0"), (f"Česko – sekce {s}", "MZDRT2", "CZ", s)]
    for popis, vyber, kod, n in urovne:
        for rok in roky21:
            zam, mzda = h(vyber, kod, n, rok, "ZAM_PREP"), h(vyber, kod, n, rok, "MZDA_PREP")
            radky21.append({"popis": f"{popis} – {rok}", "typ": "polozka", "uzemi": kod, "nace": n, "rok": rok,
                            "hodnoty": {"zam": round(zam, 1) if zam is not None else None,
                                        "mzda": round(mzda) if mzda is not None else None},
                            "poznamka": "předběžné hodnoty" if predb(vyber, kod, n, rok) else None})
    t21 = {"kod": "T21_mzdy_aktualni", "nazev": nazev21, "sloupce": sl21, "radky": radky21,
           "zverejneno": bool(radky21), "duvod": None if radky21 else "novější roky ČSÚ zatím nepublikuje",
           "poznamky": [f"Obor × kraj ČSÚ za roky po {posl20} nepublikuje: roční zjišťování podle krajů a sekcí "
                        f"končí rokem {posl20} a čtvrtletní zjišťování kombinaci kraj × odvětví nepublikuje. "
                        f"Uvádějí se proto nejbližší publikované úrovně: kraje za všechna odvětví a ČR za sekci {s}.",
                        "Zdroj: ČSÚ, DataStat, výběry MZDRT5 (ČR a kraje, pracovištní metoda) a MZDRT2 (ČR × sekce) "
                        "– čtvrtletní zjišťování, kumulace za rok. Hodnoty se od ročního zjišťování mírně liší; "
                        "obě řady se nespojují."]}
    return [t20, t21]


# skupiny A*10 regionálních účtů Eurostatu: sekce CZ-NACE → (kód skupiny, název)
SKUPINY_A10 = {
    "A": ("A", "Zemědělství, lesnictví a rybářství (A)"),
    **{s: ("B-E", "Průmysl kromě stavebnictví (B–E)") for s in "BDE"},
    "C": ("C", "Zpracovatelský průmysl (C)"),
    "F": ("F", "Stavebnictví (F)"),
    **{s: ("G-I", "Obchod, doprava, ubytování a stravování (G–I)") for s in "GHI"},
    "J": ("J", "Informační a komunikační činnosti (J)"),
    "K": ("K", "Peněžnictví a pojišťovnictví (K)"),
    "L": ("L", "Činnosti v oblasti nemovitostí (L)"),
    **{s: ("M_N", "Profesní, vědecké, technické a administrativní činnosti (M–N)") for s in "MN"},
    **{s: ("O-Q", "Veřejná správa, obrana, vzdělávání, zdravotní a sociální péče (O–Q)") for s in "OPQ"},
    **{s: ("R-U", "Kulturní, zábavní, rekreační a ostatní činnosti (R–U)") for s in "RSTU"},
}
REGIONY_SOUDRZNOSTI = {"CZ01": "Praha", "CZ02": "Střední Čechy", "CZ03": "Jihozápad", "CZ04": "Severozápad",
                       "CZ05": "Severovýchod", "CZ06": "Jihovýchod", "CZ07": "Střední Morava",
                       "CZ08": "Moravskoslezsko"}
EKON_ROKY = 5
EUROSTAT_CITACE = ("Eurostat, regionální účty: nama_10r_3gva, nama_10r_3empers, nama_10r_2coe "
                   "(https://ec.europa.eu/eurostat/databrowser/view/<kód sady>/default/table), staženo {datum}; "
                   "upraveno (výběr, podíly, poměry, řetězení objemových změn) – za úpravy Eurostat neodpovídá.")


def nacti_ekonomiku(cur, skupina: str | None) -> dict:
    """Regionální účty Eurostatu: {(ukazatel, geo, skupina A*10, rok): hodnota} a datum stažení."""
    cur.execute("SELECT to_regclass('res.eu_regionalni_ucty')")
    if cur.fetchone()[0] is None or skupina is None:
        return {}
    cur.execute("SELECT ukazatel, geo, nace, rok, hodnota, stazeno::date FROM res.eu_regionalni_ucty "
                "WHERE nace = ANY(%s)", ([skupina, "TOTAL"],))
    radky = cur.fetchall()
    out = {(u, g, n, r): float(h) for u, g, n, r, h, _ in radky}
    if radky:
        out["_stazeno"] = max(x[5] for x in radky)
    return out


def tabulky_ekonomika(uz: "Uzemi", srovnani: list["Uzemi"], obor: list[dict], kraje: dict, ek: dict) -> list[dict]:
    """T22 HPH, zaměstnanost a produktivita (kraje, ČR) a T23 náhrady zaměstnancům (regiony soudržnosti).

    Jen publikovaná čísla Eurostatu a poměry mezi nimi v témže roce a území; nic se nedopočítává
    z jiných úrovní. Objemový vývoj = řetězení meziročních změn z HPH v cenách předchozího roku."""
    sekce = {o["sekce"] for o in obor}
    skupiny = {SKUPINY_A10[s] for s in sekce if s in SKUPINY_A10}
    sl22 = [{"kod": "hph", "nazev": "HPH skupiny (mil. Kč, běžné ceny)", "ukazatel": "EKON_HPH"},
            {"kod": "hph_podil_uzemi", "nazev": "Podíl na HPH území (%)", "ukazatel": "EKON_HPH_PODIL_UZEMI"},
            {"kod": "hph_podil_cr", "nazev": "Podíl na HPH skupiny v ČR (%)", "ukazatel": "EKON_HPH_PODIL_CR"},
            {"kod": "rust", "nazev": "Objemová změna HPH (%)", "ukazatel": "EKON_HPH_RUST"},
            {"kod": "objem_index", "nazev": "Objem HPH (1. rok = 100)", "ukazatel": "EKON_HPH_OBJEM_INDEX"},
            {"kod": "zam", "nazev": "Zaměstnaní (tis.)", "ukazatel": "EKON_ZAM"},
            {"kod": "podil_self", "nazev": "Sebezaměst\u00adnaní (%)", "ukazatel": "EKON_ZAM_PODIL_SELF"},
            {"kod": "produktivita", "nazev": "HPH na zaměst\u00adnaného (tis. Kč)", "ukazatel": "EKON_PRODUKTIVITA"},
            {"kod": "produktivita_index_cr", "nazev": "Produktivita (ČR = 100)",
             "ukazatel": "EKON_PRODUKTIVITA_INDEX_CR"}]
    sl23 = [{"kod": "nahrady", "nazev": "Náhrady zaměstnancům (mil. Kč)", "ukazatel": "EKON_NAHRADY"},
            {"kod": "hph", "nazev": "HPH (mil. Kč, běžné ceny)", "ukazatel": "EKON_HPH"},
            {"kod": "podil", "nazev": "Náhrady zaměstnancům / HPH skupiny (%)", "ukazatel": "EKON_NAHRADY_PODIL"},
            {"kod": "podil_vse", "nazev": "Náhrady / HPH, všechna odvětví (%)", "ukazatel": "EKON_NAHRADY_PODIL"}]
    nazev22 = "Hrubá přidaná hodnota, zaměstnanost a produktivita – kraje a ČR (Eurostat, regionální účty)"
    nazev23 = "Náhrady zaměstnancům a hrubá přidaná hodnota – regiony soudržnosti (Eurostat)"
    if len(skupiny) != 1 or not ek:
        duvod = ("obor zasahuje do více skupin odvětví A*10 regionálních účtů" if ek
                 else "regionální účty Eurostatu nejsou načtené (res_import eurostat)")
        return [tabulka_nezverejnena("T22_ekonomika", nazev22, duvod, sl22),
                tabulka_nezverejnena("T23_nahrady", nazev23, duvod, sl23)]
    sk, sk_nazev = next(iter(skupiny))
    kraj_uz = uz.kraj_kod
    uzemi = ([("CZ", "Česko")] if uz.typ == "CR" else
             [(kraj_uz, kraje[kraj_uz]["nazev"]), ("CZ", "Česko")]
             + [(k.kod, k.nazev) for k in srovnani if k.kod != kraj_uz])
    roky_vse = sorted({k[3] for k in ek if isinstance(k, tuple) and k[0] == "HPH_CP" and k[2] == sk})
    roky = roky_vse[-EKON_ROKY:]

    def h(uk, geo, n, rok):
        return ek.get((uk, geo, n, rok))

    radky22 = []
    for geo, nazev in uzemi:
        objem = 100.0
        for i, rok in enumerate(roky):
            hph, hph_vse = h("HPH_CP", geo, sk, rok), h("HPH_CP", geo, "TOTAL", rok)
            hph_cr = h("HPH_CP", "CZ", sk, rok)
            pyp, cp_pred = h("HPH_PYP", geo, sk, rok), h("HPH_CP", geo, sk, rok - 1)
            rust = round(100 * (pyp / cp_pred - 1), 1) if pyp and cp_pred else None
            if i and pyp and cp_pred:
                objem *= pyp / cp_pred
            zam, self_ = h("ZAM_EMP", geo, sk, rok), h("ZAM_SELF", geo, sk, rok)
            prod = hph / zam if hph and zam else None              # mil. Kč / tis. osob = tis. Kč
            zam_cr, hph_cr_ = h("ZAM_EMP", "CZ", sk, rok), hph_cr
            prod_cr = hph_cr_ / zam_cr if hph_cr_ and zam_cr else None
            radky22.append({"popis": f"{nazev} – {rok}", "typ": "polozka", "uzemi": geo, "rok": rok, "hodnoty": {
                "hph": round(hph) if hph is not None else None,
                "hph_podil_uzemi": round(100 * hph / hph_vse, 2) if hph and hph_vse else None,
                "hph_podil_cr": round(100 * hph / hph_cr, 2) if hph and hph_cr and geo != "CZ" else None,
                "rust": rust, "objem_index": round(objem, 1),
                "zam": round(zam, 2) if zam is not None else None,
                "podil_self": round(100 * self_ / zam, 1) if self_ is not None and zam else None,
                "produktivita": round(prod) if prod else None,
                "produktivita_index_cr": round(100 * prod / prod_cr, 1) if prod and prod_cr and geo != "CZ" else None,
            }})
    presne = sekce == {sk}                    # skupina A*10 = právě sekce oboru (A, C, F, J, K, L)
    pozn22 = [f"Skupina odvětví A*10 regionálních účtů: {sk_nazev}. "
              + ("Odpovídá sekci oboru přesně." if presne else
                 f"Sekce oboru ({', '.join(sorted(sekce))}) je součástí této širší skupiny – nejbližší publikovaná "
                 f"úroveň; údaje zahrnují i další sekce skupiny."),
              "Zaměstnaní = zaměstnanost podle národních účtů (zaměstnanci i sebezaměstnaní, včetně podnikajících "
              "fyzických osob, místo pracoviště); liší se proto od přepočtených zaměstnanců ČSÚ v kapitole "
              "Zaměstnanost a mzdy (jen zaměstnanci, přepočet na plný úvazek) i od počtu registrovaných subjektů.",
              "Objemová změna = HPH v cenách předchozího roku / HPH v běžných cenách předchozího roku − 1; objem "
              "(první rok = 100) je řetězením těchto změn. Produktivita = HPH v běžných cenách / zaměstnaní.",
              f"Eurostat u údajů neuvádí příznak předběžnosti; poslední publikovaný rok {roky_vse[-1] if roky_vse else '–'} "
              f"se při revizích regionálních účtů může změnit."]
    if any(o["uroven"] > 1 for o in obor):
        pozn22.insert(0, f"Nejbližší publikovaná úroveň: skupina {sk_nazev} – Eurostat regionální účty podle "
                         f"oddílů a nižších úrovní CZ-NACE nepublikuje.")
    if uz.typ == "OKRES":
        pozn22.insert(0, f"Nejbližší publikovaná úroveň: kraj {kraje[kraj_uz]['nazev']} – regionální účty za okresy "
                         f"neexistují.")
    t22 = {"kod": "T22_ekonomika", "nazev": nazev22 + f" – {sk_nazev}", "sloupce": sl22, "radky": radky22,
           "zverejneno": bool(radky22), "duvod": None if radky22 else "Eurostat údaje nepublikuje",
           "poznamky": pozn22, "skupina": sk, "skupina_nazev": sk_nazev}

    regiony = []
    for geo, _ in uzemi:
        r = geo if geo == "CZ" else geo[:4]
        if r not in regiony:
            regiony.append(r)
    radky23 = []
    for r in regiony:
        kraje_r = [kraje[k]["nazev"] for k in kraje if k.startswith(r)] if r != "CZ" else []
        nazev = "Česko" if r == "CZ" else f"{REGIONY_SOUDRZNOSTI[r]} (region soudržnosti: {', '.join(kraje_r)})"
        for rok in roky:
            nah, hph = h("NAHRADY", r, sk, rok), h("HPH_CP", r, sk, rok)
            nah_v, hph_v = h("NAHRADY", r, "TOTAL", rok), h("HPH_CP", r, "TOTAL", rok)
            radky23.append({"popis": f"{nazev} – {rok}", "typ": "polozka", "uzemi": r, "rok": rok, "hodnoty": {
                "nahrady": round(nah) if nah is not None else None, "hph": round(hph) if hph is not None else None,
                "podil": round(100 * nah / hph, 1) if nah and hph else None,
                "podil_vse": round(100 * nah_v / hph_v, 1) if nah_v and hph_v else None}})
    t23 = {"kod": "T23_nahrady", "nazev": nazev23 + f" – {sk_nazev}", "sloupce": sl23, "radky": radky23,
           "zverejneno": bool(radky23), "duvod": None if radky23 else "Eurostat údaje nepublikuje",
           "poznamky": ["Nejbližší publikovaná úroveň: region soudržnosti (NUTS 2) – náhrady zaměstnancům Eurostat "
                        "za kraje nepublikuje. Region zahrnuje více krajů; srovnávací kraj ze stejného regionu má "
                        "stejné hodnoty.",
                        "Podíl náhrad zaměstnancům na HPH ukazuje, jaká část přidané hodnoty připadá na mzdy "
                        "a pojistné zaměstnanců; zbytek tvoří hlavně hrubý provozní přebytek a smíšený důchod "
                        "(příjem podnikatelů)."],
           "skupina": sk}
    return [t22, t23]


def nacti_sbs(cur, sekce: str | None) -> dict:
    """SBS ČR (sekce a její oddíly) a kurz CZK/EUR: {(ukazatel, nace, třída, rok): hodnota}."""
    cur.execute("SELECT to_regclass('res.eu_sbs')")
    if cur.fetchone()[0] is None or not sekce:
        return {}
    cur.execute("SELECT ukazatel, nace, velikost, rok, hodnota, stazeno::date FROM res.eu_sbs "
                "WHERE (sada = 'sbs_sc_ovw' AND (nace = %s OR nace ~ ('^' || %s || '[0-9]{2}$'))) "
                "OR sada = 'ert_bil_eur_a'", (sekce, sekce))
    radky = cur.fetchall()
    out = {(u, n, v, r): float(h) for u, n, v, r, h, _ in radky}
    if radky:
        out["_stazeno"] = max(x[5] for x in radky)
    return out


def tabulky_model(uz: "Uzemi", obor: list[dict], kraje: dict, subjekty_uzemi: list[tuple],
                  subjekty_cr: list[tuple], aktivita: dict, ek: dict, sbs: dict, prah: int) -> list[dict]:
    """Modelové odhady (Blok 8): T24 přidaná hodnota a obrat podle velikosti, T25 koncentrace,
    T26 fakta SBS za ČR (typický obrat, marže), T27 kontrola konzistence modelu na celé ČR."""
    from firemni_databaze import report_model as m
    sl24 = [{"kod": "hph_lo", "nazev": "Přidaná hodnota – dolní mez (mil. Kč)", "ukazatel": "MODEL_HPH"},
            {"kod": "hph_hi", "nazev": "Přidaná hodnota – horní mez (mil. Kč)", "ukazatel": "MODEL_HPH"},
            {"kod": "podil_lo", "nazev": "Podíl na přidané hodnotě – dolní (%)", "ukazatel": "MODEL_HPH_PODIL"},
            {"kod": "podil_hi", "nazev": "Podíl na přidané hodnotě – horní (%)", "ukazatel": "MODEL_HPH_PODIL"},
            {"kod": "obrat_lo", "nazev": "Obrat – dolní mez (mil. Kč)", "ukazatel": "MODEL_OBRAT"},
            {"kod": "obrat_hi", "nazev": "Obrat – horní mez (mil. Kč)", "ukazatel": "MODEL_OBRAT"}]
    sl25 = [{"kod": "hph_lo", "nazev": "Podíl na přidané hodnotě – dolní (%)", "ukazatel": "MODEL_KONCENTRACE"},
            {"kod": "hph_hi", "nazev": "Podíl na přidané hodnotě – horní (%)", "ukazatel": "MODEL_KONCENTRACE"},
            {"kod": "obrat_lo", "nazev": "Podíl na obratu – dolní (%)", "ukazatel": "MODEL_KONCENTRACE"},
            {"kod": "obrat_hi", "nazev": "Podíl na obratu – horní (%)", "ukazatel": "MODEL_KONCENTRACE"}]
    sl26 = [{"kod": "podniky", "nazev": "Podniky", "ukazatel": "SBS_PODNIKY"},
            {"kod": "osoby", "nazev": "Zaměstnané osoby", "ukazatel": "SBS_OSOBY"},
            {"kod": "obrat_podnik", "nazev": "Obrat na podnik (mil. Kč)", "ukazatel": "SBS_OBRAT_PODNIK"},
            {"kod": "obrat_podnik_lo", "nazev": "Obrat na podnik, oddíly – min. (mil. Kč)", "ukazatel": "SBS_OBRAT_PODNIK"},
            {"kod": "obrat_podnik_hi", "nazev": "Obrat na podnik, oddíly – max. (mil. Kč)", "ukazatel": "SBS_OBRAT_PODNIK"},
            {"kod": "marze", "nazev": "Hrubý provozní přebytek / obrat (%)", "ukazatel": "SBS_MARZE"}]
    sl27 = [{"kod": "model_lo", "nazev": "Model – dolní", "ukazatel": "MODEL_KONTROLA"},
            {"kod": "model_hi", "nazev": "Model – horní", "ukazatel": "MODEL_KONTROLA"},
            {"kod": "sbs", "nazev": "SBS (fakt)", "ukazatel": "MODEL_KONTROLA"},
            {"kod": "odchylka", "nazev": "Vzdálenost faktu od pásma (p. b. nebo %)", "ukazatel": "MODEL_KONTROLA"}]
    n24 = "Modelový odhad: přidaná hodnota a obrat oboru podle velikosti subjektů"
    n25 = "Modelový odhad: koncentrace – podíl subjektů s 10+ a 50+ zaměstnanými osobami"
    n26 = "Statistika podniků za ČR podle velikosti: typický obrat a marže (fakt za ČR, Eurostat SBS)"
    n27 = "Kontrola konzistence: model použitý na celou ČR proti statistice podniků (SBS)"
    vse = [(n24, "T24_model_velikost", sl24), (n25, "T25_model_koncentrace", sl25),
           (n26, "T26_sbs_cr", sl26), (n27, "T27_model_kontrola", sl27)]
    sekce = {o["sekce"] for o in obor}
    s = next(iter(sekce)) if len(sekce) == 1 else None
    duvod = None
    if not ek or not sbs:
        duvod = "vstupy modelu nejsou načtené (res_import eurostat)"
    elif s is None or len(obor) != 1 or obor[0]["uroven"] != 1:
        duvod = ("model je zatím jen pro obor zadaný jako celá sekce CZ-NACE: krajská přidaná hodnota existuje jen "
                 "za skupiny A*10 a podnikové poměry SBS za sekce a oddíly – pro užší obor by se míchaly úrovně")
    elif SKUPINY_A10.get(s, ("",))[0] != s:
        duvod = f"sekce {s} je v regionálních účtech součástí širší skupiny A*10; přidaná hodnota sekce za kraj neexistuje"
    elif not any(k[1] == s for k in sbs if isinstance(k, tuple) and k[0] == "AV_MEUR"):
        duvod = f"Eurostat SBS sekci {s} nepublikuje"
    if duvod:
        return [tabulka_nezverejnena(kod, n, duvod, sl) for n, kod, sl in vse]
    roky_sbs = {k[3] for k in sbs if isinstance(k, tuple) and k[0] == "AV_MEUR" and k[1] == s}
    roky_ek = {k[3] for k in ek if isinstance(k, tuple) and k[0] == "HPH_CP" and k[2] == s}
    rok = max(roky_sbs & roky_ek)
    kurz = sbs[("KURZ_CZK_EUR", "-", "-", rok)]
    S = {(u, tr): sbs[(u, s, tr, rok)] for u in ("ENT_NR", "EMP_NR", "AV_MEUR", "NETTUR_MEUR", "GOS_MEUR")
         for tr in m.TRIDY + ("TOTAL",) if (u, s, tr, rok) in sbs}
    kraj = uz.kraj_kod or "CZ"
    geo = "CZ" if uz.typ == "CR" else kraj
    subj = subjekty_uzemi
    a = aktivita.get((kraj, s), {})
    podil_akt = a["4958_akt"] / a["4958_reg"] if a.get("4958_reg") else None
    a_cr = aktivita.get(("CZ", s), {})
    podil_akt_cr = a_cr["4958_akt"] / a_cr["4958_reg"] if a_cr.get("4958_reg") else None
    if podil_akt is None or podil_akt_cr is None:
        return [tabulka_nezverejnena(kod, n, "ČSÚ nepublikuje podíl se zjištěnou aktivitou pro sekci a kraj", sl)
                for n, kod, sl in vse]
    hph_uz = ek[("HPH_CP", geo, s, rok)]
    var = {v: m.rozpocet(m.pocty_trid(subj, v), podil_akt, hph_uz, S) for v in ("zakladni", "pomerna")}
    for v in var.values():                                  # kontrola: součet tříd = krajský celek
        if abs(sum(v["hph"].values()) - hph_uz) > 1e-6 * hph_uz:
            raise AssertionError("modelová přidaná hodnota tříd nesedí na krajský celek")
    pocty_min = {tr: min(m.pocty_trid(subj, v)[tr] for v in var) for tr in m.TRIDY}
    skupiny = m.skupiny_publikace(pocty_min, prah)
    uz_popis = f"{kraje[kraj]['nazev']}" if geo != "CZ" else "Česko"
    pozn_rok = (f"Rok: ekonomika (regionální účty a SBS) {rok}; struktura subjektů z RES ke dni snímku. "
                f"Spojení různých let je součástí modelu.")
    radky24 = []
    for nazev, tridy in skupiny:
        h = [sum(var[v]["hph"][x] for x in tridy) for v in var]
        o = [sum(var[v]["obrat"][x] for x in tridy) for v in var]
        p_ = [100 * x / hph_uz for x in h]
        radky24.append({"popis": nazev, "typ": "polozka", "hodnoty": {
            "hph_lo": m.pasmo(*h)[0], "hph_hi": m.pasmo(*h)[1], "podil_lo": m.pasmo(*p_, 1)[0],
            "podil_hi": m.pasmo(*p_, 1)[1], "obrat_lo": m.pasmo(*o)[0], "obrat_hi": m.pasmo(*o)[1]},
            "poznamka": "modelový odhad"})
    o_cel = [var[v]["obrat_celkem"] for v in var]
    radky24.append({"popis": f"celkem ({uz_popis})", "typ": "celkem", "hodnoty": {
        "hph_lo": round(hph_uz), "hph_hi": round(hph_uz), "podil_lo": 100.0, "podil_hi": 100.0,
        "obrat_lo": m.pasmo(*o_cel)[0], "obrat_hi": m.pasmo(*o_cel)[1]},
        "poznamka": "přidaná hodnota celkem = fakt (Eurostat); obrat = modelový odhad"})
    metodika = ("Modelový odhad, ne statistika. Přidaná hodnota skupiny v kraji (Eurostat, regionální účty) je "
                "rozpočítána mezi velikostní třídy podle počtu subjektů oboru v kraji (RES, KATPO, zúženo na podíl "
                "se zjištěnou aktivitou podle ČSÚ) a celostátní přidané hodnoty na podnik třídy (Eurostat SBS); obrat "
                "= přidaná hodnota třídy × celostátní poměr obrat / přidaná hodnota v třídě. Pásmo: „Neuvedeno“ "
                "v KATPO do nejmenší třídy (FO i PO), nebo poměrně podle známé struktury FO, resp. PO.")
    pozn24 = [metodika, pozn_rok,
              "KATPO udává počet zaměstnanců, třídy SBS počet zaměstnaných osob včetně majitelů – na hranicích "
              "tříd se mohou lišit. Třídy pod prahem 10 subjektů jsou sloučeny s vyšší třídou.",
              "Obrat vychází z přidané hodnoty národních účtů, která je vyšší než přidaná hodnota SBS (zahrnuje "
              "i neregistrovanou ekonomiku a jiné ocenění); model proto obrat nadhodnocuje – viz kontrola "
              "konzistence."]
    if uz.typ == "OKRES":
        pozn24.insert(0, f"Nejbližší úroveň: kraj {kraje[kraj]['nazev']} – regionální účty za okresy neexistují.")
    t24 = {"kod": "T24_model_velikost", "nazev": f"{n24} – {uz_popis}, {rok}", "sloupce": sl24, "radky": radky24,
           "zverejneno": True, "duvod": None, "poznamky": pozn24, "rok": rok, "model": True}

    hranice = {tr for _, tridy in skupiny for tr in tridy[:1]}           # první třídy publikovaných skupin
    radky25 = []
    for prahk, klic, tr in (("10 a více osob", "10", "10-19"), ("50 a více osob", "50", "50-249")):
        if tr not in hranice:
            continue                                       # hranice by rozdělila sloučenou skupinu
        hp = [var[v][f"hph_podil_{klic}"] for v in var]
        op = [var[v][f"obrat_podil_{klic}"] for v in var]
        radky25.append({"popis": f"Subjekty s {prahk}", "typ": "polozka", "hodnoty": {
            "hph_lo": m.pasmo(*hp, 1)[0], "hph_hi": m.pasmo(*hp, 1)[1],
            "obrat_lo": m.pasmo(*op, 1)[0], "obrat_hi": m.pasmo(*op, 1)[1]}, "poznamka": "modelový odhad"})
    t25 = {"kod": "T25_model_koncentrace", "nazev": f"{n25} – {uz_popis}, {rok}", "sloupce": sl25,
           "radky": radky25, "zverejneno": bool(radky25),
           "duvod": None if radky25 else "velikostní třídy nad 10 osob jsou pod prahem – koncentraci nelze zveřejnit",
           "poznamky": [metodika, pozn_rok, "Koncentrace podle velikostních tříd, ne podle jednotlivých subjektů; "
                        "podíl největších firem by vyžadoval účetní závěrky (Sbírka listin)."], "rok": rok, "model": True}

    radky26 = []
    oddily = sorted({k[1] for k in sbs if isinstance(k, tuple) and k[0] == "AV_MEUR" and k[1] != s and k[3] == rok})
    for tr in m.TRIDY + ("TOTAL",):
        ent, emp = S.get(("ENT_NR", tr)), S.get(("EMP_NR", tr))
        obr, gos = S.get(("NETTUR_MEUR", tr)), S.get(("GOS_MEUR", tr))
        na_podnik = [sbs[("NETTUR_MEUR", o, tr, rok)] / sbs[("ENT_NR", o, tr, rok)] * kurz for o in oddily
                     if (("NETTUR_MEUR", o, tr, rok) in sbs and sbs.get(("ENT_NR", o, tr, rok)))]
        radky26.append({"popis": "celkem" if tr == "TOTAL" else m.NAZVY_TRID[tr],
                        "typ": "celkem" if tr == "TOTAL" else "polozka", "hodnoty": {
            "podniky": round(ent) if ent else None, "osoby": round(emp) if emp else None,
            "obrat_podnik": round(obr / ent * kurz, 2) if obr and ent else None,
            "obrat_podnik_lo": round(min(na_podnik), 2) if na_podnik else None,
            "obrat_podnik_hi": round(max(na_podnik), 2) if na_podnik else None,
            "marze": round(100 * gos / obr, 1) if gos is not None and obr else None}})
    t26 = {"kod": "T26_sbs_cr", "nazev": f"{n26} – sekce {s}, {rok}", "sloupce": sl26, "radky": radky26,
           "zverejneno": True, "duvod": None, "rok": rok,
           "poznamky": [f"Fakt za ČR, ne odhad za kraj. Zdroj: Eurostat, sbs_sc_ovw (podniky, zaměstnané osoby, čistý "
                        f"obrat, hrubý provozní přebytek; mil. EUR převedeno ročním průměrným kurzem {str(kurz).replace('.', ',')} "
                        f"Kč/EUR, ert_bil_eur_a). Rok {rok}.",
                        f"Obrat na podnik je průměr třídy (ne medián); pásmo min.–max. ukazuje rozdíly mezi oddíly "
                        f"({', '.join(o[1:] for o in oddily)}). Podniky SBS jsou aktivní podniky, ne registrované subjekty.",
                        "Peněžní údaje SBS jsou jen za třídy 0–9, 10–19, 20–49, 50–249 a 250+; rozdělení 0–1 a 2–9 "
                        "osob Eurostat publikuje jen u počtů."]}

    # kontrola konzistence: model na celou ČR (RES ČR, podíl aktivity ČR, HPH ČR z regionálních účtů)
    hph_cr = ek[("HPH_CP", "CZ", s, rok)]
    var_cr = {v: m.rozpocet(m.pocty_trid(subjekty_cr, v), podil_akt_cr, hph_cr, S) for v in ("zakladni", "pomerna")}
    radky27 = []
    for tr in m.TRIDY:
        mp = [100 * var_cr[v]["hph"][tr] / hph_cr for v in var_cr]
        sp = 100 * S[("AV_MEUR", tr)] / S[("AV_MEUR", "TOTAL")]
        lo, hi = m.pasmo(*mp, 1)
        sp = round(sp, 1)
        odch = 0.0 if lo <= sp <= hi else min(abs(lo - sp), abs(hi - sp))
        radky27.append({"popis": f"Podíl třídy {m.NAZVY_TRID[tr]} na přidané hodnotě (%)", "typ": "polozka",
                        "hodnoty": {"model_lo": lo, "model_hi": hi, "sbs": sp, "odchylka": round(odch, 1)},
                        "poznamka": "fakt SBS uvnitř pásma" if odch == 0 else "fakt SBS mimo pásmo (p. b.)"})
    obr_m = [var_cr[v]["obrat_celkem"] for v in var_cr]
    obr_s = S[("NETTUR_MEUR", "TOTAL")] * kurz
    lo_o, hi_o = m.pasmo(*obr_m)
    radky27.append({"popis": "Obrat sekce celkem (mil. Kč)", "typ": "polozka", "hodnoty": {
        "model_lo": lo_o, "model_hi": hi_o, "sbs": round(obr_s),
        "odchylka": 0.0 if lo_o <= obr_s <= hi_o else round(100 * (min(abs(lo_o - obr_s), abs(hi_o - obr_s)) / obr_s), 1)},
        "poznamka": "model nadhodnocuje (% od bližší meze)" if lo_o > obr_s else "fakt SBS mimo pásmo (%)"})
    radky27.append({"popis": "Přidaná hodnota sekce celkem (mil. Kč)", "typ": "polozka", "hodnoty": {
        "model_lo": round(hph_cr), "model_hi": round(hph_cr), "sbs": round(S[("AV_MEUR", "TOTAL")] * kurz),
        "odchylka": round(100 * (hph_cr / (S[("AV_MEUR", "TOTAL")] * kurz) - 1), 1)},
        "poznamka": "vstup modelu (národní účty) proti SBS, rozdíl v %; příčina nadhodnocení obratu"})
    t27 = {"kod": "T27_model_kontrola", "nazev": f"{n27} – sekce {s}, {rok}", "sloupce": sl27, "radky": radky27,
           "zverejneno": True, "duvod": None, "rok": rok, "model": True,
           "poznamky": ["Model se stejnými vstupy, ale za celou ČR (RES ČR, podíl se zjištěnou aktivitou za ČR, přidaná "
                        "hodnota sekce v ČR z regionálních účtů), porovnaný s celostátními hodnotami SBS. Odchylky "
                        "ukazují, jak přesný model je i tam, kde fakt známe.", pozn_rok]}
    return [t24, t25, t26, t27]


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
        self.promenne: dict[str, dict] = {}   # kód → {hodnota, zverejneno[, chranit]}
        self.rovnice: list = []               # (celek, [části]) nebo {"koef": {proměnná: k}}

    def promenna(self, kod: str, hodnota: int, zverejneno: bool, chranit: bool | None = None) -> None:
        """chranit=False: nezveřejněná proměnná, kterou není třeba chránit, protože je na prahu nebo nad
        ním a skrytá je jen kvůli srovnatelnosti nebo jako mezivýsledek (např. vzniky PO odvozené ze
        stavů, položka předem sloučená v benchmarku). Pro kontrolu dopočtu zůstává neznámou."""
        stara = self.promenne.get(kod)
        if stara and stara["hodnota"] != hodnota:
            raise AssertionError(f"proměnná {kod} má dvě hodnoty: {stara['hodnota']} a {hodnota}")
        if chranit is None:
            chranit = stara.get("chranit", True) if stara else True
        self.promenne[kod] = {"hodnota": hodnota, "zverejneno": zverejneno or bool(stara and stara["zverejneno"])}
        if not chranit:
            if hodnota < self.prah:
                raise AssertionError(f"pomocná proměnná {kod} je pod prahem – musí se chránit")
            self.promenne[kod]["chranit"] = False

    def rovnice_obecna(self, koef: dict[str, int]) -> None:
        self.rovnice.append({"koef": dict(koef)})

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
        skryte = {k for k, v in self.promenne.items() if not v["zverejneno"] and v.get("chranit", True)}
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
        _sekce = {o["sekce"] for o in obor}
        _skupiny = {SKUPINY_A10[s][0] for s in _sekce if s in SKUPINY_A10}
        ekonomika = nacti_ekonomiku(cur, next(iter(_skupiny)) if len(_skupiny) == 1 else None)
        sbs = nacti_sbs(cur, next(iter(_sekce)) if len(_sekce) == 1 else None)
        mzdy = nacti_mzdy(cur, next(iter({o["sekce"] for o in obor})) if len({o["sekce"] for o in obor}) == 1 else None)
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
    for okres, _, zanik in d["zaniky_po"]:
        if v_uzemi(okres, uz):
            zaniky[zanik.year] = zaniky.get(zanik.year, 0) + 1
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

    # --- Benchmarky struktury: týž obor v ČR a ve srovnávacích krajích (Blok 4 A) -------
    # Každé benchmarkové území má vlastní proměnné (předpona „cr:“ / „kraj:<kód>:“) a vlastní
    # potlačení. Položky jsou ty, které jsou zveřejněné ve zkoumaném území; co je tam sloučeno
    # do „ostatní“, je v benchmarku sloučeno předem taky, aby sloupce byly srovnatelné.
    okresy_uz_kraje = [k for k in okresy if okresy[k]["kraj_kod"] == uz.kraj_kod] if uz.kraj_kod else []
    bench: list[tuple[str, Uzemi]] = []
    if uz.typ != "CR":
        bench.append(("cr:", Uzemi("CR", "CZ", "Česko", None)))
    for k in srovnani:
        if k.kod == uz.kod or (uz.typ == "OKRES" and k.kod == uz.kraj_kod and len(okresy_uz_kraje) == 1):
            continue    # kraj s jediným okresem = zkoumané území, srovnání by obešlo potlačení
        bench.append((f"kraj:{k.kod}:", k))
    tab_uz = {t["kod"]: t for t in tabulky_uzemi}

    def sloupec(pref: str) -> str:
        return pref.rstrip(":").replace(":", "_")

    def bench_cleneni(pref: str, celek: str, zv_celek: bool, hodnoty: dict[str, int], kody_uz: list[str],
                      ostatni_kod: str):
        """Potlačení jednoho členění benchmarkového území. Vrátí ({kód: počet} zveřejněných, počet
        v „ostatní“, zda „ostatní“ obsahuje i položku zveřejněnou ve zkoumaném území), nebo None."""
        zbytek = sorted(k for k, n in hodnoty.items() if n and k not in kody_uz)
        for k, n in hodnoty.items():
            if n:   # položka sloučená jen kvůli srovnatelnosti a na prahu není citlivá (chránit netřeba)
                s.promenna(pref + k, n, False, chranit=False if k in zbytek and n >= prah else None)
        bunky = [Bunka(pref + k, k, hodnoty.get(k, 0)) for k in kody_uz]
        predem = pref + ostatni_kod + ":predem"
        if zbytek:
            n_predem = sum(hodnoty[k] for k in zbytek)
            s.promenna(predem, n_predem, False, chranit=False if n_predem >= prah else None)
            s.rovnice_souctu(predem, [pref + k for k in zbytek])
            bunky.append(Bunka(predem, "ostatní", sum(hodnoty[k] for k in zbytek)))
        p = potlac(bunky, prah)
        for b in [b for b in p.zverejnene if b.kod == predem]:     # předem sloučené zůstává v „ostatní“
            p.zverejnene.remove(b)
            p.ostatni.append(b)
        if not zv_celek:
            p.cele_skryte = True
        s.zaznamenej_potlaceni(p, celek, pref + ostatni_kod)
        if p.cele_skryte:
            return None
        return ({b.kod[len(pref):]: b.hodnota for b in p.zverejnene}, p.ostatni_hodnota,
                any(b.kod != predem for b in p.ostatni))

    def struktura_uzemi(u: Uzemi) -> dict:
        st = {"n": 0, "fopo:FO": 0, "fopo:PO": 0, "formy": {}, "vel": {}, "vek": {}}
        for okres, f, kp, v in d["subjekty"]:
            if not v_uzemi(okres, u):
                continue
            g = "FO" if f in FO_FORMY else "PO"
            st["n"] += 1
            st[f"fopo:{g}"] += 1
            st["formy"][f"forma:{f}"] = st["formy"].get(f"forma:{f}", 0) + 1
            vel = next(kod for kod, _, kody in PASMA_VELIKOSTI if kp in kody)
            st["vel"][f"vel_{g}:{vel}"] = st["vel"].get(f"vel_{g}:{vel}", 0) + 1
            vek_r = (datum - v).days / 365.25
            pas = next(k for od, do, k, _ in PASMA_VEKU if vek_r >= od and (do is None or vek_r < do))
            st["vek"][f"vek:{pas}"] = st["vek"].get(f"vek:{pas}", 0) + 1
        return st

    struktury = {pref: struktura_uzemi(u) for pref, u in bench}
    for pref, u in bench:
        assert struktury[pref]["n"] == pocet_uzemi(u)

    def bench_tabulka(kod: str, nazev: str, t_uz: dict, skupiny: list[dict], poznamky: list[str]) -> dict:
        """Podíly zkoumaného území (z tabulky t_uz) vedle týchž podílů v benchmarkových územích.
        skupiny: [{g, celek: pref → proměnná, zv: pref → bool, hodnoty: pref → {kód: počet},
        clen: kód → bool, ostatni_kod, jmenovatel: pref → počet}] – skupiny slučování (FO / PO)."""
        sloupce = [{"kod": "uzemi", "nazev": f"{uz.nazev} (%)", "ukazatel": "BENCH_PODIL"}]
        sloupce += [{"kod": sloupec(pref), "nazev": f"{u.nazev} (%)", "ukazatel": "BENCH_PODIL"} for pref, u in bench]
        ma_cr = any(pref == "cr:" for pref, _ in bench)
        if ma_cr:
            sloupce.append({"kod": "rozdil_cr", "nazev": "Rozdíl proti ČR (p. b.)", "ukazatel": "BENCH_ROZDIL_PB"})
        if not t_uz["zverejneno"]:
            return tabulka_nezverejnena(kod, nazev, f"tabulka zkoumaného území se nezveřejňuje ({t_uz['duvod']})",
                                        sloupce)
        polozky_uz = [r["promenna"] for r in t_uz["radky"] if r["typ"] == "polozka"]
        vysl = {}
        for sk in skupiny:
            for pref, _ in bench:
                hodn = {k: n for k, n in sk["hodnoty"](pref).items() if sk["clen"](k)}
                vysl[(sk["ostatni_kod"], pref)] = bench_cleneni(
                    pref, sk["celek"](pref), sk["zv"](pref), hodn, [k for k in polozky_uz if sk["clen"](k)],
                    sk["ostatni_kod"])
        radky_uz = list(t_uz["radky"])
        for sk in skupiny:   # benchmark má „ostatní“, zkoumané území ne (tam jsou ty položky nulové)
            if (not any(r["promenna"] == sk["ostatni_kod"] for r in radky_uz)
                    and any(vysl[(sk["ostatni_kod"], pref)] and vysl[(sk["ostatni_kod"], pref)][1] for pref, _ in bench)):
                kde = next(i for i, r in enumerate(radky_uz) if r["typ"] == "celkem" or
                           (r["typ"] == "mezisoucet" and r["promenna"] == f"fopo:{sk['g']}"))
                radky_uz.insert(kde, {"popis": "ostatní (sloučené malé položky)", "typ": "ostatni",
                                      "promenna": sk["ostatni_kod"], "hodnoty": {"podil": None},
                                      "poznamka": "ve zkoumaném území žádné"})
        radky, rozsirene = [], set()
        for r in radky_uz:
            var = r["promenna"]
            if r["typ"] == "polozka":
                sk = next(sk for sk in skupiny if sk["clen"](var))
            elif r["typ"] == "ostatni":
                sk = next(sk for sk in skupiny if var == sk["ostatni_kod"])
            elif r["typ"] == "mezisoucet":
                sk = next(sk for sk in skupiny if var == f"fopo:{sk['g']}")
            else:
                sk = None
            hodnoty = {"uzemi": r["hodnoty"]["podil"]}
            zaklady = {"uzemi": var} if hodnoty["uzemi"] is not None else {}
            for pref, u in bench:
                st, n, zakl = struktury[pref], None, None
                if r["typ"] == "celkem":
                    if s.zverejnena(u.promenna):
                        n, zakl = st["n"], u.promenna
                elif r["typ"] == "mezisoucet":
                    if s.zverejnena(pref + var):
                        n, zakl = st[var], pref + var
                else:
                    v = vysl[(sk["ostatni_kod"], pref)]
                    if v and r["typ"] == "polozka":
                        if var in v[0]:
                            n, zakl = v[0][var], pref + var
                        else:
                            rozsirene.add(u.nazev)
                    elif v and r["typ"] == "ostatni" and v[1]:
                        n, zakl = v[1], pref + sk["ostatni_kod"]
                        if v[2]:
                            rozsirene.add(u.nazev)
                jmen = st["n"] if sk is None else sk["jmenovatel"](pref)
                hodnoty[sloupec(pref)] = _pct(n, jmen) if n is not None else None
                if zakl:
                    zaklady[sloupec(pref)] = zakl
            if ma_cr and hodnoty["uzemi"] is not None and hodnoty["cr"] is not None:
                hodnoty["rozdil_cr"] = round(hodnoty["uzemi"] - hodnoty["cr"], 1)
                zaklady["rozdil_cr"] = var
            radky.append({"popis": r["popis"], "typ": r["typ"], "promenna": var, "zaklady": zaklady, "hodnoty": hodnoty,
                          "poznamka": r.get("poznamka") if r["typ"] == "ostatni" and hodnoty["uzemi"] is None else None})
        pozn = list(poznamky)
        if rozsirene:
            pozn.append(f"{', '.join(sorted(rozsirene))}: některá položka zveřejněná ve zkoumaném území je zde pod "
                        f"prahem a je sloučena do „ostatní“ (v tomto sloupci pomlčka).")
        return {"kod": kod, "nazev": nazev, "sloupce": sloupce, "radky": radky, "zverejneno": True, "duvod": None,
                "poznamky": pozn}

    tabulky_bench = []
    spolecna = ("Týž obor ve všech sloupcích. Položky jsou dané zkoumaným územím; co je v něm sloučeno do „ostatní“, "
                "je sloučeno i v ostatních sloupcích. Práh a slučování platí pro každé území zvlášť.")
    if bench:
        def je_fo(k: str) -> bool:
            return k.split(":", 1)[1] in FO_FORMY
        vse = lambda k: True                                                     # noqa: E731
        celek_u = dict((pref, u.promenna) for pref, u in bench)
        zv_celek = {pref: s.zverejnena(u.promenna) for pref, u in bench}
        tabulky_bench.append(bench_tabulka(
            "T13_bench_fo_po", "Typ osoby – srovnání s ČR a se srovnávacími kraji (podíl, %)", tab_uz["T05_fo_po"],
            [{"g": None, "celek": celek_u.get, "zv": zv_celek.get, "clen": lambda k: k.startswith("fopo:"),
              "hodnoty": lambda p: {k: struktury[p][k] for k in ("fopo:FO", "fopo:PO")},
              "ostatni_kod": "ostatni:T05_fo_po", "jmenovatel": lambda p: struktury[p]["n"]}], [spolecna]))
        fopo_zv = {pref: s.zverejnena(pref + "fopo:FO") and s.zverejnena(pref + "fopo:PO") for pref, _ in bench}
        t06 = tab_uz["T06_pravni_forma"]
        if any(r["typ"] == "mezisoucet" for r in t06["radky"]):
            sk_formy = [{"g": g, "celek": (lambda p, g=g: p + f"fopo:{g}"), "zv": fopo_zv.get,
                         "clen": (lambda k, g=g: k.startswith("forma:") and je_fo(k) == (g == "FO")),
                         "hodnoty": lambda p: struktury[p]["formy"], "ostatni_kod": f"ostatni:T06_pravni_forma:{g}",
                         "jmenovatel": lambda p: struktury[p]["n"]} for g in ("FO", "PO")]
        else:
            sk_formy = [{"g": None, "celek": celek_u.get, "zv": zv_celek.get, "clen": lambda k: k.startswith("forma:"),
                         "hodnoty": lambda p: struktury[p]["formy"], "ostatni_kod": "ostatni:T06_pravni_forma",
                         "jmenovatel": lambda p: struktury[p]["n"]}]
        tabulky_bench.append(bench_tabulka(
            "T14_bench_pravni_forma", "Právní forma – srovnání s ČR a se srovnávacími kraji (podíl z celku, %)",
            t06, sk_formy, [spolecna]))
        for g, kod_uz, kod_b in (("FO", "T07_velikost_fo", "T15_bench_velikost_fo"),
                                 ("PO", "T08_velikost_po", "T16_bench_velikost_po")):
            tabulky_bench.append(bench_tabulka(
                kod_b, f"Velikostní profil {g} – srovnání s ČR a se srovnávacími kraji (podíl z {g}, %)",
                tab_uz[kod_uz],
                [{"g": g, "celek": (lambda p, g=g: p + f"fopo:{g}"), "zv": fopo_zv.get,
                  "clen": (lambda k, g=g: k.startswith(f"vel_{g}:")), "hodnoty": lambda p: struktury[p]["vel"],
                  "ostatni_kod": f"ostatni:{kod_uz}", "jmenovatel": (lambda p, g=g: struktury[p][f"fopo:{g}"])}],
                [spolecna, "„Neuvedeno“ (KATPO 000) je samostatný řádek, nesčítá se s „bez zaměstnanců“."]))
        tabulky_bench.append(bench_tabulka(
            "T17_bench_vekova_struktura",
            "Věková struktura existujících subjektů – srovnání s ČR a se srovnávacími kraji (podíl, %)",
            tab_uz["T09_vekova_struktura"],
            [{"g": None, "celek": celek_u.get, "zv": zv_celek.get, "clen": lambda k: k.startswith("vek:"),
              "hodnoty": lambda p: struktury[p]["vek"], "ostatni_kod": "ostatni:T09_vekova_struktura",
              "jmenovatel": lambda p: struktury[p]["n"]}], [spolecna]))

    # --- T18 míra zániku PO v oboru (Blok 4 B) ---------------------------------------------
    # stav k 1. 1. Y = existující PO se vznikem před 1. 1. Y + PO zaniklé 1. 1. Y nebo později;
    # míra = zaniklé PO v roce / stav k 1. 1.; srovnatelné období 1. 1.–den snímku i pro dřívější roky.
    roky_z = list(range(ZANIKY_OD_ROKU, datum.year + 1))
    posledni = datum.year
    mira_uzemi = [("", uz)] + bench

    def dynamika_po(u: Uzemi) -> dict:
        exist = [v for okres, f, _, v in d["subjekty"] if f not in FO_FORMY and v_uzemi(okres, u)]
        zan = [(v, z) for okres, v, z in d["zaniky_po"] if v_uzemi(okres, u)]
        out = {}
        for y in roky_z:
            od, do_obd = date(y, 1, 1), date(y, datum.month, datum.day)
            out[y] = {
                "stav": sum(1 for v in exist if v < od) + sum(1 for v, z in zan if (v is None or v < od) and z >= od),
                "zan": sum(1 for _, z in zan if z.year == y),
                "obd": sum(1 for _, z in zan if od <= z <= do_obd),
                "vznik": sum(1 for v in exist if v.year == y) + sum(1 for v, _ in zan if v and v.year == y),
            }
        out["nyni"] = len(exist)
        for y in roky_z:     # kontrola rekonstrukce: stav(Y+1) = stav(Y) − zániky(Y) + vzniky(Y)
            dalsi = out[y + 1]["stav"] if y < posledni else out["nyni"]
            assert dalsi == out[y]["stav"] - out[y]["zan"] + out[y]["vznik"], (u.kod, y)
        return out

    t18_radky = []
    for pref, u in mira_uzemi:
        dp = dynamika_po(u)
        po_var = pref + "fopo:PO"
        for y in roky_z:
            x = dp[y]
            v_stav, v_zan, v_obd = f"{pref}stav_po:{y}", f"{pref}zanik_po:{y}", f"{pref}zanik_po_obd:{y}"
            v_vzn, v_mimo = f"{pref}vznik_po:{y}", f"{pref}zanik_po_mimo:{y}"
            # zániky za rok (u zkoumaného území převzaté z T10 včetně jejího slučování)
            zv_zan = s.zverejnena(v_zan) if pref == "" else x["zan"] >= prah
            s.promenna(v_zan, x["zan"], zv_zan)
            if y < posledni:
                mimo = x["zan"] - x["obd"]
                zv_obd = x["obd"] >= prah and (not zv_zan or mimo >= prah)
                s.promenna(v_obd, x["obd"], zv_obd)
                s.promenna(v_mimo, mimo, False, chranit=mimo < prah)
                s.rovnice_obecna({v_zan: 1, v_obd: -1, v_mimo: -1})
            else:
                v_obd, zv_obd = v_zan, zv_zan
            s.promenna(v_vzn, x["vznik"], False, chranit=x["vznik"] < prah)
            dalsi = f"{pref}stav_po:{y + 1}" if y < posledni else po_var
            s.rovnice_obecna({dalsi: 1, v_stav: -1, v_zan: 1, v_vzn: -1})
        # stavy: zveřejnit, je-li stav na prahu a nedá se z nich dopočítat malý počet vzniků
        for y in reversed(roky_z):
            x = dp[y]
            zv = x["stav"] >= prah
            dalsi_zv = s.zverejnena(f"{pref}stav_po:{y + 1}") if y < posledni else s.zverejnena(po_var)
            if zv and dalsi_zv and s.zverejnena(f"{pref}zanik_po:{y}") and x["vznik"] < prah:
                zv = False
            s.promenna(f"{pref}stav_po:{y}", x["stav"], zv)
        for y in roky_z:
            x = dp[y]
            v_stav, v_zan = f"{pref}stav_po:{y}", f"{pref}zanik_po:{y}"
            v_obd = f"{pref}zanik_po_obd:{y}" if y < posledni else v_zan
            zv_stav, zv_zan, zv_obd = s.zverejnena(v_stav), s.zverejnena(v_zan), s.zverejnena(v_obd)
            uplny = y < posledni
            hodnoty = {
                "stav": x["stav"] if zv_stav else None,
                "zan": x["zan"] if zv_zan and uplny else None,
                "mira": round(100 * x["zan"] / x["stav"], 2) if zv_stav and zv_zan and uplny else None,
                "obd": x["obd"] if zv_obd else None,
                "mira_obd": round(100 * x["obd"] / x["stav"], 2) if zv_stav and zv_obd else None,
            }
            poz = []
            if not uplny:
                poz.append("neúplný rok – jen srovnatelné období")
            if not zv_stav or (uplny and not zv_zan) or not zv_obd:
                poz.append("část skryta (práh, dopočet)")
            t18_radky.append({
                "popis": f"{u.nazev} – {y}", "typ": "polozka", "promenna": v_stav, "uzemi": u.kod, "rok": y,
                "zaklady": {"stav": v_stav, "zan": v_zan, "mira": v_zan, "obd": v_obd, "mira_obd": v_obd},
                "hodnoty": hodnoty, "poznamka": "; ".join(poz) or None})
    obdobi_txt = f"1. 1.–{datum.day}. {datum.month}."
    t18 = {"kod": "T18_mira_zaniku_po", "nazev": f"Míra zániku právnických osob v oboru (RES, {ZANIKY_OD_ROKU}–{posledni})",
           "sloupce": [{"kod": "stav", "nazev": "Stav PO k 1. 1.", "ukazatel": "ZANIK_PO_STAV"},
                       {"kod": "zan", "nazev": "Zaniklé PO za rok", "ukazatel": "ZANIK_PO_RES"},
                       {"kod": "mira", "nazev": "Míra zániku za rok (%)", "ukazatel": "MIRA_ZANIKU_PO"},
                       {"kod": "obd", "nazev": f"Zaniklé PO {obdobi_txt}", "ukazatel": "ZANIK_PO_OBD"},
                       {"kod": "mira_obd", "nazev": f"Míra zániku {obdobi_txt} (%)", "ukazatel": "MIRA_ZANIKU_PO_OBD"}],
           "radky": t18_radky, "zverejneno": True, "duvod": None, "obdobi": obdobi_txt,
           "poznamky": [
               "Pomlčka = skryto: počet pod prahem nebo by z něj šlo dopočítat skrytý počet (zániky ve zbytku "
               "roku, vzniky mezi dvěma stavy).",
               "Míra zániku PO = zaniklé PO v roce / stav PO k 1. 1. téhož roku × 100. Stav je rekonstruován "
               "ze snímku RES: existující PO se vznikem před 1. 1. + PO zaniklé 1. 1. nebo později.",
               f"Rok {posledni} je neúplný (snímek k {datum.day}. {datum.month}. {datum.year}); pro srovnání se "
               f"proto počítá i srovnatelné období {obdobi_txt} každého roku.",
               "Omezení: jen právnické osoby – zaniklé FO mají v otevřených datech jen IČO a datum zániku. "
               f"Okno {len(roky_z)} let ({ZANIKY_OD_ROKU}–{posledni}): RES uchovává zaniklé subjekty jen 4 roky po "
               "zániku. Obor a sídlo jsou podle snímku (u zaniklých poslední známé), jejich změny v čase se "
               "nepromítají."]}

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

    tabulky = ([t01_tab, t02, t03] + ([t04] if t04 else []) + tabulky_uzemi + tabulky_bench
               + tabulky_ekonomika(uz, srovnani, obor, kraje, ekonomika)
               + tabulky_model(uz, obor, kraje,
                               [(f, kp) for okres, f, kp, _ in d["subjekty"]
                                if v_uzemi(okres, uz if uz.typ != "OKRES" else
                                           Uzemi("KRAJ", uz.kraj_kod, kraje[uz.kraj_kod]["nazev"], uz.kraj_kod))],
                               [(f, kp) for _, f, kp, _ in d["subjekty"]], d["aktivita"], ekonomika, sbs, prah)
               + tabulky_mzdy(uz, srovnani, obor, kraje, mzdy) + [t10, t18, t11, t12])
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
            "ČSÚ, DataStat, výběry MZDCRRT1, MZDCRRT2, MZDRT2, MZDRT5 – zaměstnanci a průměrné hrubé měsíční mzdy",
            EUROSTAT_CITACE.format(datum=ekonomika.get("_stazeno", "–")),
            f"Eurostat, statistika podniků podle velikosti (sbs_sc_ovw) a kurz CZK/EUR (ert_bil_eur_a), staženo "
            f"{sbs.get('_stazeno', '–')}; použito pro modelové odhady – upraveno, za úpravy Eurostat neodpovídá.",
        ],
        "licence": {"nazev": "CC BY 4.0", "url": LICENCE_URL},
        "vygenerovano": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    # detektor zjištění (Blok 4 C) pracuje jen se zveřejněnými čísly tabulek
    from firemni_databaze.report_zjisteni import detekuj, tabulka_zjisteni
    zjisteni = detekuj({"meta": meta, "tabulky": tabulky})
    tabulky.append(tabulka_zjisteni(zjisteni))
    pouzite = {r.get("ukazatele", {}).get(sl["kod"]) or sl["ukazatel"] for t in tabulky for r in t["radky"] for sl in t["sloupce"]}
    meta["ukazatele"] = [{k: u.get(k) for k in ("kod", "nazev", "typ", "definice", "chybejici_hodnoty", "vyklad")}
                         for kod, u in katalog.items() if kod in pouzite]
    vysledek = {"meta": meta, "tabulky": tabulky, "zjisteni": zjisteni}
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


def soubor_zjisteni(vysledek: dict) -> dict:
    """Obsah zjisteni.json: zadání, pravidla detektoru a zjištění seřazená podle síly."""
    from firemni_databaze.report_zjisteni import MIN_PODIL_STRUKTURY, PRAH_ZJISTENI
    m = vysledek["meta"]
    return {"id_reportu": slug(vysledek), "obor": m["obor_popis"], "uzemi": m["uzemi"], "zadani": m["zadani"],
            "pravidla": {"prah_relativniho_rozdilu": PRAH_ZJISTENI, "min_podil_struktury_pct": MIN_PODIL_STRUKTURY,
                         "sila": "|hodnota / srovnání − 1|; divergence pořadí |p1 − p2| / (počet území − 1)"},
            "citace": m["citace"], "oznaceni": m["oznaceni"], "zjisteni": vysledek["zjisteni"]}


def uloz(vysledek: dict, interni: dict, adresar: Path) -> Path:
    from firemni_databaze.report_xlsx import zapis_xlsx

    cil = adresar / slug(vysledek)
    (cil / "_interni").mkdir(parents=True, exist_ok=True)
    (cil / "vysledek.json").write_text(json.dumps(vysledek, ensure_ascii=False, indent=1), encoding="utf-8")
    (cil / "vysledek.md").write_text(markdown(vysledek), encoding="utf-8")
    (cil / "zjisteni.json").write_text(json.dumps(soubor_zjisteni(vysledek), ensure_ascii=False, indent=1),
                                       encoding="utf-8")
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
    from firemni_databaze.report_vyklad import sablona_vykladu, soubor_vykladu
    vyklad = soubor_vykladu(slug(vysledek))
    if not vyklad.exists():     # rozhodnutí 12: výklad analytika začíná zástupným textem
        vyklad.parent.mkdir(parents=True, exist_ok=True)
        vyklad.write_text(sablona_vykladu(vysledek, slug(vysledek)), encoding="utf-8")
        print(f"Založen soubor výkladu analytika se zástupným textem: {vyklad}")
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
