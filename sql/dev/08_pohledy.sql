-- =====================================================================
-- 08_pohledy.sql – pohodlné čtení historizovaných dat
--
-- *_aktualne  = to, co dnes evidujeme (zaznamenano_do IS NULL)
--               a co dnes platí (platnost obsahuje current_date).
-- dev.subjekt_k_datu(...) = ukázka bitemporálního dotazu:
--               „co platilo k datu X podle toho, co jsme věděli k času Y“.
-- =====================================================================

CREATE OR REPLACE VIEW dev.subjekt_aktualne AS
SELECT
    s.ico,
    v.nazev,
    v.pravni_forma_kod,
    pf.nazev        AS pravni_forma,
    v.stav_kod,
    v.datum_vzniku,
    v.datum_zaniku,
    a.id            AS sidlo_adresa_id,
    a.text_puvodni  AS sidlo_text,
    a.obec          AS sidlo_obec,
    a.psc           AS sidlo_psc
FROM dev.subjekt s
JOIN dev.subjekt_verze v
  ON v.ico = s.ico
 AND v.zaznamenano_do IS NULL
 AND daterange(v.platnost_od, v.platnost_do, '[)') @> current_date
LEFT JOIN dev.ciselnik_pravni_forma pf
  ON pf.kod = v.pravni_forma_kod
LEFT JOIN dev.subjekt_adresa sa
  ON sa.ico = s.ico
 AND sa.typ_adresy_kod = 'SIDLO'
 AND sa.zaznamenano_do IS NULL
 AND daterange(sa.platnost_od, sa.platnost_do, '[)') @> current_date
LEFT JOIN dev.adresa a
  ON a.id = sa.adresa_id;

CREATE OR REPLACE VIEW dev.osoba_aktualne AS
SELECT
    o.id AS osoba_id,
    v.titul_pred,
    v.jmeno,
    v.prijmeni,
    v.titul_za,
    v.datum_narozeni,
    v.statni_prislusnost,
    o.ico
FROM dev.osoba o
JOIN dev.osoba_verze v
  ON v.osoba_id = o.id
 AND v.zaznamenano_do IS NULL
 AND daterange(v.platnost_od, v.platnost_do, '[)') @> current_date;

CREATE OR REPLACE VIEW dev.vazba_aktualne AS
SELECT
    vz.id AS vazba_id,
    vz.ico,
    sf.nazev  AS nazev_subjektu,
    vz.role_kod,
    r.nazev   AS role,
    r.organ,
    CASE WHEN vz.clen_osoba_id IS NOT NULL THEN 'OSOBA' ELSE 'SUBJEKT' END AS typ_clena,
    vz.clen_osoba_id,
    vz.clen_ico,
    coalesce(
        nullif(concat_ws(' ', oa.titul_pred, oa.jmeno, oa.prijmeni, oa.titul_za), ''),
        sc.nazev
    ) AS nazev_clena,
    vz.vklad,
    vz.vklad_mena,
    vz.podil_text,
    vz.podil_procento,
    vz.platnost_od
FROM dev.vazba vz
JOIN dev.ciselnik_role r            ON r.kod = vz.role_kod
LEFT JOIN dev.subjekt_aktualne sf   ON sf.ico = vz.ico
LEFT JOIN dev.osoba_aktualne oa     ON oa.osoba_id = vz.clen_osoba_id
LEFT JOIN dev.subjekt_aktualne sc   ON sc.ico = vz.clen_ico
WHERE vz.zaznamenano_do IS NULL
  AND daterange(vz.platnost_od, vz.platnost_do, '[)') @> current_date;

-- Bitemporální dotaz: údaje subjektů platné k datu p_platnost_k
-- tak, jak byly evidovány v čase p_zaznamenano_k (výchozí = teď).
CREATE OR REPLACE FUNCTION dev.subjekt_k_datu(
    p_platnost_k    date,
    p_zaznamenano_k timestamptz DEFAULT now()
)
RETURNS SETOF dev.subjekt_verze
LANGUAGE sql
STABLE
AS $$
    SELECT *
    FROM dev.subjekt_verze v
    WHERE v.zaznamenano_od <= p_zaznamenano_k
      AND (v.zaznamenano_do IS NULL OR v.zaznamenano_do > p_zaznamenano_k)
      AND daterange(v.platnost_od, v.platnost_do, '[)') @> p_platnost_k
$$;

COMMENT ON FUNCTION dev.subjekt_k_datu(date, timestamptz) IS
    'Verze subjektů platné k datu X podle stavu evidence k času Y';
