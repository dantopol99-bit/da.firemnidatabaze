-- =====================================================================
-- 04_pohledy.sql – rozhraní pro ostatní produkty a kontroly
--
-- obor.v_firma_obor_aktualni  – jeden řádek na IČO: hlavní činnost CZ-NACE 2025
--                               (sekce … podtřída, zdroj, jistota) + kód 2008 jako atribut
-- obor.v_firma_nace_mimo_ciselnik – kódy firem, které nejsou v číselníku své verze
-- =====================================================================

-- ---------------------------------------------------------------------
-- Poslední známá hlavní činnost. Pořadí: kód 2025 z RES, jinak odvozený.
-- Zaniklé subjekty jsou v pohledu taky (platnost_do vyplněno); pro živé
-- subjekty filtruj platnost_do IS NULL.
-- U odvozeného kódu má každá úroveň vlastní jistotu; kod_2025 je
-- nejpodrobnější úroveň, kterou se podařilo určit.
-- Spojení s parlamentní a aktérskou analytikou: sloupec oddil (2 místa, CZ-NACE 2025).
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW obor.v_firma_obor_aktualni AS
WITH res25 AS (
    SELECT DISTINCT ON (ico) ico, kod, platnost_od, platnost_do
    FROM obor.firma_nace
    WHERE verze = 2025 AND typ = 'hlavni' AND zdroj = 'RES'
    ORDER BY ico, platnost_od DESC NULLS LAST, id DESC
),
res08 AS (
    SELECT DISTINCT ON (ico) ico, kod, platnost_od, platnost_do
    FROM obor.firma_nace
    WHERE verze = 2008 AND typ = 'hlavni' AND zdroj = 'RES'
    ORDER BY ico, platnost_od DESC NULLS LAST, id DESC
),
odv_posledni AS (
    SELECT DISTINCT ON (ico) ico, platnost_od, odvozeno_z
    FROM obor.firma_nace
    WHERE verze = 2025 AND typ = 'hlavni' AND zdroj = 'odvozeno'
    ORDER BY ico, platnost_od DESC NULLS LAST, id DESC
),
odv AS (
    SELECT
        f.ico, f.odvozeno_z, min(f.platnost_od) AS platnost_od, max(f.platnost_do) AS platnost_do,
        max(f.kod) FILTER (WHERE f.uroven = 1)     AS sekce,
        max(f.kod) FILTER (WHERE f.uroven = 2)     AS oddil,
        max(f.kod) FILTER (WHERE f.uroven = 3)     AS skupina,
        max(f.kod) FILTER (WHERE f.uroven = 4)     AS trida,
        max(f.kod) FILTER (WHERE f.uroven = 5)     AS podtrida,
        max(f.jistota) FILTER (WHERE f.uroven = 1) AS jistota_sekce,
        max(f.jistota) FILTER (WHERE f.uroven = 2) AS jistota_oddil,
        -- nejpodrobnější odvozená úroveň = úroveň zdrojového kódu 2008
        (array_agg(f.kandidati ORDER BY f.uroven DESC))[1]                     AS kandidati_zdroje,
        coalesce((array_agg(f.priznak ORDER BY f.uroven DESC))[1] = 'nejednoznacne', false) AS nejednoznacne,
        jsonb_object_agg(f.uroven, f.jistota)       AS jistoty
    FROM obor.firma_nace f
    JOIN odv_posledni p ON p.ico = f.ico AND p.platnost_od IS NOT DISTINCT FROM f.platnost_od
    WHERE f.verze = 2025 AND f.typ = 'hlavni' AND f.zdroj = 'odvozeno'
    GROUP BY f.ico, f.odvozeno_z
),
icos AS (
    SELECT ico FROM res25 UNION SELECT ico FROM res08 UNION SELECT ico FROM odv
)
SELECT
    i.ico,
    CASE WHEN r.ico IS NOT NULL THEN 'RES' WHEN o.ico IS NOT NULL THEN 'odvozeno' END       AS zdroj,
    coalesce(c.sekce,   o.sekce)                                                           AS sekce,
    coalesce(c.oddil,   o.oddil)                                                           AS oddil,
    coalesce(c.skupina, o.skupina)                                                         AS skupina,
    coalesce(c.trida,   o.trida)                                                           AS trida,
    CASE WHEN r.ico IS NOT NULL THEN CASE WHEN c.uroven = 5 THEN c.kod END ELSE o.podtrida END AS podtrida,
    coalesce(r.kod, o.podtrida, o.trida, o.skupina, o.oddil, o.sekce)                      AS kod_2025,
    coalesce(c.uroven, CASE WHEN o.podtrida IS NOT NULL THEN 5 WHEN o.trida IS NOT NULL THEN 4
                            WHEN o.skupina IS NOT NULL THEN 3 WHEN o.oddil IS NOT NULL THEN 2
                            WHEN o.sekce IS NOT NULL THEN 1 END)                           AS uroven_2025,
    CASE WHEN r.ico IS NOT NULL THEN 1.0
         ELSE (o.jistoty ->> CASE WHEN o.podtrida IS NOT NULL THEN '5' WHEN o.trida IS NOT NULL THEN '4'
                                  WHEN o.skupina IS NOT NULL THEN '3' WHEN o.oddil IS NOT NULL THEN '2'
                                  ELSE '1' END)::numeric END                               AS jistota,
    CASE WHEN r.ico IS NOT NULL THEN CASE WHEN c.oddil IS NOT NULL THEN 1.0 END
         ELSE o.jistota_oddil END                                                          AS jistota_oddil,
    CASE WHEN r.ico IS NOT NULL THEN 1.0 ELSE o.jistota_sekce END                          AS jistota_sekce,
    CASE WHEN r.ico IS NULL AND o.nejednoznacne THEN 'nejednoznacne' END                   AS priznak,
    CASE WHEN r.ico IS NULL AND o.nejednoznacne THEN o.kandidati_zdroje END                AS kandidati,
    coalesce(c.je_pseudokod, c_odv.je_pseudokod, false)                                    AS je_pseudokod,
    s08.kod                                                                                AS kod_2008,
    c08.sekce                                                                              AS sekce_2008,
    c08.oddil                                                                              AS oddil_2008,
    coalesce(r.platnost_od, o.platnost_od, s08.platnost_od)                                AS platnost_od,
    CASE WHEN r.ico IS NOT NULL THEN r.platnost_do
         WHEN o.ico IS NOT NULL THEN o.platnost_do ELSE s08.platnost_do END                AS platnost_do
