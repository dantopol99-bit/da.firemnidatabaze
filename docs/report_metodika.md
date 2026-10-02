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

**Upřesnění pravidla 3 (schváleno 30. 9. 2026):** (a) zkoumané území a zadané srovnávací kraje se při
sekundárním slučování přeskočí, pokud je z čeho vybírat; (b) právní formy se slučují v rámci FO a v rámci PO.

## Schválená rozhodnutí – Blok 3 (30. 9. 2026)

| # | rozhodnutí | jak je v kódu |
|---|---|---|
| 8 | **Minimální rozsah**: pod 100 registrovanými subjekty se report nevydá. CLI místo toho vypíše návrh vyšší úrovně (okres → kraj, třída/skupina → oddíl → sekce) i s počty. | `report.MIN_ROZSAH`, výjimka `MalyRozsah` s `navrhy_vyssi_urovne()`; CLI skončí kódem 4 (i s `--pdf`) |
| 9 | **Spolehlivost zařazení**: podíl subjektů „jen do sekce“ (v téže sekci a území) vůči počtu oboru. Nad 25 % nese report varování na titulní straně i v metodické poznámce. | ukazatel `SPOLEHLIVOST_JEN_SEKCE` (T01), `meta.varovani`; zveřejní se, jen je-li počet „jen do sekce“ zveřejnitelný |
| 10 | **Dynamika**: v0 používá RES05 (dynamika území) a RESDP jako kontext za ČR s poznámkou o jiné jednotce (podnik). Dynamika obor × území je mimo v0 (vznikne z archivu snímků RES). | T11 (RES05), nová T12 (RESDP00, `res.csu_demografie`); míry ČSÚ zaokrouhlené na 2 desetinná místa ve výpočetní vrstvě |
| 11 | **Hlavní sdělení** nesou počet, lokalizační koeficient, hustota a pořadí. Velikostní profil jde až do strukturní kapitoly, vždy s podílem „Neuvedeno“. | shrnutí a dlaždice v PDF; velikost jen v kapitole Struktura |

## Schválené rozhodnutí – Blok 4 (1. 10. 2026)

| # | rozhodnutí | jak je v kódu |
|---|---|---|
| 12 | **Výklad má dvě vrstvy.** Stroj píše „co je vidět“ a detektor zjištění. „Proč“ a „co z toho plyne“ píše analytik do `reporty/vyklad/<id_reportu>.md`. Sazba text vloží a kontrola čísel na něj platí stejně. Dokud soubor chybí nebo obsahuje zástupný text, nejde použít `--vyklad-schvalen`. | `report_vyklad` (strojová vrstva + `nacti_vyklad_analytika`), `report_zjisteni`, `report_pdf.vysazej` (blokace schválení, kontrola čísel a zakázaných slov i v textu analytika); `report` při prvním výpočtu založí soubor se zástupným textem |

**Rozšíření rozhodnutí 12 (schváleno 1. 10. 2026):** body shrnutí na straně 2 píše analytik do oddílu
`## Shrnutí` téhož souboru (body oddělené prázdným řádkem). Dlaždice (počet, LQ, hustota, pořadí) a
varování zůstávají strojové. Chybí-li oddíl nebo obsahuje zástupný text, platí blokace
`--vyklad-schvalen` jako u ostatních oddílů. Strojová zjištění detektoru se ze strany 2 přesunula do
kapitol (nejvýš 5 nejsilnějších v každé) a celá do přílohy „Zjištění detektoru“; pravidlo „5 nejsilnějších,
nejvýš 2 téhož typu“ pro shrnutí tím zaniká.

**Čísla v textu analytika:** sazba převede mezeru (i pevnou) mezi dvěma číslicemi na úzkou nezlomitelnou
mezeru, tedy na oddělovač tisíců. „1 000“ se proto vysází nerozdělené a kontrola čísel ho čte jako
1000; špatně zapsané tisícové číslo (např. „14 798“ místo „14 799“) kontrola zachytí. Seznam čísel
oddělený jen mezerou („2023 2024“) se tím sloučí v jedno číslo a kontrolu neprojde – je třeba psát
čárku nebo spojku.

Pravidla Bloku 4 zadaná spolu s rozhodnutím 12:

- **Benchmarky struktury** (T13–T17): u FO/PO, právních forem, velikosti FO a PO (včetně
  „Neuvedeno“) a věkových pásem se vedle zkoumaného území uvádí týž obor za ČR a za zadané
  srovnávací kraje. Práh a slučování platí pro každé území zvlášť (viz níže).
