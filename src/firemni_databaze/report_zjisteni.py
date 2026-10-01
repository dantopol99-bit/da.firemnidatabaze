"""Detektor zjištění Oborově-regionálního reportu (Blok 4, rozhodnutí 12).

Ze ZVEŘEJNĚNÝCH čísel tabulek výstupu (vysledek.json) najde odchylky, které stojí
za pozornost, a každou popíše jednou věcnou větou bez interpretace. „Proč“ a „co
z toho plyne“ píše analytik (reporty/vyklad/<id_reportu>.md), ne stroj.

Každé zjištění má:
  typ          odchylka_od_cr | zmena_trendu | rozdily_uvnitr_uzemi | aktivita_oboru | divergence_poradi |
               mzdy_zamestnanost
  sila         číselná a porovnatelná: |hodnota / srovnání − 1| (relativní rozdíl);
               u divergence pořadí |p1 − p2| / (počet území − 1); obojí bezrozměrné, 0 = žádný rozdíl
  hodnota, srovnani, rozdil_pct (absolutně, %), smer (vyšší / nižší)
  cisla        čísla s odkazem na tabulku, řádek a sloupec, odkud jsou převzatá
  popis        jedna věta věcného popisu
Zjištění se řadí podle síly. Rozdíl menší než 3 % relativně se jako zjištění nehlásí
a v textu se popisuje jako „srovnatelné“ (funkce srovnej). Položky struktury, jejichž
podíl je v území i v ČR pod 5 %, se nehlásí (relativní rozdíl malých podílů je nestabilní);
u pořadí okresů se nehlásí posun o jedno místo.
"""

from firemni_databaze.report_cestina import lokativ
from firemni_databaze.report_vyklad import cz

PRAH_ZJISTENI = 0.03        # 3 % relativně
MIN_PODIL_STRUKTURY = 5.0   # %
PORADI_TYPU = ["odchylka_od_cr", "zmena_trendu", "rozdily_uvnitr_uzemi", "aktivita_oboru", "divergence_poradi",
               "mzdy_zamestnanost"]
NAZVY_TYPU = {
    "odchylka_od_cr": "odchylka od ČR",
    "zmena_trendu": "změna trendu",
    "rozdily_uvnitr_uzemi": "rozdíly uvnitř území",
    "aktivita_oboru": "aktivita oboru vůči kraji",
    "divergence_poradi": "divergence pořadí",
    "mzdy_zamestnanost": "mzdy a zaměstnanost",
}
STRUKTURA = {   # benchmarková tabulka → (název členění, jmenovatel podílu)
    "T13_bench_fo_po": ("Typ osoby", "registrovaných subjektech oboru"),
    "T14_bench_pravni_forma": ("Právní forma", "registrovaných subjektech oboru"),
    "T15_bench_velikost_fo": ("Velikost FO", "FO oboru"),
    "T16_bench_velikost_po": ("Velikost PO", "PO oboru"),
    "T17_bench_vekova_struktura": ("Věk subjektu", "registrovaných subjektech oboru"),
}


def relativni(a: float, b: float) -> float | None:
    return a / b - 1 if b else None


def srovnej(a: float | None, b: float | None, vyssi: str = "vyšší", nizsi: str = "nižší") -> str | None:
    """Slovní porovnání dvou zveřejněných čísel s pravidlem 3 %: pod ním „srovnatelné“."""
    if a is None or b is None or not b:
        return None
    r = relativni(a, b)
    if abs(r) < PRAH_ZJISTENI:
        return "srovnatelné"
    return vyssi if r > 0 else nizsi


def _cislo(popis: str, hodnota, tabulka: str, radek: str, sloupec: str) -> dict:
    return {"popis": popis, "hodnota": hodnota, "tabulka": tabulka, "radek": radek, "sloupec": sloupec}


