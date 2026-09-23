-- =====================================================================
-- 07_vazba.sql – vazby osoba/firma → firma podle obchodního rejstříku
--
-- ROZSAH: pouze přímé vazby zapsané v obchodním rejstříku (statutární
-- orgány, dozorčí rada, prokura, likvidátor, společníci / jediný
-- akcionář). Podíl je jen přímý podíl tak, jak je zapsán v OR.
-- Koncoví (skuteční) majitelé ani dopočítané nepřímé vlastnictví nejsou
-- součástí – evidence skutečných majitelů není od 17. 12. 2025 veřejná.
--
-- Členem může být fyzická osoba (clen_osoba_id) NEBO jiný subjekt
-- (clen_ico) – vždy právě jedno z nich.
-- Překryv vazeb se nehlídá: jeden společník může legálně držet více
-- obchodních podílů současně.
-- =====================================================================

CREATE TABLE IF NOT EXISTS dev.vazba (
    id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ico                 dev.ico       NOT NULL REFERENCES dev.subjekt (ico),

    clen_osoba_id       bigint        REFERENCES dev.osoba (id),
    clen_ico            dev.ico       REFERENCES dev.subjekt (ico),

    role_kod            text          NOT NULL REFERENCES dev.ciselnik_role (kod),
    organ_puvodni       text,         -- název orgánu / funkce přesně podle zdroje

    -- Přímý podíl dle OR (jen u společníků)
    vklad               numeric(18, 2),
    vklad_mena          text,
    podil_text          text,         -- podíl tak, jak je zapsán (např. '1/3')
    podil_procento      numeric(7, 4),
    splaceno_procento   numeric(7, 4),

    platnost_od         date,
    platnost_do         date,
    zaznamenano_od      timestamptz   NOT NULL DEFAULT now(),
    zaznamenano_do      timestamptz,
    import_davka_id     bigint        NOT NULL REFERENCES dev.import_davka (id),
    hash_obsahu         text,

    CHECK (num_nonnulls(clen_osoba_id, clen_ico) = 1),
    CHECK (clen_ico IS NULL OR clen_ico <> ico),
    CHECK (vklad_mena IS NULL OR vklad_mena ~ '^[A-Z]{3}$'),
    CHECK (podil_procento    IS NULL OR podil_procento    BETWEEN 0 AND 100),
    CHECK (splaceno_procento IS NULL OR splaceno_procento BETWEEN 0 AND 100),
    CHECK (platnost_od IS NULL OR platnost_do IS NULL OR platnost_do >= platnost_od),
    CHECK (zaznamenano_do IS NULL OR zaznamenano_do >= zaznamenano_od)
);

COMMENT ON TABLE dev.vazba IS 'Přímé vazby jen na úrovni obchodního rejstříku – bitemporální';

CREATE INDEX IF NOT EXISTS vazba_ico_idx        ON dev.vazba (ico);
CREATE INDEX IF NOT EXISTS vazba_clen_osoba_idx ON dev.vazba (clen_osoba_id);
CREATE INDEX IF NOT EXISTS vazba_clen_ico_idx   ON dev.vazba (clen_ico);

CREATE OR REPLACE TRIGGER vazba_jen_uzavreni
    BEFORE UPDATE ON dev.vazba
    FOR EACH ROW EXECUTE FUNCTION dev.jen_uzavreni_verze();

CREATE OR REPLACE TRIGGER vazba_zakaz_mazani
    BEFORE DELETE ON dev.vazba
    FOR EACH ROW EXECUTE FUNCTION dev.zakaz_mazani();
