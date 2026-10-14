"""
PDF-Export der Daten einzelner Module für einen Zeitraum.

- Einträge mit Datum (Fehlzeiten, Noten, Nachrichten …) werden nach dem Zeitraum gefiltert.
- Einträge ohne Datum (Personen, Klassen, Kataloge …) erscheinen auf Wunsch als „Bestand“ (aktueller Stand).
- Lange Zeiträume werden nach Monaten bzw. Halbjahren aufgeteilt; jede Datei enthält höchstens
  PDF_EINTRAEGE_JE_DATEI Einträge, darüber entstehen weitere Teile.
"""
import json
import logging
import re
import threading
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

from django.conf import settings
from django.db import close_old_connections, models
from django.utils import formats, timezone, translation
from django.utils.translation import gettext as _

from .models import Exportauftrag, Protokoll
from .module import NAMEN, ist_protokollmodell, modellname, modelle

log = logging.getLogger(__name__)

# Felder, die nie in ein PDF gehören
GEHEIM = {"password", "schluessel"}

# Datumsbezug je Modell (Pfad zu einem Datumsfeld); sonst automatisch über KANDIDATEN, sonst „Bestand“
DATUMSFELDER = {
    "noten.leistungsnachweis": "datum",
    "noten.note": "leistungsnachweis__datum",
    "noten.zeugnisnote": "unterricht__abschnitt__ende",
    "noten.unterricht": "abschnitt__ende",
    "zeugnisse.zeugnis": "abschnitt__ende",
    "zeugnisse.zeugnisfachnote": "zeugnis__abschnitt__ende",
    "zeugnisse.anmerkung": "erstellt",
    "termine.termin": "beginn",
    "termine.gespraechstermin": "beginn",
    "termine.teilnahme": "sprechtag__erstellt_am",
    "zeugnisse.beschluss": "konferenz__abschnitt__ende",
    "zeugnisse.konferenz": "abschnitt__ende",
    "elternkontakt.empfaenger": "gespraech__erstellt_am",
    "elternkontakt.beitrag": "erstellt_am",
    "foerderung.foerdereintrag": "datum",
    "aufnahme.anmeldekontakt": "anmeldung__eingang",
    "aufnahme.anmeldedatei": "anmeldung__eingang",
    "aufnahme.anmeldepunkt": "anmeldung__eingang",
}
KANDIDATEN = ["datum", "datum_von", "eingang", "erfasst_am", "erstellt_am", "hochgeladen_am", "ausgeloest_am", "am",
              "zeit", "beantragt_am", "ausgehaendigt_am"]


# ---------------------------------------------------------------- Datumsbezug

def _feld_am_ende(model, pfad):
    feld = None
    for teil in pfad.split("__"):
        feld = model._meta.get_field(teil)
        if feld.is_relation:
            model = feld.related_model
    return feld


def datumspfad(model):
    from django.core.exceptions import FieldDoesNotExist

    label = model._meta.label_lower
    if label in DATUMSFELDER:
        try:
            if isinstance(_feld_am_ende(model, DATUMSFELDER[label]), (models.DateField, models.DateTimeField)):
                return DATUMSFELDER[label]
        except FieldDoesNotExist:
            pass
    if ist_protokollmodell(model):
        return "history_date"
    namen = {f.name: f for f in model._meta.concrete_fields}
    for k in KANDIDATEN:
        f = namen.get(k)
        if isinstance(f, (models.DateField, models.DateTimeField)):
            return k
    return None


def zeitraum_filter(model, von, bis):
    pfad = datumspfad(model)
    if pfad is None:
        return None
    feld = _feld_am_ende(model, pfad)
    zusatz = "__date" if isinstance(feld, models.DateTimeField) else ""
    filt = {}
    if von:
        filt[f"{pfad}{zusatz}__gte"] = von
    if bis:
        filt[f"{pfad}{zusatz}__lte"] = bis
    return filt


def _monatsende(tag):
    naechster = (tag.replace(day=28) + timedelta(days=4)).replace(day=1)
    return naechster - timedelta(days=1)


