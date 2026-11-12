# Oberfläche „Skizzenbuch“ (ab 0.8.0)

Zweite, vollständig eigene Oberfläche neben dem Menüband. Sie wird wie ein Design gewählt
(Design-Menü › Skizzenbuch) und pro Konto gespeichert. Vorbild ist ein handgezeichnetes Lernplakat:
cremefarbenes Punktraster-Papier, dicke Tintenkonturen, Pastellkästen mit hartem Schatten, Handschrift
für Überschriften. **Kein Menüband** – stattdessen Bereichsleiste, Bereichsseiten und eine Startseite,
von der aus alles in höchstens zwei Klicks erreichbar ist.

Leitsatz: Handschrift führt (Überschriften, Knöpfe, Bereichsnamen), Daten bleiben nüchtern
(Tabellen, Eingabefelder, Noten in der normalen serifenlosen Schrift). Lesbarkeit geht vor Dekor.

## 1. Anordnung

### Jede Seite

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ SCHULNEXUS            [🔍 Person suchen ………]  [Befehle Strg+K]   DE ▾  Design ▾  ?  (MK) ▾ │  Kopfzeile
│ ~~~~~~~~~~  Meine Schule · 2026/27                                                        │  (Papier, klebt oben)
├──────────────────────────────────────────────────────────────────────────────────────────┤
│  Start     Termine     Schüler:innen     Unterricht     Förderung     Schulleitung   …    │  Bereichsleiste
│  ├────┤    ├──────┤    ├───────────┤     ├────────┤     ├────────┤     ├──────────┤        │  (Klammerlinie je Bereich
│                                                                                           │   in der Bereichsfarbe)
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ ╭ Wegleiste (hellblaues Band, nur auf Unterseiten) ─────────────────────────────────────╮ │
│ │ Unterricht ›  [Noten eintragen]  [Notenübersicht]  [Noten nach Klasse]  [Fehlzeiten]  │ │  Geschwister-Befehle der
│ ╰───────────────────────────────────────────────────────────────────────────────────────╯ │  aktiven Gruppe als Kästchen
│ ★ Favoriten:  (Notenübersicht)  (9a)  …                                                   │  (nur wenn Favoriten gemerkt)
│                                                                                           │
│  Seiteninhalt (weiße Karten mit farbigem Versatzschatten)                                 │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

- Ein Klick auf einen Bereich öffnet die **Bereichsseite** (`/bereich/<schluessel>/`), „Start“ die Startseite.
- Die Wegleiste zeigt den Bereich und die Befehle derselben Gruppe; der aktive Befehl ist gelb hinterlegt.
- Befehlssuche (Strg+K), Favoriten, Hilfe-Seitenleiste, Sprach- und Designwahl bleiben unverändert nutzbar.

### Startseite

```
┌ Kalenderblatt ┐  GUTEN ABEND, MARV                       ✦  ✦
│  Do 12 Nov    │  Donnerstag, 12. November 2026, Kalenderwoche 46      (Handschrift, blau)
└───────────────┘
 Was möchten Sie tun?
┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│ TERMINE      │ │ SCHÜLER:INNEN│ │ UNTERRICHT   │ │ FÖRDERUNG    │   Bereichskacheln: Pastellkasten,
│ ▸ Kalender   │ │ ▸ 9a         │ │ ▸ Noten      │ │ ▸ Förderpläne│   Tintenkontur, harter Schatten;
│ ▸ Raumplan   │ │ ▸ Alle …     │ │ ▸ Fehlzeiten │ │ ▸ Gültige    │   bis zu 4 wichtigste Befehle,
│   alle ›     │ │   alle ›     │ │   alle ›     │ │   alle ›     │   „alle ›“ führt zur Bereichsseite
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────┘
 Meine Klassen und Gruppen | Mein Unterricht        (Schnellzugriff als Notizkarten)
 ( 35 )  ( 11 )  ( 8 )  ( 4 )  ( 3 )  ( 2 )          Kennzahlen als runde „Basen“-Kreise
┌ Hauptspalte: Termine, Noten, Zeugnisse … ┐ ┌ Seitenspalte ──────────────┐
│ weiße Karten, Versatzschatten gelb/rosa  │ │ MERKE (Mitteilungen) mit   │
│                                          │ │ Klebestreifen, Geburtstage │
└──────────────────────────────────────────┘ └────────────────────────────┘
```

