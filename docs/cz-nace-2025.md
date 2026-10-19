# CZ-NACE 2025 – sjednocená klasifikace odvětví

Cíl: spojit firmu s oborem napříč produkty (Firemní databáze, Oborově-regionální report, parlamentní
a aktérská analytika). Primární verze ve všech výstupech je **CZ-NACE 2025**, **CZ-NACE 2008** zůstává
jako historický atribut. Obě verze se ukládají s platností v čase a verze je u každého záznamu výslovně
(některé kódy CZ-NACE 2008 mají v CZ-NACE 2025 jiný obsah, např. oddíly 58–63, sekce J–U).

Stav: schéma `obor` (migrace, číselníky, kódy firem z RES a ARES, matice přechodů, odvození, rozhraní
`obor.v_firma_obor_aktualni`, kontroly) je nasazené a ověřené na snímku RES k 15. 10. 2026 (kap. 6). Oborově-regionální report počítá od 19. 10. 2026 podle
CZ-NACE 2025 nad tímto rozhraním (R3, rozhodnutí 15 metodiky reportu).

## 1. Schválená rozhodnutí

1. Zdroj kódů 2025 pro současné firmy je atribut **NACE2025 z RES** (přes ARES nebo z otevřených dat
   RES od ČSÚ). Převodník ČSÚ slouží jen jako záloha.
2. Nejednoznačné převody (historické stavy před 2026, firmy bez kódu 2025) se řeší **empirickou vahou**
   z dvojího kódování v RES: nejčastější cíl, jeho podíl jako jistota, `zdroj = 'odvozeno'`.
3. Primární verze je CZ-NACE 2025. Verze 2008 jen jako historický atribut.

