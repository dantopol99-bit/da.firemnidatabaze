"""Návrh analytického výkladu reportu (stav KONCEPT – k revizi).

Každá kapitola má bloky ve struktuře „co je vidět → proč to tak může být →
co z toho plyne“. Pravidla:
  * čísla se berou výhradně z výstupu JSON Bloku 2 (třída Vstup) a vypisují
    se přesně tak, jak tam jsou (formát cz) – nic se nepřepočítává ani
    nezaokrouhluje; kontrola PDF ověří, že každé číslo v textu je v JSON i XLSX,
  * každé tvrzení odkazuje na tabulku nebo graf („tab. A“, „graf B“),
  * co nelze z dat doložit, je výslovně označeno jako hypotéza,
  * slova „firmy“ a „aktivní“ se nepoužívají (rozhodnutí 1).
Srovnání (vyšší/nižší) jsou jen slovní porovnání dvou zveřejněných čísel.
"""

from decimal import Decimal

NBSP = " "   # úzká nezlomitelná mezera – oddělovač tisíců (kontrola PDF ji rozpozná)


def cz(v) -> str:
    """Číslo z JSON v českém zápisu beze změny hodnoty (100.0 → 100, 4.35 → 4,35)."""
    if v is None:
        return "–"
    if isinstance(v, str):
        return v
    d = Decimal(str(v)).normalize()
    znak, cislice, exponent = d.as_tuple()
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
    """Přístup k výstupu JSON Bloku 2 (jen čtení)."""

    def __init__(self, vysledek: dict):
        self.v = vysledek
        self.meta = vysledek["meta"]
        self.tab = {t["kod"]: t for t in vysledek["tabulky"]}

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


def _blok(druh: str, text: str, hypoteza: bool = False) -> dict:
    return {"druh": druh, "text": text, "hypoteza": hypoteza}


def _v_uzemi(v: Vstup) -> str:
    return "v Česku" if v.uzemi["typ"] == "CR" else f"v území {v.uzemi['nazev']}"


def _mira_lq(lq: float) -> str:
    if lq > 1.1:
        return "nadprůměrně"
    if lq < 0.9:
        return "podprůměrně"
    return "zhruba průměrně"


def _srovnani_t02(v: Vstup) -> tuple[dict | None, dict | None, list[dict]]:
    radky = v.radky("T02_srovnani")
    cr = next((r for r in radky if r["promenna"] == "obor@CZ"), None)
    uz = next((r for r in radky if "(zkoumané území)" in r["popis"]), None)
    ostatni = [r for r in radky if r is not cr and r is not uz]
    return cr, uz, ostatni


# ---------------------------------------------------------------------------
# Shrnutí (hlavní sdělení: počet, LQ, hustota, pořadí – rozhodnutí 11)
# ---------------------------------------------------------------------------