FROM icos i
LEFT JOIN res25 r ON r.ico = i.ico
LEFT JOIN obor.nace_ciselnik c ON c.verze = 2025 AND c.kod = r.kod
LEFT JOIN odv o ON o.ico = i.ico AND r.ico IS NULL
LEFT JOIN obor.nace_ciselnik c_odv ON c_odv.verze = 2025 AND c_odv.kod = o.sekce
LEFT JOIN res08 s08 ON s08.ico = i.ico
LEFT JOIN obor.nace_ciselnik c08 ON c08.verze = 2008 AND c08.kod = s08.kod;

COMMENT ON VIEW obor.v_firma_obor_aktualni IS
    'Rozhraní pro ostatní produkty: jeden řádek na IČO, hlavní činnost CZ-NACE 2025 (sekce–podtřída, zdroj, jistota) a kód 2008 jako atribut';

-- ---------------------------------------------------------------------
-- Kontrola: kódy firem, které nejsou v číselníku své verze (má být prázdné).
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW obor.v_firma_nace_mimo_ciselnik AS
SELECT f.verze, f.zdroj, f.typ, f.kod, count(*) AS pocet
FROM obor.firma_nace f
LEFT JOIN obor.nace_ciselnik c ON c.verze = f.verze AND c.kod = f.kod
WHERE f.kod IS NOT NULL AND c.kod IS NULL
GROUP BY f.verze, f.zdroj, f.typ, f.kod;

COMMENT ON VIEW obor.v_firma_nace_mimo_ciselnik IS 'Kontrola: kódy ve firma_nace, které nejsou v číselníku své verze (má být prázdné)';
