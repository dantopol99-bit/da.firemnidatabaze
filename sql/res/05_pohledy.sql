-- =====================================================================
-- 05_pohledy.sql – čtení snímků RES přes číselníky, kontroly a průniky
--
-- res.v_subjekt             – snímek s názvy z číselníků, sekcí NACE a krajem
-- res.v_kvalita             – metriky kvality (importér je ukládá do res.kvalita)
-- res.v_pocty_kraj_sekce    – subjekty bez zániku: kraj × sekce CZ-NACE
-- res.v_srovnani_csu        – totéž proti agregátům ČSÚ (DataStat RES02QT1)
-- res.v_jadro_kontrola      – firmy z jádra (ARES) proti RES – jen ke čtení
-- res.prunik_souhrn(...)    – průnik obor × kraj s prahem pro publikaci
-- res.v_pilot_f_liberecky   – pilot: sekce F × Liberecký kraj
-- =====================================================================

-- Datum posledního snímku res_data.csv
CREATE OR REPLACE FUNCTION res.posledni_snimek()
RETURNS date
LANGUAGE sql
STABLE
AS $$
    SELECT max(datum_snimku) FROM res.snimek WHERE soubor = 'res_data.csv'
$$;

-- ---------------------------------------------------------------------
-- Snímek s výklady kódů. Kraj = okres sídla → kraj podle vazby
-- číselníků ČSÚ (res.cis_okres.kraj_kod). Sekce NACE z hierarchie
-- klasifikace (u kódů na úrovni oddílu/skupiny/třídy stejně).
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW res.v_subjekt AS
SELECT
    s.ico,
    s.datum_snimku,
    s.ddatzan IS NOT NULL      AS je_zanikly,
    s.firma,
    s.forma,
    pf.nazev                   AS forma_nazev,
    s.katpo,
    kp.nazev                   AS katpo_nazev,
    s.nace,
    n.sekce                    AS nace_sekce,
    n.oddil                    AS nace_oddil,
    n.skupina                  AS nace_skupina,
    n.trida                    AS nace_trida,
    n.je_pseudokod             AS nace_je_pseudokod,
    s.nace2025,
    n25.sekce                  AS nace2025_sekce,
    n25.oddil                  AS nace2025_oddil,
    n25.je_pseudokod           AS nace2025_je_pseudokod,
    s.okreslau                 AS okres_kod,
    o.nazev                    AS okres_nazev,
    k.kod                      AS kraj_kod,
    k.nazev                    AS kraj_nazev,
    k.kod_ruian                AS kraj_kod_ruian,
    s.ddatvzn,
    extract(year FROM s.ddatvzn)::int AS rok_vzniku,
    s.ddatzan,
    s.zpzan
FROM res.subjekt s
LEFT JOIN res.cis_nace n          ON n.klasifikace = 80004 AND n.kod = s.nace
LEFT JOIN res.cis_nace n25        ON n25.klasifikace = 80143 AND n25.kod = s.nace2025
LEFT JOIN res.cis_okres o         ON o.kod = s.okreslau
LEFT JOIN res.cis_kraj k          ON k.kod = o.kraj_kod
LEFT JOIN res.cis_pravni_forma pf ON pf.ciselnik = 56 AND pf.kod = s.forma
LEFT JOIN res.cis_katpo kp        ON kp.kod = s.katpo;

COMMENT ON VIEW res.v_subjekt IS 'Snímky RES s výklady kódů: sekce/oddíl NACE, okres a kraj, právní forma, KATPO';

