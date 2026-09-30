# Oborově-regionální report – metodika výpočetní vrstvy (v0)

Stav: **Blok 2 – výpočetní vrstva bez PDF**. Zdroj dat a jeho omezení popisuje
[`res_zdroj.md`](res_zdroj.md), ukazatele [`reporty/katalog_ukazatelu.yaml`](../reporty/katalog_ukazatelu.yaml).

## Schválená rozhodnutí (30. 9. 2026)

Rozhodnutí k nálezům z Bloku 1. Platí pro všechny výstupy reportu.

| # | rozhodnutí | jak je v kódu |
|---|---|---|
| 1 | Report vždy uvádí **„registrované subjekty“**, nikdy „firmy“ ani „aktivní“. Jako kontext uvádí **krajský podíl subjektů se zjištěnou aktivitou podle ČSÚ** z DataStatu. Aktivitu po subjektech nedopočítáváme. | ukazatel `AKTIVNI_PODIL_KRAJ` (RES02QT1, u okresu jeho kraj); kontrola výstupu odmítne texty se slovy „firm…“ a „aktivn…“ |
| 2 | Velikostní profil (KATPO) **zvlášť pro FO a PO**. „Neuvedeno“ se nikdy neslučuje s „bez zaměstnanců“ a jeho podíl se vždy zobrazí. | tabulky `T07_velikost_fo`, `T08_velikost_po`; „Neuvedeno“ je samostatné pásmo (podléhá jen prahu) |
| 3 | **Ochrana proti dopočtu**: buňky pod prahem 10 se v každém členění slučují do „ostatní“. Je-li „ostatní“ samo pod prahem, přidá se k němu další nejmenší buňka. Skryté číslo nesmí jít dopočítat odečtem od součtu ani z jiné tabulky téhož reportu. | `report_potlaceni.potlac()` + ověření lineární soustavou `dopocitatelne()` při výpočtu i v kontrolním skriptu |
| 4 | „Vzniky podle let“ se jmenují **„věková struktura existujících subjektů“**. Dynamiku vzniku a zániku bereme z publikovaných tabulek ČSÚ (DataStat) na úrovni kraj × sekce, pokud existují. Zániky z RES jen od roku 2023, výkyv FO 2–3/2023 označit jako mimořádný. | `T09_vekova_struktura` (+ průměr/medián v T01); `T11_dynamika_csu` z RES05 (**kraj × sekce neexistuje**, viz níže); `T10_zaniky_po` od 2023; řádek 2023 nese poznámku o mimořádném výkyvu |
| 5 | Klasifikace v0: **CZ-NACE Rev. 2** (sloupec `NACE`). | `KLASIFIKACE = 80004` |
| 6 | Subjekty s NACE jen na úrovni sekce: v reportu za oddíl nebo nižší úroveň samostatný řádek **„zařazeno jen do sekce“**. Pseudokód 00 = **„obor neurčen“**. | T01: `DOPL_JEN_VYSSI` (pro každý nadřazený kód oboru), `DOPL_OBOR_NEURCEN` |
| 7 | Každý výstup nese **citaci zdroje** (ČSÚ, RES, datum snímku, CC BY 4.0) a označení **„Odvozené údaje, nejde o oficiální statistiku ČSÚ.“** | `meta.citace` a `meta.oznaceni` v JSON, řádky 2–3 každého listu XLSX, list „Zdroj a licence“, hlavička MD; ověřuje kontrola |

## Výpočet

```bash
python -m firemni_databaze.report --obor F --uzemi CZ051
python -m firemni_databaze.report --obor 10 --uzemi "Kraj Vysočina" --srovnani CZ031,CZ053
python -m firemni_databaze.report --obor 62 --uzemi Jeseník --datum 2026-09-15
python -m firemni_databaze.report_kontrola reporty/vystupy/*
```

- **Obor**: kódy CZ-NACE Rev. 2 na úrovni sekce, oddílu, skupiny nebo třídy, i seznam (`41,42`).
  Kódy se nesmí překrývat (`41,4120` je chyba). Pseudokódy a podtřídy zadat nelze. Subjekt patří do
  oboru, je-li jeho převažující činnost zařazena na úrovni zadaného kódu nebo nižší. Subjekty zařazené
  jen výš (např. jen „J“ u oddílu 62) jsou v řádku „zařazeno jen do …“.
