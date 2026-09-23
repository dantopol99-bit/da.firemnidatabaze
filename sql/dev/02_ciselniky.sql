-- =====================================================================
-- 02_ciselniky.sql – číselníky (seznamy povolených kódů)
--
-- Rozsah: vazby a role pouze na úrovni obchodního rejstříku.
-- Koncoví (skuteční) majitelé nejsou součástí produktu – evidence
-- skutečných majitelů není od 17. 12. 2025 veřejná. Číselník rolí proto
-- obsahuje jen role zapisované do obchodního rejstříku.
-- =====================================================================

-- Právní formy (kódy ČSÚ). Úplný číselník se později načte ze zdroje,
-- zde je jen základ pro vývoj a testy.
CREATE TABLE IF NOT EXISTS dev.ciselnik_pravni_forma (
    kod    text PRIMARY KEY,
    nazev  text NOT NULL
);

INSERT INTO dev.ciselnik_pravni_forma (kod, nazev) VALUES
    ('101', 'Fyzická osoba podnikající dle živnostenského zákona'),
    ('111', 'Veřejná obchodní společnost'),
    ('112', 'Společnost s ručením omezeným'),
    ('113', 'Společnost komanditní'),
    ('121', 'Akciová společnost'),
    ('205', 'Družstvo')
ON CONFLICT (kod) DO NOTHING;

-- Stav subjektu
CREATE TABLE IF NOT EXISTS dev.ciselnik_stav_subjektu (
    kod    text PRIMARY KEY,
    nazev  text NOT NULL
);

INSERT INTO dev.ciselnik_stav_subjektu (kod, nazev) VALUES
    ('AKTIVNI',    'Aktivní'),
    ('LIKVIDACE',  'V likvidaci'),
    ('INSOLVENCE', 'V insolvenčním řízení'),
    ('ZANIKLY',    'Zaniklý')
ON CONFLICT (kod) DO NOTHING;

-- Typ adresy subjektu
CREATE TABLE IF NOT EXISTS dev.ciselnik_typ_adresy (
    kod    text PRIMARY KEY,
    nazev  text NOT NULL
);

INSERT INTO dev.ciselnik_typ_adresy (kod, nazev) VALUES
    ('SIDLO',       'Sídlo'),
    ('PROVOZOVNA',  'Provozovna'),
    ('DORUCOVACI',  'Doručovací adresa')
ON CONFLICT (kod) DO NOTHING;

-- Role ve vazbě (jen role zapisované v obchodním rejstříku)
CREATE TABLE IF NOT EXISTS dev.ciselnik_role (
    kod    text PRIMARY KEY,
    nazev  text NOT NULL,
    organ  text NOT NULL   -- orgán / skupina, do které role patří
);

INSERT INTO dev.ciselnik_role (kod, nazev, organ) VALUES
    ('JEDNATEL',                  'Jednatel',                     'STATUTARNI_ORGAN'),
    ('PREDSEDA_PREDSTAVENSTVA',   'Předseda představenstva',      'STATUTARNI_ORGAN'),
    ('CLEN_PREDSTAVENSTVA',       'Člen představenstva',          'STATUTARNI_ORGAN'),
    ('CLEN_SPRAVNI_RADY',         'Člen správní rady',            'STATUTARNI_ORGAN'),
    ('KOMPLEMENTAR',              'Komplementář',                 'STATUTARNI_ORGAN'),
    ('PREDSEDA_DOZORCI_RADY',     'Předseda dozorčí rady',        'DOZORCI_RADA'),
    ('CLEN_DOZORCI_RADY',         'Člen dozorčí rady',            'DOZORCI_RADA'),
    ('PROKURISTA',                'Prokurista',                   'PROKURA'),
    ('LIKVIDATOR',                'Likvidátor',                   'LIKVIDACE'),
    ('SPOLECNIK',                 'Společník',                    'SPOLECNICI'),
    ('KOMANDITISTA',              'Komanditista',                 'SPOLECNICI'),
    ('JEDINY_AKCIONAR',           'Jediný akcionář',              'SPOLECNICI')
ON CONFLICT (kod) DO NOTHING;
