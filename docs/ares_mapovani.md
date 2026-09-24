# ARES → identitní jádro: návrh mapování (ke schválení)

Stav: **schváleno a implementováno** (`ares_import.py`, `ares_mapovani.py`).
Kapitoly 1–4 popisují původní rozbor vzorku; kde se liší od schválených
rozhodnutí na konci dokumentu, platí rozhodnutí.

## Vzorek

- Staženo 24. 9. 2026 z veřejného REST API ARES
  (`https://ares.gov.cz/ekonomicke-subjekty-v-be/rest`).
- **78 subjektů**: 40× s.r.o. (112), 25× a.s. (121), 6× FO podnikatel (101),
  4× družstvo (205), 2× k.s. (113), 2× v.o.s. (111). Mezi nimi firmy
  v likvidaci, s insolvencí, se změnou jména, se zahraničním akcionářem.
- Pro každý subjekt dva dotazy:
  - `GET /ekonomicke-subjekty/{ico}`: základní záznam (souhrn ze všech registrů),
  - `GET /ekonomicke-subjekty-vr/{ico}`: výpis z veřejného (obchodního) rejstříku
    **včetně historie**. Jen z něj jsou orgány, společníci a podíly.
- Surová data leží lokálně v `data/ares_vzorek/` (necommituje se).

## 1. Co ARES o firmě vrací

### Základní záznam (`/ekonomicke-subjekty/{ico}`), jen aktuální stav

| pole | příklad | poznámka |
|---|---|---|
| `ico`, `icoId` | `27082440` | subjekt bez IČO má jen `icoId` = `ARES_00363883` |
| `obchodniJmeno` | `Alza.cz a.s.` | |
| `pravniForma` / `pravniFormaRos` | `121` / `121` | u FO se liší (`101` vs `100`) |
| `datumVzniku`, `datumZaniku` | `2003-08-26` | |
| `datumAktualizace` | `2025-11-24` | vhodné pro přírůstkovou synchronizaci |
| `dic` | `CZ27082440` | |
| `sidlo{…}` | viz adresa | strukturovaná adresa s kódem RÚIAN |
| `adresaDorucovaci` | `radekAdresy1..3` | **jen textové řádky**, bez struktury a bez RÚIAN |
| `czNace`, `czNace2008` | `["62", "47250"]` | obory činnosti |
| `financniUrad` | `006` | |
| `seznamRegistraci` | `stavZdrojeVr: AKTIVNI`, `stavZdrojeIr: AKTIVNI`, … | stav subjektu v 16 registrech (OR, RES, RŽP, DPH, insolvenční rejstřík…) |
| `primarniZdroj` | `ros` | |
| `dalsiUdaje[]` | | kopie jména/sídla/právní formy po jednotlivých zdrojích |

Pole „stav subjektu“ (aktivní / v likvidaci / zaniklý) **v základním záznamu není**.

### Výpis z OR (`/ekonomicke-subjekty-vr/{ico}`), s historií

Každá položka nese `datumZapisu` a `datumVymazu` (kdy byl údaj zapsán do OR a kdy
z něj vymazán). Chybějící `datumVymazu` znamená, že údaj platí.

| sekce | obsah |
|---|---|
| `obchodniJmeno[]` | historie jmen |
| `pravniForma[]` | historie právní formy |
| `adresy[]` | historie sídla (`typAdresy` = vždy `SIDLO`) |
| `stavSubjektu` | `AKTIVNI` / `HISTORICKY`: stav **záznamu v OR**, ne firmy |
| `spisovaZnacka[]` | soud, oddíl, vložka (`MSPH`, `B`, `8573`) |
| `zakladniKapital[]` | vklad + splaceno |
| `statutarniOrgany[]` | jednatelé, představenstvo, správní rada, statutární ředitel, komplementáři, **prokura, likvidátor** |
| `ostatniOrgany[]` | dozorčí rada, kontrolní komise (družstva) |
| `spolecnici[]` | společníci + podíly (vklad, velikost podílu, splaceno); komanditisté; členové družstva |
| `akcionari[]` | jediný akcionář |
| `zpusobJednani[]`, `pocetClenu[]` | u orgánů |
| `cinnosti.predmetPodnikani[]` | předmět podnikání (text) |
| `ostatniSkutecnosti[]` | volný text (vstup do likvidace, přeměny…) |
| `akcie[]`, `insolvence[]`, `konkursy[]`, `odstepneZavody[]` | |