- **Území**: `CZ`, kraj (CZ-NUTS 3 nebo název), okres (kód 109 nebo název). Určuje ho sídlo subjektu.
- **Datum snímku**: výchozí je poslední načtený, jinak `--datum`.
- **Srovnání**: automaticky se srovnává jen s ČR (T02) a s pořadím všech 14 krajů (T03). U kraje
  a okresu navíc s okresy kraje (T04). Srovnávací kraje zadává člověk parametrem `--srovnani`.
- **Populace**: registrované subjekty bez data zániku v daném snímku (definice ČSÚ). FO = statistická
  právní forma 101–108, 424, 425 (podle metodiky ČSÚ; součty FO/PO se shodují s RES01Q ČSÚ do +0,7 %,
  což odpovídá časovému posunu), PO = ostatní.

### Výstup (`reporty/vystupy/<obor>__<území>__<datum>/`)

| soubor | obsah |
|---|---|
| `vysledek.json` | `meta` (zadání, obor, území, populace, citace, označení, další zdroje, licence) a `tabulky` (sloupce s kódem ukazatele z katalogu, řádky se zveřejnitelnými čísly; skrytá čísla ve výstupu **nejsou**) |
| `vysledek.md` | tytéž tabulky pro čtení |
| `priloha.xlsx` | „Přehled“, každá tabulka na vlastním listu, „Metodika“ (celý katalog + příznak použití), „Zdroj a licence“ |
| `_interni/kontrola.json` | všechny proměnné včetně skrytých a lineární vztahy mezi tabulkami; **nezveřejňuje se** (je v `.gitignore`) |

Tabulky: T01 základní ukazatele, T02 srovnání s ČR a zadanými kraji, T03 pořadí 14 krajů, T04 okresy
kraje, T05 FO/PO, T06 právní forma, T07/T08 velikostní profil FO/PO, T09 věková struktura,
T10 zaniklé PO z RES od 2023, T11 vznik a zánik v území podle ČSÚ (RES05).

## Ochrana malých buněk – přesný postup

1. **Nulové buňky** se do členění nezařazují (nejsou ani zveřejněné, ani sloučené). Nulový součet
   se považuje za známý a tabulka se označí „v území žádné“.
2. **Celé členění pod prahem** (součet < 10): nezveřejní se nic, ani součet. Je-li pod prahem
   samotný počet v území, skryje se i vše, co z něj plyne (podíly, LQ, hustota, pořadí, věk, všechna
   členění).
3. **Primární slučování**: buňky < 10 → „ostatní“.
4. **Sekundární slučování**: dokud je „ostatní“ < 10, přidává se další nejmenší zveřejněná buňka.
   Tím má „ostatní“ vždy aspoň dvě položky a jeho hodnota je aspoň 10. **Upřesnění**: zkoumané území
   a zadané srovnávací kraje jsou chráněné a přeskočí se, pokud je z čeho vybírat. Jinak by se
   zkoumaný kraj mohl skrýt jen proto, že je „další nejmenší“ v pořadí krajů.
5. Když se do „ostatní“ sloučí úplně všechno (zbyl by jen součet), tabulka se nezveřejní.
6. **Mezitabulkové vazby** jsou řešené konstrukcí:
   - právní formy se slučují **v rámci FO a v rámci PO** (jinak by skrytou formu šlo dopočítat ze
     zveřejněných součtů FO a PO);
   - je-li FO nebo PO pod prahem, **rozdělení FO/PO se nezveřejní**. Formy se pak slučují přes obě
     skupiny a velikostní profily FO a PO se nezveřejní (jejich součty by rozdělení prozradily;
     slučovat FO a PO do jednoho profilu zakazuje rozhodnutí 2);
   - počty krajů (T03), okresů (T04), srovnání (T02) a základní ukazatele (T01) sdílejí tytéž
     proměnné, takže skrytá hodnota je skrytá všude, včetně odvozených ukazatelů;
   - T04 se nezveřejní, je-li skrytý počet kraje.
