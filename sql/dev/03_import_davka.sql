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
