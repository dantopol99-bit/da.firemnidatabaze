# Ověření zániků PO – sekce F × Liberecký kraj (snímek RES k 15. 10. 2026)

Zjištění ZTR-IMTV, ZTR-CISP a ZTR-LQXC pilotu ukazují, že míra zániku právnických osob ve stavebnictví
v Libereckém kraji vyskočila v roce 2025 na 5,92 % proti 2,62 % v ČR. Ověřuje se, zda jde o skutečné
zániky, o artefakt převodu na CZ-NACE 2025, o náhodu malé základny, nebo o jeden shluk.

Postup předepisuje [`report_metodika.md`](report_metodika.md), oddíl „Ověření silné změny trendu“.
Všechna čísla jsou agregáty. Počty pod 10 se podle pravidla 3 neuvádějí ani tam, kde by šly dopočítat
ze součtu; v takových případech jsou kategorie sloučené nebo je uveden podíl v pásmu. Seznam IČO
a údaje o osobách zůstaly v interním pracovním adresáři mimo repozitář.

**Závěr: skutečné zániky, ne artefakt převodu ani shluk. Příčinou je administrativní vlna: rejstříkový
soud (Krajský soud v Ústí nad Labem – pobočka v Liberci) v roce 2025 hromadně rušil nečinné obchodní
korporace v celém kraji, napříč obory.** Specifický signál stavebnictví nad touto vlnou je malý
(kap. 5 a 6).

## 1. Klasifikace: CZ-NACE 2025 proti CZ-NACE 2008

Zdroj kódu u zaniklých PO v sekci F (CZ-NACE 2025) v kraji:

| rok zániku | zaniklé PO | zdroj kódu 2025 |
|---|---:|---|
| 2023 | 35 | všechny odvozené z CZ-NACE 2008 |
| 2024 | 49 | všechny odvozené z CZ-NACE 2008 |
| 2025 | 103 | všechny z RES |
| 2026 (do 15. 10.) | 62 | všechny z RES |

Hranice je ostrá v celé ČR: PO zaniklé před 1. 1. 2025 nemají v RES kód CZ-NACE 2025, PO zaniklé od
1. 1. 2025 ho mají všechny. Zdroj zatřídění čitatele se tedy mění **přesně v roce skoku**. Proto je
rozhodující přepočet podle CZ-NACE 2008, kde mají kód z RES všechny roky.

Míra zániku PO stejnou metodou jako report (T18): zaniklé PO v roce / stav PO k 1. 1. téhož roku.

| | 2023 | 2024 | 2025 |
|---|---:|---:|---:|
| Liberecký kraj – CZ-NACE 2025 (report) | 2,10 % | 2,85 % | **5,92 %** |
| Liberecký kraj – CZ-NACE 2008 (přepočet, snímek 15. 10. 2026) | 2,08 % | 2,93 % | **5,86 %** |
| Liberecký kraj – CZ-NACE 2008 (archivní pilot, snímek 15. 9. 2026) | 2,08 % | 2,93 % | **5,86 %** |
| ČR – CZ-NACE 2025 | 2,59 % | 2,61 % | 2,62 % |
| ČR – CZ-NACE 2008 | 2,57 % | 2,59 % | 2,62 % |

Počty pro rok 2025 v kraji: CZ-NACE 2025 stav 1 739, zániky 103; CZ-NACE 2008 stav 1 759, zániky 103.
Všech 103 zaniklých PO roku 2025 je ve stavebnictví podle obou verzí. **Skok je i podle CZ-NACE 2008,
převod na CZ-NACE 2025 ho nezpůsobil.**

## 2. Konzistence čitatele a jmenovatele

Čitatel i jmenovatel stojí na stejném zatřídění každého subjektu (rozhraní `obor.v_firma_obor_aktualni`,
automatické spojení). Zdroj kódu ale není stejný ve všech letech:

| stav PO k 1. 1. (CZ-NACE 2025) | 2023 | 2024 | 2025 |
|---|---:|---:|---:|
| živé PO (kód z RES) | 1 414 | 1 506 | 1 574 |
| PO zaniklé později, kód z RES | 165 | 165 | 165 |
| PO zaniklé později, kód odvozený | 84 | 49 | 0 |