def shrnuti(v: Vstup, L: dict) -> list[str]:
    body = []
    n = v.t01("REG_POCET")
    if n is None:
        return [f"Počet registrovaných subjektů oboru {_v_uzemi(v)} je pod prahem zveřejnění ({L['T01']})."]
    podil = v.t01("REG_PODIL_CR")
    uvod = _v_uzemi(v)
    body.append(f"{uvod[0].upper() + uvod[1:]} má sídlo {cz(n)} registrovaných subjektů s převažující činností "
                f"v oboru {v.obor}" + (f", tj. {cz(podil)} % oboru v ČR" if podil is not None else "") + f" ({L['T01']}).")
    lq = v.t01("LQ")
    if lq is not None:
        body.append(f"Lokalizační koeficient {cz(lq)}: obor je v území zastoupen {_mira_lq(lq)} "
                    f"vzhledem k ČR ({L['T01']}).")
    cr, uz, srov = _srovnani_t02(v)
    h = v.t01("HUSTOTA")
    if h is not None and cr and v.uzemi["typ"] != "CR":
        porovnani = "více" if h > cr["hodnoty"]["hustota"] else "méně" if h < cr["hodnoty"]["hustota"] else "stejně"
        body.append(f"Na 1{NBSP}000 obyvatel připadá {cz(h)} registrovaných subjektů oboru, tedy {porovnani} "
                    f"než v ČR ({cz(cr['hodnoty']['hustota'])}) ({L['T02']}).")
    p1, p2 = v.t01("PORADI_POCET"), v.t01("PORADI_HUSTOTA")
    if v.uzemi["typ"] == "KRAJ" and p1 is not None:
        body.append(f"Mezi 14 kraji je kraj podle počtu {cz(p1)}., podle hustoty na obyvatele "
                    f"{cz(p2)}. ({L['T03']}).")
    elif v.uzemi["typ"] == "OKRES" and p1 is not None:
        body.append(f"{v.t01_popis('PORADI_POCET')}: {cz(p1)}. ({L['T01']}).")
    for r in srov:
        h_ = r["hodnoty"]
        if h_["pocet"] is not None:
            body.append(f"Srovnávací {r['popis']}: {cz(h_['pocet'])} registrovaných subjektů oboru, lokalizační "
                        f"koeficient {cz(h_['lq'])}, na 1{NBSP}000 obyvatel {cz(h_['hustota'])} ({L['T02']}).")
    fo = next((r for r in v.radky("T05_fo_po") if r["promenna"] == "fopo:FO"), None)
    if fo:
        body.append(f"Fyzické osoby tvoří {cz(fo['hodnoty']['podil'])} % registrovaných subjektů oboru "
                    f"v území ({L['T05']}).")
    akt = v.t01("AKTIVNI_PODIL_KRAJ")
    if akt is not None:
        body.append(f"Kontext: podle ČSÚ má v kraji zjištěnou aktivitu (daně, pojistné) {cz(akt)} % všech "
                    f"registrovaných subjektů; počty v reportu zahrnují i subjekty bez zjištěné aktivity ({L['T01']}).")
    for varovani in v.meta["varovani"]:
        body.append("Varování: " + varovani)
    return body


# ---------------------------------------------------------------------------
# Postavení území
# ---------------------------------------------------------------------------

def postaveni(v: Vstup, L: dict) -> list[dict]:
    b = []
    n = v.t01("REG_POCET")
    if n is None:
        return [_blok("vidět", f"Počet registrovaných subjektů oboru je v území pod prahem zveřejnění ({L['T01']}).")]
    cr, uz, srov = _srovnani_t02(v)
    lq, h = v.t01("LQ"), v.t01("HUSTOTA")
    p1, p2 = v.t01("PORADI_POCET"), v.t01("PORADI_HUSTOTA")
    text = (f"Obor má {_v_uzemi(v)} {cz(n)} registrovaných subjektů, což je {cz(v.t01('REG_PODIL_OBOR'))} % všech "
            f"registrovaných subjektů území ({L['T01']}).")
    if lq is not None and cr:
        text += (f" Lokalizační koeficient {cz(lq)} a hustota {cz(h)} na 1{NBSP}000 obyvatel (ČR "
                 f"{cz(cr['hodnoty']['hustota'])}) ukazují, že obor je zastoupen {_mira_lq(lq)} ({L['T02']}, {L['g_lq']}).")
    if v.uzemi["typ"] == "KRAJ" and p1 is not None:
        text += (f" Podle počtu je kraj mezi 14 kraji {cz(p1)}., podle hustoty {cz(p2)}. "
                 f"({L['T03']}, {L['g_hustota']}).")
    for r in srov:
        if r["hodnoty"]["pocet"] is not None:
            vyssi = "vyšší" if r["hodnoty"]["hustota"] > h else "nižší"
            text += (f" {r['popis']} má hustotu {cz(r['hodnoty']['hustota'])}, tedy {vyssi} než zkoumané území "
                     f"({L['T02']}).")
    b.append(_blok("vidět", text))

    if v.uzemi["typ"] == "KRAJ" and p1 is not None and p2 is not None and p2 + 3 <= p1:
        b.append(_blok("proč", f"Kraj je podle počtu obyvatel menší ({L['T02']}), ale obor je v něm na obyvatele "
                               f"zastoupen hustěji než ve většině krajů. Nízké pořadí podle počtu tak odráží hlavně "
                               f"velikost kraje, ne slabost oboru ({L['T03']}).", hypoteza=True))
    if lq is not None and lq > 1.1:
        b.append(_blok("proč", "Silnější zastoupení oboru může souviset se strukturou místní ekonomiky nebo s poptávkou "
                               "v území (např. bytová výstavba, cestovní ruch). Z registru to ověřit nelze.",
                       hypoteza=True))
    elif lq is not None and lq < 0.9:
        b.append(_blok("proč", "Slabší zastoupení může znamenat, že subjekty oboru sídlí jinde, než působí "
                               "(sídlo ≠ místo činnosti), nebo že obor je v území skutečně méně rozvinutý.",
                       hypoteza=True))
    akt = v.t01("AKTIVNI_PODIL_KRAJ")
    if akt is not None:
        b.append(_blok("proč", f"Počty zahrnují i registrované subjekty bez činnosti. V kraji má podle ČSÚ zjištěnou "
                               f"aktivitu {cz(akt)} % všech registrovaných subjektů ({L['T01']}); podíl v oboru se může "
                               f"lišit.", hypoteza=True))
    b.append(_blok("plyne", "Pro srovnání mezi územími jsou vhodnější hustota na obyvatele a lokalizační koeficient "
                            "než absolutní počet, který závisí hlavně na velikosti území. Pořadí podle počtu je "
                            "vhodné číst spolu s pořadím podle hustoty."))
    if v.meta["varovani"]:
        b.append(_blok("plyne", "Kvůli nízké spolehlivosti zařazení (viz titulní strana a metodika) je počet oboru "
                                "spíše dolní mezí skutečného stavu."))
    return b


