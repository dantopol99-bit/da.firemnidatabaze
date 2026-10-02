"""Modelové odhady ekonomického profilu (Blok 8) – NE fakta, nevstupují do detektoru zjištění.

Vstupy:
  * RES: subjekty oboru v území podle KATPO (kategorie počtu zaměstnanců) a FO/PO,
  * ČSÚ: podíl subjektů se zjištěnou aktivitou v sekci a kraji (RES02QT1),
  * Eurostat, regionální účty: hrubá přidaná hodnota skupiny A*10 v území (mil. Kč, běžné ceny),
  * Eurostat, SBS (sbs_sc_ovw): za ČR podle velikostních tříd – podniky, přidaná hodnota, čistý obrat,
    hrubý provozní přebytek (mil. EUR) a kurz CZK/EUR (ert_bil_eur_a).

Postup (poslední společný rok regionálních účtů a SBS):
  a) počty subjektů v území po velikostních třídách SBS (0–9, 10–19, 20–49, 50–249, 250+) z KATPO,
     zúžené na podíl se zjištěnou aktivitou (jednotný podíl sekce × kraj, struktura se tím nemění);
     „Neuvedeno“: základní varianta PO do nejmenší třídy a FO do „bez zaměstnanců“ (obojí 0–9),
     alternativní varianta poměrně podle známé struktury FO, resp. PO – obě varianty dávají pásmo,
  b) krajská přidaná hodnota se rozpočítá mezi třídy podle počtu subjektů × celostátní přidané hodnoty
     na podnik třídy (SBS); součet tříd = krajský celek přesně,
  c) obrat třídy = přidaná hodnota třídy × celostátní poměr obrat / přidaná hodnota v třídě,
  d) typický obrat podniku třídy = celostátní obrat / počet podniků (SBS, převod kurzem),
  e) koncentrace = podíl přidané hodnoty a obratu tříd s 10+ a 50+ zaměstnanými osobami,
  f) marže (hrubý provozní přebytek / obrat) – fakt za ČR, ne odhad za kraj.
Ochrana malých buněk: třída s méně než PRAH subjekty v území (RES) se sloučí s vyšší, aby se ze
zveřejněných hodnot nedal zpětně odvodit malý počet subjektů.
"""

from firemni_databaze.report_potlaceni import PRAH

TRIDY = ("0-9", "10-19", "20-49", "50-249", "GE250")
NAZVY_TRID = {"0-9": "0–9 osob", "10-19": "10–19 osob", "20-49": "20–49 osob", "50-249": "50–249 osob",
              "GE250": "250 a více osob"}
# KATPO (číselník 579, počet zaměstnanců) → třída SBS (počet zaměstnaných osob)
KATPO_TRIDA = {"110": "0-9", "120": "0-9", "130": "0-9", "210": "10-19", "220": "20-49", "230": "20-49",
               "240": "50-249", "310": "50-249", "320": "50-249"}
NEUVEDENO = "000"
FO_FORMY = frozenset({"101", "102", "103", "104", "105", "106", "107", "108", "424", "425"})


def trida_katpo(katpo: str) -> str | None:
    if katpo == NEUVEDENO:
        return None
    return KATPO_TRIDA.get(katpo, "GE250")


def pocty_trid(subjekty: list[tuple], varianta: str) -> dict[str, float]:
    """subjekty: [(forma, katpo)]; varianta 'zakladni' (Neuvedeno → 0–9) | 'pomerna' (Neuvedeno poměrně
    podle známé struktury FO, resp. PO)."""
    znamo = {"FO": {t: 0 for t in TRIDY}, "PO": {t: 0 for t in TRIDY}}
    neuv = {"FO": 0, "PO": 0}
    for forma, katpo in subjekty:
        g = "FO" if forma in FO_FORMY else "PO"
        t = trida_katpo(katpo)
        if t is None:
            neuv[g] += 1
        else:
            znamo[g][t] += 1
    out = {t: 0.0 for t in TRIDY}
    for g in ("FO", "PO"):
        celkem_znamo = sum(znamo[g].values())
        for t in TRIDY:
            out[t] += znamo[g][t]
            if varianta == "zakladni" or not celkem_znamo:
                if t == "0-9":
                    out[t] += neuv[g]
            else:
                out[t] += neuv[g] * znamo[g][t] / celkem_znamo
    return out


def rozpocet(pocty: dict[str, float], podil_aktivnich: float, hph_uzemi: float, sbs: dict) -> dict:
    """Kroky a)–c) a e) jedné varianty. sbs: {(ukazatel, třída): hodnota} za ČR v jednom roce."""
    aktivni = {t: pocty[t] * podil_aktivnich for t in TRIDY}
    vaha = {t: aktivni[t] * sbs[("AV_MEUR", t)] / sbs[("ENT_NR", t)] for t in TRIDY}
    soucet_vah = sum(vaha.values())
    hph = {t: hph_uzemi * vaha[t] / soucet_vah for t in TRIDY}
    obrat = {t: hph[t] * sbs[("NETTUR_MEUR", t)] / sbs[("AV_MEUR", t)] for t in TRIDY}
    obrat_celkem = sum(obrat.values())
    nad10 = ("10-19", "20-49", "50-249", "GE250")
    nad50 = ("50-249", "GE250")
    return {
        "aktivni": aktivni, "hph": hph, "obrat": obrat, "obrat_celkem": obrat_celkem,
        "hph_podil_10": 100 * sum(hph[t] for t in nad10) / hph_uzemi,
        "hph_podil_50": 100 * sum(hph[t] for t in nad50) / hph_uzemi,
        "obrat_podil_10": 100 * sum(obrat[t] for t in nad10) / obrat_celkem,
        "obrat_podil_50": 100 * sum(obrat[t] for t in nad50) / obrat_celkem,
    }


def skupiny_publikace(pocty_res: dict[str, float], prah: int = PRAH) -> list[tuple[str, tuple[str, ...]]]:
    """Třídy pro zveřejnění: třída pod prahem (v obou variantách) se slučuje s vyšší třídou;
    zbytek nahoře pod prahem se sloučí dolů. Vrací [(název, (třídy…))]."""
    skupiny, rozpracovane = [], []
    for t in TRIDY:
        rozpracovane.append(t)
        if sum(pocty_res[x] for x in rozpracovane) >= prah:
            skupiny.append(tuple(rozpracovane))
            rozpracovane = []
    if rozpracovane:
        if skupiny:
            skupiny[-1] = skupiny[-1] + tuple(rozpracovane)
        else:
            skupiny.append(tuple(rozpracovane))
    nazvy = []
    for sk in skupiny:
        if len(sk) == 1:
            nazvy.append((NAZVY_TRID[sk[0]], sk))
        else:
            od = NAZVY_TRID[sk[0]].split("–")[0].split(" ")[0]
            nazvy.append((f"{od} a více osob" if sk[-1] == "GE250" else
                          f"{od}–{NAZVY_TRID[sk[-1]].split('–')[1]}", sk))
    return nazvy


def pasmo(a: float, b: float, mista: int = 0) -> tuple[float, float]:
    lo, hi = sorted((a, b))
    return (round(lo, mista), round(hi, mista)) if mista else (round(lo), round(hi))