V letech 2023 a 2024 je v čitateli i ve jmenovateli část PO s odvozeným kódem, v roce 2025 žádná.
Dopad vyčísluje přepočet podle CZ-NACE 2008 (jednotné zatřídění z RES): rozdíl v míře je nejvýš
0,08 procentního bodu (2023 +0,02, 2024 −0,08, 2025 +0,06). **Nesoulad zdrojů na závěr nemá vliv.**

## 3. Velikost základny (Poisson)

Očekávaný počet zániků v kraji při celostátní míře téhož roku a interval běžného kolísání podle
Poissonova rozdělení (CZ-NACE 2025; podle CZ-NACE 2008 vychází prakticky stejně):

| rok | stav PO k 1. 1. | míra ČR | očekáváno | interval 95 % | interval 99,9 % | skutečnost |
|---|---:|---:|---:|---|---|---:|
| 2023 | 1 663 | 2,59 % | 43,1 | 31–56 | 23–66 | 35 |
| 2024 | 1 720 | 2,61 % | 44,9 | 32–58 | 25–68 | 49 |
| 2025 | 1 739 | 2,62 % | 45,6 | 33–59 | 25–69 | **103** |

Roky 2023 a 2024 leží v běžném kolísání. **Rok 2025 je daleko mimo** (pravděpodobnost aspoň 103 zániků
při celostátní míře je řádově 10⁻¹³). Základna 1,7 tis. PO není tak malá, aby skok vysvětlila náhoda.
Poissonův model předpokládá nezávislé zániky; hromadné soudní rušení (kap. 5) tento předpoklad
porušuje, a proto skok vytváří.

## 4. Shluky

**Čas.** Zániky roku 2025 jsou rozložené přes celý rok: 1. čtvrtletí 21, 2. čtvrtletí 28,
3. čtvrtletí 39, 4. čtvrtletí 15. V žádném dni nezaniklo 10 a více subjektů; ve 19 dnech zaniklo
po dvou a více subjektech (dohromady 42 zániků), což odpovídá dávkovému zpracování soudem, ne jedné
události.

**Adresa sídla.** Společné adresní místo RÚIAN mají jen jednotky subjektů (méně než 10); 48 subjektů
nemá v RES adresní místo vyplněné, u nich adresa posoudit nejde.

**Osoby** (OR, otevřená data dataor.justice.cz, úplné výpisy Krajského soudu v Ústí nad Labem za rok
2025 – s.r.o., v.o.s., a.s., družstva; jen interní zpracování). Subjekty se společným členem
statutárního orgánu, společníkem nebo prokuristou tvoří jen dvojice: 10 subjektů v 5 dvojicích,
žádný větší shluk. Likvidátor jmenovaný soudem se u různých subjektů neopakuje.
**Skok netáhne skupina propojených společností.**

## 5. Způsob zániku

**Liberecký kraj, sekce F** (RES, způsob zániku ZPZAN):

| rok | zaniklé PO | z toho 04 „zrušení PO bez likvidace bez nástupců“ |
|---|---:|---|
| 2023 | 35 | 25 (71 %) |
| 2024 | 49 | více než 80 % |
| 2025 | 103 | **více než 90 %** |

Zbytek tvoří hlavně likvidace (01); přesné počty se kvůli pravidlu 3 neuvádějí.

**OR – právní důvod výmazu** u zaniklých PO roku 2025 (dohledáno v OR přes 90 % ze 103):

| důvod | subjektů |
|---|---:|
| **zrušení soudem bez likvidace** (§ 105a odst. 3 zákona č. 304/2013 Sb., o veřejných rejstřících) | **76** |
| zrušení soudem, výmaz na návrh likvidátora jmenovaného soudem (§ 82 zákona č. 304/2013 Sb.) | 16 |
| ostatní (konkurs, přeměna, dobrovolná likvidace) nebo v OR nedohledáno | 11 |

U 34 subjektů OR zaznamenává, že živnostenský úřad Magistrátu města Liberce oznámil zánik jejich
posledního živnostenského oprávnění. To je typický podnět, na který soud zahajuje řízení o zrušení
nečinné obchodní korporace. Přeměny (fúze, rozdělení) jsou jednotky a ukončením podnikání nejsou.

