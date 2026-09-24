"""Import subjektů z ARES do identitního jádra (schéma dev).

Spuštění:
    python -m firemni_databaze.ares_import --ico 27082440 04115210
    python -m firemni_databaze.ares_import --soubor-ico seznam.txt
    python -m firemni_databaze.ares_import --adresar data/ares_vzorek   # offline: <adresar>/<endpoint>/<ico>.json

Postup pro každé IČO:
  1. stáhne (nebo načte) obě odpovědi ARES a VŽDY je uloží do import_surova_data,
  2. převede je na řádky jádra (ares_mapovani),
  3. zapíše je s historizací: aktuálně evidované verze, které se nezměnily
     (stejný hash_obsahu), zůstanou; zmizelé se uzavřou (zaznamenano_do);
     nové se vloží. Opakovaný import stejných dat nic nemění.
Každý subjekt běží ve vlastní transakci – chyba jednoho neshodí ostatní.
Celý běh je jedna dávka v import_davka.
"""

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

from psycopg2.extras import Json

from firemni_databaze import ares_klient
from firemni_databaze.ares_mapovani import MapovanySubjekt, mapuj, normalizuj
from firemni_databaze.db import get_engine

SLOUPCE_VERZE = (
    "nazev", "pravni_forma_kod", "stav_kod", "je_v_likvidaci", "je_v_insolvenci",
    "datum_vzniku", "datum_zaniku", "dic", "spisova_znacka", "zakladni_kapital",
    "zakladni_kapital_mena", "cz_nace", "datum_aktualizace_zdroje", "platnost_od", "platnost_do",
)
SLOUPCE_ADRESA = (
    "ruian_kod", "ulice", "cislo_popisne", "cislo_evidencni", "cislo_orientacni", "obec",
    "cast_obce", "psc", "stat", "kod_obce", "kod_kraje", "text_puvodni",
)
SLOUPCE_OSOBA = ("jmeno", "prijmeni", "titul_pred", "titul_za", "datum_narozeni", "statni_prislusnost")
SLOUPCE_VAZBA = (
    "clen_osoba_id", "clen_ico", "clen_nazev", "clen_stat", "role_kod", "organ_puvodni",
    "vklad", "vklad_mena", "podil_text", "podil_procento", "splaceno_procento",
    "platnost_od", "platnost_do", "datum_zapisu_or", "datum_vymazu_or",
)


