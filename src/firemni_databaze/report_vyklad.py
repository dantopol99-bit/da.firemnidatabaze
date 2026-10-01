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
2. Vrstva analytika: shrnutí na straně 2, „proč to tak může být“ a „co z toho plyne“
   píše člověk do reporty/vyklad/<id_reportu>.md (nacti_vyklad_analytika). Sazba text
   vloží (mezery mezi číslicemi převede na nezlomitelný oddělovač tisíců) a kontrola
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
KAPITOLY = {"postaveni": "Postavení území", "struktura": "Struktura", "ekonomicky_profil": "Ekonomický profil",
            "zamestnanost": "Zaměstnanost a mzdy",
            "dynamika": "Dynamika území a kontext ČR"}
ODDILY = {"shrnuti": "Shrnutí", **KAPITOLY}     # oddíly souboru analytika (shrnutí = body strany 2)
DRUHY_ANALYTIKA = {"Proč to tak může být": "proč", "Co z toho plyne": "plyne"}
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
# Zjištění detektoru: v kapitolách (nejsilnější) a celá v příloze
# ---------------------------------------------------------------------------

def zjisteni_priloha(v: Vstup, L: dict) -> list[str]:
    """Všechna zjištění detektoru seřazená podle síly (příloha PDF)."""
    if not v.zjisteni:
        return ["Detektor nenašel žádný rozdíl alespoň 3 % relativně."]
    return [f"{z['id']} ({z['typ_nazev']}, síla {cz(z['sila'])}): {zjisteni_text(z, L)}" for z in v.zjisteni]


def zjisteni_kapitoly(v: Vstup, kapitola: str, L: dict) -> list[dict]:
    """Zjištění detektoru patřící ke kapitole (nejvýš ZJISTENI_NA_KAPITOLU nejsilnějších)."""
    def patri(z):
        if z["typ"] == "zmena_trendu":
            return kapitola == "dynamika"
        if z["typ"] == "mzdy_zamestnanost":
            return kapitola == "zamestnanost"
        if z["typ"] == "ekonomika":
            return kapitola == "ekonomicky_profil"
        if z["typ"] == "odchylka_od_cr" and z["podtyp"].startswith("struktura"):
            return kapitola == "struktura"
        return kapitola == "postaveni"
    vybrana = [z for z in v.zjisteni if patri(z)]
    bloky = [_blok("zjištění", f"{z['id']}: {zjisteni_text(z, L)}") for z in vybrana[:ZJISTENI_NA_KAPITOLU]]
    if len(vybrana) > ZJISTENI_NA_KAPITOLU:
        bloky.append(_blok("zjištění", "Další zjištění této kapitoly jsou v příloze Zjištění detektoru."))
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
# Co je vidět: ekonomický profil (Eurostat, regionální účty)
# ---------------------------------------------------------------------------