- **Míra zániku PO** (T18) = zaniklé PO v roce / stav PO k 1. 1. téhož roku × 100, pro území, ČR
  a srovnávací kraje; za neúplný poslední rok i za srovnatelné období 1. 1.–den snímku všech let.
- **Detektor zjištění** (T19, `zjisteni.json`): typ, číselná síla, čísla s odkazem na tabulku,
  jedna věta bez interpretace; řazení podle síly. Rozdíl pod 3 % relativně se nehlásí a v textu se
  popisuje jako „srovnatelné“.
- **Čeština**: názvy území v 6. pádě z ručně psané tabulky `reporty/cestina/lokativ.yaml`
  (14 krajů, 77 okresů, ČR); text nikdy nepoužije „v území <název>“.
- **Shrnutí** (strana 2): původně 5 nejsilnějších zjištění; od rozšíření rozhodnutí 12 ho píše analytik.

**Rozhodnutí 13 (1. 10. 2026): zdroje dat.** robots.txt a podmínky provozu poskytovatelů zdrojů se
respektují vždy, bez výjimek, i pro měření a testy. Sbírka listin (`or.justice.cz`, robots.txt
`Disallow: /ias/` pro všechny automatické klienty; podmínky provozu: omezení nad 3 000 požadavků denně
nebo 50 za minutu, CAPTCHA) se automaticky nepoužívá. Firemní účetní údaje ze Sbírky listin jen po
dohodě s Ministerstvem spravedlnosti. Webové služby ISIR (port 8443) z cloudového prostředí nejsou
dostupné; obcházet přes webové rozhraní se nebudou.

**Upřesnění k rozhodnutí 1:** kontrola zakázaných slov povoluje jen sousloví **„aktivní podnik(y)“**.
Je to oficiální jednotka ČSÚ v demografii podniků (RESDP00, rozhodnutí 10), ne označení
registrovaných subjektů.

Osnova a pravidla sazby PDF: [`report_osnova.md`](report_osnova.md).

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
| `zjisteni.json` | zjištění detektoru seřazená podle síly, s pravidly detektoru, citací a označením |
| `priloha.xlsx` | „Přehled“, každá tabulka na vlastním listu, „Metodika“ (celý katalog + příznak použití), „Zdroj a licence“ |
| `_interni/kontrola.json` | všechny proměnné včetně skrytých a lineární vztahy mezi tabulkami; **nezveřejňuje se** (je v `.gitignore`) |

Tabulky: T01 základní ukazatele, T02 srovnání s ČR a zadanými kraji, T03 pořadí 14 krajů, T04 okresy
kraje, T05 FO/PO, T06 právní forma, T07/T08 velikostní profil FO/PO, T09 věková struktura,
T10 zaniklé PO z RES od 2023, T11 vznik a zánik v území podle ČSÚ (RES05), T12 demografie podniků ČR
(RESDP00), T13–T17 benchmarky struktury (ČR a srovnávací kraje), T18 míra zániku PO, T19 zjištění.

## Benchmarky struktury (T13–T17)

- Sloupce: zkoumané území (podíly převzaté z T05–T09), ČR (chybí, je-li území ČR), zadané
  srovnávací kraje a rozdíl proti ČR v procentních bodech (z hodnot zaokrouhlených na 0,1).
- Řádky určuje zkoumané území: položky, které jsou v něm sloučené do „ostatní“, se v ostatních
  sloupcích **předem** sloučí taky (jinak by sloupce nebyly srovnatelné). Má-li benchmark navíc
  položky, které v území vůbec nejsou, jdou rovněž do „ostatní“ (řádek s poznámkou „ve zkoumaném
  území žádné“).
- Každé benchmarkové území prochází **vlastním** potlačením: položka pod prahem v benchmarku se
  sloučí do jeho „ostatní“ (v jeho sloupci pomlčka), je-li „ostatní“ pod prahem, přidá se další
  nejmenší. Formy se slučují v rámci FO a PO; velikost FO a PO se zveřejní jen při zveřejněném
  rozdělení FO/PO v daném území.
- Proměnné benchmarků mají předponu (`cr:`, `kraj:<kód>:`) a vlastní rovnice, takže je pokrývá
  kontrola dopočtu. Kraj s jediným okresem se jako benchmark okresu nepoužije (byl by totožný se
  zkoumaným územím a obešel by jeho potlačení).
