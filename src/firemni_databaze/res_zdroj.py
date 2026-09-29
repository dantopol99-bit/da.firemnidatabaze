"""Zdroje ČSÚ pro schéma res: otevřená data RES, číselníky a agregáty.

Jen čisté funkce bez databáze: stažení, otisk a počet řádků souboru,
kontrola hlavičky proti CSVW metadatům, převod číselníků na řádky tabulek.
Zápis do databáze dělá res_import.
"""

import csv
import email.utils
import hashlib
import io
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Otevřená data RES (produkt ČSÚ 140134-26)
# https://csu.gov.cz/produkty/registr-ekonomickych-subjektu-otevrena-data
# ---------------------------------------------------------------------------

RES_URL = "https://opendata.csu.gov.cz/soubory/od/od_org03/"

# Sloupce souborů přesně v pořadí podle CSVW metadat (…-metadata.json).
# Změní-li ČSÚ strukturu, import skončí chybou – schéma se musí upravit vědomě.
SLOUPCE = {
    "res_data.csv": (
        "ICO", "OKRESLAU", "DDATVZN", "DDATZAN", "ZPZAN", "DDATPAKT", "FORMA", "ROSFORMA",
        "KATPO", "NACE", "NACE2025", "ICZUJ", "FIRMA", "CISS2010", "KODADM", "TEXTADR",
        "PSC", "OBEC_TEXT", "COBCE_TEXT", "ULICE_TEXT", "TYPCDOM", "CDOM", "COR",
        "DATPLAT", "PRIZNAK",
    ),
    "res_pf_nace.csv": ("ICO", "ZDRUD", "KODCIS", "HODN", "DATPLAT", "DDATPAKT", "PRIZNAK"),
}
TABULKY = {"res_data.csv": "subjekt", "res_pf_nace.csv": "pf_nace"}
SLOUPCE_DATUM = {
    "res_data.csv": {"DDATVZN", "DDATZAN", "DDATPAKT", "DATPLAT"},
    "res_pf_nace.csv": {"DATPLAT", "DDATPAKT"},
}


def url_souboru(soubor: str) -> str:
    return RES_URL + soubor


def soubor_metadat(soubor: str) -> str:
    """res_data.csv → res_data-metadata.json"""
    return soubor.removesuffix(".csv") + "-metadata.json"


# ---------------------------------------------------------------------------
# Stahování
# ---------------------------------------------------------------------------

def stahni(url: str, cil: Path, pokusy: int = 4, timeout: int = 120) -> datetime | None:
    """Stáhne URL do souboru po blocích. Vrátí Last-Modified ze serveru
    (a nastaví ho jako čas změny souboru, jako `curl -R`)."""
    for pokus in range(pokusy):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as r, open(cil, "wb") as f:
                while blok := r.read(1 << 20):
                    f.write(blok)
                lm = r.headers.get("Last-Modified")
            posledni_zmena = email.utils.parsedate_to_datetime(lm) if lm else None
            if posledni_zmena:
                os.utime(cil, (posledni_zmena.timestamp(), posledni_zmena.timestamp()))
            return posledni_zmena
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if pokus == pokusy - 1:
                raise
            time.sleep(2 ** (pokus + 1))
    raise RuntimeError("nedosažitelné")


def stahni_text(url: str, timeout: int = 120) -> bytes:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read()


# ---------------------------------------------------------------------------
# Otisk, počet řádků, hlavička – jedním průchodem souboru
# ---------------------------------------------------------------------------

@dataclass
class SouhrnSouboru:
    sha256: str
    velikost_bajtu: int
    pocet_radku: int              # záznamy podle CSV parseru, bez hlavičky
    hlavicka: list[str]
    posledni_zmena: datetime      # čas změny souboru (po stažení = Last-Modified)


class _Hashujici(io.RawIOBase):
    """Čte soubor a průběžně počítá SHA-256 a velikost."""

    def __init__(self, f):
        self._f = f
        self.hash = hashlib.sha256()
        self.velikost = 0

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:
        n = self._f.readinto(b)
        if n:
            self.hash.update(memoryview(b)[:n])
            self.velikost += n
        return n


def souhrn_souboru(cesta: Path) -> SouhrnSouboru:
    """SHA-256 celého souboru a počet záznamů podle CSV parseru (nezávisle na
    databázi – slouží ke kontrole, že COPY načetl všechno)."""
    with open(cesta, "rb") as f:
        h = _Hashujici(f)
        text = io.TextIOWrapper(io.BufferedReader(h, 1 << 20), encoding="utf-8", newline="")
        cteni = csv.reader(text)
        hlavicka = next(cteni, [])
        pocet = sum(1 for _ in cteni)
        text.read()  # dočíst případný zbytek do otisku
    zmena = datetime.fromtimestamp(os.stat(cesta).st_mtime, tz=timezone.utc)
    return SouhrnSouboru(h.hash.hexdigest(), h.velikost, pocet, hlavicka, zmena)