**Rozhodnutí z 19. 10. 2026** (po PR #20):

| # | rozhodnutí | jak je v kódu |
|---|---|---|
| R1 | Jistotu 1 dostane i **jediný cíl podle převodníku** (vazba N:1, nebo kandidáti s jediným společným předkem na cílové úrovni), ne jen vazba 1:1. | metoda `prevodnik_jediny_cil` (`nace_firmy.pravidlo`) |
| R2 | **Rozpor převodníku s empirií**: má-li empirická matice pro kód 2008 základ ≥ 20 subjektů a cíl s podílem ≥ 0,9, který převodník neuvádí jako jediný cíl, **rozhoduje empirie**. Každý případ se zapisuje. | metoda `empiricky_rozpor`, tabulka `obor.nace_rozpory_prevodnik`, kap. 6 |
| R3 | **Oborově-regionální report přechází na CZ-NACE 2025** (rozhodnutí 15 metodiky reportu nahrazuje rozhodnutí 5). | `report.py` nad `obor.v_firma_obor_aktualni`, [`report_metodika.md`](report_metodika.md) |
| R4 | **Náhrada vdb.czso.cz** za iSMS + pseudokódy RES je schválená (kap. 2). | `res_zdroj.CISELNIKY`, `nace_ciselniky` |
| R5 | Práh empirické matice zůstává **20 subjektů**. Automatické spojení firmy s oborem jen při **`jistota_oddil ≥ 0,8`**, pod tím „odvozeno, nejisté“. | `v_firma_obor_aktualni.automaticke_spojeni`, `stav_zarazeni` (kap. 8) |
| R6 | Začátek platnosti kódu 2025: `platnost_od` = **pozdější z data aktualizace záznamu v RES a 1. 1. 2025**. | `obor.zacatek_2025()`, loader i oprava uložených dat (kap. 4) |
| R7 | **Konec dvojího kódování**: po 31. 12. 2028 (nebo jakmile zdroj kódy 2008 přestane dodávat) loader uzavře všechny otevřené kódy 2008 s `platnost_do = 2028-12-31` a důvodem „konec dvojího kódování“. | `nace_firmy.je_konec_dvojiho_kodovani`, `uzavri_kody_2008`, sloupec `duvod_uzavreni` |

**Rozhodnutí z 20. 10. 2026** (otevřené otázky PR #21):

| # | rozhodnutí | jak je v kódu |
|---|---|---|
| R8 | **Změna klasifikace bez počtu odchodů.** Výstup uvádí počty podle obou verzí, čistou změnu a hlavní oddíl odchodů a příchodů; počet odchodů ani příchodů ne – z čisté změny by šel dopočítat ten druhý. Směr pod prahem se uvádí jen jako „méně než 10“. | `report.zmena_klasifikace` (obě věty vždy), proměnné `klas:*` v kontrole dopočtu (`zaregistruj_zmenu_klasifikace`), testy `TestZmenaKlasifikaceDopocet`, `test_zmena_klasifikace_bez_dopoctu_pod_prahem` |
| R9 | **Ořez na 1. 1. 2025 (R6) platí jen pro kódy z RES; odvozené kódy se neořezávají.** Důvod: odvozený kód je rekonstrukce historie ve verzi 2025 – popisuje stav, který skončil dřív, než CZ-NACE 2025 platila. S ořezem by u zaniklých subjektů neplatil nikdy (prázdný interval) a historická řada podle CZ-NACE 2025 by nešla sestavit. | `nace_firmy.odvod_firmy` přebírá platnost stavu 2008 beze změny |
| R10 | Funkce „kód k datu“ se teď nedělá; je **povinná před načtením druhého snímku RES** (kap. 9). | – |
| R11 | Rozhraní se obnovuje **po každém snímku RES**; noční obnova po změnách z ARES až po zprovoznění serveru (kap. 9). | `nace_firmy res` / `matice` → `obnov_rozhrani` |
| R12 | Starý pilot podle CZ-NACE 2008 (15. 9. 2026) zůstává jako **archiv s označením „CZ-NACE 2008, nahrazeno“**. | `meta.archiv` ve `vysledek.json`, nadpis `vysledek.md`, list Přehled v XLSX, `reporty/ukazky/F__CZ051__2026-09-15/ARCHIV.md` |

## 2. Zdroje a podmínky (ověřeno 18. 10. 2026)

| údaj | zdroj | robots.txt / podmínky | použito |
|---|---|---|---|
| kódy firem 2008 a 2025 (hlavní i vedlejší) – populace | otevřená data RES, `opendata.csu.gov.cz/soubory/od/od_org03/` (`res_data.csv`, `res_pf_nace.csv`) | robots.txt neexistuje (404); CC BY 4.0 | **ano** – hlavní zdroj |
| kódy firem z jádra (jednotlivá IČO) | ARES, `ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty-res/{ico}` | robots.txt zakazuje jen `/cms/` | **ano** – loader `ares_import` |
| číselník CZ-NACE 2008 a 2025, úrovně 1–5 | iSMS ČSÚ, `apl2.czso.cz/iSMS/do_cis_export` (klasifikace 80004 a 80143); odkazuje na něj [stránka ČSÚ ke CZ-NACE 2025](https://csu.gov.cz/klasifikace-ekonomickych-cinnosti-cz-nace-platna-od-1-1-2025) | robots.txt neexistuje (404) | **ano** |
| převodník NACE Rev. 2 ↔ Rev. 2.1 (třídy) | [csu.gov.cz/prevodniky-v105](https://csu.gov.cz/prevodniky-v105), Eurostat V1.05 | robots.txt `csu.gov.cz` zakazuje jen 3 cesty, AI crawlery neblokuje | **ano** |
| převodník 5místných položek CZ-NACE 2008 ↔ 2025 | tamtéž, ČSÚ 12/2025 | tamtéž | **ano** |
| číselníky `CZ_NACE_RES`, `CZ_NACE_RES2025` (s pseudokódy RES) | `vdb.czso.cz/opendata/ciselniky` | **robots.txt `User-agent: *` / `Disallow: /`** – blokuje všechny automatické klienty | **ne** – krok zastaven, viz níže |

**Rozhodnutí R4 (19. 10. 2026): číselníky CZ-NACE z iSMS místo vdb.czso.cz.** Důvod: robots.txt
`vdb.czso.cz` obsahuje `User-agent: *` / `Disallow: /`, tedy zakazuje celý web všem automatickým
klientům včetně AI crawlerů, a podle rozhodnutí 13 se takový zdroj nekontaktuje ani neobchází.
iSMS (`apl2.czso.cz`) je oficiální kanál, na který odkazuje stránka ČSÚ ke CZ-NACE 2025, a robots.txt
nemá. Náhrada pokryla všechny kódy snímku RES (kap. 7).

**vdb.czso.cz je blokované.** Dosavadní `res_import ciselniky` z něj bral číselníky CZ-NACE pro RES.
Robots.txt teď zakazuje celý web všem robotům (tedy i AI crawlerům), proto se už nekontaktuje
(rozhodnutí 13). Náhrada: oficiální klasifikace z iSMS (stejná čísla klasifikací 80004 a 80143)
+ čtyři pseudokódy RES z dokumentace otevřených dat (X/04 „nezjištěno“, Y/00 „neuvedeno v přílohách
živnostenského zákona“). Pokud VDB obsahovala další položky navíc (jiné pseudokódy), ukáže je kontrola
„kódy mimo číselník“ (kap. 7) – v tomto snímku žádné nejsou.

ARES a otevřená data RES nesou **tentýž atribut RES** (`NACE2025` = `czNacePrevazujici`). Pro populaci
se používají otevřená data (jeden soubor místo milionů dotazů), pro firmy jádra ARES. Na třech IČO
ověřeno 18. 10. 2026:

| IČO | subjekt | `czNacePrevazujici2008` | `czNacePrevazujici` (2025) |
|---|---|---|---|
| 27082440 | Alza.cz a.s. | 47911 | 47120 |
| 00216208 | Univerzita Karlova | 85420 | 85402 |
| 04115210 | Pekárna Unčín s.r.o. | 107 | 107 |

Základní endpoint `ekonomicke-subjekty` vrací jen seznamy `czNace` (2025) a `czNace2008` všech činností
bez určení převažující; převažující je jen v `ekonomicke-subjekty-res`.

## 3. Kde byly kódy NACE před touto změnou (krok 0)

| místo | obsah | verze |
|---|---|---|
| `res.subjekt.nace`, `res.subjekt.nace2025` | převažující činnost ze snímku RES | 2008 / 2025, oba sloupce vedle sebe |
| `res.pf_nace` (`kodcis` 80004 / 80143) | všechny činnosti podle zdroje údaje | obě |
| `res.cis_nace` (`klasifikace` 80004 / 80143) | číselník pro výklad snímku | obě |
| `dev.subjekt_verze.cz_nace` | ARES `czNace` = **všechny** činnosti, bez převažující | **2025** (název sloupce verzi neříká) |
| `dev.import_surova_data` | surový JSON ARES (od této změny i `ekonomicke-subjekty-res`) | obě |
| `res.v_subjekt`, `res.v_pocty_kraj_sekce`, `res.v_srovnani_csu`, `res.prunik_souhrn`, `res.v_pilot_f_liberecky` | pohledy nad snímkem | převážně 2008, `prunik_souhrn` umí obě |
| `res.v_jadro_kontrola` | jádro vs. RES, shoda NACE | 2025 |
| `report.py` (`KLASIFIKACE = 80004`, `urci_obor`, `nacti_populaci`, `SKUPINY_A10`, mzdy, SBS) | Oborově-regionální report | **2008** |
| `res.csu_agregat` (RES02QT1), `res.csu_mzdy`, `res.csu_demografie`, `res.eu_regionalni_ucty`, `res.eu_sbs` | publikované statistiky | Rev. 2 (2008) |

## 4. Schéma `obor`

```bash
python -m firemni_databaze.nasad_sql obor            # po dev a res; idempotentní
python -m firemni_databaze.nace_ciselniky nahraj     # číselníky z ciselniky/nace/*.csv
python -m firemni_databaze.nace_firmy vse            # snímek RES → firma_nace, matice, odvození, kontroly
python -m firemni_databaze.nace_ciselniky sestav     # (jen při nové verzi zdrojů) stáhne ČSÚ → CSV
```

| objekt | obsah |
|---|---|
| `obor.nace_ciselnik` | `(verze, kod, uroven, nazev, nadrazeny_kod)` + předci `sekce/oddil/skupina/trida`, `je_pseudokod`, platnost, zdroj |
| `obor.nace_prevodnik` | `(kod_2008, kod_2025, uroven, typ_vazby 1:1/1:N/N:1/N:M, castecne, zdroj)` – páry na téže úrovni |
| `obor.nace_sekce_a10` | sekce 2025 → skupina A*10 NACE Rev. 2 (pro Eurostat) |
| `obor.firma_nace` | `(ico, verze, kod, uroven, typ hlavni/vedlejsi, zdroj RES/odvozeno, zdroj_detail, jistota, priznak, kandidati, odvozeno_z, platnost_od, platnost_do, nacteno, import_davka_id)` |
| `obor.nace_prechod_empiricky` | matice přechodů `(zaklad_k, kod_2008, uroven_2008, uroven, kod_2025, pocet, zaklad, podil)` |
| `obor.nace_odvozeni` | pravidlo pro každý kód 2008 a cílovou úroveň `(kod_2025, jistota, metoda, zaklad, kandidati)` |
| `obor.v_firma_obor_aktualni` | **rozhraní** – jeden řádek na IČO |
| `obor.v_firma_nace_mimo_ciselnik` | kontrola kódů mimo číselník |

Číselníky v repozitáři (`ciselniky/nace/`): `nace_ciselnik.csv` (3 488 položek: 2008 – 23 sekcí vč. X/Y,
90 oddílů, 272 skupin, 615 tříd, 721 podtříd; 2025 – 24 / 89 / 287 / 651 / 716), `nace_prevodnik.csv`
(2 728 párů), `sekce2025_a10.csv`.

**Převodník** sestavuje `nace_ciselniky.sestav`: úrovně 1–4 z obou směrů převodníku Eurostatu (CZ-NACE
2008/2025 = NACE Rev. 2/2.1 až po třídu), podtřídy, které se národně člení, z převodníku ČSÚ pro 5místné
položky, a podtřídy „xxxx0“ (třída se nečlení) z převodníku tříd. Třída 2025 **46.89** nemá v Rev. 2
předchůdce (Eurostat: „not possible to link“).

### Pravidla platnosti a historie

- Kód z RES: `platnost_od` = datum poslední aktualizace záznamu v RES (`DDATPAKT` z otevřených dat,
  `datumAktualizace` z ARES) – kód platí nejpozději od tohoto dne. **U kódu 2025 nejdřív 1. 1. 2025**
  (R6, `obor.zacatek_2025`); u subjektu zaniklého před 1. 1. 2025 je interval kódu 2025 prázdný
  (`platnost_od = platnost_do = 2025-01-01`). **Odvozených kódů se R6 netýká (R9):** odvozený kód je
  rekonstrukce historie ve verzi 2025 a s ořezem by u zaniklých subjektů neplatil nikdy.
  `platnost_do` = datum zániku, nebo datum aktualizace, se kterou další snímek kód nahradil.
- `duvod_uzavreni` (R7): `zánik subjektu`, `zdroj kód už neuvádí`, `konec dvojího kódování`.
- **Konec dvojího kódování (R7):** je-li snímek po 31. 12. 2028, nebo neobsahuje žádný kód 2008, loader
  kódy 2008 nenačítá a všechny otevřené kódy 2008 uzavře k 2028-12-31. U ARES (jedno IČO) rozhoduje jen
  datum – chybějící kód 2008 u jedné firmy neznamená, že ho zdroj přestal dodávat.
- Každý snímek RES / dotaz ARES: otevřené kódy, které zdroj už neuvádí, se **uzavřou**; nové se vloží;
  stejné se nemění. Opakovaný běh nic nezmění (ověřeno, kap. 7).
- Kódy z RES se nemažou a nepřepisují (trigger `obor.firma_nace_straz`), smí se jen uzavřít. Stávající
  kódy 2008 (`res.subjekt`, `res.pf_nace`) se převádí do `firma_nace` jako verze 2008; v `res` zůstávají.
- Odvozené řádky jsou výpočet: při novém výpočtu matice se nahradí celé.

## 5. Odvození kódů 2025 (krok 3)

**Empirická matice:** firmy, které mají v RES oba kódy hlavní činnosti (tentýž stav záznamu). Firma
s kódem 2008 `k` přispívá za `k` i za jeho předky a za každou cílovou úroveň 2025 zvlášť (ne
podrobnější než zdrojový kód). Každý starý kód má tak vlastní rozdělení i na úrovni oddílu a sekce.

**Pravidlo pro kód 2008 `k` a cílovou úroveň L** (pořadí):

| metoda | podmínka | výsledek |
|---|---|---|
| `prevodnik_1:1` | `k` nebo jeho předek na úrovni L má v převodníku vazbu 1:1 | cíl (jeho předek na úrovni L), jistota 1 |
| `prevodnik_jediny_cil` | všichni kandidáti z převodníku mají na úrovni L společného předka (vč. vazby N:1) – R1 | ten předek, jistota 1 |
| `empiricky_rozpor` | převodník dává jediný cíl, ale matice má základ ≥ 20 a jiný cíl s podílem ≥ 0,9 – R2 | empirický cíl, jistota = jeho podíl; zápis do `nace_rozpory_prevodnik` |
| `empiricky` | v matici je pro `k` aspoň 20 firem | nejčastější cíl, jistota = jeho podíl |
| `nejednoznacne` | jinak | `kod` NULL, `priznak = 'nejednoznacne'`, `kandidati` z převodníku |

Odvozuje se pro každý stav hlavní činnosti 2008 z RES, ke kterému neexistuje kód 2025 z RES pro tentýž
stav – dnes zaniklé subjekty, které zanikly před dvojím kódováním, v budoucnu i starší stavy z archivu
snímků.

## 6. Kontroly a dopad (krok 6)

Snímek RES k **15. 10. 2026** (3 531 342 subjektů, 22 349 555 řádků činností), matice k témuž dni.
Výpočet: `python -m firemni_databaze.nace_firmy vse`. Počty pod 10 se uvádějí jako „< 10“ (rozhodnutí 3).

**Obsah `obor.firma_nace`:** 21 995 785 kódů. CZ-NACE 2008: 3 038 940 hlavních + 7 952 994 vedlejších,
CZ-NACE 2025: 2 993 853 hlavních + 7 839 168 vedlejších, odvozených 170 904 řádků (IČO × úroveň).

### Pokrytí (hlavní činnost CZ-NACE 2025)

| subjekty | celkem | kód 2025 z RES | odvozený kód | z toho nejednoznačný na úrovni kódu | odvozený oddíl | bez kódu |
|---|---:|---:|---:|---:|---:|---:|
| bez zániku | 2 954 228 | 2 954 228 (100,00 %) | 0 | 0 | 0 | 0 |
| zaniklé (v souboru 4 roky) | 577 114 | 39 625 (6,87 %) | 45 087 (7,81 %) | 71 | 44 944 | 492 402 (85,32 %) |
| **celkem** | 3 531 342 | 2 993 853 (84,78 %) | 45 087 (1,28 %) | 71 | 44 944 | 492 402 (13,94 %) |

- Všechny subjekty bez zániku mají kód 2025 přímo z RES. Odvozuje se jen u **zaniklých PO**, které
  zanikly před dvojím kódováním (mají jen kód 2008).
- „Bez kódu“ jsou zaniklé FO: v otevřených datech mají jen IČO a datum zániku (GDPR), kód nemají
  v žádné verzi.
- Z 45 087 odvozených má 44 944 určený oddíl. Jen 71 je nejednoznačných na úrovni svého kódu
  (většinou podtřída) a dostali kandidáty z převodníku.

### Základ empirické matice

**2 993 853 subjektů** má v RES oba kódy hlavní činnosti (tentýž stav záznamu). Matice má 10 827 párů.

| cílová úroveň 2025 | kódů 2008 v matici | z toho se základem ≥ 20 firem |
|---|---:|---:|
| sekce | 1 649 | 1 305 |
| oddíl | 1 628 | 1 284 |
| skupina | 1 541 | 1 198 |
| třída | 1 275 | 957 |
| podtřída | 677 | 480 |

### Odvozené kódy podle úrovně a metody (subjektů, průměrná jistota)

| úroveň | `prevodnik_1:1` | `prevodnik_jediny_cil` | `empiricky_rozpor` | `empiricky` | `nejednoznacne` |
|---|---:|---:|---:|---:|---:|
| sekce | 14 255 (1) | 18 537 (1) | – | 12 294 (0,9974) | < 10 |
| oddíl | 14 988 (1) | 15 574 (1) | – | 14 382 (0,9979) | < 10 |
| skupina | 16 719 (1) | 5 811 (1) | – | 15 755 (0,9863) | 10 |
| třída | 11 234 (1) | 2 457 (1) | 12 (0,9975) | 14 176 (0,9905) | 26 |
| podtřída | 6 300 (1) | 2 247 (1) | < 10 (0,9994) | 6 046 (0,9747) | 70 |

### Rozpory převodníku s empirií (R2, `obor.nace_rozpory_prevodnik`)

| kód 2008 | cílová úroveň | cíl převodníku | cíl empirie (použit) | podíl | základ |
|---|---:|---|---|---:|---:|
| 96.09 | třída | 96.99 | **96.91** | 0,9919 | 14 653 |
| 96.09.0 | třída | 96.99 | **96.91** | 0,9994 | 14 383 |
| 96.09.0 | podtřída | 96.99.0 | **96.91.0** | 0,9994 | 14 383 |

Jiné rozpory (základ ≥ 20, podíl ≥ 0,9, jiný než jediný cíl převodníku) v matici k 15. 10. 2026 nejsou.
Na úrovni skupiny, oddílu a sekce rozpor nevzniká (96.91 i 96.99 leží ve skupině 96.9).

### Stav zařazení v rozhraní (R5)

| `stav_zarazeni` | IČO |
|---|---:|
| RES | 2 993 853 |
| odvozeno (`jistota_oddil ≥ 0,8`) | 44 931 |
| odvozeno, nejisté | 156 |

### Změna oproti PR #20 (přepočet 19. 10. 2026)

| | PR #20 | nyní |
|---|---:|---:|
| odvozených subjektů | 45 087 | 45 087 |
| z toho nejednoznačných na úrovni kódu | 71 | 71 |
| pravidel s rozporem převodník × empirie (R2) | – | 3 |
| subjektů s kódem podle empirie místo vazby 1:1 (třída / podtřída) | – | 12 / < 10 |
| kódů 2025 z RES s posunutým začátkem platnosti na 1. 1. 2025 (R6) | – | 4 |
| subjektů „odvozeno, nejisté“ (mimo automatické spojení, R5) | – | 156 |

R1 (jistota 1 pro jediný cíl) platil už v PR #20 jako návrh – počty se nemění. R6 se v otevřených
datech RES neprojevil (datum aktualizace je u všech záznamů po 1. 1. 2025, hromadné překódování
v lednu 2026); posunuly se jen 4 kódy dvou subjektů načtených přes ARES (`datumAktualizace` 2023).
Druhý běh loaderu po změnách nic nevložil ani neuzavřel.

**Převodník proti empirii:** u pravidel se základem ≥ 20 firem dává `prevodnik_jediny_cil` stejný cíl
jako nejčastější empirický přechod ve **všech 1 627 případech**. U `prevodnik_1:1` je to 2 617 z 2 620.
Jediný rozpor je **96.09 → 96.99** („ostatní osobní služby j. n.“): podle převodníku Eurostatu jde
o vazbu 1:1, ČSÚ ale v RES zařadil 99,9 % z 14 383 subjektů do **96.91** („osobní služby
v domácnostech“). Podle R2 teď rozhoduje empirie (tabulka výše).

### Změna oddílu a sekce (subjekty bez zániku s oběma kódy z RES)

- **jiný kód oddílu:** 69 420 z 2 895 807 subjektů zařazených aspoň na oddíl (**2,40 %**);
- **jiná sekce obsahově** (sekce 2025 neodpovídá sekci 2008 podle `obor.nace_sekce_a10`): 64 828 (**2,19 %**);
- jiné písmeno sekce: 1 337 547 (45,28 %). Toto číslo nic neznamená, písmena se mezi verzemi posunula
  (např. J 2008 → J + K 2025, K 2008 → L 2025, P 2008 → Q 2025).

| hlavní přechody oddílů | subjektů | | hlavní přechody sekcí | subjektů |
|---|---:|---|---|---:|
| 45 → 95 (opravy motorových vozidel) | 61 384 | | G → T (opravy vozidel do „ostatních činností“) | 61 442 |
| 45 → 47 | 2 683 | | F → M (developerská činnost 41.1 → 68.12) | 1 008 |
| 45 → 46 | 1 045 | | G → M | 648 |
| 63 → 60 (zpravodajské agentury) | 610 | | J → G | 494 |
| 41 → 68 | 609 | | J → N | 140 |
| 46 → 68 | 570 | | G → N | 126 |
| 43 → 68 | 399 | | G → H | 101 |

Změna je soustředěná: 88 % změn oddílu tvoří přesun oprav motorových vozidel (45.2, 45.4) do
oddílu 95 v sekci T.

### Pilot: stavebnictví × Liberecký kraj (CZ051), subjekty bez zániku

- sekce F podle CZ-NACE 2008: **14 817**, podle CZ-NACE 2025: **14 799**, čistá změna **−18** (−0,12 %);
- odchody šly hlavně do oddílu **68** (činnosti v oblasti nemovitostí; developerská činnost 41.1 → 68.12);
- příchodů bylo **méně než 10**, hlavně z oddílu **45**;
- počty odchodů a příchodů se neuvádějí (R8): z čisté změny by šel dopočítat ten druhý, a ten je pod prahem.

Pro report o stavebnictví v kraji je změna verze zanedbatelná.

## 7. Fakta, odhady a co nejde

| | obsah |
|---|---|
| **fakta** | kódy 2008 a 2025 z RES (oficiální přidělení ČSÚ, ne nutně skutečná činnost); číselníky a převodníky ČSÚ/Eurostatu; matice přechodů (počty z dvojího kódování) |
| **odhady** | odvozené kódy 2025 (`zdroj = 'odvozeno'`) s metodou `empiricky` – jistota = podíl v matici, tj. pravděpodobnost za předpokladu, že se zaniklé firmy překódovaly jako dnešní; `prevodnik_*` jsou logicky jisté jen vzhledem k převodníku |
| **nejde** | kód zaniklých FO (otevřená data ho neuvádějí); historie kódů před prvním načteným snímkem (ČSÚ zveřejňuje jen poslední snímek); ověření, že kód odpovídá skutečné činnosti; ekonomické údaje Eurostatu přesně podle sekcí 2025 (jen přes převodní tabulku A*10) |

**Kontrola číselníku:** všech 21 995 785 kódů ve `firma_nace` je v číselníku své verze. Pseudokódy X/04
a Y/00 doplněné místo VDB stačí, žádný kód RES mimo ně se nevyskytuje.

**Idempotence:** opakovaný běh `nace_firmy res` nad týmž snímkem nevloží ani neuzavře žádný kód
(ověřeno 18. 10. 2026: 0 vložených a 0 uzavřených ve všech čtyřech kombinacích verze × typ, 3 min). Při načtení snímku se nezdvojily ani kódy tří IČO, které předtím zapsal loader ARES
(3 038 940 hlavních kódů 2008 v RES, z toho 3 už byly v tabulce).

### Oprava převodníku (po sloučení PR #19)

První verze `nace_prevodnik.csv` přiřazovala podtřídám 2008 „xxxx0“, které převodník ČSÚ pro 5místné
položky uvádí jen jako **dílčí zdroj** nové podtřídy 2025, pouze tento dílčí cíl. Hlavní převod podle
převodníku tříd se ztratil, např. 16.29.0 → jen 15.20.9 místo 16.26–16.28 + 15.20.9. Chybu odhalilo
srovnání s empirickou maticí. Po opravě má převodník 2 728 párů místo 2 543 a regresi hlídá test.

## 8. Rozhraní pro ostatní produkty

`obor.v_firma_obor_aktualni` – jeden řádek na IČO, poslední známá hlavní činnost. Od 19. 10. 2026 je to
**materializovaný pohled** (výpočet `obor.v_firma_obor_vypocet` trvá ~2 min, dotaz nad materializovaným
pohledem s indexy na `ico`, `oddil`, `sekce` jsou milisekundy). Obnovuje ho `nace_firmy` po každém
načtení (`res`, `matice`) nebo ručně `python -m firemni_databaze.nace_firmy obnov`; `ares_import` ho
neobnovuje.

| sloupec | význam |
|---|---|
| `ico` | IČO (8 číslic) |
| `zdroj` | `RES` (kód 2025 přidělený ČSÚ) nebo `odvozeno` |
| `sekce`, `oddil`, `skupina`, `trida`, `podtrida` | CZ-NACE 2025; u nižší úrovně zařazení NULL |
| `kod_2025`, `uroven_2025` | nejpodrobnější známý kód 2025 a jeho úroveň |
| `jistota`, `jistota_oddil`, `jistota_sekce` | RES = 1; odvozeno = jistota dané úrovně |
| `priznak`, `kandidati` | `nejednoznacne` + kandidáti z převodníku (kód na úrovni zdroje nejde určit) |
| `je_pseudokod` | sekce X/Y (obor neurčen) |
| `kod_2008`, `sekce_2008`, `oddil_2008` | historický atribut (CZ-NACE 2008 z RES) |
| `platnost_od`, `platnost_do` | platnost řádku; živé subjekty mají `platnost_do IS NULL` |
| `automaticke_spojeni` | R5: `true` = kód z RES, nebo odvozený s `jistota_oddil ≥ 0,8` |
| `stav_zarazeni` | `RES` / `odvozeno` / `odvozeno, nejisté` (odvozený s `jistota_oddil < 0,8` nebo bez oddílu) |

**Pravidlo pro všechny produkty (R5):** firmu s oborem spojuj automaticky jen při `automaticke_spojeni`
(tj. kód z RES, nebo `jistota_oddil ≥ 0,8`). Pod tím ji zobrazuj jako **„odvozeno, nejisté“**
(`stav_zarazeni`) a do automatických výpočtů nezahrnuj. Oborově-regionální report to tak dělá
(`report.PODMINKA_OBORU`).

**Spojení s parlamentní a aktérskou analytikou** jde přes `oddil` (2 místa, CZ-NACE 2025):

```sql
SELECT z.zakon_id, f.ico
FROM analytika.zakon_oddil z                       -- tagy zákonů do oddílů CZ-NACE 2025
JOIN obor.v_firma_obor_aktualni f ON f.oddil = z.oddil
WHERE f.platnost_do IS NULL AND NOT f.je_pseudokod
  AND f.automaticke_spojeni;                       -- R5: kód z RES nebo jistota_oddil ≥ 0,8
```

Doporučení pro konzumenty: (1) vždy uvádět, že kód z RES je oficiální, ne neomylný (ČSÚ připouští, že
u části subjektů neodpovídá skutečné činnosti); (2) u odvozených kódů pracovat s `jistota_oddil`
a nejednoznačné řádky vykazovat zvlášť; (3) neporovnávat kódy 2008 a 2025 jako řetězce – stejný kód
může znamenat jiný obsah.

Ekonomické údaje Eurostatu (A*10, NACE Rev. 2) se k sekcím 2025 připojují přes `obor.nace_sekce_a10`.
Jde o **spojení dvou verzí klasifikace na úrovni sekcí** – obsah sekcí se mezi verzemi mírně liší
(např. 41.1 developerská činnost přešla z F do M, části J do K). Výstup, který tabulku použije, to musí
uvést poznámkou: „Skupiny A*10 podle NACE Rev. 2 jsou k sekcím CZ-NACE 2025 přiřazeny převodní tabulkou
na úrovni sekcí; obsah sekcí se mezi verzemi klasifikace částečně liší.“

## 9. Další kroky

Hotovo: kroky 0–6 původního zadání a rozhodnutí R1–R7 (19. 10. 2026), včetně přepnutí
Oborově-regionálního reportu na CZ-NACE 2025. Zbývá:

1. **Funkce „kód k datu“ – POVINNÉ PŘED NAČTENÍM DRUHÉHO SNÍMKU RES (R10).** Rozhraní je „poslední
   známý stav“; report nad starším snímkem by bral dnešní kód 2025. Než se načte druhý snímek, doplnit
   funkci `obor.firma_obor_k_datu(d)` (stejné sloupce jako rozhraní, kódy platné k datu `d`, tatáž
   pravidla R5 a R9) a report přepnout na ni pro `--datum` starší než poslední snímek.
2. **Noční obnova rozhraní (R11), po zprovoznění serveru.** Cron jednou za noc spustí
   `python -m firemni_databaze.nace_firmy obnov`, ale jen pokud `ares_import` od poslední obnovy něco
   změnil (nová nebo uzavřená řádka v `obor.firma_nace` se zdrojem ARES – např. porovnat
   `max(nacteno)` a počet uzavřených řádků s časem poslední obnovy). Po každém snímku RES se rozhraní
   obnovuje už teď.
3. **Pilot a vzorové výstupy.** Nový pilot `reporty/vystupy/F__CZ051__2026-10-15` je spočítaný v CZ-NACE
   2025; výklad analytika k němu (`reporty/vyklad/F__CZ051__2026-10-15.md`) má jen zástupný text a
   PDF (`reporty/ukazky/`) se nesázelo (v prostředí chybí typst). Starý pilot k 15. 9. 2026 je archiv
   „CZ-NACE 2008, nahrazeno“ (R12).
4. **Pohledy ve schématu `res`** (`v_pocty_kraj_sekce`, `prunik_souhrn`, `v_pilot_f_liberecky`,
   `v_srovnani_csu`, `v_kvalita`) dál pracují s kódy RES v obou verzích (výchozí Rev. 2) – jsou to
   kontroly zdroje, ne report; přepnout jen bude-li je některý produkt používat.
5. **Archiv snímků**: po každém snímku RES (2× měsíčně) spustit `nace_firmy res` a `matice`; historie
   kódů v `firma_nace` vzniká až řadou snímků (dnes jeden).
6. `dev.subjekt_verze.cz_nace` obsahuje CZ-NACE **2025** (všechny činnosti), název to neříká – doplnit
   komentář sloupce, nebo ho nahradit odkazem na `obor.firma_nace`.
7. Odvození vedlejších činností (dnes jen hlavní) – jen pokud je některý produkt potřebuje.
8. Kontrola skutečné činnosti: ČSÚ připouští, že `NACE2025` u části subjektů neodpovídá skutečnosti.
   Kandidáti na revizi = firmy, jejichž dvojice (2008, 2025) má v matici podíl pod např. 5 %.

## 10. Otevřené otázky k rozhodnutí

Otázky z PR #21 jsou rozhodnuté (R8–R12, kap. 1). Nové otevřené otázky nejsou.
