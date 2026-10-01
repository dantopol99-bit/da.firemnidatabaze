"""Výklad reportu ve dvou vrstvách (rozhodnutí 12).

1. Strojová vrstva (tento modul): „co je vidět“ a zjištění detektoru (report_zjisteni).
   Jen věcný popis zveřejněných čísel, žádné hypotézy ani doporučení:
     * čísla se berou výhradně z výstupu JSON (třída Vstup) a vypisují se přesně tak,
       jak tam jsou (formát cz) – nic se nepřepočítává ani nezaokrouhluje,
     * každé tvrzení odkazuje na tabulku nebo graf („tab. A“, „graf B“),
     * slovní srovnání dvou čísel jen funkcí report_zjisteni.srovnej: rozdíl pod 3 %
       relativně je „srovnatelné“,
     * názvy území v 6. pádě z ručně psané tabulky (report_cestina), nikdy „v území <název>“,
     * slova „firmy“ a „aktivní“ se nepoužívají (rozhodnutí 1).
2. Vrstva analytika: „proč to tak může být“ a „co z toho plyne“ píše člověk do
   reporty/vyklad/<id_reportu>.md (nacti_vyklad_analytika). Sazba text vloží a kontrola
   čísel na něj platí stejně. Dokud soubor chybí nebo obsahuje zástupný text, nelze
   report vysázet jako schválený (--vyklad-schvalen).
"""

import re
from decimal import Decimal
from pathlib import Path

from firemni_databaze.report_cestina import lokativ, velke

NBSP = "\u202f"   # úzká nezlomitelná mezera – oddělovač tisíců (kontrola PDF ji rozpozná)
KOREN = Path(__file__).resolve().parents[2]
VYKLAD = KOREN / "reporty" / "vyklad"
ZASTUPNY_TEXT = "ZÁSTUPNÝ TEXT"
KAPITOLY = {"postaveni": "Postavení území", "struktura": "Struktura", "dynamika": "Dynamika území a kontext ČR"}
DRUHY_ANALYTIKA = {"Proč to tak může být": "proč", "Co z toho plyne": "plyne"}
SHRNUTI_POCET = 5            # rozhodnutí E: shrnutí z 5 nejsilnějších zjištění
SHRNUTI_MAX_TYPU = 2         # … nejvýš 2 téhož typu, aby shrnutí nepopisovalo jeden jev pětkrát
ZJISTENI_NA_KAPITOLU = 5


def cz(v) -> str:
    """Číslo z JSON v českém zápisu beze změny hodnoty (100.0 → 100, 4.35 → 4,35)."""
    if v is None:
        return "–"
    if isinstance(v, str):
        return v
    d = Decimal(str(v)).normalize()
    text = format(d, "f")
    cele, _, desetinne = text.partition(".")
    minus = cele.startswith("-")
    cele = cele.lstrip("-")
    skupiny = []
    while len(cele) > 3:
        skupiny.insert(0, cele[-3:])
        cele = cele[:-3]
    skupiny.insert(0, cele)
    return ("-" if minus else "") + NBSP.join(skupiny) + ("," + desetinne if desetinne else "")


class Vstup:
    """Přístup k výstupu JSON (jen čtení)."""

    def __init__(self, vysledek: dict):
        self.v = vysledek
        self.meta = vysledek["meta"]
        self.tab = {t["kod"]: t for t in vysledek["tabulky"]}
        self.zjisteni = vysledek.get("zjisteni", [])

    def t(self, kod: str) -> dict | None:
        t = self.tab.get(kod)
        return t if t and t["zverejneno"] else None

    def t01(self, ukazatel: str, index: int = 0):
        radky = [r for r in self.tab["T01_zakladni"]["radky"] if r["ukazatele"]["hodnota"] == ukazatel]
        return radky[index]["hodnoty"]["hodnota"] if len(radky) > index else None

    def t01_popis(self, ukazatel: str, index: int = 0) -> str | None:
        radky = [r for r in self.tab["T01_zakladni"]["radky"] if r["ukazatele"]["hodnota"] == ukazatel]
        return radky[index]["popis"] if len(radky) > index else None

    def radky(self, kod: str, typ: str | None = "polozka") -> list[dict]:
        t = self.t(kod)
        return [r for r in t["radky"] if typ is None or r["typ"] == typ] if t else []

    @property
    def uzemi(self) -> dict:
        return self.meta["uzemi"]

    @property
    def obor(self) -> str:
        return self.meta["obor_popis"]

    @property
    def v_uzemi(self) -> str:
        return lokativ(self.uzemi["kod"])


