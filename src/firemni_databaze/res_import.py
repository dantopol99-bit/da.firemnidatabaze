"""Hromadný import Registru ekonomických subjektů ČSÚ (RES) do schématu res.

Spuštění:
    python -m firemni_databaze.res_import ciselniky              # oficiální číselníky ČSÚ
    python -m firemni_databaze.res_import snimek                 # stáhne poslední snímek, načte, soubory smaže
    python -m firemni_databaze.res_import snimek --adresar DIR   # dříve stažené soubory (ponechá je)
    python -m firemni_databaze.res_import agregaty               # DataStat: RES02QT1, obyvatelstvo, vznik/zánik
    python -m firemni_databaze.res_import vse                    # vše výše v tomto pořadí
    python -m firemni_databaze.res_import prehled                # kvalita, srovnání s ČSÚ, jádro, pilot

Každý příkaz je jedna dávka v dev.import_davka. Snímek se načítá hromadně:
COPY do dočasné tabulky → kontrola počtu řádků a data snímku → INSERT do
res.subjekt / res.pf_nace, oba soubory v jedné transakci. Surové soubory se
stahují do dočasné složky mimo repozitář a po importu se mažou.

Po načtení se spočítá kvalita (res.kvalita). Chybí-li NACE sekce nebo kraj
u víc než 20 % subjektů bez zániku, import skončí kódem 3 a dál se nepokračuje.
"""

import argparse
import hashlib
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

from psycopg2.extras import Json, execute_values

from firemni_databaze import res_zdroj as z
from firemni_databaze.db import get_engine

PRAH_CHYBEJICICH = 0.20            # bod 4 zadání: víc než 20 % → stop
UKAZATELE_PRAHU = ("bez_nace_sekce", "bez_kraje")
KOD_PRAH_PREKROCEN = 3


# ---------------------------------------------------------------------------
# Dávky (dev.import_davka)
# ---------------------------------------------------------------------------

def zahaj_davku(conn, zdroj: str, popis: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO dev.import_davka (zdroj, soubor_nebo_url) VALUES (%s, %s) RETURNING id",
            (zdroj, popis),
        )
        davka = cur.fetchone()[0]
    conn.commit()
    return davka


def ukonci_davku(conn, davka: int, stav: str, pocet: int | None, poznamka: str | None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE dev.import_davka SET konec = now(), stav = %s, pocet_zaznamu = %s, poznamka = %s WHERE id = %s",
            (stav, pocet, poznamka[:4000] if poznamka else None, davka),
        )
    conn.commit()


def v_davce(conn, zdroj: str, popis: str, prace):
    """Spustí prace(davka) jako dávku; chyba = rollback + stav CHYBA."""
    davka = zahaj_davku(conn, zdroj, popis)
    try:
        pocet, poznamka = prace(davka)
    except Exception as exc:
        conn.rollback()
        ukonci_davku(conn, davka, "CHYBA", None, f"{type(exc).__name__}: {exc}")
        raise
    ukonci_davku(conn, davka, "OK", pocet, poznamka)
    return davka


def vloz(cur, tabulka: str, radky: list[dict]) -> None:
    if not radky:
        return
    sloupce = list(radky[0])
    execute_values(
        cur,
        f"INSERT INTO res.{tabulka} ({', '.join(sloupce)}) VALUES %s",
        [tuple(r[s] for s in sloupce) for r in radky],
        page_size=1000,
    )


# ---------------------------------------------------------------------------
# Číselníky
# ---------------------------------------------------------------------------