class _Detektor:
    def __init__(self, vysledek: dict):
        self.meta = vysledek["meta"]
        self.tab = {t["kod"]: t for t in vysledek["tabulky"] if t["zverejneno"]}
        uz = self.meta["uzemi"]
        self.uz = uz
        self.v_uz = lokativ(uz["kod"])
        self.v_cr = lokativ("CZ")
        self.zjisteni: list[dict] = []

    def radky(self, kod: str, typ: str | None = "polozka") -> list[dict]:
        t = self.tab.get(kod)
        return [r for r in t["radky"] if typ is None or r["typ"] == typ] if t else []

    def t01(self, ukazatel: str) -> tuple[dict | None, object]:
        r = next((r for r in self.radky("T01_zakladni", "ukazatel") if r["ukazatele"]["hodnota"] == ukazatel), None)
        return r, (r["hodnoty"]["hodnota"] if r else None)

    def pridej(self, typ: str, podtyp: str, a: float, b: float, cisla: list[dict], popis_fn, sila: float | None = None,
               rozdil: bool = True) -> None:
        """popis_fn(rozdil_text) → věta; rozdil_text je „o 21 % vyšší“ apod."""
        if a is None or b is None:
            return
        r = relativni(a, b) if rozdil else None
        s = abs(r) if sila is None else sila
        if s is None or s < PRAH_ZJISTENI:
            return
        rozdil_pct = round(abs(100 * r), 1) if r is not None else None
        smer = ("vyšší" if r > 0 else "nižší") if r is not None else None
        self.zjisteni.append({
            "typ": typ, "typ_nazev": NAZVY_TYPU[typ], "podtyp": podtyp, "sila": round(s, 4),
            "hodnota": a, "srovnani": b, "rozdil_pct": rozdil_pct, "smer": smer,
            "cisla": cisla, "popis": popis_fn(f"relativně o {cz(rozdil_pct)} % {smer}" if r is not None else ""),
        })

    # --- 1. odchylka od ČR -------------------------------------------------------------------
    def odchylka_od_cr(self) -> None:
        if self.uz["typ"] == "CR":
            return
        t02 = self.radky("T02_srovnani")
        cr = next((r for r in t02 if r["promenna"] == "obor@CZ"), None)
        uz = next((r for r in t02 if r["popis"].endswith("(zkoumané území)")), None)
        if not cr or not uz:
            return
        lq, lq_cr = uz["hodnoty"]["lq"], cr["hodnoty"]["lq"]
        self.pridej("odchylka_od_cr", "LQ", lq, lq_cr, [
            _cislo(f"Lokalizační koeficient – {uz['popis']}", lq, "T02_srovnani", uz["popis"], "lq"),
            _cislo("Lokalizační koeficient – Česko", lq_cr, "T02_srovnani", cr["popis"], "lq")],
            lambda d: f"Lokalizační koeficient oboru je {self.v_uz} {cz(lq)} proti {cz(lq_cr)} za ČR ({d}).")
        h, h_cr = uz["hodnoty"]["hustota"], cr["hodnoty"]["hustota"]
        self.pridej("odchylka_od_cr", "hustota", h, h_cr, [
            _cislo(f"Na 1\u202f000 obyvatel – {uz['popis']}", h, "T02_srovnani", uz["popis"], "hustota"),
            _cislo("Na 1\u202f000 obyvatel – Česko", h_cr, "T02_srovnani", cr["popis"], "hustota")],
            lambda d: f"Na 1\u202f000 obyvatel připadá {self.v_uz} {cz(h)} registrovaných subjektů oboru, "
                      f"{self.v_cr} {cz(h_cr)} ({d}).")
        for kod, (cleneni, jmenovatel) in STRUKTURA.items():
            for r in self.radky(kod):
                a, b = r["hodnoty"].get("uzemi"), r["hodnoty"].get("cr")
                if a is None or b is None or (a < MIN_PODIL_STRUKTURY and b < MIN_PODIL_STRUKTURY):
                    continue
                self.pridej("odchylka_od_cr", f"struktura: {cleneni}", a, b, [
                    _cislo(f"{cleneni} – „{r['popis']}“, {self.uz['nazev']} (%)", a, kod, r["popis"], "uzemi"),
                    _cislo(f"{cleneni} – „{r['popis']}“, Česko (%)", b, kod, r["popis"], "cr")],
                    lambda d, r=r, a=a, b=b, cleneni=cleneni, jmenovatel=jmenovatel:
                        f"{cleneni} – „{r['popis']}“: podíl na {jmenovatel} je {self.v_uz} {cz(a)} %, "
                        f"{self.v_cr} {cz(b)} % ({d}).")

    # --- 2. změna trendu: míra zániku PO --------------------------------------------------------
    def zmena_trendu(self) -> None:
        t18 = self.tab.get("T18_mira_zaniku_po")
        if not t18:
            return
        obdobi = t18.get("obdobi", "srovnatelné období")
        radky = self.radky("T18_mira_zaniku_po")
        uz = [r for r in radky if r["uzemi"] == self.uz["kod"]]
        cr = {r["rok"]: r for r in radky if r["uzemi"] == "CZ"}
        for sl, nazev_obd, druh in (("mira", "za rok", "rok"), ("mira_obd", f"za období {obdobi}", "období")):
            rady = [(r["rok"], r) for r in uz if r["hodnoty"][sl] is not None]
            if len(rady) >= 2:
                rok, posl = rady[-1]
                predchozi = rady[:-1]
                prumer = round(sum(r["hodnoty"][sl] for _, r in predchozi) / len(predchozi), 2)
                roky_txt = (f"{predchozi[0][0]}–{predchozi[-1][0]}" if len(predchozi) > 1 else str(predchozi[0][0]))
                a = posl["hodnoty"][sl]
                self.pridej("zmena_trendu", f"míra zániku PO {nazev_obd}: poslední rok proti předchozím", a, prumer,
                            [_cislo(f"Míra zániku PO {nazev_obd} {rok} (%)", a, "T18_mira_zaniku_po", posl["popis"], sl)]
                            + [_cislo(f"Míra zániku PO {nazev_obd} {y} (%)", r["hodnoty"][sl], "T18_mira_zaniku_po",
                                      r["popis"], sl) for y, r in predchozi]
                            + [_cislo(f"Průměr let {roky_txt} (%)", prumer, "T19_zjisteni", "", "srovnani")],
                            lambda d, rok=rok, a=a, prumer=prumer, roky_txt=roky_txt, nazev_obd=nazev_obd:
                                f"Míra zániku PO v oboru {nazev_obd} {rok} je {self.v_uz} {cz(a)} %, průměr "
                                f"{'let' if '–' in roky_txt else 'roku'} {roky_txt} je {cz(prumer)} % ({d}).")
            if self.uz["typ"] == "CR" or not rady:
                continue
            rok, posl = rady[-1]
            c = cr.get(rok)
            if c and c["hodnoty"][sl] is not None:
                a, b = posl["hodnoty"][sl], c["hodnoty"][sl]
                self.pridej("zmena_trendu", f"míra zániku PO {nazev_obd}: proti ČR", a, b, [
                    _cislo(f"Míra zániku PO {nazev_obd} {rok} – {self.uz['nazev']} (%)", a, "T18_mira_zaniku_po",
                           posl["popis"], sl),
                    _cislo(f"Míra zániku PO {nazev_obd} {rok} – Česko (%)", b, "T18_mira_zaniku_po", c["popis"], sl)],
                    lambda d, rok=rok, a=a, b=b, nazev_obd=nazev_obd:
                        f"Míra zániku PO v oboru {nazev_obd} {rok} je {self.v_uz} {cz(a)} %, {self.v_cr} {cz(b)} % ({d}).")
            # vývoj proti ČR: index posledního roku k prvnímu (jen úplné roky)
            prvni_rok, prvni = rady[0]
            c0 = cr.get(prvni_rok)
            if druh == "rok" and c and c0 and len(rady) >= 2 and c["hodnoty"][sl] and c0["hodnoty"][sl]:
                a0, a1, b0, b1 = prvni["hodnoty"][sl], posl["hodnoty"][sl], c0["hodnoty"][sl], c["hodnoty"][sl]
                i_uz, i_cr = round(a1 / a0, 2), round(b1 / b0, 2)
                self.pridej("zmena_trendu", "míra zániku PO za rok: vývoj proti ČR", i_uz, i_cr, [
                    _cislo(f"Míra zániku PO {prvni_rok} – {self.uz['nazev']} (%)", a0, "T18_mira_zaniku_po", prvni["popis"], sl),
                    _cislo(f"Míra zániku PO {rok} – {self.uz['nazev']} (%)", a1, "T18_mira_zaniku_po", posl["popis"], sl),
                    _cislo(f"Míra zániku PO {prvni_rok} – Česko (%)", b0, "T18_mira_zaniku_po", c0["popis"], sl),
                    _cislo(f"Míra zániku PO {rok} – Česko (%)", b1, "T18_mira_zaniku_po", c["popis"], sl),
                    _cislo(f"Index {rok}/{prvni_rok} – {self.uz['nazev']}", i_uz, "T19_zjisteni", "", "hodnota"),
                    _cislo(f"Index {rok}/{prvni_rok} – Česko", i_cr, "T19_zjisteni", "", "srovnani")],
                    lambda d, a0=a0, a1=a1, b0=b0, b1=b1, i_uz=i_uz, i_cr=i_cr, r0=prvni_rok, r1=rok:
                        f"Míra zániku PO v oboru se mezi lety {r0} a {r1} změnila {self.v_uz} z {cz(a0)} % na "
                        f"{cz(a1)} % (index {cz(i_uz)}), {self.v_cr} z {cz(b0)} % na {cz(b1)} % (index {cz(i_cr)}); "
                        f"index je {d} než {self.v_cr}.")

    # --- 3. rozdíly uvnitř území: okresy vůči kraji a ČR ---------------------------------------
    def rozdily_uvnitr(self) -> None:
        okresy = self.radky("T04_okresy")
        t02 = self.radky("T02_srovnani")
        cr = next((r for r in t02 if r["promenna"] == "obor@CZ"), None)
        kraj = next((r for r in t02 if r["promenna"] == f"obor@kraj:{self.uz['kraj']}"), None)
        if not okresy or not cr or not kraj:
            return
        kraj_nazev = kraj["popis"].replace(" (zkoumané území)", "")
        v_kraji = lokativ(self.uz["kraj"])
        for r in okresy:
            kod = r["promenna"].split(":")[1]
            v_okr, h = lokativ(kod), r["hodnoty"]["hustota"]
            for ref, ref_popis, v_ref in ((kraj, kraj_nazev, v_kraji), (cr, "Česko", self.v_cr)):
                hr = ref["hodnoty"]["hustota"]
                self.pridej("rozdily_uvnitr_uzemi", f"hustota okresu proti {'kraji' if ref is kraj else 'ČR'}", h, hr, [
                    _cislo(f"Na 1\u202f000 obyvatel – {r['popis']}", h, "T04_okresy", r["popis"], "hustota"),
                    _cislo(f"Na 1\u202f000 obyvatel – {ref_popis}", hr, "T02_srovnani", ref["popis"], "hustota")],
                    lambda d, v_okr=v_okr, h=h, hr=hr, v_ref=v_ref:
                        f"Na 1\u202f000 obyvatel připadá {v_okr} {cz(h)} registrovaných subjektů oboru, {v_ref} {cz(hr)} ({d}).")
        if len(okresy) >= 2:
            mx = max(okresy, key=lambda r: r["hodnoty"]["hustota"])
            mn = min(okresy, key=lambda r: r["hodnoty"]["hustota"])
            a, b = mx["hodnoty"]["hustota"], mn["hodnoty"]["hustota"]
            self.pridej("rozdily_uvnitr_uzemi", "rozpětí hustoty mezi okresy", a, b, [
                _cislo(f"Na 1\u202f000 obyvatel – {mx['popis']} (nejvyšší)", a, "T04_okresy", mx["popis"], "hustota"),
                _cislo(f"Na 1\u202f000 obyvatel – {mn['popis']} (nejnižší)", b, "T04_okresy", mn["popis"], "hustota")],
                lambda d: f"Nejvyšší hustotu oboru mezi okresy kraje má okres {mx['popis']} ({cz(a)} na 1\u202f000 "
                          f"obyvatel), nejnižší okres {mn['popis']} ({cz(b)}); hustota "
                          f"{lokativ(mx['promenna'].split(':')[1])} je {d} než {lokativ(mn['promenna'].split(':')[1])}.")

    # --- 4. aktivita oboru vůči kraji (ČSÚ) ---------------------------------------------------
    def aktivita(self) -> None:
        r_s, a = self.t01("AKTIVNI_PODIL_SEKCE_KRAJ")
        r_k, b = self.t01("AKTIVNI_PODIL_KRAJ")
        if a is None or b is None:
            return
        kraj_kod = self.uz["kraj"] or "CZ"
        sekce = self.meta["obor"][0]["kod"]
        self.pridej("aktivita_oboru", "podíl se zjištěnou aktivitou: sekce proti všem oborům", a, b, [
            _cislo(r_s["popis"], a, "T01_zakladni", r_s["popis"], "hodnota"),
            _cislo(r_k["popis"], b, "T01_zakladni", r_k["popis"], "hodnota")],
            lambda d: f"Podíl registrovaných subjektů se zjištěnou aktivitou je {lokativ(kraj_kod)} v sekci {sekce} "
                      f"{cz(a)} %, ve všech oborech {cz(b)} % (ČSÚ; {d}).")

    # --- 5. divergence pořadí: počet vs hustota -----------------------------------------------
    def divergence(self) -> None:
        r1, p1 = self.t01("PORADI_POCET")
        r2, p2 = self.t01("PORADI_HUSTOTA")
        if self.uz["typ"] == "KRAJ" and p1 is not None and p2 is not None:
            n = 14
            self.pridej("divergence_poradi", "kraj mezi 14 kraji", p1, p2, [
                _cislo(r1["popis"], p1, "T01_zakladni", r1["popis"], "hodnota"),
                _cislo(r2["popis"], p2, "T01_zakladni", r2["popis"], "hodnota")],
                lambda d: f"Kraj je mezi 14 kraji {cz(p1)}. podle počtu registrovaných subjektů oboru a {cz(p2)}. "
                          f"podle hustoty na 1\u202f000 obyvatel.", sila=abs(p1 - p2) / (n - 1), rozdil=False)
        okresy = self.radky("T04_okresy")
        n_ok = len(okresy) + len(self.radky("T04_okresy", "ostatni"))
        if self.uz["typ"] == "KRAJ" and n_ok >= 3:
            for r in okresy:
                q1, q2 = r["hodnoty"]["poradi_pocet"], r["hodnoty"]["poradi_hustota"]
                if q1 is None or q2 is None or abs(q1 - q2) < 2:
                    continue    # posun o jedno místo mezi několika okresy se nehlásí
                self.pridej("divergence_poradi", "okres mezi okresy kraje", q1, q2, [
                    _cislo(f"Pořadí podle počtu – {r['popis']}", q1, "T04_okresy", r["popis"], "poradi_pocet"),
                    _cislo(f"Pořadí podle hustoty – {r['popis']}", q2, "T04_okresy", r["popis"], "poradi_hustota")],
                    lambda d, r=r, q1=q1, q2=q2: f"Okres {r['popis']} je mezi okresy kraje {cz(q1)}. podle počtu "
                                                 f"registrovaných subjektů oboru a {cz(q2)}. podle hustoty.",
                    sila=abs(q1 - q2) / (n_ok - 1), rozdil=False)