- Položka, která je skrytá **jen kvůli srovnatelnosti** (předem sloučená) a je na prahu nebo nad
  ním, se nechrání (`chranit: false` v interní kontrole): pro dopočet je dál neznámá, ale její
  případné dopočítání nic neprozradí.

## Míra zániku PO (T18)

- **Stav PO k 1. 1. Y** = existující PO se vznikem před 1. 1. Y + PO zaniklé 1. 1. Y nebo později
  (rekonstrukce z jednoho snímku RES). Výpočet ověřuje identitu stav(Y+1) = stav(Y) − zániky(Y) + vzniky(Y)
  a pro poslední rok stav − zániky + vzniky = dnešní počet PO.
- **Míra za rok** = zaniklé PO v roce / stav k 1. 1. × 100 (jen úplné roky); **míra za srovnatelné
  období** = zaniklé PO 1. 1.–den snímku / stav k 1. 1. × 100 (všechny roky, tedy i neúplný poslední).
- **Ochrana**: počty pod prahem se nezveřejní. Navíc se nezveřejní zániky za srovnatelné období, pokud
  by šlo odečtem od celoročních zániků dopočítat zániky ve zbytku roku pod prahem, a stav, pokud by
  z dvou po sobě jdoucích stavů a zániků šel dopočítat počet vzniků pod prahem. Tyto vztahy jsou
  v interní kontrole jako obecné lineární rovnice (`{"koef": …}`).
- **Omezení** (poznámka v T18): jen PO (zaniklé FO mají v otevřených datech jen IČO a datum zániku);
  okno 4 let 2023–2026, protože RES uchovává zaniklé subjekty jen 4 roky po zániku (nejstarší zánik ve
  snímku k 15. 9. 2026 je 1. 10. 2022, rok 2023 je tedy úplný); obor a sídlo podle snímku, jejich
  změny v čase se nepromítají.

## Detektor zjištění (T19, `zjisteni.json`)

Pracuje jen se zveřejněnými čísly tabulek. Typy:

| typ | co srovnává | tabulky |
|---|---|---|
| `odchylka_od_cr` | LQ proti 1, hustota proti ČR, každá položka struktury proti ČR | T02, T13–T17 |
| `zmena_trendu` | míra zániku PO posledního roku proti průměru předchozích let (za rok i za srovnatelné období), proti ČR, a vývoj (index poslední/první rok) proti ČR | T18 |
| `rozdily_uvnitr_uzemi` | hustota okresů proti kraji a proti ČR, rozpětí mezi okresy | T04, T02 |
| `aktivita_oboru` | podíl se zjištěnou aktivitou v sekci proti všem oborům kraje (ČSÚ) | T01 |
| `divergence_poradi` | pořadí podle počtu proti pořadí podle hustoty (kraj mezi 14 kraji, okresy v kraji) | T01, T04 |

- **Stálé ID** (od 2. 10. 2026): `Z` + typ (OD, TR, UZ, AK, PO, MZ, EK) + `-` + 4 písmena z otisku toho,
  co zjištění srovnává (typ, podtyp, tabulka/řádek/sloupec převzatých čísel; ne hodnoty ani pořadí), např.
  `ZTR-IMTV`. Nové zjištění proto stávající nepřečísluje a odkazy v textu analytika zůstávají platné;
  pořadí podle síly je v poli `poradi`. ID neobsahuje číslice, aby ho kontrola čísel v PDF nečetla jako
  číslo. Test ověřuje, že každý odkaz v souboru výkladu existuje v `zjisteni.json`. Rok v popisu řádku
  (např. míra zániku 2025) je součástí otisku, takže u nového snímku s jinými roky vzniknou nová ID.
- **Síla** = |hodnota / srovnání − 1|; u divergence pořadí |p1 − p2| / (počet území − 1). Obě míry
  jsou bezrozměrné a 0 znamená shodu, takže jdou řadit společně.
- **Nehlásí se**: rozdíl pod 3 % relativně (v textu „srovnatelné“); položky struktury s podílem pod 5 %
  v území i v ČR (relativní rozdíl malých podílů je nestabilní); posun pořadí okresů o jedno místo.
- Každé zjištění nese čísla s odkazem na tabulku, řádek a sloupec. Vypočtená čísla (průměr let,
  index, relativní rozdíl) jsou v tabulce T19, takže jsou v JSON i XLSX a projdou kontrolou PDF.