def nacti_ciselniky(conn, k_datu: date) -> int:
    def prace(davka: int):
        stazene = {}
        for c in z.CISELNIKY:
            url = c.url(k_datu)
            obsah = z.stahni_text(url)
            polozky = z.nacti_csv(obsah)
            if not polozky:
                raise ValueError(f"číselník {c.ciselnik} je prázdný ({url})")
            stazene[c.ciselnik] = (c, url, obsah, polozky)
            print(f"  {c.ciselnik:16} {len(polozky):5} položek  {c.nazev}")

        p = {k: v[3] for k, v in stazene.items()}
        tabulky = {
            "cis_nace": z.radky_nace(p["CZ_NACE_RES"], 80004) + z.radky_nace(p["CZ_NACE_RES2025"], 80143),
            "cis_kraj": z.radky_kraj(p["100"]),
            "cis_okres": z.radky_okres(p["109"], p["109-108"]),
            "cis_pravni_forma": z.radky_pravni_forma(p["56"], 56) + z.radky_pravni_forma(p["149"], 149),
            "cis_katpo": z.radky_jednoduche(p["579"]),
            "cis_zpusob_zaniku": z.radky_jednoduche(p["572"]),
            "cis_zdroj_udaje": z.radky_jednoduche(p["564"]),
        }
        with conn.cursor() as cur:
            # okres odkazuje na kraj: mazat od závislých, vkládat od nadřízených
            for t in ("cis_okres", "cis_kraj", "cis_nace", "cis_pravni_forma", "cis_katpo",
                      "cis_zpusob_zaniku", "cis_zdroj_udaje"):
                cur.execute(f"DELETE FROM res.{t}")
            for t in ("cis_kraj", "cis_okres", "cis_nace", "cis_pravni_forma", "cis_katpo",
                      "cis_zpusob_zaniku", "cis_zdroj_udaje"):
                vloz(cur, t, tabulky[t])
            for c, url, obsah, polozky in stazene.values():
                cur.execute(
                    "INSERT INTO res.cis_zdroj (ciselnik, tabulka, nazev, url, pocet_polozek, sha256, import_davka_id) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (ciselnik) DO UPDATE SET tabulka = EXCLUDED.tabulka, nazev = EXCLUDED.nazev, "
                    "url = EXCLUDED.url, pocet_polozek = EXCLUDED.pocet_polozek, sha256 = EXCLUDED.sha256, "
                    "stazeno = now(), import_davka_id = EXCLUDED.import_davka_id",
                    (c.ciselnik, c.tabulka, c.nazev, url, len(polozky), hashlib.sha256(obsah).hexdigest(), davka),
                )
        conn.commit()
        return sum(len(r) for r in tabulky.values()), f"číselníky ČSÚ k {k_datu:%d.%m.%Y}"

    return v_davce(conn, "CSU-CISELNIKY", "apl2.czso.cz/iSMS + vdb.czso.cz", prace)


# ---------------------------------------------------------------------------
# Snímek RES
# ---------------------------------------------------------------------------

def _q(identifikator: str) -> str:
    return '"' + identifikator.replace('"', '""') + '"'


def copy_do_stagingu(cur, soubor: str, cesta: Path) -> tuple[int, int, str | None]:
    """COPY souboru do dočasné tabulky stg_res (vše text; prázdné i "" = NULL;
    hlavička musí přesně odpovídat sloupcům). Vrací (řádků, různých DATPLAT, DATPLAT)."""
    sloupce = z.SLOUPCE[soubor]
    cur.execute("DROP TABLE IF EXISTS stg_res")
    cur.execute(
        "CREATE TEMP TABLE stg_res (" + ", ".join(f"{_q(s)} text" for s in sloupce) + ") ON COMMIT DROP"
    )
    seznam = ", ".join(_q(s) for s in sloupce)
    with open(cesta, "rb") as f:
        cur.copy_expert(
            f"COPY stg_res FROM STDIN WITH (FORMAT csv, HEADER match, ENCODING 'UTF8', FORCE_NULL ({seznam}))",
            f,
            size=1 << 20,
        )
    cur.execute('SELECT count(*), count(DISTINCT "DATPLAT"), min("DATPLAT") FROM stg_res')
    return cur.fetchone()