def _mzdy(self) -> None:
    """Typ mzdy_zamestnanost: T20 (ČSÚ, obor × kraj, roční zjišťování) – kraj proti ČR v posledním roce
    a vývoj (index posledního roku k prvnímu) proti ČR."""
    t20 = self.tab.get("T20_mzdy_obor")
    if not t20 or self.uz["typ"] == "CR":
        return
    kraj = self.uz["kraj"]
    v_kraji = lokativ(kraj) + (" (nejbližší publikovaná úroveň)" if self.uz["typ"] == "OKRES" else "")
    sekce = t20.get("sekce", "")
    uz = [r for r in t20["radky"] if r["uzemi"] == kraj]
    cr = {r["rok"]: r for r in t20["radky"] if r["uzemi"] == "CZ"}
    if not uz:
        return
    posl, prvni = uz[-1], uz[0]
    c, c0 = cr.get(posl["rok"]), cr.get(prvni["rok"])
    if not c:
        return
    rok, rok0 = posl["rok"], prvni["rok"]

    def cislo(r, sl, popis):
        return _cislo(popis, r["hodnoty"][sl], "T20_mzdy_obor", r["popis"], sl)

    a, b = posl["hodnoty"]["mzda"], c["hodnoty"]["mzda"]
    self.pridej("mzdy_zamestnanost", "průměrná mzda v oboru proti ČR", a, b,
                [cislo(posl, "mzda", f"Průměrná mzda v sekci {sekce} {rok} – kraj (Kč)"),
                 cislo(c, "mzda", f"Průměrná mzda v sekci {sekce} {rok} – Česko (Kč)")],
                lambda d: f"Průměrná hrubá měsíční mzda v sekci {sekce} byla v roce {rok} {v_kraji} {cz(a)} Kč, "
                          f"{self.v_cr} {cz(b)} Kč ({d}).")
    a, b = posl["hodnoty"]["mzda_index_uzemi"], c["hodnoty"]["mzda_index_uzemi"]
    self.pridej("mzdy_zamestnanost", "mzda v oboru proti všem odvětvím území, kraj proti ČR", a, b,
                [cislo(posl, "mzda_index_uzemi", f"Mzda v sekci {sekce} proti všem odvětvím kraje {rok}"),
                 cislo(c, "mzda_index_uzemi", f"Mzda v sekci {sekce} proti všem odvětvím ČR {rok}")],
                lambda d: f"Průměrná mzda v sekci {sekce} dosahovala v roce {rok} {v_kraji} {cz(a)} % průměrné mzdy "
                          f"všech odvětví kraje, {self.v_cr} {cz(b)} % ({d}).")
    a, b = posl["hodnoty"]["zam_podil_uzemi"], c["hodnoty"]["zam_podil_uzemi"]
    self.pridej("mzdy_zamestnanost", "podíl oboru na zaměstnancích, kraj proti ČR", a, b,
                [cislo(posl, "zam_podil_uzemi", f"Podíl sekce {sekce} na zaměstnancích kraje {rok} (%)"),
                 cislo(c, "zam_podil_uzemi", f"Podíl sekce {sekce} na zaměstnancích ČR {rok} (%)")],
                lambda d: f"Sekce {sekce} tvořila v roce {rok} {v_kraji} {cz(a)} % zaměstnanců (přepočtené počty), "
                          f"{self.v_cr} {cz(b)} % ({d}).")
    if c0 and rok0 != rok:
        for sl, co, jednotka in (("mzda", "průměrná mzda", " Kč"), ("zam", "počet zaměstnanců", " tis.")):
            a0, a1, b0, b1 = prvni["hodnoty"][sl], posl["hodnoty"][sl], c0["hodnoty"][sl], c["hodnoty"][sl]
            if not all((a0, a1, b0, b1)):
                continue
            i_uz, i_cr = round(a1 / a0, 2), round(b1 / b0, 2)
            self.pridej("mzdy_zamestnanost", f"vývoj: {co} proti ČR", i_uz, i_cr, [
                cislo(prvni, sl, f"{co} {rok0} – kraj"), cislo(posl, sl, f"{co} {rok} – kraj"),
                cislo(c0, sl, f"{co} {rok0} – Česko"), cislo(c, sl, f"{co} {rok} – Česko"),
                _cislo(f"Index {rok}/{rok0} – kraj", i_uz, "T19_zjisteni", "", "hodnota"),
                _cislo(f"Index {rok}/{rok0} – Česko", i_cr, "T19_zjisteni", "", "srovnani")],
                lambda d, a0=a0, a1=a1, b0=b0, b1=b1, i_uz=i_uz, i_cr=i_cr, co=co, j=jednotka:
                    f"V sekci {sekce} se {co} mezi lety {rok0} a {rok} změnil{'a' if co.endswith('mzda') else ''} "
                    f"{v_kraji} z {cz(a0)}{j} na {cz(a1)}{j} (index {cz(i_uz)}), {self.v_cr} z {cz(b0)}{j} na "
                    f"{cz(b1)}{j} (index {cz(i_cr)}); index je {d} než {self.v_cr}.")