-- ---------------------------------------------------------------------
-- Kvalita snímku. Každý ukazatel ve třech základech:
--   vse = všechny řádky, bez_zaniku = DDATZAN prázdné, se_zanikem.
-- „Bez NACE sekce“ = NACE prázdné, pseudokód (X/Y) nebo kód mimo
-- číselník – subjekt nejde zařadit do sekce A–U. Stejně „bez kraje“.
-- Tyto dva ukazatele u subjektů bez zániku hlídá práh 20 % (importér).
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW res.v_kvalita AS
WITH r AS (
    SELECT
        s.datum_snimku,
        s.ddatzan IS NOT NULL                                          AS zanik,
        s.ddatzan IS NOT NULL AND s.ddatvzn IS NULL AND s.forma IS NULL
            AND s.okreslau IS NULL AND s.nace IS NULL AND s.firma IS NULL AS jen_ico,
        s.nace IS NULL                                                 AS nace_prazdne,
        coalesce(n.je_pseudokod, false)                                AS nace_pseudo,
        s.nace IS NOT NULL AND n.kod IS NULL                           AS nace_mimo,
        s.nace2025 IS NULL                                             AS nace2025_prazdne,
        s.okreslau IS NULL                                             AS okres_prazdny,
        s.okreslau IS NOT NULL AND o.kod IS NULL                       AS okres_mimo,
        s.katpo IS NULL                                                AS katpo_prazdne,
        s.katpo = '000'                                                AS katpo_neuvedeno,
        s.katpo IS NOT NULL AND kp.kod IS NULL                         AS katpo_mimo,
        s.forma IS NULL                                                AS forma_prazdna,
        s.forma IS NOT NULL AND pf.kod IS NULL                         AS forma_mimo,
        s.ddatvzn IS NULL                                              AS vznik_prazdny,
        s.kodadm IS NULL                                               AS kodadm_prazdny
    FROM res.subjekt s
    LEFT JOIN res.cis_nace n          ON n.klasifikace = 80004 AND n.kod = s.nace
    LEFT JOIN res.cis_okres o         ON o.kod = s.okreslau
    LEFT JOIN res.cis_katpo kp        ON kp.kod = s.katpo
    LEFT JOIN res.cis_pravni_forma pf ON pf.ciselnik = 56 AND pf.kod = s.forma
), z AS (
    SELECT 'vse'::text AS zaklad, r.* FROM r
    UNION ALL
    SELECT CASE WHEN r.zanik THEN 'se_zanikem' ELSE 'bez_zaniku' END, r.* FROM r
), a AS (
    SELECT
        datum_snimku, zaklad,
        count(*)                                                             AS n,
        count(*) FILTER (WHERE zanik)                                        AS se_zanikem,
        count(*) FILTER (WHERE NOT zanik)                                    AS bez_zaniku,
        count(*) FILTER (WHERE jen_ico)                                      AS jen_ico,
        count(*) FILTER (WHERE nace_prazdne)                                 AS nace_prazdne,
        count(*) FILTER (WHERE nace_pseudo)                                  AS nace_pseudo,
        count(*) FILTER (WHERE nace_mimo)                                    AS nace_mimo,
        count(*) FILTER (WHERE nace_prazdne OR nace_pseudo OR nace_mimo)     AS bez_nace_sekce,
        count(*) FILTER (WHERE nace2025_prazdne)                             AS nace2025_prazdne,
        count(*) FILTER (WHERE okres_prazdny)                                AS okres_prazdny,
        count(*) FILTER (WHERE okres_mimo)                                   AS okres_mimo,
        count(*) FILTER (WHERE okres_prazdny OR okres_mimo)                  AS bez_kraje,
        count(*) FILTER (WHERE katpo_prazdne)                                AS katpo_prazdne,
        count(*) FILTER (WHERE katpo_neuvedeno)                              AS katpo_neuvedeno,
        count(*) FILTER (WHERE katpo_mimo)                                   AS katpo_mimo,
        count(*) FILTER (WHERE katpo_prazdne OR katpo_neuvedeno OR katpo_mimo) AS bez_kategorie_prac,
        count(*) FILTER (WHERE forma_prazdna)                                AS forma_prazdna,
        count(*) FILTER (WHERE forma_mimo)                                   AS forma_mimo,
        count(*) FILTER (WHERE vznik_prazdny)                                AS vznik_prazdny,
        count(*) FILTER (WHERE kodadm_prazdny)                               AS kodadm_prazdny
    FROM z
    GROUP BY datum_snimku, zaklad
)
SELECT
    a.datum_snimku,
    a.zaklad,
    u.poradi,
    u.ukazatel,
    u.popis,
    u.pocet,
    a.n AS jmenovatel,
    round(u.pocet::numeric / nullif(a.n, 0), 6) AS podil
