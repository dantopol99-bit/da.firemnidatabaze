// Oborově-regionální report – šablona sazby (Typst)
//
// Pevná osnova (docs/report_osnova.md): titulní strana → shrnutí → postavení území
// → struktura → dynamika území a kontext ČR → metodika, omezení a zdroje → příloha.
// Šablona NIC NEPOČÍTÁ: všechna čísla i texty přicházejí hotové v data.json
// (report_pdf.sestav_data z výstupu JSON Bloku 2). Tabulky a grafy se číslují
// písmeny, aby jediná čísla v textu byla čísla z dat (kontrola konzistence PDF).
//
// Kompilace:  typst compile --root / --font-path reporty/sablona/fonty --ignore-system-fonts \
//               --input data=/cesta/data.json reporty/sablona/report.typ report.pdf

#let d = json(sys.inputs.data)

#let inkoust = rgb("#0b0b0b")
#let sedy = rgb("#52514e")
#let modra = rgb("#2a78d6")
#let jemna = rgb("#e6e5e1")
#let podklad = rgb("#f4f3f0")
#let varovna = rgb("#b42318")

#set document(title: "Oborově-regionální report – " + d.titul.obor + " × " + d.titul.uzemi)
#set text(font: "IBM Plex Sans", size: 9.5pt, lang: "cs", fill: inkoust)
#set par(justify: true, leading: 0.62em, spacing: 0.95em)
#set page(
  paper: "a4",
  margin: (left: 2cm, right: 2cm, top: 2.2cm, bottom: 2.7cm),
  header: context {
    if counter(page).get().first() > 1 {
      set text(size: 7.5pt, fill: sedy)
      [#d.titul.obor × #d.titul.uzemi #h(1fr) Oborově-regionální report]
      v(-0.4em)
      line(length: 100%, stroke: 0.4pt + jemna)
    }
  },
  footer: context {
    set text(size: 7pt, fill: sedy)
    line(length: 100%, stroke: 0.4pt + jemna)
    v(-0.3em)
    if d.koncept {
      text(fill: varovna, weight: "bold", size: 8pt)[KONCEPT – výklad k revizi]
      linebreak()
    }
    [#d.zapati #h(1fr) strana #counter(page).display() z #counter(page).final().first()]
  },
)

#show heading.where(level: 1): it => {
  pagebreak(weak: true)
  block(below: 1em, text(size: 17pt, weight: "semibold", fill: modra, it.body))
}
#show heading.where(level: 2): it => block(above: 1.2em, below: 0.6em,
  text(size: 11pt, weight: "semibold", it.body))

// ---------------------------------------------------------------------------
// Stavební prvky
// ---------------------------------------------------------------------------

#let popisek(t) = text(size: 7.5pt, fill: sedy, t)

#let tabulka(t) = block(width: 100%, above: 1.2em, below: 1.2em, breakable: t.radky.len() > 22)[
  #text(size: 8.5pt, weight: "semibold")[Tabulka #t.pismeno: #t.nazev]
  #v(-0.2em)
  #let n = t.zahlavi.len()
  #let ma_poznamku = t.zahlavi.last() == "Poznámka"
  #let siroka = t.cisel >= 5
  #let sloupce = (if siroka { 1.5fr } else { 2.6fr },) + range(n - 1).map(i => if ma_poznamku and i == n - 2 { 1.3fr } else { 1fr })
  #set text(size: if siroka { 6.6pt } else { 7.5pt })
  #set par(justify: false)
  #table(
    columns: sloupce,
    stroke: none,
    inset: (x: if siroka { 2.5pt } else { 4pt }, y: 3pt),
    align: (x, y) => if x == 0 or (ma_poznamku and x == n - 1) { left } else { right },
    fill: (x, y) => if y == 0 { podklad },
    table.hline(stroke: 0.6pt + inkoust),
    ..t.zahlavi.map(z => text(weight: "semibold", z)),
    table.hline(stroke: 0.4pt + jemna),
    ..t.radky.map(r => r.bunky.map(b => if r.zvyrazneni { text(weight: "semibold", b) } else { b })).flatten(),
    table.hline(stroke: 0.6pt + inkoust),
  )
  #v(-0.3em)
  #for p in t.poznamky [#popisek(p) \ ]
  #popisek(t.zdroj)
]