def nacti_soubor(cur, soubor: str, cesta: Path, metadata: dict, davka: int) -> tuple[date, int, bool]:
    """Načte jeden soubor snímku. Vrací (datum_snimku, počet řádků, zda byl nově načten)."""
    souhrn = z.souhrn_souboru(cesta)
    z.over_strukturu(soubor, souhrn.hlavicka, metadata)
    sloupce = z.SLOUPCE[soubor]
    tabulka = z.TABULKY[soubor]

    # 1) COPY do dočasné tabulky, 2) kontrola: počet řádků = CSV parser, jediné datum platnosti
    nacteno, pocet_dat, datplat = copy_do_stagingu(cur, soubor, cesta)
    if nacteno != souhrn.pocet_radku:
        raise ValueError(f"{soubor}: COPY načetl {nacteno} řádků, soubor jich má {souhrn.pocet_radku}")
    if pocet_dat != 1:
        raise ValueError(f"{soubor}: soubor obsahuje {pocet_dat} různých DATPLAT, očekáván jeden snímek")
    datum_snimku = date.fromisoformat(datplat)

    # 3) snímek už je v databázi?
    cur.execute("SELECT sha256 FROM res.snimek WHERE datum_snimku = %s AND soubor = %s", (datum_snimku, soubor))
    radek = cur.fetchone()
    if radek:
        if radek[0] != souhrn.sha256:
            raise ValueError(
                f"{soubor} k {datum_snimku}: v databázi je snímek s jiným otiskem ({radek[0]}) – "
                "ČSÚ soubor zřejmě přegeneroval; snímky se nepřepisují"
            )
        print(f"  {soubor}: snímek k {datum_snimku} už je načtený (stejný SHA-256), přeskakuji")
        return datum_snimku, nacteno, False

    cur.execute(
        "INSERT INTO res.snimek (datum_snimku, soubor, url, sha256, velikost_bajtu, posledni_zmena, "
        "pocet_radku, metadata, import_davka_id) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (datum_snimku, soubor, z.url_souboru(soubor), souhrn.sha256, souhrn.velikost_bajtu,
         souhrn.posledni_zmena, souhrn.pocet_radku, Json(metadata), davka),
    )
    snimek_id = cur.fetchone()[0]

    # 4) převod do cílové tabulky – jen typy, žádná změna významu
    cilove = ", ".join(s.lower() for s in sloupce)
    vyrazy = ", ".join(
        f"{_q(s)}::date" if s in z.SLOUPCE_DATUM[soubor] else _q(s) for s in sloupce
    )
    cur.execute(
        f"INSERT INTO res.{tabulka} (datum_snimku, snimek_id, {cilove}) "
        f"SELECT %s, %s, {vyrazy} FROM stg_res",
        (datum_snimku, snimek_id),
    )
    if cur.rowcount != souhrn.pocet_radku:
        raise ValueError(f"{soubor}: do res.{tabulka} vloženo {cur.rowcount} řádků místo {souhrn.pocet_radku}")
    cur.execute("DROP TABLE stg_res")
    print(f"  {soubor}: {souhrn.pocet_radku:,} řádků, snímek k {datum_snimku}, SHA-256 {souhrn.sha256}".replace(",", " "))
    return datum_snimku, nacteno, True


def pripravit_soubory(adresar: Path | None, docasny: Path) -> Path:
    """Vrátí adresář se soubory snímku; bez --adresar je stáhne do dočasné složky."""
    if adresar:
        return adresar
    for soubor in z.SLOUPCE:
        for nazev in (z.soubor_metadat(soubor), soubor):
            print(f"  stahuji {z.url_souboru(nazev)}")
            z.stahni(z.url_souboru(nazev), docasny / nazev)
    return docasny


def uloz_kvalitu(cur, datum_snimku: date) -> None:
    cur.execute("DELETE FROM res.kvalita WHERE datum_snimku = %s", (datum_snimku,))
    cur.execute(
        "INSERT INTO res.kvalita (datum_snimku, zaklad, poradi, ukazatel, popis, pocet, jmenovatel, podil) "
        "SELECT datum_snimku, zaklad, poradi, ukazatel, popis, pocet, jmenovatel, podil "
        "FROM res.v_kvalita WHERE datum_snimku = %s",
        (datum_snimku,),
    )


def prekrocene_prahy(cur, datum_snimku: date, prah: float = PRAH_CHYBEJICICH) -> list[tuple]:
    cur.execute(
        "SELECT ukazatel, popis, pocet, jmenovatel, podil FROM res.kvalita "
        "WHERE datum_snimku = %s AND zaklad = 'bez_zaniku' AND ukazatel = ANY(%s) AND podil > %s "
        "ORDER BY poradi",
        (datum_snimku, list(UKAZATELE_PRAHU), prah),
    )
    return cur.fetchall()