- **V PDF**: nejsilnější zjištění (nejvýš 5) u každé kapitoly, všechna v příloze „Zjištění detektoru“.
  Shrnutí na straně 2 píše analytik (rozšíření rozhodnutí 12).

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
5. Žádné skryté číslo nejde dopočítat (i přes obecné rovnice míry zániku PO). Každé „ostatní“ má aspoň
   2 položky a je nad prahem.
6. Čísla odpovídají interním proměnným (u tabulek s více územími podle `zaklady` po sloupcích).
7. Citace (ČSÚ, RES, datum snímku, CC BY 4.0) a označení jsou v JSON i na každém listu.
8. Žádné „firm…“ ani „aktivn…“ v textech JSON ani XLSX.

## Dynamika vzniku a zániku v DataStatu (rozhodnutí 4 – zjištění)

| sada | obsah | obor | území | použití |
|---|---|---|---|---|
| **RES05** Vznik a zánik ekonomických subjektů | vzniklé, zaniklé; FO/PO/celkem; čtvrtletí 2020-Q1 – 2026-Q2 (roky jen v souhrnném výběru za ČR) | **ne** | ČR, kraje, okresy | T11 – dynamika **celého území**, ne oboru |
| RES06 / RES0A Registrace ekonomických subjektů | registrace; 9 skupin CZ-NACE | ano (hrubě) | **jen ČR** | nepoužito |
| RESDP00/01 Demografie podniků | aktivní, vzniklé, zaniklé **podniky**, míry; 18 odvětví | ano | **jen ČR** | T12 – jen kontext ČR (rozhodnutí 10; jiná jednotka: podnik) |
| RES06UP Úpadky | úpadky; 9 skupin CZ-NACE | ano (hrubě) | jen ČR | nepoužito |

**Tabulka vzniku a zániku v členění kraj × sekce v DataStatu neexistuje.** Ukazatel `DYN_OBOR_CSU`
je proto v katalogu „nelze naplnit“. Náhradou v reportu jsou dynamika území (T11), zaniklé PO oboru
z RES (T10) a věková struktura (T09). V RES05 je vidět mimořádný výkyv: v 1. čtvrtletí 2023 zaniklo
v ČR **200 977 FO** (obvykle 15–45 tis. za čtvrtletí).

## Zaměstnanost a mzdy (Blok 6, T20–T21)

Co ČSÚ v DataStatu publikuje (ověřeno v katalogu sad a výběrů, 1. 10. 2026):

| výběr (sada) | území | odvětví | roky | zjišťování | použití |
|---|---|---|---|---|---|
| **MZDCRRT2** (MZDCRR) | 14 krajů | 19 sekcí CZ-NACE + celkem | 2010–2022 (2022 předběžně) | roční, pracovištní metoda | T20 – obor × kraj |
| **MZDCRRT1** (MZDCRR) | ČR | sekce + celkem | 2010–2022 | roční | T20 – ČR |
| **MZDRT2** (MZDR) | ČR | sekce + B–E + celkem | 2000–2025 | čtvrtletní, kumulace za rok | T21 – ČR × sekce pro novější roky |
| **MZDRT5** (MZDR) | ČR, regiony, kraje | jen celkem | 2011–2025 | čtvrtletní, pracovištní metoda | T21 – kraje za všechna odvětví |
| WGEN02BT02 (WGEN02B) | ČR, kraje | jen celkem | 2011–2024 | Struktura mezd | nepoužito: medián za kraje jen podle pohlaví, bez celku a bez odvětví |

- **Kraj × sekce** existuje jen v ročním zjišťování (MZDCRR) a končí rokem 2022. V čtvrtletním
  zjišťování (MZDR) ČSÚ kombinaci kraj × odvětví zakazuje (pravidla výběru sady). Okresy ani oddíly
  CZ-NACE ČSÚ nepublikuje.
- Obě sady mají přepočtené počty (na plný úvazek) i fyzické osoby; report používá **přepočtené počty**
  a **průměrnou mzdu na přepočtené počty**. Načítají se oba typy (`res.csu_mzdy`).