#let graf(g) = block(width: 100%, above: 1.2em, below: 1.2em, breakable: false)[
  #text(size: 8.5pt, weight: "semibold")[Graf #g.pismeno: #g.nazev]
  #v(-0.2em)
  #align(center, image(g.soubor, width: if g.at("maly", default: false) { 85% } else { 100% }))
  #v(-0.4em)
  #popisek(g.zdroj)
]

// Rozhodnutí 12: „co je vidět“ a zjištění píše stroj, „proč“ a „co z toho plyne“ analytik.
#let nazvy_druhu = ("vidět": "Co je vidět", "zjištění": "Zjištění detektoru",
  "proč": "Proč to tak může být (analytik)", "plyne": "Co z toho plyne (analytik)")

#let vyklad(bloky) = {
  let predchozi = none
  for b in bloky {
    if b.druh != predchozi {
      block(above: 0.9em, below: 0.3em, text(size: 9pt, weight: "semibold", fill: modra, nazvy_druhu.at(b.druh)))
      predchozi = b.druh
    }
    if b.druh == "zjištění" {
      block(above: 0.35em, below: 0.35em, grid(columns: (0.9em, 1fr), text(fill: modra)[■], b.text))
    } else if b.hypoteza {
      par[#text(style: "italic", weight: "medium")[Hypotéza:] #emph(b.text)]
    } else {
      par(b.text)
    }
  }
}

#let varovani_box(seznam) = if seznam.len() > 0 {
  block(width: 100%, inset: 10pt, radius: 3pt, stroke: 1pt + varovna, fill: rgb("#fdf1f0"))[
    #text(weight: "bold", fill: varovna)[⚠ Varování]
    #for v in seznam [ \ #v ]
  ]
}

// ---------------------------------------------------------------------------
// Titulní strana
// ---------------------------------------------------------------------------

#page(header: none)[
  #v(3.2cm)
  #text(size: 10pt, weight: "medium", fill: modra)[OBOROVĚ-REGIONÁLNÍ REPORT]
  #v(0.4em)
  #text(size: 24pt, weight: "semibold", hyphenate: false)[#d.titul.obor]
  #v(0.2em)
  #text(size: 18pt, weight: "regular", fill: sedy)[#d.titul.uzemi (#d.titul.typ_uzemi)]
  #v(1.4em)
  #grid(columns: (auto, 1fr), column-gutter: 1.2em, row-gutter: 0.7em,
    text(fill: sedy)[Stav údajů (snímek RES)], text(weight: "semibold")[#d.titul.datum],
    text(fill: sedy)[Klasifikace], d.titul.klasifikace,
    text(fill: sedy)[Srovnávací kraje], if d.titul.srovnani.len() > 0 { d.titul.srovnani.join(", ") } else [nezadány],
    text(fill: sedy)[Počty], [registrované ekonomické subjekty bez data zániku],
  )
  #v(1.6em)
  #varovani_box(d.titul.varovani)
  #if d.koncept {
    v(1em)
    block(width: 100%, inset: 10pt, radius: 3pt, fill: podklad)[
      #text(weight: "bold", fill: varovna)[KONCEPT – výklad k revizi.]
      Výklad analytika („proč“ a „co z toho plyne“) není schválen; čísla, tabulky, popis „co je vidět“
      a zjištění pocházejí přímo z výpočetní vrstvy.
    ]
  }
  #v(1fr)
  #set text(size: 8pt, fill: sedy)
  #d.titul.citace \
  #text(weight: "semibold")[#d.titul.oznaceni]
]

// ---------------------------------------------------------------------------
// Shrnutí (1 strana)
// ---------------------------------------------------------------------------

= Shrnutí klíčových zjištění

