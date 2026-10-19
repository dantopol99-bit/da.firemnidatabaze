-- =====================================================================
-- 02_firma_nace.sql – kódy CZ-NACE firem s platností v čase
--
-- Jeden řádek = jeden kód jedné verze klasifikace pro jedno IČO a interval
-- platnosti [platnost_od, platnost_do). Verze se ukládá výslovně, nikdy
-- se neodvozuje z kódu.
--
-- zdroj = 'RES'      kód přidělený v Registru ekonomických subjektů ČSÚ
--                    (otevřená data RES nebo ARES, endpoint ekonomicke-subjekty-res);
--                    oficiální, ne neomylný. jistota = 1.
-- zdroj = 'odvozeno' kód CZ-NACE 2025 odvozený ze CZ-NACE 2008 (firmy bez kódu 2025,
--                    historické stavy). Jeden řádek na každou úroveň (sekce … podtřída),
--                    každá úroveň má vlastní jistotu. kod NULL + priznak 'nejednoznacne'
--                    = nejde určit, kandidáti z převodníku jsou v poli kandidati.
--
-- Platnost u kódů z RES: platnost_od = datum poslední aktualizace záznamu
-- v RES (DDATPAKT / datumAktualizace) – kód platí nejpozději od tohoto dne;
-- platnost_do = datum zániku subjektu, nebo den aktualizace, kterou kód
-- nahradil jiný (z dalšího snímku). NULL = platí dosud.
--
-- Kódy z RES se nemažou a nepřepisují (trigger); smí se jen uzavřít
-- (platnost_do z NULL). Odvozené řádky jsou výpočet a při novém výpočtu
-- se nahrazují.
-- =====================================================================

CREATE TABLE IF NOT EXISTS obor.firma_nace (
    id               bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ico              text        NOT NULL CHECK (ico ~ '^[0-9]{8}$'),
    verze            smallint    NOT NULL CHECK (verze IN (2008, 2025)),
    kod              text,
    uroven           smallint    NOT NULL CHECK (uroven BETWEEN 1 AND 5),
    typ              text        NOT NULL CHECK (typ IN ('hlavni', 'vedlejsi')),
    zdroj            text        NOT NULL CHECK (zdroj IN ('RES', 'odvozeno')),
    zdroj_detail     text        NOT NULL,          -- např. 'RES otevřená data, snímek 2026-09-15'
    jistota          numeric(5, 4) CHECK (jistota BETWEEN 0 AND 1),
    priznak          text        CHECK (priznak IN ('nejednoznacne')),
    kandidati        text[],                        -- jen u 'nejednoznacne': kandidáti z převodníku
    odvozeno_z       text,                          -- u 'odvozeno': kód CZ-NACE 2008, ze kterého se odvozovalo
    platnost_od      date,
    platnost_do      date,
    nacteno          timestamptz NOT NULL DEFAULT now(),
    import_davka_id  bigint      REFERENCES dev.import_davka (id),

    CHECK (platnost_do IS NULL OR platnost_od IS NULL OR platnost_do >= platnost_od),
    CHECK (zdroj <> 'RES' OR (kod IS NOT NULL AND jistota = 1 AND priznak IS NULL AND odvozeno_z IS NULL)),
    CHECK (zdroj <> 'odvozeno' OR (verze = 2025 AND odvozeno_z IS NOT NULL)),
    CHECK ((kod IS NULL) = (priznak IS NOT DISTINCT FROM 'nejednoznacne')),
    CHECK (kod IS NOT NULL OR jistota IS NULL)
);

CREATE UNIQUE INDEX IF NOT EXISTS firma_nace_klic
    ON obor.firma_nace (ico, verze, typ, zdroj, uroven, kod, platnost_od) NULLS NOT DISTINCT;
CREATE INDEX IF NOT EXISTS firma_nace_hlavni_idx ON obor.firma_nace (ico, verze, platnost_od) WHERE typ = 'hlavni';
CREATE INDEX IF NOT EXISTS firma_nace_kod_idx ON obor.firma_nace (verze, kod);

COMMENT ON TABLE obor.firma_nace IS 'Kódy CZ-NACE firem (obě verze, hlavní i vedlejší) s platností v čase; zdroj RES nebo odvozeno';
COMMENT ON COLUMN obor.firma_nace.jistota IS 'RES = 1; odvozeno: 1 u vazby 1:1 v převodníku, jinak podíl nejčastějšího cíle v empirické matici';
COMMENT ON COLUMN obor.firma_nace.platnost_od IS 'RES: datum poslední aktualizace záznamu v RES (kód platí nejpozději od něj); u verze 2025 nejdřív 1. 1. 2025';