# ---------------------------------------------------------------------------
# Struktura
# ---------------------------------------------------------------------------

def struktura(v: Vstup, L: dict) -> list[dict]:
    b = []
    casti = []
    fo = next((r for r in v.radky("T05_fo_po") if r["promenna"] == "fopo:FO"), None)
    if fo:
        casti.append(f"Fyzické osoby tvoří {cz(fo['hodnoty']['podil'])} % registrovaných subjektů oboru ({L['T05']}).")
    formy = v.radky("T06_pravni_forma")
    if formy:
        nej = formy[0]
        casti.append(f"Nejčastější právní formou je {nej['popis']} ({cz(nej['hodnoty']['podil'])} %, {L['T06']}).")
    for kod, g, lbl in (("T07_velikost_fo", "FO", L["g_vel_fo"]), ("T08_velikost_po", "PO", L["g_vel_po"])):
        radky = v.radky(kod)
        neuv = next((r for r in radky if r["popis"] == "Neuvedeno"), None)
        bez = next((r for r in radky if r["popis"] == "bez zaměstnanců"), None)
        if radky:
            veta = f"U {g} je "
            if bez:
                veta += f"{cz(bez['hodnoty']['podil'])} % bez zaměstnanců a "
            veta += (f"u {cz(neuv['hodnoty']['podil'])} % není počet zaměstnanců uveden" if neuv
                     else "počet zaměstnanců uveden u všech zveřejněných skupin")
            casti.append(veta + f" ({lbl}).")
    prumer, median = v.t01("VEK_PRUMER"), v.t01("VEK_MEDIAN")
    vek = v.radky("T09_vekova_struktura")
    if prumer is not None:
        veta = f"Průměrný věk existujících subjektů je {cz(prumer)} roku, medián {cz(median)} roku ({L['T01']})"
        if vek:
            nej = max(vek, key=lambda r: r["hodnoty"]["pocet"])
            veta += f"; nejpočetnější je pásmo {nej['popis']} ({cz(nej['hodnoty']['podil'])} %, {L['g_vek']})"
        casti.append(veta + ".")
    if not casti:
        return [_blok("vidět", "Strukturu nelze zveřejnit – členění jsou pod prahem (viz příloha).")]
    b.append(_blok("vidět", " ".join(casti)))
    if fo and fo["hodnoty"]["podil"] > 70:
        b.append(_blok("proč", "Vysoký podíl fyzických osob ukazuje na obor s nízkými vstupními náklady, kde převládá "
                               "samostatné podnikání a subdodávky. Registrované FO zahrnují i osoby s vedlejší nebo "
                               "přerušenou činností.", hypoteza=True))
    if v.radky("T07_velikost_fo") or v.radky("T08_velikost_po"):
        b.append(_blok("proč", "„Neuvedeno“ neznamená nulu zaměstnanců: u právnických osob se kategorie „bez "
                               "zaměstnanců“ v registru prakticky nepoužívá a subjekty bez hlášených zaměstnanců mají "
                               "„Neuvedeno“ (metodika)."))
    if vek:
        b.append(_blok("proč", "Starší pásma obsahují i dlouhodobě registrované subjekty, u nichž registr nemusí "
                               "odrážet současnou činnost.", hypoteza=True))
    b.append(_blok("plyne", "Velikostní profil je kvůli vysokému podílu „Neuvedeno“ jen orientační a patří do "
                            "strukturní části, ne do hlavních sdělení. Věková struktura popisuje dnes existující "
                            "subjekty, nikoli vývoj zakládání v čase."))
    return b