def over_strukturu(soubor: str, hlavicka: list[str], metadata: dict) -> None:
    """Hlavička souboru i metadata musí odpovídat očekávaným sloupcům a typům."""
    ocekavane = list(SLOUPCE[soubor])
    sloupce_meta = metadata.get("tableSchema", {}).get("columns", [])
    podle_metadat = [s["name"] for s in sloupce_meta]
    if podle_metadat != ocekavane:
        raise ValueError(f"{soubor}: metadata ČSÚ mají jiné sloupce, než schéma res očekává: {podle_metadat}")
    if hlavicka != ocekavane:
        raise ValueError(f"{soubor}: hlavička souboru neodpovídá metadatům: {hlavicka}")
    datumove = {s["name"] for s in sloupce_meta if s.get("datatype") == "date"}
    if datumove != SLOUPCE_DATUM[soubor]:
        raise ValueError(f"{soubor}: metadata mají jiné datumové sloupce: {sorted(datumove)}")


# ---------------------------------------------------------------------------
# Číselníky ČSÚ
# ---------------------------------------------------------------------------

ISMS_EXPORT = "https://apl2.czso.cz/iSMS/do_cis_export"
VDB_CISELNIK = "https://vdb.czso.cz/opendata/ciselniky/polozky?kod="


def url_ciselniku(kodcis: int, k_datu: date, vazba: str | None = None) -> str:
    """CSV export číselníku (nebo jeho vazby) ze Statistického metainformačního systému ČSÚ."""
    parametry = {
        "kodcis": kodcis,
        "typdat": 1 if vazba else 0,
        "cisvaz": vazba or "",
        "datpohl": k_datu.strftime("%d.%m.%Y"),
        "cisjaz": 203,
        "format": 2,
        "separator": ",",
    }
    return ISMS_EXPORT + "?" + urllib.parse.urlencode(parametry)


@dataclass(frozen=True)
class Ciselnik:
    ciselnik: str        # klíč v res.cis_zdroj
    nazev: str
    tabulka: str         # cílová tabulka res.cis_*
    kodcis: int | None = None
    vazba: str | None = None
    vdb_kod: str | None = None

    def url(self, k_datu: date) -> str:
        if self.vdb_kod:
            return VDB_CISELNIK + self.vdb_kod
        return url_ciselniku(self.kodcis, k_datu, self.vazba)


CISELNIKY = (
    Ciselnik("CZ_NACE_RES", "CZ-NACE pro RES (klasifikace 80004)", "cis_nace", vdb_kod="CZ_NACE_RES"),
    Ciselnik("CZ_NACE_RES2025", "CZ-NACE 2025 pro RES (klasifikace 80143)", "cis_nace", vdb_kod="CZ_NACE_RES2025"),
    Ciselnik("100", "Kraj (CZ-NUTS 3 a kód RÚIAN)", "cis_kraj", kodcis=100),
    Ciselnik("109", "Okres (OKRES_LAU)", "cis_okres", kodcis=109),
    Ciselnik("109-108", "Vazba okres → kraj (109 → 108)", "cis_okres", kodcis=109, vazba="108_210"),
    Ciselnik("56", "Právní forma statistická (FORMA)", "cis_pravni_forma", kodcis=56),
    Ciselnik("149", "Právní forma registr osob (ROSFORMA)", "cis_pravni_forma", kodcis=149),
    Ciselnik("579", "Kategorie počtu pracovníků (KATPO)", "cis_katpo", kodcis=579),
    Ciselnik("572", "Způsob zániku (ZPZAN)", "cis_zpusob_zaniku", kodcis=572),
    Ciselnik("564", "Zdroj údaje (ZDRUD)", "cis_zdroj_udaje", kodcis=564),
)


def nacti_csv(obsah: bytes) -> list[dict]:
    """CSV z ČSÚ → seznam slovníků s malými názvy sloupců (VDB je má velkými)."""
    text = obsah.decode("utf-8-sig")
    return [{k.lower(): (v if v != "" else None) for k, v in r.items()} for r in csv.DictReader(io.StringIO(text))]


def _datum(hodnota: str | None) -> date | None:
    return date.fromisoformat(hodnota) if hodnota else None


