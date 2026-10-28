"""
Excel-Notentabelle Sek I (ab 0.4.11.0): Muster zum Herunterladen und Grundlage für den Import.

Die Datei rechnet unabhängig von Schulnexus (Master-Blatt mit allen Gewichten, je Halbjahr bis zu 8 Klassenarbeiten
und 20 SoMi-Noten, Jahresnote, Blatt „Erklärung“). Sie verwendet nur Grundfunktionen (keine benannten Bereiche, keine
Matrixformeln), damit sie auch in Numbers, LibreOffice und Excel für iPad rechnet.

Die festen Positionen (Master!B5 Klasse, Zeilen 6–8 Kopf der Leistungsnachweise, ab Zeile 10 die Schüler:innen,
Spalten D–K Klassenarbeiten, L–AE SoMi) nutzt `noten.notenimport` beim Einlesen.
"""
import io
import math
import re

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.datavalidation import DataValidation

SCHRIFT = "Arial"


def F(**k):
    return Font(name=SCHRIFT, **k)


EINGABE = PatternFill("solid", fgColor="FFF2CC")
FORMEL = PatternFill("solid", fgColor="F2F2F2")
KOPF = PatternFill("solid", fgColor="1F5F5B")
KOPF2 = PatternFill("solid", fgColor="E3EFED")
ORANGE = PatternFill("solid", fgColor="B4532A")
duenn = Side(style="thin", color="BFBFBF")
RAND = Border(left=duenn, right=duenn, top=duenn, bottom=duenn)
MITTE = Alignment(horizontal="center", vertical="center", wrap_text=True)
LINKS = Alignment(horizontal="left", vertical="center", wrap_text=True)
OBEN = Alignment(horizontal="left", vertical="top", wrap_text=True)
BLAU = F(color="0000FF")
GRUEN = F(color="008000")
LEISE = F(size=9, color="5B6670")

ERSTE, ANZAHL = 10, 35
LETZTE = ERSTE + ANZAHL - 1
N_KA, N_SOMI = 8, 20
SP_K = 4                          # D
SP_S = SP_K + N_KA                # L
SP_ENDE = SP_S + N_SOMI - 1       # AE
ERG = SP_ENDE + 1                 # AF
HELFER = ERG + 8 + 2              # AO: Notenwerte, danach wirksame Gewichte und Produkte
ANZ = N_KA + N_SOMI
STUFEN_STANDARD = [("1+", 0.7), ("1", 1.0), ("1-", 1.3), ("2+", 1.7), ("2", 2.0), ("2-", 2.3), ("3+", 2.7), ("3", 3.0),
          ("3-", 3.3), ("4+", 3.7), ("4", 4.0), ("4-", 4.3), ("5+", 4.7), ("5", 5.0), ("5-", 5.3), ("6", 6.0)]
SEP = 'MID(FIXED(1.5,1),2,1)'     # Dezimaltrennzeichen der eingestellten Sprache

BLATT_HJ = {1: "1. Halbjahr", 2: "2. Halbjahr"}
MASTER = {"klasse": "B5", "fach": "B6", "lehrkraft": "B7", "schuljahr": "B8"}


