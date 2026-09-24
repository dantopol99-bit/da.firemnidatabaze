-- =====================================================================
-- 03_import_davka.sql – evidence načtení dat (původ / lineage)
--
-- Každé načtení ze zdroje (ARES, veřejný rejstřík, …) vytvoří jeden
-- řádek. Každá verze v jádru na něj odkazuje, takže je vždy dohledatelné,
-- odkud a kdy údaj přišel.
-- Tabulka je provozní: průběh dávky (stav, konec) se smí aktualizovat.
-- =====================================================================

CREATE TABLE IF NOT EXISTS dev.import_davka (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    zdroj            text        NOT NULL,          -- např. 'ARES', 'OR'
    zacatek          timestamptz NOT NULL DEFAULT now(),
    konec            timestamptz,
    soubor_nebo_url  text,
    pocet_zaznamu    integer,
    stav             text        NOT NULL DEFAULT 'BEZI'
                     CHECK (stav IN ('BEZI', 'OK', 'CHYBA')),
    poznamka         text,
    CHECK (konec IS NULL OR konec >= zacatek)
);

COMMENT ON TABLE dev.import_davka IS 'Jedno načtení dat ze zdroje; na dávku odkazují všechny verze';

CREATE OR REPLACE TRIGGER import_davka_zakaz_mazani
    BEFORE DELETE ON dev.import_davka
    FOR EACH ROW EXECUTE FUNCTION dev.zakaz_mazani();

CREATE OR REPLACE TRIGGER import_davka_zakaz_truncate
    BEFORE TRUNCATE ON dev.import_davka
    FOR EACH STATEMENT EXECUTE FUNCTION dev.zakaz_mazani();

-- ---------------------------------------------------------------------
-- Surové odpovědi zdroje – pojistka pro případ chybného odvození.
-- Ukládá se VŽDY: při každé dávce, i když se nic nezměnilo a i když
-- se odpověď nepodařilo převést do jádra. Neměnné, nemaže se.
-- ico záměrně bez FK na subjekt: surová data se uloží dřív než jádro
-- (a zůstanou, i když převod selže).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dev.import_surova_data (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    import_davka_id  bigint      NOT NULL REFERENCES dev.import_davka (id),
    ico              dev.ico     NOT NULL,
    endpoint         text        NOT NULL,          -- např. 'ekonomicke-subjekty-vr'
    http_status      integer,
    stazeno          timestamptz NOT NULL DEFAULT now(),
    raw              jsonb       NOT NULL,
    UNIQUE (import_davka_id, ico, endpoint)
);

COMMENT ON TABLE dev.import_surova_data IS 'Celá surová odpověď zdroje (JSON) pro každý subjekt a dávku';

CREATE INDEX IF NOT EXISTS import_surova_data_ico_idx ON dev.import_surova_data (ico);

CREATE OR REPLACE TRIGGER import_surova_data_zakaz_zmeny
    BEFORE UPDATE ON dev.import_surova_data
    FOR EACH ROW EXECUTE FUNCTION dev.zakaz_zmeny();

CREATE OR REPLACE TRIGGER import_surova_data_zakaz_mazani
    BEFORE DELETE ON dev.import_surova_data
    FOR EACH ROW EXECUTE FUNCTION dev.zakaz_mazani();

CREATE OR REPLACE TRIGGER import_surova_data_zakaz_truncate
    BEFORE TRUNCATE ON dev.import_surova_data
    FOR EACH STATEMENT EXECUTE FUNCTION dev.zakaz_mazani();
