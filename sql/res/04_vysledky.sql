-- =====================================================================
-- 04_vysledky.sql – výsledky kontrol nad snímky RES
--
-- res.kvalita     – metriky kvality snímku (bod 4 zadání), zapisuje je
--                   importér po každém načtení ze res.v_kvalita
-- res.csu_agregat – agregáty, které ČSÚ sám publikuje z RES v DataStatu
--                   (veřejná databáze), pro kontrolu úplnosti snímku
-- Obě tabulky jsou odvozené/referenční: při přepočtu se obsah pro daný
-- snímek / výběr nahradí.
-- =====================================================================

CREATE TABLE IF NOT EXISTS res.kvalita (
    datum_snimku  date        NOT NULL,
    zaklad        text        NOT NULL CHECK (zaklad IN ('vse', 'bez_zaniku', 'se_zanikem')),
    poradi        integer     NOT NULL,
    ukazatel      text        NOT NULL,
    popis         text        NOT NULL,
    pocet         bigint      NOT NULL,
    jmenovatel    bigint      NOT NULL,
    podil         numeric(9, 6),
    spocitano     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (datum_snimku, zaklad, ukazatel)
);

COMMENT ON TABLE res.kvalita IS 'Kvalita snímku RES: počty a podíly chybějících údajů (základ: všechny řádky / bez zániku / se zánikem)';

CREATE TABLE IF NOT EXISTS res.csu_agregat (
    vyber            text        NOT NULL,          -- kód výběru v DataStatu, např. 'RES02QT1'
    ukazatel_kod     text        NOT NULL,          -- '4958_reg' = celkem, '4958_akt' = se zjištěnou aktivitou
    ukazatel         text        NOT NULL,
    uzemi_kod        text        NOT NULL,          -- 'CZ' nebo CZ-NUTS 3 kraje
    uzemi            text        NOT NULL,
    nace_kod         text        NOT NULL,          -- položka dimenze CZ-NACE ('0' = celkem, '05390001' = B–E, '8' = X)
    nace             text        NOT NULL,
    obdobi           text        NOT NULL CHECK (obdobi ~ '^[0-9]{4}-Q[1-4]$'),
    hodnota          numeric     NOT NULL,
    url              text        NOT NULL,
    stazeno          timestamptz NOT NULL DEFAULT now(),
    import_davka_id  bigint      NOT NULL REFERENCES dev.import_davka (id),
    PRIMARY KEY (vyber, ukazatel_kod, uzemi_kod, nace_kod, obdobi)
);

COMMENT ON TABLE res.csu_agregat IS 'Počty ekonomických subjektů publikované ČSÚ v DataStatu (stav ke konci čtvrtletí)';

-- Poslední den čtvrtletí z označení '2026-Q2'
CREATE OR REPLACE FUNCTION res.konec_ctvrtleti(p_obdobi text)
RETURNS date
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT (make_date(split_part(p_obdobi, '-Q', 1)::int, split_part(p_obdobi, '-Q', 2)::int * 3, 1)
            + interval '1 month - 1 day')::date
$$;