def radky_nace(polozky: list[dict], klasifikace: int) -> list[dict]:
    """Položky CZ-NACE doplněné o sekci/oddíl/skupinu/třídu podle hierarchie
    číselníku (nadvaz). Úroveň 1 sekce, 2 oddíl, 3 skupina, 4 třída, 5 podtřída."""
    podle_kodu = {}
    for p in polozky:
        if p["chodnota"] in podle_kodu:
            raise ValueError(f"CZ-NACE {klasifikace}: duplicitní kód {p['chodnota']}")
        podle_kodu[p["chodnota"]] = p
    radky = []
    for kod, p in podle_kodu.items():
        predci: dict[int, str] = {}
        k = kod
        while k is not None:
            q = podle_kodu.get(k)
            if q is None:
                raise ValueError(f"CZ-NACE {klasifikace}: položka {kod} má neznámého předka {k}")
            predci[int(q["uroven"])] = k
            k = q["nadvaz"]
        if 1 not in predci:
            raise ValueError(f"CZ-NACE {klasifikace}: položka {kod} nemá sekci")
        radky.append({
            "klasifikace": klasifikace,
            "kod": kod,
            "uroven": int(p["uroven"]),
            "nadrazeny_kod": p["nadvaz"],
            "nazev": p["text"],
            "zkraceny_nazev": p["zkrtext"],
            "sekce": predci[1],
            "oddil": predci.get(2),
            "skupina": predci.get(3),
            "trida": predci.get(4),
            "je_pseudokod": predci[1] in ("X", "Y"),
            "platnost_od": _datum(p["admplod"]),
            "platnost_do": _datum(p["admnepo"]),
        })
    return radky


def radky_kraj(polozky: list[dict]) -> list[dict]:
    return [{
        "kod": p["cznuts"],
        "nazev": p["text"],
        "zkratka": p.get("zkrkraj"),
        "kod_csu": int(p["chodnota"]),
        "kod_ruian": int(p["kod_ruian"]) if p.get("kod_ruian") else None,
        "platnost_od": _datum(p["admplod"]),
        "platnost_do": _datum(p["admnepo"]),
    } for p in polozky]


def radky_okres(polozky: list[dict], vazby: list[dict]) -> list[dict]:
    kraj = {}
    for v in vazby:
        if v["kodcis1"] != "109" or v["kodcis2"] != "108":
            raise ValueError(f"neočekávaná vazba číselníků {v['kodcis1']} → {v['kodcis2']}")
        kraj[v["chodnota1"]] = v["chodnota2"]
    chybi = [p["chodnota"] for p in polozky if p["chodnota"] not in kraj]
    if chybi:
        raise ValueError(f"okresy bez vazby na kraj: {chybi}")
    return [{
        "kod": p["chodnota"],
        "nazev": p["text"],
        "kraj_kod": kraj[p["chodnota"]],
        "platnost_od": _datum(p["admplod"]),
        "platnost_do": _datum(p["admnepo"]),
    } for p in polozky]


def radky_jednoduche(polozky: list[dict]) -> list[dict]:
    return [{
        "kod": p["chodnota"],
        "nazev": p["text"],
        "platnost_od": _datum(p["admplod"]),
        "platnost_do": _datum(p["admnepo"]),
    } for p in polozky]


def radky_pravni_forma(polozky: list[dict], ciselnik: int) -> list[dict]:
    return [{
        "ciselnik": ciselnik,
        "kod": p["chodnota"],
        "nazev": p["text"],
        "zkraceny_nazev": p["zkrtext"],
        "platnost_od": _datum(p["admplod"]),
        "platnost_do": _datum(p["admnepo"]),
    } for p in polozky]


# ---------------------------------------------------------------------------
# Agregáty ČSÚ (DataStat) – počty subjektů po krajích a odvětvích
# ---------------------------------------------------------------------------

DATASTAT_VYBER = "RES02QT1"   # Ekonomické subjekty podle převažující činnosti CZ-NACE - data za ČR a kraje
DATASTAT_KATALOG = "https://data.csu.gov.cz/api/katalog/v1/vybery/"
DATASTAT_DATA = "https://data.csu.gov.cz/api/dotaz/v1/data/vybery/"


def url_datastat(vyber: str) -> str:
    return DATASTAT_DATA + vyber + "?" + urllib.parse.urlencode(
        {"format": "CSV", "rozsah": "CELY_VYBER", "kodCiselniku": "true"})


def radky_agregatu(obsah: bytes, definice: dict) -> list[dict]:
    """CSV z DataStatu → řádky res.csu_agregat. Kódy ukazatelů podle definice výběru."""
    vyber = definice["vyber"]
    ukazatele = {u["nazev"]: u["kod"] for u in vyber["ukazatele"]}
    dimenze = {d["typDimenzeKod"]: d for d in vyber["variantyDimenze"]}
    uz, nace, cas = dimenze["VUZEMI"], dimenze["CZNACE"], dimenze["REF_CAS"]
    radky = []
    for r in csv.DictReader(io.StringIO(obsah.decode("utf-8-sig"))):
        if r["Hodnota"] in ("", None):
            continue
        radky.append({
            "vyber": vyber["kod"],
            "ukazatel_kod": ukazatele[r["Ukazatel"]],
            "ukazatel": r["Ukazatel"],
            "uzemi_kod": r[uz["kod"] + ".Polozka"],
            "uzemi": r[uz["nazev"]],
            "nace_kod": r[nace["kod"] + ".Polozka"],
            "nace": r[nace["nazev"]],
            "obdobi": r[cas["kod"] + ".Polozka"],
            "hodnota": float(r["Hodnota"]),
        })
    return radky