### Bereichsseite

Überschrift in Markerschrift, darunter je Befehlsgruppe ein Abschnitt (Handschrift-Zwischenüberschrift)
mit Befehlskarten: Symbol, Titel, einzeilige Erklärung (`hinweis`). Große Befehle zuerst und größer.

### Telefon (390 px)

Kopfzeile bricht um (Marke, Konto oben; Suche darunter volle Breite), Bereichsleiste waagerecht
rollbar, Kacheln einspaltig, Wegleiste rollbar. Kein seitliches Überlaufen der Seite.

## 2. Designvorgaben

### Farben (CSS-Variablen in `static/skizze.css`)

| Variable | Wert | Verwendung |
|---|---|---|
| `--sk-papier` | `#FFF8E7` | Seitengrund, darauf Punktraster `#E8DCC0`, 22 px |
| `--sk-tinte` | `#2B2B33` | Text, Konturen, harte Schatten |
| `--sk-leise` | `#666A78` | Nebentext |
| `--sk-blau-tinte` | `#1A5FA8` | Links, Handschrift-Unterzeilen |
| `--sk-rot` | `#C2273D` | Warnungen, „Merke“-Titel |
| `--sk-gelb` / `-kraeftig` | `#FFE08A` / `#F2B100` | Hauptknopf, aktiver Befehl, Wellenlinie |
| `--sk-rosa` / `-kraeftig` | `#FFB8CB` / `#E0527A` | |
| `--sk-gruen` / `-kraeftig` | `#BDEFC6` / `#2E9E63` | „ok“-Kennzeichen |
| `--sk-lila` / `-kraeftig` | `#DCC8FF` / `#7B4FD6` | |
| `--sk-blau` / `-kraeftig` | `#AEDBFF` / `#1F6FC4` | Wegleiste, Tabellenkopf |
| `--sk-orange` / `-kraeftig` | `#FFCF96` / `#E0801A` | Klebestreifen, „offen“-Kennzeichen |
| `--sk-tuerkis` / `-kraeftig` | `#ACEBE0` / `#159A8A` | |

Bereichsfarben in fester Reihenfolge der Bereiche: gelb, rosa, grün, lila, blau, orange, türkis, dann von vorn
(`.sk-farbe-1` … `.sk-farbe-7`, setzt `--sk-f` und `--sk-f-kraeftig`). Die bestehenden Variablen
(`--grund`, `--flaeche`, `--text`, `--leise`, `--linie`, `--akzent`, `--akzent-hell`, `--warnung`, …) werden unter
`:root[data-design="skizze"]` passend belegt, damit alle vorhandenen Seiten ohne Einzelanpassung stimmig sind.
Text auf Farbe ist immer `--sk-tinte` (Kontrast ≥ 4,5 : 1).

### Schrift (lokal in `static/schrift/`, keine fremden Server)

| Variable | Schrift | Einsatz |
|---|---|---|
| `--sk-marker` | Permanent Marker | Marke, `h1`, Kacheltitel – Großbuchstaben, nie unter 1,3 rem |
| `--sk-schrift` | Caveat 600/700 | Unterzeilen, Bereichsnamen, Randbemerkungen – nie unter 1,15 rem |
| `--sk-hand` | Patrick Hand | `h2`/`h3`, Knöpfe, Kennzeichen, Tabellenkopf – nie unter 1 rem |
| (Standard) | Systemschrift | Fließtext, Tabellenzellen, Eingabefelder, Noten |

