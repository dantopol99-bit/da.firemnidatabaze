# Stálá pravidla pro práci v tomto repozitáři

Platí pro každou session. Popis projektu je v [README.md](README.md), metodika reportu
v [docs/report_metodika.md](docs/report_metodika.md).

## Komunikace a GitHub
- Komunikuj česky (zprávy, commity, popisy PR, dokumentace).
- PR po otevření hlídat nemusíš (neodebírej aktivitu PR, neplánuj kontroly).
- CI (GitHub Actions ani jiné) nezakládej.

## Větve
- Před založením nebo resetem větve zkontroluj otevřené PR (i na pracovní větvi této session).
- Na větev s otevřeným PR nikdy nedělej force-push ani reset; další práci přidávej běžnými commity.
- Při pochybnosti, zda je PR sloučený nebo zda větev smíš přepsat, se zeptej.

## Před každým PR
- Spusť celou sadu testů: `python -m unittest discover -s tests`.
- Bez zelených testů PR neotvírej. Testy, které se přeskočí kvůli chybějící databázi nebo typstu,
  uveď v popisu PR.

## Text analytika (`reporty/vyklad/`)
- Text analytika nikdy neupravuj sám, ani když neprojde kontrolou čísel nebo zakázaných slov.
- Při chybě jen ohlas, co neprošlo a kde: oddíl, přesnou větu, číslo nebo slovo a důvod.
- Bez pokynu smíš jen založit nový soubor se zástupným textem (to dělá `report` automaticky)
  nebo vložit text, který analytik dodal, beze změny znění.

## Co do gitu nepatří
- Surová data (soubory RES, stažené CSV a exporty z DataStatu, výpisy databáze). Patří mimo
  repozitář nebo do gitignorovaného `data/`.
- Instalační balíčky a binárky (`.whl`, `.tar.gz`, `.tar.xz`, `.zip`, binárka typst apod.).
- Interní kontrolní data reportu (`reporty/vystupy/*/_interni/`) a `.env`.
- Před commitem zkontroluj `git status` a nenechávej pracovní soubory v kořeni repozitáře.