FROM a
CROSS JOIN LATERAL (VALUES
    ( 1, 'radky',                    'Řádků',                                                   a.n),
    ( 2, 'se_zanikem',               'S datem zániku',                                          a.se_zanikem),
    ( 3, 'bez_zaniku',               'Bez data zániku',                                         a.bez_zaniku),
    ( 4, 'zanik_jen_ico',            'Zaniklé jen s IČO a datem zániku (FO, GDPR)',             a.jen_ico),
    (10, 'nace_prazdne',             'NACE prázdné',                                            a.nace_prazdne),
    (11, 'nace_pseudokod',           'NACE je pseudokód RES (00 = neuvedeno v přílohách ŽZ, 04 = nezjištěno)', a.nace_pseudo),
    (12, 'nace_mimo_ciselnik',       'NACE mimo číselník CZ_NACE_RES',                          a.nace_mimo),
    (13, 'bez_nace_sekce',           'Bez NACE sekce A–U (prázdné + pseudokód + mimo číselník)', a.bez_nace_sekce),
    (14, 'nace2025_prazdne',         'NACE2025 prázdné',                                        a.nace2025_prazdne),
    (20, 'uzemi_prazdne',            'Územní kód (OKRESLAU) prázdný',                           a.okres_prazdny),
    (21, 'uzemi_mimo_ciselnik',      'OKRESLAU mimo číselník 109',                              a.okres_mimo),
    (22, 'bez_kraje',                'Nelze určit kraj (prázdný nebo neznámý okres)',           a.bez_kraje),
    (30, 'katpo_prazdne',            'Kategorie pracovníků (KATPO) prázdná',                     a.katpo_prazdne),
    (31, 'katpo_neuvedeno',          'KATPO = 000 Neuvedeno',                                   a.katpo_neuvedeno),
    (32, 'katpo_mimo_ciselnik',      'KATPO mimo číselník 579',                                 a.katpo_mimo),
    (33, 'bez_kategorie_pracovniku', 'Bez kategorie pracovníků (prázdná + 000 + mimo číselník)', a.bez_kategorie_prac),
    (40, 'forma_prazdna',            'Právní forma (FORMA) prázdná',                            a.forma_prazdna),
    (41, 'forma_mimo_ciselnik',      'FORMA mimo číselník 56',                                  a.forma_mimo),
    (42, 'vznik_prazdny',            'Datum vzniku prázdné',                                    a.vznik_prazdny),
    (43, 'adresni_misto_prazdne',    'Kód adresního místa (KODADM) prázdný',                    a.kodadm_prazdny)
) AS u (poradi, ukazatel, popis, pocet);

COMMENT ON VIEW res.v_kvalita IS 'Metriky kvality snímků RES; importér je ukládá do res.kvalita';

-- ---------------------------------------------------------------------
-- Subjekty bez zániku podle kraje a sekce CZ-NACE (Rev. 2, 21 sekcí
-- A–U + pseudo-sekce X/Y). NULL sekce = NACE prázdné nebo mimo číselník.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW res.v_pocty_kraj_sekce AS
SELECT
    datum_snimku,
    kraj_kod,
    kraj_nazev,
    nace_sekce AS sekce,
    count(*) AS pocet
FROM res.v_subjekt
WHERE NOT je_zanikly
GROUP BY datum_snimku, kraj_kod, kraj_nazev, nace_sekce;

COMMENT ON VIEW res.v_pocty_kraj_sekce IS 'Subjekty bez data zániku: kraj × sekce CZ-NACE (Rev. 2)';