### Formen

- Kontur 2 px `--sk-tinte`, Ecken 14 px (Kacheln 18 px, Kennzeichen rund).
- Harter Schatten ohne Weichzeichnung: Kästen `4px 5px 0 var(--sk-tinte)`; weiße Karten farbig
  (`5px 6px 0` in Gelb, Rosa, Grün … reihum per `:nth-of-type`).
- Knöpfe: Hauptknopf gelb, Nebenknopf weiß, gefährlich rosa; beim Drücken rückt der Knopf in den Schatten.
- Kennzeichen (Status): Pille mit Kontur und Pastellfüllung.
- Tabellen: weiße Karte, Kopfzeile hellblau in Patrick Hand, gestrichelte Zeilenlinien, Zahlen tabellarisch.
- Eingabefelder: weiß, 2 px Kontur, Fokus = 3 px gelber Ring. `:focus-visible` überall deutlich sichtbar.
- Dekor sparsam: Wellenlinie unter der Marke, Klebestreifen auf „Merke“, Textmarker-Hervorhebung
  (`.sk-marker-gelb` usw.), leichte Drehung (höchstens 0,5°) nur bei Notizkarten.
- Bewegung nur als kurze Hover-Rückmeldung; `prefers-reduced-motion` schaltet sie ab.
- Druck: `@media print` entfernt Papiergrund, Schatten und Kopfzeile; Zeugnis- und Listenausdrucke bleiben unverändert.

## 3. Technischer Aufbau

| Teil | Datei |
|---|---|
| Design-Eintrag `skizze`, Gruppe „Skizzenbuch“ | `portal/models.py` (+ Migration) |
| Schalter `SKIZZE` für Vorlagen | `portal/context.py` |
| Kopfzeile, Bereichsleiste, Wegleiste | `templates/portal/_skizze_kopf.html` |
| Befehlssuche und Hilfeleiste (für beide Oberflächen) | `templates/portal/_befehlssuche.html`, `_hilfeleiste.html` |
| Bereichskacheln der Startseite | `templates/portal/_skizze_bereiche.html` |
| Bereichsseite | `portal/views.py: bereich`, `templates/portal/bereich.html`, URL `bereich/<schluessel>/` |
| Grundlagen, Kopf, Bauteile | `static/skizze.css` |
| Startseite, Bereichsseite | `static/skizze_start.css` |
| Fachseiten, Verwaltungsoberfläche | `static/skizze_seiten.css` |
| Schriften | `static/schrift/*.woff2` (OFL 1.1 bzw. Apache 2.0, Lizenztexte liegen bei) |

Alle Regeln stehen unter `html[data-design="skizze"]`; die übrigen elf Designs und das Menüband bleiben unberührt.
Die Befehlssuche liest ihre Befehle weiterhin aus einem (im Skizzenbuch unsichtbaren) Befehlsverzeichnis im Kopf.

## Variante „klar“ (ab 0.8.1)

Das Design `klar` („Skizzenbuch klar (modern)“) hat dieselbe Anordnung wie das Skizzenbuch, aber schlichte, moderne
Farben: helles Grau-Weiß als Grund, Schiefer als Schrift, blaue Akzente und blasse Pastellflächen mit kräftigen Tönen.

Technisch: Die Regeln der Anordnung in `skizze.css`, `skizze_start.css` und `skizze_seiten.css` gelten unter
`:is([data-design="skizze"],[data-design="klar"])`. Alle festen Flächenfarben stehen dort als Variablen
(`--sk-karte`, `--sk-papier-hell`, `--sk-zebra`, `--sk-hover`, `--sk-linie` …); die Werte für das Skizzenbuch sind unverändert.
`static/skizze_klar.css` überschreibt nur die Farbvariablen und wird ausschließlich für `klar` geladen.
Schriften bleiben in beiden Designs gleich. Der Schalter `SKIZZE` in `portal/context.py` gilt für beide.