def zeitfenster(auftrag, anzahl_gesamt):
    """Liste (Titel, von, bis) der Zeitabschnitte, auf die die datierten Einträge verteilt werden."""
    von, bis = auftrag.von, auftrag.bis
    ganz = (von, bis)
    titel_ganz = zeitraum_text(von, bis)
    art = auftrag.aufteilung
    if not (von and bis) or art == "keine":
        return [(titel_ganz, *ganz)]
    if art == "auto":
        if (bis - von).days <= 92 or anzahl_gesamt <= settings.PDF_EINTRAEGE_JE_DATEI:
            return [(titel_ganz, *ganz)]
        art = "monat"
    if art == "halbjahr":
        from stammdaten.models import Abschnitt

        fenster = []
        for a in Abschnitt.objects.filter(beginn__lte=bis, ende__gte=von).select_related("schuljahr").order_by("beginn"):
            fenster.append((f"{a.lokal_name} {a.schuljahr}", max(von, a.beginn), min(bis, a.ende)))
        return fenster or [(titel_ganz, *ganz)]
    fenster, tag = [], von.replace(day=1)
    while tag <= bis:
        ende = _monatsende(tag)
        fenster.append((formats.date_format(tag, "YEAR_MONTH_FORMAT"), max(von, tag), min(bis, ende)))
        tag = ende + timedelta(days=1)
    return fenster


def zeitraum_text(von, bis):
    if von and bis:
        return f"{formats.date_format(von, 'SHORT_DATE_FORMAT')} – {formats.date_format(bis, 'SHORT_DATE_FORMAT')}"
    if von:
        return _("ab %(d)s") % {"d": formats.date_format(von, "SHORT_DATE_FORMAT")}
    if bis:
        return _("bis %(d)s") % {"d": formats.date_format(bis, "SHORT_DATE_FORMAT")}
    return _("gesamter Zeitraum")


# ---------------------------------------------------------------- Werte darstellen

def _wert(obj, feld):
    if feld.choices and not feld.is_relation:
        w = getattr(obj, f"get_{feld.name}_display")()
    else:
        w = getattr(obj, feld.name, None) if not isinstance(feld, models.ForeignKey) else getattr(obj, feld.name)
    if w is None or w == "":
        return "–"
    if isinstance(w, bool):
        return _("ja") if w else _("nein")
    if isinstance(w, datetime):
        return formats.date_format(timezone.localtime(w) if timezone.is_aware(w) else w, "SHORT_DATETIME_FORMAT")
    if isinstance(w, date):
        return formats.date_format(w, "SHORT_DATE_FORMAT")
    if isinstance(w, Decimal):
        return formats.number_format(w)
    if isinstance(feld, models.FileField):
        return w.name or "–"
    if isinstance(w, (dict, list)):
        text = json.dumps(w, ensure_ascii=False)
        return text if len(text) <= 600 else text[:600] + " …"
    return str(w)


def _felder(model):
    return [f for f in model._meta.concrete_fields
            if f.name not in GEHEIM and not (f.primary_key and f.name == "id")]


# ---------------------------------------------------------------- PDF schreiben

_SCHRIFT = None


def schrift():
    """DejaVu Sans (Unicode, z. B. für Namen mit Sonderzeichen), sonst Helvetica."""
    global _SCHRIFT
    if _SCHRIFT:
        return _SCHRIFT
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    kandidaten = [getattr(settings, "PDF_SCHRIFT_ORDNER", ""), "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu",
                  "/usr/share/fonts/TTF"]
    for ordner in kandidaten:
        if ordner and Path(ordner, "DejaVuSans.ttf").exists() and Path(ordner, "DejaVuSans-Bold.ttf").exists():
            pdfmetrics.registerFont(TTFont("SV", str(Path(ordner, "DejaVuSans.ttf"))))
            pdfmetrics.registerFont(TTFont("SV-Fett", str(Path(ordner, "DejaVuSans-Bold.ttf"))))
            from reportlab.pdfbase.pdfmetrics import registerFontFamily

            registerFontFamily("SV", normal="SV", bold="SV-Fett", italic="SV", boldItalic="SV-Fett")
            _SCHRIFT = ("SV", "SV-Fett")
            return _SCHRIFT
    _SCHRIFT = ("Helvetica", "Helvetica-Bold")
    return _SCHRIFT


