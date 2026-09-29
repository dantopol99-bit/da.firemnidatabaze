-- =====================================================================
-- 03_subjekt.sql – obsah snímků RES
--
-- Sloupce odpovídají souborům ČSÚ 1:1 (stejné názvy malými písmeny,
-- stejný význam, viz CSVW metadata). Jediné úpravy při načtení:
--   * prázdná hodnota (i "" v uvozovkách) = NULL,
--   * sloupce s datatype "date" v metadatech jsou typu date.
-- Kódy (NACE, OKRESLAU, KATPO…) zůstávají text – úvodní nuly nesou
-- význam a délka kódu NACE určuje úroveň klasifikace (2–5 znaků).
-- Snímky se nepřepisují ani nemažou; další snímek = nové datum_snimku.
-- =====================================================================

-- ---------------------------------------------------------------------
-- res_data.csv – Seznam ekonomických subjektů (jeden řádek na IČO)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS res.subjekt (
    ico           text    NOT NULL CHECK (ico ~ '^[0-9]{8}$'),  -- ICO
    datum_snimku  date    NOT NULL,                             -- = DATPLAT celého snímku
    snimek_id     bigint  NOT NULL REFERENCES res.snimek (id),

    okreslau      text,   -- kód okresu sídla (CZ-NUTS/LAU 1), číselník 109
    ddatvzn       date,   -- datum vzniku
    ddatzan       date,   -- datum zániku
    zpzan         text,   -- způsob zániku, číselník 572
    ddatpakt      date,   -- datum aktualizace záznamu
    forma         text,   -- právní forma (statistická), číselník 56
    rosforma      text,   -- právní forma (registr osob), číselník 149
    katpo         text,   -- kategorie počtu pracovníků, číselník 579
    nace          text,   -- převažující činnost CZ-NACE (Rev. 2), klasifikace 80004
    nace2025      text,   -- převažující činnost CZ-NACE 2025, klasifikace 80143
    iczuj         text,   -- základní územní jednotka sídla, číselník 51
    firma         text,   -- obchodní firma / název / jméno
    ciss2010      text,   -- institucionální sektor ESA 2010, číselník 5161
    kodadm        text,   -- kód adresního místa RÚIAN
    textadr       text,   -- text adresy (jen bez KODADM)
    psc           text,
    obec_text     text,
    cobce_text    text,
    ulice_text    text,
    typcdom       text,   -- typ čísla domovního, číselník 73
    cdom          text,
    cor           text,
    datplat       date    NOT NULL,   -- datum platnosti dat
    priznak       text,   -- P = přírůstek, Z = změna oproti minulému snímku

    PRIMARY KEY (ico, datum_snimku),
    CHECK (datplat = datum_snimku)
);

COMMENT ON TABLE res.subjekt IS 'Snímek res_data.csv (RES, ČSÚ): jeden řádek na IČO a datum snímku, sloupce beze změny významu';
COMMENT ON COLUMN res.subjekt.ddatzan IS 'Vyplněno = subjekt zanikl. Zaniklé FO mají (GDPR) jen IČO a datum zániku; zaniklé více než 4 roky v souboru nejsou';

CREATE INDEX IF NOT EXISTS subjekt_snimek_okres_nace_idx ON res.subjekt (datum_snimku, okreslau, nace);

CREATE OR REPLACE TRIGGER subjekt_zakaz_zmeny
    BEFORE UPDATE ON res.subjekt
    FOR EACH ROW EXECUTE FUNCTION dev.zakaz_zmeny();

CREATE OR REPLACE TRIGGER subjekt_zakaz_mazani
    BEFORE DELETE ON res.subjekt
    FOR EACH ROW EXECUTE FUNCTION dev.zakaz_mazani();

CREATE OR REPLACE TRIGGER subjekt_zakaz_truncate
    BEFORE TRUNCATE ON res.subjekt
    FOR EACH STATEMENT EXECUTE FUNCTION dev.zakaz_mazani();

-- ---------------------------------------------------------------------
-- res_pf_nace.csv – Seznam právních forem a činností (N řádků na IČO)
-- Všechny činnosti subjektu (ne jen převažující), každá podle zdroje
-- údaje. Zaniklé subjekty mají jediný řádek bez KODCIS/HODN.
-- Klíč tvoří i sloupce s NULL, proto UNIQUE NULLS NOT DISTINCT.
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS res.pf_nace (
    ico           text    NOT NULL CHECK (ico ~ '^[0-9]{8}$'),
    datum_snimku  date    NOT NULL,
    snimek_id     bigint  NOT NULL REFERENCES res.snimek (id),

    zdrud         text,   -- zdroj údaje, číselník 564
    kodcis        text,   -- 80004 = CZ-NACE, 80143 = CZ-NACE 2025, 56 = právní forma
    hodn          text,   -- kód položky v číselníku KODCIS
    datplat       date    NOT NULL,
    ddatpakt      date,
    priznak       text,

    CONSTRAINT pf_nace_klic UNIQUE NULLS NOT DISTINCT (ico, datum_snimku, kodcis, zdrud, hodn),
    CHECK (datplat = datum_snimku)
);

COMMENT ON TABLE res.pf_nace IS 'Snímek res_pf_nace.csv (RES, ČSÚ): všechny činnosti a právní formy subjektu podle zdroje údaje';

CREATE OR REPLACE TRIGGER pf_nace_zakaz_zmeny
    BEFORE UPDATE ON res.pf_nace
    FOR EACH ROW EXECUTE FUNCTION dev.zakaz_zmeny();

CREATE OR REPLACE TRIGGER pf_nace_zakaz_mazani
    BEFORE DELETE ON res.pf_nace
    FOR EACH ROW EXECUTE FUNCTION dev.zakaz_mazani();

CREATE OR REPLACE TRIGGER pf_nace_zakaz_truncate
    BEFORE TRUNCATE ON res.pf_nace
    FOR EACH STATEMENT EXECUTE FUNCTION dev.zakaz_mazani();