Člen orgánu je `fyzickaOsoba` (jméno, příjmení, tituly, datum narození,
občanství, adresa bydliště) **nebo** `pravnickaOsoba` (IČO, jméno, právní forma,
adresa). K tomu `clenstvi.funkce.nazev` (volný text funkce) a data
`vznikFunkce`/`zanikFunkce` a `vznikClenstvi`/`zanikClenstvi`.

## 2. Mapování na naše tabulky

### `subjekt`

| sloupec | ← ARES |
|---|---|
| `ico` | `ico` |
| `import_davka_id` | nová dávka `zdroj = 'ARES'` |

### `subjekt_verze`

| sloupec | ← ARES | pozn. |
|---|---|---|
| `nazev` | VR `obchodniJmeno[].hodnota` (FO: základní `obchodniJmeno`) | |
| `pravni_forma_kod` | VR `pravniForma[].hodnota` / `pravniForma` | kódy ČSÚ |
| `stav_kod` | **odvozený**, viz níže | |
| `datum_vzniku` | `datumVzniku` | |
| `datum_zaniku` | `datumZaniku` | |
| `platnost_od` / `platnost_do` | body změn z `obchodniJmeno[]` + `pravniForma[]` (`datumZapisu`/`datumVymazu`) | každá změna jména/formy = nová verze |

Odvození `stav_kod` (navrhované pořadí):
1. `datumZaniku` vyplněno → `ZANIKLY`
2. `seznamRegistraci.stavZdrojeIr = AKTIVNI` → `INSOLVENCE`
3. platný orgán `LIKVIDATOR` ve VR (záložně „v likvidaci“ ve jméně) → `LIKVIDACE`
4. jinak `AKTIVNI`

### `adresa`

| sloupec | ← ARES (`sidlo` / `adresy[].adresa`) |
|---|---|
| `ruian_kod` | `kodAdresnihoMista` |
| `ulice` | `nazevUlice` (v obcích bez ulic chybí) |
| `cislo_popisne` | `cisloDomovni`, **jen když** `typCisloDomovni = 1` |
| `cislo_orientacni` | `cisloOrientacni` + `cisloOrientacniPismeno` (`12a`) |
| `obec` | `nazevObce` |
| `cast_obce` | `nazevCastiObce` |
| `psc` | `psc` (číslo → text 5 znaků), u cizích adres `pscTxt` |
| `stat` | `kodStatu` (už ISO alpha-2: `CZ`, `SK`, `CY`, `DE`…) |
| `text_puvodni` | `textovaAdresa` |

### `subjekt_adresa`

| typ | ← ARES | platnost |
|---|---|---|
| `SIDLO` | VR `adresy[]` (historie), jinak základní `sidlo` | `datumZapisu` / `datumVymazu` |
| `DORUCOVACI` | `adresaDorucovaci`: jen text, uložit do `text_puvodni` a jen když se liší od sídla | neznámá |
| `PROVOZOVNA` | **ARES v těchto dvou endpointech neposkytuje** (jsou v RŽP) | |

### `osoba` / `osoba_verze` (členové orgánů, kteří jsou FO)

| sloupec | ← `fyzickaOsoba` |
|---|---|
| `klic_parovani` | `dev.klic_osoby(jmeno, prijmeni, datumNarozeni)` |
| `jmeno`, `prijmeni` | `jmeno`, `prijmeni` (často VELKÝMI písmeny) |
| `titul_pred`, `titul_za` | `titulPredJmenem`, `titulZaJmenem` |
| `datum_narozeni` | `datumNarozeni` |
| `statni_prislusnost` | `statniObcanstvi` |
| (bydliště) | **zahodit**, podle rozhodnutí v `05_osoba.sql` |

