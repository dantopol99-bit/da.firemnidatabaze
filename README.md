# Firemní databáze

Datový produkt nad veřejnými registry ČR (např. ARES, obchodní rejstřík, registr ekonomických subjektů).
Cílem je stahovat data z registrů, čistit je a ukládat do PostgreSQL tak, aby nad nimi šlo
dělat analýzy a reporty.

## Struktura projektu

```
.
├── src/firemni_databaze/   # Python balíček (kód projektu)
│   ├── db.py               # připojení k PostgreSQL podle .env
│   └── overeni_schemat.py  # ověří připojení a existenci schémat
├── sql/init/               # SQL skripty spouštěné při prvním startu databáze
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