- **Medián** za kraj × odvětví ČSÚ nepublikuje, report proto uvádí průměr a říká to v poznámce.
- **Nic se nedopočítává z jiných úrovní.** Kde obor × kraj chybí, kapitola to říká a použije nejbližší
  publikovanou úroveň s označením: okres → kraj, oddíl/skupina/třída → sekce, roky po 2022 → kraj za
  všechna odvětví a ČR za sekci (T21). Obor přes více sekcí → T20 a T21 se nezveřejní s důvodem.
  Roční a čtvrtletní zjišťování se v řadách nespojují (hodnoty se mírně liší).
- Odvozené ukazatele jsou jen poměry publikovaných čísel téhož zjišťování a roku: podíl kraje na ČR,
  podíl oboru na zaměstnancích území, mzda proti ČR (ČR = 100) a proti všem odvětvím území (= 100).
  Zaměstnanci se zaokrouhlují na 0,1 tis., mzdy na celé Kč (jak ČSÚ publikuje). Práh 10 subjektů se
  na publikované údaje ČSÚ nevztahuje.
- **Zaměstnanci ≠ registrované subjekty**: statistika zahrnuje jen zaměstnance v pracovním poměru
  (přepočtené počty), ne podnikající fyzické osoby. Pilot: 6,4 tis. zaměstnanců stavebnictví
  v Libereckém kraji proti 14 799 registrovaným subjektům, z nichž 88,3 % jsou FO.
- **Detektor** má typ `mzdy_zamestnanost`: mzda v oboru kraj proti ČR, mzda v oboru proti všem
  odvětvím (kraj proti ČR), podíl oboru na zaměstnancích (kraj proti ČR), vývoj mzdy a zaměstnanců
  (index posledního roku k prvnímu) proti ČR. Pravidlo 3 % platí stejně.
- Import: `python -m firemni_databaze.res_import mzdy` (i součást `agregaty`), každý výběr ve vlastní
  dávce `dev.import_davka`.

## Ekonomický profil – regionální účty Eurostatu (Blok 7b, T22–T23)

**Zdroj a podmínky** (ověřeno 1. 10. 2026, před prvním datovým požadavkem): robots.txt
`ec.europa.eu` pro `User-agent: *` nezakazuje cestu `/eurostat/api/` (zakázané jsou jen staré
`/eurostat/SDMX/diss-web/rest/`, vyhledávání a data-browser). Licence (Copyright notice and free re-use of
data): další užití, i komerční, je povoleno s uvedením zdroje; úpravy dat se musí výslovně označit
a připojit doložku, že za ně Eurostat neodpovídá. Citace: kód sady s odkazem do data browseru a datum
stažení – v reportu v dalších zdrojích, poznámkách tabulek a na listu „Zdroj a licence“. Stahuje se
API JSON-stat (`/eurostat/api/dissemination/statistics/1.0/data/<sada>`), 3 požadavky s pauzou 2 s.

Co Eurostat publikuje pro Česko (stav sad: HPH aktualizace 23. 3. 2026, zaměstnanost 31. 7. 2026,
náhrady 10. 2. 2026):

| sada | ukazatel | území | odvětví | roky | jednotky |
|---|---|---|---|---|---|
| `nama_10r_3gva` | hrubá přidaná hodnota v základních cenách | ČR, regiony soudržnosti, **14 krajů** | A*10 (+ C, G–J, K–N, O–U) | 2000–2024 | mil. Kč běžné ceny (CP_MNAC), mil. Kč v cenách předchozího roku (PYP_MNAC); také EUR |
| `nama_10r_3empers` | zaměstnanost (národní účty) | ČR, **14 krajů** | A*10 | 2000–2024 | tis. osob: zaměstnaní (EMP), zaměstnanci (SAL), sebezaměstnaní (SELF) |
| `nama_10r_2coe` | náhrady zaměstnancům | ČR, **regiony soudržnosti** (ne kraje) | A*10 | 2000–2024 | mil. Kč (MIO_NAC) |

- **Okresy** v regionálních účtech nejsou. **Stálé ceny** jsou jen jako ceny předchozího roku
  (objemová změna rok k roku); objem za více let vzniká řetězením těchto změn.
- **Příznaky**: Eurostat u žádné hodnoty neuvádí příznak předběžnosti (p) ani odhadu (e); poslední rok
  2024 se ale při revizích může změnit (poznámka v T22).