-- ---------------------------------------------------------------------
-- Srovnání posledního snímku s posledním čtvrtletím, které ČSÚ publikuje
-- (DataStat, výběr RES02QT1: ČR a kraje × odvětví CZ-NACE).
-- ČSÚ publikuje průmysl jen souhrnně (B–E) a pseudokódy RES jako
-- „X Nezjištěno“; naše sekce se na tyto kategorie převádějí.
--   nase_bez_zaniku  = subjekty bez data zániku ve snímku (definice ČSÚ,
--                      ale k datu snímku, ne ke konci čtvrtletí),
--   nase_k_datu_csu  = rekonstrukce stavu ke konci čtvrtletí ČSÚ ze
--                      snímku: vznik ≤ konec čtvrtletí a (bez zániku
--                      nebo zánik později). Zaniklé FO bez atributů
--                      (GDPR) do ní zařadit nelze.
-- Ukazatel „se zjištěnou aktivitou“ (platí daně/pojistné) otevřená data
-- RES neobsahují – je tu jen pro pojmenování rozdílu registrované × aktivní.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW res.v_srovnani_csu AS
WITH ref AS (
    SELECT
        res.posledni_snimek() AS datum_snimku,
        q.obdobi,
        res.konec_ctvrtleti(q.obdobi) AS konec_obdobi
    FROM (SELECT max(obdobi) AS obdobi FROM res.csu_agregat WHERE vyber = 'RES02QT1') q
), nase AS (
    SELECT
        v.kraj_kod,
        CASE
            WHEN v.nace_sekce IN ('B', 'C', 'D', 'E')              THEN '05390001'
            WHEN v.nace_sekce IS NULL OR v.nace_je_pseudokod     THEN '8'
            ELSE v.nace_sekce
        END AS nace_kod,
        NOT v.je_zanikly AS bez_zaniku,
        coalesce(v.ddatvzn <= ref.konec_obdobi
                 AND (v.ddatzan IS NULL OR v.ddatzan > ref.konec_obdobi), false) AS existoval_k_datu_csu
    FROM res.v_subjekt v
    CROSS JOIN ref
    WHERE v.datum_snimku = ref.datum_snimku
), agg AS (
    SELECT
        CASE WHEN grouping(kraj_kod) = 1 THEN 'CZ' ELSE coalesce(kraj_kod, '?') END AS uzemi_kod,
        CASE WHEN grouping(nace_kod) = 1 THEN '0'  ELSE nace_kod END              AS nace_kod,
        count(*) FILTER (WHERE bez_zaniku)           AS nase_bez_zaniku,
        count(*) FILTER (WHERE existoval_k_datu_csu) AS nase_k_datu_csu
    FROM nase
    WHERE bez_zaniku OR existoval_k_datu_csu
    GROUP BY CUBE (kraj_kod, nace_kod)
), csu AS (
    SELECT
        c.uzemi_kod, c.uzemi, c.nace_kod, c.nace, c.obdobi,
        max(c.hodnota) FILTER (WHERE c.ukazatel_kod = '4958_reg') AS registrovane,
        max(c.hodnota) FILTER (WHERE c.ukazatel_kod = '4958_akt') AS aktivni
    FROM res.csu_agregat c
    JOIN ref ON ref.obdobi = c.obdobi
    WHERE c.vyber = 'RES02QT1'
    GROUP BY c.uzemi_kod, c.uzemi, c.nace_kod, c.nace, c.obdobi
)
SELECT
    ref.datum_snimku,
    ref.obdobi                                    AS csu_obdobi,
    ref.konec_obdobi                              AS csu_stav_k,
    coalesce(csu.uzemi_kod, agg.uzemi_kod)        AS uzemi_kod,
    csu.uzemi,
    coalesce(csu.nace_kod, agg.nace_kod)          AS nace_kod,
    csu.nace,
    coalesce(agg.nase_bez_zaniku, 0)              AS nase_bez_zaniku,
    coalesce(agg.nase_k_datu_csu, 0)              AS nase_k_datu_csu,
    csu.registrovane::bigint                      AS csu_registrovane,
    csu.aktivni::bigint                           AS csu_se_zjistenou_aktivitou,
    coalesce(agg.nase_bez_zaniku, 0) - csu.registrovane::bigint AS rozdil,
    round(100.0 * (coalesce(agg.nase_bez_zaniku, 0) - csu.registrovane) / nullif(csu.registrovane, 0), 2) AS rozdil_pct,
    round(100.0 * (coalesce(agg.nase_k_datu_csu, 0) - csu.registrovane) / nullif(csu.registrovane, 0), 2) AS rozdil_k_datu_csu_pct,
    CASE
        WHEN csu.registrovane IS NULL OR csu.registrovane = 0 THEN coalesce(agg.nase_bez_zaniku, 0) > 0
        ELSE abs(coalesce(agg.nase_bez_zaniku, 0) - csu.registrovane) > 0.10 * csu.registrovane
    END                                           AS nad_10_pct,
    round(100.0 * csu.aktivni / nullif(csu.registrovane, 0), 1) AS csu_podil_aktivnich_pct