def _blok(druh: str, text: str, hypoteza: bool = False) -> dict:
    return {"druh": druh, "text": text, "hypoteza": hypoteza}


def vztah(a, b, lok_ref: str) -> str:
    """„vyšší než v Česku“ / „nižší než …“ / „srovnatelné s hodnotou v Česku“ (pravidlo 3 %)."""
    from firemni_databaze.report_zjisteni import srovnej
    s = srovnej(a, b)
    return f"srovnatelné s hodnotou {lok_ref}" if s == "srovnatelné" else f"{s} než {lok_ref}"


def _t02(v: Vstup) -> tuple[dict | None, dict | None, list[dict]]:
    radky = v.radky("T02_srovnani")
    cr = next((r for r in radky if r["promenna"] == "obor@CZ"), None)
    uz = next((r for r in radky if "(zkoumané území)" in r["popis"]), None)
    ostatni = [r for r in radky if r is not cr and r is not uz]
    return cr, uz, ostatni


def _kod(radek_t02: dict) -> str:
    return radek_t02["promenna"].split(":")[-1].replace("obor@CZ", "CZ")


def _ref(z: dict, L: dict) -> str:
    """Odkazy na tabulky, z nichž jsou čísla zjištění."""
    kody = []
    for c in z["cisla"]:
        k = c["tabulka"][:3]
        if k != "T19" and k not in kody:
            kody.append(k)
    return ", ".join(L.get(k, "příloha") for k in kody)


def zjisteni_text(z: dict, L: dict) -> str:
    return f"{z['popis'].rstrip('.')} ({_ref(z, L)})."


# ---------------------------------------------------------------------------
# Shrnutí: 5 nejsilnějších zjištění detektoru (dlaždice sestavuje report_pdf)
# ---------------------------------------------------------------------------

def vyber_shrnuti(zjisteni: list[dict]) -> list[dict]:
    vybrana, podle_typu = [], {}
    for z in zjisteni:                      # už seřazená podle síly
        if podle_typu.get(z["typ"], 0) >= SHRNUTI_MAX_TYPU:
            continue
        vybrana.append(z)
        podle_typu[z["typ"]] = podle_typu.get(z["typ"], 0) + 1
        if len(vybrana) == SHRNUTI_POCET:
            break
    return vybrana


def shrnuti(v: Vstup, L: dict) -> list[str]:
    n = v.t01("REG_POCET")
    if n is None:
        return [f"Počet registrovaných subjektů oboru {v.v_uzemi} je pod prahem zveřejnění ({L['T01']})."]
    body = [zjisteni_text(z, L) for z in vyber_shrnuti(v.zjisteni)]
    if not body:
        body.append(f"Detektor nenašel žádný rozdíl alespoň 3 % relativně – hodnoty jsou srovnatelné s ČR ({L['T02']}).")
    for varovani in v.meta["varovani"]:
        body.append("Varování: " + varovani)
    return body


def zjisteni_kapitoly(v: Vstup, kapitola: str, L: dict) -> list[dict]:
    """Zjištění detektoru patřící ke kapitole (nejvýš ZJISTENI_NA_KAPITOLU nejsilnějších)."""
    def patri(z):
        if z["typ"] == "zmena_trendu":
            return kapitola == "dynamika"
        if z["typ"] == "odchylka_od_cr" and z["podtyp"].startswith("struktura"):
            return kapitola == "struktura"
        return kapitola == "postaveni"
    vybrana = [z for z in v.zjisteni if patri(z)]
    bloky = [_blok("zjištění", f"{z['id']}: {zjisteni_text(z, L)}") for z in vybrana[:ZJISTENI_NA_KAPITOLU]]
    if len(vybrana) > ZJISTENI_NA_KAPITOLU:
        bloky.append(_blok("zjištění", "Další zjištění této kapitoly jsou v datové příloze a v souboru zjisteni.json."))
    return bloky