# ---------------------------------------------------------------------------
# Dynamika území a kontext ČR
# ---------------------------------------------------------------------------

def dynamika(v: Vstup, L: dict) -> list[dict]:
    b = []
    casti = []
    t11 = v.radky("T11_dynamika_csu")
    posledni = {}   # jen úplné roky (poslední rok s poznámkou „N čtvrtletí“ se vynechá)
    for r in t11:
        rok, _, druh = r["popis"].partition(" – ")
        if r.get("poznamka") and r["poznamka"].split(";")[0].endswith(" čtvrtletí"):
            continue
        posledni.setdefault(rok, {})[druh] = r
    if posledni:
        rok = max(posledni)
        vz, za = posledni[rok].get("vzniklé"), posledni[rok].get("zaniklé")
        if vz and za and vz["hodnoty"]["celkem"] is not None and za["hodnoty"]["celkem"] is not None:
            vice = "více" if vz["hodnoty"]["celkem"] > za["hodnoty"]["celkem"] else "méně"
            casti.append(f"V celém území (všechny obory) v roce {rok} vzniklo {cz(vz['hodnoty']['celkem'])} a zaniklo "
                         f"{cz(za['hodnoty']['celkem'])} ekonomických subjektů – vzniklo tedy {vice} subjektů, než "
                         f"zaniklo ({L['g_dyn']}, {L['T11']}).")
    r2023 = next((r for r in t11 if r["popis"] == "2023 – zaniklé"), None)
    if r2023 and r2023["hodnoty"]["celkem"] is not None:
        casti.append(f"Rok 2023 je mimořádný: zaniklo {cz(r2023['hodnoty']['celkem'])} subjektů, převážně fyzických "
                     f"osob ({L['T11']}).")
    celkem = next((r for r in v.radky("T10_zaniky_po", "celkem")), None)
    if celkem:
        casti.append(f"V oboru a území zaniklo od roku 2023 {cz(celkem['hodnoty']['pocet'])} právnických osob "
                     f"({L['T10']}).")
    t12 = v.radky("T12_demografie_cr")
    if t12:
        posl_fo = [r for r in t12 if r["popis"].endswith("podniky FO")][-1]
        h = posl_fo["hodnoty"]
        if h.get("obor_mira_vzniku") is not None:
            rok12 = posl_fo["popis"].split(" – ")[0]
            vyssi = "vyšší" if h["obor_mira_vzniku"] > h["cr_mira_vzniku"] else "nižší"
            casti.append(f"V ČR byla v roce {rok12} míra vzniků podniků fyzických osob v odvětví oboru "
                         f"{cz(h['obor_mira_vzniku'])} %, tedy {vyssi} než ve všech odvětvích "
                         f"({cz(h['cr_mira_vzniku'])} %) ({L['g_miry']}, {L['T12']}).")
    if not casti:
        return [_blok("vidět", "Údaje o dynamice nejsou k dispozici.")]
    b.append(_blok("vidět", " ".join(casti)))
    b.append(_blok("proč", "Výkyv zániků v roce 2023 souvisí s hromadným ukončením registrací fyzických osob, které "
                           "ČSÚ vykazuje v 1. čtvrtletí 2023; s vývojem oboru pravděpodobně nesouvisí.", hypoteza=True))
    b.append(_blok("proč", "Míry z demografie podniků se týkají jiné jednotky (aktivní podnik) a celé ČR; o dynamice "
                           "oboru ve zkoumaném území nevypovídají."))
    b.append(_blok("plyne", "Dynamiku oboru v území nelze z publikovaných tabulek ČSÚ určit (ČSÚ ji v členění kraj × "
                            "obor nepublikuje). Vznikne z archivu snímků RES; do té doby slouží dynamika území a "
                            "kontext ČR jen jako rámec."))
    return b