def nacti_snimek(conn, adresar: Path | None) -> tuple[int, date, list[tuple]]:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM res.cis_okres")
        if cur.fetchone()[0] == 0:
            raise SystemExit("Nejdřív načti číselníky: python -m firemni_databaze.res_import ciselniky")
    conn.commit()

    vysledek = {}

    def prace(davka: int):
        with tempfile.TemporaryDirectory(prefix="res_snimek_") as tmp:
            zdroj = pripravit_soubory(adresar, Path(tmp))
            data = {}
            with conn.cursor() as cur:
                cur.execute("SET LOCAL maintenance_work_mem = '1GB'")
                for soubor in z.SLOUPCE:
                    metadata = json.loads((zdroj / z.soubor_metadat(soubor)).read_text(encoding="utf-8"))
                    data[soubor] = nacti_soubor(cur, soubor, zdroj / soubor, metadata, davka)
                datumy = {d for d, _, _ in data.values()}
                if len(datumy) != 1:
                    raise ValueError(f"soubory snímku mají různé DATPLAT: {sorted(datumy)}")
                datum_snimku = datumy.pop()
                uloz_kvalitu(cur, datum_snimku)
            conn.commit()
            if not adresar:
                print("  stažené soubory se mažou (do repozitáře nepatří)")
        with conn.cursor() as cur:
            for t in ("subjekt", "pf_nace"):
                cur.execute(f"ANALYZE res.{t}")
            prahy = prekrocene_prahy(cur, datum_snimku)
        conn.commit()
        vysledek.update(datum=datum_snimku, prahy=prahy)
        pocet = sum(n for _, n, nove in data.values() if nove)
        poznamka = f"snímek k {datum_snimku}"
        if prahy:
            poznamka += "; PRAH 20 % PŘEKROČEN: " + ", ".join(p[0] for p in prahy)
        return pocet, poznamka

    popis = str(adresar) if adresar else z.RES_URL
    davka = v_davce(conn, "RES", popis, prace)
    return davka, vysledek["datum"], vysledek["prahy"]


# ---------------------------------------------------------------------------
# Agregáty ČSÚ
# ---------------------------------------------------------------------------

def nacti_agregaty(conn, vyber: str = z.DATASTAT_VYBER) -> int:
    url = z.url_datastat(vyber)

    def prace(davka: int):
        definice = json.loads(z.stahni_text(z.DATASTAT_KATALOG + vyber))
        radky = z.radky_agregatu(z.stahni_text(url), definice)
        for r in radky:
            r.update(url=url, import_davka_id=davka)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM res.csu_agregat WHERE vyber = %s", (vyber,))
            vloz(cur, "csu_agregat", radky)
            cur.execute("SELECT max(obdobi) FROM res.csu_agregat WHERE vyber = %s", (vyber,))
            posledni = cur.fetchone()[0]
        conn.commit()
        print(f"  {vyber}: {len(radky)} hodnot, poslední čtvrtletí {posledni}")
        return len(radky), f"DataStat {vyber}, poslední čtvrtletí {posledni}"

    return v_davce(conn, "CSU-DATASTAT", url, prace)


def nacti_obyvatelstvo(conn, rok: int = date.today().year - 1) -> int:
    """Počet obyvatel ČR, krajů a okresů z DataStatu (OBY02A) za zadaný rok."""
    url = z.url_vlastni_vyber("OBY02A")

    def prace(davka: int):
        definice = json.loads(z.stahni_text(z.DATASTAT_SADY + "OBY02A"))
        radky = z.radky_obyvatel(z.stahni_post_json(url, z.vyber_obyvatel(rok)), definice)
        if not any(r["uroven"] == "OKRES" for r in radky):
            raise ValueError(f"OBY02A za rok {rok} neobsahuje okresy")
        for r in radky:
            r.update(url=url, import_davka_id=davka)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM res.csu_obyvatelstvo WHERE rok = %s", (rok,))
            vloz(cur, "csu_obyvatelstvo", radky)
        conn.commit()
        print(f"  OBY02A: {len(radky)} hodnot za rok {rok}")
        return len(radky), f"DataStat OBY02A, rok {rok}"

    return v_davce(conn, "CSU-DATASTAT", url, prace)


def nacti_demografii(conn) -> int:
    """Demografie podniků ČR (DataStat RESDP00) – kontext za ČR, jiná jednotka (podnik)."""
    url = z.url_sady_csv("RESDP00")

    def prace(davka: int):
        definice = json.loads(z.stahni_text(z.DATASTAT_SADY + "RESDP00"))
        radky = z.radky_demografie(z.stahni_text(url), definice)
        for r in radky:
            r.update(url=url, import_davka_id=davka)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM res.csu_demografie")
            vloz(cur, "csu_demografie", radky)
        conn.commit()
        roky = sorted({r["rok"] for r in radky})
        print(f"  RESDP00: {len(radky)} hodnot, {roky[0]} – {roky[-1]}")
        return len(radky), f"DataStat RESDP00, {roky[0]} – {roky[-1]}"

    return v_davce(conn, "CSU-DATASTAT", url, prace)