# ---------------------------------------------------------------------------
# Co je vidět: postavení území
# ---------------------------------------------------------------------------

def postaveni(v: Vstup, L: dict) -> list[dict]:
    n = v.t01("REG_POCET")
    if n is None:
        return [_blok("vidět", f"Počet registrovaných subjektů oboru je {v.v_uzemi} pod prahem zveřejnění ({L['T01']}).")]
    cr, uz, srov = _t02(v)
    v_cr = lokativ("CZ")
    casti = [f"{velke(v.v_uzemi)} má sídlo {cz(n)} registrovaných subjektů s převažující činností v oboru, tj. "
             f"{cz(v.t01('REG_PODIL_OBOR'))} % všech registrovaných subjektů území"
             + (f" a {cz(v.t01('REG_PODIL_CR'))} % oboru v ČR" if v.t01("REG_PODIL_CR") is not None else "")
             + f" ({L['T01']})."]
    lq, h = v.t01("LQ"), v.t01("HUSTOTA")
    if lq is not None and cr:
        h_cr = cr["hodnoty"]["hustota"]
        casti.append(f"Lokalizační koeficient je {cz(lq)} (ČR = 1) a na 1{NBSP}000 obyvatel připadá {cz(h)} "
                     f"registrovaných subjektů oboru, což je {vztah(h, h_cr, v_cr)} ({cz(h_cr)}) ({L['T02']}, {L['g_lq']}).")
    p1, p2 = v.t01("PORADI_POCET"), v.t01("PORADI_HUSTOTA")
    if v.uzemi["typ"] == "KRAJ" and p1 is not None:
        casti.append(f"Mezi 14 kraji je kraj podle počtu {cz(p1)}., podle hustoty na obyvatele {cz(p2)}. "
                     f"({L['T03']}, {L['g_hustota']}).")
    elif v.uzemi["typ"] == "OKRES" and p1 is not None:
        casti.append(f"{v.t01_popis('PORADI_POCET')}: {cz(p1)}. ({L['T01']}).")
    for r in srov:
        hk = r["hodnoty"]
        if hk["pocet"] is not None and h is not None:
            casti.append(f"{velke(lokativ(_kod(r)))} připadá na 1{NBSP}000 obyvatel {cz(hk['hustota'])} registrovaných "
                         f"subjektů oboru ({vztah(hk['hustota'], h, v.v_uzemi)}), lokalizační koeficient je "
                         f"{cz(hk['lq'])} ({L['T02']}).")
    okresy = v.radky("T04_okresy")
    if v.uzemi["typ"] == "KRAJ" and len(okresy) >= 2:
        mx = max(okresy, key=lambda r: r["hodnoty"]["hustota"])
        mn = min(okresy, key=lambda r: r["hodnoty"]["hustota"])
        casti.append(f"Mezi okresy kraje je hustota nejvyšší {lokativ(_kod(mx))} ({cz(mx['hodnoty']['hustota'])}) a "
                     f"nejnižší {lokativ(_kod(mn))} ({cz(mn['hodnoty']['hustota'])}) ({L['T04']}).")
    akt, akt_s = v.t01("AKTIVNI_PODIL_KRAJ"), v.t01("AKTIVNI_PODIL_SEKCE_KRAJ")
    if akt is not None:
        v_kraji = lokativ(v.uzemi["kraj"] or "CZ")
        veta = (f"Podle ČSÚ má {v_kraji} zjištěnou aktivitu (daně, pojistné) {cz(akt)} % všech registrovaných "
                f"subjektů")
        if akt_s is not None:
            veta += f" a {cz(akt_s)} % subjektů sekce {v.meta['obor'][0]['kod']} ({vztah(akt_s, akt, 've všech oborech')})"
        casti.append(veta + f"; počty v reportu zahrnují i subjekty bez zjištěné aktivity ({L['T01']}).")
    return [_blok("vidět", " ".join(casti))] + zjisteni_kapitoly(v, "postaveni", L)