### `vazba`

| sloupec | ← ARES |
|---|---|
| `ico` | firma, jejíž výpis čteme |
| `clen_osoba_id` | `fyzickaOsoba` → osoba |
| `clen_ico` | `pravnickaOsoba.ico` |
| `role_kod` | odvozeno z `typOrganu` + `nazevOrganu` + `funkce.nazev` (tabulka níže) |
| `organ_puvodni` | `nazevOrganu` + ` / ` + `funkce.nazev` |
| `vklad` | `podil[].vklad.hodnota` (`"8000;00"` → 8000.00) |
| `vklad_mena` | `typObnos = KORUNY` → `CZK` |
| `podil_text` | `podil[].velikostPodilu.hodnota` |
| `podil_procento` | `PROCENTA` přímo; `TEXT` s „10 %“ nebo „1/5“ → přepočet; jinak NULL |
| `splaceno_procento` | `podil[].splaceni.hodnota` (když `PROCENTA`) |
| `platnost_od` | `vznikClenstvi` → `vznikFunkce` → `datumZapisu` (první vyplněné) |
| `platnost_do` | `zanikClenstvi` → `zanikFunkce` → `datumVymazu` |

Mapování rolí:

| ARES (`typOrganu` / `funkce.nazev`) | → `role_kod` | výskyt ve vzorku |
|---|---|---|
| STATUTARNI_ORGAN / „jednatel“ | `JEDNATEL` | 105 |
| STATUTARNI_ORGAN / „předseda představenstva“ | `PREDSEDA_PREDSTAVENSTVA` | 136 |
| STATUTARNI_ORGAN / „**místopředseda** představenstva“ | ❌ **chybí** | 127 |
| STATUTARNI_ORGAN / „člen představenstva“, „člen“ | `CLEN_PREDSTAVENSTVA` | 550+ |
| STATUTARNI_ORGAN „Správní rada“ | `CLEN_SPRAVNI_RADY` (předseda ❌) | 19 |
| STATUTARNI_ORGAN „Statutární ředitel“ | ❌ **chybí** | 2 |
| STATUTARNI_ORGAN „předseda / místopředseda družstva“ | ❌ **chybí** | 16 |
| KOMPLEMENTAR | `KOMPLEMENTAR` | 10 |
| DOZORCI_RADA / předseda | `PREDSEDA_DOZORCI_RADY` | 112 |
| DOZORCI_RADA / **místopředseda** | ❌ **chybí** | 51 |
| DOZORCI_RADA / člen | `CLEN_DOZORCI_RADY` | 390 |
| KONTROLNI_KOMISE (družstva) | ❌ **chybí** celý orgán | 40 |
| PROKURA | `PROKURISTA` | 163 |
| LIKVIDATOR | `LIKVIDATOR` | 5 |
| SPOLECNIK | `SPOLECNIK` | 173 |
| KOMANDITISTA | `KOMANDITISTA` | 20 |
| AKCIONAR | `JEDINY_AKCIONAR` | 47 |
| VKLAD_CLEN_DRUZSTVA | mimo rozsah (člen družstva) | 1 |
| insolvenční / konkursní správce, vedoucí odštěpného závodu | mimo rozsah | 21 |

## 3. Nesoulady a pole, se kterými jsme nepočítali

### Nesoulady, které blokují import (je potřeba rozhodnout)

1. **Zahraniční právnická osoba bez IČO jako člen/společník/akcionář.**
   14 z 50 PO členů ve vzorku nemá IČO (např. jediný akcionář Alzy
   `L.S. INVESTMENTS LIMITED`, Kypr). `vazba` vyžaduje buď `clen_osoba_id`,
   nebo `clen_ico`, takže se takový člen nedá uložit.
