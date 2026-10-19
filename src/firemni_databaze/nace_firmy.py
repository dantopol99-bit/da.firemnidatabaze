"""Kódy CZ-NACE firem s platností v čase (obor.firma_nace), empirická matice přechodů
2008 → 2025, odvození kódů 2025 a kontroly dopadu.

Spuštění (po nasad_sql obor a nace_ciselniky nahraj):
    python -m firemni_databaze.nace_firmy res [--datum D] [--bez-vedlejsich]   # snímek RES → firma_nace
    python -m firemni_databaze.nace_firmy matice                               # matice + pravidla + odvození
    python -m firemni_databaze.nace_firmy kontroly [--vystup soubor.md]        # krok 6: pokrytí, změny, pilot
    python -m firemni_databaze.nace_firmy obnov                                # jen obnoví obor.v_firma_obor_aktualni
    python -m firemni_databaze.nace_firmy vse

Všechny kroky jsou idempotentní: opakované spuštění se stejnými daty nic nezmění.
Kódy z RES se nikdy nemažou, jen se uzavírají (platnost_do), když je další snímek nahradí.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path

MIN_ZAKLAD = 20          # méně firem v matici → kandidáti z převodníku, kód NULL
PRAH_ROZPORU = 0.9       # rozhodnutí 2: empirický cíl s podílem ≥ 0,9 přebije jediný cíl převodníku
ZACATEK_2025 = date(2025, 1, 1)               # rozhodnutí 6: kód 2025 platí nejdřív od 1. 1. 2025
KONEC_DVOJIHO_KODOVANI = date(2028, 12, 31)   # rozhodnutí 7: poslední den kódů 2008 v RES
DUVOD_ZANIK = "zánik subjektu"
DUVOD_NEUVADI = "zdroj kód už neuvádí"
DUVOD_KONEC_2008 = "konec dvojího kódování"
PRAH_ZVEREJNENI = 10     # rozhodnutí 3: počty pod 10 se ve výstupech nevypisují
VERZE = (2008, 2025)


# ---------------------------------------------------------------------------
# Kódy z RES (otevřená data, schéma res) → obor.firma_nace
# ---------------------------------------------------------------------------

UROVEN_KODU = "CASE WHEN {k} ~ '^[A-Z]$' THEN 1 ELSE length({k}) END"


def _zapis_res(cur, zdroj_sql: str, subjekty_sql: str, verze: int, typ: str, zdroj_detail: str,
               davka: int | None) -> tuple[int, int]:
    """Zapíše kódy RES jedné verze a typu. zdroj_sql vrací (ico, kod, platnost_od, platnost_do),
    subjekty_sql všechny subjekty snímku (ico, konec_snimku) – konec_snimku je datum, ke kterému
    se uzavře kód, který snímek u subjektu už neuvádí. Vrací (uzavřeno, vloženo)."""
    cur.execute(f"CREATE TEMP TABLE stg_fn ON COMMIT DROP AS {zdroj_sql}")
    cur.execute(f"CREATE TEMP TABLE stg_sn ON COMMIT DROP AS {subjekty_sql}")
    cur.execute("CREATE INDEX ON stg_fn (ico, kod)")
    cur.execute("CREATE INDEX ON stg_sn (ico)")
    cur.execute("ANALYZE stg_fn")
    cur.execute("ANALYZE stg_sn")
    # 1) uzavřít otevřené kódy, které snímek nahradil jiným (jen subjekty obsažené ve snímku),
    #    a kódy zaniklých subjektů (platnost_do = datum zániku)
    cur.execute(
        """
        WITH uzavrit AS (
            SELECT f.id, CASE WHEN s.ico IS NULL THEN sn.konec_snimku ELSE s.platnost_do END AS konec,
                   CASE WHEN s.ico IS NULL THEN %(neuvadi)s ELSE %(zanik)s END AS duvod
            FROM obor.firma_nace f
            JOIN stg_sn sn ON sn.ico = f.ico
            LEFT JOIN stg_fn s ON s.ico = f.ico AND s.kod = f.kod
            WHERE f.zdroj = 'RES' AND f.verze = %(verze)s AND f.typ = %(typ)s AND f.platnost_do IS NULL
        )
        UPDATE obor.firma_nace f
        SET platnost_do = greatest(u.konec, f.platnost_od), duvod_uzavreni = u.duvod
        FROM uzavrit u
        WHERE f.id = u.id AND u.konec IS NOT NULL
        """,
        {"verze": verze, "typ": typ, "zanik": DUVOD_ZANIK, "neuvadi": DUVOD_NEUVADI},
    )
    uzavreno = cur.rowcount
    # 2) vložit kódy, které nejsou otevřené (ani uzavřené ke stejnému datu zániku)
    cur.execute(
        f"""
        INSERT INTO obor.firma_nace (ico, verze, kod, uroven, typ, zdroj, zdroj_detail, jistota,
                                     platnost_od, platnost_do, duvod_uzavreni, import_davka_id)
        SELECT s.ico, %(verze)s, s.kod, coalesce(c.uroven, {UROVEN_KODU.format(k='s.kod')}), %(typ)s, 'RES',
               %(detail)s, 1, s.platnost_od, s.platnost_do,
               CASE WHEN s.platnost_do IS NOT NULL THEN %(zanik)s END, %(davka)s
        FROM stg_fn s
        LEFT JOIN obor.nace_ciselnik c ON c.verze = %(verze)s AND c.kod = s.kod
        WHERE NOT EXISTS (
            SELECT 1 FROM obor.firma_nace f
            WHERE f.ico = s.ico AND f.verze = %(verze)s AND f.typ = %(typ)s AND f.zdroj = 'RES' AND f.kod = s.kod
              AND (f.platnost_do IS NULL OR f.platnost_do = s.platnost_do OR f.platnost_od = s.platnost_od)
        )
        ON CONFLICT DO NOTHING
        """,
        {"verze": verze, "typ": typ, "detail": zdroj_detail, "davka": davka, "zanik": DUVOD_ZANIK},
    )
    vlozeno = cur.rowcount
    cur.execute("DROP TABLE stg_fn, stg_sn")
    return uzavreno, vlozeno


def nacti_res(conn, datum: date | None = None, vedlejsi: bool = True) -> dict:
    """Snímek RES (res.subjekt, res.pf_nace) → obor.firma_nace, obě verze.
    Hlavní činnost = NACE / NACE2025; vedlejší = ostatní kódy téže verze z res_pf_nace."""
    from firemni_databaze.res_import import v_davce

    with conn.cursor() as cur:
        if datum is None:
            cur.execute("SELECT max(datum_snimku) FROM res.subjekt")
            datum = cur.fetchone()[0]
        if datum is None:
            raise SystemExit("Ve schématu res není žádný snímek (python -m firemni_databaze.res_import snimek).")
    conn.commit()
    detail = f"RES otevřená data ČSÚ, snímek {datum:%Y-%m-%d}"
    vysledek = {}

    def prace(davka: int):
        with conn.cursor() as cur:
            cur.execute("SET LOCAL work_mem = '256MB'")
            subjekty = f"""
                SELECT ico, coalesce(ddatzan, ddatpakt, datum_snimku) AS konec_snimku
                FROM res.subjekt WHERE datum_snimku = '{datum}'"""
            cur.execute(f"SELECT count(nace) FROM res.subjekt WHERE datum_snimku = '{datum}'")
            konec_2008 = je_konec_dvojiho_kodovani(datum, cur.fetchone()[0])
            for verze, sloupec, kodcis in ((2008, "nace", "80004"), (2025, "nace2025", "80143")):
                if verze == 2008 and konec_2008:
                    vysledek[(2008, "konec")] = (uzavri_kody_2008(cur), 0)
                    print(f"  CZ-NACE 2008: konec dvojího kódování – uzavřeno {vysledek[(2008, 'konec')][0]} kódů")
                    conn.commit()
                    continue
                # rozhodnutí 6: kód 2025 platí nejdřív od 1. 1. 2025 (u zaniklých dřív je interval prázdný)
                od = "least(coalesce({p}ddatpakt, {p}datum_snimku), {p}ddatzan)"
                do = "{p}ddatzan"
                if verze == 2025:
                    od, do = f"obor.zacatek_2025({od})", f"obor.konec_2025({do})"
                hlavni = f"""
                    SELECT ico, {sloupec} AS kod, {od.format(p='')} AS platnost_od, {do.format(p='')} AS platnost_do
                    FROM res.subjekt WHERE datum_snimku = '{datum}' AND {sloupec} IS NOT NULL"""
                vysledek[(verze, "hlavni")] = _zapis_res(cur, hlavni, subjekty, verze, "hlavni", detail, davka)
                if vedlejsi:
                    ved = f"""
                        SELECT DISTINCT p.ico, p.hodn AS kod, {od.format(p='s.')} AS platnost_od,
                               {do.format(p='s.')} AS platnost_do
                        FROM res.pf_nace p
                        JOIN res.subjekt s ON s.ico = p.ico AND s.datum_snimku = p.datum_snimku
                        WHERE p.datum_snimku = '{datum}' AND p.kodcis = '{kodcis}' AND p.hodn IS NOT NULL
                          AND p.hodn IS DISTINCT FROM s.{sloupec}"""
                    vysledek[(verze, "vedlejsi")] = _zapis_res(cur, ved, subjekty, verze, "vedlejsi", detail, davka)
                conn.commit()
                for typ in ("hlavni", "vedlejsi"):
                    if (verze, typ) in vysledek:
                        u, v = vysledek[(verze, typ)]
                        print(f"  CZ-NACE {verze} {typ:8}: vloženo {v:>10,}, uzavřeno {u:>8,}".replace(",", " "))
        with conn.cursor() as cur:
            cur.execute("ANALYZE obor.firma_nace")
        conn.commit()
        return sum(v for _, v in vysledek.values()), f"firma_nace ze snímku RES k {datum}"

    v_davce(conn, "OBOR-NACE-RES", detail, prace)
    return vysledek


def je_konec_dvojiho_kodovani(datum_stavu: date, pocet_kodu_2008: int) -> bool:
    """Rozhodnutí 7: dvojí kódování končí po 31. 12. 2028, nebo jakmile zdroj přestane kódy 2008 dodávat."""
    return datum_stavu > KONEC_DVOJIHO_KODOVANI or pocet_kodu_2008 == 0


def uzavri_kody_2008(cur, ico: str | None = None) -> int:
    """Uzavře všechny otevřené kódy CZ-NACE 2008 z RES (celé populace, nebo jednoho IČO)
    k 31. 12. 2028 s důvodem „konec dvojího kódování“. Opakované volání nic nezmění."""
    cur.execute(
        "UPDATE obor.firma_nace SET platnost_do = greatest(%s::date, platnost_od), duvod_uzavreni = %s "
        "WHERE zdroj = 'RES' AND verze = 2008 AND platnost_do IS NULL AND (%s::text IS NULL OR ico = %s)",
        (KONEC_DVOJIHO_KODOVANI, DUVOD_KONEC_2008, ico, ico),
    )
    return cur.rowcount


def obnov_rozhrani(conn) -> None:
    """Obnoví materializované rozhraní obor.v_firma_obor_aktualni (~2 min)."""
    with conn.cursor() as cur:
        cur.execute("REFRESH MATERIALIZED VIEW obor.v_firma_obor_aktualni")
        cur.execute("ANALYZE obor.v_firma_obor_aktualni")
    conn.commit()
    print("  obor.v_firma_obor_aktualni obnoveno")


def zapis_ares(cur, ico: str, res_zaznam: dict | None, davka: int | None, dnes: date | None = None) -> int:
    """Záznam z ARES (endpoint ekonomicke-subjekty-res) → obor.firma_nace, obě verze.
    czNacePrevazujici / czNacePrevazujici2008 = hlavní, ostatní kódy z czNace / czNace2008 = vedlejší.
    Platnost od = datumAktualizace (stejný význam jako DDATPAKT v otevřených datech RES)."""
    if not res_zaznam:
        return 0
    dnes = dnes or date.today()
    platnost_do = res_zaznam.get("datumZaniku")
    platnost_od = min(filter(None, (res_zaznam.get("datumAktualizace"), platnost_do)), default=None)
    meze = {2008: (platnost_od, platnost_do),
            2025: (_nejdriv_2025(platnost_od), _nejdriv_2025(platnost_do))}   # rozhodnutí 6
    # rozhodnutí 7: u jednoho IČO rozhoduje jen datum – chybějící kód 2008 u jedné firmy
    # neznamená, že ho zdroj přestal dodávat (to pozná až nacti_res na celém snímku)
    konec_2008 = dnes > KONEC_DVOJIHO_KODOVANI
    radky = []
    for verze, pole_hlavni, pole_vse in ((2008, "czNacePrevazujici2008", "czNace2008"),
                                        (2025, "czNacePrevazujici", "czNace")):
        if verze == 2008 and konec_2008:
            continue
        hlavni = res_zaznam.get(pole_hlavni)
        if hlavni:
            radky.append((verze, hlavni, "hlavni"))
        for kod in sorted(set(res_zaznam.get(pole_vse) or []) - {hlavni}):
            radky.append((verze, kod, "vedlejsi"))
    vlozeno = sum(_zapis_jeden(cur, ico, verze, kod, typ, *meze[verze], davka) for verze, kod, typ in radky)
    if konec_2008:
        uzavri_kody_2008(cur, ico)
    # kódy, které ARES už neuvádí, se uzavřou ke dni aktualizace (nebo zániku)
    for verze in VERZE:
        for typ in ("hlavni", "vedlejsi"):
            aktualni = [k for v, k, t in radky if v == verze and t == typ]
            od, do = meze[verze]
            cur.execute(
                "UPDATE obor.firma_nace SET platnost_do = greatest(coalesce(%s::date, current_date), platnost_od), "
                "duvod_uzavreni = %s "
                "WHERE ico = %s AND verze = %s AND typ = %s AND zdroj = 'RES' AND platnost_do IS NULL "
                "AND NOT (kod = ANY(%s))",
                (do or od, DUVOD_ZANIK if do else DUVOD_NEUVADI, ico, verze, typ, aktualni),
            )
    return vlozeno


def _nejdriv_2025(d: str | None) -> str | None:
    """Datum ISO nejdřív 1. 1. 2025 (začátek i konec platnosti kódu 2025, viz obor.zacatek_2025)."""
    return max(d, ZACATEK_2025.isoformat()) if d else None


def _zapis_jeden(cur, ico, verze, kod, typ, platnost_od, platnost_do, davka) -> int:
    cur.execute(
        f"""
        INSERT INTO obor.firma_nace (ico, verze, kod, uroven, typ, zdroj, zdroj_detail, jistota,
                                     platnost_od, platnost_do, duvod_uzavreni, import_davka_id)
        SELECT %(ico)s, %(verze)s, %(kod)s, coalesce(c.uroven, {UROVEN_KODU.format(k='%(kod)s')}), %(typ)s, 'RES',
               'ARES, endpoint ekonomicke-subjekty-res', 1, %(od)s, %(do)s,
               CASE WHEN %(do)s::date IS NOT NULL THEN %(zanik)s END, %(davka)s
        FROM (SELECT 1) x
        LEFT JOIN obor.nace_ciselnik c ON c.verze = %(verze)s AND c.kod = %(kod)s
        WHERE NOT EXISTS (
            SELECT 1 FROM obor.firma_nace f
            WHERE f.ico = %(ico)s AND f.verze = %(verze)s AND f.typ = %(typ)s AND f.zdroj = 'RES'
              AND f.kod = %(kod)s AND (f.platnost_do IS NULL OR f.platnost_od = %(od)s::date))
        ON CONFLICT DO NOTHING
        """,
        {"ico": ico, "verze": verze, "kod": kod, "typ": typ, "od": platnost_od, "do": platnost_do, "davka": davka,
         "zanik": DUVOD_ZANIK},
    )
    return cur.rowcount


# ---------------------------------------------------------------------------
# Empirická matice a pravidla odvození
# ---------------------------------------------------------------------------

SQL_MATICE = """
WITH h08 AS (
    SELECT DISTINCT ON (ico) ico, kod, platnost_od FROM obor.firma_nace
    WHERE verze = 2008 AND typ = 'hlavni' AND zdroj = 'RES' ORDER BY ico, platnost_od DESC NULLS LAST, id DESC
), h25 AS (
    SELECT DISTINCT ON (ico) ico, kod, platnost_od FROM obor.firma_nace
    WHERE verze = 2025 AND typ = 'hlavni' AND zdroj = 'RES' ORDER BY ico, platnost_od DESC NULLS LAST, id DESC
), par AS (
    SELECT c08.sekce s1, c08.oddil s2, c08.skupina s3, c08.trida s4, CASE WHEN c08.uroven = 5 THEN c08.kod END s5,
           c25.sekce t1, c25.oddil t2, c25.skupina t3, c25.trida t4, CASE WHEN c25.uroven = 5 THEN c25.kod END t5
    FROM h08 JOIN h25 USING (ico)
    JOIN obor.nace_ciselnik c08 ON c08.verze = 2008 AND c08.kod = h08.kod
    JOIN obor.nace_ciselnik c25 ON c25.verze = 2025 AND c25.kod = h25.kod
    WHERE h25.platnost_od IS NOT DISTINCT FROM obor.zacatek_2025(h08.platnost_od)   -- tentýž stav záznamu RES
), rozpad AS (
    SELECT z.kod AS kod_2008, z.u AS uroven_2008, t.u AS uroven, t.kod AS kod_2025
    FROM par
    CROSS JOIN LATERAL (VALUES (s1, 1), (s2, 2), (s3, 3), (s4, 4), (s5, 5)) z (kod, u)
    CROSS JOIN LATERAL (VALUES (t1, 1), (t2, 2), (t3, 3), (t4, 4), (t5, 5)) t (kod, u)
    WHERE z.kod IS NOT NULL AND t.kod IS NOT NULL AND t.u <= z.u
), pocty AS (
    SELECT kod_2008, uroven_2008, uroven, kod_2025, count(*)::int AS pocet FROM rozpad
    GROUP BY kod_2008, uroven_2008, uroven, kod_2025
)
INSERT INTO obor.nace_prechod_empiricky (zaklad_k, kod_2008, uroven_2008, uroven, kod_2025, pocet, zaklad, podil)
SELECT %(k)s, kod_2008, uroven_2008, uroven, kod_2025, pocet, zaklad, round(pocet::numeric / zaklad, 4)
FROM (SELECT *, sum(pocet) OVER (PARTITION BY kod_2008, uroven)::int AS zaklad FROM pocty) x
"""


@dataclass(frozen=True)
class Pravidlo:
    kod_2025: str | None
    jistota: float | None
    metoda: str
    zaklad: int
    kandidati: tuple[str, ...] | None
    cil_prevodnik: str | None = None     # u 'empiricky_rozpor': jediný cíl podle převodníku, který empirie přebila


def predek(ciselnik: dict, verze: int, kod: str, uroven: int) -> str | None:
    """Předek kódu na dané úrovni (kód sám na vlastní úrovni)."""
    c = ciselnik.get((verze, kod))
    if c is None or c["uroven"] < uroven:
        return None
    return c["kod"] if c["uroven"] == uroven else c[("sekce", "oddil", "skupina", "trida")[uroven - 1]]


def pravidlo(kod: str, uroven: int, ciselnik: dict, prevodnik: dict, matice: dict) -> Pravidlo:
    """Pravidlo odvození kódu 2025 na cílové úrovni pro kód 2008 (viz sql/obor/03_prechod.sql).
    prevodnik: (kod_2008) → [(kod_2025, typ_vazby)] na úrovni kódu; matice: (kod_2008, uroven) → (cíl, počet, základ)."""
    zaklad = matice.get((kod, uroven), (None, 0, 0))[2]

    def podle_prevodniku(cil: str, metoda: str) -> Pravidlo:
        # rozhodnutí 2: jiný empirický cíl s podílem ≥ 0,9 při základu ≥ 20 přebije převodník
        if zaklad >= MIN_ZAKLAD:
            cil_e, pocet, _ = matice[(kod, uroven)]
            if cil_e != cil and pocet / zaklad >= PRAH_ROZPORU:
                return Pravidlo(cil_e, round(pocet / zaklad, 4), "empiricky_rozpor", zaklad, None, cil)
        return Pravidlo(cil, 1.0, metoda, zaklad, None)

    # 1) vazba 1:1 – u kódu samotného, nebo u jeho předka na cílové úrovni
    for k in (kod, predek(ciselnik, 2008, kod, uroven)):
        if k is None:
            continue
        pary = prevodnik.get(k, [])
        if len(pary) == 1 and pary[0][1] == "1:1":
            cil = predek(ciselnik, 2025, pary[0][0], uroven)
            if cil is not None:
                return podle_prevodniku(cil, "prevodnik_1:1")
    # 2) rozhodnutí 1: převodník dává na cílové úrovni jediného kandidáta (vč. vazby N:1) → jistota 1
    kandidati = tuple(sorted({p for b, _ in prevodnik.get(kod, []) if (p := predek(ciselnik, 2025, b, uroven))}))
    if len(kandidati) == 1:
        return podle_prevodniku(kandidati[0], "prevodnik_jediny_cil")
    # 3) empirická matice
    if zaklad >= MIN_ZAKLAD:
        cil, pocet, zaklad = matice[(kod, uroven)]
        return Pravidlo(cil, round(pocet / zaklad, 4), "empiricky", zaklad, None)
    # 4) nejednoznačné
    return Pravidlo(None, None, "nejednoznacne", zaklad, kandidati)


def spocti_matici(conn, zaklad_k: date | None = None) -> date:
    """Matice přechodů a pravidla odvození pro všechny kódy 2008 → obor.nace_prechod_empiricky, obor.nace_odvozeni."""
    with conn.cursor() as cur:
        if zaklad_k is None:
            cur.execute("SELECT max(datum_snimku) FROM res.snimek")
            zaklad_k = cur.fetchone()[0] or date.today()
        cur.execute("SET LOCAL work_mem = '512MB'")
        cur.execute("DELETE FROM obor.nace_prechod_empiricky WHERE zaklad_k = %s", (zaklad_k,))
        cur.execute(SQL_MATICE, {"k": zaklad_k})
        print(f"  matice k {zaklad_k}: {cur.rowcount} párů")

        cur.execute("SELECT verze, kod, uroven, sekce, oddil, skupina, trida FROM obor.nace_ciselnik")
        ciselnik = {(r[0], r[1]): dict(zip(("verze", "kod", "uroven", "sekce", "oddil", "skupina", "trida"), r))
                    for r in cur.fetchall()}
        cur.execute("SELECT kod_2008, kod_2025, typ_vazby FROM obor.nace_prevodnik")
        prevodnik = defaultdict(list)
        for a, b, t in cur.fetchall():
            prevodnik[a].append((b, t))
        cur.execute(
            "SELECT DISTINCT ON (kod_2008, uroven) kod_2008, uroven, kod_2025, pocet, zaklad "
            "FROM obor.nace_prechod_empiricky WHERE zaklad_k = %s ORDER BY kod_2008, uroven, pocet DESC, kod_2025",
            (zaklad_k,),
        )
        matice = {(r[0], r[1]): (r[2], r[3], r[4]) for r in cur.fetchall()}

        radky = []
        for (verze, kod), c in ciselnik.items():
            if verze != 2008:
                continue
            for uroven in range(1, c["uroven"] + 1):
                p = pravidlo(kod, uroven, ciselnik, prevodnik, matice)
                radky.append((zaklad_k, kod, uroven, p.kod_2025, p.jistota, p.metoda, p.zaklad,
                              list(p.kandidati) if p.kandidati is not None else None, p.cil_prevodnik))
        cur.execute("DELETE FROM obor.nace_odvozeni WHERE zaklad_k = %s", (zaklad_k,))
        cur.executemany(
            "INSERT INTO obor.nace_odvozeni (zaklad_k, kod_2008, uroven, kod_2025, jistota, metoda, zaklad, kandidati) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", [r[:8] for r in radky])
        cur.execute("DELETE FROM obor.nace_rozpory_prevodnik WHERE zaklad_k = %s", (zaklad_k,))
        rozpory = [(r[0], r[1], r[2], r[8], r[3], r[4], r[6]) for r in radky if r[5] == "empiricky_rozpor"]
        cur.executemany(
            "INSERT INTO obor.nace_rozpory_prevodnik (zaklad_k, kod_2008, uroven, cil_prevodnik, cil_empirie, podil, "
            "zaklad) VALUES (%s, %s, %s, %s, %s, %s, %s)", rozpory)
        print(f"  pravidla odvození: {len(radky)} (kód 2008 × cílová úroveň), rozporů s převodníkem: {len(rozpory)}")
    conn.commit()
    return zaklad_k


def odvod_firmy(conn, zaklad_k: date) -> int:
    """Firmám (a stavům), které mají v RES hlavní činnost jen podle CZ-NACE 2008, odvodí CZ-NACE 2025
    na všech úrovních. Odvozené řádky se při každém výpočtu nahradí."""
    with conn.cursor() as cur:
        cur.execute("SET LOCAL work_mem = '256MB'")
        cur.execute("DELETE FROM obor.firma_nace WHERE zdroj = 'odvozeno'")
        cur.execute(
            """
            INSERT INTO obor.firma_nace (ico, verze, kod, uroven, typ, zdroj, zdroj_detail, jistota, priznak,
                                         kandidati, odvozeno_z, platnost_od, platnost_do)
            SELECT f.ico, 2025, o.kod_2025, o.uroven, 'hlavni', 'odvozeno',
                   'odvozeno z CZ-NACE 2008 (' || o.metoda || '), matice k ' || o.zaklad_k,
                   o.jistota, CASE WHEN o.kod_2025 IS NULL THEN 'nejednoznacne' END, o.kandidati,
                   f.kod, f.platnost_od, f.platnost_do
            FROM obor.firma_nace f
            JOIN obor.nace_odvozeni o ON o.zaklad_k = %s AND o.kod_2008 = f.kod
            WHERE f.verze = 2008 AND f.typ = 'hlavni' AND f.zdroj = 'RES'
              AND NOT EXISTS (
                  SELECT 1 FROM obor.firma_nace g
                  WHERE g.ico = f.ico AND g.verze = 2025 AND g.typ = 'hlavni' AND g.zdroj = 'RES'
                    AND g.platnost_od IS NOT DISTINCT FROM obor.zacatek_2025(f.platnost_od))
            """,
            (zaklad_k,),
        )
        n = cur.rowcount
    conn.commit()
    print(f"  odvozené řádky (IČO × úroveň): {n}")
    return n


# ---------------------------------------------------------------------------
# Kontroly a dopad (krok 6)
# ---------------------------------------------------------------------------

def _pocet(n: int) -> str:
    return f"{n:,}".replace(",", " ") if n >= PRAH_ZVEREJNENI else f"< {PRAH_ZVEREJNENI}"


def _procento(a: int, b: int) -> str:
    return f"{100 * a / b:.2f} %".replace(".", ",") if b else "–"


def kontroly(conn, kraj: str = "CZ051", sekce_2008: str = "F", sekce_2025: str = "F") -> str:
    """Pokrytí, změny oddílu a sekce, pilot sekce F × kraj, kontrola číselníku. Vrací Markdown."""
    md = []
    with conn.cursor() as cur:
        cur.execute("SELECT max(datum_snimku) FROM res.subjekt")
        datum = cur.fetchone()[0]
        cur.execute("SELECT max(zaklad_k) FROM obor.nace_prechod_empiricky")
        zaklad_k = cur.fetchone()[0]
        md.append(f"Stav RES k {datum:%d. %m. %Y}, matice přechodů k {zaklad_k:%d. %m. %Y}.\n")

        # --- pokrytí
        cur.execute(
            """
            SELECT (s.ddatzan IS NULL) AS zije,
                   count(*)                                                       AS vse,
                   count(*) FILTER (WHERE v.zdroj = 'RES')                         AS res,
                   count(*) FILTER (WHERE v.zdroj = 'odvozeno' AND v.priznak IS NULL) AS odv,
                   count(*) FILTER (WHERE v.zdroj = 'odvozeno' AND v.priznak IS NOT NULL) AS odv_nejedn,
                   count(*) FILTER (WHERE v.zdroj = 'odvozeno' AND v.oddil IS NOT NULL) AS odv_oddil,
                   count(*) FILTER (WHERE v.zdroj IS NULL)                         AS bez
            FROM res.subjekt s
            LEFT JOIN obor.v_firma_obor_aktualni v ON v.ico = s.ico
            WHERE s.datum_snimku = %s
            GROUP BY 1 ORDER BY 1 DESC
            """,
            (datum,),
        )
        md.append("### Pokrytí (hlavní činnost CZ-NACE 2025)\n")
        md.append("| subjekty | celkem | kód 2025 z RES | odvozený kód | z toho nejednoznačný na úrovni kódu | odvozený oddíl | bez kódu |")
        md.append("|---|---:|---:|---:|---:|---:|---:|")
        celkem = [0] * 6
        for zije, vse, res, odv, nej, odv_oddil, bez in cur.fetchall():
            nazev = "bez zániku" if zije else "zaniklé (v souboru 4 roky)"
            md.append(f"| {nazev} | {_pocet(vse)} | {_pocet(res)} ({_procento(res, vse)}) | "
                      f"{_pocet(odv + nej)} ({_procento(odv + nej, vse)}) | {_pocet(nej)} | {_pocet(odv_oddil)} | "
                      f"{_pocet(bez)} ({_procento(bez, vse)}) |")
            celkem = [a + b for a, b in zip(celkem, (vse, res, odv + nej, nej, odv_oddil, bez))]
        vse, res, odv, nej, odv_oddil, bez = celkem
        md.append(f"| **celkem** | {_pocet(vse)} | {_pocet(res)} ({_procento(res, vse)}) | {_pocet(odv)} "
                  f"({_procento(odv, vse)}) | {_pocet(nej)} | {_pocet(odv_oddil)} | {_pocet(bez)} ({_procento(bez, vse)}) |")
        md.append("")

        # --- základ matice
        cur.execute(
            "SELECT uroven, count(DISTINCT kod_2008), max(zaklad) FILTER (WHERE uroven_2008 = 1), "
            "count(DISTINCT kod_2008) FILTER (WHERE zaklad >= %s) "
            "FROM obor.nace_prechod_empiricky WHERE zaklad_k = %s GROUP BY uroven ORDER BY uroven",
            (MIN_ZAKLAD, zaklad_k),
        )
        urovne = cur.fetchall()
        cur.execute(
            "SELECT sum(pocet) FROM obor.nace_prechod_empiricky WHERE zaklad_k = %s AND uroven = 1 AND uroven_2008 = 1",
            (zaklad_k,),
        )
        zaklad_firem = cur.fetchone()[0] or 0
        md.append("### Základ empirické matice\n")
        md.append(f"Firem s oběma kódy hlavní činnosti v RES (tentýž stav záznamu): **{_pocet(zaklad_firem)}**.\n")
        md.append("| cílová úroveň 2025 | kódů 2008 v matici | z toho se základem ≥ 20 firem |")
        md.append("|---|---:|---:|")
        for u, n, _, n20 in urovne:
            md.append(f"| {('sekce', 'oddíl', 'skupina', 'třída', 'podtřída')[u - 1]} | {n} | {n20} |")
        md.append("")
        cur.execute(
            """
            SELECT o.uroven, o.metoda, count(*) AS stavu,
                   round(avg(f.jistota) FILTER (WHERE f.jistota IS NOT NULL), 4) AS jistota
            FROM obor.firma_nace f
            JOIN obor.nace_odvozeni o ON o.zaklad_k = %s AND o.kod_2008 = f.odvozeno_z AND o.uroven = f.uroven
            WHERE f.zdroj = 'odvozeno'
            GROUP BY 1, 2 ORDER BY 1, 2
            """,
            (zaklad_k,),
        )
        md.append("### Odvozené kódy podle úrovně a metody\n")
        md.append("| úroveň | metoda | subjektů | průměrná jistota |")
        md.append("|---|---|---:|---:|")
        for u, m, n, j in cur.fetchall():
            md.append(f"| {u} | {m} | {_pocet(n)} | {str(j).replace('.', ',') if j is not None else '–'} |")
        md.append("")

        # --- rozpory převodníku s empirií (rozhodnutí 2)
        cur.execute(
            "SELECT kod_2008, uroven, cil_prevodnik, cil_empirie, podil, zaklad FROM obor.nace_rozpory_prevodnik "
            "WHERE zaklad_k = %s ORDER BY zaklad DESC, kod_2008, uroven", (zaklad_k,))
        rozpory = cur.fetchall()
        md.append("### Rozpory převodníku s empirií (rozhoduje empirie)\n")
        md.append(f"Pravidel: **{len(rozpory)}** (základ ≥ {MIN_ZAKLAD}, podíl empirického cíle ≥ "
                  f"{str(PRAH_ROZPORU).replace('.', ',')}).\n")
        if rozpory:
            md.append("| kód 2008 | cílová úroveň | cíl převodníku | cíl empirie | podíl | základ |")
            md.append("|---|---:|---|---|---:|---:|")
            for k, u, cp, ce, podil, zaklad in rozpory:
                md.append(f"| {k} | {u} | {cp} | {ce} | {str(podil).replace('.', ',')} | {_pocet(zaklad)} |")
        md.append("")

        # --- stav zařazení v rozhraní (rozhodnutí 5)
        cur.execute("SELECT coalesce(stav_zarazeni, 'bez kódu 2025'), count(*) FROM obor.v_firma_obor_aktualni "
                    "GROUP BY 1 ORDER BY 2 DESC")
        md.append("### Stav zařazení v rozhraní `v_firma_obor_aktualni`\n")
        md.append("| stav | IČO |")
        md.append("|---|---:|")
        for stav, n in cur.fetchall():
            md.append(f"| {stav} | {_pocet(n)} |")
        md.append("")

        # --- změna oddílu a sekce
        cur.execute(
            """
            SELECT count(*),
                   count(*) FILTER (WHERE v.oddil IS DISTINCT FROM v.oddil_2008 AND v.oddil IS NOT NULL
                                      AND v.oddil_2008 IS NOT NULL),
                   count(*) FILTER (WHERE v.oddil IS NOT NULL AND v.oddil_2008 IS NOT NULL),
                   count(*) FILTER (WHERE coalesce(a.sekce_rev2, v.sekce) IS DISTINCT FROM v.sekce_2008),
                   count(*) FILTER (WHERE v.sekce IS DISTINCT FROM v.sekce_2008)
            FROM obor.v_firma_obor_aktualni v
            LEFT JOIN obor.nace_sekce_a10 a ON a.sekce_2025 = v.sekce
            WHERE v.zdroj = 'RES' AND v.kod_2008 IS NOT NULL AND v.platnost_do IS NULL
            """
        )
        n, zm_oddil, n_oddil, zm_sekce, zm_pismeno = cur.fetchone()
        md.append("### Změna oddílu a sekce (subjekty bez zániku s oběma kódy z RES)\n")
        md.append(f"- subjektů: {_pocet(n)}")
        md.append(f"- **jiný kód oddílu** 2025 než 2008: {_pocet(zm_oddil)} z {_pocet(n_oddil)} se zařazením "
                  f"aspoň na oddíl ({_procento(zm_oddil, n_oddil)})")
        md.append(f"- **jiná sekce obsahově** (sekce 2025 neodpovídá sekci 2008 podle `obor.nace_sekce_a10`, "
                  f"tj. K 2025 ⊂ J 2008, L 2025 = K 2008 …): {_pocet(zm_sekce)} ({_procento(zm_sekce, n)})")
        md.append(f"- jiné písmeno sekce (jen pro srovnání, písmena se mezi verzemi posunula): "
                  f"{_pocet(zm_pismeno)} ({_procento(zm_pismeno, n)})")
        md.append("")

        # --- pilot sekce F × kraj
        cur.execute(
            """
            SELECT v.oddil_2008, v.oddil, (v.sekce_2008 = %(s08)s) AS v08, (v.sekce = %(s25)s) AS v25, count(*)
            FROM obor.v_firma_obor_aktualni v
            JOIN res.subjekt s ON s.ico = v.ico AND s.datum_snimku = %(d)s AND s.ddatzan IS NULL
            JOIN res.cis_okres o ON o.kod = s.okreslau
            WHERE o.kraj_kod = %(kraj)s AND (v.sekce_2008 = %(s08)s OR v.sekce = %(s25)s)
            GROUP BY 1, 2, 3, 4 ORDER BY 5 DESC
            """,
            {"s08": sekce_2008, "s25": sekce_2025, "d": datum, "kraj": kraj},
        )
        radky = cur.fetchall()
        v08 = sum(r[4] for r in radky if r[2])
        v25 = sum(r[4] for r in radky if r[3])
        oboji = sum(r[4] for r in radky if r[2] and r[3])
        md.append(f"### Pilot: sekce {sekce_2008} (2008) / {sekce_2025} (2025) × kraj {kraj}, subjekty bez zániku\n")
        md.append(f"- v sekci podle CZ-NACE 2008: {_pocet(v08)}; podle CZ-NACE 2025: {_pocet(v25)}; v obou: {_pocet(oboji)}")
        md.append(f"- **přibylo** (2025 ano, 2008 ne): {_pocet(v25 - oboji)}; **ubylo** (2008 ano, 2025 ne): "
                  f"{_pocet(v08 - oboji)}; rozdíl {v25 - v08:+d}")
        md.append("\n| směr | oddíl 2008 | oddíl 2025 | subjektů |")
        md.append("|---|---|---|---:|")
        for o08, o25, a, b, n in radky:
            if a != b:
                md.append(f"| {'přibylo' if b else 'ubylo'} | {o08 or '–'} | {o25 or '–'} | {_pocet(n)} |")
        md.append("")

        # --- kontrola číselníku
        cur.execute("SELECT verze, zdroj, typ, kod, pocet FROM obor.v_firma_nace_mimo_ciselnik ORDER BY pocet DESC")
        mimo = cur.fetchall()
        cur.execute("SELECT count(*) FROM obor.firma_nace WHERE kod IS NOT NULL")
        vse_kody = cur.fetchone()[0]
        md.append("### Kódy mimo číselník své verze\n")
        if mimo:
            md.append(f"**{len(mimo)} kódů ({sum(r[4] for r in mimo)} záznamů) z {vse_kody:,} není v číselníku:**\n"
                      .replace(",", " "))
            for r in mimo[:20]:
                md.append(f"- CZ-NACE {r[0]}, {r[1]}, {r[2]}: `{r[3]}` ({r[4]}×)")
        else:
            md.append(f"Všech {vse_kody:,} kódů ve `firma_nace` je v číselníku své verze.".replace(",", " "))
    conn.commit()
    return "\n".join(md) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="prikaz", required=True)
    r = sub.add_parser("res", help="snímek RES → obor.firma_nace")
    r.add_argument("--datum", type=date.fromisoformat)
    r.add_argument("--bez-vedlejsich", action="store_true", help="jen hlavní činnost")
    sub.add_parser("matice", help="matice přechodů, pravidla a odvozené kódy")
    k = sub.add_parser("kontroly", help="pokrytí, změny, pilot, číselník (Markdown)")
    k.add_argument("--vystup", type=Path)
    sub.add_parser("obnov", help="obnoví materializované rozhraní obor.v_firma_obor_aktualni")
    v = sub.add_parser("vse", help="res + matice + kontroly")
    v.add_argument("--vystup", type=Path)
    args = parser.parse_args()

    from firemni_databaze.db import get_engine

    conn = get_engine().raw_connection()
    try:
        if args.prikaz in ("res", "vse"):
            nacti_res(conn, getattr(args, "datum", None), not getattr(args, "bez_vedlejsich", False))
        if args.prikaz in ("matice", "vse"):
            odvod_firmy(conn, spocti_matici(conn))
        if args.prikaz in ("res", "matice", "obnov", "vse"):
            obnov_rozhrani(conn)
        if args.prikaz in ("kontroly", "vse"):
            text = kontroly(conn)
            print(text)
            if args.vystup:
                args.vystup.write_text(text, encoding="utf-8")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