# ---------------------------------------------------------------------------
# Co je vidět: struktura (se srovnáním s ČR a srovnávacími kraji)
# ---------------------------------------------------------------------------

def _bench_text(r: dict, t: dict) -> str:
    """„v Česku 82,5 %, Královéhradecký kraj 89,3 %, …“ ze sloupců benchmarkové tabulky."""
    casti = []
    for sl in t["sloupce"]:
        if sl["kod"] in ("uzemi", "rozdil_cr") or r["hodnoty"].get(sl["kod"]) is None:
            continue
        nazev = sl["nazev"].removesuffix(" (%)")
        casti.append(f"{lokativ('CZ') if sl['kod'] == 'cr' else nazev} {cz(r['hodnoty'][sl['kod']])} %")
    return "; ".join(casti)


def struktura(v: Vstup, L: dict) -> list[dict]:
    casti = []
    t13, t14 = v.t("T13_bench_fo_po"), v.t("T14_bench_pravni_forma")
    fo = next((r for r in v.radky("T05_fo_po") if r["promenna"] == "fopo:FO"), None)
    if fo:
        veta = f"Fyzické osoby tvoří {v.v_uzemi} {cz(fo['hodnoty']['podil'])} % registrovaných subjektů oboru"
        rb = next((r for r in v.radky("T13_bench_fo_po") if r["promenna"] == "fopo:FO"), None)
        if rb and t13:
            veta += f", {_bench_text(rb, t13)} ({L['T05']}, {L['T13']})."
        else:
            veta += f" ({L['T05']})."
        casti.append(veta)
    formy = v.radky("T06_pravni_forma")
    for g in ("FO", "PO"):
        kandidati = [r for r in formy if (g == "PO") == (r["promenna"].split(":")[1] not in _FO)]
        if kandidati:
            nej = max(kandidati, key=lambda r: r["hodnoty"]["pocet"])
            rb = next((r for r in v.radky("T14_bench_pravni_forma") if r["promenna"] == nej["promenna"]), None)
            casti.append(f"Nejčastější právní formou {g} je {nej['popis']}: {v.v_uzemi} {cz(nej['hodnoty']['podil'])} % "
                         f"všech registrovaných subjektů oboru" + (f", {_bench_text(rb, t14)}" if rb and t14 else "")
                         + f" ({L['T06']}" + (f", {L['T14']}" if t14 else "") + ").")
    for kod, kod_b, g, lbl in (("T07_velikost_fo", "T15_bench_velikost_fo", "FO", L["g_vel_fo"]),
                               ("T08_velikost_po", "T16_bench_velikost_po", "PO", L["g_vel_po"])):
        radky = v.radky(kod)
        if not radky:
            continue
        tb = v.t(kod_b)
        bench = {r["popis"]: r for r in v.radky(kod_b)}
        polozky = []
        for r in radky:
            p = f"„{r['popis']}“ {cz(r['hodnoty']['podil'])} %"
            if r["popis"] in bench and tb and bench[r["popis"]]["hodnoty"].get("cr") is not None:
                p += f" ({lokativ('CZ')} {cz(bench[r['popis']]['hodnoty']['cr'])} %)"
            polozky.append(p)
        casti.append(f"Počet zaměstnanců {g} {v.v_uzemi}: " + ", ".join(polozky)
                     + f" ({lbl}, {L[kod[:3]]}" + (f", {L[kod_b[:3]]}" if tb else "") + ").")
    prumer, median = v.t01("VEK_PRUMER"), v.t01("VEK_MEDIAN")
    if prumer is not None:
        veta = f"Průměrný věk existujících subjektů je {cz(prumer)} roku, medián {cz(median)} roku ({L['T01']})"
        t17 = v.radky("T17_bench_vekova_struktura")
        rozdily = [r for r in t17 if r["hodnoty"].get("rozdil_cr") is not None]
        if rozdily:
            r = max(rozdily, key=lambda r: abs(r["hodnoty"]["rozdil_cr"]))
            veta += (f"; největší rozdíl proti ČR je v pásmu {r['popis']}: {v.v_uzemi} {cz(r['hodnoty']['uzemi'])} %, "
                     f"{lokativ('CZ')} {cz(r['hodnoty']['cr'])} % ({L['g_vek']}, {L['T17']})")
        casti.append(veta + ".")
    if not casti:
        return [_blok("vidět", "Strukturu nelze zveřejnit – členění jsou pod prahem (viz příloha).")]
    return [_blok("vidět", " ".join(casti))] + zjisteni_kapitoly(v, "struktura", L)


