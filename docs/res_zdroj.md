# Registr ekonomických subjektů ČSÚ (RES) jako zdroj Oborově-regionálního reportu

Stav: **implementováno a načteno** (schéma `res`, `res_import.py`), snímek k **15. 9. 2026**.
Všechna čísla v tomto dokumentu pocházejí z tohoto snímku, z číselníků ČSÚ platných k 15. 9. 2026
a z agregátů ČSÚ stažených 29. 9. 2026. Po dalším importu je vypíše
`python -m firemni_databaze.res_import prehled`.

## 1. Co zdroj je

Registr ekonomických subjektů vede ČSÚ podle § 20 zákona č. 89/1995 Sb., o státní statistické
službě. Obsahuje všechny ekonomické subjekty se sídlem v ČR: právnické osoby, podnikající fyzické
osoby a organizační složky státu, které jsou účetní jednotkou. Primárně slouží jako opora výběru pro
statistická šetření. **Zápis do RES má jen evidenční význam** a údaje z RES nemohou sloužit jako
doklad ve správním ani jiném řízení.

Otevřená data jsou produkt ČSÚ **140134-26**
([stránka produktu](https://csu.gov.cz/produkty/registr-ekonomickych-subjektu-otevrena-data),
[dokumentace](https://csu.gov.cz/statistika/registr-ekonomickych-subjektu-otevrena-data-dokumentace)):

| soubor | obsah | řádků (15. 9. 2026) | velikost | SHA-256 |
|---|---|---:|---:|---|
| [`res_data.csv`](https://opendata.csu.gov.cz/soubory/od/od_org03/res_data.csv) | seznam ekonomických subjektů, 1 řádek na IČO | 3 528 951 | 543 309 993 B | `c6b6031d0598ce95117de7980c5f52d1d8675b49f92ddbb72f80e201d5dc4fdc` |
| [`res_pf_nace.csv`](https://opendata.csu.gov.cz/soubory/od/od_org03/res_pf_nace.csv) | všechny činnosti (a výjimečně právní formy) subjektu podle zdroje údaje | 22 263 363 | 1 049 777 357 B | `6668d835a12b1521dd3920a4b511aa2f3a9226ff62c716bc0190176f1f789c10` |
| `res_data-metadata.json`, `res_pf_nace-metadata.json` | schéma CSVW (sloupce, typy, popisy) | – | 4 224 / 1 561 B | uloženo v `res.snimek.metadata` |

Soubory byly na serveru naposledy změněny 17. 9. 2026 (HTTP `Last-Modified`), metadata 9. 1. 2026.
CSV je v UTF-8 bez BOM, řádky končí CRLF, oddělovač je čárka a texty `FIRMA` a `TEXTADR` jsou
v uvozovkách (i prázdné, tj. `""`). Surové soubory se do repozitáře neukládají. Importér je stáhne
do dočasné složky a po načtení smaže. Původ každého souboru (URL, SHA-256, počet řádků, čas
importu, dávka) je v `res.snimek`.

## 2. Podmínky užití

- Statistické informace ČSÚ jsou licencovány **CC BY 4.0**
  ([podmínky ČSÚ](https://csu.gov.cz/podminky_pro_vyuzivani_a_dalsi_zverejnovani_statistickych_udaju_csu)).
  Při šíření je nutné uvést podmínky licence, nejlépe odkazem na uvedenou stránku.
- **Upravené nebo odvozené údaje musí být jako upravené/odvozené označeny a nesmí se prezentovat
  jako nezměněné oficiální statistiky ČSÚ.** Všechny počty v reportu (průniky obor × území) jsou
  odvozené, proto je report musí takto označit, např. „Zdroj: ČSÚ, Registr ekonomických subjektů,
  stav k 15. 9. 2026; vlastní výpočet“.
- `FIRMA` je u fyzických osob **jméno a příjmení podnikatele** a sídlo je často adresa bydliště.
  Jde o osobní údaje. Report proto pracuje jen s agregáty a s prahem 10 subjektů (viz kap. 10).

## 3. Frekvence a aktualizace

- RES se aktualizuje 2× měsíčně. Snímek zachycuje stav k 15. dni a k poslednímu dni měsíce a vychází
  „několik dní poté“ (snímek k 15. 9. 2026 vyšel 17. 9.). Datum snímku nese sloupec `DATPLAT`,
  v celém souboru je stejné.
- `PRIZNAK` označuje změnu proti **předchozímu snímku**: `Z` = změna (14 618 řádků), `P` = přírůstek
  (6 722). Historie jednoho subjektu se tedy získá jen řadou snímků. Schéma `res` je na ni připravené
  (klíč IČO + datum snímku), zatím je načtený jen jeden snímek.
- Od 1. 1. 2026 RES kóduje činnost dvakrát: `NACE` (CZ-NACE, Rev. 2) a `NACE2025` (CZ-NACE 2025,
  Rev. 2.1). Dvojí kódování ČSÚ ukončí 31. 12. 2028. Hromadné překódování je vidět na `DDATPAKT`:
  2,61 mil. subjektů bez zániku má datum aktualizace v lednu 2026.
- Opakovaný import téhož souboru importér přeskočí (stejný SHA-256). Jiný soubor ke stejnému datu
  odmítne, protože snímky se nepřepisují.

## 4. Mapování sloupců a odpovědi na otázky ze zadání

Každý sloupec souboru má v `res.subjekt` / `res.pf_nace` sloupec se stejným jménem (malými písmeny)
a **stejným významem**. Při načtení se provádějí jen dvě úpravy: prázdná hodnota (i `""`) = `NULL`
a sloupce s `datatype: date` v metadatech mají typ `date`. Kódy zůstávají text, protože úvodní nuly
a délka kódu NACE nesou význam. Klíč `(ico, datum_snimku)` je unikátní a `datum_snimku = DATPLAT`.

### Klíčové údaje pro report

| otázka | sloupec | číselník ČSÚ | jak ho používáme |
|---|---|---|---|
| **převažující činnost** | `NACE` = „Převažující činnost (statistická)“ | klasifikace **80004** (CZ-NACE Rev. 2), rozšířená pro RES: [`CZ_NACE_RES`](https://vdb.czso.cz/opendata/ciselniky/polozky?kod=CZ_NACE_RES) | sekce/oddíl/skupina/třída z hierarchie číselníku (`res.cis_nace`) |
| | `NACE2025` | klasifikace **80143** (CZ-NACE 2025): `CZ_NACE_RES2025` | totéž, `klasifikace = 80143` |
| **kategorie počtu pracovníků** | `KATPO` | **579** (KATPOECD): 000 Neuvedeno, 110 Bez zaměstnanců, 120 1–5, 130 6–9, 210 10–19, 220 20–24, 230 25–49, 240 50–99, 310 100–199 … 510 10 000+ | `res.cis_katpo` |
| **územní kód sídla** | `OKRESLAU` = kód okresu sídla (CZ-NUTS/LAU 1, např. `CZ0513` Liberec) | **109** (OKRES_LAU) | `res.cis_okres` |
| **→ kraj** | – | oficiální **vazba číselníků 109 → 108** (CZ-NUTS 3) | `res.cis_okres.kraj_kod` → `res.cis_kraj`; kraj **neodvozujeme z prefixu** kódu |
| | (pro porovnání s ARES) | číselník **100** (Kraj) nese k NUTS 3 i kód RÚIAN (`CZ051` = 3077 = RÚIAN 78) | `res.cis_kraj.kod_ruian` |
| jemnější území | `ICZUJ` = základní územní jednotka sídla (obec, v Praze/Brně… městská část) | 51 | nenačteno (kap. 11) |
| **datum vzniku** | `DDATVZN` | – | `date` |
| **datum zániku** | `DDATZAN` (+ `ZPZAN` způsob zániku) | 572 | vyplněné `DDATZAN` = zaniklý subjekt |
| **právní forma** | `FORMA` = právní forma statistická | **56** | `res.cis_pravni_forma` (`ciselnik = 56`) – pro report |
| | `ROSFORMA` = právní forma podle registru osob | **149** | `res.cis_pravni_forma` (`ciselnik = 149`); u FO jiné kódy (100 místo 101/105/107) |

Pseudokódy RES v CZ-NACE, které nejsou ekonomickou činností: sekce **Y / oddíl 00** („Výroba, obchod
a služby neuvedené v přílohách 1 až 3 živnostenského zákona“, v praxi volná živnost bez určení oboru)
a **X / 04** („nezjištěno“). ČSÚ oba ve svých tabulkách vykazuje jako „X Nezjištěno“.
Kód `NACE` může být na libovolné úrovni: písmeno sekce (`G`), oddíl (`46`), skupina (`461`), třída
(`4120`) nebo národní podtřída (`41201`). Do sekce jde zařadit každý.

### Všechny sloupce `res_data.csv` → `res.subjekt`

| sloupec | význam (metadata ČSÚ) | číselník | typ | vyplněno u subjektů bez zániku |
|---|---|---|---|---|
| `ICO` | identifikační číslo | – | text, 8 číslic | 100 % |
| `OKRESLAU` | kód okresu sídla (CZ-NUTS) | 109 | text | 100 % |
| `DDATVZN` | datum vzniku | – | date | 100 % |
| `DDATZAN` | datum zániku | – | date | 0 % (definice) |
| `ZPZAN` | způsob zániku | 572 | text | – |
| `DDATPAKT` | datum aktualizace | – | date | 100 % |
| `FORMA` | právní forma (statistická) | 56 | text | 100 % |
| `ROSFORMA` | právní forma (registr osob) | 149 | text | 99,97 % |
| `KATPO` | kategorie dle počtu pracovníků | 579 | text | 100 %, z toho 50,7 % „000 Neuvedeno“ |
| `NACE` | převažující činnost (statistická) | 80004 | text | 100 %, z toho 4,2 % pseudokód `00` |
| `NACE2025` | převažující činnost (statistická) | 80143 | text | 100 % |
| `ICZUJ` | základní územní jednotka sídla | 51 | text | 100 % |
| `FIRMA` | firma, název (jméno) | – | text | 100 % |
| `CISS2010` | institucionální sektor ESA 2010 | 5161 | text | 100 % |
| `KODADM` | kód adresního místa RÚIAN | – | text | 99,1 % |
| `TEXTADR` | text adresy (jen bez `KODADM`) | – | text | – |
| `PSC`, `OBEC_TEXT`, `COBCE_TEXT`, `ULICE_TEXT`, `TYPCDOM`, `CDOM`, `COR` | adresa sídla podle `KODADM` | 73 (`TYPCDOM`) | text | podle adresy |
| `DATPLAT` | datum platnosti dat (= datum snímku) | – | date | 100 % |
| `PRIZNAK` | změna proti minulému snímku (`P`/`Z`) | – | text | 0,7 % |

### `res_pf_nace.csv` → `res.pf_nace`

`ICO`, `ZDRUD` (zdroj údaje, číselník 564, např. 411 živnostenský rejstřík, 401 rejstříkový soud),
`KODCIS` (80004 / 80143 / **56**), `HODN` (kód v číselníku `KODCIS`), `DATPLAT`, `DDATPAKT`, `PRIZNAK`.
Jeden subjekt má v průměru 3,1 činnosti CZ-NACE. Zaniklé subjekty mají jediný řádek bez `KODCIS`
a `HODN` (497 410 řádků). Klíč `(ico, datum_snimku, kodcis, zdrud, hodn)` je unikátní
(`UNIQUE NULLS NOT DISTINCT`). Metadata tohoto souboru uvádějí v poli `url` jméno `pf_nace_5000.csv`,
které neodpovídá skutečnému jménu souboru. Kontrolujeme proto sloupce, ne `url`.

## 5. Schéma `res`

| objekt | obsah |
|---|---|
| `res.snimek` | soubor snímku: datum, soubor, URL, SHA-256, velikost, `Last-Modified`, počet řádků, CSVW metadata, čas importu, `dev.import_davka` |
| `res.subjekt`, `res.pf_nace` | obsah souborů beze změny významu; neměnné (triggery zakazují UPDATE/DELETE/TRUNCATE) |
| `res.cis_nace` | CZ-NACE 80004 a 80143 pro RES se sekcí, oddílem, skupinou, třídou a příznakem pseudokódu |
| `res.cis_kraj`, `res.cis_okres` | kraje (číselník 100: NUTS 3, kód ČSÚ, kód RÚIAN) a okresy (109) s krajem podle vazby 109 → 108 |
| `res.cis_pravni_forma`, `res.cis_katpo`, `res.cis_zpusob_zaniku`, `res.cis_zdroj_udaje` | číselníky 56 + 149, 579, 572, 564 |
| `res.cis_zdroj` | odkud a kdy se který číselník načetl (URL exportu, SHA-256, dávka) |
| `res.kvalita` | metriky kvality snímku (kap. 6), zapisuje je importér |
| `res.csu_agregat` | publikované počty ČSÚ z DataStatu (kap. 7) |
| `res.v_subjekt` | snímek s výklady: sekce/oddíl NACE, okres, kraj, názvy právní formy a KATPO |
| `res.v_kvalita`, `res.v_pocty_kraj_sekce`, `res.v_srovnani_csu` | kvalita, kraj × sekce, srovnání s ČSÚ |
| `res.v_jadro_kontrola`, `res.v_jadro_kontrola_souhrn` | jádro (ARES) proti RES, **jen čtení** |
| `res.prunik_souhrn(sekce, kraj, prah, klasifikace, datum)` | průnik obor × kraj s prahem; `res.v_pilot_f_liberecky` |

Importy se evidují v `dev.import_davka`: zdroj `RES` (snímek), `CSU-CISELNIKY` a `CSU-DATASTAT`.
Snímek se načítá takto: `COPY … FROM STDIN (FORMAT csv, HEADER match, FORCE_NULL …)` do dočasné
tabulky → kontrola, že COPY načetl přesně tolik řádků, kolik napočítal nezávislý CSV parser, a že je
v souboru jediné `DATPLAT` → `INSERT` do cílové tabulky. Oba soubory jdou v jedné transakci. Hlavička
souboru i CSVW metadata se kontrolují proti očekávaným sloupcům a typům. Když ČSÚ strukturu změní,
import skončí chybou a schéma je nutné upravit vědomě. Import snímku z lokálních souborů trvá asi 6 minut, stažení 1,6 GB dalších ~20 minut (rychlost serveru ČSÚ ~0,85 MB/s).
V PostgreSQL zabírá `res.subjekt` 740 MB a `res.pf_nace` 2,8 GB.

## 6. Kvalita zdroje (snímek k 15. 9. 2026)

| ukazatel | všechny řádky | % | bez zániku | % | se zánikem | % |
|---|---:|---:|---:|---:|---:|---:|
| **řádků celkem** | **3 528 951** | 100 | **2 947 143** | 83,51 | **581 808** | 16,49 |
| zaniklé jen s IČO a datem zániku (FO, GDPR) | 497 410 | 14,10 | 0 | 0 | 497 410 | 85,49 |
| NACE prázdné | 497 410 | 14,10 | 0 | 0,00 | 497 410 | 85,49 |
| NACE = pseudokód (`00`) | 123 777 | 3,51 | 122 453 | 4,16 | 1 324 | 0,23 |
| NACE mimo číselník | 0 | 0 | 0 | 0 | 0 | 0 |
| **bez NACE sekce A–U** (prázdné + pseudokód) | 621 187 | **17,60** | 122 453 | **4,16** | 498 734 | 85,72 |
| NACE2025 prázdné | 543 968 | 15,41 | 0 | 0 | 543 968 | 93,50 |
| **bez územního kódu** (`OKRESLAU` prázdný) | 497 410 | **14,10** | 0 | **0,00** | 497 410 | 85,49 |
| `OKRESLAU` mimo číselník 109 | 0 | 0 | 0 | 0 | 0 | 0 |
| KATPO prázdné | 497 410 | 14,10 | 0 | 0 | 497 410 | 85,49 |
| KATPO = 000 Neuvedeno | 1 574 698 | 44,62 | 1 494 282 | 50,70 | 80 416 | 13,82 |
| **bez kategorie pracovníků** (prázdné + 000) | 2 072 108 | **58,72** | 1 494 282 | **50,70** | 577 826 | 99,32 |
| právní forma / datum vzniku prázdné | 497 410 | 14,10 | 0 | 0 | 497 410 | 85,49 |
| kód adresního místa (`KODADM`) prázdný | 530 213 | 15,02 | 25 889 | 0,88 | 504 324 | 86,68 |

**Práh 20 % (NACE nebo území u subjektů bez zániku) nebyl překročen**: bez NACE sekce 4,16 %,
bez území 0,00 %. Všechny chybějící údaje u zaniklých subjektů jsou zaniklé FO, u nichž ČSÚ podle
GDPR smí zveřejnit jen IČO a datum zániku. Kategorie pracovníků je slabá: „000 Neuvedeno“ má
polovina subjektů bez zániku. U PO se navíc kategorie 110 „Bez zaměstnanců“ prakticky nepoužívá
(13 PO proti 1 030 653 FO) a „000“ tam znamená hlavně „nejsou hlášení zaměstnanci“ (62 % PO).
KATPO tedy nejde číst stejně napříč právními formami.

Importér práh hlídá sám: překročí-li „bez NACE sekce“ nebo „bez kraje“ u subjektů bez zániku
20 %, skončí kódem 3 a vypíše důvod.

## 7. Kontrola proti ČSÚ

**Metoda.** ČSÚ publikuje z RES „počet ekonomických subjektů“ = subjekty **bez data zániku**
evidované v RES ke konci čtvrtletí, územně podle sídla
([metodika](https://csu.gov.cz/statistiky-z-registru-ekonomickych-subjektu-metodika)). Srovnáváme
s veřejnou databází ČSÚ (DataStat), výběr
[**RES02QT1**](https://data.csu.gov.cz/api/dotaz/v1/data/vybery/RES02QT1?format=CSV&rozsah=CELY_VYBER&kodCiselniku=true) „Ekonomické subjekty podle převažující
činnosti CZ-NACE – data za ČR a kraje“, poslední čtvrtletí **2Q 2026 (stav k 30. 6. 2026)**.
Pohled `res.v_srovnani_csu` ukazuje dvě naše čísla:

- `nase_bez_zaniku`: subjekty bez zániku ve snímku k 15. 9. 2026 (definice ČSÚ, jiné datum),
- `nase_k_datu_csu`: rekonstrukce stavu k 30. 6. 2026 ze snímku (vznik ≤ 30. 6. a bez zániku nebo
  zánik po 30. 6.). Zaniklé FO bez atributů do ní zařadit nejde a změny zařazení po 30. 6. se
  nevrací.

**Registrované ≠ aktivní.** RES02QT1 má i ukazatel „se zjištěnou aktivitou“: subjekt platí daň
z příjmů nebo DPH, případně pojistné za zaměstnance nebo jako OSVČ. Ten otevřená data RES
**neobsahují**. K 30. 6. 2026 bylo registrovaných subjektů 2 930 465, ale se zjištěnou aktivitou
jen **1 789 008 (61,0 %)**. Report z otevřených dat tedy počítá **registrované** subjekty, přibližně
o 40 % víc, než kolik jich skutečně vykazuje činnost. Podíl aktivních kolísá podle kraje (53 % KVK,
65 % VYS) i podle odvětví (34 % u X, 51 % S, 52 % G, 87 % Q) a do reportu patří jako kontext.

### Po krajích (subjekty bez zániku)

| kraj | RES 15. 9. 2026 | ČSÚ 30. 6. 2026 | rozdíl | % | RES rekonstr. k 30. 6. | % | ČSÚ aktivní | % aktivních |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Česko** | **2 947 143** | **2 930 465** | +16 678 | +0,57 | 2 924 866 | −0,19 | 1 789 008 | 61,0 |
| Hlavní město Praha | 710 086 | 705 215 | +4 871 | +0,69 | 704 384 | −0,12 | 437 984 | 62,1 |
| Středočeský | 362 043 | 359 485 | +2 558 | +0,71 | 359 113 | −0,10 | 225 003 | 62,6 |
| Jihočeský | 158 992 | 158 201 | +791 | +0,50 | 157 894 | −0,19 | 95 695 | 60,5 |
| Plzeňský | 142 116 | 141 427 | +689 | +0,49 | 141 173 | −0,18 | 81 742 | 57,8 |
| Karlovarský | 68 873 | 68 758 | +115 | +0,17 | 68 514 | −0,35 | 36 530 | 53,1 |
| Ústecký | 169 044 | 168 168 | +876 | +0,52 | 167 701 | −0,28 | 94 300 | 56,1 |
| Liberecký | 107 418 | 107 008 | +410 | +0,38 | 106 747 | −0,24 | 63 237 | 59,1 |
| Královéhradecký | 131 212 | 130 620 | +592 | +0,45 | 130 351 | −0,21 | 81 492 | 62,4 |
| Pardubický | 119 651 | 119 135 | +516 | +0,43 | 118 798 | −0,28 | 73 993 | 62,1 |
| Vysočina | 110 782 | 110 304 | +478 | +0,43 | 109 990 | −0,28 | 71 286 | 64,6 |
| Jihomoravský | 335 043 | 332 933 | +2 110 | +0,63 | 332 427 | −0,15 | 206 726 | 62,1 |
| Olomoucký | 139 609 | 138 961 | +648 | +0,47 | 138 575 | −0,28 | 83 073 | 59,8 |
| Zlínský | 136 179 | 135 496 | +683 | +0,50 | 135 171 | −0,24 | 83 963 | 62,0 |
| Moravskoslezský | 256 095 | 254 754 | +1 341 | +0,53 | 254 028 | −0,28 | 153 984 | 60,4 |

Kraje sedí. Snímek je o 0,2–0,7 % nad ČSÚ, což odpovídá čistému přírůstku za 2,5 měsíce
(ČSÚ: +17,8 tis. za 2Q 2026). Rekonstrukce k 30. 6. je o 0,1–0,35 % pod ČSÚ. Chybějí v ní FO
zaniklé mezi 1. 7. a 15. 9., jejichž okres snímek neuvádí.

### Po sekcích CZ-NACE (ČR)

ČSÚ publikuje průmysl jen souhrnně (**B–E**) a pseudokódy RES jako **X Nezjištěno**. Sekce B, C, D
a E zvlášť nepublikuje v žádné tabulce RES (čtvrtletní ani roční, za kraje ani obce), takže je nelze
porovnat jednotlivě. Naše počty 21 sekcí: A 140 367, **B 914, C 324 442, D 20 108, E 10 852**,
F 339 922, G 450 410, H 111 625, I 143 227, J 103 503, K 44 558, L 205 945, M 379 419, N 82 206,
O 15 692, P 66 747, Q 35 503, R 90 528, S 258 662, T 0, U 60; pseudokód 00: 122 453.

| odvětví | RES 15. 9. | ČSÚ 30. 6. | % | rekonstr. % | % aktivních |
|---|---:|---:|---:|---:|---:|
| A Zemědělství, lesnictví, rybářství | 140 367 | 140 807 | −0,31 | −0,81 | 66,8 |
| B–E Průmysl | 356 316 | 355 992 | +0,09 | −0,70 | 67,0 |
| F Stavebnictví | 339 922 | 343 314 | −0,99 | −2,01 | 64,6 |
| G Obchod; opravy motorových vozidel | 450 410 | 428 112 | **+5,21** | +4,90 | 52,2 |
| H Doprava a skladování | 111 625 | 109 373 | +2,06 | +0,12 | 62,1 |
| I Ubytování, stravování | 143 227 | 142 153 | +0,76 | +0,33 | 56,6 |
| J Informační a komunikační činnosti | 103 503 | 103 987 | −0,47 | −1,68 | 72,6 |
| K Peněžnictví a pojišťovnictví | 44 558 | 48 766 | **−8,63** | −9,17 | 85,6 |
| L Nemovitosti | 205 945 | 200 048 | +2,95 | +2,82 | 58,9 |
| M Profesní, vědecké, technické | 379 419 | 381 377 | −0,51 | −1,08 | 67,7 |
| N Administrativní a podpůrné | 82 206 | 87 675 | **−6,24** | −7,15 | 62,6 |
| O Veřejná správa | 15 692 | 15 714 | −0,14 | −0,14 | 71,0 |
| P Vzdělávání | 66 747 | 66 656 | +0,14 | −0,96 | 68,8 |
| Q Zdravotní a sociální péče | 35 503 | 36 943 | −3,90 | −4,33 | 87,1 |
| R Kultura, zábava, rekreace | 90 528 | 91 687 | −1,26 | −2,15 | 58,4 |
| S Ostatní činnosti | 258 662 | 258 373 | +0,11 | −0,41 | 50,9 |
| T Domácnosti jako zaměstnavatelé | 0 | 0 | – | – | – |
| U Exteritoriální organizace | 60 | 61 | −1,64 | −1,64 | 67,2 |
| X Nezjištěno (pseudokód 00) | 122 453 | 119 427 | +2,53 | −0,31 | 33,6 |

Za ČR **žádná sekce nepřekračuje 10 %**. Největší rozdíly mají K (−8,6 %), N (−6,2 %) a G (+5,2 %).

### Kraj × sekce: 22 z 266 buněk nad 10 %

| odvětví | kraje s rozdílem nad 10 % (RES proti ČSÚ) |
|---|---|
| **X Nezjištěno** (10 buněk) | MSK −33 %, ZLK −31 %, OLK −21 %, JHM −18 %; Praha +30 %, STČ +22 %, PAK +18 %, PLK +14 %, LBK +12 %, HKK +11 % |
| **G Obchod** (4) | MSK +18,6 %, OLK +12,7 %, ZLK +11,5 %, JHM +10,7 % |
| **J Informace a komunikace** (3) | MSK +25 %, OLK +18 %, JHM +12 % |
| **K Finance** (5) | JHČ −12,7 %, VYS −11,7 %, JHM −10,8 %, OLK −10,3 %, ZLK −10,0 % |

**Vysvětlení, co víme a co ne:**

1. **Čas to nevysvětluje.** Časová řada ČSÚ je hladká (G v ČR klesá o 2–6 tis. za čtvrtletí,
   X v MSK se od roku 2024 drží mezi 13,7 a 15,1 tis.), rozdíly zůstávají i v rekonstrukci k 30. 6. a `DDATPAKT`
   nevykazuje po 30. 6. hromadné změny (v MSK sekci G jen ~960 aktualizací od července).
2. **Převod Rev. 2 ↔ 2025 to také nevysvětluje.** Stejné srovnání pro `NACE2025` proti tabulce
   ČSÚ pro CZ-NACE 2025 (RES02QNACET1) dává stejný vzor: G +6,0 %, finance −8,6 %, administrativa
   −6,1 %.
3. **Nejpravděpodobnější příčinou jsou subjekty zařazené jen na úroveň sekce.** 45 001 subjektů má
   `NACE = 'G'` a 12 282 `NACE = 'J'` (jen písmeno, ze živnostenského rejstříku, ZDRUD 411, hromadně
   aktualizováno v lednu 2026). Jsou silně soustředěné na Moravě: v MSK je 24 % všech `G` proti
   8,7 % podílu MSK na populaci. 13 tis. z nich má v `res_pf_nace` zároveň pseudokód `00`.
   V MSK se deficit X (−5 tis.) a přebytek G (+6,1 tis.) řádově shodují s počtem těchto subjektů.
   Vypadá to, že ČSÚ je ve své statistice zařazuje jinak (část jako X), než je uvádí otevřený soubor.
   **Ověřit se to z veřejných dat nedá.** Dotaz na ČSÚ (kontakt k otevřeným datům:
   michal.cigas@csu.gov.cz): „Jak jsou v RES02Q zařazeny subjekty s převažující činností jen na
   úrovni sekce (G, J) a se současnými kódy 00?“
4. U K (finance) a N nevíme. Deficity jsou menší a rozprostřené po krajích.

**Dopad na report:** kraj a celková čísla jsou spolehlivá (±1 %). Pro sekce G, J, K a X na úrovni
kraje je nutné počítat s odchylkou od oficiální statistiky ČSÚ 10–35 % a v reportu to uvést.
Pilotní sekce F je v pořádku: ČR −1,0 %, Liberecký kraj −0,2 %.

## 8. Kontrola jádra (ARES) proti RES – `res.v_jadro_kontrola`

Pohled spojí `dev.subjekt_aktualne` s posledním snímkem RES přes IČO a pro každou firmu z jádra
ukáže, zda je v RES a zda sedí stav, převažující činnost a kraj. **Nic nepřepisuje.**

Na co pohled dává pozor:
- ARES pole `czNace`, které jádro ukládá do `dev.subjekt_verze.cz_nace`, obsahuje **CZ-NACE 2025**
  (Rev. 2 je v ARES v `czNace2008`) a **všechny** činnosti subjektu, ne převažující. Shoda NACE proto
  znamená, že převažující `NACE2025` z RES je v seznamu z ARES (`PRESNA`), případně aspoň její
  oddíl (`ODDIL`). S pseudokódem `00` porovnat nelze (`NELZE`).
- Kraj v jádru je kód RÚIAN (`dev.adresa.kod_kraje`), do NUTS 3 se převádí přes `res.cis_kraj.kod_ruian`.

**Výsledek v tomto prostředí.** Vzorek 78 firem z ARES je jen v lokálním `data/` autora, proto jsem
do lokálního `dev` naimportoval stávajícím `ares_import` **náhodný vzorek 219 IČO z RES** (150 PO
a 50 FO bez zániku, 15 zaniklých s.r.o. a 4 firmy z `docs/ares_mapovani.md`). Do jádra se dostalo
204 firem:

| | počet |
|---|---:|
| firem v jádru | 204 |
| z nich v RES | 204 (100 %) |
| stav sedí / nesedí | 203 / 1 |
| převažující NACE2025 z RES je v seznamu ARES | 193 |
| jen oddíl / nesedí | 0 / 0 |
| nelze porovnat (pseudokód `00` nebo chybí) | 11 |
| kraj sedí / nesedí / nelze porovnat | 203 / 0 / 1 (ARES bez kódu kraje) |

Nálezy pro jádro (jádro jsem neměnil, jen je zapisuji):
- **Zaniklé subjekty ARES nevrací.** 14 z 15 náhodně vybraných s.r.o. zaniklých v letech 2022–2026
  (RES je má včetně atributů) vrátilo `/ekonomicke-subjekty/{ico}` jako `NENALEZENO`. Pro populaci
  zaniklých PO je RES jediný z těchto dvou zdrojů.
- **Stav:** DAKO-CZ TRANSELCO, s.r.o. (25733117) zaniklo podle RES 1. 9. 2024 fúzí (ZPZAN 02). ARES
  ale nemá `datumZaniku`, jen `seznamRegistraci.stavZdrojeRes = ZANIKLY` (`stavZdrojeVr = AKTIVNI`),
  a jádro ho proto vede jako `AKTIVNI`.
- **Právní forma:** u FO 67955681 uvádí výpis z OR `pravniForma = 100` (kód registru osob, číselník
  149), který v `dev.ciselnik_pravni_forma` není, takže import do jádra spadl na cizím klíči.

## 9. Pilot: sekce F (Stavebnictví, CZ-NACE Rev. 2) × Liberecký kraj

`SELECT * FROM res.v_pilot_f_liberecky` (= `res.prunik_souhrn('F', 'CZ051')`). Populací jsou subjekty
**bez zániku** se sídlem v Libereckém kraji a převažující činností v sekci F. Každé číslo nese příznak
`pod_prahem` (< 10 subjektů). Takové číslo se nepublikuje (`pocet_k_publikaci = NULL`), jen se označí.

**Celkem 14 799 subjektů** (ČSÚ k 30. 6.: 14 833, −0,2 %; se zjištěnou aktivitou podle ČSÚ jen
9 316 = 62,8 %). Podle CZ-NACE 2025 (sekce F „Stavební činnosti“) je to 14 781.

| právní forma (56) | počet | práh |
|---|---:|---|
| 101 FO podnikající dle živnostenského zákona | 12 717 | |
| 112 Společnost s ručením omezeným | 1 648 | |
| 424 Zahraniční fyzická osoba | 329 | |
| 121 Akciová společnost | 30 | |
| 111 Veřejná obchodní společnost | 28 | |
| 105 FO podnikající dle jiných zákonů | 17 | |
| 205 Družstvo | 12 | |
| 421 Odštěpný závod zahraniční PO | 7 | **pod prahem** |
| 107 Zemědělský podnikatel – FO | 5 | **pod prahem** |
| 113 Komanditní společnost | 2 | **pod prahem** |
| 932 Evropská společnost | 2 | **pod prahem** |
| 301 Státní podnik | 1 | **pod prahem** |
| 706 Spolek | 1 | **pod prahem** |

| kategorie počtu pracovníků (579) | počet | práh |
|---|---:|---|
| 110 Bez zaměstnanců | 6 775 | |
| 000 Neuvedeno | 6 737 | |
| 120 1–5 | 946 | |
| 130 6–9 | 150 | |
| 210 10–19 | 115 | |
| 230 25–49 | 41 | |
| 220 20–24 | 21 | |
| 240 50–99 | 11 | |
| 310 100–199 | 1 | **pod prahem** |
| 320 200–249 | 1 | **pod prahem** |
| 330 250–499 | 1 | **pod prahem** |

Vzniky podle let (rok vzniku subjektů, které k 15. 9. 2026 existují):

| rok | počet | rok | počet | rok | počet | rok | počet |
|---|---:|---|---:|---|---:|---|---:|
| 1972 | 1 **pod prahem** | 1992 | 404 | 2004 | 266 | 2016 | 362 |
| 1988 | 1 **pod prahem** | 1993 | 322 | 2005 | 279 | 2017 | 355 |
| 1989 | 2 **pod prahem** | 1994 | 455 | 2006 | 305 | 2018 | 402 |
| 1990 | 576 | 1995 | 458 | 2007 | 398 | 2019 | 420 |
| 1991 | 766 | 1996 | 496 | 2008 | 420 | 2020 | 408 |
| | | 1997 | 510 | 2009 | 387 | 2021 | 415 |
| | | 1998 | 496 | 2010 | 350 | 2022 | 493 |
| | | 1999 | 418 | 2011 | 312 | 2023 | 490 |
| | | 2000 | 268 | 2012 | 324 | 2024 | 522 |
| | | 2001 | 255 | 2013 | 263 | 2025 | 543 |
| | | 2002 | 255 | 2014 | 234 | 2026 (do 15. 9.) | 524 |
| | | 2003 | 327 | 2015 | 317 | | |

Poznámky k interpretaci:
- **„Vzniky podle let“ nejsou počet založených firem v daném roce.** Jde o věkovou strukturu
  přeživších subjektů. Zaniklé FO snímek bez atributů neuvádí a zaniklé PO (255 v F × LBK, z toho
  163 zaniklých od roku 2025) do populace „bez zániku“ nepatří. Tok vzniků a zániků je potřeba
  počítat z řady snímků nebo z tabulek ČSÚ RES05.
- **Velikost:** 45,5 % subjektů má KATPO „Neuvedeno“ (viz kap. 6).
- **Sekundární ochrana** (dopočet skrytého čísla odečtením od součtu) není implementovaná. V pilotu
  má každé členění aspoň 3 skryté buňky, takže jednotlivou hodnotu odečíst nelze, jen jejich součet
  (formy 18, velikost 3, roky 4). Pro obecný report je to otevřené rozhodnutí (kap. 11).

## 10. Omezení zdroje

- **Zaniklé subjekty**: jsou v souboru jen **4 roky** od zániku (nejstarší zánik ve snímku k 15. 9. 2026
  je z 1. 10. 2022, okno se tedy zřejmě posouvá po celých měsících). **Zaniklé FO** (497 410 řádků) mají jen IČO a datum zániku: nejde je zařadit do
  oboru, území ani právní formy. Zaniklé PO (84 398) mají všechny atributy.
- **Fyzické osoby** tvoří 70 % subjektů bez zániku (FORMA 101/105/107/424: 2 067 103). `FIRMA` je
  jméno a sídlo často bydliště (osobní údaje, jen agregáty). Zahraniční FO (424) jsou v populaci
  a ve stavebnictví LBK je jich 329.
- **Registrované ≠ aktivní** (kap. 7): příznak aktivity v otevřených datech není. Registrovaných
  je ~1,64× víc než aktivních.
- **Území = sídlo**, ne místo činnosti. Provozovny v RES open data nejsou a firma s mnoha provozovnami
  se počítá jen v kraji sídla.
- **Převažující činnost** je jedna. Vedlejší činnosti jsou v `res.pf_nace` (průměrně 3,1 na subjekt),
  ale pro průniky se zatím nepoužívají. Část subjektů je zařazena jen na úroveň sekce (`G` 45 tis.,
  `J` 12 tis.) a 122 tis. má pseudokód `00` bez oboru.
- **KATPO** je z poloviny „Neuvedeno“ a u FO a PO má jiný význam (kap. 6). Od 1. 7. 2024 se do počtu
  zaměstnanců počítají i DPP (změna evidence ČSSZ), takže časová řada velikosti má zlom.
- Hromadné ukončení FO v únoru–březnu 2023 (~187 tis. zániků za dva měsíce proti obvyklým 7–20 tis.)
  zkresluje zániky podle let. Příčinu ze zdroje nelze určit.
- Jeden snímek je stav k jednomu datu. Porovnání s ČSÚ (konec čtvrtletí) proto vždy nese časový posun.

## 11. Vědomě nezpracované údaje

| údaj | proč nezpracováno | co by bylo potřeba |
|---|---|---|
| `ICZUJ` (obec / městská část sídla) a číselník 51 | report je na úrovni kraje; obec by zvýšila riziko malých buněk | načíst číselník 51 (+ vazbu na obce 43) do `res.cis_*` |
| `CISS2010` (institucionální sektor) a číselník 5161 | pro obor × území netřeba | načíst číselník 5161 |
| adresa sídla (`KODADM`, `PSC`, `OBEC_TEXT` …) | jen uložená, nepropojená s `dev.adresa` (jádro se nemění) | rozhodnutí o propojení RES ↔ jádro přes RÚIAN |
| vedlejší činnosti (`res.pf_nace`) | průniky stojí na převažující činnosti | rozhodnout, zda report ukáže i „firmy s vedlejší činností v oboru“ |
| `ROSFORMA` ve výstupech | pro report stačí statistická `FORMA` | – |
| `PRIZNAK`, `DDATPAKT` | zatím jediný snímek | přírůstkové zpracování řady snímků |
| starší snímky | ČSÚ zveřejňuje jen poslední snímek | pravidelný import (2× měsíčně) buduje historii |
| B, C, D, E proti ČSÚ | ČSÚ publikuje jen B–E | – |
| příznak aktivity | v otevřených datech není | nelze z RES; jen agregát ČSÚ (kap. 7) |
| sekundární ochrana malých buněk | zadání požaduje jen označení pod prahem | pravidlo pro skrytí další buňky, když by šla skrytá dopočítat |
| KATPO „000“ u PO | nevykládáme jako „0 zaměstnanců“ | rozhodnutí, jak ho v reportu prezentovat |

## 12. Jak zopakovat

```bash
python -m firemni_databaze.nasad_sql dev
python -m firemni_databaze.nasad_sql res
python -m firemni_databaze.res_import vse       # číselníky, snímek (~1,6 GB, ~6 min), agregáty, přehled
python -m unittest discover -s tests            # DB testy potřebují načtený snímek
```

Ad-hoc srovnání s CZ-NACE 2025 (kap. 7, bod 2): `res_import.nacti_agregaty(conn, 'RES02QNACET1')`
načte do `res.csu_agregat` i tabulku ČSÚ pro CZ-NACE 2025. Pohled `res.v_srovnani_csu` pracuje
s RES02QT1 (Rev. 2).
