# Firemní databáze

Datový produkt nad veřejnými registry ČR (např. ARES, obchodní rejstřík, registr ekonomických subjektů).
Cílem je stahovat data z registrů, čistit je a ukládat do PostgreSQL tak, aby nad nimi šlo
dělat analýzy a reporty.

## Struktura projektu

```
.
├── src/firemni_databaze/   # Python balíček (kód projektu)
│   ├── db.py               # připojení k PostgreSQL podle .env
│   ├── overeni_schemat.py  # ověří připojení a existenci schémat
│   ├── nasad_sql.py        # nasadí SQL skripty ze sql/<schema>/
│   ├── ares_klient.py      # stahování z REST API ARES
│   ├── ares_mapovani.py    # převod odpovědí ARES na řádky jádra (bez DB)
│   └── ares_import.py      # import z ARES do dev (historizace + import_davka)
├── sql/init/               # SQL skripty spouštěné při prvním startu databáze
├── sql/dev/                # identitní jádro – tabulky ve schématu dev
├── docs/                   # návrhy a rozhodnutí (např. mapování ARES)
├── tests/                  # testy (unittest)
├── data/                   # lokální data – NEcommitují se
├── docker-compose.yml      # lokální PostgreSQL v Dockeru
├── .env.example            # vzor konfigurace (zkopírovat na .env)
├── requirements.txt        # Python závislosti
└── pyproject.toml          # aby šel balíček nainstalovat (pip install -e .)
```

### Schémata v databázi

| schéma | účel |
|--------|------|
| `dev`  | vývoj a pokusy |
| `test` | testování načítání dat |
| `prod` | ověřená data |

## Jak spustit lokálně

Potřebuješ: **Git**, **Python 3.10+** a **Docker Desktop** (běžící).

```bash
# 1) Stažení repa
git clone https://github.com/dantopol99-bit/da.firemnidatabaze.git
cd da.firemnidatabaze

# 2) Konfigurace – zkopíruj vzor a v .env změň heslo
cp .env.example .env          # Windows PowerShell: Copy-Item .env.example .env

# 3) Spuštění databáze
docker compose up -d
docker compose ps             # počkej, až bude STATUS "healthy"

# 4) Python prostředí
python -m venv .venv
source .venv/bin/activate     # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .

# 5) Ověření
python -m firemni_databaze.overeni_schemat
python -m unittest discover -s tests
```

## Identitní jádro (schéma `dev`)

SQL skripty jsou v `sql/dev/` a nasazují se v pořadí podle čísla:

| skript | obsah |
|--------|-------|
| `01_zaklad.sql` | rozšíření, typ `dev.ico`, kontrola IČO, párovací klíč osoby, stráže historizace |
| `02_ciselniky.sql` | právní formy (úplný číselník z ARES), stavy subjektu, typy adres, role (jen role z OR) |
| `03_import_davka.sql` | evidence načtení dat (původ každého údaje) + surové odpovědi zdroje (`import_surova_data`) |
| `04_subjekt.sql` | `subjekt` (klíč IČO) + `subjekt_verze` |
| `05_osoba.sql` | `osoba` (interní ID + párovací klíč) + `osoba_verze` |
| `06_adresa.sql` | `adresa` (neměnné) + `subjekt_adresa` |
| `07_vazba.sql` | vazby osoba/firma → firma podle obchodního rejstříku |
| `08_pohledy.sql` | `*_aktualne` pohledy a funkce `subjekt_k_datu` |

Nasazení (opakovatelné, skripty jsou idempotentní):

```bash
python -m firemni_databaze.nasad_sql dev
```

**Historizace:** verze mají dvě časové osy – `platnost_od/do` (kdy údaj platil podle registru,
interval `[od, do)`) a `zaznamenano_od/do` (kdy jsme ho evidovali). Změna = uzavřít starou verzi
(`zaznamenano_do = now()`) a vložit novou. Mazání a přepisování databáze sama zakazuje (triggery).

**Rozsah vazeb:** jen přímé vazby zapsané v obchodním rejstříku. Skuteční (koncoví) majitelé
nejsou součástí – jejich evidence není od 17. 12. 2025 veřejná.

**Schéma se změnilo (mapování ARES):** skripty používají `CREATE TABLE IF NOT EXISTS`, takže do
už existujícího `dev` nové sloupce nepřidají. Pokud máš `dev` nasazené z dřívějška, založ ho
znovu (viz níže).

## Import z ARES

Mapování a jeho rozhodnutí jsou popsané v [`docs/ares_mapovani.md`](docs/ares_mapovani.md).

```bash
python -m firemni_databaze.ares_import --ico 27082440 04115210
python -m firemni_databaze.ares_import --soubor-ico seznam_ico.txt
```

Každý běh je jedna dávka v `dev.import_davka`. Surové odpovědi ARES se ukládají vždy
(`dev.import_surova_data`). Opakovaný import stejných dat nic nezmění; změněné údaje uzavřou
starou verzi a vloží novou. Každý subjekt běží ve vlastní transakci, takže chyba jednoho
neshodí ostatní. Na konci se vypíše souhrn, přeskočené údaje a chyby.

Chceš-li `dev` začít úplně od nuly (smaže vše v něm):
`docker compose exec db psql -U firemni -d firemni_databaze -c "DROP SCHEMA dev CASCADE; CREATE SCHEMA dev;"`
a pak znovu `python -m firemni_databaze.nasad_sql dev`.

Zastavení databáze: `docker compose down` (data zůstanou ve volume).
Smazání i s daty: `docker compose down -v`.

## Řešení problémů

- **Chybí schémata** – init skripty v `sql/init/` se spouští jen při *prvním* startu s prázdným
  volume. Pokud jsi databázi spustil dřív, buď smaž volume (`docker compose down -v` a znovu
  `docker compose up -d`), nebo skript spusť ručně:
  `docker compose exec -T db psql -U firemni -d firemni_databaze < sql/init/01_schemata.sql`
- **Port 5432 je obsazený** (běží ti jiný PostgreSQL) – v `.env` nastav `POSTGRES_PORT=5433`
  a spusť `docker compose up -d` znovu.
- **Změnil jsem heslo v .env a nejde se připojit** – heslo se nastavuje jen při vytvoření volume.
  Buď vrať původní, nebo `docker compose down -v` a začni znovu.