def nacti_vznik_zanik(conn) -> int:
    """Vzniklé a zaniklé ekonomické subjekty (DataStat RES05) – celá sada."""
    url = z.url_sady_csv("RES05")

    def prace(davka: int):
        definice = json.loads(z.stahni_text(z.DATASTAT_SADY + "RES05"))
        radky = z.radky_vznik_zanik(z.stahni_text(url), definice)
        for r in radky:
            r.update(url=url, import_davka_id=davka)
        with conn.cursor() as cur:
            cur.execute("DELETE FROM res.csu_vznik_zanik")
            vloz(cur, "csu_vznik_zanik", radky)
            cur.execute("SELECT min(obdobi), max(obdobi) FROM res.csu_vznik_zanik")
            od, do = cur.fetchone()
        conn.commit()
        print(f"  RES05: {len(radky)} hodnot, {od} – {do}")
        return len(radky), f"DataStat RES05, {od} – {do}"

    return v_davce(conn, "CSU-DATASTAT", url, prace)


# ---------------------------------------------------------------------------
# Přehled výsledků
# ---------------------------------------------------------------------------

def _tabulka(cur, sql: str, parametry=()) -> None:
    cur.execute(sql, parametry)
    hlavicka = [d[0] for d in cur.description]
    radky = [["" if v is None else str(v) for v in r] for r in cur.fetchall()]
    sirky = [max(len(h), *(len(r[i]) for r in radky)) if radky else len(h) for i, h in enumerate(hlavicka)]
    print("  " + "  ".join(h.ljust(s) for h, s in zip(hlavicka, sirky)))
    for r in radky:
        print("  " + "  ".join(v.rjust(s) if v.replace(".", "").replace("-", "").isdigit() else v.ljust(s)
                              for v, s in zip(r, sirky)))


