-- =====================================================================
-- 01_ciselnik.sql – schéma obor: číselníky CZ-NACE 2008 a 2025, převodník
--
-- Schéma obor sjednocuje klasifikaci odvětví pro všechny produkty
-- (Oborově-regionální report, parlamentní a aktérská analytika).
-- Primární verze je CZ-NACE 2025, CZ-NACE 2008 zůstává jako historický
-- atribut. Verze se u každého záznamu ukládá výslovně: některé kódy jsou
-- v CZ-NACE 2025 použité pro jiný obsah než v CZ-NACE 2008.
--
-- Obsah plní python -m firemni_databaze.nace_ciselniky nahraj
-- z ciselniky/nace/*.csv (sestavené z oficiálních zdrojů ČSÚ, viz
-- docs/cz-nace-2025.md). Skript je idempotentní.
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS obor;
COMMENT ON SCHEMA obor IS 'Klasifikace odvětví CZ-NACE 2008/2025 – číselníky, kódy firem v čase, rozhraní pro ostatní produkty';

-- ---------------------------------------------------------------------
-- Číselník obou verzí, všech 5 úrovní (sekce, oddíl, skupina, třída,
-- národní podtřída) + pseudokódy RES (X/04, Y/00).
-- Kódy bez teček: F, 41, 412, 4120, 41201.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS obor.nace_ciselnik (
    verze           smallint NOT NULL CHECK (verze IN (2008, 2025)),
    kod             text     NOT NULL,
    uroven          smallint NOT NULL CHECK (uroven BETWEEN 1 AND 5),
    nazev           text     NOT NULL,
    nadrazeny_kod   text,
    sekce           text     NOT NULL,          -- předci podle hierarchie; na vlastní úrovni položka sama
    oddil           text,
    skupina         text,
    trida           text,
    je_pseudokod    boolean  NOT NULL,          -- X nebo Y: není ekonomická činnost
    platnost_od     date,
    platnost_do     date,
    zdroj           text     NOT NULL,
    PRIMARY KEY (verze, kod),
    CHECK ((uroven = 1) = (nadrazeny_kod IS NULL))
);

COMMENT ON TABLE obor.nace_ciselnik IS 'CZ-NACE 2008 (iSMS 80004) a CZ-NACE 2025 (iSMS 80143), úrovně 1–5, s pseudokódy RES';

-- ---------------------------------------------------------------------
-- Převodník 2008 ↔ 2025 na každé úrovni zvlášť (páry na téže úrovni).
-- typ_vazby z pohledu celé úrovně: 1:1, 1:N (starý kód se dělí),
-- N:1 (staré kódy se slučují), N:M.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS obor.nace_prevodnik (
    kod_2008        text     NOT NULL,
    kod_2025        text     NOT NULL,
    uroven          smallint NOT NULL CHECK (uroven BETWEEN 1 AND 5),
    typ_vazby       text     NOT NULL CHECK (typ_vazby IN ('1:1', '1:N', 'N:1', 'N:M')),
    castecne        boolean  NOT NULL,          -- převodník uvádí „(částečně)“
    zdroj           text     NOT NULL,
    PRIMARY KEY (kod_2008, kod_2025)
);

CREATE INDEX IF NOT EXISTS nace_prevodnik_2025_idx ON obor.nace_prevodnik (kod_2025);

COMMENT ON TABLE obor.nace_prevodnik IS 'Převodník CZ-NACE 2008 ↔ 2025 (Eurostat V1.05 pro úrovně 1–4, ČSÚ pro 5místné položky)';

-- ---------------------------------------------------------------------
-- Sekce CZ-NACE 2025 → skupina A*10 podle NACE Rev. 2 (regionální účty
-- Eurostatu). Spojení dvou verzí klasifikace na úrovni sekcí: obsah
-- sekcí se mezi verzemi mírně liší (viz docs/cz-nace-2025.md).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS obor.nace_sekce_a10 (
    sekce_2025      text     PRIMARY KEY,
    a10_rev2        text     NOT NULL,          -- A, B-E, C, F, G-I, J, K, L, M_N, O-Q, R-U
    sekce_rev2      text     NOT NULL,          -- odpovídající sekce NACE Rev. 2 (CZ-NACE 2008)
    poznamka        text
);

COMMENT ON TABLE obor.nace_sekce_a10 IS 'Sekce CZ-NACE 2025 → skupina A*10 NACE Rev. 2 (spojení dvou verzí na úrovni sekcí)';