def ekonomika(v: Vstup, L: dict) -> list[dict]:
    t22 = v.t("T22_ekonomika")
    if not t22:
        duvod = (v.tab.get("T22_ekonomika") or {}).get("duvod") or "údaje nejsou k dispozici"
        return [_blok("vidět", f"Regionální účty za obor nejsou k dispozici: {duvod} ({L['T22']}).")]
    sk = t22.get("skupina_nazev", "")
    kraj = v.uzemi["kraj"] or "CZ"
    v_kraji, v_cr = lokativ(kraj), lokativ("CZ")
    radky = [r for r in t22["radky"] if r["uzemi"] == kraj]
    cr = {r["rok"]: r for r in t22["radky"] if r["uzemi"] == "CZ"}
    casti = []
    if v.uzemi["typ"] == "OKRES":
        casti.append(f"Regionální účty za okresy neexistují; uvádí se kraj jako nejbližší publikovaná úroveň ({L['T22']}).")
    if any("součástí této širší skupiny" in p or "Nejbližší publikovaná úroveň: skupina" in p for p in t22["poznamky"]):
        casti.append(f"Eurostat publikuje regionální účty jen za skupiny odvětví A*10; uvádí se skupina {sk}, "
                     f"která obor zahrnuje ({L['T22']}).")
    if radky and radky[-1]["rok"] in cr:
        p, c = radky[-1], cr[radky[-1]["rok"]]
        h, hc = p["hodnoty"], c["hodnoty"]
        rok = p["rok"]
        if kraj != "CZ":
            casti.append(f"Podle regionálních účtů Eurostatu vytvořila skupina {sk} v roce {rok} {v_kraji} hrubou "
                         f"přidanou hodnotu {cz(h['hph'])} mil. Kč, tj. {cz(h['hph_podil_uzemi'])} % HPH kraje "
                         f"({vztah(h['hph_podil_uzemi'], hc['hph_podil_uzemi'], v_cr)}, {cz(hc['hph_podil_uzemi'])} %) "
                         f"a {cz(h['hph_podil_cr'])} % HPH skupiny v ČR ({L['T22']}).")
            casti.append(f"Zaměstnaných (národní účty, včetně sebezaměstnaných) bylo {cz(h['zam'])} tis., z toho "
                         f"{cz(h['podil_self'])} % sebezaměstnaných ({v_cr} {cz(hc['podil_self'])} %). Hrubá přidaná "
                         f"hodnota na zaměstnaného dosáhla {cz(h['produktivita'])} tis. Kč, tj. "
                         f"{cz(h['produktivita_index_cr'])} % úrovně ČR ({cz(hc['produktivita'])} tis. Kč) "
                         f"({L['g_ekon']}, {L['T22']}).")
            srov = [f"{lokativ(r['uzemi'])} {cz(r['hodnoty']['produktivita'])} tis. Kč "
                    f"({vztah(r['hodnoty']['produktivita'], h['produktivita'], v_kraji)})"
                    for r in t22["radky"] if r["uzemi"] not in (kraj, "CZ") and r["rok"] == rok
                    and r["hodnoty"]["produktivita"] is not None]
            if srov:
                casti.append("Ve srovnávacích krajích byla HPH na zaměstnaného " + ", ".join(srov) + f" ({L['T22']}).")
        prvni = radky[0]
        if prvni is not p and prvni["rok"] in cr:
            casti.append(f"Objem HPH skupiny (ve stálých cenách) se mezi lety {prvni['rok']} a {rok} změnil {v_kraji} na "
                         f"{cz(h['objem_index'])} % výchozí úrovně, {v_cr} na {cz(hc['objem_index'])} %; v roce {rok} "
                         f"byla objemová změna {v_kraji} {cz(h['rust'])} %, {v_cr} {cz(hc['rust'])} % ({L['T22']}).")
    t23 = v.t("T23_nahrady")
    if t23 and radky:
        rok = radky[-1]["rok"]
        reg = next((r for r in t23["radky"] if r["uzemi"] == kraj[:4] and r["rok"] == rok), None)
        c23 = next((r for r in t23["radky"] if r["uzemi"] == "CZ" and r["rok"] == rok), None)
        if reg and c23 and kraj != "CZ":
            casti.append(f"Náhrady zaměstnancům Eurostat za kraje nepublikuje; v regionu soudržnosti "
                         f"{reg['popis'].split(' (')[0]} (nejbližší publikovaná úroveň) tvořily v roce {rok} "
                         f"{cz(reg['hodnoty']['podil'])} % HPH skupiny, {v_cr} {cz(c23['hodnoty']['podil'])} % "
                         f"({L['T23']}).")
    if not casti:
        return [_blok("vidět", f"Regionální účty pro toto území nejsou k dispozici ({L['T22']}).")]
    return [_blok("vidět", " ".join(casti))] + zjisteni_kapitoly(v, "ekonomicky_profil", L)


# ---------------------------------------------------------------------------
# Co je vidět: zaměstnanost a mzdy (ČSÚ, obor × kraj jen z ročního zjišťování)
# ---------------------------------------------------------------------------

