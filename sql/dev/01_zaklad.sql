-- =====================================================================
-- 01_zaklad.sql – společný základ identitního jádra (schéma dev)
--
-- * rozšíření PostgreSQL (btree_gist pro hlídání překryvu období,
--   unaccent pro normalizaci jmen)
-- * datový typ dev.ico (8 číslic, text kvůli úvodním nulám)
-- * pomocné funkce (kontrolní číslice IČO, párovací klíč osoby)
-- * triggerové funkce, které vynucují historizaci:
--   nic se nemaže a u verzí jde jen „uzavřít“ záznam (zaznamenano_do)
--
-- Skript je idempotentní – lze ho spustit opakovaně.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- ---------------------------------------------------------------------
-- Datový typ pro IČO: přesně 8 číslic.
-- Kontrolní číslici NEvynucujeme omezením (u historických dat hrozí
-- výjimky, které by zablokovaly import) – ověřuje ji funkce níže.
-- ---------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'dev' AND t.typname = 'ico'
    ) THEN
        CREATE DOMAIN dev.ico AS text CHECK (VALUE ~ '^[0-9]{8}$');
    END IF;
END
$$;

COMMENT ON DOMAIN dev.ico IS 'IČO – 8 číslic včetně úvodních nul';

-- ---------------------------------------------------------------------
-- Kontrola kontrolní číslice IČO (modulo 11).
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION dev.je_platne_ico(p_ico text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
        WHEN p_ico IS NULL OR p_ico !~ '^[0-9]{8}$' THEN false
        ELSE (
            WITH s AS (
                SELECT sum(substr(p_ico, i, 1)::int * (9 - i)) % 11 AS zbytek
                FROM generate_series(1, 7) AS i
            )
            SELECT substr(p_ico, 8, 1)::int =
                   CASE zbytek WHEN 0 THEN 1 WHEN 1 THEN 0 ELSE 11 - zbytek END
            FROM s
        )
    END
$$;

COMMENT ON FUNCTION dev.je_platne_ico(text) IS 'true, pokud IČO má 8 číslic a sedí kontrolní číslice';

-- ---------------------------------------------------------------------
-- Párovací klíč osoby: normalizované jméno | příjmení | datum narození.
-- Normalizace: bez diakritiky, malá písmena, sjednocené mezery.
-- Chybí-li datum narození, použije se '?' (takové osoby se mohou
-- chybně sloučit – loader je má označit k ruční kontrole).
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION dev.normalizuj_text(p text)
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT lower(regexp_replace(btrim(public.unaccent(coalesce(p, ''))), '\s+', ' ', 'g'))
$$;

CREATE OR REPLACE FUNCTION dev.klic_osoby(p_jmeno text, p_prijmeni text, p_datum_narozeni date)
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT dev.normalizuj_text(p_jmeno)
        || '|' || dev.normalizuj_text(p_prijmeni)
        || '|' || coalesce(to_char(p_datum_narozeni, 'YYYY-MM-DD'), '?')
$$;

COMMENT ON FUNCTION dev.klic_osoby(text, text, date) IS 'Párovací klíč osoby: jméno|příjmení|datum narození (normalizované)';

-- ---------------------------------------------------------------------
-- Stráž 1: zákaz mazání (identity i verze se nikdy nemažou).
-- Používá se pro DELETE (po řádcích) i TRUNCATE (po příkazech) –
-- TRUNCATE řádkové triggery nespouští, proto potřebuje vlastní.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION dev.zakaz_mazani()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'Tabulka %.% je historizovaná – mazání není povoleno.',
        TG_TABLE_SCHEMA, TG_TABLE_NAME;
END
$$;

-- ---------------------------------------------------------------------
-- Stráž 2: zákaz jakékoli změny (pro neměnné tabulky, např. adresa).
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION dev.zakaz_zmeny()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'Záznamy v %.% jsou neměnné – vlož nový záznam místo úpravy.',
        TG_TABLE_SCHEMA, TG_TABLE_NAME;
END
$$;

-- ---------------------------------------------------------------------
-- Stráž 3: u verzovaných tabulek je jediná povolená úprava
-- „uzavření“ verze – doplnění zaznamenano_do (z NULL na hodnotu).
-- Všechny ostatní sloupce musí zůstat beze změny.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION dev.jen_uzavreni_verze()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.zaznamenano_do IS NOT NULL THEN
        RAISE EXCEPTION 'Verze v %.% je už uzavřená a nelze ji měnit.',
            TG_TABLE_SCHEMA, TG_TABLE_NAME;
    END IF;

    IF NEW.zaznamenano_do IS NULL THEN
        RAISE EXCEPTION 'U %.% lze pouze doplnit zaznamenano_do (uzavřít verzi).',
            TG_TABLE_SCHEMA, TG_TABLE_NAME;
    END IF;

    IF (to_jsonb(NEW) - 'zaznamenano_do') IS DISTINCT FROM (to_jsonb(OLD) - 'zaznamenano_do') THEN
        RAISE EXCEPTION 'U %.% se nesmí měnit obsah verze – vlož novou verzi.',
            TG_TABLE_SCHEMA, TG_TABLE_NAME;
    END IF;

    RETURN NEW;
END
$$;