def pdf_schreiben(pfad, titel, untertitel, abschnitte, kopfzeile, fusszeile):
    """
    abschnitte: Liste von {"titel", "model", "objekte"} oder {"titel", "protokoll": [(zeit, wer, art, text)]}.
    Gibt die Seitenzahl zurück.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    normal_s, fett_s = schrift()
    st_text = ParagraphStyle("t", fontName=normal_s, fontSize=7.6, leading=9.4)
    st_kopf = ParagraphStyle("k", parent=st_text, fontName=fett_s)
    st_h1 = ParagraphStyle("h1", fontName=fett_s, fontSize=15, leading=19, textColor=colors.HexColor("#1f5f5b"), spaceAfter=2 * mm)
    st_h2 = ParagraphStyle("h2", fontName=fett_s, fontSize=10.5, leading=13, textColor=colors.HexColor("#1f5f5b"),
                           spaceBefore=4 * mm, spaceAfter=1.5 * mm)
    st_unter = ParagraphStyle("u", fontName=normal_s, fontSize=8.5, leading=11, textColor=colors.HexColor("#5b6670"))
    linie = colors.HexColor("#c9cfd3")
    flaeche = colors.HexColor("#e3efed")
    breite = A4[0] - 30 * mm

    def p(text, stil=st_text):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), stil)

    story = [p(titel, st_h1), p(untertitel, st_unter), Spacer(1, 3 * mm)]
    if not abschnitte:
        story.append(p(_("Keine Einträge in diesem Zeitraum.")))
    for a in abschnitte:
        if "protokoll" in a:
            story.append(p(a["titel"], st_h2))
            daten = [[p(_("Zeitpunkt"), st_kopf), p(_("Benutzer:in"), st_kopf), p(_("Art"), st_kopf), p(_("Eintrag"), st_kopf)]]
            daten += [[p(z), p(w), p(art), p(t)] for z, w, art, t in a["protokoll"]]
            tab = Table(daten, colWidths=[30 * mm, 30 * mm, 20 * mm, breite - 80 * mm], repeatRows=1)
            tab.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, linie), ("BACKGROUND", (0, 0), (-1, 0), flaeche),
                                     ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story.append(tab)
            continue
        model, objekte = a["model"], a["objekte"]
        felder = _felder(model)
        story.append(p(a["titel"], st_h2))
        if len(felder) <= 6:
            daten = [[p(f.verbose_name, st_kopf) for f in felder]]
            daten += [[p(_wert(o, f)) for f in felder] for o in objekte]
            tab = Table(daten, colWidths=[breite / len(felder)] * len(felder), repeatRows=1)
            tab.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.3, linie), ("BACKGROUND", (0, 0), (-1, 0), flaeche),
                                     ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story.append(tab)
        else:
            # Datenblatt je Eintrag: zwei Feldpaare je Zeile, leere Felder werden ausgelassen
            story.append(p(_("Leere Felder sind ausgelassen."), st_unter))
            for o in objekte:
                paare = [(f.verbose_name, w) for f in felder for w in [_wert(o, f)] if w != "–"]
                zeilen = [[p(str(o), st_kopf), "", "", ""]]
                for i in range(0, len(paare), 2):
                    links, rechts = paare[i], paare[i + 1] if i + 1 < len(paare) else ("", "")
                    zeilen.append([p(links[0], st_unter), p(links[1]), p(rechts[0], st_unter), p(rechts[1])])
                spalte = breite / 2
                tab = Table(zeilen, colWidths=[30 * mm, spalte - 30 * mm, 30 * mm, spalte - 30 * mm])
                tab.setStyle(TableStyle([("SPAN", (0, 0), (3, 0)), ("BACKGROUND", (0, 0), (3, 0), flaeche),
                                         ("BOX", (0, 0), (-1, -1), 0.3, linie), ("LINEBELOW", (0, 0), (-1, -2), 0.2, linie),
                                         ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                                         ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
                story += [KeepTogether([tab]) if len(zeilen) < 30 else tab, Spacer(1, 1.6 * mm)]

    def rahmen(canvas, doc):
        canvas.saveState()
        canvas.setFont(normal_s, 7)
        canvas.setFillColor(colors.HexColor("#5b6670"))
        canvas.drawString(15 * mm, A4[1] - 10 * mm, kopfzeile)
        canvas.drawString(15 * mm, 9 * mm, fusszeile)
        canvas.drawRightString(A4[0] - 15 * mm, 9 * mm, _("Seite %(n)d") % {"n": doc.page})
        canvas.restoreState()

    doc = SimpleDocTemplate(str(pfad), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=15 * mm,
                            title=titel, author=settings.SCHULNAME, subject=untertitel)
    doc.build(story, onFirstPage=rahmen, onLaterPages=rahmen)
    return doc.page


# ---------------------------------------------------------------- Auftrag ausführen

def _abfrage(model):
    qs = model._default_manager.all()
    fk = [f.name for f in model._meta.concrete_fields if isinstance(f, models.ForeignKey) and not f.name.startswith("history_")]
    if fk:
        qs = qs.select_related(*fk)
    pfad = datumspfad(model)
    return qs.order_by(pfad, "pk") if pfad else qs.order_by("pk")


def _protokoll_eintraege(model, filt):
    arten = {"+": _("angelegt"), "~": _("geändert"), "-": _("gelöscht")}
    zeilen = []
    for h in model._default_manager.filter(**filt).select_related("history_user").order_by("history_date"):
        try:
            text = str(h.instance)
        except Exception:  # Bezug gelöscht o. Ä.
            text = f"#{h.pk}"
        zeilen.append((formats.date_format(timezone.localtime(h.history_date), "SHORT_DATETIME_FORMAT"),
                       getattr(h.history_user, "username", "") or "–", arten.get(h.history_type, h.history_type), text))
    return zeilen


def _stuecke(abschnitte, grenze):
    """Teilt Abschnitte so auf, dass jede Datei höchstens `grenze` Einträge enthält."""
    teile, aktuell, n = [], [], 0
    for a in abschnitte:
        liste = a.get("objekte", a.get("protokoll"))
        schluessel = "objekte" if "objekte" in a else "protokoll"
        start = 0
        while start < len(liste):
            platz = grenze - n
            if platz <= 0:
                teile.append(aktuell)
                aktuell, n, platz = [], 0, grenze
            stueck = liste[start:start + platz]
            aktuell.append({**a, schluessel: stueck})
            n += len(stueck)
            start += len(stueck)
    if aktuell or not teile:
        teile.append(aktuell)
    return teile


def _dateiname(*teile):
    text = "-".join(t for t in teile if t)
    text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-")[:120] + ".pdf"


def export_ausfuehren(auftrag_pk):
    auftrag = Exportauftrag.objects.get(pk=auftrag_pk)
    auftrag.status = Exportauftrag.LAEUFT
    auftrag.save(update_fields=["status"])
    try:
        with translation.override(auftrag.sprache):
            dateien = _export(auftrag)
        auftrag.dateien = dateien
        auftrag.status = Exportauftrag.FERTIG
        auftrag.fertig_am = timezone.now()
        auftrag.save(update_fields=["dateien", "status", "fertig_am"])
        Protokoll.schreiben(auftrag.erstellt_von, "pdf", _("%(n)d PDF-Dateien: %(module)s, %(zeitraum)s") % {
            "n": len(dateien), "module": ", ".join(str(NAMEN[m]) for m in auftrag.module),
            "zeitraum": zeitraum_text(auftrag.von, auftrag.bis)})
    except Exception as fehler:
        log.exception("PDF-Export %s fehlgeschlagen", auftrag_pk)
        auftrag.status = Exportauftrag.FEHLER
        auftrag.fehler = str(fehler)[:2000]
        auftrag.save(update_fields=["status", "fehler"])


def _export(auftrag):
    ordner = auftrag.ordner
    ordner.mkdir(parents=True, exist_ok=True)
    grenze = max(50, settings.PDF_EINTRAEGE_JE_DATEI)
    erstellt = formats.date_format(timezone.localtime(), "SHORT_DATETIME_FORMAT")
    wer = getattr(auftrag.erstellt_von, "username", "")
    fuss = _("Vertraulich – erstellt am %(zeit)s von %(wer)s") % {"zeit": erstellt, "wer": wer or "–"}
    dateien = []
    nr = 0
    for key in auftrag.module:
        alle = [m for m in modelle(key) if not ist_protokollmodell(m)]
        protokolle = ([m for m in modelle(key) if any(f.name == "history_date" for f in m._meta.fields)]
                      if auftrag.mit_protokoll else [])
        datiert = [m for m in alle if datumspfad(m)]
        bestand = [m for m in alle if not datumspfad(m)] if auftrag.mit_bestand else []
        gesamt = sum(_abfrage(m).filter(**zeitraum_filter(m, auftrag.von, auftrag.bis)).count() for m in datiert)
        fenster = zeitfenster(auftrag, gesamt) if (datiert or protokolle) else []
        modulname = str(NAMEN[key])
        for titel_fenster, von, bis in fenster:
            abschnitte = []
            for m in datiert:
                objekte = list(_abfrage(m).filter(**zeitraum_filter(m, von, bis)))
                if objekte:
                    abschnitte.append({"titel": f"{modellname(m)} ({len(objekte)})", "model": m, "objekte": objekte})
            for m in protokolle:
                eintraege = _protokoll_eintraege(m, zeitraum_filter(m, von, bis))
                if eintraege:
                    abschnitte.append({"titel": f"{modellname(m)} ({len(eintraege)})", "protokoll": eintraege})
            if not abschnitte and len(fenster) > 1:
                continue
            teile = _stuecke(abschnitte, grenze)
            for i, teil in enumerate(teile, 1):
                nr += 1
                teiltext = _("Teil %(i)d von %(n)d") % {"i": i, "n": len(teile)} if len(teile) > 1 else ""
                name = _dateiname(f"{nr:02d}", key, titel_fenster, f"teil{i}" if len(teile) > 1 else "")
                eintraege = sum(len(a.get("objekte", a.get("protokoll", []))) for a in teil)
                untertitel = " · ".join(x for x in [_("Zeitraum: %(z)s") % {"z": titel_fenster}, teiltext,
                                                    _("%(n)d Einträge") % {"n": eintraege}] if x)
                seiten = pdf_schreiben(ordner / name, f"{modulname}", untertitel, teil,
                                       f"{settings.SCHULNAME} · {modulname} · {titel_fenster}", fuss)
                dateien.append({"name": name, "modul": key, "titel": f"{modulname} – {titel_fenster}" + (f" ({teiltext})" if teiltext else ""),
                                "eintraege": eintraege, "seiten": seiten, "groesse": (ordner / name).stat().st_size})
        if bestand:
            abschnitte = []
            for m in bestand:
                objekte = list(_abfrage(m))
                if objekte:
                    abschnitte.append({"titel": f"{modellname(m)} ({len(objekte)})", "model": m, "objekte": objekte})
            teile = _stuecke(abschnitte, grenze)
            for i, teil in enumerate(teile if abschnitte else [], 1):
                nr += 1
                teiltext = _("Teil %(i)d von %(n)d") % {"i": i, "n": len(teile)} if len(teile) > 1 else ""
                name = _dateiname(f"{nr:02d}", key, "bestand", f"teil{i}" if len(teile) > 1 else "")
                eintraege = sum(len(a["objekte"]) for a in teil)
                stand = formats.date_format(timezone.localdate(), "SHORT_DATE_FORMAT")
                untertitel = " · ".join(x for x in [_("Bestand (Stand %(d)s)") % {"d": stand}, teiltext,
                                                    _("%(n)d Einträge") % {"n": eintraege}] if x)
                seiten = pdf_schreiben(ordner / name, modulname, untertitel, teil,
                                       f"{settings.SCHULNAME} · {modulname} · {_('Bestand')}", fuss)
                dateien.append({"name": name, "modul": key, "titel": f"{modulname} – {_('Bestand')}" + (f" ({teiltext})" if teiltext else ""),
                                "eintraege": eintraege, "seiten": seiten, "groesse": (ordner / name).stat().st_size})
    return dateien


def export_starten(auftrag):
    if settings.SICHERUNG_HINTERGRUND:
        def lauf():
            try:
                export_ausfuehren(auftrag.pk)
            finally:
                close_old_connections()

        threading.Thread(target=lauf, daemon=True, name=f"pdf-export-{auftrag.pk}").start()
    else:
        export_ausfuehren(auftrag.pk)