def zamestnanost(v: Vstup, L: dict) -> list[dict]:
    t20 = v.t("T20_mzdy_obor")
    if not t20:
        duvod = (v.tab.get("T20_mzdy_obor") or {}).get("duvod") or "údaje nejsou k dispozici"
        return [_blok("vidět", f"Zaměstnance a mzdy za obor ČSÚ v tomto členění nepublikuje: {duvod} ({L['T20']}).")]
    s = t20.get("sekce", "")
    kraj = v.uzemi["kraj"] or "CZ"
    v_kraji = lokativ(kraj)
    radky = [r for r in t20["radky"] if r["uzemi"] == kraj]
    cr = {r["rok"]: r for r in t20["radky"] if r["uzemi"] == "CZ"}
    casti = []
    if v.uzemi["typ"] == "OKRES":
        casti.append(f"ČSÚ zaměstnance a mzdy za okresy nepublikuje; uvádí se kraj jako nejbližší publikovaná úroveň "
                     f"({L['T20']}).")
    if any("Nejbližší publikovaná úroveň: sekce" in p for p in t20["poznamky"]):
        casti.append(f"ČSÚ zaměstnance a mzdy publikuje jen po sekcích CZ-NACE; uvádí se sekce {s} ({L['T20']}).")
    posl = radky[-1] if radky else None
    c = cr.get(posl["rok"]) if posl else None
    if posl and c and kraj != "CZ":
        h, hc = posl["hodnoty"], c["hodnoty"]
        casti.append(f"Podle ČSÚ (roční zjišťování, pracovištní metoda) pracovalo v roce {posl['rok']} v sekci {s} "
                     f"{v_kraji} {cz(h['zam'])} tis. zaměstnanců (přepočtené počty), tj. {cz(h['zam_podil_cr'])} % "
                     f"zaměstnanců sekce v ČR. Sekce tvořila {cz(h['zam_podil_uzemi'])} % zaměstnanců kraje, což je "
                     f"{vztah(h['zam_podil_uzemi'], hc['zam_podil_uzemi'], lokativ('CZ'))} "
                     f"({cz(hc['zam_podil_uzemi'])} %) ({L['T20']}).")
        casti.append(f"Průměrná hrubá měsíční mzda v sekci byla {cz(h['mzda'])} Kč, tj. {cz(h['mzda_index_cr'])} % mzdy "
                     f"sekce v ČR ({cz(hc['mzda'])} Kč), a dosahovala {cz(h['mzda_index_uzemi'])} % průměrné mzdy "
                     f"všech odvětví kraje; {lokativ('CZ')} je to {cz(hc['mzda_index_uzemi'])} % ({L['g_mzdy']}, "
                     f"{L['T20']}).")
        srov = []
        for r in t20["radky"]:
            if r["uzemi"] not in (kraj, "CZ") and r["rok"] == posl["rok"] and r["hodnoty"]["mzda"] is not None:
                srov.append(f"{lokativ(r['uzemi'])} {cz(r['hodnoty']['mzda'])} Kč "
                            f"({vztah(r['hodnoty']['mzda'], h['mzda'], v_kraji)})")
        if srov:
            casti.append("Ve srovnávacích krajích byla průměrná mzda v sekci " + ", ".join(srov) + f" ({L['T20']}).")
        prvni, c0 = radky[0], cr.get(radky[0]["rok"])
        if c0 and prvni is not posl:
            casti.append(f"Mezi lety {prvni['rok']} a {posl['rok']} vzrostla průměrná mzda v sekci {v_kraji} z "
                         f"{cz(prvni['hodnoty']['mzda'])} Kč na {cz(h['mzda'])} Kč, {lokativ('CZ')} z "
                         f"{cz(c0['hodnoty']['mzda'])} Kč na {cz(hc['mzda'])} Kč; počet zaměstnanců sekce {v_kraji} "
                         f"z {cz(prvni['hodnoty']['zam'])} tis. na {cz(h['zam'])} tis. ({L['T20']}).")
    t21 = v.radky("T21_mzdy_aktualni")
    if t21 and posl:
        rok21 = max(r["rok"] for r in t21)
        posl21 = {(r["uzemi"], r["nace"]): r for r in t21 if r["rok"] == rok21}
        k, cr0, crs = posl21.get((kraj, "0")), posl21.get(("CZ", "0")), posl21.get(("CZ", s))
        veta = (f"Za roky po {posl['rok']} ČSÚ obor × kraj nepublikuje; nejbližší publikované úrovně ukazují pro rok "
                f"{rok21} průměrnou mzdu")
        casti_21 = []
        if k and k["hodnoty"]["mzda"] is not None and kraj != "CZ":
            casti_21.append(f"{v_kraji} za všechna odvětví {cz(k['hodnoty']['mzda'])} Kč")
        if cr0 and cr0["hodnoty"]["mzda"] is not None:
            casti_21.append(f"{lokativ('CZ')} za všechna odvětví {cz(cr0['hodnoty']['mzda'])} Kč")
        if crs and crs["hodnoty"]["mzda"] is not None:
            casti_21.append(f"{lokativ('CZ')} v sekci {s} {cz(crs['hodnoty']['mzda'])} Kč")
        if casti_21:
            casti.append(veta + " " + ", ".join(casti_21) + f" ({L['T21']}).")
    if not casti:
        return [_blok("vidět", f"Údaje ČSÚ o zaměstnancích a mzdách nejsou pro toto území k dispozici ({L['T20']}).")]
    return [_blok("vidět", " ".join(casti))] + zjisteni_kapitoly(v, "zamestnanost", L)


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


