# Oborově-regionální report – pevná osnova (v0)

Osnova je **stejná pro každé zadání** (obor × území × datum snímku). Kapitoly se nepřidávají ani
nevypouštějí. Chybí-li kapitole údaje (členění pod prahem, ČSÚ údaj nepublikuje), kapitola zůstane
a výčet chybějících tabulek s důvodem jde do **přílohy „odchylky od osnovy“**.

Sazba: `reporty/sablona/report.typ` (Typst, font IBM Plex Sans v `reporty/sablona/fonty`, licence OFL).
Data: výhradně `vysledek.json` z výpočetní vrstvy (Blok 2). Šablona nic nepočítá.

| # | kapitola | obsah | zdroj v JSON |
|---|---|---|---|
| 1 | **Titulní strana** | obor, území a jeho typ, datum snímku RES, klasifikace, srovnávací kraje (zadal člověk), **varování** (rozhodnutí 9), stav KONCEPT, citace a označení odvozených údajů | `meta` |
| 2 | **Shrnutí klíčových zjištění** (1 strana) | dlaždice: počet, lokalizační koeficient, hustota na 1 000 obyvatel (+ ČR), pořadí; body shrnutí. Hlavní sdělení nesou jen počet, LQ, hustota a pořadí (rozhodnutí 11) | T01, T02, T03, T05 |
| 3 | **Postavení území** | výklad; tab. základní ukazatele; tab. srovnání s ČR a zadanými kraji; graf kraje podle hustoty; graf kraje podle LQ; tab. pořadí 14 krajů; tab. okresy kraje (u kraje a okresu) | T01–T04 |
| 4 | **Struktura** | výklad; graf a tab. FO/PO; tab. právní formy; graf a tab. velikostní profil FO a PO zvlášť, vždy s „Neuvedeno“ (rozhodnutí 2, 11); graf a tab. věková struktura existujících subjektů | T05–T09, T01 (věk) |
| 5 | **Dynamika území a kontext ČR** | výklad; graf a tab. vznik a zánik v území, všechny obory (RES05), rok 2023 označen jako mimořádný; tab. zaniklé PO v oboru od 2023 (RES); graf a tab. demografie podniků ČR (RESDP00) s poznámkou o jiné jednotce (rozhodnutí 10) | T10–T12 |
| 6 | **Metodika, omezení a zdroje** | populace a klasifikace; pravidla zveřejnění (práh, minimální rozsah, spolehlivost zařazení); varování; omezení; použité ukazatele z katalogu; zdroje, **licence CC BY 4.0**, **„Odvozené údaje, nejde o oficiální statistiku ČSÚ.“** | `meta` |
| 7 | **Příloha: odchylky od osnovy** | nezveřejněné tabulky s důvodem; jinak „Žádné“ | `tabulky[].zverejneno`, `duvod` |

## Pravidla sazby

- **Výklad** ke kapitolám 3–5 má strukturu *co je vidět → proč to tak může být → co z toho plyne*.
  Každé tvrzení odkazuje na tabulku nebo graf a nedoložitelná tvrzení jsou označena **„Hypotéza:“**.
  Výklad je návrh: dokud ho člověk neschválí (`report_pdf --vyklad-schvalen`), nese každé zápatí
  **„KONCEPT – výklad k revizi“**.
- **Grafy** jen z knihovny `report_grafy` (6 typů, strop 8): pořadí území, index proti referenci,
  skladba celku, rozložení do kategorií, vznik a zánik v letech, míry v čase. Jednotný vzhled:
  zkoumané území modře, srovnávací kraje oranžově, ostatní šedě; „Neuvedeno“ a „ostatní“ šedě se šrafou.
- **Každý graf a každá tabulka** nese pod sebou zdroj a datum snímku.
- Tabulky a grafy se označují **písmeny** (Tabulka A, Graf B) a kapitoly nemají čísla. Jediná čísla
  v textu PDF jsou tak čísla z dat a čísla stránek.
- **Kontrola konzistence** (`report_kontrola.zkontroluj_pdf`): každé číslo v textu PDF, včetně výkladu,
  musí být v `vysledek.json` i v `priloha.xlsx`. Čísla stránek („strana X z Y“) se vynechávají.
  Nesoulad zastaví sazbu a PDF se smaže. Čísla uvnitř grafů jsou křivky, ne text; popisky hodnot
  v grafech se přebírají z JSON bez zaokrouhlení.
- **Minimální rozsah** (rozhodnutí 8): pod 100 registrovanými subjekty se report nevydá; CLI vypíše
  návrh vyšší úrovně s počty.

## Spuštění

```bash
python -m firemni_databaze.report --obor F --uzemi CZ051 --srovnani CZ052,CZ041 --pdf
python -m firemni_databaze.report_pdf reporty/vystupy/F__CZ051__2026-09-15 --vystup reporty/ukazky
```

Vzorový pilot: `reporty/ukazky/F__CZ051__2026-09-15/` (report.pdf, priloha.xlsx). Odmítnutí podle
rozhodnutí 8: `reporty/ukazky/62__CZ0711__odmitnuti.txt`.
