# CZ-NACE 2025 – sjednocená klasifikace odvětví

Cíl: spojit firmu s oborem napříč produkty (Firemní databáze, Oborově-regionální report, parlamentní
a aktérská analytika). Primární verze ve všech výstupech je **CZ-NACE 2025**, **CZ-NACE 2008** zůstává
jako historický atribut. Obě verze se ukládají s platností v čase a verze je u každého záznamu výslovně
(některé kódy CZ-NACE 2008 mají v CZ-NACE 2025 jiný obsah, např. oddíly 58–63, sekce J–U).

Stav: schéma `obor` (migrace, číselníky, kódy firem z RES a ARES, matice přechodů, odvození, rozhraní
`obor.v_firma_obor_aktualni`, kontroly). Oborově-regionální report zatím počítá podle CZ-NACE 2008
(rozhodnutí 5 metodiky), přepnutí je v [dalších krocích](#9-další-kroky).

## 1. Schválená rozhodnutí

1. Zdroj kódů 2025 pro současné firmy je atribut **NACE2025 z RES** (přes ARES nebo z otevřených dat
   RES od ČSÚ). Převodník ČSÚ slouží jen jako záloha.
2. Nejednoznačné převody (historické stavy před 2026, firmy bez kódu 2025) se řeší **empirickou vahou**
   z dvojího kódování v RES: nejčastější cíl, jeho podíl jako jistota, `zdroj = 'odvozeno'`.
3. Primární verze je CZ-NACE 2025. Verze 2008 jen jako historický atribut.

## 2. Zdroje a podmínky (ověřeno 18. 10. 2026)

| údaj | zdroj | robots.txt / podmínky | použito |
|---|---|---|---|
| kódy firem 2008 a 2025 (hlavní i vedlejší) – populace | otevřená data RES, `opendata.csu.gov.cz/soubory/od/od_org03/` (`res_data.csv`, `res_pf_nace.csv`) | robots.txt neexistuje (404); CC BY 4.0 | **ano** – hlavní zdroj |
| kódy firem z jádra (jednotlivá IČO) | ARES, `ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty-res/{ico}` | robots.txt zakazuje jen `/cms/` | **ano** – loader `ares_import` |
| číselník CZ-NACE 2008 a 2025, úrovně 1–5 | iSMS ČSÚ, `apl2.czso.cz/iSMS/do_cis_export` (klasifikace 80004 a 80143); odkazuje na něj [stránka ČSÚ ke CZ-NACE 2025](https://csu.gov.cz/klasifikace-ekonomickych-cinnosti-cz-nace-platna-od-1-1-2025) | robots.txt neexistuje (404) | **ano** |
| převodník NACE Rev. 2 ↔ Rev. 2.1 (třídy) | [csu.gov.cz/prevodniky-v105](https://csu.gov.cz/prevodniky-v105), Eurostat V1.05 | robots.txt `csu.gov.cz` zakazuje jen 3 cesty, AI crawlery neblokuje | **ano** |
| převodník 5místných položek CZ-NACE 2008 ↔ 2025 | tamtéž, ČSÚ 12/2025 | tamtéž | **ano** |
| číselníky `CZ_NACE_RES`, `CZ_NACE_RES2025` (s pseudokódy RES) | `vdb.czso.cz/opendata/ciselniky` | **robots.txt `User-agent: *` / `Disallow: /`** – blokuje všechny automatické klienty | **ne** – krok zastaven, viz níže |

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
(2 543 párů), `sekce2025_a10.csv`.

**Převodník** sestavuje `nace_ciselniky.sestav`: úrovně 1–4 z obou směrů převodníku Eurostatu (CZ-NACE
2008/2025 = NACE Rev. 2/2.1 až po třídu), podtřídy, které se národně člení, z převodníku ČSÚ pro 5místné
položky, a podtřídy „xxxx0“ (třída se nečlení) z převodníku tříd. Třída 2025 **46.89** nemá v Rev. 2
předchůdce (Eurostat: „not possible to link“).

### Pravidla platnosti a historie

- Kód z RES: `platnost_od` = datum poslední aktualizace záznamu v RES (`DDATPAKT` z otevřených dat,
  `datumAktualizace` z ARES) – kód platí nejpozději od tohoto dne. U kódu 2025 to může být datum
  před 1. 1. 2025: jde o zařazení stavu, který trvá od té doby (ČSÚ překódoval existující stavy).
  `platnost_do` = datum zániku, nebo datum aktualizace, se kterou další snímek kód nahradil.
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
| `prevodnik_jediny_cil` | všichni kandidáti z převodníku mají na úrovni L společného předka (vč. vazby N:1) | ten předek, jistota 1 |
| `empiricky` | v matici je pro `k` aspoň 20 firem | nejčastější cíl, jistota = jeho podíl |
| `nejednoznacne` | jinak | `kod` NULL, `priznak = 'nejednoznacne'`, `kandidati` z převodníku |

Metoda `prevodnik_jediny_cil` rozšiřuje zadání „vazba 1:1 → jistota 1“: je-li podle převodníku jediný
možný cíl (vazba N:1, nebo se kandidáti na vyšší úrovni sejdou v jednom oddílu či sekci), je výsledek
logicky jistý. Bez ní by např. kód s 15 firmami, jehož všechny kandidátní třídy leží v jednom oddílu,
dostal oddíl NULL. **Ke schválení** (kap. 10).

Odvozuje se pro každý stav hlavní činnosti 2008 z RES, ke kterému neexistuje kód 2025 z RES pro tentýž
stav – dnes zaniklé subjekty, které zanikly před dvojím kódováním, v budoucnu i starší stavy z archivu
snímků.

KONTROLY_ZDE

## 8. Rozhraní pro ostatní produkty

`obor.v_firma_obor_aktualni` – jeden řádek na IČO, poslední známá hlavní činnost:

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

**Spojení s parlamentní a aktérskou analytikou** jde přes `oddil` (2 místa, CZ-NACE 2025):

```sql
SELECT z.zakon_id, f.ico
FROM analytika.zakon_oddil z                       -- tagy zákonů do oddílů CZ-NACE 2025
JOIN obor.v_firma_obor_aktualni f ON f.oddil = z.oddil
WHERE f.platnost_do IS NULL AND NOT f.je_pseudokod
  AND coalesce(f.jistota_oddil, 0) >= 0.8;         -- práh jistoty volí konzument
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

Hotovo v této změně: kroky 0–4 a 6, z kroku 5 loader ARES/RES (obě verze do `firma_nace`), převodní
tabulka sekce 2025 → A*10 a náhrada blokovaného zdroje číselníků. Zbývá:

1. **Přepnout Oborově-regionální report na CZ-NACE 2025** (report je v tomto repozitáři). Vyžaduje nové
   rozhodnutí místo rozhodnutí 5 metodiky („v0 = CZ-NACE Rev. 2“) – změní čísla pilotu a tím i podklad
   textu analytika (`reporty/vyklad/`), který se sám upravovat nesmí. Místa ke změně:
   - `report.py`: `KLASIFIKACE = 80004`; `urci_obor` (číselník `res.cis_nace` 80004 → `obor.nace_ciselnik`
     verze 2025); `nacti_populaci` / dotazy nad `res.subjekt.nace` a `JOIN res.cis_nace … 80004`
     (populace, „zařazeno jen do sekce“, „obor neurčen“) → `obor.v_firma_obor_aktualni` (pro historický
     snímek `obor.firma_nace` k datu); `navrhy_vyssi_urovne`.
   - srovnání s ČSÚ: `res.csu_agregat` z RES02QT1 (Rev. 2) → RES02QNACET1 (CZ-NACE 2025, importér už umí,
     `res_import.nacti_agregaty(conn, 'RES02QNACET1')`), `res.v_srovnani_csu`.
   - `ODVETVI_DEMOGRAFIE` (RESDP00), `nacti_mzdy` (MZDCRR/MZDR), `nacti_sbs` (SBS) a `SKUPINY_A10`
     (regionální účty) jsou v Rev. 2: sekce 2025 se na ně převede přes `obor.nace_sekce_a10`
     (`sekce_rev2`, `a10_rev2`) a do `meta.poznamky` / metodické poznámky PDF se přidá věta z kap. 8
     („spojení dvou verzí na úrovni sekcí“). U sekcí J/K 2025 (obě → J Rev. 2) mzdy a SBS za oddíly
     nejdou.
   - `res.prunik_souhrn`, `res.v_pilot_f_liberecky`, `res.v_pocty_kraj_sekce`, `res.v_kvalita`
     (výchozí klasifikace 80004), `reporty/katalog_ukazatelu.yaml`, `docs/report_metodika.md`, vzorový
     pilot `reporty/ukazky/`.
2. **Archiv snímků**: po každém snímku RES (2× měsíčně) spustit `nace_firmy res` a `matice`; historie
   kódů v `firma_nace` vzniká až řadou snímků (dnes jeden).
3. **Konec dvojího kódování (31. 12. 2028)**: až RES přestane dodávat `NACE`, loader otevřené kódy 2008
   uzavře k datu aktualizace záznamu. Rozhodnout, zda je místo toho nechat otevřené jako „poslední známý“.
4. `dev.subjekt_verze.cz_nace` obsahuje CZ-NACE **2025** (všechny činnosti), název to neříká – doplnit
   komentář sloupce, nebo ho nahradit odkazem na `obor.firma_nace`.
5. Odvození vedlejších činností (dnes jen hlavní) – jen pokud je některý produkt potřebuje.
6. Kontrola skutečné činnosti: ČSÚ připouští, že `NACE2025` u části subjektů neodpovídá skutečnosti.
   Kandidáti na revizi = firmy, jejichž dvojice (2008, 2025) má v matici podíl pod např. 5 %.

## 10. Otevřené otázky k rozhodnutí

1. **Metoda `prevodnik_jediny_cil`** (kap. 5): smí jedinečný cíl podle převodníku (vazba N:1, kandidáti
   v jednom oddílu/sekci) dostat jistotu 1 i mimo vazbu 1:1? Bez ní by část oddílů a sekcí zůstala NULL.
2. **Přepnutí reportu na CZ-NACE 2025** (kap. 9, bod 1): nahradit rozhodnutí 5 metodiky? Změní čísla
   pilotu F × Liberecký kraj a analytik musí napsat nový výklad. A přechodně vydávat obě verze?
3. **Náhrada vdb.czso.cz** (kap. 2): souhlas s iSMS + čtyřmi pseudokódy RES jako zdrojem `res.cis_nace`?
   Alternativou je požádat ČSÚ o výjimku pro VDB.
4. **Práh 20 firem** pro empirickou váhu a **doporučený práh jistoty** pro konzumenty (návrh: oddíl
   s `jistota_oddil ≥ 0,8`, jinak vykazovat jako nejednoznačné).
5. **Platnost kódu 2025 před 1. 1. 2025** (kap. 4): ponechat `platnost_od` = datum aktualizace záznamu
   (zpětné zařazení stavu), nebo ořezat na 1. 1. 2025?
6. **Kontrola ARES**: `ares_import` nově posílá 3 dotazy na IČO místo 2 (navíc `ekonomicke-subjekty-res`).
   Pro hromadné běhy hlídat limity provozovatele ARES.