_FO = {"101", "102", "103", "104", "105", "106", "107", "108", "424", "425"}


# ---------------------------------------------------------------------------
# Co je vidět: dynamika
# ---------------------------------------------------------------------------

def dynamika(v: Vstup, L: dict) -> list[dict]:
    casti = []
    t11 = v.radky("T11_dynamika_csu")
    posledni = {}   # jen úplné roky (rok s poznámkou „N čtvrtletí“ se vynechá)
    for r in t11:
        rok, _, druh = r["popis"].partition(" – ")
        if r.get("poznamka") and r["poznamka"].split(";")[0].endswith(" čtvrtletí"):
            continue
        posledni.setdefault(rok, {})[druh] = r
    if posledni:
        rok = max(posledni)
        vz, za = posledni[rok].get("vzniklé"), posledni[rok].get("zaniklé")
        if vz and za and vz["hodnoty"]["celkem"] is not None and za["hodnoty"]["celkem"] is not None:
            casti.append(f"{velke(v.v_uzemi)} (všechny obory) v roce {rok} vzniklo {cz(vz['hodnoty']['celkem'])} a "
                         f"zaniklo {cz(za['hodnoty']['celkem'])} ekonomických subjektů ({L['g_dyn']}, {L['T11']}).")
    r2023 = next((r for r in t11 if r["popis"] == "2023 – zaniklé"), None)
    if r2023 and r2023["hodnoty"]["celkem"] is not None:
        casti.append(f"Rok 2023 je mimořádný: zaniklo {cz(r2023['hodnoty']['celkem'])} subjektů, převážně fyzických "
                     f"osob ({L['T11']}).")
    t10 = [r for r in v.radky("T10_zaniky_po", None) if r["typ"] == "polozka"]
    if t10:
        casti.append("Zaniklé právnické osoby v oboru " + v.v_uzemi + ": "
                     + ", ".join(f"{r['popis']} {cz(r['hodnoty']['pocet'])}" for r in t10) + f" ({L['T10']}).")
    t18 = v.radky("T18_mira_zaniku_po")
    obdobi = (v.t("T18_mira_zaniku_po") or {}).get("obdobi", "")
    for kod, lok in ((v.uzemi["kod"], v.v_uzemi), ("CZ", lokativ("CZ"))):
        if kod == "CZ" and v.uzemi["typ"] == "CR":
            continue
        radky = [r for r in t18 if r["uzemi"] == kod]
        rok_txt = [f"{r['rok']} {cz(r['hodnoty']['mira'])} %" for r in radky if r["hodnoty"]["mira"] is not None]
        obd_txt = [f"{r['rok']} {cz(r['hodnoty']['mira_obd'])} %" for r in radky if r["hodnoty"]["mira_obd"] is not None]
        if rok_txt or obd_txt:
            casti.append(f"Míra zániku PO v oboru {lok}: za celý rok " + (", ".join(rok_txt) or "nezveřejněna")
                         + f"; za období {obdobi} " + (", ".join(obd_txt) or "nezveřejněna") + f" ({L['g_zanik']}, {L['T18']}).")
    t12 = v.radky("T12_demografie_cr")
    if t12:
        posl_fo = [r for r in t12 if r["popis"].endswith("podniky FO")][-1]
        h = posl_fo["hodnoty"]
        if h.get("obor_mira_vzniku") is not None:
            rok12 = posl_fo["popis"].split(" – ")[0]
            casti.append(f"Kontext ČR (jiná jednotka – podnik): v roce {rok12} byla míra vzniků podniků fyzických osob "
                         f"v odvětví oboru {cz(h['obor_mira_vzniku'])} %, ve všech odvětvích {cz(h['cr_mira_vzniku'])} % "
                         f"({L['g_miry']}, {L['T12']}).")
    if not casti:
        return [_blok("vidět", "Údaje o dynamice nejsou k dispozici.")]
    return [_blok("vidět", " ".join(casti))] + zjisteni_kapitoly(v, "dynamika", L)


