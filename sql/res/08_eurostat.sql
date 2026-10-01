-- =====================================================================
-- 08_eurostat.sql – regionální účty Eurostatu (ekonomický profil)
--
-- res.eu_regionalni_ucty – hrubá přidaná hodnota, zaměstnanost a náhrady
-- zaměstnancům z API Eurostatu (JSON-stat, /eurostat/api/dissemination, robots.txt
-- tuto cestu nezakazuje; licence: další užití povoleno s uvedením zdroje,
-- úpravy dat se musí označit):
--   nama_10r_3gva    HPH, NUTS 0/2/3 × A*10, mil. Kč, běžné ceny (CP_MNAC) a ceny
--                    předchozího roku (PYP_MNAC)
--   nama_10r_3empers zaměstnanost (národní účty, tis. osob): zaměstnaní celkem (EMP),
--                    zaměstnanci (SAL), sebezaměstnaní (SELF), NUTS 0/3 × A*10
--   nama_10r_2coe    náhrady zaměstnancům, NUTS 0/2 × A*10, mil. Kč (jen regiony
--                    soudržnosti – za kraje Eurostat nepublikuje)
-- Tabulka je referenční: při novém načtení se obsah sady nahradí.
-- =====================================================================

CREATE TABLE IF NOT EXISTS res.eu_regionalni_ucty (
    sada             text        NOT NULL,          -- kód datové sady Eurostatu
    geo              text        NOT NULL,          -- NUTS 2021: CZ, CZ0x (region soudržnosti), CZ0xx (kraj)
    uroven           text        NOT NULL CHECK (uroven IN ('STAT', 'REGION', 'KRAJ')),
    nace             text        NOT NULL,          -- skupina A*10 (TOTAL, A, B-E, C, F, G-I, J, K, L, M_N, O-Q, R-U …)
    rok              integer     NOT NULL,
    ukazatel         text        NOT NULL,          -- HPH_CP, HPH_PYP, ZAM_EMP, ZAM_SAL, ZAM_SELF, NAHRADY
    hodnota          numeric     NOT NULL,          -- mil. Kč nebo tis. osob
    priznak          text        NOT NULL DEFAULT '', -- příznak Eurostatu (p = předběžné, e = odhad …), '' = bez příznaku
    aktualizace      timestamptz,                   -- „updated“ sady podle Eurostatu
    url              text        NOT NULL,
    stazeno          timestamptz NOT NULL DEFAULT now(),
    import_davka_id  bigint      NOT NULL REFERENCES dev.import_davka (id),
    PRIMARY KEY (sada, geo, nace, rok, ukazatel)
);

COMMENT ON TABLE res.eu_regionalni_ucty IS 'Regionální účty Eurostatu (nama_10r_3gva, nama_10r_3empers, nama_10r_2coe) – ČR, regiony soudržnosti, kraje × A*10';
