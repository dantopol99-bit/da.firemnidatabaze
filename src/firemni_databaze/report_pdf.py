"""Sazba Oborově-regionálního reportu do PDF (Typst) z výstupu JSON výpočetní vrstvy.

Spuštění:
    python -m firemni_databaze.report_pdf reporty/vystupy/F__CZ051__2026-09-15
    python -m firemni_databaze.report_pdf <adresář> --vystup reporty/ukazky --vyklad-schvalen

Postup (každý krok, který selže, sazbu zastaví):
  1. kontrola výstupu Bloku 2 (report_kontrola.zkontroluj),
  2. data pro šablonu: všechna čísla se jen převezmou z vysledek.json a naformátují
     (šablona reporty/sablona/report.typ nic nepočítá); výklad má dvě vrstvy (rozhodnutí 12):
     „co je vidět“ a zjištění detektoru píše stroj (report_vyklad), „proč“ a „co z toho
     plyne“ analytik do reporty/vyklad/<id_reportu>.md,
  3. grafy výhradně z knihovny report_grafy,
  4. kontrola čísel ve výkladu ještě před sazbou,
  5. typst compile (fonty jen z reporty/sablona/fonty),
  6. kontrola konzistence PDF: každé číslo v textu PDF (včetně výkladu) musí být
     v JSON i XLSX; při nesouladu se PDF smaže a skončí se chybou.
Dokud výklad neschválí člověk (--vyklad-schvalen), nese zápatí „KONCEPT – výklad k revizi“.
--vyklad-schvalen selže, dokud soubor analytika chybí nebo obsahuje zástupný text.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from firemni_databaze import report_grafy as g
from firemni_databaze import report_vyklad as vy
from firemni_databaze.report_cestina import lokativ
from firemni_databaze.report_kontrola import ZAKAZANA_SLOVA, cisla_v_textu, povolena_cisla, zkontroluj, zkontroluj_pdf
from firemni_databaze.report_vyklad import Vstup, cz

KOREN = Path(__file__).resolve().parents[2]
SABLONA = KOREN / "reporty" / "sablona" / "report.typ"
FONTY = KOREN / "reporty" / "sablona" / "fonty"
UKAZKY = KOREN / "reporty" / "ukazky"


class ChybaSazby(RuntimeError):
    pass


def _datum_cz(iso: str) -> str:
    r, m, d = iso.split("-")
    return f"{int(d)}. {int(m)}. {r}"


# ---------------------------------------------------------------------------
# Tabulky a grafy z JSON
# ---------------------------------------------------------------------------

def tabulka(t: dict, pismeno: str, zdroj: str, sloupce: list[str] | None = None) -> dict:
    """Tabulka z JSON beze změny hodnot; jen formát čísel a výběr sloupců."""
    sl = [s for s in t["sloupce"] if sloupce is None or s["kod"] in sloupce]
    ma_poznamku = any(r.get("poznamka") for r in t["radky"])
    radky = []
    for r in t["radky"]:
        bunky = [r["popis"]] + [cz(r["hodnoty"].get(s["kod"])) for s in sl]
        if ma_poznamku:
            bunky.append(r.get("poznamka") or "")
        radky.append({"bunky": bunky, "zvyrazneni": r["typ"] in ("celkem", "mezisoucet")})
    return {
        "typ": "tabulka", "pismeno": pismeno, "nazev": t["nazev"],
        "zahlavi": ["Položka"] + [s["nazev"] for s in sl] + (["Poznámka"] if ma_poznamku else []),
        "radky": radky, "poznamky": t["poznamky"], "zdroj": zdroj,
        "cisel": len(sl),
    }


def _role(popis: str, uzemi: str, srovnani: set[str]) -> str:
    return "uzemi" if popis == uzemi else "srovnani" if popis in srovnani else "jine"


class Sestava:
    """Přiděluje písmena tabulkám a grafům v pořadí osnovy."""

    def __init__(self, adresar_grafu: Path):
        self.adresar = adresar_grafu
        self.tab, self.graf = 0, 0
        self.L: dict[str, str] = {}

    def pismeno_tab(self, klic: str) -> str:
        p = chr(ord("A") + self.tab)
        self.tab += 1
        self.L[klic] = f"tab. {p}"
        return p

    def pismeno_graf(self, klic: str) -> str:
        p = chr(ord("A") + self.graf)
        self.graf += 1
        self.L[klic] = f"graf {p}"
        return p


def sestav_data(vysledek: dict, adresar: Path, koncept: bool, vyklad_analytika: dict | None = None) -> dict:
    v = Vstup(vysledek)
    meta = v.meta
    datum = _datum_cz(meta["zadani"]["datum_snimku"])
    zdroj_res = f"Zdroj: ČSÚ, Registr ekonomických subjektů, stav k {datum}; vlastní výpočet."
    zdroj_ds = f"Zdroj: ČSÚ, DataStat; RES stav k {datum}; vlastní výpočet."
    s = Sestava(adresar)
    uzemi_nazev = v.uzemi["nazev"]
    kraj_uz = next((r["popis"] for r in v.radky("T02_srovnani") if r["promenna"] == f"obor@kraj:{v.uzemi['kraj']}"),
                   None) if v.uzemi["kraj"] else None
    kraj_uz = (kraj_uz or uzemi_nazev).replace(" (zkoumané území)", "")
    srov = {r["popis"] for r in v.radky("T02_srovnani")} - {"Česko", uzemi_nazev + " (zkoumané území)", kraj_uz}

    kapitoly = []
    odchylky = [f"{t['nazev']}: nezveřejněno – {t['duvod']}." for t in vysledek["tabulky"] if not t["zverejneno"]]

    # --- Postavení území ------------------------------------------------------------
    obsah = []
    obsah.append(tabulka(v.tab["T01_zakladni"], s.pismeno_tab("T01"), zdroj_res))
    obsah.append(tabulka(v.tab["T02_srovnani"], s.pismeno_tab("T02"), zdroj_res))
    kraje = v.radky("T03_kraje")
    celkem_cr = next((r for r in v.radky("T03_kraje", "celkem")), None)
    if kraje and celkem_cr:
        p = s.pismeno_graf("g_hustota")
        polozky = [{"popis": r["popis"], "hodnota": r["hodnoty"]["hustota"], "role": _role(r["popis"], kraj_uz, srov)}
                   for r in sorted(kraje, key=lambda r: -r["hodnoty"]["hustota"])]
        obsah.append({"typ": "graf", "pismeno": p, "soubor": str(g.poradi(
            polozky, adresar / "g_hustota.svg", "Registrované subjekty oboru na 1 000 obyvatel",
            referencni=("Česko", celkem_cr["hodnoty"]["hustota"]), mista=1)),
            "nazev": "Kraje podle hustoty registrovaných subjektů oboru na 1 000 obyvatel", "zdroj": zdroj_res})
        p = s.pismeno_graf("g_lq")
        polozky = [{"popis": r["popis"], "hodnota": r["hodnoty"]["lq"], "role": _role(r["popis"], kraj_uz, srov)}
                   for r in sorted(kraje, key=lambda r: -r["hodnoty"]["lq"])]
        obsah.append({"typ": "graf", "pismeno": p, "soubor": str(g.index_srovnani(
            polozky, adresar / "g_lq.svg", "Lokalizační koeficient (1 = průměr ČR)")),
            "nazev": "Kraje podle lokalizačního koeficientu oboru", "zdroj": zdroj_res})
    if v.t("T03_kraje"):
        obsah.append(tabulka(v.tab["T03_kraje"], s.pismeno_tab("T03"), zdroj_res))
    if v.t("T04_okresy"):
        obsah.append(tabulka(v.tab["T04_okresy"], s.pismeno_tab("T04"), zdroj_res))
    kapitoly.append({"nadpis": "Postavení území", "klic": "postaveni", "obsah": obsah})

    # --- Struktura ------------------------------------------------------------------
    obsah = []
    if v.t("T05_fo_po"):
        casti = [{"popis": r["popis"], "podil": r["hodnoty"]["podil"]} for r in v.radky("T05_fo_po")]
        p = s.pismeno_graf("g_fopo")
        obsah.append({"typ": "graf", "pismeno": p, "soubor": str(g.skladba(casti, adresar / "g_fopo.svg")),
                      "nazev": "Registrované subjekty oboru podle typu osoby", "zdroj": zdroj_res, "maly": True})
        obsah.append(tabulka(v.tab["T05_fo_po"], s.pismeno_tab("T05"), zdroj_res))
    if v.t("T13_bench_fo_po"):
        obsah.append(tabulka(v.tab["T13_bench_fo_po"], s.pismeno_tab("T13"), zdroj_res))
    if v.t("T06_pravni_forma"):
        obsah.append(tabulka(v.tab["T06_pravni_forma"], s.pismeno_tab("T06"), zdroj_res))
    if v.t("T14_bench_pravni_forma"):
        obsah.append(tabulka(v.tab["T14_bench_pravni_forma"], s.pismeno_tab("T14"), zdroj_res))
    for kod, klic, nazev, kod_b in (
            ("T07_velikost_fo", "g_vel_fo", "Velikostní profil fyzických osob (podíl, %)", "T15_bench_velikost_fo"),
            ("T08_velikost_po", "g_vel_po", "Velikostní profil právnických osob (podíl, %)", "T16_bench_velikost_po")):
        if v.t(kod):
            kat = [{"popis": r["popis"], "podil": r["hodnoty"]["podil"],
                    "zvlastni": r["popis"] == "Neuvedeno" or r["typ"] == "ostatni"}
                   for r in v.radky(kod, None) if r["typ"] in ("polozka", "ostatni")]
            p = s.pismeno_graf(klic)
            obsah.append({"typ": "graf", "pismeno": p, "soubor": str(g.rozlozeni(kat, adresar / f"{klic}.svg")),
                          "nazev": nazev + " – „Neuvedeno“ a „ostatní“ šrafovaně", "zdroj": zdroj_res})
            obsah.append(tabulka(v.tab[kod], s.pismeno_tab(kod[:3]), zdroj_res))
        if v.t(kod_b):
            obsah.append(tabulka(v.tab[kod_b], s.pismeno_tab(kod_b[:3]), zdroj_res))
    if v.t("T09_vekova_struktura"):
        kat = [{"popis": r["popis"], "podil": r["hodnoty"]["podil"], "zvlastni": r["typ"] == "ostatni"}
               for r in v.radky("T09_vekova_struktura", None) if r["typ"] in ("polozka", "ostatni")]
        p = s.pismeno_graf("g_vek")
        obsah.append({"typ": "graf", "pismeno": p, "soubor": str(g.rozlozeni(kat, adresar / "g_vek.svg")),
                      "nazev": "Věková struktura existujících subjektů (podíl, %)", "zdroj": zdroj_res})
        obsah.append(tabulka(v.tab["T09_vekova_struktura"], s.pismeno_tab("T09"), zdroj_res))
    if v.t("T17_bench_vekova_struktura"):
        obsah.append(tabulka(v.tab["T17_bench_vekova_struktura"], s.pismeno_tab("T17"), zdroj_res))
    kapitoly.append({"nadpis": "Struktura", "klic": "struktura", "obsah": obsah})

    # --- Dynamika území a kontext ČR -------------------------------------------------
    obsah = []
    t11 = v.radky("T11_dynamika_csu")
    if t11:
        roky = {}
        for r in t11:
            rok, _, druh = r["popis"].partition(" – ")
            poz = r.get("poznamka") or ""
            roky.setdefault(rok, {"rok": rok})[druh] = r["hodnoty"]["celkem"]
            roky[rok]["neuplny"] = roky[rok].get("neuplny") or poz.split(";")[0].endswith(" čtvrtletí")
            roky[rok]["mimoradny_zanik"] = roky[rok].get("mimoradny_zanik") or "mimořádný" in poz
        p = s.pismeno_graf("g_dyn")
        obsah.append({"typ": "graf", "pismeno": p, "soubor": str(g.vznik_zanik(list(roky.values()), adresar / "g_dyn.svg")),
                      "nazev": f"Vzniklé a zaniklé ekonomické subjekty {v.v_uzemi} – všechny obory",
                      "zdroj": "Zdroj: ČSÚ, DataStat, RES05; " + f"RES stav k {datum}."})
        obsah.append(tabulka(v.tab["T11_dynamika_csu"], s.pismeno_tab("T11"), "Zdroj: ČSÚ, DataStat, RES05."))
    if v.t("T10_zaniky_po"):
        obsah.append(tabulka(v.tab["T10_zaniky_po"], s.pismeno_tab("T10"), zdroj_res))
    t18 = v.radky("T18_mira_zaniku_po")
    if t18:
        uzemi_t18 = list(dict.fromkeys(r["uzemi"] for r in t18))
        roky = sorted({r["rok"] for r in t18})
        def rada(kod_u, sl, roky_):
            radky_u = {r["rok"]: r for r in t18 if r["uzemi"] == kod_u}
            popis = radky_u[roky[0]]["popis"].rsplit(" – ", 1)[0]
            role = "uzemi" if kod_u == v.uzemi["kod"] else "cr" if kod_u == "CZ" else "srovnani"
            return {"popis": popis, "role": role, "body": [(y, radky_u[y]["hodnoty"][sl]) for y in roky_]}
        panely = [{"nazev": "Za celý rok", "rady": [rada(k, "mira", roky[:-1]) for k in uzemi_t18]},
                  {"nazev": f"Za období {v.tab['T18_mira_zaniku_po']['obdobi']}",
                   "rady": [rada(k, "mira_obd", roky) for k in uzemi_t18]}]
        p = s.pismeno_graf("g_zanik")
        obsah.append({"typ": "graf", "pismeno": p, "soubor": str(g.miry_v_case(panely, adresar / "g_zanik.svg",
                                                                             "Míra zániku PO (%)")),
                      "nazev": "Míra zániku právnických osob v oboru – zkoumané území, ČR a srovnávací kraje",
                      "zdroj": zdroj_res + " Chybějící bod = pod prahem."})
        obsah.append(tabulka(v.tab["T18_mira_zaniku_po"], s.pismeno_tab("T18"), zdroj_res))
    t12 = v.radky("T12_demografie_cr")
    if t12:
        panely = []
        for forma, nazev in (("FO", "Podniky fyzických osob"), ("PO", "Podniky právnických osob")):
            radky = [r for r in t12 if r["popis"].endswith(f"podniky {forma}")]
            rady = []
            if radky[0]["hodnoty"].get("obor_mira_vzniku") is not None:
                rady.append({"popis": "odvětví oboru", "hlavni": True,
                             "body": [(r["popis"].split(" – ")[0], r["hodnoty"]["obor_mira_vzniku"]) for r in radky]})
            rady.append({"popis": "všechna odvětví", "hlavni": False,
                         "body": [(r["popis"].split(" – ")[0], r["hodnoty"]["cr_mira_vzniku"]) for r in radky]})
            panely.append({"nazev": nazev, "rady": rady})
        p = s.pismeno_graf("g_miry")
        obsah.append({"typ": "graf", "pismeno": p, "soubor": str(g.miry_v_case(panely, adresar / "g_miry.svg", "Míra vzniků (%)")),
                      "nazev": "Míra vzniků podniků v ČR – kontext (jednotka podnik, ne registrovaný subjekt)",
                      "zdroj": "Zdroj: ČSÚ, DataStat, RESDP00 (demografie podniků)."})
        obsah.append(tabulka(v.tab["T12_demografie_cr"], s.pismeno_tab("T12"), "Zdroj: ČSÚ, DataStat, RESDP00."))
    kapitoly.append({"nadpis": "Dynamika území a kontext ČR", "klic": "dynamika", "obsah": obsah})

    # --- výklad (po přidělení písmen) --------------------------------------------------
    L = {k: s.L.get(k, "příloha") for k in
         [f"T{i:02d}" for i in range(1, 20)]
         + ["g_dyn", "g_fopo", "g_hustota", "g_lq", "g_miry", "g_vek", "g_vel_fo", "g_vel_po", "g_zanik"]}
    for k in kapitoly:
        k["vyklad"] = {"postaveni": vy.postaveni, "struktura": vy.struktura, "dynamika": vy.dynamika}[k["klic"]](v, L)
        if vyklad_analytika is None:
            k["vyklad"].append(vy._blok("proč", "Výklad analytika zatím chybí."))
        else:
            k["vyklad"] += vyklad_analytika.get(k["klic"], [])

    # --- shrnutí (rozhodnutí 11: počet, LQ, hustota, pořadí) ------------------------
    cr = next((r for r in v.radky("T02_srovnani") if r["promenna"] == "obor@CZ"), None)
    dlazdice = [{"popis": "Registrované subjekty", "hodnota": cz(v.t01("REG_POCET")),
                 "pozn": f"{cz(v.t01('REG_PODIL_CR'))} % oboru v ČR" if v.t01("REG_PODIL_CR") is not None else "Česko"}]
    if v.t01("LQ") is not None:
        dlazdice.append({"popis": "Lokalizační koeficient", "hodnota": cz(v.t01("LQ")), "pozn": "1 = průměr ČR"})
    if v.t01("HUSTOTA") is not None:
        dlazdice.append({"popis": "Na 1 000 obyvatel", "hodnota": cz(v.t01("HUSTOTA")),
                         "pozn": f"Česko {cz(cr['hodnoty']['hustota'])}" if cr else ""})
    if v.t01("PORADI_POCET") is not None:
        dlazdice.append({"popis": v.t01_popis("PORADI_POCET").replace(" podle počtu", ""),
                         "hodnota": f"{cz(v.t01('PORADI_POCET'))}.",
                         "pozn": f"podle hustoty {cz(v.t01('PORADI_HUSTOTA'))}." if v.t01("PORADI_HUSTOTA") else "podle počtu"})
    # body shrnutí píše analytik (rozhodnutí 12, rozšíření); dlaždice a varování jsou strojové
    body = [b["text"] for b in (vyklad_analytika or {}).get("shrnuti", [])]
    if not body:
        body = ["Shrnutí analytika zatím chybí."]
    shrnuti = {"dlazdice": dlazdice, "body": body, "varovani": meta["varovani"]}

    # --- metodika --------------------------------------------------------------------
    pr = meta["pravidla"]
    spolehlivost = v.t01("SPOLEHLIVOST_JEN_SEKCE")
    metodika = {
        "populace": meta["populace"].capitalize() + ".",
        "klasifikace": meta["klasifikace"] + ".",
        "pravidla": [
            f"Čísla pod prahem {cz(pr['prah'])} registrovaných subjektů se nezveřejňují; v každém členění se slučují "
            f"do řádku „ostatní“ a je-li „ostatní“ samo pod prahem, přidá se k němu další nejmenší položka. Skryté "
            f"číslo nelze dopočítat ze součtů ani z jiné tabulky (ověřeno výpočtem).",
            f"Report se nevydá pro obor a území s méně než {cz(pr['min_rozsah'])} registrovanými subjekty.",
            f"Spolehlivost zařazení: podíl subjektů zařazených jen do sekce oboru vůči počtu oboru; nad "
            f"{cz(pr['prah_spolehlivosti_pct'])} % nese report varování."
            + (f" Pro toto zadání: {cz(spolehlivost)} % ({L['T01']})." if spolehlivost is not None else ""),
            "Hlavní sdělení nesou počet, lokalizační koeficient, hustota a pořadí; velikostní profil je jen ve "
            "strukturní kapitole, vždy s podílem „Neuvedeno“.",
            "Výklad má dvě vrstvy: „co je vidět“ a zjištění detektoru píše stroj (jen věcný popis zveřejněných čísel), "
            "„proč to tak může být“ a „co z toho plyne“ píše analytik. Na oba texty platí kontrola čísel.",
            "Zjištění: síla je relativní rozdíl |hodnota / srovnání − 1| (u pořadí rozdíl pořadí dělený počtem území "
            "bez jednoho); zjištění se řadí podle síly. Rozdíl pod 3 % relativně se nehlásí a popisuje se jako "
            "„srovnatelné“. Nejsilnější zjištění jsou v kapitolách, všechna v příloze. Shrnutí na straně 2 píše "
            "analytik, dlaždice jsou strojové.",
            "Srovnání struktury s ČR a srovnávacími kraji: týž obor, položky podle zkoumaného území; práh a "
            "slučování platí pro každé území zvlášť.",
        ],
        "varovani": meta["varovani"],
        "omezeni": [
            "Počty jsou registrované subjekty, nikoli subjekty s činností; podíl se zjištěnou aktivitou uvádí ČSÚ "
            "jen souhrnně za kraj.",
            "Území určuje sídlo subjektu, ne místo činnosti; provozovny v datech nejsou.",
            "Obor určuje jediná převažující činnost; subjekty zařazené jen do sekce a subjekty s neurčeným oborem "
            "se uvádějí zvlášť.",
            "Kategorie počtu zaměstnanců „Neuvedeno“ se neslučuje s „bez zaměstnanců“; u právnických osob znamená "
            "hlavně nehlášené zaměstnance.",
            "Zaniklé fyzické osoby mají v otevřených datech jen IČO a datum zániku, proto zánik v oboru lze sledovat "
            "jen u právnických osob; dynamiku oboru za kraj ani okres ČSÚ nepublikuje.",
            "Demografie podniků ČSÚ používá jinou jednotku (aktivní podnik) a je jen za ČR – slouží jen jako kontext.",
            "Míra zániku PO: jen právnické osoby a jen okno let, které RES ještě uchovává (zaniklé subjekty jsou "
            "v RES 4 roky po zániku); stav k 1. 1. je rekonstruován z jednoho snímku, obor a sídlo jsou podle "
            "snímku. Neúplný poslední rok se srovnává za stejné období roku.",
        ],
        "ukazatele": [{"kod": u["kod"], "nazev": u["nazev"], "definice": u["definice"]} for u in meta["ukazatele"]],
        "zdroje": [meta["citace"]] + meta["dalsi_zdroje"],
        "licence": f"Licence {meta['licence']['nazev']}: {meta['licence']['url']}",
        "oznaceni": meta["oznaceni"],
    }
    return {
        "koncept": koncept,
        "fonty": str(FONTY),
        "titul": {
            "obor": meta["obor_popis"], "uzemi": uzemi_nazev,
            "typ_uzemi": {"CR": "Česko", "KRAJ": "kraj", "OKRES": "okres"}[v.uzemi["typ"]],
            "datum": datum, "srovnani": sorted(srov), "varovani": meta["varovani"],
            "citace": meta["citace"], "oznaceni": meta["oznaceni"], "klasifikace": meta["klasifikace"],
        },
        "zapati": f"ČSÚ, RES, stav k {datum} · CC BY 4.0 · {meta['oznaceni']}",
        "shrnuti": shrnuti,
        "kapitoly": kapitoly,
        "metodika": metodika,
        "zjisteni": vy.zjisteni_priloha(v, L),
        "odchylky": odchylky or ["Žádné – všechny kapitoly mají údaje."],
    }


def texty_dat(data: dict):
    """Všechny textové řetězce, které šablona vysází (pro kontrolu čísel před sazbou)."""
    if isinstance(data, str):
        yield data
    elif isinstance(data, dict):
        for k, v in data.items():
            if k not in ("soubor", "fonty", "koncept", "pismeno", "cisel", "zvyrazneni", "klic", "typ", "hypoteza", "druh"):
                yield from texty_dat(v)
    elif isinstance(data, list):
        for v in data:
            yield from texty_dat(v)


# ---------------------------------------------------------------------------
# Sazba
# ---------------------------------------------------------------------------

def vysazej(adresar_vysledku: Path, cil: Path, koncept: bool = True, adresar_vykladu: Path = vy.VYKLAD) -> Path:
    """koncept=False (výklad schválen) vyžaduje hotový soubor analytika bez zástupného textu."""
    chyby = zkontroluj(adresar_vysledku)
    if chyby:
        raise ChybaSazby("výstup výpočetní vrstvy neprošel kontrolou: " + "; ".join(chyby[:5]))
    vysledek = json.loads((adresar_vysledku / "vysledek.json").read_text(encoding="utf-8"))
    from firemni_databaze.report import slug
    soubor = vy.soubor_vykladu(slug(vysledek), adresar_vykladu)
    stav, vyklad_analytika = vy.nacti_vyklad_analytika(soubor)
    if not koncept and stav != "hotovy":
        prazdne = [vy.ODDILY[k] for k, b in vyklad_analytika.items() if not b]
        raise ChybaSazby(f"výklad nelze označit jako schválený: soubor analytika {soubor} "
                         + ("chybí" if stav == "chybi" else f"obsahuje „{vy.ZASTUPNY_TEXT}“ nebo prázdný oddíl"
                            + (f" ({', '.join(prazdne)})" if prazdne else "")))
    for bloky in vyklad_analytika.values():
        for b in bloky:
            if ZAKAZANA_SLOVA.search(b["text"]):
                raise ChybaSazby(f"zakázané slovo ve výkladu analytika (rozhodnutí 1): {b['text'][:80]!r}")
    povolena = povolena_cisla(adresar_vysledku)
    cil.mkdir(parents=True, exist_ok=True)
    pdf = cil / "report.pdf"
    with tempfile.TemporaryDirectory(prefix="sazba_") as tmp:
        tmp = Path(tmp)
        data = sestav_data(vysledek, tmp, koncept, vyklad_analytika if stav != "chybi" else None)
        # kontrola čísel v textech ještě před sazbou (rychlé selhání)
        spatne = sorted({c for t in texty_dat(data) for c in cisla_v_textu(t)} - povolena)
        if spatne:
            raise ChybaSazby(f"čísla v textu reportu, která nejsou v JSON a XLSX: {spatne}")
        (tmp / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        prikaz = ["typst", "compile", "--root", "/", "--font-path", str(FONTY), "--ignore-system-fonts",
                  "--input", f"data={tmp / 'data.json'}", str(SABLONA), str(pdf)]
        vystup = subprocess.run(prikaz, capture_output=True, text=True)
        if vystup.returncode != 0:
            raise ChybaSazby("typst: " + vystup.stderr.strip())
    chyby = zkontroluj_pdf(pdf, adresar_vysledku)
    if chyby:
        pdf.unlink(missing_ok=True)
        raise ChybaSazby("nesoulad čísel v PDF – sazba zastavena: " + "; ".join(chyby[:10]))
    for soubor in ("priloha.xlsx", "zjisteni.json"):
        if (adresar_vysledku / soubor).exists() and (cil / soubor).resolve() != (adresar_vysledku / soubor).resolve():
            shutil.copy(adresar_vysledku / soubor, cil / soubor)
    return pdf


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("adresar", type=Path, help="adresář s výstupem Bloku 2 (vysledek.json, priloha.xlsx)")
    parser.add_argument("--vystup", type=Path, help="kam uložit PDF a XLSX (výchozí: vedle vysledek.json); "
                                                  "ukázky do reporty/ukazky")
    parser.add_argument("--vyklad-schvalen", action="store_true",
                        help="odstraní ze zápatí stav KONCEPT; selže, dokud soubor analytika chybí nebo má zástupný text")
    parser.add_argument("--vyklad", type=Path, default=vy.VYKLAD, help="adresář výkladů analytika (reporty/vyklad)")
    args = parser.parse_args()
    try:
        cil = args.vystup / args.adresar.name if args.vystup else args.adresar
        pdf = vysazej(args.adresar, cil, koncept=not args.vyklad_schvalen, adresar_vykladu=args.vyklad)
    except ChybaSazby as exc:
        print(f"SAZBA ZASTAVENA: {exc}")
        return 1
    print(f"Hotovo: {pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
