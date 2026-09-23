-- =====================================================================
-- 04_subjekt.sql – subjekt (identita, klíč IČO) a jeho verze
--
-- Historizace (platí stejně pro všechny *_verze tabulky):
--   platnost_od / platnost_do       – kdy údaj platil ve skutečnosti
--                                     (podle registru), interval [od, do)
--   zaznamenano_od / zaznamenano_do – kdy jsme údaj evidovali v databázi
--   Změna údaje = uzavření staré verze (zaznamenano_do = now())
--                 + vložení nové verze. Nic se nepřepisuje ani nemaže.
--   Aktuálně evidované verze (zaznamenano_do IS NULL) téhož subjektu
--   se nesmí časově překrývat.
-- =====================================================================

-- Identita: jeden řádek na IČO, nikdy se nemění ani nemaže
CREATE TABLE IF NOT EXISTS dev.subjekt (
    ico              dev.ico     PRIMARY KEY,
    vznik_zaznamu    timestamptz NOT NULL DEFAULT now(),
    import_davka_id  bigint      NOT NULL REFERENCES dev.import_davka (id)
);

COMMENT ON TABLE dev.subjekt IS 'Identita subjektu (firmy) – klíčem je IČO';

CREATE OR REPLACE TRIGGER subjekt_zakaz_zmeny
    BEFORE UPDATE ON dev.subjekt
    FOR EACH ROW EXECUTE FUNCTION dev.zakaz_zmeny();

CREATE OR REPLACE TRIGGER subjekt_zakaz_mazani
    BEFORE DELETE ON dev.subjekt
    FOR EACH ROW EXECUTE FUNCTION dev.zakaz_mazani();

CREATE OR REPLACE TRIGGER subjekt_zakaz_truncate
    BEFORE TRUNCATE ON dev.subjekt
    FOR EACH STATEMENT EXECUTE FUNCTION dev.zakaz_mazani();

-- Verze údajů subjektu
CREATE TABLE IF NOT EXISTS dev.subjekt_verze (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ico               dev.ico     NOT NULL REFERENCES dev.subjekt (ico),

    nazev             text        NOT NULL,
    pravni_forma_kod  text        REFERENCES dev.ciselnik_pravni_forma (kod),
    stav_kod          text        NOT NULL REFERENCES dev.ciselnik_stav_subjektu (kod),
    datum_vzniku      date,
    datum_zaniku      date,

    platnost_od       date,
    platnost_do       date,
    zaznamenano_od    timestamptz NOT NULL DEFAULT now(),
    zaznamenano_do    timestamptz,
    import_davka_id   bigint      NOT NULL REFERENCES dev.import_davka (id),
    hash_obsahu       text,

    CHECK (platnost_od IS NULL OR platnost_do IS NULL OR platnost_do >= platnost_od),
    CHECK (zaznamenano_do IS NULL OR zaznamenano_do >= zaznamenano_od),
    CHECK (datum_zaniku IS NULL OR datum_vzniku IS NULL OR datum_zaniku >= datum_vzniku),

    CONSTRAINT subjekt_verze_bez_prekryvu EXCLUDE USING gist (
        ico WITH =,
        daterange(platnost_od, platnost_do, '[)') WITH &&
    ) WHERE (zaznamenano_do IS NULL)
);

COMMENT ON TABLE dev.subjekt_verze IS 'Historie údajů subjektu (bitemporální: platnost + zaznamenáno)';

CREATE INDEX IF NOT EXISTS subjekt_verze_ico_idx ON dev.subjekt_verze (ico);

CREATE OR REPLACE TRIGGER subjekt_verze_jen_uzavreni
    BEFORE UPDATE ON dev.subjekt_verze
    FOR EACH ROW EXECUTE FUNCTION dev.jen_uzavreni_verze();

CREATE OR REPLACE TRIGGER subjekt_verze_zakaz_mazani
    BEFORE DELETE ON dev.subjekt_verze
    FOR EACH ROW EXECUTE FUNCTION dev.zakaz_mazani();

CREATE OR REPLACE TRIGGER subjekt_verze_zakaz_truncate
    BEFORE TRUNCATE ON dev.subjekt_verze
    FOR EACH STATEMENT EXECUTE FUNCTION dev.zakaz_mazani();