# ---------------------------------------------------------------------------
# Vrstva analytika: reporty/vyklad/<id_reportu>.md
# ---------------------------------------------------------------------------

def soubor_vykladu(id_reportu: str, adresar: Path = VYKLAD) -> Path:
    return adresar / f"{id_reportu}.md"


def nacti_vyklad_analytika(cesta: Path) -> tuple[str, dict[str, list[dict]]]:
    """Vrátí (stav, {kapitola: [bloky proč/plyne]}); stav: chybi | zastupny | hotovy.

    Formát: „## <název kapitoly>“, pod ním „### Proč to tak může být“ a „### Co z toho plyne“,
    odstavce oddělené prázdným řádkem; odstavec začínající „Hypotéza:“ se vysází jako hypotéza.
    HTML komentáře (<!-- … -->) jsou pokyny pro analytika a do sazby nejdou."""
    if not cesta.exists():
        return "chybi", {}
    text = re.sub(r"<!--.*?-->", "", cesta.read_text(encoding="utf-8"), flags=re.S)
    podle_nazvu = {n: k for k, n in KAPITOLY.items()}
    bloky: dict[str, list[dict]] = {k: [] for k in KAPITOLY}
    kapitola = druh = None
    odstavec: list[str] = []

    def uzavri():
        if odstavec and kapitola and druh:
            t = " ".join(s.strip() for s in odstavec).strip()
            hyp = t.startswith("Hypotéza:")
            bloky[kapitola].append(_blok(druh, t.removeprefix("Hypotéza:").strip() if hyp else t, hyp))
        odstavec.clear()

    for radek in text.splitlines():
        if radek.startswith("## "):
            uzavri()
            kapitola, druh = podle_nazvu.get(radek[3:].strip()), None
        elif radek.startswith("### "):
            uzavri()
            druh = DRUHY_ANALYTIKA.get(radek[4:].strip())
        elif not radek.strip():
            uzavri()
        elif not radek.startswith("# "):
            odstavec.append(radek)
    uzavri()
    stav = "zastupny" if ZASTUPNY_TEXT in text or any(not b for b in bloky.values()) else "hotovy"
    return stav, bloky


def sablona_vykladu(vysledek: dict, id_reportu: str) -> str:
    """Zástupný soubor výkladu pro analytika (kapitoly × proč / plyne)."""
    m = vysledek["meta"]
    radky = [f"# Výklad analytika: {m['obor_popis']} × {m['uzemi']['nazev']}, snímek RES {m['zadani']['datum_snimku']}",
             "",
             "<!--",
             "Rozhodnutí 12: stroj píše „co je vidět“ a zjištění detektoru (zjisteni.json), analytik píše",
             "„proč to tak může být“ a „co z toho plyne“. Pravidla:",
             "  * odstavce oddělené prázdným řádkem; odstavec začínající „Hypotéza:“ se vysází jako hypotéza,",
             "  * každé číslo musí být ve vysledek.json i v priloha.xlsx (kontrola čísel v PDF platí i sem),",
             "  * odkazujte na zjištění (Z01 …) a tabulky; nepoužívejte slova „firmy“ ani „aktivní“,",
             f"  * dokud soubor obsahuje „{ZASTUPNY_TEXT}“, nelze report vysázet s --vyklad-schvalen.",
             "-->",
             ""]
    for nazev in KAPITOLY.values():
        radky += [f"## {nazev}", ""]
        for druh in DRUHY_ANALYTIKA:
            radky += [f"### {druh}", "", f"{ZASTUPNY_TEXT} – doplní analytik.", ""]
    return "\n".join(radky)
