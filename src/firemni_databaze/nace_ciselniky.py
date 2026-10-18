"""Číselníky CZ-NACE 2008 a CZ-NACE 2025 a převodník mezi nimi (ČSÚ).

Spuštění:
    python -m firemni_databaze.nace_ciselniky sestav [--adresar DIR]   # stáhne zdroje ČSÚ → ciselniky/nace/*.csv
    python -m firemni_databaze.nace_ciselniky nahraj                   # CSV z repozitáře → obor.nace_*

Zdroje (ověřeno 18. 10. 2026, robots.txt ani podmínky stažení nezakazují):
  * iSMS ČSÚ (apl2.czso.cz, robots.txt neexistuje) – klasifikace 80004 (CZ-NACE 2008)
    a 80143 (CZ-NACE 2025), všech 5 úrovní. Na iSMS odkazuje stránka ČSÚ ke CZ-NACE 2025.
  * csu.gov.cz/prevodniky-v105 – převodníky NACE Rev. 2 ↔ Rev. 2.1 (Eurostat, V1.05, úrovně 1–4)
    a převodník pro 5místné položky CZ-NACE 2008 ↔ 2025 (ČSÚ, 12/2025).
  * Pseudokódy RES (X/04 nezjištěno, Y/00 neuvedeno v přílohách ŽZ) podle dokumentace otevřených
    dat RES – v oficiální klasifikaci nejsou, RES je ale používá v obou verzích.
vdb.czso.cz (dřívější zdroj CZ_NACE_RES) má od října 2026 v robots.txt „User-agent: * / Disallow: /“,
proto se nepoužívá.

Kódy jsou bez teček a mezer, stejně jako v RES a ARES: sekce „F“, oddíl „41“, skupina „412“,
třída „4120“, podtřída „41201“ (národní, 5. místo „0“ = třída se dál nečlení).
Verze se ukládá u každého záznamu výslovně – stejný kód může v obou verzích znamenat něco jiného.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ADRESAR = Path(__file__).resolve().parents[2] / "ciselniky" / "nace"
SOUBOR_CISELNIK = "nace_ciselnik.csv"
SOUBOR_PREVODNIK = "nace_prevodnik.csv"
SOUBOR_A10 = "sekce2025_a10.csv"

ISMS_KLASIFIKACE = {2008: 80004, 2025: 80143}
PREVODNIKY = {
    "rev2_rev21": "https://csu.gov.cz/docs/107516/5c624607-9408-9c0b-9645-f6686a7f4b8d/"
                  "prevodnik_nace_rev_2_nace_rev_2_1_v1_05.xlsx?version=1.0",
    "rev21_rev2": "https://csu.gov.cz/docs/107516/2b851f87-f77c-23e9-eeda-f9d9d84dad5a/"
                  "prevodnik_nace_rev_2_1_nace_rev_2_v1_05.xlsx?version=1.0",
    "cz_5mist": "https://csu.gov.cz/docs/107516/1ad3222e-9681-77b4-ef20-d95fa4a112f0/"
                "prevodnik_5mistne_polozky_cz_nace_opravy_nazvu_202512.xlsx?version=1.0",
}
LIST_5MIST_2008 = "CZ-NACE 2008xCZ-NACE 2025-5míst"
LIST_5MIST_2025 = "CZ-NACE 2025xCZ-NACE 2008-5míst"

# Pseudokódy RES (docs/res_zdroj.md, kap. 4) – v obou verzích stejné, nejsou ekonomickou činností.
PSEUDOKODY = (
    ("X", 1, None, "Nezjištěno (pseudo-sekce RES)"),
    ("04", 2, "X", "Nezjištěno (pseudokód RES)"),
    ("Y", 1, None, "Neuvedeno v přílohách živnostenského zákona (pseudo-sekce RES)"),
    ("00", 2, "Y", "Výroba, obchod a služby neuvedené v přílohách 1 až 3 živnostenského zákona (pseudokód RES)"),
)

SLOUPCE_CISELNIK = ("verze", "kod", "uroven", "nazev", "nadrazeny_kod", "sekce", "oddil", "skupina", "trida",
                    "je_pseudokod", "platnost_od", "platnost_do", "zdroj")
SLOUPCE_PREVODNIK = ("kod_2008", "kod_2025", "uroven", "typ_vazby", "castecne", "zdroj")


def normalizuj_kod(hodnota) -> tuple[str, bool]:
    """'01.47.0 (částečně)' → ('01470', True); '41.2' → ('412', False); 'A' → ('A', False)."""
    text = str(hodnota).replace("\n", " ").strip()
    castecne = "částečně" in text
    text = text.split("(")[0].strip()
    return text.replace(".", "").replace(" ", ""), castecne


# ---------------------------------------------------------------------------
# Číselník
# ---------------------------------------------------------------------------

def radky_ciselniku(polozky: list[dict], verze: int, zdroj: str) -> list[dict]:
    """Položky exportu iSMS (chodnota, uroven, nadvaz, text, admplod, admnepo) + pseudokódy RES,
    doplněné o předky na úrovních 1–4."""
    podle_kodu: dict[str, dict] = {}
    for p in polozky:
        kod = p["chodnota"]
        if kod in podle_kodu:
            raise ValueError(f"CZ-NACE {verze}: duplicitní kód {kod}")
        podle_kodu[kod] = {"kod": kod, "uroven": int(p["uroven"]), "nadrazeny_kod": p.get("nadvaz") or None,
                           "nazev": p["text"], "platnost_od": p.get("admplod") or None,
                           "platnost_do": p.get("admnepo") or None, "zdroj": zdroj, "je_pseudokod": False}
    for kod, uroven, nadrazeny, nazev in PSEUDOKODY:
        if kod in podle_kodu:
            raise ValueError(f"CZ-NACE {verze}: pseudokód RES {kod} koliduje s oficiálním kódem")
        podle_kodu[kod] = {"kod": kod, "uroven": uroven, "nadrazeny_kod": nadrazeny, "nazev": nazev,
                           "platnost_od": None, "platnost_do": None, "je_pseudokod": True,
                           "zdroj": "pseudokód RES (dokumentace otevřených dat RES, ČSÚ)"}
    radky = []
    for kod, p in podle_kodu.items():
        predci: dict[int, str] = {}
        k = kod
        while k is not None:
            q = podle_kodu.get(k)
            if q is None:
                raise ValueError(f"CZ-NACE {verze}: položka {kod} má neznámého předka {k}")
            predci[q["uroven"]] = k
            k = q["nadrazeny_kod"]
        if 1 not in predci:
            raise ValueError(f"CZ-NACE {verze}: položka {kod} nemá sekci")
        radky.append({"verze": verze, **{s: p[s] for s in ("kod", "uroven", "nazev", "nadrazeny_kod")},
                      "sekce": predci[1], "oddil": predci.get(2), "skupina": predci.get(3),
                      "trida": predci.get(4), "je_pseudokod": p["je_pseudokod"],
                      "platnost_od": p["platnost_od"], "platnost_do": p["platnost_do"], "zdroj": p["zdroj"]})
    radky.sort(key=lambda r: (r["verze"], r["sekce"], r["kod"].ljust(5, " ")))
    return radky


# ---------------------------------------------------------------------------
# Převodník
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Par:
    kod_2008: str
    kod_2025: str
    uroven: int
    castecne: bool
    zdroj: str


def pary_eurostat(radky_rev2: list[tuple], radky_rev21: list[tuple]) -> list[Par]:
    """Úrovně 1–4 z obou směrů převodníku Eurostatu (sloupce: ID, kód, úroveň, název, kód, …).
    CZ-NACE 2008 = NACE Rev. 2 a CZ-NACE 2025 = NACE Rev. 2.1 až po třídu."""
    pary: dict[tuple[str, str], Par] = {}
    for radky, obraceny in ((radky_rev2, False), (radky_rev21, True)):
        for r in radky:
            if not isinstance(r[0], (int, float)) or r[1] is None or r[2] is None or r[4] is None:
                continue
            a, _ = normalizuj_kod(r[1])
            b, _ = normalizuj_kod(r[4])
            if "*" in (a, b):          # „bez vazby“ (Rev. 2.1 46.89 nemá předchůdce v Rev. 2)
                continue
            k08, k25 = (b, a) if obraceny else (a, b)
            zdroj = "Eurostat NACE Rev. 2 ↔ Rev. 2.1 V1.05"
            pary.setdefault((k08, k25), Par(k08, k25, int(r[2]), False, zdroj))
    return list(pary.values())


def pary_5mist(list_2008: list[tuple], list_2025: list[tuple]) -> list[Par]:
    """Podtřídy, které se národně člení (oba listy převodníku ČSÚ pro 5místné položky)."""
    pary: dict[tuple[str, str], Par] = {}
    zdroj = "ČSÚ převodník 5místných položek CZ-NACE 2008 ↔ 2025 (12/2025)"
    for radky, obraceny in ((list_2008, False), (list_2025, True)):
        for r in radky:
            if r[0] in (None, "ID") or r[1] is None or r[4] is None:
                continue
            a, ca = normalizuj_kod(r[1])
            b, cb = normalizuj_kod(r[4])
            k08, k25 = (b, a) if obraceny else (a, b)
            stary = pary.get((k08, k25))
            pary[(k08, k25)] = Par(k08, k25, 5, (stary.castecne if stary else False) or ca or cb, zdroj)
    return list(pary.values())


def pary_tridy_na_podtridy(pary4: list[Par], l5_2008: set[str], l5_2025: set[str]) -> list[Par]:
    """Podtřídy „xxxx0“ (třída se národně nečlení) v obou verzích: převod podle převodníku tříd.
    Kód „xxxx0“ existuje právě tehdy, když se třída nečlení (národní podtřídy nulou nekončí), takže
    pár se přidá vždy, když oba kódy existují. Převodník ČSÚ pro 5místné položky k nim přidá jen
    páry s podtřídami, které se národně člení (kód „xxxx0“ tam bývá jen dílčím zdrojem nebo cílem)."""
    vysledek = []
    for p in pary4:
        a, b = p.kod_2008 + "0", p.kod_2025 + "0"
        if a in l5_2008 and b in l5_2025:
            vysledek.append(Par(a, b, 5, p.castecne, "odvozeno z převodníku tříd (podtřída se národně nečlení)"))
    return vysledek


def typy_vazby(pary: list[Par]) -> list[dict]:
    """Typ vazby na každé úrovni: 1:1, 1:N (starý kód se dělí), N:1 (staré kódy se slučují), N:M."""
    cile, zdroje = defaultdict(set), defaultdict(set)
    for p in pary:
        cile[(p.uroven, p.kod_2008)].add(p.kod_2025)
        zdroje[(p.uroven, p.kod_2025)].add(p.kod_2008)
    radky = []
    for p in pary:
        n_cilu = len(cile[(p.uroven, p.kod_2008)])
        n_zdroju = len(zdroje[(p.uroven, p.kod_2025)])
        typ = {(True, True): "1:1", (False, True): "1:N", (True, False): "N:1", (False, False): "N:M"}[
            (n_cilu == 1, n_zdroju == 1)]
        radky.append({"kod_2008": p.kod_2008, "kod_2025": p.kod_2025, "uroven": p.uroven, "typ_vazby": typ,
                      "castecne": p.castecne, "zdroj": p.zdroj})
    radky.sort(key=lambda r: (r["uroven"], r["kod_2008"], r["kod_2025"]))
    return radky


def over_prevodnik(prevodnik: list[dict], ciselnik: list[dict]) -> list[str]:
    """Kódy převodníku, které nejsou v číselníku své verze na stejné úrovni (mají být žádné)."""
    znamy = {(r["verze"], r["kod"], r["uroven"]) for r in ciselnik}
    chyby = []
    for r in prevodnik:
        for verze, sloupec in ((2008, "kod_2008"), (2025, "kod_2025")):
            if (verze, r[sloupec], r["uroven"]) not in znamy:
                chyby.append(f"{sloupec}={r[sloupec]} (úroveň {r['uroven']}) není v CZ-NACE {verze}")
    return chyby


# ---------------------------------------------------------------------------
# Sestavení CSV a nahrání do databáze
# ---------------------------------------------------------------------------

def _xlsx_list(cesta: Path, nazev: str | None = None) -> list[tuple]:
    import openpyxl

    wb = openpyxl.load_workbook(cesta, read_only=True)
    ws = wb[nazev] if nazev else wb.worksheets[0]
    return list(ws.iter_rows(values_only=True))


def _zapis_csv(cesta: Path, sloupce: tuple, radky: list[dict]) -> None:
    with open(cesta, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=sloupce, lineterminator="\n")
        w.writeheader()
        for r in radky:
            w.writerow({k: ("" if r[k] is None else (str(r[k]).lower() if isinstance(r[k], bool) else r[k]))
                        for k in sloupce})


def stahni_zdroje(adresar: Path, k_datu: date) -> None:
    from firemni_databaze import res_zdroj as z

    for verze, kodcis in ISMS_KLASIFIKACE.items():
        z.stahni(z.url_ciselniku(kodcis, k_datu), adresar / f"isms_{kodcis}.csv")
    for nazev, url in PREVODNIKY.items():
        z.stahni(url, adresar / f"{nazev}.xlsx")


def sestav(adresar: Path, cil: Path = ADRESAR) -> tuple[list[dict], list[dict]]:
    ciselnik = []
    for verze, kodcis in ISMS_KLASIFIKACE.items():
        text = (adresar / f"isms_{kodcis}.csv").read_text(encoding="utf-8-sig")
        polozky = [{k: (v if v != "" else None) for k, v in r.items()} for r in csv.DictReader(io.StringIO(text))]
        ciselnik += radky_ciselniku(polozky, verze, f"ČSÚ iSMS, klasifikace {kodcis}")

    pary4 = pary_eurostat(_xlsx_list(adresar / "rev2_rev21.xlsx"), _xlsx_list(adresar / "rev21_rev2.xlsx"))
    pary5 = pary_5mist(_xlsx_list(adresar / "cz_5mist.xlsx", LIST_5MIST_2008),
                       _xlsx_list(adresar / "cz_5mist.xlsx", LIST_5MIST_2025))
    l5 = {v: {r["kod"] for r in ciselnik if r["verze"] == v and r["uroven"] == 5} for v in (2008, 2025)}
    pary_tridy = [p for p in pary4 if p.uroven == 4]
    prevodnik = typy_vazby(pary4 + pary5 + pary_tridy_na_podtridy(pary_tridy, l5[2008], l5[2025]))
    chyby = over_prevodnik(prevodnik, ciselnik)
    if chyby:
        raise ValueError("převodník neodpovídá číselníkům: " + "; ".join(chyby[:10]))

    cil.mkdir(parents=True, exist_ok=True)
    _zapis_csv(cil / SOUBOR_CISELNIK, SLOUPCE_CISELNIK, ciselnik)
    _zapis_csv(cil / SOUBOR_PREVODNIK, SLOUPCE_PREVODNIK, prevodnik)
    return ciselnik, prevodnik


def nacti_csv(cesta: Path) -> list[dict]:
    with open(cesta, encoding="utf-8", newline="") as f:
        return [{k: (v if v != "" else None) for k, v in r.items()} for r in csv.DictReader(f)]


def nahraj(conn, adresar: Path = ADRESAR) -> dict[str, int]:
    """CSV z repozitáře → obor.nace_ciselnik, obor.nace_prevodnik, obor.nace_sekce_a10.
    Idempotentní: tabulky se nahradí celé (žádné jiné tabulky na ně neodkazují cizím klíčem)."""
    tabulky = {
        "nace_ciselnik": (SOUBOR_CISELNIK, SLOUPCE_CISELNIK),
        "nace_prevodnik": (SOUBOR_PREVODNIK, SLOUPCE_PREVODNIK),
        "nace_sekce_a10": (SOUBOR_A10, None),
    }
    pocty = {}
    with conn.cursor() as cur:
        for tabulka, (soubor, _) in tabulky.items():
            radky = nacti_csv(adresar / soubor)
            sloupce = list(radky[0].keys())
            cur.execute(f"DELETE FROM obor.{tabulka}")
            cur.executemany(
                f"INSERT INTO obor.{tabulka} ({', '.join(sloupce)}) VALUES ({', '.join(['%s'] * len(sloupce))})",
                [tuple(r[s] for s in sloupce) for r in radky],
            )
            pocty[tabulka] = len(radky)
    conn.commit()
    return pocty


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="prikaz", required=True)
    s = sub.add_parser("sestav", help="stáhne zdroje ČSÚ a zapíše ciselniky/nace/*.csv")
    s.add_argument("--adresar", type=Path, help="už stažené zdroje (isms_80004.csv, isms_80143.csv, *.xlsx)")
    sub.add_parser("nahraj", help="nahraje CSV z repozitáře do schématu obor")
    args = parser.parse_args()

    if args.prikaz == "sestav":
        with tempfile.TemporaryDirectory(prefix="nace_") as tmp:
            adresar = args.adresar or Path(tmp)
            if not args.adresar:
                stahni_zdroje(adresar, date.today())
            ciselnik, prevodnik = sestav(adresar)
        for v in (2008, 2025):
            urovne = defaultdict(int)
            for r in ciselnik:
                if r["verze"] == v:
                    urovne[r["uroven"]] += 1
            print(f"CZ-NACE {v}: " + ", ".join(f"úroveň {u}: {n}" for u, n in sorted(urovne.items())))
        typy = defaultdict(int)
        for r in prevodnik:
            typy[(r["uroven"], r["typ_vazby"])] += 1
        print("převodník: " + ", ".join(f"{u}/{t}: {n}" for (u, t), n in sorted(typy.items())))
        return 0

    from firemni_databaze.db import get_engine

    raw = get_engine().raw_connection()
    try:
        for tabulka, n in nahraj(raw).items():
            print(f"  obor.{tabulka}: {n} řádků")
    finally:
        raw.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