_Detektor.mzdy = _mzdy


def detekuj(vysledek: dict) -> list[dict]:
    """Zjištění seřazená podle síly (sestupně); id Z01… podle pořadí."""
    d = _Detektor(vysledek)
    d.odchylka_od_cr()
    d.zmena_trendu()
    d.rozdily_uvnitr()
    d.aktivita()
    d.divergence()
    d.mzdy()
    z = sorted(d.zjisteni, key=lambda x: (-x["sila"], PORADI_TYPU.index(x["typ"]), x["podtyp"]))
    for i, x in enumerate(z, start=1):
        x["poradi"] = i
        x["id"] = f"Z{i:02d}"
    return z


def tabulka_zjisteni(zjisteni: list[dict]) -> dict:
    """Zjištění jako tabulka výstupu (JSON + list XLSX), aby čísla ve větách prošla kontrolou PDF."""
    return {
        "kod": "T19_zjisteni", "nazev": "Zjištění detektoru (seřazeno podle síly)",
        "sloupce": [{"kod": "id", "nazev": "Zjištění", "ukazatel": "ZJ_TYP"},
                    {"kod": "typ", "nazev": "Typ zjištění", "ukazatel": "ZJ_TYP"},
                    {"kod": "sila", "nazev": "Síla", "ukazatel": "ZJ_SILA"},
                    {"kod": "hodnota", "nazev": "Hodnota", "ukazatel": "ZJ_HODNOTA"},
                    {"kod": "srovnani", "nazev": "Srovnání", "ukazatel": "ZJ_SROVNANI"},
                    {"kod": "rozdil_pct", "nazev": "Relativní rozdíl (%)", "ukazatel": "ZJ_ROZDIL_PCT"}],
        "radky": [{"popis": z["popis"], "typ": "polozka", "id": z["id"],
                   "hodnoty": {"id": z["id"], "typ": z["typ_nazev"], "sila": z["sila"], "hodnota": z["hodnota"],
                               "srovnani": z["srovnani"], "rozdil_pct": z["rozdil_pct"]}} for z in zjisteni],
        "zverejneno": True, "duvod": None,
        "poznamky": [f"Síla = |hodnota / srovnání − 1|; u divergence pořadí |p1 − p2| / (počet území − 1). Rozdíly "
                     f"pod {cz(round(100 * PRAH_ZJISTENI))} % relativně se nehlásí. Položky struktury s podílem pod "
                     f"{cz(MIN_PODIL_STRUKTURY)} % v území i v ČR se nehlásí. Popisy jsou věcné, bez interpretace."],
    }