#grid(columns: range(d.shrnuti.dlazdice.len()).map(_ => 1fr), column-gutter: 8pt,
  ..d.shrnuti.dlazdice.map(t => block(width: 100%, inset: 9pt, radius: 3pt, fill: podklad)[
    #text(size: 7.5pt, fill: sedy)[#t.popis] \
    #text(size: 18pt, weight: "semibold")[#t.hodnota] \
    #text(size: 7.5pt, fill: sedy)[#t.pozn]
  ]))
#v(0.8em)
#set list(marker: text(fill: modra)[■], spacing: 0.8em)
// body shrnutí píše analytik (rozhodnutí 12); dlaždice a varování jsou strojové
#for b in d.shrnuti.body [- #b]
#if d.shrnuti.varovani.len() > 0 { v(0.6em); varovani_box(d.shrnuti.varovani) }

// ---------------------------------------------------------------------------
// Kapitoly: postavení území, struktura, dynamika
// ---------------------------------------------------------------------------

#let nedostupne_box(n) = block(width: 100%, inset: 10pt, radius: 3pt, stroke: 0.8pt + jemna, fill: podklad)[
  #text(weight: "bold", fill: sedy)[Stav: zatím nedostupné]
  #v(0.3em)
  #grid(columns: (auto, 1fr), column-gutter: 1em, row-gutter: 0.6em,
    text(fill: sedy)[Důvod], n.duvod,
    text(fill: sedy)[Plánovaný zdroj], n.zdroj,
    text(fill: sedy)[Plánovaný obsah], n.obsah,
  )
]

#for k in d.kapitoly [
  = #k.nadpis
  #if k.nedostupne != none { nedostupne_box(k.nedostupne) }
  #vyklad(k.vyklad)
  #for o in k.obsah {
    if o.typ == "tabulka" { tabulka(o) }
    else if o.typ == "graf" { graf(o) }
    else if o.typ == "nadpis" { heading(level: 2, o.text) }
    else if o.typ == "odstavec" { block(width: 100%, inset: 8pt, radius: 3pt, fill: podklad, text(size: 8.5pt, o.text)) }
    else if o.typ == "vyklad" { vyklad(o.bloky) }
  }
  #if k.pododdil != none [
    == #k.pododdil.nadpis
    #nedostupne_box(k.pododdil)
  ]
]

// ---------------------------------------------------------------------------
// Metodika, omezení a zdroje
// ---------------------------------------------------------------------------

= Metodika, omezení a zdroje

== Populace a klasifikace
#d.metodika.populace #d.metodika.klasifikace

== Pravidla zveřejnění
#for p in d.metodika.pravidla [- #p]

#if d.metodika.varovani.len() > 0 [
  == Varování
  #varovani_box(d.metodika.varovani)
]

== Omezení
#for p in d.metodika.omezeni [- #p]

== Použité ukazatele
#block[
  #set text(size: 7.3pt)
  #set par(justify: false)
  #table(columns: (auto, 1.3fr, 2.4fr), stroke: none, inset: (x: 4pt, y: 3pt),
    fill: (x, y) => if y == 0 { podklad },
    table.hline(stroke: 0.6pt + inkoust),
    text(weight: "semibold")[Kód], text(weight: "semibold")[Ukazatel], text(weight: "semibold")[Definice],
    table.hline(stroke: 0.4pt + jemna),
    ..d.metodika.ukazatele.map(u => (raw(u.kod), u.nazev, u.definice)).flatten(),
    table.hline(stroke: 0.6pt + inkoust),
  )
]

== Zdroje a licence
#for z in d.metodika.zdroje [- #z]
#d.metodika.licence

#text(weight: "semibold")[#d.metodika.oznaceni]

// ---------------------------------------------------------------------------
// Příloha
// ---------------------------------------------------------------------------

= Příloha: zjištění detektoru
#text(size: 8.5pt, fill: sedy)[Všechna zjištění seřazená podle síly; věcný popis bez interpretace (rozhodnutí 12).]
#block[
  #set text(size: 8.3pt)
  #for z in d.zjisteni [- #z]
]

= Příloha: odchylky od osnovy
#for o in d.odchylky [- #o]