FROM csu
FULL JOIN agg ON agg.uzemi_kod = csu.uzemi_kod AND agg.nace_kod = csu.nace_kod
CROSS JOIN ref;

COMMENT ON VIEW res.v_srovnani_csu IS 'Poslední snímek RES proti agregátům ČSÚ (RES02QT1) po krajích a odvětvích CZ-NACE';

-- ---------------------------------------------------------------------
-- Kontrola jádra (ARES) proti RES. JEN ČTENÍ – nic se nepřepisuje.
-- Pozor na verze klasifikace: ARES pole czNace (→ dev.subjekt_verze.cz_nace)
-- obsahuje CZ-NACE 2025 a VŠECHNY činnosti subjektu; RES NACE2025 je
-- převažující činnost. Shoda proto = převažující činnost z RES je
-- v seznamu činností z ARES (PRESNA), nebo aspoň její oddíl (ODDIL).
-- Kraj: dev.adresa.kod_kraje je kód RÚIAN → res.cis_kraj.kod_ruian.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW res.v_jadro_kontrola AS
SELECT
    j.ico,
    j.nazev                          AS ares_nazev,
    j.stav_kod                       AS ares_stav,
    r.ico IS NOT NULL                AS v_res,
    r.datum_snimku                   AS res_datum_snimku,
    r.je_zanikly                     AS res_zanikly,
    CASE
        WHEN r.ico IS NULL THEN NULL
        ELSE (j.stav_kod = 'ZANIKLY') = r.je_zanikly
    END                              AS stav_sedi,
    j.cz_nace                        AS ares_nace2025_vse,
    r.nace2025                       AS res_nace2025,
    r.nace2025_sekce                 AS res_sekce2025,
    CASE
        WHEN r.ico IS NULL                                        THEN NULL
        WHEN r.nace2025 IS NULL OR j.cz_nace IS NULL
             OR coalesce(r.nace2025_je_pseudokod, false)          THEN 'NELZE'
        WHEN r.nace2025 = ANY (j.cz_nace)                         THEN 'PRESNA'
        WHEN EXISTS (SELECT 1 FROM unnest(j.cz_nace) AS k (kod)
                     WHERE left(k.kod, 2) = left(r.nace2025, 2))  THEN 'ODDIL'
        ELSE 'NE'
    END                              AS nace_shoda,
    ka.kod                           AS ares_kraj_kod,
    ka.nazev                         AS ares_kraj,
    r.kraj_kod                       AS res_kraj_kod,
    r.kraj_nazev                     AS res_kraj,
    CASE
        WHEN r.ico IS NULL OR ka.kod IS NULL OR r.kraj_kod IS NULL THEN NULL
        ELSE ka.kod = r.kraj_kod
    END                              AS kraj_sedi
FROM dev.subjekt_aktualne j
LEFT JOIN dev.adresa a     ON a.id = j.sidlo_adresa_id
LEFT JOIN res.cis_kraj ka  ON ka.kod_ruian = a.kod_kraje
LEFT JOIN res.v_subjekt r  ON r.ico = j.ico AND r.datum_snimku = res.posledni_snimek();

COMMENT ON VIEW res.v_jadro_kontrola IS 'Firmy z jádra (ARES) proti poslednímu snímku RES: přítomnost, stav, NACE 2025, kraj. Jen kontrola.';

