-- =====================================================================
-- 06_report_zdroje.sql – další publikované údaje ČSÚ pro výpočet reportu
--
-- res.csu_obyvatelstvo – počet obyvatel ČR, krajů a okresů (DataStat OBY02A)
--                        pro hustotu registrovaných subjektů na 1 000 obyvatel
-- res.csu_vznik_zanik  – počty vzniklých a zaniklých ekonomických subjektů
--                        (DataStat RES05): ČR, kraje, okresy × FO/PO × čtvrtletí.
--                        ČSÚ je NEpublikuje v členění podle oboru (CZ-NACE).
-- Obě tabulky jsou referenční: při novém načtení se obsah nahradí.
-- =====================================================================

CREATE TABLE IF NOT EXISTS res.csu_obyvatelstvo (
    uzemi_kod        text        NOT NULL,          -- 'CZ', CZ-NUTS 3 kraje, kód okresu (109)
    uroven           text        NOT NULL CHECK (uroven IN ('STAT', 'REGION', 'KRAJ', 'OKRES')),
    uzemi            text        NOT NULL,
    rok              integer     NOT NULL,
    ukazatel_kod     text        NOT NULL,          -- 2406K2 = stav k 31. 12., 9379 = k 1. 7., 2406P = k 1. 1.
    ukazatel         text        NOT NULL,
    hodnota          numeric     NOT NULL,
    url              text        NOT NULL,
    stazeno          timestamptz NOT NULL DEFAULT now(),
    import_davka_id  bigint      NOT NULL REFERENCES dev.import_davka (id),
    PRIMARY KEY (uzemi_kod, rok, ukazatel_kod)
);

COMMENT ON TABLE res.csu_obyvatelstvo IS 'Počet obyvatel ČR, krajů a okresů (ČSÚ DataStat OBY02A)';

CREATE TABLE IF NOT EXISTS res.csu_vznik_zanik (
    uzemi_kod        text        NOT NULL,
    uroven           text        NOT NULL CHECK (uroven IN ('STAT', 'KRAJ', 'OKRES')),
    uzemi            text        NOT NULL,
    forma_kod        text        NOT NULL,          -- '0' celkem, '10' fyzické osoby, '30' právnické osoby
    forma            text        NOT NULL,
    obdobi           text        NOT NULL CHECK (obdobi ~ '^[0-9]{4}-Q[1-4]$'),
    ukazatel_kod     text        NOT NULL,          -- 4962 = vzniklé, 4963 = zaniklé
    ukazatel         text        NOT NULL,
    hodnota          numeric     NOT NULL,
    url              text        NOT NULL,
    stazeno          timestamptz NOT NULL DEFAULT now(),
    import_davka_id  bigint      NOT NULL REFERENCES dev.import_davka (id),
    PRIMARY KEY (uzemi_kod, forma_kod, obdobi, ukazatel_kod)
);

COMMENT ON TABLE res.csu_vznik_zanik IS 'Vzniklé a zaniklé ekonomické subjekty podle území a FO/PO (ČSÚ DataStat RES05), bez členění podle oboru';

-- ---------------------------------------------------------------------
-- Demografie podniků (DataStat RESDP00) – jen ČR, 18 odvětví, FO/PO, roky.
-- Jednotka je PODNIK (aktivní podnik), ne ekonomický subjekt z RES –
-- v reportu slouží jen jako kontext za ČR (rozhodnutí 10).
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS res.csu_demografie (
    odvetvi_kod      text        NOT NULL,          -- sekce CZ-NACE (B…R) nebo agregát ČSÚ
    odvetvi          text        NOT NULL,
    forma_kod        text        NOT NULL,          -- '10' podniky FO, '30' podniky PO
    rok              integer     NOT NULL,
    ukazatel_kod     text        NOT NULL,          -- 6594_RESDP aktivní, 9505 vzniklé, 9507 míra vzniků, 9506 zaniklé, 9508 míra zániků
    ukazatel         text        NOT NULL,
    hodnota          numeric     NOT NULL,
    predbezna        boolean     NOT NULL DEFAULT false,
    url              text        NOT NULL,
    stazeno          timestamptz NOT NULL DEFAULT now(),
    import_davka_id  bigint      NOT NULL REFERENCES dev.import_davka (id),
    PRIMARY KEY (odvetvi_kod, forma_kod, rok, ukazatel_kod)
);

COMMENT ON TABLE res.csu_demografie IS 'Demografie podniků ČR podle odvětví a FO/PO (ČSÚ DataStat RESDP00) – jiná jednotka než RES';
