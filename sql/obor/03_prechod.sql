-- =====================================================================
-- 03_prechod.sql – empirická matice přechodů 2008 → 2025 a pravidla odvození
--
-- Matice: firmy, které mají v RES oba kódy hlavní činnosti (stav ke dni
-- zaklad_k). Firma s kódem 2008 k přispívá za k i za všechny jeho předky
-- (třída, skupina, oddíl, sekce) a za každou cílovou úroveň 2025 zvlášť,
-- která není podrobnější než zdrojový kód a než kód 2025 firmy.
-- Díky tomu má každý starý kód vlastní rozdělení i na úrovni oddílu
-- a sekce, kde bývá jistota vyšší než u podtřídy.
--
-- Pravidlo odvození pro starý kód k a cílovou úroveň L (obor.nace_odvozeni):
--   1. 'prevodnik_1:1'        k (nebo jeho předek na úrovni L) má v převodníku
--                             vazbu 1:1                     → jistota 1
--   2. 'prevodnik_jediny_cil' převodník dává pro k na úrovni L jediného
--                             kandidáta (vazba N:1 nebo kandidáti se sejdou
--                             v jednom předkovi)            → jistota 1
--   3. 'empiricky'            v matici je pro k aspoň 20 firem
--                                                           → nejčastější cíl, jistota = podíl
--   4. 'nejednoznacne'        jinak: kod NULL, kandidáti z převodníku
-- Plní python -m firemni_databaze.nace_firmy matice.
-- =====================================================================

CREATE TABLE IF NOT EXISTS obor.nace_prechod_empiricky (
    zaklad_k        date     NOT NULL,          -- stav RES, ze kterého se matice počítala
    kod_2008        text     NOT NULL,
    uroven_2008     smallint NOT NULL CHECK (uroven_2008 BETWEEN 1 AND 5),
    uroven          smallint NOT NULL CHECK (uroven BETWEEN 1 AND 5),   -- cílová úroveň 2025
    kod_2025        text     NOT NULL,
    pocet           integer  NOT NULL CHECK (pocet > 0),
    zaklad          integer  NOT NULL CHECK (zaklad >= pocet),          -- firem s kod_2008 (pro tuto cílovou úroveň)
    podil           numeric(5, 4) NOT NULL,
    PRIMARY KEY (zaklad_k, kod_2008, uroven, kod_2025),
    CHECK (uroven <= uroven_2008)
);

COMMENT ON TABLE obor.nace_prechod_empiricky IS
    'Empirická matice přechodů hlavní činnosti CZ-NACE 2008 → 2025 z dvojího kódování v RES (počet, podíl) po cílových úrovních';

CREATE TABLE IF NOT EXISTS obor.nace_odvozeni (
    zaklad_k        date     NOT NULL,
    kod_2008        text     NOT NULL,
    uroven          smallint NOT NULL CHECK (uroven BETWEEN 1 AND 5),   -- cílová úroveň 2025
    kod_2025        text,
    jistota         numeric(5, 4),
    metoda          text     NOT NULL CHECK (metoda IN ('prevodnik_1:1', 'prevodnik_jediny_cil', 'empiricky', 'nejednoznacne')),
    zaklad          integer  NOT NULL,          -- firem v matici (0 = žádná)
    kandidati       text[],
    PRIMARY KEY (zaklad_k, kod_2008, uroven),
    CHECK ((kod_2025 IS NULL) = (metoda = 'nejednoznacne')),
    CHECK ((kod_2025 IS NULL) = (jistota IS NULL))
);

COMMENT ON TABLE obor.nace_odvozeni IS
    'Pravidlo odvození kódu CZ-NACE 2025 pro každý kód CZ-NACE 2008 a cílovou úroveň';

-- ---------------------------------------------------------------------
-- Rozhodnutí 2 (19. 10. 2026): rozpor převodníku s empirií. Dává-li převodník
-- jediný cíl, ale empirická matice má pro kód 2008 základ aspoň 20 subjektů
-- a jiný cíl s podílem aspoň 0,9, rozhoduje empirie (metoda 'empiricky_rozpor').
-- Každý takový případ se zapíše sem. Známý případ: 96.09 → 96.91 místo 96.99.
-- ---------------------------------------------------------------------
ALTER TABLE obor.nace_odvozeni DROP CONSTRAINT IF EXISTS nace_odvozeni_metoda_check;
ALTER TABLE obor.nace_odvozeni ADD CONSTRAINT nace_odvozeni_metoda_check CHECK (metoda IN (
    'prevodnik_1:1', 'prevodnik_jediny_cil', 'empiricky', 'empiricky_rozpor', 'nejednoznacne'));

CREATE TABLE IF NOT EXISTS obor.nace_rozpory_prevodnik (
    zaklad_k        date     NOT NULL,          -- matice, ze které rozpor plyne
    kod_2008        text     NOT NULL,
    uroven          smallint NOT NULL CHECK (uroven BETWEEN 1 AND 5),   -- cílová úroveň 2025
    cil_prevodnik   text     NOT NULL,          -- jediný cíl podle převodníku
    cil_empirie     text     NOT NULL,          -- nejčastější cíl v matici (použije se)
    podil           numeric(5, 4) NOT NULL CHECK (podil >= 0.9),
    zaklad          integer  NOT NULL CHECK (zaklad >= 20),
    PRIMARY KEY (zaklad_k, kod_2008, uroven),
    CHECK (cil_prevodnik <> cil_empirie)
);

COMMENT ON TABLE obor.nace_rozpory_prevodnik IS
    'Kódy 2008, u kterých empirie (základ ≥ 20, podíl ≥ 0,9) odporuje jedinému cíli převodníku a rozhoduje empirie';