CREATE OR REPLACE VIEW res.v_jadro_kontrola_souhrn AS
SELECT
    count(*)                                          AS firem_v_jadru,
    count(*) FILTER (WHERE v_res)                     AS v_res,
    count(*) FILTER (WHERE NOT v_res)                 AS neni_v_res,
    count(*) FILTER (WHERE stav_sedi)                 AS stav_sedi,
    count(*) FILTER (WHERE NOT stav_sedi)             AS stav_nesedi,
    count(*) FILTER (WHERE nace_shoda = 'PRESNA')     AS nace_presna,
    count(*) FILTER (WHERE nace_shoda = 'ODDIL')      AS nace_jen_oddil,
    count(*) FILTER (WHERE nace_shoda = 'NE')         AS nace_nesedi,
    count(*) FILTER (WHERE nace_shoda = 'NELZE')      AS nace_nelze_porovnat,
    count(*) FILTER (WHERE kraj_sedi)                 AS kraj_sedi,
    count(*) FILTER (WHERE NOT kraj_sedi)             AS kraj_nesedi,
    count(*) FILTER (WHERE v_res AND kraj_sedi IS NULL) AS kraj_nelze_porovnat
FROM res.v_jadro_kontrola;

-- ---------------------------------------------------------------------
-- Průnik obor × kraj pro Oborově-regionální report.
-- Populace: subjekty BEZ data zániku v posledním (nebo zadaném) snímku,
-- převažující činnost v sekci p_sekce (klasifikace 80004 = CZ-NACE Rev. 2
-- nebo 80143 = CZ-NACE 2025), sídlo v kraji p_kraj_kod (CZ-NUTS 3).
-- Každé číslo nese příznak pod_prahem (< p_prah subjektů); takové číslo
-- se nepublikuje – pocet_k_publikaci je pak NULL.
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION res.prunik_souhrn(
    p_sekce        text,
    p_kraj_kod     text,
    p_prah         integer DEFAULT 10,
    p_klasifikace  integer DEFAULT 80004,
    p_datum        date    DEFAULT NULL
)
RETURNS TABLE (
    clenitko           text,
    poradi             integer,
    kod                text,
    kategorie          text,
    pocet              bigint,
    pod_prahem         boolean,
    pocet_k_publikaci  bigint
)
LANGUAGE sql
STABLE
AS $$
    WITH p AS (
        SELECT v.*
        FROM res.v_subjekt v
        WHERE v.datum_snimku = coalesce(p_datum, res.posledni_snimek())
          AND NOT v.je_zanikly
          AND v.kraj_kod = p_kraj_kod
          AND CASE p_klasifikace WHEN 80143 THEN v.nace2025_sekce ELSE v.nace_sekce END = p_sekce
    ), c AS (
        SELECT 'celkem'::text AS clenitko, 0 AS poradi, NULL::text AS kod,
               'Subjekty bez zániku'::text AS kategorie, count(*) AS pocet
        FROM p
        UNION ALL
        SELECT 'pravni_forma', 1, p.forma, coalesce(p.forma_nazev, '(mimo číselník)'), count(*)
        FROM p GROUP BY p.forma, p.forma_nazev
        UNION ALL
        SELECT 'kategorie_pracovniku', 2, p.katpo, coalesce(p.katpo_nazev, '(mimo číselník)'), count(*)
        FROM p GROUP BY p.katpo, p.katpo_nazev
        UNION ALL
        SELECT 'rok_vzniku', 3, p.rok_vzniku::text, coalesce(p.rok_vzniku::text, '(neuvedeno)'), count(*)
        FROM p GROUP BY p.rok_vzniku
    )
    SELECT
        c.clenitko, c.poradi, c.kod, c.kategorie, c.pocet,
        c.pocet < p_prah AS pod_prahem,
        CASE WHEN c.pocet < p_prah THEN NULL ELSE c.pocet END AS pocet_k_publikaci
    FROM c
    ORDER BY c.poradi,
             CASE WHEN c.clenitko = 'rok_vzniku' THEN c.kod END,   -- roky chronologicky
             c.pocet DESC, c.kod
$$;

COMMENT ON FUNCTION res.prunik_souhrn(text, text, integer, integer, date) IS
    'Průnik sekce NACE × kraj: celkem, právní forma, kategorie pracovníků, rok vzniku; čísla pod prahem se označí a nepublikují';

CREATE OR REPLACE VIEW res.v_pilot_f_liberecky AS
SELECT * FROM res.prunik_souhrn('F', 'CZ051');

COMMENT ON VIEW res.v_pilot_f_liberecky IS 'Pilot Oborově-regionálního reportu: sekce F (Stavebnictví, CZ-NACE Rev. 2) × Liberecký kraj';