2. **Člen s IČO, které v `subjekt` ještě není.** `clen_ico` má FK na `subjekt`.
   Buď dotáhnout i tuto firmu, nebo založit „holou“ identitu (`subjekt` bez verze).
3. **Subjekty bez IČO** (`icoId = ARES_…`, např. staré JZD) doména `dev.ico`
   nepřijme. Návrh: přeskočit a zalogovat.
4. **`stav_kod` je jedna hodnota, ale stavy se kombinují.** Např. Riegrova
   pekárna Sever s.r.o. je zároveň v likvidaci **a** v insolvenci.
5. **Chybějící role v číselníku:** místopředseda představenstva (127×),
   místopředseda DR (51×), kontrolní komise družstva (40×), předseda/místopředseda
   družstva, statutární ředitel, předseda správní rady.

### Nesoulady v datech

6. **Dvě sady dat u vazby.** `vznikFunkce`/`zanikFunkce` (skutečnost) a
   `datumZapisu`/`datumVymazu` (zápis do OR, někdy o roky později). Máme jen
   `platnost_od/do`. Navrhuji do platnosti dávat skutečnost a zápis/výmaz
   buď zahodit, nebo přidat sloupce `datum_zapisu_or`/`datum_vymazu_or`.
7. **Každá změna u člena = nový záznam v ARES.** Změna příjmení nebo funkce
   se v OR zapíše jako výmaz starého a zápis nového člena. Ve vzorku je 6 osob
   se stejným jménem a datem narození, ale jiným příjmením (Hájková →
   Babincová). Náš `klic_osoby` z nich udělá **dvě různé osoby**.
8. **Chybějící datum narození** u 398 z 2 526 FO členů (16 %, hlavně starší
   zápisy), takže klíč bude `…|?` a hrozí chybné sloučení.
9. **Velikost podílu je volný text:** `4/5`, `10 %`, `padesát procent`,
   `60 % (10 podílů, každý o velikosti po 6 %)`, zlomek `1;3`. Procento půjde
   dopočítat jen někdy.
10. **Čísla s desetinným středníkem:** `"8000;00"`, `"100;00"`.
11. **`typCisloDomovni = 2` je číslo evidenční**, ne popisné (rekreační
    objekty). Nemáme na něj sloupec, a kdyby šlo do `cislo_popisne`, byla by
    to chyba.
12. **Doručovací adresa** je jen 1–3 textové řádky, často jen „Česká
    republika“ nebo kopie sídla.
13. **`hash_adresy` zahrnuje `text_puvodni`.** Stejné adresní místo RÚIAN
    s jinak zformátovaným textem (jiný zdroj) dostane jiný hash, ale stejný
    `ruian_kod`, a INSERT spadne na `UNIQUE (ruian_kod)`. Loader musí hledat
    nejdřív podle `ruian_kod`. Ve vzorku ARES formátoval konzistentně.
14. **Více záznamů ve VR pro jedno IČO** (2×, `primarniZaznam = false`,
    `stavSubjektu = HISTORICKY`), starší registrace. Brát jen primární.
15. **Duplicita komplementářů:** v k.s. je komplementář jak v orgánu
    „Statutární orgán - komplementář“, tak v „Společníci - komplementáři“.
    V v.o.s. jsou společníci zároveň statutárním orgánem.
16. **Zaniklé subjekty ve vzorku nejsou.** Vyhledávání ARES (`/vyhledat`)
    vrací jen existující subjekty (200 FO „Jan Novák“: 0× `datumZaniku`).
    Zaniklé se budou muset dotahovat podle IČO; na reálných zaniklých
    firmách jsme odvození `ZANIKLY` zatím neověřili.

### Pole navíc (dnes je nikam neukládáme)

