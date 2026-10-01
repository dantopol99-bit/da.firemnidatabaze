-- =====================================================================
-- 07_mzdy.sql – zaměstnanost a průměrné mzdy (ČSÚ DataStat)
--
-- res.csu_mzdy – průměrný evidenční počet zaměstnanců a průměrná hrubá měsíční
-- mzda (přepočtené počty i fyzické osoby) z publikovaných výběrů DataStatu:
--   MZDCRRT2  kraj × sekce CZ-NACE, roční zjišťování, pracovištní metoda (2010–2022)
--   MZDCRRT1  ČR × sekce CZ-NACE, roční zjišťování (2010–2022)
--   MZDRT2    ČR × sekce CZ-NACE, čtvrtletní zjišťování, kumulace za rok (2001–…)
--   MZDRT5    ČR a kraje, všechna odvětví, čtvrtletní zjišťování, pracovištní metoda (2011–…)
-- Kraj × sekce ČSÚ publikuje jen z ročního zjišťování (MZDCRR); v čtvrtletním je
-- kombinace kraj × odvětví zakázaná. Nic se nedopočítává z jiných úrovní.
-- Tabulka je referenční: při novém načtení se obsah výběru nahradí.
-- =====================================================================

CREATE TABLE IF NOT EXISTS res.csu_mzdy (
    vyber            text        NOT NULL,          -- kód výběru DataStatu (MZDCRRT1, MZDCRRT2, MZDRT2, MZDRT5)
    zjisteni         text        NOT NULL CHECK (zjisteni IN ('rocni', 'ctvrtletni')),
    uzemi_kod        text        NOT NULL,          -- 'CZ' nebo CZ-NUTS 3 kraje
    uroven           text        NOT NULL CHECK (uroven IN ('STAT', 'KRAJ')),
    uzemi            text        NOT NULL,
    nace_kod         text        NOT NULL,          -- '0' = všechna odvětví, sekce A…S, '05390001' = B–E průmysl
    nace             text        NOT NULL,
    rok              integer     NOT NULL,
    ukazatel_kod     text        NOT NULL,          -- ZAM_PREP, ZAM_FYZ, MZDA_PREP, MZDA_FYZ (normalizované)
    ukazatel_csu     text        NOT NULL,          -- kód ukazatele ČSÚ v dané sadě
    ukazatel         text        NOT NULL,
    hodnota          numeric     NOT NULL,          -- zaměstnanci v tis. osob, mzda v Kč
    predbezna        boolean     NOT NULL DEFAULT false,
    url              text        NOT NULL,
    stazeno          timestamptz NOT NULL DEFAULT now(),
    import_davka_id  bigint      NOT NULL REFERENCES dev.import_davka (id),
    PRIMARY KEY (vyber, uzemi_kod, nace_kod, rok, ukazatel_kod)
);

COMMENT ON TABLE res.csu_mzdy IS 'Zaměstnanci a průměrné hrubé měsíční mzdy (ČSÚ DataStat MZDCRR, MZDR) – kraj × sekce jen z ročního zjišťování';