- **Skupiny A*10** (sekce → skupina): A; B, D, E → B–E (Průmysl kromě stavebnictví); C (samostatně);
  **F (samostatně)**; G, H, I → G–I; J; K; L; M, N → M–N; O, P, Q → O–Q; R, S, T, U → R–U. Odpovídá-li
  skupina sekci přesně (A, C, F, J, K, L), tabulka to uvádí; jinak je označena jako širší skupina
  (nejbližší publikovaná úroveň). Oddíl a nižší úrovně → skupina jeho sekce, okres → kraj, vždy
  s označením. Obor přes více skupin → T22/T23 se nezveřejní s důvodem.
- **Konzistence s ČSÚ**: HPH Libereckého kraje celkem 2023 = 213 778 mil. Kč u Eurostatu i v DataStatu
  (NUC06R) – regionální účty Eurostatu jsou údaje ČSÚ předané Eurostatu.
- **Produktivita** = HPH v běžných cenách / zaměstnaní (obojí z regionálních účtů, tedy konzistentní
  definice), v tis. Kč na zaměstnanou osobu (ne na hodinu ani na plný úvazek).
- **Proč se zaměstnanost liší od kapitoly Zaměstnanost a mzdy**: Eurostat (národní účty) počítá osoby
  včetně sebezaměstnaných (podnikajících FO) podle místa pracoviště; ČSÚ ve statistice mezd uvádí jen
  zaměstnance v pracovním poměru přepočtené na plné úvazky. Pilot 2022: 13,23 tis. zaměstnaných ve
  stavebnictví Libereckého kraje (Eurostat; z toho 33,8 % sebezaměstnaných) proti 6,4 tis. přepočtených
  zaměstnanců (ČSÚ). Ani jedno číslo není počet registrovaných subjektů.
- **Náhrady zaměstnancům / HPH** jen za region soudržnosti (kraj Liberecký patří do Severovýchodu
  spolu s Královéhradeckým a Pardubickým) – vždy označeno; srovnávací kraj ze stejného regionu má
  stejné hodnoty.
- **Detektor** má typ `ekonomika`: produktivita, podíl skupiny na HPH území, podíl sebezaměstnaných
  a objem HPH (kraj proti ČR); podíl náhrad na HPH (region soudržnosti proti ČR). Pravidlo 3 % platí.
- **Pododdíl „Koncentrace a firemní ukazatele“** zůstává „zatím nedostupné“ (rozhodnutí 13).
- Import: `python -m firemni_databaze.res_import eurostat` (i součást `agregaty`), tabulka
  `res.eu_regionalni_ucty`, každá sada ve vlastní dávce `dev.import_davka` (zdroj `EUROSTAT`).

## Modelové odhady ekonomického profilu (Blok 8, T24–T27)

**Nejsou to fakta.** Kombinují zdroje modelem, uvádějí se jen jako pásmo s označením „modelový odhad“
a **nevstupují do detektoru zjištění** (ten pracuje jen s fakty; test to hlídá).

**Zdroj podnikových poměrů – Eurostat SBS** (`sbs_sc_ovw`, aktualizace 30. 9. 2026; robots.txt a licence
jako u regionálních účtů). Pro ČR publikuje sekce i oddíly CZ-NACE (pro F: F, 41, 42, 43) × velikostní
třídy podle **počtu zaměstnaných osob** (včetně majitelů), roky **2021–2024**:

| ukazatel | třídy |
|---|---|
| podniky, zaměstnané osoby | 0–1, 2–9, 0–9, 10–19, 20–49, 50–249, 250+, celkem |
| přidaná hodnota, čistý obrat, hrubý provozní přebytek, mzdy aj. | jen 0–9, 10–19, 20–49, 50–249, 250+, celkem |

Peněžní údaje jsou **jen v mil. EUR**; převod ročním průměrným kurzem (`ert_bil_eur_a`, 2024: 25,12 Kč/EUR).
Pro sekci F ani oddíly 41–43 nejsou žádné buňky skryté jako důvěrné (2021–2024); rozdělení 0–1 a 2–9 osob
se u peněžních údajů nepublikuje vůbec. Regionální (krajské) SBS podle velikosti Eurostat nemá.

**Postup** (poslední společný rok regionálních účtů a SBS, nyní 2024; struktura subjektů z RES ke dni
snímku – spojení různých let je součástí modelu a je uvedeno u každé tabulky):
1. Počty subjektů oboru v kraji podle tříd SBS z KATPO (110–130 → 0–9, 210 → 10–19, 220–230 → 20–49,
   240–320 → 50–249, ostatní → 250+), zúžené jednotným podílem se zjištěnou aktivitou (ČSÚ, sekce × kraj;
   struktura se tím nemění, protože ČSÚ podíl podle velikosti nepublikuje). „Neuvedeno“ (KATPO 000):
   základní varianta – PO do nejmenší třídy, FO do „bez zaměstnanců“ (obojí 0–9); alternativní varianta –
   poměrně podle známé struktury FO, resp. PO. Obě varianty dávají dolní a horní mez pásma.
