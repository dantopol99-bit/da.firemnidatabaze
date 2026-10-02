-- =====================================================================
-- 09_eurostat_sbs.sql – statistika podniků Eurostatu podle velikostních tříd
--
-- res.eu_sbs – vstupy modelových odhadů ekonomického profilu (Blok 8):
--   sbs_sc_ovw     ČR × CZ-NACE (sekce, oddíly) × velikostní třída podle počtu
--                  zaměstnaných osob: podniky (ENT_NR), zaměstnané osoby (EMP_NR),
--                  přidaná hodnota (AV_MEUR), čistý obrat (NETTUR_MEUR), hrubý
--                  provozní přebytek (GOS_MEUR); peněžní údaje jen v mil. EUR
--   ert_bil_eur_a  roční průměrný kurz CZK/EUR (pro převod typického obratu na Kč)
-- Zdroj: API Eurostatu (robots.txt /eurostat/api/ nezakazuje; licence: další užití
-- s uvedením zdroje, úpravy označit). Tabulka je referenční: obsah sady se nahradí.
-- =====================================================================

CREATE TABLE IF NOT EXISTS res.eu_sbs (
    sada             text        NOT NULL,          -- sbs_sc_ovw | ert_bil_eur_a
    nace             text        NOT NULL,          -- F, F41 …; '-' u kurzu
    velikost         text        NOT NULL,          -- TOTAL, 0_1, 0-9, 2-9, 10-19, 20-49, 50-249, GE250; '-' u kurzu
    rok              integer     NOT NULL,
    ukazatel         text        NOT NULL,          -- ENT_NR, EMP_NR, AV_MEUR, NETTUR_MEUR, GOS_MEUR, KURZ_CZK_EUR
    hodnota          numeric     NOT NULL,
    priznak          text        NOT NULL DEFAULT '',
    aktualizace      timestamptz,
    url              text        NOT NULL,
    stazeno          timestamptz NOT NULL DEFAULT now(),
    import_davka_id  bigint      NOT NULL REFERENCES dev.import_davka (id),
    PRIMARY KEY (sada, nace, velikost, rok, ukazatel)
);

COMMENT ON TABLE res.eu_sbs IS 'Statistika podniků Eurostatu podle velikostních tříd (sbs_sc_ovw, ČR) a kurz CZK/EUR – vstupy modelových odhadů';