**ČR, sekce F** (RES, CZ-NACE 2025), pro srovnání:

| rok | zaniklé PO | likvidace (01) | bez likvidace bez nástupců (04) | přeměny (02, 03) a ostatní |
|---|---:|---:|---:|---:|
| 2023 | 1 319 | 909 | 366 | 44 |
| 2024 | 1 373 | 820 | 513 | 40 |
| 2025 | 1 429 | 749 | 625 | 55 |

V ČR převažuje likvidace; v Libereckém kraji v roce 2025 zrušení soudem bez likvidace.

## 6. Je to stavebnictví, nebo celý kraj?

Míra zániku PO podle CZ-NACE 2008 (sekce F proti ostatním oborům), Liberecký kraj proti zbytku ČR:

| | 2023 | 2024 | 2025 | 2025 bez kódu 04 |
|---|---:|---:|---:|---:|
| Liberecký kraj – sekce F | 2,08 % | 2,93 % | **5,86 %** | pod 0,6 % |
| Liberecký kraj – ostatní obory | 1,96 % | 2,28 % | **4,79 %** | 0,90 % |
| zbytek ČR – sekce F | 2,59 % | 2,58 % | 2,52 % | 1,52 % |
| zbytek ČR – ostatní obory | 2,54 % | 2,47 % | 2,59 % | 1,89 % |

Zaniklých PO ve **všech oborech** Libereckého kraje bylo 485 (2023), 581 (2024) a **1 225 (2025)**,
z toho kódem 04 288, 388 a **1 009**. Skok je tedy celokrajský a nese ho zrušení bez likvidace.
Ve stavebnictví je míra zániku o něco vyšší než v ostatních oborech kraje (poměr 1,22 v roce 2025,
1,29 v roce 2024), ale ten rozdíl existoval i před vlnou. **Bez kódu 04 je míra zániku stavebnictví
v kraji pod 0,6 %, nižší než v ČR (1,52 %).** (Přesná hodnota by se stavem PO prozradila počet
pod 10.) Pro srovnání: Ústecký kraj (stejný krajský soud) má podíl kódu 04
na zánicích PO dlouhodobě kolem 90 %; pobočka v Liberci se k podobné praxi přidala v roce 2025.

## 7. Závěr

| hypotéza | výsledek |
|---|---|
| artefakt převodu na CZ-NACE 2025 | **ne** – podle CZ-NACE 2008 je skok stejný (5,86 %), rozdíl metod nejvýš 0,08 p. b. |
| malá základna / náhoda | **ne** – 103 zániků proti očekávaným 45,6, mimo interval 99,9 % |
| jeden shluk (skupina společností) | **ne** – nejvýš dvojice propojených subjektů, zániky rozložené přes rok |
| skutečné zániky | **ano** – subjekty byly zrušeny a vymazány z OR |
| příčina | hromadné rušení nečinných korporací rejstříkovým soudem v celém kraji (§ 105a zákona o veřejných rejstřících), ne zhoršení stavebního trhu |

Zjištění „míra zániku PO v oboru je v kraji výrazně vyšší než v ČR“ platí, ale popisuje **úklid
rejstříku**, ne ekonomický signál oboru. Pro výklad to podporuje první hypotézu analytika (výmazy
spících společností) a vyvrací třetí (shluk jednoho vlastníka); druhou (skutečný tlak na obor) data
nepodporují.

## Zdroje a podmínky

- RES – otevřená data ČSÚ, snímek k 15. 10. 2026 (CC BY 4.0); `res.subjekt` (DDATZAN, ZPZAN, KODADM),
  `obor.v_firma_obor_aktualni`, `res.cis_nace` (CZ-NACE 2008).
- OR – otevřená data Ministerstva spravedlnosti, dataor.justice.cz (robots.txt neexistuje), úplné
  výpisy `sro|vos|as|dr-full-usti_nad_labem-2025`, staženo 19. 10. 2026. Údaje o osobách zpracovány
  jen interně a mimo repozitář; ven jen agregáty. ARES (endpoint VR) vymazané subjekty nevrací
  (HTTP 404), proto se nepoužil.
- Archivní pilot `reporty/vystupy/F__CZ051__2026-09-15` (CZ-NACE 2008, nahrazeno).