2. Krajská přidaná hodnota skupiny (regionální účty, mil. Kč) se rozpočítá mezi třídy podle počtu subjektů
   × celostátní přidané hodnoty **na podnik** třídy (v kraji známe jen počty subjektů, ne osoby).
   Součet tříd = krajský celek přesně (výpočet to ověřuje).
3. Obrat třídy = přidaná hodnota třídy × celostátní poměr obrat / přidaná hodnota v třídě.
4. Typický obrat podniku třídy = celostátní obrat / počet podniků (průměr, ne medián) – fakt za ČR;
   pásmo = minimum–maximum mezi oddíly sekce.
5. Koncentrace = podíl přidané hodnoty a obratu tříd s 10+ a 50+ osobami.
6. Marže (hrubý provozní přebytek / obrat) – fakt za ČR, ne odhad za kraj.

**Ochrana malých buněk:** třída s méně než 10 subjekty v kraji (RES, v obou variantách) se sloučí s vyšší;
podíl nad hranicí (10+, 50+) se nezveřejní, pokud by hranice rozdělila sloučenou skupinu.

**Kontrola konzistence (T27):** model se stejnými vstupy za celou ČR proti celostátním hodnotám SBS.
Pilot (F, 2024): celostátní podíl každé z pěti tříd na přidané hodnotě leží **uvnitř pásma modelu**;
obrat sekce model **nadhodnocuje o 35,6 %** (od bližší meze), protože přidaná hodnota národních účtů
(409 647 mil. Kč) je o 36,1 % vyšší než přidaná hodnota SBS (300 901 mil. Kč) – národní účty zahrnují
i neregistrovanou ekonomiku a oceňují jinak. **Absolutní obrat je proto nespolehlivý**, podíly tříd
a koncentrace spolehlivější. Model na vlastních celostátních počtech podniků SBS vrací přesně hodnoty
SBS (jednotkový test).

**Omezení:** jen obor zadaný jako celá sekce, která je samostatnou skupinou A*10 (A, C, F, J, L; K a
některé další sekce SBS nepokrývá); KATPO (zaměstnanci) ≠ třídy SBS (zaměstnané osoby) na hranicích
tříd; podíl aktivních jen souhrnně za sekci a kraj; celostátní poměry platí pro kraj jen za předpokladu,
že se podniky téže třídy v kraji neliší od průměru ČR.

## Ukazatele, které nelze (plně) naplnit

| ukazatel | proč |
|---|---|
| `DYN_OBOR_CSU` vznik a zánik v oboru × území | ČSÚ tabulku nepublikuje (viz výše) |
| `ZANIK_PO_RES` jen částečně | zaniklé FO mají v otevřených datech jen IČO a datum zániku (GDPR), nejde je přiřadit oboru ani území; zaniklé starší 4 let v RES nejsou |
| `MIRA_ZANIKU_PO`, `MIRA_ZANIKU_PO_OBD` jen částečně | jen PO a jen okno 2023–2026; u menších území je část let skrytá pravidlem prahu a dopočtu |
| `DYN_VZNIK_CSU`, `DYN_ZANIK_CSU` jen částečně | jen celé území, ne obor; poslední rok neúplný |
| `AKTIVNI_PODIL_SEKCE_KRAJ` jen částečně | jen je-li obor přesně jedna sekce publikovaná samostatně (ne B, C, D, E ani oddíl) |
| `AKTIVNI_PODIL_KRAJ` za okres | ČSÚ podíl aktivity za okres podle převažující činnosti nepublikuje, uvádí se krajský |
| `OBYVATELE` okresu Praha | v OBY02A nemá Praha okres; použije se kraj Hlavní město Praha (totožné území) |
| `PORADI_*` pro ČR | nemá smysl |
| `EKON_*` jen částečně | jen skupiny A*10, ne oddíly; jen kraje, ne okresy; náhrady zaměstnancům jen za region soudržnosti |
| `MZDY_*` obor × kraj jen částečně | ČSÚ publikuje jen sekce, jen kraje, jen roky 2010–2022 (roční zjišťování); medián vůbec |
