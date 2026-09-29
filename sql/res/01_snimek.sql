-- =====================================================================
-- 01_snimek.sql – schéma res: Registr ekonomických subjektů ČSÚ (RES)
--
-- RES je druhý zdroj platformy vedle ARES. Na rozdíl od ARES (dotazy
-- po jednotlivých IČO) se načítá hromadně: celý snímek otevřených dat
-- ČSÚ (stav k 15. dni a ke konci měsíce). Podklad pro Oborově-regionální
-- report – potřebuje celou populaci subjektů v průniku obor × území.
--
-- Schéma res NESAHÁ do identitního jádra (dev.subjekt, dev.subjekt_verze,
-- dev.adresa, dev.vazba…). Z dev používá jen:
--   * dev.import_davka   – evidence načtení (každý import = jedna dávka),
--   * dev.zakaz_zmeny(), dev.zakaz_mazani() – stráže neměnnosti,
--   * dev.subjekt_aktualne + dev.adresa – jen ke čtení v kontrolním pohledu.
-- Proto se nasazuje až po schématu dev:  nasad_sql dev && nasad_sql res
--
-- Skript je idempotentní – lze ho spustit opakovaně.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS res;

COMMENT ON SCHEMA res IS 'Registr ekonomických subjektů ČSÚ – hromadné snímky otevřených dat';

-- ---------------------------------------------------------------------
-- Snímek = jeden stažený soubor RES k jednomu datu (DATPLAT).
-- Jeden snímek RES má dva soubory (res_data.csv, res_pf_nace.csv),
-- proto je klíčem datum + soubor.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS res.snimek (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    datum_snimku     date        NOT NULL,          -- DATPLAT (stav k datu)
    soubor           text        NOT NULL
                     CHECK (soubor IN ('res_data.csv', 'res_pf_nace.csv')),
    url              text        NOT NULL,
    sha256           text        NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    velikost_bajtu   bigint      NOT NULL CHECK (velikost_bajtu > 0),
    posledni_zmena   timestamptz,                   -- Last-Modified souboru na serveru ČSÚ
    pocet_radku      bigint      NOT NULL CHECK (pocet_radku >= 0),  -- datové řádky bez hlavičky
    metadata         jsonb,                         -- CSVW schéma (…-metadata.json) platné při importu
    importovano      timestamptz NOT NULL DEFAULT now(),
    import_davka_id  bigint      NOT NULL REFERENCES dev.import_davka (id),
    UNIQUE (datum_snimku, soubor)
);

COMMENT ON TABLE res.snimek IS 'Načtený soubor otevřených dat RES: datum snímku, původ, otisk a počet řádků';
COMMENT ON COLUMN res.snimek.pocet_radku IS 'Počet záznamů v souboru podle CSV parseru (bez hlavičky); musí sedět s počtem řádků v cílové tabulce';

CREATE OR REPLACE TRIGGER snimek_zakaz_zmeny
    BEFORE UPDATE ON res.snimek
    FOR EACH ROW EXECUTE FUNCTION dev.zakaz_zmeny();

CREATE OR REPLACE TRIGGER snimek_zakaz_mazani
    BEFORE DELETE ON res.snimek
    FOR EACH ROW EXECUTE FUNCTION dev.zakaz_mazani();

CREATE OR REPLACE TRIGGER snimek_zakaz_truncate
    BEFORE TRUNCATE ON res.snimek
    FOR EACH STATEMENT EXECUTE FUNCTION dev.zakaz_mazani();

-- ---------------------------------------------------------------------
-- Původ číselníků: odkud a kdy se který číselník ČSÚ načetl.
-- Číselníky nejsou historizované – při novém načtení se obsah nahradí.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS res.cis_zdroj (
    ciselnik         text        PRIMARY KEY,       -- např. 'CZ_NACE_RES', '109'
    tabulka          text        NOT NULL,          -- cílová tabulka res.cis_*
    nazev            text        NOT NULL,
    url              text        NOT NULL,
    pocet_polozek    integer     NOT NULL,
    sha256           text        NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    stazeno          timestamptz NOT NULL DEFAULT now(),
    import_davka_id  bigint      NOT NULL REFERENCES dev.import_davka (id)
);

COMMENT ON TABLE res.cis_zdroj IS 'Odkud a kdy byl načten který oficiální číselník ČSÚ';