def erstellen(vorgabe=None):
    """Erzeugt die Notentabelle als .xlsx (Bytes). `vorgabe` = Vorbelegung (siehe noten.notenimport.vorlage_daten); ohne `vorgabe`
    entsteht die allgemeine Vorlage mit Beispielzeile."""
    vg = vorgabe or {}
    STUFEN = vg.get("stufen") or STUFEN_STANDARD
    wb = Workbook()


    NAMEN = {}


    def name(n, ref):
        NAMEN[n] = ref   # wird am Ende direkt in die Formeln eingesetzt (Kompatibilität mit Numbers u. a.)


    def zelle(ws, ref, wert=None, font=None, fill=None, fmt=None, ausr=None, rand=True):
        c = ws[ref]
        if wert is not None:
            c.value = wert
        if font is not None:
            c.font = font
        if fill is not None:
            c.fill = fill
        if fmt is not None:
            c.number_format = fmt
        if ausr is not None:
            c.alignment = ausr
        if rand:
            c.border = RAND
        return c


    def kopf(ws, ref, text, fill=KOPF, farbe="FFFFFF", groesse=9):
        return zelle(ws, ref, text, F(bold=True, color=farbe, size=groesse), fill, None, MITTE)


    def textblatt(ws, zeilen, breite=112):
        ws.sheet_view.showGridLines = False
        ws.column_dimensions["A"].width = 3
        ws.column_dimensions["B"].width = breite
        for i, (text, art) in enumerate(zeilen, start=2):
            c = ws.cell(row=i, column=2, value=text)
            c.alignment = OBEN
            c.font = {"titel": F(size=16, bold=True, color="1F5F5B"), "kopf": F(size=11, bold=True, color="1F5F5B"),
                      "formel": Font(name="Consolas", size=10)}.get(art, F(size=10))
            if art == "kopf":
                ws.row_dimensions[i].height = 22
        return 2 + len(zeilen)


    # =================================================================== Anleitung
    an = wb.active
    an.title = "Anleitung"
    textblatt(an, [
        ("Notenliste Sek I – Anleitung", "titel"),
        ("Unabhängig von Schulnexus nutzbar; in Schulnexus über „Excel-Notentabelle“ beim Unterricht hoch- und herunterzuladen. "
         "Rechenweg und Rundung: Blatt „Erklärung“.", ""),
        ("", ""),
        ("1. Blatt „Master“ ausfüllen", "kopf"),
        ("Klasse, Fach, Lehrkraft und Schuljahr; die Gewichtung der beiden Halbjahre (z. B. 40 : 60, 50 : 50 oder 0 : 100) und die Gewichtung von "
         "Klassenarbeiten und sonstiger Mitarbeit je Halbjahr; Rundungsregel und weitere Einstellungen. Alle anderen Blätter übernehmen diese Werte.", ""),
        ("2. Blatt „1. Halbjahr“", "kopf"),
        ("Namen der Schüler:innen eintragen (nur hier – „2. Halbjahr“ und „Jahresnote“ übernehmen sie in derselben Reihenfolge).", ""),
        ("Zeilen 6–8: Titel, Datum und Gewicht jedes Leistungsnachweises (bis zu 8 Klassenarbeiten, bis zu 20 SoMi-Noten). "
         "Gewicht leer = 1; 0 = zählt nicht; z. B. 0,5 für einen Test.", ""),
        ("Dann die Noten eintragen. Gezählt wird nur, was eingetragen ist – leere Spalten stören nicht.", ""),
        ("3. Blatt „2. Halbjahr“ genauso; das Blatt „Jahresnote“ rechnet selbständig.", "kopf"),
        ("", ""),
        ("Erlaubte Eingaben in den Notenfeldern", "kopf"),
        ("1+  1  1-  2+  2  2-  …  5-  6   (Tendenzwerte im Master)   oder eine Dezimalnote zwischen 0,7 und 6 (z. B. 2,3).", ""),
        ("e = entschuldigt, b = befreit, nb = nicht bewertbar → zählt nicht.   u = unentschuldigt → zählt mit der Ersatznote aus dem Master (Voreinstellung 6).   "
         "leer = noch keine Note.   Minus als Bindestrich tippen (2-).", ""),
        ("", ""),
        ("Farben", "kopf"),
        ("Gelb = Eingabe.   Grau = wird berechnet, nicht überschreiben.   Grüne Schrift = aus einem anderen Blatt übernommen.   "
         "Orange Spalte „Zeugnisnote (festgesetzt)“ = Ihre pädagogische Entscheidung (optional); weicht sie vom Vorschlag ab, erscheint ein Hinweis.", ""),
        ("", ""),
        ("Beispielzeile", "kopf"),
        ("Die allgemeine Vorlage enthält in Zeile 1 eine Beispielschülerin („Beispiel, Anna“); sie wird im Blatt „Erklärung“ durchgerechnet. "
         "Vor dem Einsatz überschreiben oder löschen. Aus Schulnexus heruntergeladene Tabellen enthalten stattdessen die Schüler:innen des Kurses.", ""),
        ("", ""),
        ("Übernahme in Schulnexus", "kopf"),
        ("Beim Unterricht „Excel-Notentabelle“ wählen und die Datei hochladen. Voraussetzung: Die Klasse im Master stimmt mit der Gruppe des "
         "Unterrichts überein und die Namen (Nachname, Vorname) mit den Schüler:innen. Übernommen wird das Blatt des passenden Halbjahres; "
         "vor dem Speichern zeigt Schulnexus eine Vorschau. Leere Zellen löschen keine vorhandenen Noten.", ""),
        ("", ""),
        ("Grenzen", "kopf"),
        ("Nur Sek I (Noten 1–6). Zwei Bereiche (Klassenarbeiten, sonstige Mitarbeit) ohne Unterordner; keine individuellen Gewichte einzelner Noten; "
         "bis zu 35 Schüler:innen. Verwendung in eigener Verantwortung – maßgeblich sind die an der Schule geltenden Bestimmungen.", ""),
    ])

    # =================================================================== Master
    ms = wb.create_sheet("Master")
    ms.sheet_view.showGridLines = False
    for sp, b in (("A", 38), ("B", 15), ("C", 15), ("D", 15), ("E", 62)):
        ms.column_dimensions[sp].width = b
    ms["A1"] = "Master – zentrale Einstellungen"
    ms["A1"].font = F(size=16, bold=True, color="1F5F5B")
    ms["A2"] = "Gelbe Felder ändern; alle Blätter übernehmen die Werte sofort."
    ms["A2"].font = LEISE


    def abschnitt(z, text):
        c = ms.cell(row=z, column=1, value=text)
        c.font = F(size=12, bold=True, color="1F5F5B")


    def label(z, text, hinweis=None):
        ms.cell(row=z, column=1, value=text).font = F(bold=True)
        if hinweis:
            h = ms.cell(row=z, column=5, value=hinweis)
            h.font, h.alignment = LEISE, LINKS


    abschnitt(4, "Kurs")
    for z, (t, w) in enumerate((("Klasse", vg.get("klasse", "9a")), ("Fach", vg.get("fach", "Chemie")), ("Lehrkraft", vg.get("lehrkraft", "")),
                                    ("Schuljahr", vg.get("schuljahr", "2026/27"))), start=5):
        label(z, t)
        zelle(ms, f"B{z}", w, BLAU, EINGABE, "@", MITTE)
        ms.merge_cells(f"B{z}:C{z}")
        name({"Klasse": "Klasse", "Fach": "Fach", "Lehrkraft": "Lehrkraft", "Schuljahr": "Schuljahr"}[t], f"Master!$B${z}")

    abschnitt(10, "Gewichtung der Halbjahre für die Jahresnote")
    kopf(ms, "B11", "Gewicht")
    kopf(ms, "C11", "ergibt Anteil")
    label(12, "1. Halbjahr", "Beliebige Verhältniszahlen, z. B. 40 : 60, 1 : 1 oder 1 : 2. 0 beim 1. Halbjahr = Jahresnote nur aus dem 2. Halbjahr.")
    label(13, "2. Halbjahr")
    g1, g2 = vg.get("gewicht_hj", (40, 60))
    zelle(ms, "B12", g1, F(color="0000FF", bold=True), EINGABE, "0.##", MITTE)
    zelle(ms, "B13", g2, F(color="0000FF", bold=True), EINGABE, "0.##", MITTE)
    zelle(ms, "C12", "=IF(SUM(B12:B13)=0,0,B12/SUM(B12:B13))", F(bold=True), FORMEL, "0%", MITTE)
    zelle(ms, "C13", "=IF(SUM(B12:B13)=0,1,B13/SUM(B12:B13))", F(bold=True), FORMEL, "0%", MITTE)
    name("Anteil", "Master!$C$12")

    abschnitt(15, "Gewichtung innerhalb der Halbjahre")
    kopf(ms, "B16", "1. Halbjahr")
    kopf(ms, "C16", "2. Halbjahr")
    label(17, "Klassenarbeiten", "Verhältniszahlen, z. B. 50 : 50 oder 60 : 40. Fehlt in einem Bereich jede Note, zählt der andere allein (mit Hinweis).")
    label(18, "Sonstige Mitarbeit (SoMi)")
    label(19, "ergibt Anteil Klassenarbeiten")
    bereiche = vg.get("bereiche", {1: (50, 50), 2: (50, 50)})
    for nr_hj, sp, (k, s) in ((1, "B", ("GKA1", "GSM1")), (2, "C", ("GKA2", "GSM2"))):
        zelle(ms, f"{sp}17", bereiche[nr_hj][0], F(color="0000FF", bold=True), EINGABE, "0.##", MITTE)
        zelle(ms, f"{sp}18", bereiche[nr_hj][1], F(color="0000FF", bold=True), EINGABE, "0.##", MITTE)
        zelle(ms, f"{sp}19", f"=IF(SUM({sp}17:{sp}18)=0,\"–\",{sp}17/SUM({sp}17:{sp}18))", F(bold=True), FORMEL, "0%", MITTE)
        name(k, f"Master!${sp}$17")
        name(s, f"Master!${sp}$18")

    abschnitt(21, "Rundung und weitere Einstellungen")
    weitere = [
        (22, "Rundung bei genau x,50", vg.get("regel", "zugunsten"), "@", "Regel", "„zugunsten“ = bessere Note (2,50 → 2); „kaufmännisch“ = aufrunden, in Sek I schlechtere Note (2,50 → 3)."),
        (23, "Grundlage 1. Halbjahr", vg.get("grundlage", "Schnitt"), "@", "Grundlage", "„Schnitt“ = exakter Schnitt des 1. Halbjahres; „Zeugnisnote“ = festgesetzte Halbjahreszeugnisnote (sonst der Vorschlag)."),
        (24, "Ersatznote bei „u“ (unentschuldigt)", vg.get("ersatz", 6), "0.0", "Ersatz", "Leer lassen = „u“ zählt nicht."),
        (25, "„gefährdet“ ab ganzer Note", 5, "0", "GefAb", "Sek I: Note 5 oder 6."),
    ]
    for z, t, w, fmt, n, h in weitere:
        label(z, t, h)
        zelle(ms, f"B{z}", w, BLAU, EINGABE, fmt, MITTE)
        ms.merge_cells(f"B{z}:C{z}")
        name(n, f"Master!$B${z}")

    abschnitt(27, "Notenstufen (Tendenzwerte)")
    ms["E27"] = "Reihenfolge von der besten zur schlechtesten Stufe beibehalten; Werte änderbar (Voreinstellung wie in Schulnexus)."
    ms["E27"].font = LEISE
    kopf(ms, "A28", "Eingabe")
    kopf(ms, "B28", "Interner Wert")
    for i, (bez, w) in enumerate(STUFEN, start=29):
        zelle(ms, f"A{i}", bez, BLAU, EINGABE, "@", MITTE)
        zelle(ms, f"B{i}", w, BLAU, EINGABE, "0.00", MITTE)
    ende = 28 + len(STUFEN)
    name("StBez", f"Master!$A$29:$A${ende}")
    name("StWert", f"Master!$B$29:$B${ende}")

    for ref, formel, fehler in (("B12:B13", "B12>=0", "Gewicht: Zahl ≥ 0."), ("B17:C18", "B17>=0", "Gewicht: Zahl ≥ 0.")):
        d = DataValidation(type="custom", formula1=f"AND(ISNUMBER({formel.split('>')[0]}),{formel})", showErrorMessage=True, error=fehler)
        ms.add_data_validation(d)
        d.add(ref)
    for ref, liste in (("B22", '"zugunsten,kaufmännisch"'), ("B23", '"Schnitt,Zeugnisnote"')):
        d = DataValidation(type="list", formula1=liste, allow_blank=False, showErrorMessage=True)
        ms.add_data_validation(d)
        d.add(ref)
    ms.conditional_formatting.add("C12:C13", FormulaRule(formula=["SUM($B$12:$B$13)=0"], fill=PatternFill("solid", fgColor="F8D7DA")))


    # =================================================================== Formelbausteine
    def wert_aus_eingabe(e):
        zahl = f'VALUE(SUBSTITUTE(SUBSTITUTE(TRIM({e}&""),",",{SEP}),".",{SEP}))'
        return (f'=IF(OR(TRIM({e}&"")="",LOWER({e}&"")="e",LOWER({e}&"")="b",LOWER({e}&"")="nb"),"",'
                f'IF(LOWER({e}&"")="u",IF(ISNUMBER(Ersatz),Ersatz,""),'
                f'IFERROR(INDEX(StWert,MATCH(TRIM({e}&""),StBez,0)),'
                f'IFERROR(IF(AND({zahl}>=0.7,{zahl}<=6),{zahl},"?"),"?"))))')


    def bereichsschnitt(gw, pr):
        """Nur eingetragene Noten zählen: Σ Produkte / Σ wirksame Gewichte (Hilfsspalten, nur SUM)."""
        return f'=IF(SUM({gw})=0,"",SUM({pr})/SUM({gw}))'


    def gerundet(t):
        return f"ROUND({t},10)"


    def ganz(t):
        y = gerundet(t)
        return f'=IF(ISNUMBER({t}),MAX(1,MIN(6,IF(MOD({y},1)=0.5,IF(Regel="kaufmännisch",INT({y})+1,INT({y})),ROUND({y},0)))),"")'


    def tendenz(ws, ref, t):
        """Nächstgelegene Stufe ohne Matrixformel: StWert ist aufsteigend sortiert; Nachbarn per MATCH(…;1) vergleichen."""
        i = f"IFERROR(MATCH({t},StWert,1),1)"
        j = f"MIN({i}+1,ROWS(StWert))"
        dl = f"ABS(ROUND({t}-INDEX(StWert,{i}),10))"
        du = f"ABS(ROUND(INDEX(StWert,{j})-{t},10))"
        ws[ref] = (f'=IF(ISNUMBER({t}),INDEX(StBez,IF({du}<{dl},{j},IF({du}>{dl},{i},IF(Regel="kaufmännisch",{j},{i})))),"")')


    def grenzfall(t):
        y = gerundet(t)
        return (f'IF(ISNUMBER({t}),IF(AND(ABS(MOD({y},1)-0.5)<0.005,MOD({y},1)<>0.5),'
                f'"Grenzfall: exakt "&FIXED({t},3,TRUE)&"; ",""),"")')


    # =================================================================== Halbjahresblätter
    def halbjahr(titel, nr):
        ws = wb.create_sheet(titel)
        ws.sheet_view.showGridLines = False
        ws.sheet_view.zoomScale = 90
        gka, gsm = f"GKA{nr}", f"GSM{nr}"
        ws["A1"] = f"Notenliste {titel}"
        ws["A1"].font = F(size=14, bold=True, color="1F5F5B")
        ws["A2"] = '="Klasse "&Klasse&" · "&Fach&IF(Lehrkraft="",""," · "&Lehrkraft)&" · Schuljahr "&Schuljahr'
        ws["A2"].font = F(size=10, color="008000")

        ws.merge_cells(start_row=4, start_column=SP_K, end_row=4, end_column=SP_S - 1)
        ws.merge_cells(start_row=4, start_column=SP_S, end_row=4, end_column=SP_ENDE)
        kopf(ws, f"{L(SP_K)}4", "Klassenarbeiten")
        kopf(ws, f"{L(SP_S)}4", "Sonstige Mitarbeit (SoMi)")
        for r, lab in ((5, "Gewicht des Bereichs (aus Master) →"), (6, "Leistungsnachweis →"), (7, "Datum →"),
                       (8, "Gewicht (leer = 1) →")):
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
            c = ws.cell(row=r, column=1, value=lab)
            c.font, c.alignment = F(bold=True, size=9, color="5B6670"), Alignment(horizontal="right", vertical="center")
        ws.merge_cells(start_row=5, start_column=SP_K, end_row=5, end_column=SP_S - 1)
        ws.merge_cells(start_row=5, start_column=SP_S, end_row=5, end_column=SP_ENDE)
        zelle(ws, f"{L(SP_K)}5", f'={gka}&"  ("&IF(({gka}+{gsm})=0,"–",FIXED({gka}/({gka}+{gsm})*100,0)&" %")&")"',
              F(color="008000", bold=True), FORMEL, None, MITTE)
        zelle(ws, f"{L(SP_S)}5", f'={gsm}&"  ("&IF(({gka}+{gsm})=0,"–",FIXED({gsm}/({gka}+{gsm})*100,0)&" %")&")"',
              F(color="008000", bold=True), FORMEL, None, MITTE)
        for sp in range(SP_K, SP_ENDE + 1):
            ka = sp < SP_S
            nr_ln = sp - SP_K + 1 if ka else sp - SP_S + 1
            zelle(ws, f"{L(sp)}6", f"KA {nr_ln}" if ka else f"SoMi {nr_ln}", F(color="0000FF", size=8), EINGABE, "@", MITTE)
            zelle(ws, f"{L(sp)}7", None, F(color="0000FF", size=8), EINGABE, "DD.MM.", MITTE)
            zelle(ws, f"{L(sp)}8", None, F(color="0000FF", size=8), EINGABE, "0.0#", MITTE)
            zelle(ws, f"{L(sp)}9", f"={L(sp)}6", F(bold=True, size=8, color="1F5F5B"), KOPF2, None, MITTE)
            ws.column_dimensions[L(sp)].width = 6.3 if ka else 6.0
        for sp, t in ((1, "Nr."), (2, "Nachname"), (3, "Vorname")):
            kopf(ws, f"{L(sp)}9", t)
        namen = ["Ø Klassen-arbeiten", "Ø SoMi", "Halbjahres-schnitt", "Ganze Note (Vorschlag)", "Tendenz",
                 "Zeugnisnote (festgesetzt)", "gefährdet", "Hinweis"]
        for i, t in enumerate(namen):
            sp = ERG + i
            ws.merge_cells(start_row=4, start_column=sp, end_row=9, end_column=sp)
            kopf(ws, f"{L(sp)}4", t, fill=ORANGE if "festgesetzt" in t else KOPF)
            ws.column_dimensions[L(sp)].width = [9, 8, 10, 10, 8, 11, 10, 44][i]
        ws.column_dimensions["A"].width = 4.5
        ws.column_dimensions["B"].width = 15
        ws.column_dimensions["C"].width = 12
        ws.row_dimensions[9].height = 26
        ws.row_dimensions[8].height = 16
        K, S_, T, U, V, W, X, Y = (L(ERG + i) for i in range(8))

        for sp in range(SP_K, SP_ENDE + 1):
            for block, txt in enumerate(("Wert", "Gew.", "Prod.")):
                h = HELFER + block * ANZ + sp - SP_K
                zelle(ws, f"{L(h)}9", f"{txt} {L(sp)}", F(size=8, color="5B6670"), FORMEL, None, MITTE)
        ws.column_dimensions.group(L(HELFER - 1), L(HELFER + 3 * ANZ - 1), hidden=True, outline_level=1)

        for r in range(ERSTE, LETZTE + 1):
            zelle(ws, f"A{r}", r - ERSTE + 1, F(size=9, color="5B6670"), None, None, MITTE)
            for sp in ("B", "C"):
                if nr == 1:
                    zelle(ws, f"{sp}{r}", None, BLAU, EINGABE, "@")
                else:
                    zelle(ws, f"{sp}{r}", f"=IF('1. Halbjahr'!{sp}{r}=\"\",\"\",'1. Halbjahr'!{sp}{r})", GRUEN, FORMEL)
            for sp in range(SP_K, SP_ENDE + 1):
                zelle(ws, f"{L(sp)}{r}", None, BLAU, EINGABE, "@", MITTE)
                h = ws.cell(row=r, column=HELFER + sp - SP_K, value=wert_aus_eingabe(f"{L(sp)}{r}"))
                h.number_format, h.font = "0.00", F(size=8, color="5B6670")
                hw = L(HELFER + sp - SP_K)
                g = ws.cell(row=r, column=HELFER + ANZ + sp - SP_K,
                            value=f'=IF(ISNUMBER({hw}{r}),IF(ISNUMBER({L(sp)}$8),{L(sp)}$8,1),0)')
                pr = ws.cell(row=r, column=HELFER + 2 * ANZ + sp - SP_K, value=f'=IF(ISNUMBER({hw}{r}),{hw}{r}*{L(g.column)}{r},0)')
                for c in (g, pr):
                    c.number_format, c.font = "0.00", F(size=8, color="5B6670")
            def spanne(block, von, anz):
                a = HELFER + block * ANZ + von
                return f"{L(a)}{r}:{L(a + anz - 1)}{r}"
            ws[f"{K}{r}"] = bereichsschnitt(spanne(1, 0, N_KA), spanne(2, 0, N_KA))
            ws[f"{S_}{r}"] = bereichsschnitt(spanne(1, N_KA, N_SOMI), spanne(2, N_KA, N_SOMI))
            k, s = f"{K}{r}", f"{S_}{r}"
            ws[f"{T}{r}"] = (f'=IFERROR(IF(AND(NOT(ISNUMBER({k})),NOT(ISNUMBER({s}))),"",'
                             f'(IF(ISNUMBER({k}),{k}*{gka},0)+IF(ISNUMBER({s}),{s}*{gsm},0))'
                             f'/(IF(ISNUMBER({k}),{gka},0)+IF(ISNUMBER({s}),{gsm},0))),"")')
            t = f"{T}{r}"
            ws[f"{U}{r}"] = ganz(t)
            tendenz(ws, f"{V}{r}", t)
            ws[f"{X}{r}"] = f'=IF({U}{r}="","",IF({U}{r}>=GefAb,"gefährdet",""))'
            ws[f"{Y}{r}"] = (f'=IF(COUNTIF({L(HELFER)}{r}:{L(HELFER + SP_ENDE - SP_K)}{r},"?")>0,"ungültige Eingabe; ","")'
                             f'&IF(AND(ISNUMBER({k}),NOT(ISNUMBER({s})),{gsm}>0),"nur Klassenarbeiten; ",'
                             f'IF(AND(ISNUMBER({s}),NOT(ISNUMBER({k})),{gka}>0),"nur SoMi; ",""))'
                             f'&IF(AND(ISNUMBER({k}),ISNUMBER({s}),NOT(ISNUMBER({t}))),"Bereichsgewichte im Master sind 0; ","")'
                             f'&{grenzfall(t)}'
                             f'&IF(AND(ISNUMBER({W}{r}),ISNUMBER({U}{r})),IF({W}{r}<>{U}{r},"Zeugnisnote weicht vom Vorschlag ab; ",""),"")')
            for sp, fmt in ((K, "0.00"), (S_, "0.00"), (T, "0.00"), (U, "0"), (V, "@"), (W, "0"), (X, "@"), (Y, "@")):
                c = ws[f"{sp}{r}"]
                c.border, c.number_format = RAND, fmt
                c.alignment = LINKS if sp == Y else MITTE
                if sp == W:
                    c.fill, c.font = EINGABE, F(color="0000FF", bold=True)
                else:
                    c.fill, c.font = FORMEL, F(bold=sp in (T, U), size=8 if sp == Y else 10)

        e0 = f"{L(SP_K)}{ERSTE}"
        zahl = f'VALUE(SUBSTITUTE(SUBSTITUTE(TRIM({e0}&""),",",{SEP}),".",{SEP}))'
        erlaubt = (f'OR(TRIM({e0}&"")="",LOWER({e0}&"")="e",LOWER({e0}&"")="b",LOWER({e0}&"")="nb",LOWER({e0}&"")="u",'
                   f'ISNUMBER(MATCH(TRIM({e0}&""),StBez,0)),AND(ISNUMBER({zahl}),{zahl}>=0.7,{zahl}<=6))')
        d = DataValidation(type="custom", formula1=erlaubt, allow_blank=True, showErrorMessage=True, errorStyle="warning",
                           errorTitle="Ungültige Note", error="Erlaubt: 1+ … 6 (z. B. 2-), Dezimalnote 0,7–6, e, b, nb, u oder leer.")
        ws.add_data_validation(d)
        d.add(f"{L(SP_K)}{ERSTE}:{L(SP_ENDE)}{LETZTE}")
        d = DataValidation(type="custom", formula1=f'OR({L(SP_K)}8="",AND(ISNUMBER({L(SP_K)}8),{L(SP_K)}8>=0))', allow_blank=True,
                           showErrorMessage=True, error="Gewicht: Zahl ≥ 0 oder leer (= 1).")
        ws.add_data_validation(d)
        d.add(f"{L(SP_K)}8:{L(SP_ENDE)}8")
        d = DataValidation(type="whole", operator="between", formula1="1", formula2="6", allow_blank=True, showErrorMessage=True,
                           error="Zeugnisnote: ganze Note 1 bis 6.")
        ws.add_data_validation(d)
        d.add(f"{W}{ERSTE}:{W}{LETZTE}")
        rot = Font(name=SCHRIFT, color="C00000", bold=True)
        ws.conditional_formatting.add(f"{X}{ERSTE}:{X}{LETZTE}", FormulaRule(formula=[f'{X}{ERSTE}="gefährdet"'], font=rot))
        ws.conditional_formatting.add(f"{U}{ERSTE}:{U}{LETZTE}", FormulaRule(formula=[f'AND(ISNUMBER({U}{ERSTE}),{U}{ERSTE}>=GefAb)'], font=rot))
        ws.conditional_formatting.add(f"{Y}{ERSTE}:{Y}{LETZTE}", FormulaRule(formula=[f'{Y}{ERSTE}<>""'], font=Font(name=SCHRIFT, color="B4532A", size=8)))
        ws.freeze_panes = ws[f"{L(SP_K)}{ERSTE}"]
        ws.print_title_rows = "4:9"
        ws.page_setup.orientation = "landscape"
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.print_area = f"A1:{Y}{LETZTE}"
        return ws, (K, S_, T, U, V, W)


    hj1, (K1, S1, T1, U1, V1, W1) = halbjahr("1. Halbjahr", 1)
    hj2, (K2, S2, T2, U2, V2, W2) = halbjahr("2. Halbjahr", 2)

    if vg.get("schueler") is None:
        # allgemeine Vorlage: Beispielzeile
        for ws, werte in ((hj1, {"B": "Beispiel", "C": "Anna", "D": "2-", "E": "3", "L": "2", "M": "2+", "N": "e", "O": "3", "P": "2"}),
                          (hj2, {"D": "3+", "E": "2", "L": "2", "M": "3-", "N": "u", "O": "2-"})):
            for k, v in werte.items():
                ws[f"{k}{ERSTE}"] = v
        hj1["M8"], hj1["N8"] = 0.5, 0.5
        hj1[f"B{ERSTE}"].comment = Comment("Beispielzeile – wird im Blatt „Erklärung“ durchgerechnet. Vor dem Einsatz überschreiben oder löschen.",
                                           "Notenliste")
    else:
        for i, (nachname, vorname) in enumerate(vg["schueler"][:ANZAHL]):
            hj1[f"B{ERSTE + i}"], hj1[f"C{ERSTE + i}"] = nachname, vorname
        for nr_hj, ws in ((1, hj1), (2, hj2)):
            for bereich, start, anzahl in (("ka", SP_K, N_KA), ("somi", SP_S, N_SOMI)):
                for j, sp_daten in enumerate(vg.get("spalten", {}).get(nr_hj, {}).get(bereich, [])[:anzahl]):
                    sp = L(start + j)
                    ws[f"{sp}6"] = sp_daten["titel"]
                    if sp_daten.get("datum"):
                        ws[f"{sp}7"] = sp_daten["datum"]
                    if sp_daten.get("gewicht") is not None and sp_daten["gewicht"] != 1:
                        ws[f"{sp}8"] = sp_daten["gewicht"]
                    for zeile, text in sp_daten.get("noten", {}).items():
                        if 0 <= zeile < ANZAHL:
                            ws[f"{sp}{ERSTE + zeile}"] = text

    # =================================================================== Jahresnote
    jn = wb.create_sheet("Jahresnote")
    jn.sheet_view.showGridLines = False
    jn["A1"] = "Jahresnote (Vorschlag für das Jahreszeugnis)"
    jn["A1"].font = F(size=14, bold=True, color="1F5F5B")
    jn["A2"] = ('="Klasse "&Klasse&" · "&Fach&" · Gewichtung 1. : 2. Halbjahr = "&Master!B12&" : "&Master!B13&'
                '" ("&FIXED(Anteil*100,0)&" % / "&FIXED((1-Anteil)*100,0)&" %) · Grundlage: "&Grundlage&" · Rundung: "&Regel')
    jn["A2"].font = F(size=9, color="008000")
    spalten = ["Nr.", "Nachname", "Vorname", "Schnitt 1. Hj.", "Zeugnisnote 1. Hj.", "W1 (verwendet)", "Schnitt 2. Hj.",
               "Jahres-schnitt", "Ganze Note (Vorschlag)", "Tendenz", "Zeugnisnote (festgesetzt)", "gefährdet", "Hinweis"]
    for i, (t, b) in enumerate(zip(spalten, [4.5, 15, 12, 10, 11, 10, 10, 10, 11, 9, 11, 10, 50]), start=1):
        jn.merge_cells(start_row=4, start_column=i, end_row=9, end_column=i)
        kopf(jn, f"{L(i)}4", t, fill=ORANGE if "festgesetzt" in t else KOPF)
        jn.column_dimensions[L(i)].width = b
    for r in range(ERSTE, LETZTE + 1):
        jn[f"A{r}"] = r - ERSTE + 1
        for sp in ("B", "C"):
            jn[f"{sp}{r}"] = f"=IF('1. Halbjahr'!{sp}{r}=\"\",\"\",'1. Halbjahr'!{sp}{r})"
        jn[f"D{r}"] = f"=IF(ISNUMBER('1. Halbjahr'!{T1}{r}),'1. Halbjahr'!{T1}{r},\"\")"
        jn[f"E{r}"] = (f"=IF(ISNUMBER('1. Halbjahr'!{W1}{r}),'1. Halbjahr'!{W1}{r},"
                       f"IF(ISNUMBER('1. Halbjahr'!{U1}{r}),'1. Halbjahr'!{U1}{r},\"\"))")
        jn[f"F{r}"] = f'=IF(Grundlage="Zeugnisnote",E{r},D{r})'
        jn[f"G{r}"] = f"=IF(ISNUMBER('2. Halbjahr'!{T2}{r}),'2. Halbjahr'!{T2}{r},\"\")"
        jn[f"H{r}"] = (f'=IF(AND(NOT(ISNUMBER(F{r})),NOT(ISNUMBER(G{r}))),"",IF(OR(Anteil=0,NOT(ISNUMBER(F{r}))),'
                       f'IF(ISNUMBER(G{r}),G{r},""),IF(OR(Anteil=1,NOT(ISNUMBER(G{r}))),F{r},Anteil*F{r}+(1-Anteil)*G{r})))')
        jn[f"I{r}"] = ganz(f"H{r}")
        tendenz(jn, f"J{r}", f"H{r}")
        jn[f"L{r}"] = f'=IF(I{r}="","",IF(I{r}>=GefAb,"gefährdet",""))'
        jn[f"M{r}"] = (f'=IF(AND(ISNUMBER(F{r}),NOT(ISNUMBER(G{r}))),IF(Anteil=0,"noch keine Note im 2. Halbjahr; ",'
                       f'IF(Anteil<1,"noch keine Note im 2. Halbjahr – nur 1. Halbjahr; ","")),"")'
                       f'&IF(AND(ISNUMBER(G{r}),NOT(ISNUMBER(F{r})),Anteil>0),"ohne 1. Halbjahr – nur 2. Halbjahr; ","")'
                       f'&{grenzfall(f"H{r}")}'
                       f'&IF(AND(ISNUMBER(K{r}),ISNUMBER(I{r})),IF(K{r}<>I{r},"Zeugnisnote weicht vom Vorschlag ab; ",""),"")')
        for sp in "ABCDEFGHIJKLM":
            c = jn[f"{sp}{r}"]
            c.border = RAND
            c.alignment = LINKS if sp == "M" else MITTE
            c.number_format = {"D": "0.00", "F": "0.00", "G": "0.00", "H": "0.00", "E": "0", "I": "0", "K": "0"}.get(sp, "General")
            if sp == "K":
                c.fill, c.font = EINGABE, F(color="0000FF", bold=True)
            else:
                c.fill = FORMEL
                c.font = GRUEN if sp in "BCDEG" else F(bold=sp in "HI", size=8 if sp == "M" else 9 if sp == "A" else 10)
    d = DataValidation(type="whole", operator="between", formula1="1", formula2="6", allow_blank=True, showErrorMessage=True,
                       error="Zeugnisnote: ganze Note 1 bis 6.")
    jn.add_data_validation(d)
    d.add(f"K{ERSTE}:K{LETZTE}")
    rot = Font(name=SCHRIFT, color="C00000", bold=True)
    jn.conditional_formatting.add(f"L{ERSTE}:L{LETZTE}", FormulaRule(formula=[f'L{ERSTE}="gefährdet"'], font=rot))
    jn.conditional_formatting.add(f"I{ERSTE}:I{LETZTE}", FormulaRule(formula=[f'AND(ISNUMBER(I{ERSTE}),I{ERSTE}>=GefAb)'], font=rot))
    jn.conditional_formatting.add(f"M{ERSTE}:M{LETZTE}", FormulaRule(formula=[f'M{ERSTE}<>""'], font=Font(name=SCHRIFT, color="B4532A", size=8)))
    jn.freeze_panes = jn[f"D{ERSTE}"]
    jn.page_setup.orientation = "landscape"
    jn.sheet_properties.pageSetUpPr.fitToPage = True
    jn.page_setup.fitToHeight = 0

    # =================================================================== Erklärung
    er = wb.create_sheet("Erklärung")
    weiter = textblatt(er, [
        ("Erklärung der Berechnung", "titel"),
        ("Die Tabelle rechnet wie Schulnexus, mit einer Ausnahme: Die ganze Note wird aus dem exakten Schnitt gebildet, nicht aus dem auf zwei "
         "Stellen gerundeten (keine Doppelrundung).", ""),
        ("", ""),
        ("Schritt 1 – Notenwert", "kopf"),
        ("Jede Eingabe wird in einen Zahlenwert übersetzt: 1+ = 0,7 · 1 = 1,0 · 1- = 1,3 · 2+ = 1,7 … 5- = 5,3 · 6 = 6,0 (Tabelle im Master). "
         "Dezimalnoten zählen mit ihrem Wert. e (entschuldigt) und b (befreit) zählen nicht, u (unentschuldigt) mit der Ersatznote (Voreinstellung 6).", ""),
        ("Schritt 2 – Schnitt je Bereich (Klassenarbeiten bzw. SoMi)", "kopf"),
        ("Ø Bereich = Σ (Gewicht · Notenwert) / Σ Gewicht", "formel"),
        ("Summiert wird nur über Leistungsnachweise, bei denen für diese Schülerin bzw. diesen Schüler eine zählende Note steht. Leere Spalten, "
         "noch nicht geschriebene Arbeiten oder e/b verändern den Schnitt also nicht. Gewicht leer = 1, 0 = zählt nicht.", ""),
        ("Schritt 3 – Halbjahresschnitt", "kopf"),
        ("Halbjahr = (Ø KA · Gewicht KA + Ø SoMi · Gewicht SoMi) / (Gewicht KA + Gewicht SoMi)      Gewichte aus dem Master, je Halbjahr", "formel"),
        ("Fehlt in einem Bereich jede Note, entfällt er; der andere zählt allein (Hinweis „nur Klassenarbeiten“ bzw. „nur SoMi“).", ""),
        ("Schritt 4 – Jahresschnitt", "kopf"),
        ("Jahr = a · W1 + (1 − a) · Halbjahr 2      a = Gewicht 1. Hj. / (Gewicht 1. Hj. + Gewicht 2. Hj.) aus dem Master", "formel"),
        ("W1 ist je nach Master-Einstellung der exakte Schnitt des 1. Halbjahres oder dessen Zeugnisnote (festgesetzt, sonst Vorschlag). "
         "Fehlt das 2. Halbjahr noch, gilt W1 (Hinweis); bei a = 0 zählt nur das 2. Halbjahr.", ""),
        ("Schritt 5 – Rundung", "kopf"),
        ("Alle Schnitte werden exakt weiterverwendet; die zwei Nachkommastellen sind nur Anzeige. Die ganze Note entsteht direkt aus dem exakten Wert:", ""),
        ("unter x,50 → abrunden (bessere Note) · über x,50 → aufrunden · genau x,50 → nach Master-Regel: „zugunsten“ = bessere Note, "
         "„kaufmännisch“ = aufrunden (in Sek I schlechtere Note).", ""),
        ("Liegt der exakte Wert weniger als 0,005 neben x,50, erscheint „Grenzfall: exakt …“ mit drei Nachkommastellen – angezeigt wird dann z. B. 2,50, "
         "die Note ist aber 3, weil der exakte Wert 2,503 beträgt.", ""),
        ("Tendenz = nächstgelegene Stufe der Tabelle (bei Gleichstand nach derselben Regel). „gefährdet“ = ganze Note ≥ Wert im Master (5).", ""),
        ("Technisch: Excel rechnet mit Gleitkommazahlen; vor der Prüfung auf genau x,50 wird deshalb auf 10 Nachkommastellen gerundet "
         "(entfernt nur Rechenrauschen).", ""),
        ("", ""),
        ("Rechenbeispiel (live): Zeile 1 der Notenlisten", "kopf"),
    ])
    for i in range(2, weiter):
        c = er.cell(row=i, column=2)
        if c.value:
            er.merge_cells(start_row=i, start_column=2, end_row=i, end_column=4)
            if c.font.name != "Consolas" and not (c.font.size and c.font.size >= 11):
                er.row_dimensions[i].height = 14 * max(1, math.ceil(len(str(c.value)) / 125))
    r0 = weiter + 1
    er.column_dimensions["B"].width = 34
    er.column_dimensions["C"].width = 78
    er.column_dimensions["D"].width = 14
    for i, t in enumerate(("Größe", "eingesetzt", "Ergebnis"), start=2):
        kopf(er, f"{L(i)}{r0}", t, groesse=10)
    z = ERSTE
    h1, h2 = "'1. Halbjahr'", "'2. Halbjahr'"


    def liste(blatt, von, bis):
        """Text „Note·Gewicht + …“ der eingetragenen Noten in einem Bereich der Beispielzeile."""
        teile = []
        for sp in range(von, bis + 1):
            hw = f"{blatt}!{L(HELFER + sp - SP_K)}{z}"
            g = f"IF({blatt}!{L(sp)}$8=\"\",1,{blatt}!{L(sp)}$8)"
            teile.append(f'IF(ISNUMBER({hw}),FIXED({g},2,TRUE)&" · "&FIXED({hw},2,TRUE)&" + ","")')
        return "&".join(teile)


    def ohne_letztes_plus(ausdruck):
        return f'IFERROR(LEFT({ausdruck},LEN({ausdruck})-3),"")'


    beispiel = [
        ("Ø Klassenarbeiten 1. Hj.", f'="("&{ohne_letztes_plus(liste(h1, SP_K, SP_S - 1))}&") / Σ Gewichte"', f"={h1}!{K1}{z}"),
        ("Ø SoMi 1. Hj.", f'="("&{ohne_letztes_plus(liste(h1, SP_S, SP_ENDE))}&") / Σ Gewichte"', f"={h1}!{S1}{z}"),
        ("Halbjahresschnitt 1. Hj.", f'="("&FIXED({h1}!{K1}{z},4,TRUE)&" · "&GKA1&" + "&FIXED({h1}!{S1}{z},4,TRUE)&" · "&GSM1&") / ("&GKA1&" + "&GSM1&")"',
         f"={h1}!{T1}{z}"),
        ("Ø Klassenarbeiten 2. Hj.", f'="("&{ohne_letztes_plus(liste(h2, SP_K, SP_S - 1))}&") / Σ Gewichte"', f"={h2}!{K2}{z}"),
        ("Ø SoMi 2. Hj. (u = Ersatznote)", f'="("&{ohne_letztes_plus(liste(h2, SP_S, SP_ENDE))}&") / Σ Gewichte"', f"={h2}!{S2}{z}"),
        ("Halbjahresschnitt 2. Hj.", f'="("&FIXED({h2}!{K2}{z},4,TRUE)&" · "&GKA2&" + "&FIXED({h2}!{S2}{z},4,TRUE)&" · "&GSM2&") / ("&GKA2&" + "&GSM2&")"',
         f"={h2}!{T2}{z}"),
        ("Anteil a des 1. Halbjahres", '=Master!B12&" / ("&Master!B12&" + "&Master!B13&")"', "=Anteil"),
        ("Jahresschnitt", f'=FIXED(Anteil,4,TRUE)&" · "&FIXED(Jahresnote!F{z},4,TRUE)&" + "&FIXED(1-Anteil,4,TRUE)&" · "&FIXED(Jahresnote!G{z},4,TRUE)',
         f"=Jahresnote!H{z}"),
        ("Ganze Note (Vorschlag)", f'="Rundung „"&Regel&"“ aus dem exakten Wert "&FIXED(Jahresnote!H{z},4,TRUE)', f"=Jahresnote!I{z}"),
        ("Tendenz", f'="nächstgelegene Stufe zu "&FIXED(Jahresnote!H{z},4,TRUE)', f"=Jahresnote!J{z}"),
    ]
    for i, (g, eing, erg) in enumerate(beispiel, start=r0 + 1):
        zelle(er, f"B{i}", g, F(bold=True, size=10), None, None, LINKS)
        zelle(er, f"C{i}", f'=IFERROR({eing[1:]},"–")', Font(name="Consolas", size=9, color="008000"), FORMEL, "@", LINKS)
        zelle(er, f"D{i}", erg, F(bold=True, color="008000"), FORMEL,
              "0%" if g.startswith("Anteil") else "0" if g.startswith("Ganze") else "@" if g == "Tendenz" else "0.0000", MITTE)
        er.row_dimensions[i].height = 28
    er.cell(row=r0 + len(beispiel) + 2, column=2,
            value="Die Werte ändern sich mit, wenn Sie die Noten in Zeile 1 oder die Gewichte im Master ändern.").font = LEISE

    for ws, quer in ((ms, False), (er, True), (an, False)):
        ws.page_setup.orientation = "landscape" if quer else "portrait"
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
    # Reihenfolge und Schriftart
    wb._sheets = [an, ms, hj1, hj2, jn, er]
    wb.active = 1
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if c.font is not None and c.font.name not in (SCHRIFT, "Consolas"):
                    c.font = Font(name=SCHRIFT, size=c.font.size, bold=c.font.bold, color=c.font.color)
    MUSTER = re.compile(r"(?<![A-Za-z0-9_!'.$])(" + "|".join(sorted(NAMEN, key=len, reverse=True)) + r")(?![A-Za-z0-9_(])")


    def einsetzen(formel):
        teile = formel.split('"')
        for k in range(0, len(teile), 2):          # gerade Indizes liegen außerhalb von "…"
            teile[k] = MUSTER.sub(lambda m: NAMEN[m.group(1)], teile[k])
        return '"'.join(teile)


    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    c.value = einsetzen(c.value)
        for dv in ws.data_validations.dataValidation:
            if dv.formula1:
                dv.formula1 = einsetzen(dv.formula1)
        for bereich in ws.conditional_formatting:
            for regel in bereich.rules:
                regel.formula = [einsetzen(f) for f in (regel.formula or [])]
    wb.calculation.fullCalcOnLoad = True
    puffer = io.BytesIO()
    wb.save(puffer)
    return puffer.getvalue()
