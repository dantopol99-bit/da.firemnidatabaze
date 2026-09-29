-- =====================================================================
-- 02_ciselniky.sql – oficiální číselníky ČSÚ pro interpretaci RES
--
-- Obsah se NEvkládá tímto skriptem: tabulky plní importér
-- (python -m firemni_databaze.res_import ciselniky) přímo z exportů ČSÚ,
-- původ je v res.cis_zdroj. Na číselníky záměrně NEvedou cizí klíče
-- z res.subjekt – snímek se ukládá tak, jak ho ČSÚ vydal, i kdyby
-- obsahoval kód, který v číselníku (zatím) není. Takové kódy hlásí
-- kontrola kvality (res.kvalita).
-- =====================================================================

-- ---------------------------------------------------------------------
-- CZ-NACE v rozšířené variantě pro RES (dle dokumentace otevřených dat):
--   80004 = CZ-NACE (NACE Rev. 2)  – sloupec NACE,    zdroj CZ_NACE_RES
--   80143 = CZ-NACE 2025 (Rev. 2.1) – sloupec NACE2025, zdroj CZ_NACE_RES2025
-- Úrovně: 1 sekce, 2 oddíl, 3 skupina, 4 třída, 5 podtřída (národní).
-- Sloupce sekce … trida jsou předci položky odvození z hierarchie
-- číselníku (nadrazeny_kod), na vlastní úrovni obsahují položku samu.
-- RES rozšiřuje oficiální klasifikaci o pseudo-sekce, které nejsou
-- ekonomickou činností:  X / 04 = nezjištěno,
--                        Y / 00 = výroba, obchod a služby neuvedené
--                                 v přílohách 1 až 3 živnostenského zákona.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS res.cis_nace (
    klasifikace      integer  NOT NULL CHECK (klasifikace IN (80004, 80143)),
    kod              text     NOT NULL,
    uroven           smallint NOT NULL CHECK (uroven BETWEEN 1 AND 5),
    nadrazeny_kod    text,
    nazev            text     NOT NULL,
    zkraceny_nazev   text,
    sekce            text     NOT NULL,
    oddil            text,
    skupina          text,
    trida            text,
    je_pseudokod     boolean  NOT NULL,             -- sekce X nebo Y (není ekonomická činnost)
    platnost_od      date,
    platnost_do      date,
    PRIMARY KEY (klasifikace, kod)
);

COMMENT ON TABLE res.cis_nace IS 'CZ-NACE pro RES (80004 = Rev. 2, 80143 = CZ-NACE 2025) se sekcí/oddílem/skupinou/třídou';

-- ---------------------------------------------------------------------
-- Kraje: číselník ČSÚ 100 (Kraj), obsahuje kód CZ-NUTS 3 i kód RÚIAN.
-- Kód RÚIAN umožňuje porovnat kraj s jádrem z ARES (dev.adresa.kod_kraje).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS res.cis_kraj (
    kod              text     PRIMARY KEY,          -- CZ-NUTS 3, např. 'CZ051'
    nazev            text     NOT NULL,
    zkratka          text,                          -- např. 'LBK'
    kod_csu          integer  NOT NULL UNIQUE,      -- položka číselníku 100, např. 3077
    kod_ruian        integer  UNIQUE,               -- kód VÚSC v RÚIAN, např. 78
    platnost_od      date,
    platnost_do      date
);

COMMENT ON TABLE res.cis_kraj IS 'Kraje (číselník ČSÚ 100) – kód CZ-NUTS 3, kód ČSÚ a kód RÚIAN';

-- ---------------------------------------------------------------------
-- Okresy: číselník ČSÚ 109 (OKRES_LAU) – na něj odkazuje sloupec
-- OKRESLAU v res_data.csv. Kraj podle oficiální vazby 109 → 108
-- (hierarchie číselníků ČSÚ), tj. ne odvozením z prefixu kódu.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS res.cis_okres (
    kod              text     PRIMARY KEY,          -- CZ-NUTS / LAU 1, např. 'CZ0513'
    nazev            text     NOT NULL,
    kraj_kod         text     NOT NULL REFERENCES res.cis_kraj (kod),
    platnost_od      date,
    platnost_do      date
);

COMMENT ON TABLE res.cis_okres IS 'Okresy (číselník ČSÚ 109) s krajem podle vazby číselníků 109 → 108';

-- ---------------------------------------------------------------------
-- Právní formy: 56 = FORMA (statistická), 149 = ROSFORMA (registr osob).
-- Pozn.: dev.ciselnik_pravni_forma (jádro) je číselník z ARES a zůstává
-- beze změny; tento je oficiální číselník ČSÚ ve verzi k datu snímku.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS res.cis_pravni_forma (
    ciselnik         integer  NOT NULL CHECK (ciselnik IN (56, 149)),
    kod              text     NOT NULL,
    nazev            text     NOT NULL,
    zkraceny_nazev   text,
    platnost_od      date,
    platnost_do      date,
    PRIMARY KEY (ciselnik, kod)
);

COMMENT ON TABLE res.cis_pravni_forma IS 'Právní formy ČSÚ: 56 = statistická (FORMA), 149 = registr osob (ROSFORMA)';

-- Kategorie podle počtu pracovníků (číselník ČSÚ 579, KATPO)
CREATE TABLE IF NOT EXISTS res.cis_katpo (
    kod              text     PRIMARY KEY,
    nazev            text     NOT NULL,
    platnost_od      date,
    platnost_do      date
);

COMMENT ON TABLE res.cis_katpo IS 'Kategorie počtu pracovníků (číselník ČSÚ 579); 000 = Neuvedeno';

-- Způsob zániku (číselník ČSÚ 572, ZPZAN)
CREATE TABLE IF NOT EXISTS res.cis_zpusob_zaniku (
    kod              text     PRIMARY KEY,
    nazev            text     NOT NULL,
    platnost_od      date,
    platnost_do      date
);

COMMENT ON TABLE res.cis_zpusob_zaniku IS 'Způsob zániku subjektu (číselník ČSÚ 572)';

-- Zdroj údaje (číselník ČSÚ 564, ZDRUD v res_pf_nace.csv)
CREATE TABLE IF NOT EXISTS res.cis_zdroj_udaje (
    kod              text     PRIMARY KEY,
    nazev            text     NOT NULL,
    platnost_od      date,
    platnost_do      date
);

COMMENT ON TABLE res.cis_zdroj_udaje IS 'Zdroj údaje o činnosti (číselník ČSÚ 564)';