| pole | doporučení |
|---|---|
| `dic` | přidat do `subjekt_verze` (levné, často potřeba) |
| `czNace` | samostatná tabulka `subjekt_nace` (1:N) |
| `spisovaZnacka` (soud, oddíl, vložka) | přidat do `subjekt_verze` |
| `zakladniKapital` | přidat (částka + měna + splaceno) |
| `datumAktualizace` | uložit k dávce / verzi, pro přírůstkový import |
| `seznamRegistraci` | použít k odvození stavu; uložit jako `jsonb` jen pro audit |
| RÚIAN kódy obce, části obce, ulice, okresu, kraje | přidat do `adresa` (`kod_obce` hlavně pro analýzy po regionech) |
| `typCisloDomovni`, `cisloDoAdresy`, `standardizaceAdresy` | přidat `cislo_evidencni`, případně příznak standardizace |
| `predmetPodnikani`, `zpusobJednani`, `ostatniSkutecnosti`, `akcie` | zatím nechat; uložit celý surový JSON (viz níže) |
| `insolvence`, `konkursy` | mimo jádro; stačí pro odvození stavu |
| `odstepneZavody` (vlastní jméno, sídlo, vedoucí) | zatím mimo |
| `textZaOsobu`, `textOsoba` | volný text; do `organ_puvodni`/poznámky |

Obecné doporučení: ukládat **celou surovou odpověď ARES** (`jsonb`) k dávce,
aby šlo cokoli z výše uvedeného dopočítat později bez nového stahování.

## 4. Ukázky, jak by záznamy vypadaly

Hodnoty `import_davka_id`, `id` a `zaznamenano_od` jsou ilustrační.

### A) Pekárna Unčín s.r.o. (IČO 04115210): s.r.o., společník je FO i PO

**subjekt:** `('04115210', davka=1)`

**subjekt_verze**

| nazev | pravni_forma_kod | stav_kod | datum_vzniku | platnost_od | platnost_do |
|---|---|---|---|---|---|
| Pekárna Unčín s.r.o. | 112 | AKTIVNI | 2015-05-29 | 2015-05-29 | NULL |

**adresa** + **subjekt_adresa**

| ruian_kod | ulice | cislo_popisne | cislo_orientacni | obec | cast_obce | psc | stat | text_puvodni |
|---|---|---|---|---|---|---|---|---|
| 3732941 | NULL | 54 | NULL | Unčín | Unčín | 59242 | CZ | č.p. 54, 59242 Unčín |

→ `SIDLO`, platnost 2015-05-29 – NULL

**osoba / osoba_verze**

| klic_parovani | jmeno | prijmeni | datum_narozeni |
|---|---|---|---|
| `tomas\|hajek\|1978-08-17` | TOMÁŠ | HÁJEK | 1978-08-17 |
| `vladimira\|hajkova\|1989-12-20` | VLADIMÍRA | HÁJKOVÁ | 1989-12-20 |
| `vladimira\|babincova\|1989-12-20` | VLADIMÍRA | BABINCOVÁ | 1989-12-20 |

⚠️ Hájková a Babincová je podle všeho tatáž osoba (sňatek), ale klíč je rozdělí.

**vazba**

| člen | role_kod | organ_puvodni | vklad | podil_text | podil_procento | splaceno | platnost_od | platnost_do |
|---|---|---|---|---|---|---|---|---|
| Tomáš Hájek | JEDNATEL | Statutární orgán / jednatel | | | | | 2015-05-29 | NULL |
| Vladimíra Hájková | JEDNATEL | Statutární orgán / jednatel | | | | | 2015-05-29 | 2019-09-11 |
| Vladimíra Babincová | JEDNATEL | Statutární orgán / jednatel | | | | | 2019-09-11 | NULL |
| Vladimíra Hájková | SPOLECNIK | Společníci | 8000.00 CZK | 4/5 | 80.0000 | 100 | 2015-05-29 | 2019-09-11 |
| Vladimíra Babincová | SPOLECNIK | Společníci | 8000.00 CZK | 4/5 | 80.0000 | 100 | 2019-09-11 | NULL |
| `clen_ico = 63488302` (Původní bílovická pekárna s.r.o.) | SPOLECNIK | Společníci | 2000.00 CZK | 1/5 | 20.0000 | 100 | 2015-05-29 | NULL |