def otisk(radek: dict, sloupce: tuple) -> str:
    def hodnota(v):
        if isinstance(v, (date, Decimal)):
            return str(v)
        return v
    return hashlib.md5(
        json.dumps({s: hodnota(radek.get(s)) for s in sloupce}, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


# ---------------------------------------------------------------------------
# Zápis do databáze
# ---------------------------------------------------------------------------

def synchronizuj(cur, tabulka: str, ico: str, radky: list[dict], sloupce: tuple, davka: int) -> tuple[int, int]:
    """Porovná aktuálně evidované verze subjektu s novými (podle hash_obsahu).

    Vrací (vloženo, uzavřeno).
    """
    cur.execute(f"SELECT id, hash_obsahu FROM dev.{tabulka} WHERE ico = %s AND zaznamenano_do IS NULL", (ico,))
    stavajici: dict[str, list[int]] = {}
    for id_, h in cur.fetchall():
        stavajici.setdefault(h, []).append(id_)

    nove = {}
    for r in radky:
        nove.setdefault(otisk(r, sloupce), r)

    uzavrit = [i for h, ids in stavajici.items() if h not in nove for i in ids]
    if uzavrit:
        cur.execute(f"UPDATE dev.{tabulka} SET zaznamenano_do = now() WHERE id = ANY(%s)", (uzavrit,))

    vlozeno = 0
    for h, r in nove.items():
        if h in stavajici:
            continue
        cols = ("ico",) + sloupce + ("import_davka_id", "hash_obsahu")
        cur.execute(
            f"INSERT INTO dev.{tabulka} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
            (ico, *[r.get(s) for s in sloupce], davka, h),
        )
        vlozeno += 1
    return vlozeno, len(uzavrit)


def zajisti_subjekt(cur, ico: str, davka: int) -> bool:
    """Založí identitu subjektu, pokud ještě není. Vrací True, pokud vznikla."""
    cur.execute(
        "INSERT INTO dev.subjekt (ico, import_davka_id) VALUES (%s, %s) ON CONFLICT (ico) DO NOTHING",
        (ico, davka),
    )
    return cur.rowcount == 1


def zajisti_adresu(cur, a: dict) -> int:
    """Vrátí id adresy. S RÚIAN kódem se adresa pozná podle kódu (text se může
    drobně lišit), bez něj podle otisku obsahu."""
    a = {s: a.get(s) for s in SLOUPCE_ADRESA}
    a["stat"] = a["stat"] or "CZ"
    if a["ruian_kod"] is not None:
        cur.execute("SELECT id FROM dev.adresa WHERE ruian_kod = %s", (a["ruian_kod"],))
        radek = cur.fetchone()
        if radek:
            return radek[0]
        konflikt = "(ruian_kod)"
    else:
        konflikt = "(hash_adresy) WHERE ruian_kod IS NULL"
    cur.execute(
        f"INSERT INTO dev.adresa ({', '.join(SLOUPCE_ADRESA)}) VALUES ({', '.join(['%s'] * len(SLOUPCE_ADRESA))}) "
        f"ON CONFLICT {konflikt} DO NOTHING RETURNING id",
        tuple(a.values()),
    )
    radek = cur.fetchone()
    if radek:
        return radek[0]
    if a["ruian_kod"] is not None:
        cur.execute("SELECT id FROM dev.adresa WHERE ruian_kod = %s", (a["ruian_kod"],))
    else:
        cur.execute(
            "SELECT id FROM dev.adresa WHERE ruian_kod IS NULL AND hash_adresy = dev.otisk_adresy("
            "%(ulice)s, %(cislo_popisne)s, %(cislo_evidencni)s, %(cislo_orientacni)s, "
            "%(obec)s, %(cast_obce)s, %(psc)s, %(stat)s, %(text_puvodni)s)",
            a,
        )
    return cur.fetchone()[0]


def zajisti_osobu(cur, o: dict, davka: int, stat: Counter) -> int:
    """Najde osobu podle párovacího klíče, případně ji založí; při změně
    údajů (tituly, občanství…) uzavře starou verzi a vloží novou."""
    cur.execute("SELECT dev.klic_osoby(%s, %s, %s)", (o["jmeno"], o["prijmeni"], o["datum_narozeni"]))
    klic = cur.fetchone()[0]
    cur.execute("SELECT id FROM dev.osoba WHERE klic_parovani = %s", (klic,))
    radek = cur.fetchone()
    if radek:
        osoba_id = radek[0]
    else:
        cur.execute(
            "INSERT INTO dev.osoba (klic_parovani, import_davka_id) VALUES (%s, %s) RETURNING id",
            (klic, davka),
        )
        osoba_id = cur.fetchone()[0]
        stat["osoby_nove"] += 1

    h = otisk(o, SLOUPCE_OSOBA)
    cur.execute(
        "SELECT id, hash_obsahu FROM dev.osoba_verze WHERE osoba_id = %s AND zaznamenano_do IS NULL",
        (osoba_id,),
    )
    verze = cur.fetchall()
    if any(vh == h for _, vh in verze):
        return osoba_id
    if verze:
        cur.execute("UPDATE dev.osoba_verze SET zaznamenano_do = now() WHERE id = ANY(%s)", ([v[0] for v in verze],))
    cur.execute(
        f"INSERT INTO dev.osoba_verze (osoba_id, {', '.join(SLOUPCE_OSOBA)}, import_davka_id, hash_obsahu) "
        f"VALUES (%s, {', '.join(['%s'] * len(SLOUPCE_OSOBA))}, %s, %s)",
        (osoba_id, *[o[s] for s in SLOUPCE_OSOBA], davka, h),
    )
    return osoba_id


def uloz_surova_data(cur, davka: int, ico: str, odpovedi: dict[str, ares_klient.Odpoved]) -> None:
    for o in odpovedi.values():
        cur.execute(
            "INSERT INTO dev.import_surova_data (import_davka_id, ico, endpoint, http_status, raw) "
            "VALUES (%s, %s, %s, %s, %s)",
            (davka, ico, o.endpoint, o.http_status, Json(o.data)),
        )


def uloz_subjekt(cur, m: MapovanySubjekt, osoby: dict, davka: int, stat: Counter) -> None:
    if zajisti_subjekt(cur, m.ico, davka):
        stat["subjekty_nove"] += 1

    v, u = synchronizuj(cur, "subjekt_verze", m.ico, m.verze, SLOUPCE_VERZE, davka)
    stat["subjekt_verze_vlozeno"] += v
    stat["subjekt_verze_uzavreno"] += u

    radky_adres = []
    for a in m.adresy:
        radky_adres.append({"adresa_id": zajisti_adresu(cur, a["adresa"]), "typ_adresy_kod": a["typ"],
                            "platnost_od": a["platnost_od"], "platnost_do": a["platnost_do"]})
    v, u = synchronizuj(cur, "subjekt_adresa", m.ico, radky_adres,
                        ("adresa_id", "typ_adresy_kod", "platnost_od", "platnost_do"), davka)
    stat["subjekt_adresa_vlozeno"] += v
    stat["subjekt_adresa_uzavreno"] += u

    radky_vazeb = []
    for vz in m.vazby:
        clen = vz["clen"]
        r = {k: vz[k] for k in SLOUPCE_VAZBA if k in vz}
        if clen["typ"] == "OSOBA":
            o = osoby.get(_klic_osoby(clen["osoba"]), clen["osoba"])
            r["clen_osoba_id"] = zajisti_osobu(cur, o, davka, stat)
        elif clen["typ"] == "SUBJEKT":
            if zajisti_subjekt(cur, clen["ico"], davka):
                stat["subjekty_jen_identita"] += 1
            r["clen_ico"] = clen["ico"]
        else:
            r["clen_nazev"], r["clen_stat"] = clen["nazev"], clen["stat"]
        radky_vazeb.append(r)
    v, u = synchronizuj(cur, "vazba", m.ico, radky_vazeb, SLOUPCE_VAZBA, davka)
    stat["vazba_vlozeno"] += v
    stat["vazba_uzavreno"] += u


def _klic_osoby(o: dict) -> tuple:
    return (normalizuj(o["jmeno"]), normalizuj(o["prijmeni"]), o["datum_narozeni"])


def nejnovejsi_udaje_osob(mapovane: list[MapovanySubjekt]) -> dict:
    """Pro každou osobu (párovací klíč) údaje z nejnověji zapsaného výskytu."""
    nejlepsi: dict[tuple, tuple] = {}
    for m in mapovane:
        for vz in m.vazby:
            if vz["clen"]["typ"] != "OSOBA":
                continue
            o = vz["clen"]["osoba"]
            klic = _klic_osoby(o)
            poradi = vz["datum_zapisu_or"] or date.min
            if klic not in nejlepsi or poradi > nejlepsi[klic][0]:
                nejlepsi[klic] = (poradi, o)
    return {k: o for k, (_, o) in nejlepsi.items()}


# ---------------------------------------------------------------------------
# Běh dávky
# ---------------------------------------------------------------------------

def nacti_z_adresare(adresar: Path, ico: str) -> dict[str, ares_klient.Odpoved]:
    vysledek = {}
    for endpoint, podadresar in ((ares_klient.ENDPOINT_ZAKLAD, "zakl"), (ares_klient.ENDPOINT_VR, "vr")):
        soubor = adresar / podadresar / f"{ico}.json"
        data = json.loads(soubor.read_text(encoding="utf-8")) if soubor.exists() else {"kod": "NENALEZENO"}
        vysledek[endpoint] = ares_klient.Odpoved(endpoint, 404 if "kod" in data else 200, data)
    return vysledek


def importuj(ica: list[str], zdroj_popis: str, nacti) -> tuple[int, Counter, list, list]:
    engine = get_engine()
    conn = engine.raw_connection()
    stat: Counter = Counter()
    chyby: list[tuple[str, str]] = []
    preskoceno: list[tuple[str, str, str]] = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO dev.import_davka (zdroj, soubor_nebo_url) VALUES ('ARES', %s) RETURNING id",
                (zdroj_popis,),
            )
            davka = cur.fetchone()[0]
        conn.commit()

        # 1) stažení + uložení surových dat (vždy), 2) převod
        mapovane: list[MapovanySubjekt] = []
        for ico in ica:
            try:
                odpovedi = nacti(ico)
                with conn.cursor() as cur:
                    uloz_surova_data(cur, davka, ico, odpovedi)
                conn.commit()
                stat["surova_data"] += len(odpovedi)
                zakl = odpovedi[ares_klient.ENDPOINT_ZAKLAD]
                if not zakl.nalezeno:
                    raise ValueError(f"ARES subjekt nenašel ({zakl.data.get('kod')})")
                m = mapuj(zakl.data, odpovedi[ares_klient.ENDPOINT_VR].data)
                mapovane.append(m)
                preskoceno += [(ico, d, x) for d, x in m.preskoceno]
                stat["varovani"] += len(m.varovani)
            except Exception as exc:  # noqa: BLE001 – chyba jednoho subjektu nezastaví dávku
                conn.rollback()
                chyby.append((ico, f"{type(exc).__name__}: {exc}"))

        # 3) zápis do jádra, každý subjekt ve vlastní transakci
        osoby = nejnovejsi_udaje_osob(mapovane)
        for m in mapovane:
            try:
                with conn.cursor() as cur:
                    uloz_subjekt(cur, m, osoby, davka, stat)
                conn.commit()
                stat["subjekty_zpracovane"] += 1
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                chyby.append((m.ico, f"{type(exc).__name__}: {exc}".splitlines()[0]))

        with conn.cursor() as cur:
            cur.execute("SELECT dev.oznac_kandidaty_slouceni()")
            stat["kandidati_slouceni_nove"] = cur.fetchone()[0]
            poznamka = "; ".join(f"{i}: {c}" for i, c in chyby)[:4000] or None
            cur.execute(
                "UPDATE dev.import_davka SET konec = now(), pocet_zaznamu = %s, stav = %s, poznamka = %s "
                "WHERE id = %s",
                (stat["subjekty_zpracovane"], "CHYBA" if chyby else "OK", poznamka, davka),
            )
        conn.commit()
    finally:
        conn.close()
    return davka, stat, chyby, preskoceno


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    zdroj = parser.add_mutually_exclusive_group(required=True)
    zdroj.add_argument("--ico", nargs="+", help="seznam IČO")
    zdroj.add_argument("--soubor-ico", type=Path, help="soubor s IČO (jedno na řádek)")
    zdroj.add_argument("--adresar", type=Path, help="offline: dříve stažené odpovědi <adresar>/{zakl,vr}/<ico>.json")
    args = parser.parse_args()

    if args.adresar:
        ica = sorted(p.stem for p in (args.adresar / "zakl").glob("*.json"))
        nacti = lambda ico: nacti_z_adresare(args.adresar, ico)  # noqa: E731
        popis = f"soubory: {args.adresar}"
    else:
        ica = args.ico or [r.strip() for r in args.soubor_ico.read_text().splitlines() if r.strip()]
        nacti = ares_klient.stahni_subjekt
        popis = ares_klient.ARES_URL

    davka, stat, chyby, preskoceno = importuj(ica, popis, nacti)

    print(f"Dávka {davka}: {stat['subjekty_zpracovane']} z {len(ica)} subjektů zpracováno.")
    for k in sorted(stat):
        print(f"  {k:28} {stat[k]}")
    if preskoceno:
        print(f"Přeskočené údaje ({len(preskoceno)}):")
        for (d, x), n in Counter((d, x) for _, d, x in preskoceno).most_common():
            print(f"  {n:4}×  {d}: {x}")
    if chyby:
        print(f"CHYBY ({len(chyby)}):")
        for ico, c in chyby:
            print(f"  {ico}: {c}")
    return 1 if chyby else 0


if __name__ == "__main__":
    sys.exit(main())
