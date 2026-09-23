-- =====================================================================
-- 05_osoba.sql – fyzická osoba (identita s interním ID) a její verze
--
-- Osoby nemají veřejný jednoznačný identifikátor, proto interní ID.
-- Tutéž osobu poznáme podle párovacího klíče
-- (jméno|příjmení|datum narození – viz dev.klic_osoby).
-- Adresy osob (bydliště) záměrně nevedeme.
-- =====================================================================

CREATE TABLE IF NOT EXISTS dev.osoba (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    klic_parovani    text        NOT NULL UNIQUE,
    ico              dev.ico     REFERENCES dev.subjekt (ico),  -- jen u podnikajících osob s IČO
    vznik_zaznamu    timestamptz NOT NULL DEFAULT now(),
    import_davka_id  bigint      NOT NULL REFERENCES dev.import_davka (id)
);

COMMENT ON TABLE dev.osoba IS 'Identita fyzické osoby – interní ID + párovací klíč';
COMMENT ON COLUMN dev.osoba.ico IS 'Volitelné propojení na subjekt, pokud osoba podniká pod vlastním IČO';

CREATE INDEX IF NOT EXISTS osoba_ico_idx ON dev.osoba (ico);

-- Identitu (id, párovací klíč) nelze měnit; doplnit propojení na IČO ano
CREATE OR REPLACE TRIGGER osoba_zakaz_zmeny_identity
    BEFORE UPDATE OF id, klic_parovani ON dev.osoba
    FOR EACH ROW EXECUTE FUNCTION dev.zakaz_zmeny();

CREATE OR REPLACE TRIGGER osoba_zakaz_mazani
    BEFORE DELETE ON dev.osoba
    FOR EACH ROW EXECUTE FUNCTION dev.zakaz_mazani();

CREATE TABLE IF NOT EXISTS dev.osoba_verze (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    osoba_id            bigint      NOT NULL REFERENCES dev.osoba (id),

    jmeno               text,
    prijmeni            text        NOT NULL,
    titul_pred          text,
    titul_za            text,
    datum_narozeni      date,
    statni_prislusnost  text,

    platnost_od         date,
    platnost_do         date,
    zaznamenano_od      timestamptz NOT NULL DEFAULT now(),
    zaznamenano_do      timestamptz,
    import_davka_id     bigint      NOT NULL REFERENCES dev.import_davka (id),
    hash_obsahu         text,

    CHECK (platnost_od IS NULL OR platnost_do IS NULL OR platnost_do >= platnost_od),
    CHECK (zaznamenano_do IS NULL OR zaznamenano_do >= zaznamenano_od),

    CONSTRAINT osoba_verze_bez_prekryvu EXCLUDE USING gist (
        osoba_id WITH =,
        daterange(platnost_od, platnost_do, '[)') WITH &&
    ) WHERE (zaznamenano_do IS NULL)
);

COMMENT ON TABLE dev.osoba_verze IS 'Historie údajů osoby (jméno, tituly…) – bitemporální';

CREATE INDEX IF NOT EXISTS osoba_verze_osoba_idx ON dev.osoba_verze (osoba_id);

CREATE OR REPLACE TRIGGER osoba_verze_jen_uzavreni
    BEFORE UPDATE ON dev.osoba_verze
    FOR EACH ROW EXECUTE FUNCTION dev.jen_uzavreni_verze();

CREATE OR REPLACE TRIGGER osoba_verze_zakaz_mazani
    BEFORE DELETE ON dev.osoba_verze
    FOR EACH ROW EXECUTE FUNCTION dev.zakaz_mazani();
