-- =====================================================================
-- 06_adresa.sql – adresy (neměnné hodnoty) a přiřazení adres subjektům
--
-- Adresa je jen hodnota: jednou uložená se nemění (stejnou adresu sdílí
-- mnoho subjektů). Historii nese až vazba subjekt_adresa.
-- =====================================================================

-- Otisk obsahu adresy (normalizovaný). Používá ho generovaný sloupec
-- hash_adresy i loader při hledání adresy bez RÚIAN kódu.
CREATE OR REPLACE FUNCTION dev.otisk_adresy(
    p_ulice text, p_cislo_popisne text, p_cislo_evidencni text, p_cislo_orientacni text,
    p_obec text, p_cast_obce text, p_psc text, p_stat text, p_text_puvodni text
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT md5(
           lower(btrim(coalesce(p_ulice, '')))
        || '|' || lower(btrim(coalesce(p_cislo_popisne, '')))
        || '|' || lower(btrim(coalesce(p_cislo_evidencni, '')))
        || '|' || lower(btrim(coalesce(p_cislo_orientacni, '')))
        || '|' || lower(btrim(coalesce(p_obec, '')))
        || '|' || lower(btrim(coalesce(p_cast_obce, '')))
        || '|' || replace(coalesce(p_psc, ''), ' ', '')
        || '|' || upper(coalesce(p_stat, ''))
        || '|' || lower(btrim(coalesce(p_text_puvodni, '')))
    )
$$;

CREATE TABLE IF NOT EXISTS dev.adresa (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ruian_kod         bigint UNIQUE,          -- kód adresního místa RÚIAN, pokud je znám
    ulice             text,
    cislo_popisne     text,
    cislo_evidencni   text,                   -- č.ev. (rekreační objekty) – místo č.p.
    cislo_orientacni  text,
    obec              text,
    cast_obce         text,
    psc               text,
    stat              text NOT NULL DEFAULT 'CZ',   -- ISO 3166-1 alpha-2
    kod_obce          integer,                -- kód obce RÚIAN
    kod_kraje         integer,                -- kód kraje RÚIAN
    text_puvodni      text,                   -- adresa přesně tak, jak přišla ze zdroje
    vznik_zaznamu     timestamptz NOT NULL DEFAULT now(),

    -- Otisk obsahu. Jednoznačnost ale hlídá:
    --   * adresa s RÚIAN kódem  -> ruian_kod (text se může drobně lišit),
    --   * adresa bez RÚIAN kódu -> hash_adresy (index níže).
    hash_adresy       text GENERATED ALWAYS AS (
        dev.otisk_adresy(ulice, cislo_popisne, cislo_evidencni, cislo_orientacni,
                         obec, cast_obce, psc, stat, text_puvodni)
    ) STORED,

    CHECK (stat ~ '^[A-Z]{2}$'),
    CHECK (cislo_popisne IS NULL OR cislo_evidencni IS NULL)
);

-- Adresy bez RÚIAN kódu se odlišují otiskem obsahu
CREATE UNIQUE INDEX IF NOT EXISTS adresa_bez_ruian_hash_uq
    ON dev.adresa (hash_adresy) WHERE ruian_kod IS NULL;

COMMENT ON TABLE dev.adresa IS 'Unikátní adresy; neměnné, sdílené více subjekty';

CREATE OR REPLACE TRIGGER adresa_zakaz_zmeny
    BEFORE UPDATE ON dev.adresa
    FOR EACH ROW EXECUTE FUNCTION dev.zakaz_zmeny();

CREATE OR REPLACE TRIGGER adresa_zakaz_mazani
    BEFORE DELETE ON dev.adresa
    FOR EACH ROW EXECUTE FUNCTION dev.zakaz_mazani();

CREATE OR REPLACE TRIGGER adresa_zakaz_truncate
    BEFORE TRUNCATE ON dev.adresa
    FOR EACH STATEMENT EXECUTE FUNCTION dev.zakaz_mazani();

-- Přiřazení adresy subjektu v čase (sídlo, provozovna, doručovací)
CREATE TABLE IF NOT EXISTS dev.subjekt_adresa (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ico              dev.ico     NOT NULL REFERENCES dev.subjekt (ico),
    adresa_id        bigint      NOT NULL REFERENCES dev.adresa (id),
    typ_adresy_kod   text        NOT NULL REFERENCES dev.ciselnik_typ_adresy (kod),

    platnost_od      date,
    platnost_do      date,
    zaznamenano_od   timestamptz NOT NULL DEFAULT now(),
    zaznamenano_do   timestamptz,
    import_davka_id  bigint      NOT NULL REFERENCES dev.import_davka (id),
    hash_obsahu      text,

    CHECK (platnost_od IS NULL OR platnost_do IS NULL OR platnost_do >= platnost_od),
    CHECK (zaznamenano_do IS NULL OR zaznamenano_do >= zaznamenano_od),

    -- V jednom okamžiku má subjekt nejvýš jedno sídlo
    CONSTRAINT subjekt_adresa_jedno_sidlo EXCLUDE USING gist (
        ico WITH =,
        daterange(platnost_od, platnost_do, '[)') WITH &&
    ) WHERE (typ_adresy_kod = 'SIDLO' AND zaznamenano_do IS NULL),

    -- Stejná adresa stejného typu se u subjektu nesmí časově překrývat
    CONSTRAINT subjekt_adresa_bez_prekryvu EXCLUDE USING gist (
        ico WITH =,
        adresa_id WITH =,
        typ_adresy_kod WITH =,
        daterange(platnost_od, platnost_do, '[)') WITH &&
    ) WHERE (zaznamenano_do IS NULL)
);

COMMENT ON TABLE dev.subjekt_adresa IS 'Adresy subjektu v čase – bitemporální';

CREATE INDEX IF NOT EXISTS subjekt_adresa_ico_idx    ON dev.subjekt_adresa (ico);
CREATE INDEX IF NOT EXISTS subjekt_adresa_adresa_idx ON dev.subjekt_adresa (adresa_id);

CREATE OR REPLACE TRIGGER subjekt_adresa_jen_uzavreni
    BEFORE UPDATE ON dev.subjekt_adresa
    FOR EACH ROW EXECUTE FUNCTION dev.jen_uzavreni_verze();

CREATE OR REPLACE TRIGGER subjekt_adresa_zakaz_mazani
    BEFORE DELETE ON dev.subjekt_adresa
    FOR EACH ROW EXECUTE FUNCTION dev.zakaz_mazani();

CREATE OR REPLACE TRIGGER subjekt_adresa_zakaz_truncate
    BEFORE TRUNCATE ON dev.subjekt_adresa
    FOR EACH STATEMENT EXECUTE FUNCTION dev.zakaz_mazani();
