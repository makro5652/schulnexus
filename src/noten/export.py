"""
Druck und Export der Notenübersicht eines Unterrichts (ab 0.4.8.0):
- Excel (.xlsx): Notenübersicht, Leistungsnachweise, Bewertungsstruktur
- PDF „Notenbogen“: Kursübersicht (quer) und je Schüler:in ein Bogen mit allen Noten, Gewichten und Rechenweg
Die Dateien werden nicht gespeichert, sondern direkt ausgeliefert; jeder Abruf steht im Protokoll.
"""
import io
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from xml.sax.saxutils import escape

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import formats, timezone
from django.utils.translation import gettext as _

from portal.rechte import darf_unterricht_sehen

from .ansichten import gewicht_text
from .berechnung import Baum, Vorhalbjahr, nominale_anteile, vorschlagsnote
from .models import Note, Unterricht, Zeugnisnote, weicht_ab


def _zahl(wert, stellen=2):
    if wert is None:
        return ""
    # number_format schneidet ab statt zu runden – daher vorher kaufmännisch auf die Stellen runden
    gerundet = Decimal(wert).quantize(Decimal(1).scaleb(-stellen), rounding=ROUND_HALF_UP)
    return formats.number_format(gerundet, stellen, use_l10n=True)


def _note_text(n, skala):
    if n is None:
        return ""
    if n.stufe_id:
        text = n.stufe.bezeichnung
        if n.sonderstatus == "unentschuldigt":
            text = f"{n.sonderstatus_kurz} {text}"
    elif n.sonderstatus:
        text = str(n.sonderstatus_kurz)
        if n.sonderstatus == "unentschuldigt" and skala.unentschuldigt_stufe_id:
            text += f" ({skala.unentschuldigt_stufe.bezeichnung})"
    else:
        return ""
    if n.gewicht_individuell is not None and n.gewicht_individuell != n.leistungsnachweis.gewicht:
        text += f" ×{_zahl(n.gewicht_individuell, 2).rstrip('0').rstrip(',').rstrip('.')}"
    return text


def datensatz(u):
    """Alle Angaben für Excel und PDF in einer Struktur."""
    baum = Baum(u)
    anteil_o, anteil_ln = nominale_anteile(baum.ordner, baum.nachweise)
    art_von = {o.pk: o.gewichtsart for o in baum.ordner}
    spalten = [{"ln": ln, "pfad": pfad, "anteil": anteil_ln.get(ln.pk), "gewicht": gewicht_text(ln.gewicht, art_von.get(ln.ordner_id))}
               for ln, pfad in baum.nachweise_in_reihenfolge()]
    ordner = [{"o": o, "ebene": ebene, "pfad": pfad, "anteil": anteil_o.get(o.pk),
               "gewicht": gewicht_text(o.gewicht, art_von.get(o.eltern_id) if o.eltern_id else u.gewichtsart)}
              for o, ebene, pfad in baum.in_reihenfolge()]
    noten_je = defaultdict(list)
    for n in Note.objects.filter(leistungsnachweis__unterricht=u).select_related("stufe", "leistungsnachweis"):
        noten_je[n.schueler_id].append(n)
    zeugnis = {z.schueler_id: z for z in Zeugnisnote.objects.filter(unterricht=u).select_related("stufe")}
    jahr = Vorhalbjahr(u) if u.mit_jahresnote else False
    zeilen = []
    for s in u.schueler():
        nach_ln = {n.leistungsnachweis_id: n for n in noten_je[s.pk]}
        v = vorschlagsnote(u, s, noten_je[s.pk], baum, jahr=jahr)
        z = zeugnis.get(s.pk)
        zeilen.append({
            "s": s, "name": s.person.anzeigename if hasattr(s.person, "anzeigename") else str(s.person),
            "noten": [nach_ln.get(sp["ln"].pk) for sp in spalten],
            "texte": [_note_text(nach_ln.get(sp["ln"].pk), u.skala) for sp in spalten],
            "v": v, "zeugnis": (z.stufe.bezeichnung if z and z.stufe_id else (z.get_vermerk_display() if z and z.vermerk else "")),
            "abweichung": bool(z and z.stufe_id and weicht_ab(u.skala, v.schnitt, z.stufe)),
        })
    return {"u": u, "spalten": spalten, "ordner": ordner, "zeilen": zeilen, "jahresnote": u.mit_jahresnote,
            "stand": timezone.localtime()}