ARES vrací 5 záznamů jednatelů (Hájek je tam dvakrát: výmaz a znovuzápis
v 11/2025 se stejným `vznikFunkce`). Loader je sloučí podle
osoba + role + `vznikFunkce`. Poslední řádek vyžaduje, aby IČO 63488302
existovalo v `subjekt` (bod 2).

### B) Alza.cz a.s. (IČO 27082440): a.s., změna jména i sídla, zahraniční akcionář

**subjekt_verze**, dvě verze kvůli změně jména:

| nazev | pravni_forma_kod | stav_kod | datum_vzniku | platnost_od | platnost_do |
|---|---|---|---|---|---|
| Alzasoft a.s. | 121 | AKTIVNI | 2003-08-26 | 2003-08-26 | 2008-09-19 |
| Alza.cz a.s. | 121 | AKTIVNI | 2003-08-26 | 2008-09-19 | NULL |

**adresa** + **subjekt_adresa (SIDLO)**, dvě adresy v čase:

| ruian_kod | ulice | č.p. | č.o. | obec | cast_obce | psc | platnost_od | platnost_do |
|---|---|---|---|---|---|---|---|---|
| 22754075 | Jateční | 1530 | 33 | Praha | Holešovice | 17000 | 2003-08-26 | 2018-05-10 |
| 25958895 | Jankovcova | 1522 | 53 | Praha | Holešovice | 17000 | 2018-05-10 | NULL |

**vazba**, jen aktuální členové (s historií 52 záznamů):

| člen | role_kod | organ_puvodni | platnost_od |
|---|---|---|---|
| Aleš Zavoral (1976-10-24) | PREDSEDA_PREDSTAVENSTVA | Statutární orgán - představenstvo / Předseda představenstva | 2022-11-09 |
| Miroslav Köváry (1989-07-27) | ❌ *místopředseda* | … / Místopředseda představenstva | 2022-08-15 |
| Ing. Petr Bena (1969-12-02) | ❌ *místopředseda* | … / Místopředseda představenstva | 2025-03-31 |
| Jakub Krejčíř (1986-02-19) | ❌ *místopředseda* | … / Místopředseda představenstva | 2022-08-15 |
| Marek Premus (1989-11-13) | PREDSEDA_DOZORCI_RADY | Dozorčí rada / Předseda dozorčí rady | 2026-03-31 |
| Petr Hošek (1980-12-06) | CLEN_DOZORCI_RADY | Dozorčí rada / Člen dozorčí rady | 2024-09-27 |
| Ing. Hana Žáková Petrová (1972-03-22) | CLEN_DOZORCI_RADY | Dozorčí rada / Člen dozorčí rady | 2023-11-28 |
| **L.S. INVESTMENTS LIMITED** (Kypr, bez IČO) | JEDINY_AKCIONAR | Akcionář | 2017-09-18 |

❌ Tři místopředsedové nemají roli v číselníku a jediného akcionáře nejde
uložit (není FO ani nemá IČO). Uvedený `platnost_od` je `vznikClenstvi`;
zápis do OR proběhl u Zavorala a Krejčíře až 23. 7. 2026.

### C) Jan Novák (IČO 00719331): fyzická osoba podnikatel

**subjekt_verze**

| nazev | pravni_forma_kod | stav_kod | datum_vzniku | platnost_od |
|---|---|---|---|---|
| Jan Novák | 101 | AKTIVNI | 2007-11-09 | 2007-11-09 |

**adresa** (SIDLO): `ruian_kod 4904451`, č.p. 120, Ostrožská Lhota, 68723, CZ

**vazba:** žádná, FO podnikatel není v OR.
**osoba:** nevytváří se. ARES u FO podnikatele nedává datum narození, takže
ji nelze spárovat přes `dev.klic_osoby` a `osoba.ico` zůstane nepropojené.