def tisice(text: str) -> str:
    """Mezera mezi číslicemi = oddělovač tisíců („1 000“ → 1 000 s úzkou nezlomitelnou mezerou),
    takže sazba číslo nerozdělí a kontrola čísel ho čte jako jedno číslo (1000)."""
    return re.sub(r"(?<=\d)[ \u00a0](?=\d)", NBSP, text)


def nacti_vyklad_analytika(cesta: Path) -> tuple[str, dict[str, list[dict]]]:
    """Vrátí (stav, {oddíl: [bloky]}); stav: chybi | zastupny | hotovy.

    Formát: „## Shrnutí“ (body strany 2, odstavce oddělené prázdným řádkem), pak „## <název
    kapitoly>“ a pod ní „### Proč to tak může být“ a „### Co z toho plyne“; odstavec začínající
    „Hypotéza:“ se vysází jako hypotéza. HTML komentáře (<!-- … -->) jsou pokyny pro analytika
    a do sazby nejdou. Chybí-li některý oddíl nebo obsahuje zástupný text, stav je „zastupny“."""
    if not cesta.exists():
        return "chybi", {}
    text = re.sub(r"<!--.*?-->", "", cesta.read_text(encoding="utf-8"), flags=re.S)
    podle_nazvu = {n: k for k, n in ODDILY.items()}
    bloky: dict[str, list[dict]] = {k: [] for k in ODDILY}
    kapitola = druh = None
    odstavec: list[str] = []

    def uzavri():
        if odstavec and kapitola and druh:
            t = tisice(" ".join(s.strip() for s in odstavec).strip())
            hyp = t.startswith("Hypotéza:")
            bloky[kapitola].append(_blok(druh, t.removeprefix("Hypotéza:").strip() if hyp else t, hyp))
        odstavec.clear()

    for radek in text.splitlines():
        if radek.startswith("## "):
            uzavri()
            kapitola = podle_nazvu.get(radek[3:].strip())
            druh = "shrnutí" if kapitola == "shrnuti" else None
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
             "Rozhodnutí 12: stroj píše dlaždice, „co je vidět“ a zjištění detektoru (zjisteni.json), analytik",
             "píše shrnutí (strana 2), „proč to tak může být“ a „co z toho plyne“. Pravidla:",
             "  * shrnutí: body oddělené prázdným řádkem pod nadpisem „## Shrnutí“,",
             "  * odstavce oddělené prázdným řádkem; odstavec začínající „Hypotéza:“ se vysází jako hypotéza,",
             "  * každé číslo musí být ve vysledek.json i v priloha.xlsx (kontrola čísel v PDF platí i sem),",
             "  * odkazujte na zjištění stálým ID ze zjisteni.json (tvar ZXX-XXXX) a na tabulky;",
             "    nepoužívejte slova „firmy“ ani „aktivní“,",
             f"  * dokud soubor obsahuje „{ZASTUPNY_TEXT}“, nelze report vysázet s --vyklad-schvalen.",
             "-->",
             ""]
    radky += [f"## {ODDILY['shrnuti']}", "", f"{ZASTUPNY_TEXT} – doplní analytik.", ""]
    for nazev in KAPITOLY.values():
        radky += [f"## {nazev}", ""]
        for druh in DRUHY_ANALYTIKA:
            radky += [f"### {druh}", "", f"{ZASTUPNY_TEXT} – doplní analytik.", ""]
    return "\n".join(radky)
