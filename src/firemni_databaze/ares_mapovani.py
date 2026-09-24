"""Převod odpovědí ARES na řádky identitního jádra (bez databáze).

Vstup:  základní záznam (ekonomicke-subjekty) a výpis z OR (ekonomicke-subjekty-vr).
Výstup: MapovanySubjekt – verze subjektu, adresy, vazby, varování a přeskočené údaje.

Zásady (schválené mapování, viz docs/ares_mapovani.md):
  * nic se nehádá – co nejde spolehlivě odvodit, zůstane NULL nebo se
    přeskočí a zapíše do `preskoceno`,
  * platnost vazby = vznik/zánik funkce či členství, zápis/výmaz v OR zvlášť,
  * údaje, které ARES dává jen aktuálně (DIČ, CZ-NACE, insolvence…),
    se vyplní jen v poslední (otevřené) verzi subjektu.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

ICO_RE = re.compile(r"^[0-9]{8}$")
MENY = {"KORUNY": "CZK", "EURA": "EUR"}


@dataclass
class MapovanySubjekt:
    ico: str
    verze: list[dict] = field(default_factory=list)
    adresy: list[dict] = field(default_factory=list)   # {typ, adresa, platnost_od, platnost_do}
    vazby: list[dict] = field(default_factory=list)
    varovani: list[str] = field(default_factory=list)
    preskoceno: list[tuple[str, str]] = field(default_factory=list)  # (důvod, detail)


# ---------------------------------------------------------------------------
# Pomocné převody
# ---------------------------------------------------------------------------

def datum(hodnota) -> date | None:
    return date.fromisoformat(hodnota[:10]) if hodnota else None


def normalizuj(text: str | None) -> str:
    """Bez diakritiky, malými písmeny, interpunkce jako mezery."""
    t = unicodedata.normalize("NFKD", text or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", t)).strip()


def cislo(hodnota) -> Decimal | None:
    """ARES píše desetinnou čárku jako středník: '8000;00'."""
    if hodnota is None:
        return None
    try:
        return Decimal(str(hodnota).strip().replace(";", ".").replace(",", ".").replace(" ", ""))
    except InvalidOperation:
        return None


def obnos(o: dict | None) -> tuple[Decimal | None, str | None]:
    """Částka s měnou; jiný typ než peněžní (např. TEXT) se nepřevádí."""
    if not o or o.get("typObnos") not in MENY:
        return None, None
    castka = cislo(o.get("hodnota"))
    return (castka, MENY[o["typObnos"]]) if castka is not None else (None, None)


def procento(o: dict | None) -> Decimal | None:
    if not o or o.get("typObnos") != "PROCENTA":
        return None
    p = cislo(o.get("hodnota"))
    return p if p is not None and 0 <= p <= 100 else None


_PROC_RE = re.compile(r"^(\d+(?:[.,]\d+)?)\s*%$")
_ZLOMEK_RE = re.compile(r"^(\d+)\s*[/;]\s*(\d+)$")


def podil_procento(velikost: dict | None) -> Decimal | None:
    """Číselný podíl v %, jen když jde text spolehlivě přečíst; jinak None."""
    if not velikost or velikost.get("hodnota") is None:
        return None
    typ = velikost.get("typObnos")
    text = str(velikost["hodnota"]).strip()
    if typ == "PROCENTA":
        p = cislo(text)
    elif typ in ("ZLOMEK", "TEXT"):
        m = _PROC_RE.match(text) if typ == "TEXT" else None
        z = _ZLOMEK_RE.match(text)
        if m:
            p = cislo(m.group(1))
        elif z and int(z.group(2)) > 0:
            p = Decimal(z.group(1)) * 100 / Decimal(z.group(2))
        else:
            return None
    else:
        return None
    if p is None or not 0 <= p <= 100:
        return None
    return p.quantize(Decimal("0.0001"))


def adresa(a: dict) -> dict:
    """Strukturovaná adresa ARES -> řádek dev.adresa."""
    typ_cisla = a.get("typCisloDomovni")
    cislo_domu = a.get("cisloDomovni")
    co = a.get("cisloOrientacni")
    psc = a.get("psc")
    return {
        "ruian_kod": a.get("kodAdresnihoMista"),
        "ulice": a.get("nazevUlice"),
        # typCisloDomovni: 1 = číslo popisné, 2 = číslo evidenční; jinak nevíme
        "cislo_popisne": str(cislo_domu) if cislo_domu is not None and typ_cisla == 1 else None,
        "cislo_evidencni": str(cislo_domu) if cislo_domu is not None and typ_cisla == 2 else None,
        "cislo_orientacni": f"{co}{a.get('cisloOrientacniPismeno') or ''}" if co is not None else None,
        "obec": a.get("nazevObce"),
        "cast_obce": a.get("nazevCastiObce"),
        "psc": f"{psc:05d}" if isinstance(psc, int) else (psc or a.get("pscTxt")),
        "stat": a.get("kodStatu"),
        "kod_obce": a.get("kodObce"),
        "kod_kraje": a.get("kodKraje"),
        "text_puvodni": a.get("textovaAdresa"),
    }


def platne_k(zaznamy: list[tuple], k: date):
    """Hodnota záznamu (od, do, hodnota) platného k datu; při souběhu nejnovější."""
    platne = [z for z in zaznamy if z[0] <= k and (z[1] is None or z[1] > k)]
    return max(platne, key=lambda z: z[0])[2] if platne else None


def intervaly(zaznamy: list[dict], hodnota) -> list[tuple]:
    """Položky VR se zápisem/výmazem -> [(od, do, hodnota)]."""
    vysledek = []
    for z in zaznamy or []:
        od, do = datum(z.get("datumZapisu")), datum(z.get("datumVymazu"))
        h = hodnota(z)
        if od and h is not None and (do is None or do > od):
            vysledek.append((od, do, h))
    return vysledek


# ---------------------------------------------------------------------------
# Role
# ---------------------------------------------------------------------------

def _hodnost(f: str) -> str | None:
    """Předseda / místopředseda / člen z volného textu funkce."""
    if re.search(r"\bmistop", f):
        return "MISTOPREDSEDA"
    # „předseda“, zkratky „předs.“/„před.“ – ne „představenstvo“
    if re.search(r"\bpredsed|\bpreds\b|\bpred\b", f):
        return "PREDSEDA"
    if re.search(r"\bclen", f) or f == "":
        return "CLEN"
    return None


def role(typ_organu: str | None, nazev_organu: str | None, funkce: str | None,
         pravni_forma: str | None) -> str | None:
    """Kód role z číselníku, nebo None, pokud ji nelze spolehlivě určit."""
    n, f = normalizuj(nazev_organu), normalizuj(funkce)
    pevne = {
        "PROKURA": "PROKURISTA",
        "LIKVIDATOR": "LIKVIDATOR",
        "KOMPLEMENTAR": "KOMPLEMENTAR",
        "SPOLECNIK": "SPOLECNIK",
        "KOMANDITISTA": "KOMANDITISTA",
        "AKCIONAR": "JEDINY_AKCIONAR",
    }
    if typ_organu in pevne:
        return pevne[typ_organu]
    h = _hodnost(f)
    if typ_organu == "DOZORCI_RADA":
        return f"{h}_DOZORCI_RADY" if h else None
    if typ_organu == "KONTROLNI_KOMISE":
        return f"{h}_KONTROLNI_KOMISE" if h else None
    if typ_organu != "STATUTARNI_ORGAN":
        return None

    if "komplementar" in n:
        return "KOMPLEMENTAR"
    if "spolecnik" in n:                       # v.o.s.: statutárním orgánem jsou společníci
        return "SPOLECNIK"
    if "statutarni reditel" in n or "statutarni reditel" in f:
        return "STATUTARNI_REDITEL"
    if "spravni rada" in n or "spravni rad" in f:
        return {"PREDSEDA": "PREDSEDA_SPRAVNI_RADY", "CLEN": "CLEN_SPRAVNI_RADY"}.get(h)
    if "jednatel" in f:
        return "JEDNATEL"
    if pravni_forma == "112" and f == "":     # statutárním orgánem s.r.o. je jen jednatel
        return "JEDNATEL"
    if "druzstv" in f and h in ("PREDSEDA", "MISTOPREDSEDA"):
        return f"{h}_DRUZSTVA"
    if "predstav" in n or "predstav" in f or pravni_forma in ("121", "205"):
        # a.s. a družstvo: statutárním orgánem je představenstvo
        # (správní rada a statutární ředitel jsou zachyceny výše);
        # funkce bez hodnosti (např. „generální ředitel“) -> neznámá
        return f"{h}_PREDSTAVENSTVA" if h else None
    return None


# ---------------------------------------------------------------------------
# Subjekt
# ---------------------------------------------------------------------------

def _primarni_zaznam_vr(vr: dict | None) -> dict | None:
    if not vr or "kod" in vr:
        return None
    zaznamy = [z for z in vr.get("zaznamy", []) if z.get("primarniZaznam")]
    return zaznamy[0] if zaznamy else None


def _likvidace(z: dict) -> list[tuple]:
    """Období likvidace podle likvidátorů zapsaných v OR."""
    obdobi = []
    for o in z.get("statutarniOrgany", []):
        if o.get("typOrganu") != "LIKVIDATOR":
            continue
        for m in o.get("clenoveOrganu", []):
            od, do, _, _ = _data_clena(m, o)
            if od:
                obdobi.append((od, do, True))
    return obdobi


def _verze_subjektu(zakl: dict, z: dict | None, vysledek: MapovanySubjekt) -> list[dict]:
    datum_vzniku = datum(zakl.get("datumVzniku"))
    datum_zaniku = datum(zakl.get("datumZaniku"))
    v_insolvenci = (zakl.get("seznamRegistraci") or {}).get("stavZdrojeIr") == "AKTIVNI"
    aktualni = {
        "dic": zakl.get("dic"),
        "cz_nace": sorted(set(zakl.get("czNace") or [])) or None,
        "datum_aktualizace_zdroje": datum(zakl.get("datumAktualizace")),
        "je_v_insolvenci": v_insolvenci,
    }

    if z is None:
        jmena = [(datum_vzniku or date.min, None, zakl.get("obchodniJmeno"))]
        formy = [(datum_vzniku or date.min, None, zakl.get("pravniForma"))]
        spisy, kapitaly, likvidace = [], [], []
    else:
        jmena = intervaly(z.get("obchodniJmeno"), lambda x: x.get("hodnota"))
        formy = intervaly(z.get("pravniForma"), lambda x: x.get("hodnota"))
        spisy = intervaly(
            z.get("spisovaZnacka"),
            lambda x: f"{x['oddil']} {x['vlozka']}/{x['soud']}"
            if x.get("oddil") and x.get("vlozka") and x.get("soud") else None,
        )
        kapitaly = intervaly(z.get("zakladniKapital"),
                             lambda x: obnos(x.get("vklad")) if obnos(x.get("vklad"))[0] is not None else None)
        likvidace = _likvidace(z)
        if not jmena:
            vysledek.varovani.append("výpis z OR bez obchodního jména – použit základní záznam")
            jmena = [(datum_vzniku or date.min, None, zakl.get("obchodniJmeno"))]

    body = {od for od, _, _ in jmena}
    for rada in (jmena, formy, spisy, kapitaly, likvidace):
        for od, do, _ in rada:
            body.add(od)
            if do:
                body.add(do)
    if datum_zaniku:
        body.add(datum_zaniku)
    zacatek = min(od for od, _, _ in jmena)
    body = sorted(b for b in body if b >= zacatek)

    verze: list[dict] = []
    for i, od in enumerate(body):
        do = body[i + 1] if i + 1 < len(body) else None
        nazev = platne_k(jmena, od)
        if nazev is None:
            continue
        kapital, mena = platne_k(kapitaly, od) or (None, None)
        zanikly = datum_zaniku is not None and od >= datum_zaniku
        obsah = {
            "nazev": nazev,
            "pravni_forma_kod": platne_k(formy, od),
            "stav_kod": "ZANIKLY" if zanikly else "AKTIVNI",
            "je_v_likvidaci": bool(platne_k(likvidace, od)) or "v likvidaci" in normalizuj(nazev),
            "je_v_insolvenci": None,
            "datum_vzniku": datum_vzniku,
            "datum_zaniku": datum_zaniku,
            "dic": None,
            "spisova_znacka": platne_k(spisy, od),
            "zakladni_kapital": kapital,
            "zakladni_kapital_mena": mena,
            "cz_nace": None,
            "datum_aktualizace_zdroje": None,
        }
        if verze and verze[-1]["platnost_do"] == od and \
                {k: v for k, v in verze[-1].items() if not k.startswith("platnost")} == obsah:
            verze[-1]["platnost_do"] = do
        else:
            verze.append({**obsah, "platnost_od": od, "platnost_do": do})

    if verze and verze[-1]["platnost_do"] is None:
        verze[-1].update(aktualni)
    if z is None and datum_vzniku is None:
        for v in verze:
            if v["platnost_od"] == date.min:
                v["platnost_od"] = None
    return verze


def _sidla(zakl: dict, z: dict | None, vysledek: MapovanySubjekt) -> list[dict]:
    if z is None:
        return [{"typ": "SIDLO", "adresa": adresa(zakl["sidlo"]), "platnost_od": None,
                 "platnost_do": None}] if zakl.get("sidlo") else []
    polozky = []
    for a in z.get("adresy", []):
        if a.get("typAdresy") != "SIDLO":
            vysledek.preskoceno.append(("neznámý typ adresy", str(a.get("typAdresy"))))
            continue
        od, do = datum(a.get("datumZapisu")), datum(a.get("datumVymazu"))
        if od and (do is None or do > od):
            polozky.append({"typ": "SIDLO", "adresa": adresa(a["adresa"]),
                            "platnost_od": od, "platnost_do": do})
    polozky.sort(key=lambda p: p["platnost_od"])
    # Subjekt má v jednom okamžiku jen jedno sídlo – překryv v datech OR se zkrátí
    for prev, nxt in zip(polozky, polozky[1:]):
        if prev["platnost_do"] is None or prev["platnost_do"] > nxt["platnost_od"]:
            vysledek.varovani.append(
                f"překryv sídel {prev['platnost_od']} / {nxt['platnost_od']} – starší zkráceno")
            prev["platnost_do"] = nxt["platnost_od"]
    polozky = [p for p in polozky if p["platnost_do"] is None or p["platnost_do"] > p["platnost_od"]]
    if not polozky and zakl.get("sidlo"):
        vysledek.varovani.append("výpis z OR bez sídla – použito sídlo ze základního záznamu")
        polozky = [{"typ": "SIDLO", "adresa": adresa(zakl["sidlo"]), "platnost_od": None, "platnost_do": None}]
    return polozky


def _dorucovaci(zakl: dict, sidla: list[dict]) -> list[dict]:
    radky = [r for k, r in sorted((zakl.get("adresaDorucovaci") or {}).items())
             if k.startswith("radekAdresy") and r]
    text = ", ".join(radky)
    if not radky or normalizuj(text) in ("", "ceska republika"):
        return []
    aktualni = [s for s in sidla if s["platnost_do"] is None]
    if aktualni and normalizuj(text) == normalizuj(aktualni[0]["adresa"]["text_puvodni"]):
        return []                               # jen kopie sídla
    stat = (zakl.get("sidlo") or {}).get("kodStatu")
    return [{"typ": "DORUCOVACI",
             "adresa": {"text_puvodni": text, "stat": stat},
             "platnost_od": None, "platnost_do": None}]


# ---------------------------------------------------------------------------
# Vazby
# ---------------------------------------------------------------------------

def _data_clena(m: dict, organ: dict) -> tuple:
    """(platnost_od, platnost_do, zápis do OR, výmaz z OR)."""
    clenstvi = m.get("clenstvi") or {}
    funkce = clenstvi.get("funkce") or {}
    cl = clenstvi.get("clenstvi") or {}
    zapis = datum(m.get("datumZapisu"))
    vymaz = datum(m.get("datumVymazu")) or datum(organ.get("datumVymazu"))
    od = datum(funkce.get("vznikFunkce")) or datum(cl.get("vznikClenstvi")) or zapis
    do = datum(funkce.get("zanikFunkce")) or datum(cl.get("zanikClenstvi")) or vymaz
    if od and do and do < od:
        od, do = zapis, vymaz                  # nekonzistentní data – jen údaje o zápisu
    if zapis and vymaz and vymaz < zapis:
        vymaz = None
    return od, do, zapis, vymaz


def _clen(m: dict, ico: str, vysledek: MapovanySubjekt) -> dict | None:
    fo, po = m.get("fyzickaOsoba"), m.get("pravnickaOsoba")
    if fo:
        if not fo.get("prijmeni"):
            vysledek.preskoceno.append(("osoba bez příjmení", fo.get("textOsoba") or "?"))
            return None
        return {"typ": "OSOBA", "osoba": {
            "jmeno": fo.get("jmeno"),
            "prijmeni": fo["prijmeni"],
            "titul_pred": fo.get("titulPredJmenem"),
            "titul_za": fo.get("titulZaJmenem"),
            "datum_narozeni": datum(fo.get("datumNarozeni")),
            "statni_prislusnost": fo.get("statniObcanstvi"),
        }}
    if po:
        ico_clena = (po.get("ico") or "").strip()
        if ico_clena:
            if not ICO_RE.match(ico_clena):
                vysledek.preskoceno.append(("neplatné IČO člena", ico_clena))
                return None
            if ico_clena == ico:
                vysledek.preskoceno.append(("člen = sám subjekt", ico_clena))
                return None
            return {"typ": "SUBJEKT", "ico": ico_clena}
        stat = (po.get("adresa") or {}).get("kodStatu")
        if not po.get("obchodniJmeno") or not stat:
            vysledek.preskoceno.append(("PO bez IČO a bez názvu/státu", po.get("obchodniJmeno") or "?"))
            return None
        return {"typ": "POJMENOVANY", "nazev": po["obchodniJmeno"], "stat": stat}
    vysledek.preskoceno.append(("člen bez osoby", str(m.get("nazevAngazma"))))
    return None


def _klic_clena(clen: dict) -> tuple:
    if clen["typ"] == "OSOBA":
        o = clen["osoba"]
        return ("OSOBA", normalizuj(o["jmeno"]), normalizuj(o["prijmeni"]), o["datum_narozeni"])
    if clen["typ"] == "SUBJEKT":
        return ("SUBJEKT", clen["ico"])
    return ("POJMENOVANY", normalizuj(clen["nazev"]), clen["stat"])


_PODIL_POLE = ("vklad", "vklad_mena", "podil_text", "podil_procento", "splaceno_procento")


def _vazby(z: dict, ico: str, pravni_forma: str | None, vysledek: MapovanySubjekt) -> list[dict]:
    surove = []

    def pridej(m, organ, typ_organu, funkce, podil=None):
        kod = role(typ_organu, organ.get("nazevOrganu"), funkce, pravni_forma)
        if kod is None:
            vysledek.preskoceno.append(
                ("neznámá role", f"{typ_organu} / {organ.get('nazevOrganu')} / {funkce}"))
            return
        clen = _clen(m, ico, vysledek)
        if clen is None:
            return
        od, do, zapis, vymaz = _data_clena(m, organ)
        radek = {"clen": clen, "role_kod": kod,
                 "organ_puvodni": " / ".join(x for x in (organ.get("nazevOrganu"), funkce) if x) or None,
                 "platnost_od": od, "platnost_do": do,
                 "datum_zapisu_or": zapis, "datum_vymazu_or": vymaz,
                 **dict.fromkeys(_PODIL_POLE)}
        if podil:
            pzapis, pvymaz = datum(podil.get("datumZapisu")), datum(podil.get("datumVymazu"))
            vklad, mena = obnos(podil.get("vklad"))
            velikost = podil.get("velikostPodilu") or {}
            radek.update({
                "vklad": vklad, "vklad_mena": mena,
                "podil_text": velikost.get("hodnota"),
                "podil_procento": podil_procento(velikost),
                "splaceno_procento": procento(podil.get("splaceni")),
                # podíl nemá vlastní vznik/zánik – platí dle zápisu podílu v OR
                "platnost_od": pzapis or od,
                "platnost_do": pvymaz or do,
                "datum_zapisu_or": pzapis or zapis,
                "datum_vymazu_or": pvymaz or vymaz,
            })
            if radek["platnost_od"] and radek["platnost_do"] and radek["platnost_do"] < radek["platnost_od"]:
                radek["platnost_do"] = radek["platnost_od"]
        surove.append(radek)

    for skupina in ("statutarniOrgany", "ostatniOrgany", "akcionari"):
        for organ in z.get(skupina, []):
            for m in organ.get("clenoveOrganu", []):
                funkce = ((m.get("clenstvi") or {}).get("funkce") or {}).get("nazev")
                pridej(m, organ, organ.get("typOrganu"), funkce)

    for organ in z.get("spolecnici", []):
        typ = organ.get("typOrganu")
        if typ == "VKLAD_CLEN_DRUZSTVA_SEKCE":
            vysledek.preskoceno.append(("mimo rozsah: člen družstva", str(len(organ.get("spolecnik", [])))))
            continue
        for sp in organ.get("spolecnik", []):
            osoba = dict(sp.get("osoba") or {})
            osoba.setdefault("datumZapisu", sp.get("datumZapisu"))
            osoba.setdefault("datumVymazu", sp.get("datumVymazu"))
            for podil in sp.get("podil") or [None]:
                pridej(osoba, organ, typ, None, podil)

    return _slouc_vazby(surove)


def _slouc_vazby(radky: list[dict]) -> list[dict]:
    """Sloučí opakované zápisy téže vazby (OR přepisuje člena při každé změně).

    1) stejný člen + role + podíl + platnost_od -> jeden řádek,
    2) navazující řádky se stejným obsahem (do == od dalšího) -> jeden řádek.
    """
    skupiny: dict[tuple, dict] = {}
    for r in radky:
        klic = (_klic_clena(r["clen"]), r["role_kod"], tuple(r[p] for p in _PODIL_POLE), r["platnost_od"])
        if klic not in skupiny:
            skupiny[klic] = {**r, "_posledni": r["datum_zapisu_or"]}
            continue
        s = skupiny[klic]
        s["platnost_do"] = None if None in (s["platnost_do"], r["platnost_do"]) else max(s["platnost_do"], r["platnost_do"])
        zapisy = [d for d in (s["datum_zapisu_or"], r["datum_zapisu_or"]) if d]
        s["datum_zapisu_or"] = min(zapisy) if zapisy else None
        s["datum_vymazu_or"] = None if None in (s["datum_vymazu_or"], r["datum_vymazu_or"]) \
            else max(s["datum_vymazu_or"], r["datum_vymazu_or"])
        if r["datum_zapisu_or"] and (not s.get("_posledni") or r["datum_zapisu_or"] > s["_posledni"]):
            s["clen"], s["_posledni"] = r["clen"], r["datum_zapisu_or"]

    serazene = sorted(skupiny.values(), key=lambda r: (str(_klic_clena(r["clen"])), r["role_kod"],
                                                       r["platnost_od"] or date.min))
    vysledek: list[dict] = []
    for r in serazene:
        r.pop("_posledni", None)
        p = vysledek[-1] if vysledek else None
        if p and _klic_clena(p["clen"]) == _klic_clena(r["clen"]) and p["role_kod"] == r["role_kod"] \
                and all(p[x] == r[x] for x in _PODIL_POLE) \
                and p["platnost_do"] is not None and p["platnost_do"] == r["platnost_od"]:
            p["platnost_do"] = r["platnost_do"]
            p["datum_vymazu_or"] = r["datum_vymazu_or"]
            p["clen"] = r["clen"]
            continue
        vysledek.append(r)
    return vysledek


# ---------------------------------------------------------------------------
# Vstupní bod
# ---------------------------------------------------------------------------

def mapuj(zakl: dict, vr: dict | None) -> MapovanySubjekt:
    ico = zakl.get("ico")
    if not ico or not ICO_RE.match(ico):
        raise ValueError(f"subjekt bez platného IČO (icoId={zakl.get('icoId')})")
    vysledek = MapovanySubjekt(ico=ico)
    z = _primarni_zaznam_vr(vr)
    vysledek.verze = _verze_subjektu(zakl, z, vysledek)
    sidla = _sidla(zakl, z, vysledek)
    vysledek.adresy = sidla + _dorucovaci(zakl, sidla)
    if z is not None:
        forma = vysledek.verze[-1]["pravni_forma_kod"] if vysledek.verze else zakl.get("pravniForma")
        vysledek.vazby = _vazby(z, ico, forma, vysledek)
    return vysledek