## Schválená rozhodnutí a jejich implementace

| # | rozhodnutí | implementace |
|---|---|---|
| 1 | Zahraniční PO bez IČO jako pojmenovaný člen bez identity | `vazba.clen_nazev` + `clen_stat`; člen je právě jedno z `clen_osoba_id` / `clen_ico` / `clen_nazev` (+`clen_stat`) |
| 2 | Chybějící firmy z vazeb: jen identita | `INSERT INTO subjekt (ico)`, bez verze a bez stahování |
| 3 | Doplnit nalezené role | místopředseda představenstva a DR, předseda/místopředseda/člen kontrolní komise, předseda/místopředseda družstva, statutární ředitel, předseda správní rady |
| 4 | Stav = AKTIVNI/ZANIKLY + dva nezávislé příznaky | `stav_kod`, `je_v_likvidaci`, `je_v_insolvenci` |
| 5 | Platnost dle vzniku/zániku funkce, zápis do OR zvlášť | `platnost_od/do` + `datum_zapisu_or` / `datum_vymazu_or` |
| 6 | Pole navíc hned | `subjekt_verze`: `dic`, `spisova_znacka`, `zakladni_kapital(_mena)`, `cz_nace`, `datum_aktualizace_zdroje`; `adresa`: `cislo_evidencni`, `kod_obce`, `kod_kraje`; surový JSON v `import_surova_data.raw` |
| 7 | Změna příjmení: dvě osoby + příznak | `osoba.kandidat_slouceni`, funkce `dev.oznac_kandidaty_slouceni()`, pohled `dev.osoba_kandidati_slouceni` |
| – | Podíl: originál + číslo jen při spolehlivém parsování | `podil_text` = hodnota přesně z ARES; `podil_procento` jen z `%`, `a/b`, zlomku `a;b` nebo typu PROCENTA |
| – | Adresa: jednoznačnost podle RÚIAN | s RÚIAN kódem: `UNIQUE (ruian_kod)`, text se neporovnává; bez RÚIAN: částečný unikátní index na `hash_adresy` |

### Upřesnění při implementaci (k odsouhlasení)

- **Surový JSON je v samostatné tabulce `import_surova_data`, ne ve sloupci `subjekt_verze`.**
  Ukládá se při každé dávce pro každé IČO a endpoint, i když se nic nezměnilo nebo převod selhal.
  Ve sloupci verze by chyběl právě v těchto případech a u firem s více verzemi by se duplikoval.
- **`je_v_insolvenci` u historických verzí = NULL (nezjištěno).** ARES dává spolehlivě jen
  aktuální stav (`stavZdrojeIr`). Sekce insolvence ve výpisu z OR zůstává otevřená i po skončení
  řízení (např. Sokolovské strojírny), proto ji na historii nepoužíváme. Stejně tak DIČ, CZ-NACE
  a datum aktualizace se vyplní jen v poslední (otevřené) verzi.
- **`je_v_likvidaci`** = v daném období byl zapsán likvidátor, nebo název obsahuje „v likvidaci“.
- **Platnost podílu společníka** = zápis/výmaz podílu v OR (podíl nemá vlastní vznik/zánik).
- **Družstvo:** holé „předseda/místopředseda/člen“ ve statutárním orgánu = představenstvo;
  „předseda družstva“ se v OR píše výslovně.
- **Nepřevedeno** (zůstává jen v surových datech, vypisuje se jako přeskočené): „ředitel družstva“,
  „generální ředitel a.s.“ bez hodnosti v představenstvu, zahraniční PO bez uvedeného státu
  (např. GPL Limited, Guernsey, jen textová adresa), sekce členů družstva a jejich vkladů.
- **Opakované zápisy téhož člena** (OR přepíše člena při každé změně) se slučují podle
  člen + role + podíl + `platnost_od`; navazující řádky se stejným obsahem se spojí.