7. **Ověření**: všechny tabulky se převedou na proměnné a lineární vztahy (součet tabulky, podskupiny
   FO/PO, sloučené „ostatní“) a Gaussovou eliminací nad zlomky se ověří, že jednotkový vektor žádné
   skryté proměnné neleží v prostoru rovnic doplněném o zveřejněné proměnné. Výpočet v takovém případě
   skončí chybou a kontrolní skript to ověřuje znovu z výstupních souborů.
   **Neposuzuje se** intervalový dopočet z nezápornosti (např. „ostatní = 11 ze dvou položek → každá
   ≤ 9“). To je vlastnost samotného pravidla slučování, ne chyba.
8. Pořadí krajů a okresů se počítá ze skutečných počtů všech území. Zveřejní se jen u zveřejněných
   počtů. U chráněné buňky tak pořadí může prozradit, že některá skrytá buňka je větší (jen pořadí,
   ne hodnotu).

## Kontrola výstupu (`report_kontrola`)

1. Každé číslo z JSON je ve stejné buňce XLSX a listy tabulek existují.
2. Každé číslo má ukazatel z katalogu.
3. Žádný zveřejněný počet (typ `pocet`) není pod prahem.
4. Odvozené ukazatele (podíl, index, pořadí, průměr) jsou jen u zveřejněných počtů.
5. Žádné skryté číslo nejde dopočítat. Každé „ostatní“ má aspoň 2 položky a je nad prahem.
6. Čísla odpovídají interním proměnným.
7. Citace (ČSÚ, RES, datum snímku, CC BY 4.0) a označení jsou v JSON i na každém listu.
8. Žádné „firm…“ ani „aktivn…“ v textech JSON ani XLSX.

## Dynamika vzniku a zániku v DataStatu (rozhodnutí 4 – zjištění)

| sada | obsah | obor | území | použití |
|---|---|---|---|---|
| **RES05** Vznik a zánik ekonomických subjektů | vzniklé, zaniklé; FO/PO/celkem; čtvrtletí 2020-Q1 – 2026-Q2 (roky jen v souhrnném výběru za ČR) | **ne** | ČR, kraje, okresy | T11 – dynamika **celého území**, ne oboru |
| RES06 / RES0A Registrace ekonomických subjektů | registrace; 9 skupin CZ-NACE | ano (hrubě) | **jen ČR** | nepoužito |
| RESDP00/01 Demografie podniků | aktivní, vzniklé, zaniklé **podniky**, míry; 18 odvětví | ano | **jen ČR** | nepoužito (jiná jednotka: podnik, ne ekonomický subjekt) |
| RES06UP Úpadky | úpadky; 9 skupin CZ-NACE | ano (hrubě) | jen ČR | nepoužito |

**Tabulka vzniku a zániku v členění kraj × sekce v DataStatu neexistuje.** Ukazatel `DYN_OBOR_CSU`
je proto v katalogu „nelze naplnit“. Náhradou v reportu jsou dynamika území (T11), zaniklé PO oboru
z RES (T10) a věková struktura (T09). V RES05 je vidět mimořádný výkyv: v 1. čtvrtletí 2023 zaniklo
v ČR **200 977 FO** (obvykle 15–45 tis. za čtvrtletí).

## Ukazatele, které nelze (plně) naplnit

| ukazatel | proč |
|---|---|
| `DYN_OBOR_CSU` vznik a zánik v oboru × území | ČSÚ tabulku nepublikuje (viz výše) |
| `ZANIK_PO_RES` jen částečně | zaniklé FO mají v otevřených datech jen IČO a datum zániku (GDPR), nejde je přiřadit oboru ani území; zaniklé starší 4 let v RES nejsou |
| `DYN_VZNIK_CSU`, `DYN_ZANIK_CSU` jen částečně | jen celé území, ne obor; poslední rok neúplný |
| `AKTIVNI_PODIL_SEKCE_KRAJ` jen částečně | jen je-li obor přesně jedna sekce publikovaná samostatně (ne B, C, D, E ani oddíl) |
| `AKTIVNI_PODIL_KRAJ` za okres | ČSÚ podíl aktivity za okres podle převažující činnosti nepublikuje, uvádí se krajský |
| `OBYVATELE` okresu Praha | v OBY02A nemá Praha okres; použije se kraj Hlavní město Praha (totožné území) |
| `PORADI_*` pro ČR | nemá smysl |
