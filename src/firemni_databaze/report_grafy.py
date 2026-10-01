"""Knihovna grafů Oborově-regionálního reportu (nejvýš 8 typů, jednotný vzhled).

Grafy se v reportu smějí kreslit JEN funkcemi z této knihovny (seznam GRAFY).
Každá funkce dostane hotová čísla z výstupu JSON Bloku 2 – nic nepočítá,
jen je kreslí – a uloží SVG (text převedený na křivky, takže čísla v grafech
nejsou textem PDF; datum snímku a zdroj nese popisek grafu v sazbě).

Barvy: referenční paleta (skill dataviz, světlý režim, validováno):
  slot 1 modrá = zkoumané území / hlavní řada, slot 2 oranžová = srovnávací
  kraje / druhá řada, šedá = ostatní; „Neuvedeno“ a „ostatní“ šedě se šrafou
  (identita nikdy jen barvou).
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

FONTY = Path(__file__).resolve().parents[2] / "reporty" / "sablona" / "fonty"
for f in FONTY.glob("*.ttf"):
    font_manager.fontManager.addfont(str(f))

MODRA, ORANZOVA, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SEDA, SEDA_TMAVA = "#c9c8c3", "#8a8984"
TEXT, TEXT_2, MRIZKA, POVRCH = "#0b0b0b", "#52514e", "#e6e5e1", "#ffffff"
SRAFA = "////"
SIRKA_CM = 16.0

plt.rcParams.update({
    "font.family": "IBM Plex Sans", "font.size": 8.5, "text.color": TEXT,
    "axes.edgecolor": MRIZKA, "axes.labelcolor": TEXT_2, "axes.linewidth": 0.6,
    "xtick.color": TEXT_2, "ytick.color": TEXT_2, "xtick.major.size": 0, "ytick.major.size": 0,
    "axes.spines.top": False, "axes.spines.right": False,
    "svg.fonttype": "path", "hatch.color": SEDA_TMAVA, "hatch.linewidth": 0.6,
    "legend.frameon": False, "legend.fontsize": 8,
})


def _cz(v: float, mista: int = 0) -> str:
    s = f"{v:,.{mista}f}".replace(",", " ").replace(".", ",")
    return s


def _presne(v: float) -> str:
    """Popisek hodnoty přesně podle JSON (bez zaokrouhlení): 32.99 → 32,99, 1.0 → 1."""
    from firemni_databaze.report_vyklad import cz
    return cz(v)


def _obr(vyska_cm: float):
    fig, ax = plt.subplots(figsize=(SIRKA_CM / 2.54, vyska_cm / 2.54), dpi=150)
    fig.patch.set_facecolor(POVRCH)
    ax.set_facecolor(POVRCH)
    return fig, ax


def _mrizka(ax, osa: str) -> None:
    ax.grid(axis=osa, color=MRIZKA, linewidth=0.5)
    ax.set_axisbelow(True)


def _uloz(fig, cesta: Path) -> Path:
    fig.tight_layout(pad=0.4)
    fig.savefig(cesta, format="svg", facecolor=POVRCH)
    plt.close(fig)
    return cesta


def _barva(role: str) -> str:
    return {"uzemi": MODRA, "srovnani": ORANZOVA, "cr": SEDA_TMAVA}.get(role, SEDA)


# ---------------------------------------------------------------------------
# 1. Pořadí území (vodorovné sloupce, zvýraznění zkoumaného a srovnávacích území)
# ---------------------------------------------------------------------------

def poradi(polozky: list[dict], cesta: Path, popis_osy: str, referencni: tuple[str, float] | None = None,
           mista: int = 0) -> Path:
    """polozky: [{popis, hodnota, role: uzemi|srovnani|jine}] v pořadí shora dolů."""
    fig, ax = _obr(0.55 * len(polozky) + 1.4)
    y = list(range(len(polozky)))[::-1]
    ax.barh(y, [p["hodnota"] for p in polozky], height=0.62, color=[_barva(p["role"]) for p in polozky],
            edgecolor=POVRCH, linewidth=1)
    ax.set_yticks(y, [p["popis"] for p in polozky])
    for yi, p in zip(y, polozky):
        if p["role"] in ("uzemi", "srovnani"):
            ax.text(p["hodnota"], yi, " " + _presne(p["hodnota"]), va="center", fontsize=7.5, color=TEXT)
            ax.get_yticklabels()[len(polozky) - 1 - yi].set_fontweight("bold")
    if referencni:
        ax.axvline(referencni[1], color=TEXT_2, linewidth=0.8)
        ax.text(referencni[1], len(polozky) - 0.35, f" {referencni[0]}", fontsize=7, color=TEXT_2, va="bottom")
    ax.set_xlabel(popis_osy)
    ax.xaxis.set_major_formatter(lambda v, _: _cz(v, mista if v != int(v) else 0))
    _mrizka(ax, "x")
    ax.spines["left"].set_visible(False)
    return _uloz(fig, cesta)


# ---------------------------------------------------------------------------
# 2. Index proti referenci (např. lokalizační koeficient kolem 1)
# ---------------------------------------------------------------------------

def index_srovnani(polozky: list[dict], cesta: Path, popis_osy: str, reference: float = 1.0) -> Path:
    """polozky: [{popis, hodnota, role}] – sloupce vycházejí z reference (1 = průměr ČR)."""
    fig, ax = _obr(0.62 * len(polozky) + 1.3)
    y = list(range(len(polozky)))[::-1]
    ax.barh(y, [p["hodnota"] - reference for p in polozky], left=reference, height=0.55,
            color=[_barva(p["role"]) for p in polozky], edgecolor=POVRCH, linewidth=1)
    ax.set_yticks(y, [p["popis"] for p in polozky])
    for yi, p in zip(y, polozky):
        zarovnani = "left" if p["hodnota"] >= reference else "right"
        ax.text(p["hodnota"], yi, f" {_presne(p['hodnota'])} ", va="center", ha=zarovnani, fontsize=7.5)
    ax.axvline(reference, color=TEXT, linewidth=0.9)
    rozsah = max(abs(p["hodnota"] - reference) for p in polozky) * 1.35 or 0.1
    ax.set_xlim(reference - rozsah, reference + rozsah)
    ax.set_xlabel(popis_osy)
    ax.xaxis.set_major_formatter(lambda v, _: _cz(v, 1))
    _mrizka(ax, "x")
    ax.spines["left"].set_visible(False)
    return _uloz(fig, cesta)


# ---------------------------------------------------------------------------
# 3. Skladba celku (jeden 100% pruh, nejvýš 3 části)
# ---------------------------------------------------------------------------

def skladba(casti: list[dict], cesta: Path) -> Path:
    """casti: [{popis, podil}] – podíly v %, součet 100; nejvýš 3 části."""
    if len(casti) > 3:
        raise ValueError("skladba: nejvýš 3 části (víc → rozložení)")
    fig, ax = _obr(2.0)
    vlevo = 0.0
    for i, c in enumerate(casti):
        ax.barh([0], [c["podil"]], left=vlevo, height=0.5, color=(MODRA, ORANZOVA, AQUA)[i],
                edgecolor=POVRCH, linewidth=2, label=f"{c['popis']} ({_presne(c['podil'])} %)")
        vlevo += c["podil"]
    ax.set_xlim(0, 100)
    ax.set_yticks([])
    ax.xaxis.set_major_formatter(lambda v, _: f"{_cz(v)} %")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.45), ncol=len(casti))
    ax.spines["left"].set_visible(False)
    return _uloz(fig, cesta)


# ---------------------------------------------------------------------------
# 4. Rozložení do kategorií (svislé sloupce, jedna řada; Neuvedeno/ostatní šrafou)
# ---------------------------------------------------------------------------

def rozlozeni(kategorie: list[dict], cesta: Path, popis_osy: str = "Podíl (%)") -> Path:
    """kategorie: [{popis, podil, zvlastni: bool}] v pevném pořadí; zvlastni = Neuvedeno / ostatní."""
    fig, ax = _obr(5.2)
    x = range(len(kategorie))
    for xi, k in zip(x, kategorie):
        ax.bar(xi, k["podil"], width=0.62, color=SEDA if k.get("zvlastni") else MODRA,
               hatch=SRAFA if k.get("zvlastni") else None, edgecolor=POVRCH, linewidth=1)
        ax.text(xi, k["podil"], f"{_presne(k['podil'])} %", ha="center", va="bottom", fontsize=7.5)
    ax.set_xticks(list(x), [k["popis"] for k in kategorie])
    ax.set_ylabel(popis_osy)
    ax.set_ylim(0, max(k["podil"] for k in kategorie) * 1.18)
    ax.yaxis.set_major_formatter(lambda v, _: _cz(v))
    _mrizka(ax, "y")
    return _uloz(fig, cesta)


# ---------------------------------------------------------------------------
# 5. Vznik a zánik v letech (seskupené sloupce, mimořádný rok šrafou)
# ---------------------------------------------------------------------------

def vznik_zanik(roky: list[dict], cesta: Path) -> Path:
    """roky: [{rok, vzniklé, zaniklé, mimoradny_zanik: bool, neuplny: bool}]"""
    fig, ax = _obr(5.4)
    x = list(range(len(roky)))
    s = 0.36
    ax.bar([i - s / 2 for i in x], [r["vzniklé"] for r in roky], width=s, color=MODRA, label="vzniklé",
           edgecolor=POVRCH, linewidth=1)
    for i, r in zip(x, roky):
        ax.bar(i + s / 2, r["zaniklé"], width=s, color=ORANZOVA, edgecolor=POVRCH, linewidth=1,
               hatch=SRAFA if r.get("mimoradny_zanik") else None, label="zaniklé" if i == 0 else None)
    ax.set_xticks(x, [r["rok"] + (" (část)" if r.get("neuplny") else "") for r in roky])
    if any(r.get("mimoradny_zanik") for r in roky):
        i = next(i for i, r in zip(x, roky) if r.get("mimoradny_zanik"))
        ax.annotate("mimořádný výkyv zániků", (i + s, roky[i]["zaniklé"]), xytext=(6, 0),
                    textcoords="offset points", fontsize=7, color=TEXT_2, va="top", ha="left")
    ax.yaxis.set_major_formatter(lambda v, _: _cz(v))
    ax.set_ylabel("Počet subjektů")
    ax.legend(loc="upper right")
    _mrizka(ax, "y")
    return _uloz(fig, cesta)


# ---------------------------------------------------------------------------
# 6. Míry v čase (čáry; malé násobky, jedna osa na panel)
# ---------------------------------------------------------------------------

def miry_v_case(panely: list[dict], cesta: Path, popis_osy: str = "%") -> Path:
    """panely: [{nazev, rady: [{popis, body: [(rok, hodnota | None)], role: uzemi|cr|srovnani}]}] – nejvýš 4 řady
    na panel (zkoumané území modře, ČR tmavě šedě, srovnávací kraje oranžově, odlišené typem čáry a značkou).
    Starší volání s hlavni=True/False odpovídá roli uzemi/cr. Chybějící hodnota (pod prahem) = mezera v čáře."""
    fig, osy = plt.subplots(1, len(panely), figsize=(SIRKA_CM / 2.54, 5.8 / 2.54), dpi=150, sharey=True)
    fig.patch.set_facecolor(POVRCH)
    osy = osy if len(panely) > 1 else [osy]
    styly_srovnani = iter([("--", "s"), (":", "^"), ("-.", "D")])
    styl_rady: dict[str, tuple[str, str]] = {}
    for ax, p in zip(osy, panely):
        ax.set_facecolor(POVRCH)
        if len(p["rady"]) > 4:
            raise ValueError("graf míry v čase: nejvýš 4 řady na panel")
        vsechny_roky = sorted({rok for r in p["rady"] for rok, _ in r["body"]})
        for r in p["rady"]:
            role = r.get("role") or ("uzemi" if r.get("hlavni") else "cr")
            if role == "srovnani" and r["popis"] not in styl_rady:
                styl_rady[r["popis"]] = next(styly_srovnani)
            cara, znacka = styl_rady.get(r["popis"], ("-", "o"))
            roky = [rok for rok, _ in r["body"]]
            hodnoty = [float("nan") if h is None else h for _, h in r["body"]]
            ax.plot(roky, hodnoty, color=_barva(role), linestyle=cara, marker=znacka, markersize=3.5,
                    linewidth=2 if role == "uzemi" else 1.2, label=r["popis"], zorder=3 if role == "uzemi" else 2)
        ax.set_title(p["nazev"], fontsize=8.5, color=TEXT, loc="left")
        ax.set_xticks(vsechny_roky, [str(r) for r in vsechny_roky])
        ax.yaxis.set_major_formatter(lambda v, _: _cz(v, 1) if v % 1 else _cz(v))
        _mrizka(ax, "y")
    osy[0].set_ylabel(popis_osy)
    ruce, popisy = [], []
    for ax in osy:
        for h, l in zip(*ax.get_legend_handles_labels()):
            if l not in popisy:
                ruce.append(h)
                popisy.append(l)
    fig.legend(ruce, popisy, loc="lower center", ncol=min(len(popisy), 4), fontsize=7.5)
    fig.tight_layout(pad=0.4, rect=(0, 0.11, 1, 1))
    fig.savefig(cesta, format="svg", facecolor=POVRCH)
    plt.close(fig)
    return cesta


GRAFY = {f.__name__: f for f in (poradi, index_srovnani, skladba, rozlozeni, vznik_zanik, miry_v_case)}
assert len(GRAFY) <= 8, "knihovna smí mít nejvýš 8 typů grafů"