def _dateiname(u, endung):
    roh = f"Noten_{u.fach.kuerzel}_{u.gruppe.name}_{u.abschnitt.schuljahr.name}_{u.abschnitt.nummer}HJ".replace("/", "-").replace(" ", "_")
    return f"{roh}.{endung}"


def _pruefen(request, pk):
    u = get_object_or_404(Unterricht.objects.select_related("fach", "gruppe", "abschnitt__schuljahr", "skala", "lehrkraft__person"), pk=pk)
    if not darf_unterricht_sehen(request.user, u):
        raise PermissionDenied
    return u


def _protokoll(request, u, art):
    from sicherung.models import Protokoll

    Protokoll.schreiben(request.user, "pdf", _("%(art)s: %(fach)s %(gruppe)s, %(abschnitt)s") % {
        "art": art, "fach": u.fach.kuerzel, "gruppe": u.gruppe.name, "abschnitt": u.abschnitt})


# ---------------------------------------------------------------- Excel

@login_required
def excel(request, pk):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    u = _pruefen(request, pk)
    d = datensatz(u)
    wb = Workbook()
    ws = wb.active
    ws.title = _("Notenübersicht")[:31]
    fett, kopf_fl = Font(bold=True), PatternFill("solid", fgColor="E3EFED")
    gefahr_fl = PatternFill("solid", fgColor="F8E1D7")
    duenn = Side(style="thin", color="C9CFD3")
    rahmen = Border(left=duenn, right=duenn, top=duenn, bottom=duenn)
    umbruch = Alignment(wrap_text=True, vertical="top")

    ws["A1"] = f"{u.fach.lokal_name} · {u.gruppe.name}"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = (f"{u.abschnitt.schuljahr} – {u.abschnitt.lokal_name} · {_('Lehrkraft')} {u.lehrkraft.person} · "
                f"{_('Skala')} {u.skala} · {_('Stand')} {formats.date_format(d['stand'], 'SHORT_DATETIME_FORMAT')}")
    ws["A3"] = settings.SCHULNAME + " · " + _("Vertraulich – personenbezogene Daten")

    kopf = [_("Schüler:in")]
    unter = [""]
    for sp in d["spalten"]:
        kopf.append(sp["ln"].titel)
        unter.append(f"{sp['pfad']}\n{formats.date_format(sp['ln'].datum, 'SHORT_DATE_FORMAT')} · {sp['gewicht']} · ≈ {_zahl(sp['anteil'], 1)} %")
    for o in d["ordner"]:
        kopf.append("Ø " + o["o"].name)
        unter.append(o["pfad"])
    if d["jahresnote"]:
        kopf += [_("Ø 2. Halbjahr"), _("1. Halbjahr")]
        unter += ["", f"{_zahl(u.anteil_vorhalbjahr, 0)} %"]
    kopf += [_("Ø Vorschlag"), _("Vorschlag"), _("Zeugnisnote")]
    unter += ["", "", ""]
    start = 5
    for spalte, (k, t) in enumerate(zip(kopf, unter), start=1):
        c = ws.cell(row=start, column=spalte, value=k)
        c.font, c.fill, c.alignment, c.border = fett, kopf_fl, umbruch, rahmen
        c = ws.cell(row=start + 1, column=spalte, value=t)
        c.font, c.fill, c.alignment, c.border = Font(size=8, color="5B6670"), kopf_fl, umbruch, rahmen
    for i, z in enumerate(d["zeilen"]):
        r = start + 2 + i
        v = z["v"]
        werte = [z["name"]] + z["texte"]
        werte += [float(e.schnitt) if e.schnitt is not None else None for e in v.alle_ordner]
        if d["jahresnote"]:
            werte += [float(v.halbjahr_schnitt) if v.halbjahr_schnitt is not None else None,
                      float(v.vorhalbjahr) if v.vorhalbjahr is not None else None]
        werte += [float(v.schnitt) if v.schnitt is not None else None, str(v.stufe) if v.stufe else "", z["zeugnis"]]
        for spalte, w in enumerate(werte, start=1):
            c = ws.cell(row=r, column=spalte, value=w)
            c.border = rahmen
            if isinstance(w, float):
                c.number_format = "0.00"
            if v.gefaehrdet:
                c.fill = gefahr_fl
        if z["abweichung"]:
            c = ws.cell(row=r, column=len(werte))
            c.fill = PatternFill("solid", fgColor="F6C995")
            c.value = f"{z['zeugnis']} ≠ " + (str(v.stufe) if v.stufe else "")
    ws.column_dimensions["A"].width = 26
    for spalte in range(2, len(kopf) + 1):
        ws.column_dimensions[get_column_letter(spalte)].width = 13
    ws.row_dimensions[start + 1].height = 48
    ws.freeze_panes = ws.cell(row=start + 2, column=2)
    letzte = start + 2 + len(d["zeilen"]) + 1
    ws.cell(row=letzte, column=1, value=_("Der Vorschlag ist rechnerisch ermittelt; die Zeugnisnote setzt die Lehrkraft fest. "
                                         "Rot hinterlegt: Gefährdung. Gerundet wird bei Gleichstand zur besseren Note.")).font = Font(size=8, italic=True)
    ws.cell(row=letzte + 1, column=1, value=_("Orange: Die Zeugnisnote weicht vom rechnerischen Vorschlag ab.")).font = Font(size=8, italic=True)

    ws2 = wb.create_sheet(_("Leistungsnachweise")[:31])
    kopf2 = [_("Ordner"), _("Bezeichnung"), _("Datum"), _("Gewicht"), _("Anteil an der Note (%)"), _("Noten"), _("Schnitt")]
    for spalte, k in enumerate(kopf2, start=1):
        c = ws2.cell(row=1, column=spalte, value=k)
        c.font, c.fill, c.border = fett, kopf_fl, rahmen
    for i, sp in enumerate(d["spalten"]):
        werte_ln = [n.stufe.wert for z in d["zeilen"] for n in [z["noten"][i]] if n is not None and n.stufe_id]
        schnitt = sum(werte_ln) / len(werte_ln) if werte_ln else None
        reihe = [sp["pfad"], sp["ln"].titel, sp["ln"].datum, sp["gewicht"], float(sp["anteil"]) if sp["anteil"] is not None else None,
                 len(werte_ln), float(u.skala.runden(schnitt)) if schnitt is not None else None]
        for spalte, w in enumerate(reihe, start=1):
            c = ws2.cell(row=i + 2, column=spalte, value=w)
            c.border = rahmen
            if spalte == 3:
                c.number_format = "DD.MM.YYYY"
            elif isinstance(w, float):
                c.number_format = "0.0" if spalte == 5 else "0.00"
    for spalte, breite in enumerate([30, 30, 12, 10, 18, 8, 10], start=1):
        ws2.column_dimensions[get_column_letter(spalte)].width = breite

    ws3 = wb.create_sheet(_("Bewertungsstruktur")[:31])
    for spalte, k in enumerate([_("Ordner"), _("Gewicht"), _("Anteil an der Note (%)")], start=1):
        c = ws3.cell(row=1, column=spalte, value=k)
        c.font, c.fill, c.border = fett, kopf_fl, rahmen
    for i, o in enumerate(d["ordner"]):
        for spalte, w in enumerate(["\u00a0\u00a0\u00a0" * o["ebene"] + ("└ " if o["ebene"] else "") + o["o"].name, o["gewicht"], float(o["anteil"]) if o["anteil"] is not None else None], start=1):
            c = ws3.cell(row=i + 2, column=spalte, value=w)
            c.border = rahmen
            if isinstance(w, float):
                c.number_format = "0.0"
    ws3.column_dimensions["A"].width = 40
    ws3.column_dimensions["B"].width = 12
    ws3.column_dimensions["C"].width = 22

    puffer = io.BytesIO()
    wb.save(puffer)
    _protokoll(request, u, _("Notenübersicht als Excel"))
    antwort = HttpResponse(puffer.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    antwort["Content-Disposition"] = f'attachment; filename="{_dateiname(u, "xlsx")}"'
    return antwort


# ---------------------------------------------------------------- PDF-Notenbogen

@login_required
def notenbogen(request, pk):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        BaseDocTemplate, Frame, NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
    )

    from sicherung.pdf import schrift

    u = _pruefen(request, pk)
    d = datensatz(u)
    nur = request.GET.get("schueler")
    normal_s, fett_s = schrift()
    gruen, linie, flaeche = colors.HexColor("#1f5f5b"), colors.HexColor("#c9cfd3"), colors.HexColor("#e3efed")
    gefahr = colors.HexColor("#f8e1d7")
    abw = colors.HexColor("#f6c995")
    st = ParagraphStyle("t", fontName=normal_s, fontSize=7.4, leading=9)
    st_k = ParagraphStyle("k", parent=st, fontName=fett_s)
    st_klein = ParagraphStyle("kl", parent=st, fontSize=6.4, leading=7.8, textColor=colors.HexColor("#5b6670"))
    st_h1 = ParagraphStyle("h1", fontName=fett_s, fontSize=14, leading=18, textColor=gruen, spaceAfter=1.5 * mm)
    st_h2 = ParagraphStyle("h2", fontName=fett_s, fontSize=10, leading=13, textColor=gruen, spaceBefore=3 * mm, spaceAfter=1.5 * mm)
    st_u = ParagraphStyle("u", fontName=normal_s, fontSize=8.5, leading=11, textColor=colors.HexColor("#5b6670"))

    def p(text, stil=st):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), stil)

    kopftext = f"{u.fach.lokal_name} · {u.gruppe.name} · {u.abschnitt.schuljahr} – {u.abschnitt.lokal_name}"
    unter = (f"{_('Lehrkraft')} {u.lehrkraft.person} · {_('Skala')} {u.skala} · "
             f"{_('Stand')} {formats.date_format(d['stand'], 'SHORT_DATETIME_FORMAT')}")

    def rahmen(canvas, doc):
        canvas.saveState()
        canvas.setFont(normal_s, 7)
        canvas.setFillColor(colors.HexColor("#5b6670"))
        b, _h = canvas._pagesize
        canvas.drawString(15 * mm, 8 * mm, f"{settings.SCHULNAME} · {_('Vertraulich – personenbezogene Daten')}")
        canvas.drawRightString(b - 15 * mm, 8 * mm, f"{_('Seite')} {doc.page}")
        canvas.restoreState()

    puffer = io.BytesIO()
    doc = BaseDocTemplate(puffer, pagesize=landscape(A4), leftMargin=15 * mm, rightMargin=15 * mm, topMargin=13 * mm, bottomMargin=15 * mm,
                          title=f"{_('Notenbogen')} {u.fach.kuerzel} {u.gruppe.name}", author=settings.SCHULNAME)
    quer = Frame(15 * mm, 15 * mm, landscape(A4)[0] - 30 * mm, landscape(A4)[1] - 28 * mm, id="quer")
    hoch = Frame(15 * mm, 15 * mm, A4[0] - 30 * mm, A4[1] - 28 * mm, id="hoch")
    doc.addPageTemplates([PageTemplate(id="quer", frames=[quer], pagesize=landscape(A4), onPage=rahmen),
                          PageTemplate(id="hoch", frames=[hoch], pagesize=A4, onPage=rahmen)])
    story = []
    zeilen = [z for z in d["zeilen"] if not nur or str(z["s"].pk) == nur]

    # Kursübersicht (quer): Noten je Leistungsnachweis, Vorschlag
    if not nur:
        story += [p(_("Notenübersicht") + " · " + kopftext, st_h1), p(unter, st_u), Spacer(1, 3 * mm)]
        breite = landscape(A4)[0] - 30 * mm
        extra = [_("Ø 2. Hj."), _("1. Hj.")] if d["jahresnote"] else []
        kopf = [p(_("Schüler:in"), st_k)] + [Paragraph(f"<b>{escape(sp['ln'].titel)}</b><br/>{escape(formats.date_format(sp['ln'].datum, 'd.m.'))} · "
                                                      f"{escape(sp['gewicht'])}", st_klein) for sp in d["spalten"]]
        kopf += [p(t, st_k) for t in extra] + [p(_("Vorschlag"), st_k), p(_("Zeugnis"), st_k)]
        daten = [kopf]
        stil = [("GRID", (0, 0), (-1, -1), 0.3, linie), ("BACKGROUND", (0, 0), (-1, 0), flaeche), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 1), (-1, -1), "CENTER")]
        for i, z in enumerate(zeilen, start=1):
            v = z["v"]
            reihe = [p(z["name"])] + [p(t) for t in z["texte"]]
            if d["jahresnote"]:
                reihe += [p(_zahl(v.halbjahr_schnitt)), p(_zahl(v.vorhalbjahr))]
            reihe += [Paragraph(f"<b>{escape(str(v.stufe or '–'))}</b> {escape(_zahl(v.schnitt))}", st), p(z["zeugnis"] or "–")]
            daten.append(reihe)
            if v.gefaehrdet:
                stil.append(("BACKGROUND", (0, i), (-1, i), gefahr))
            if z["abweichung"]:
                stil.append(("BACKGROUND", (-1, i), (-1, i), abw))
        namen_b, ende_b = 42 * mm, (2 if not d["jahresnote"] else 4) * 21 * mm
        rest = max(breite - namen_b - ende_b, 10 * mm)
        n = max(len(d["spalten"]), 1)
        breiten = [namen_b] + [rest / n] * len(d["spalten"]) + [21 * mm] * (len(extra) + 2)
        tab = Table(daten, colWidths=breiten, repeatRows=1)
        tab.setStyle(TableStyle(stil))
        story += [tab, Spacer(1, 2 * mm),
                  p(_("Der Vorschlag ist rechnerisch ermittelt; die Zeugnisnote setzt die Lehrkraft fest. Hinterlegt: Gefährdung. "
                      "Gerundet wird bei Gleichstand zur besseren Note.") + " " + _("Orange: Die Zeugnisnote weicht vom rechnerischen Vorschlag ab."), st_klein)]
        story += [NextPageTemplate("hoch"), PageBreak()]
    else:
        story.append(NextPageTemplate("hoch"))
        doc.pageTemplates.reverse()   # erste Seite hochkant

    # Ein Bogen je Schüler:in (hochkant)
    breite_h = A4[0] - 30 * mm
    for nr, z in enumerate(zeilen):
        v = z["v"]
        story += [p(_("Notenbogen") + " · " + z["name"], st_h1), p(kopftext, st_u), p(unter, st_u), Spacer(1, 2 * mm)]
        daten = [[p(_("Ordner"), st_k), p(_("Leistungsnachweis"), st_k), p(_("Datum"), st_k), p(_("Gewicht"), st_k),
                  p(_("Anteil"), st_k), p(_("Note"), st_k), p(_("Kommentar"), st_k)]]
        for sp, n, t in zip(d["spalten"], z["noten"], z["texte"]):
            daten.append([p(sp["pfad"], st_klein), p(sp["ln"].titel), p(formats.date_format(sp["ln"].datum, "SHORT_DATE_FORMAT")),
                          p(sp["gewicht"]), p(f"{_zahl(sp['anteil'], 1)} %"), Paragraph(f"<b>{escape(t or '–')}</b>", st),
                          p(n.kommentar if n else "", st_klein)])
        if len(daten) == 1:
            daten.append([p(_("Noch keine Leistungsnachweise."))] + [""] * 6)
        tab = Table(daten, colWidths=[32 * mm, 40 * mm, 21 * mm, 17 * mm, 15 * mm, 16 * mm, breite_h - 141 * mm], repeatRows=1)
        tab.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, linie), ("BACKGROUND", (0, 0), (-1, 0), flaeche),
                                 ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story += [tab, p(_("Rechenweg"), st_h2)]
        rech = [[p(_("Ordner"), st_k), p(_("Gewicht"), st_k), p(_("Anteil an der Note"), st_k), p(_("Ø"), st_k)]]
        for o, e in zip(d["ordner"], v.alle_ordner):
            rech.append([p("\u00a0\u00a0\u00a0" * o["ebene"] + ("└ " if o["ebene"] else "") + o["o"].name), p(o["gewicht"]), p(f"{_zahl(o['anteil'], 1)} %"), p(_zahl(e.schnitt) or "–")])
        if d["jahresnote"]:
            rech.append([p(_("Schnitt 2. Halbjahr"), st_k), p(""), p(f"{_zahl(Decimal(100) - (u.anteil_vorhalbjahr or 0), 0)} %"),
                         p(_zahl(v.halbjahr_schnitt) or "–")])
            rech.append([p(_("1. Halbjahr"), st_k), p(""), p(f"{_zahl(u.anteil_vorhalbjahr, 0)} %"), p(_zahl(v.vorhalbjahr) or "–")])
        rech.append([p(_("Jahresvorschlag") if d["jahresnote"] else _("Vorschlag"), st_k), p(""), p(""),
                     Paragraph(f"<b>{escape(str(v.stufe or '–'))}</b> ({escape(_zahl(v.schnitt) or '–')})", st)])
        rech.append([p(_("Festgesetzte Zeugnisnote"), st_k), p(_("weicht vom Vorschlag ab") if z["abweichung"] else "", st_klein), p(""),
                     Paragraph(f"<b>{escape(z['zeugnis'] or '–')}</b>", st)])
        t2 = Table(rech, colWidths=[80 * mm, 25 * mm, 35 * mm, breite_h - 140 * mm])
        stil2 = [("GRID", (0, 0), (-1, -1), 0.3, linie), ("BACKGROUND", (0, 0), (-1, 0), flaeche), ("VALIGN", (0, 0), (-1, -1), "TOP")]
        if v.gefaehrdet:
            stil2.append(("BACKGROUND", (0, len(rech) - 2), (-1, len(rech) - 2), gefahr))
        if z["abweichung"]:
            stil2.append(("BACKGROUND", (0, len(rech) - 1), (-1, len(rech) - 1), abw))
        t2.setStyle(TableStyle(stil2))
        story.append(t2)
        for w in v.warnungen:
            story.append(p("! " + w, st_klein))
        unterschrift = Table([["", "", ""], [p(_("Ort, Datum"), st_klein), "", p(_("Unterschrift Lehrkraft"), st_klein)]],
                             colWidths=[breite_h * 0.42, breite_h * 0.16, breite_h * 0.42], rowHeights=[12 * mm, None])
        unterschrift.setStyle(TableStyle([("LINEBELOW", (0, 0), (0, 0), 0.5, colors.black), ("LINEBELOW", (2, 0), (2, 0), 0.5, colors.black)]))
        story += [Spacer(1, 6 * mm), unterschrift]
        if nr < len(zeilen) - 1:
            story.append(PageBreak())
    doc.build(story)
    _protokoll(request, u, _("Notenbogen als PDF"))
    antwort = HttpResponse(puffer.getvalue(), content_type="application/pdf")
    antwort["Content-Disposition"] = f'attachment; filename="{_dateiname(u, "pdf")}"'
    return antwort