-- ---------------------------------------------------------------------
-- Rozhodnutí 6 (19. 10. 2026): kód CZ-NACE 2025 z RES platí nejdřív od 1. 1. 2025,
-- tj. platnost_od = pozdější z data aktualizace záznamu v RES a 1. 1. 2025.
-- Interval zůstává [od, do): u subjektu zaniklého před 1. 1. 2025 je prázdný
-- (od = do = 1. 1. 2025). Odvozené kódy se netýká – popisují historické stavy.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION obor.zacatek_2025(d date) RETURNS date
LANGUAGE sql IMMUTABLE AS $$ SELECT greatest(d, DATE '2025-01-01') $$;

CREATE OR REPLACE FUNCTION obor.konec_2025(d date) RETURNS date
LANGUAGE sql IMMUTABLE AS $$ SELECT CASE WHEN d < DATE '2025-01-01' THEN DATE '2025-01-01' ELSE d END $$;

-- Rozhodnutí 7: proč byl kód uzavřen ('zánik subjektu', 'zdroj kód už neuvádí',
-- 'konec dvojího kódování').
ALTER TABLE obor.firma_nace ADD COLUMN IF NOT EXISTS duvod_uzavreni text;
COMMENT ON COLUMN obor.firma_nace.duvod_uzavreni IS
    'Důvod uzavření kódu: zánik subjektu / zdroj kód už neuvádí / konec dvojího kódování (31. 12. 2028)';

-- Stráž: kódy z RES se nemažou a nemění. Povolené jsou jen tyto změny:
--   (a) uzavření otevřeného kódu: platnost_do z NULL, s důvodem;
--   (b) doplnění důvodu uzavření, který chybí;
--   (c) rozhodnutí 6: posun začátku kódu 2025 na 1. 1. 2025 (a konce, byl-li dřív).
CREATE OR REPLACE FUNCTION obor.firma_nace_straz() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.zdroj = 'RES' THEN
            RAISE EXCEPTION 'obor.firma_nace: kódy ze zdroje RES se nemažou (IČO %, verze %, kód %)',
                OLD.ico, OLD.verze, OLD.kod;
        END IF;
        RETURN OLD;
    END IF;
    IF OLD.zdroj <> 'RES' THEN
        RETURN NEW;
    END IF;
    IF (to_jsonb(NEW) - 'platnost_do' - 'duvod_uzavreni') = (to_jsonb(OLD) - 'platnost_do' - 'duvod_uzavreni')
       AND (
           (OLD.platnost_do IS NULL AND NEW.platnost_do IS NOT NULL)                                     -- (a)
           OR (NEW.platnost_do IS NOT DISTINCT FROM OLD.platnost_do AND OLD.duvod_uzavreni IS NULL)     -- (b)
       ) THEN
        RETURN NEW;
    END IF;
    IF OLD.verze = 2025 AND OLD.platnost_od < DATE '2025-01-01'                                          -- (c)
       AND NEW.platnost_od = DATE '2025-01-01'
       AND NEW.platnost_do IS NOT DISTINCT FROM obor.konec_2025(OLD.platnost_do)
       AND (to_jsonb(NEW) - 'platnost_od' - 'platnost_do') = (to_jsonb(OLD) - 'platnost_od' - 'platnost_do') THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'obor.firma_nace: kód ze zdroje RES lze jen uzavřít (IČO %, verze %, kód %)',
        OLD.ico, OLD.verze, OLD.kod;
END;
$$;

CREATE OR REPLACE TRIGGER firma_nace_straz_zmena
    BEFORE UPDATE OR DELETE ON obor.firma_nace
    FOR EACH ROW EXECUTE FUNCTION obor.firma_nace_straz();

CREATE OR REPLACE TRIGGER firma_nace_zakaz_truncate
    BEFORE TRUNCATE ON obor.firma_nace
    FOR EACH STATEMENT EXECUTE FUNCTION dev.zakaz_mazani();

-- Rozhodnutí 6 pro už uložená data (idempotentní: podruhé nic nenajde).
UPDATE obor.firma_nace
SET platnost_od = DATE '2025-01-01', platnost_do = obor.konec_2025(platnost_do)
WHERE zdroj = 'RES' AND verze = 2025 AND platnost_od < DATE '2025-01-01';

-- Důvod u kódů uzavřených dřív, než sloupec existoval (zaniklé subjekty ze snímku).
UPDATE obor.firma_nace
SET duvod_uzavreni = 'zánik subjektu'
WHERE zdroj = 'RES' AND platnost_do IS NOT NULL AND duvod_uzavreni IS NULL;