def prehled(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT res.posledni_snimek()")
        datum = cur.fetchone()[0]
        if datum is None:
            print("Žádný snímek RES není načtený.")
            return
        print(f"\n== Kvalita snímku k {datum}")
        _tabulka(cur, """
            SELECT k.popis, a.pocet AS vse, round(100 * a.podil, 2) AS "vse_pct",
                   b.pocet AS bez_zaniku, round(100 * b.podil, 2) AS "bez_zaniku_pct"
            FROM res.kvalita a
            JOIN res.kvalita b USING (datum_snimku, ukazatel)
            JOIN res.kvalita k USING (datum_snimku, ukazatel)
            WHERE a.datum_snimku = %s AND a.zaklad = 'vse' AND b.zaklad = 'bez_zaniku' AND k.zaklad = 'vse'
            ORDER BY a.poradi""", (datum,))
        print("\n== Srovnání s ČSÚ po krajích (subjekty bez zániku)")
        _tabulka(cur, """
            SELECT uzemi_kod, uzemi, nase_bez_zaniku, csu_registrovane, rozdil, rozdil_pct AS "rozdil_pct",
                   nase_k_datu_csu, rozdil_k_datu_csu_pct AS "rozdil_k_datu_pct",
                   csu_se_zjistenou_aktivitou, csu_podil_aktivnich_pct AS "aktivni_pct", csu_obdobi
            FROM res.v_srovnani_csu WHERE nace_kod = '0' ORDER BY uzemi_kod = 'CZ' DESC, uzemi_kod""")
        print("\n== Srovnání s ČSÚ po odvětvích CZ-NACE (ČR)")
        _tabulka(cur, """
            SELECT nace, nase_bez_zaniku, csu_registrovane, rozdil, rozdil_pct AS "rozdil_pct",
                   rozdil_k_datu_csu_pct AS "rozdil_k_datu_pct", csu_podil_aktivnich_pct AS "aktivni_pct"
            FROM res.v_srovnani_csu WHERE uzemi_kod = 'CZ' ORDER BY nace_kod = '0' DESC, nace""")
        print("\n== Buňky kraj × odvětví s rozdílem nad 10 %")
        _tabulka(cur, """
            SELECT uzemi, nace, nase_bez_zaniku, csu_registrovane, rozdil_pct AS "rozdil_pct",
                   rozdil_k_datu_csu_pct AS "rozdil_k_datu_pct"
            FROM res.v_srovnani_csu WHERE nad_10_pct ORDER BY abs(rozdil_pct) DESC NULLS FIRST""")
        print("\n== Jádro (ARES) proti RES")
        _tabulka(cur, "SELECT * FROM res.v_jadro_kontrola_souhrn")
        print("\n== Pilot: sekce F × Liberecký kraj (práh 10 subjektů)")
        _tabulka(cur, """
            SELECT clenitko, kod, kategorie, pocet,
                   CASE WHEN pod_prahem THEN 'POD PRAHEM – nepublikovat' ELSE '' END AS prah
            FROM res.v_pilot_f_liberecky""")
    conn.commit()


# ---------------------------------------------------------------------------

def nacti_mzdy(conn) -> list[int]:
    """Zaměstnanci a průměrné mzdy (DataStat MZDCRR, MZDR) – každý výběr ve vlastní dávce."""
    davky = []
    for vyber, (sada, _, popis) in z.MZDY_VYBERY.items():
        url = z.url_datastat(vyber)

        def prace(davka: int, vyber=vyber, sada=sada, popis=popis, url=url):
            definice = json.loads(z.stahni_text(z.DATASTAT_SADY + sada))
            radky = z.radky_mzdy(vyber, z.stahni_text(url), definice)
            if not radky:
                raise ValueError(f"{vyber}: žádné hodnoty")
            for r in radky:
                r.update(url=url, import_davka_id=davka)
            with conn.cursor() as cur:
                cur.execute("DELETE FROM res.csu_mzdy WHERE vyber = %s", (vyber,))
                vloz(cur, "csu_mzdy", radky)
            conn.commit()
            print(f"  {vyber}: {len(radky)} hodnot ({popis})")
            return len(radky), f"DataStat {vyber} ({sada}): {popis}"

        davky.append(v_davce(conn, "CSU-DATASTAT", url, prace))
    return davky


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="prikaz", required=True)
    p_cis = sub.add_parser("ciselniky", help="načte oficiální číselníky ČSÚ")
    p_cis.add_argument("--k-datu", type=date.fromisoformat, default=date.today(), help="platnost číselníků (YYYY-MM-DD)")
    p_sn = sub.add_parser("snimek", help="načte snímek RES")
    p_sn.add_argument("--adresar", type=Path, help="adresář s dříve staženými res_data.csv, res_pf_nace.csv a *-metadata.json")
    sub.add_parser("agregaty", help="načte agregáty ČSÚ z DataStatu (RES02QT1, OBY02A, RES05, RESDP00, mzdy)")
    sub.add_parser("mzdy", help="načte zaměstnance a průměrné mzdy z DataStatu (MZDCRR, MZDR)")
    p_vse = sub.add_parser("vse", help="číselníky + snímek + agregáty")
    p_vse.add_argument("--adresar", type=Path)
    sub.add_parser("prehled", help="vypíše kvalitu, srovnání s ČSÚ, kontrolu jádra a pilot")
    args = parser.parse_args()

    conn = get_engine().raw_connection()
    try:
        if args.prikaz in ("ciselniky", "vse"):
            print("Číselníky ČSÚ:")
            davka = nacti_ciselniky(conn, getattr(args, "k_datu", date.today()))
            print(f"  dávka {davka} OK")
        if args.prikaz in ("snimek", "vse"):
            print("Snímek RES:")
            davka, datum, prahy = nacti_snimek(conn, args.adresar)
            print(f"  dávka {davka} OK, snímek k {datum}")
            if prahy:
                print("STOP – chybějící údaje u víc než 20 % subjektů bez zániku:")
                for ukazatel, popis, pocet, jmenovatel, podil in prahy:
                    print(f"  {popis}: {pocet} z {jmenovatel} ({100 * podil:.2f} %)")
                print("Data jsou načtená, ale před dalším použitím je potřeba rozhodnutí.")
                return KOD_PRAH_PREKROCEN
        if args.prikaz in ("agregaty", "vse"):
            print("Agregáty ČSÚ:")
            for davka in (nacti_agregaty(conn), nacti_obyvatelstvo(conn), nacti_vznik_zanik(conn),
                          nacti_demografii(conn)):
                print(f"  dávka {davka} OK")
        if args.prikaz in ("agregaty", "mzdy", "vse"):
            print("Zaměstnanci a mzdy ČSÚ:")
            for davka in nacti_mzdy(conn):
                print(f"  dávka {davka} OK")
        if args.prikaz in ("prehled", "vse"):
            prehled(conn)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
