"""
Zeugnisnoten gesammelt setzen (ab 0.4.13.0) – für den Excel-Import und die Klassenübersicht.

Die Regeln sind die der Zeugnisnoten-Seite: Die Lehrkraft des Unterrichts (und die Schulleitung) setzt die Note fest,
gesperrte Schüler:innen und freigegebene Zeugnisse bleiben unverändert, ohne Einzelnoten braucht es die Freigabe
„Zeugnisnote ohne Einzelnoten“. Eine Abweichung vom Vorschlag wird nur markiert (`weicht_ab`), nicht verhindert.
Gespeichert wird nur, was sich ändert; `quelle` hält fest, woher die Note stammt.

Ab 0.4.15.0 gilt ohne festgesetzte Note automatisch die gerundete Note aus den Einzelnoten (`automatisch`).
"""
from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

from .berechnung import Baum, Vorhalbjahr, vorschlagsnote
from .models import Note, Zeugnisnote, Zeugnisnotenfreigabe
from .sperre import gesperrte_schueler

VERMERKE = {"nb": "nb", "n.b.": "nb", "n.b": "nb", "befreit": "befreit", "b": "befreit"}


def ganze_stufen(skala):
    """{ganze Note: Notenstufe} der Skala (Sek I: 1–6)."""
    return {int(s.wert): s for s in skala.stufen.all() if s.wert == s.wert.to_integral_value()}


def lesen(text, stufen):
    """Excel-/Formulareingabe → ("stufe", Notenstufe) | ("vermerk", "nb"|"befreit") | None (leer) | ValueError."""
    t = str(text if text is not None else "").strip().casefold().replace(",", ".")
    if not t:
        return None
    if t in VERMERKE:
        return "vermerk", VERMERKE[t]
    try:
        zahl = float(t)
    except ValueError:
        raise ValueError(_("„%(text)s“ ist keine Zeugnisnote (ganze Note 1 bis 6, nb oder befreit).") % {"text": text})
    if zahl != int(zahl) or int(zahl) not in stufen:
        raise ValueError(_("„%(text)s“ ist keine Zeugnisnote (ganze Note 1 bis 6, nb oder befreit).") % {"text": text})
    return "stufe", stufen[int(zahl)]


def gesperrt(u, schueler_ids):
    """Schüler-IDs, deren Zeugnisnote nicht mehr geändert werden darf (Notensperre oder freigegebenes Zeugnis)."""
    from zeugnisse.models import Zeugnis

    ids = list(schueler_ids)
    if not ids:
        return set()
    frei = set(Zeugnis.objects.filter(abschnitt=u.abschnitt, schueler__in=ids, status=Zeugnis.FREIGEGEBEN)
               .values_list("schueler_id", flat=True))
    return frei | gesperrte_schueler(u, ids)


def freigegebene(u, schueler_ids):
    """Schüler-IDs mit freigegebenem Zeugnis im Halbjahr des Unterrichts (ein Grund für `gesperrt`)."""
    from zeugnisse.models import Zeugnis

    return set(Zeugnis.objects.filter(abschnitt=u.abschnitt, schueler__in=list(schueler_ids), status=Zeugnis.FREIGEGEBEN)
               .values_list("schueler_id", flat=True))


def aktuell(u, schueler_ids=None):
    """{Schüler-ID: Zeugnisnote} des Unterrichts."""
    qs = Zeugnisnote.objects.filter(unterricht=u).select_related("stufe")
    if schueler_ids is not None:
        qs = qs.filter(schueler__in=list(schueler_ids))
    return {z.schueler_id: z for z in qs}


def anzeige(z):
    """Kurztext der Zeugnisnote für Tabellen und Vorschau."""
    if z is None:
        return ""
    return z.vermerk or (z.stufe.bezeichnung if z.stufe_id else "")


def formwert(z):
    """Wert der Auswahl in der Klassenübersicht: ganze Note als Zahl, Vermerk als Text, sonst die Bezeichnung der Stufe."""
    if z is None:
        return ""
    if z.vermerk:
        return z.vermerk
    if not z.stufe_id:
        return ""
    w = z.stufe.wert
    return str(int(w)) if w == w.to_integral_value() else z.stufe.bezeichnung


def pruefen(u, wuensche, mit_noten=()):
    """
    wuensche: {Schüler:in (Schuelerprofil): ("stufe", Notenstufe) | ("vermerk", str)} – leere Wünsche vorher entfernen.
    `mit_noten`: Schüler-IDs, die in demselben Vorgang noch Einzelnoten bekommen (zählen als „hat Einzelnoten“).
    Gibt eine Liste von Dicts zurück (ohne zu speichern): {s, art, wert, status, text, z}.
    status: neu | geaendert | gleich | gesperrt | fehler
    """
    bestehend = aktuell(u, [s.pk for s in wuensche])
    sperre = gesperrt(u, [s.pk for s in wuensche])
    nur_zeugnisnote = Zeugnisnotenfreigabe.fuer(u) is not None
    baum = Baum(u)
    jahr = Vorhalbjahr(u) if u.mit_jahresnote else False
    ergebnis = []
    for s, (art, wert) in wuensche.items():
        z = bestehend.get(s.pk)
        schnitt = vorschlagsnote(u, s, None, baum, jahr=jahr).schnitt     # ohne Einzelnoten gibt es keinen Vorschlag
        zeile = {"s": s, "art": art, "wert": wert, "z": z, "status": "neu", "text": "", "vorschlag": schnitt,
                 "alt": anzeige(z), "neu": wert if art == "vermerk" else wert.bezeichnung}
        if s.pk in sperre:
            zeile.update(status="gesperrt", text=_("gesperrt – nicht geändert"))
        elif art == "stufe" and wert.skala_id != u.skala_id:
            zeile.update(status="fehler", text=_("Die Note gehört nicht zur Notenskala des Unterrichts."))
        elif art == "stufe" and schnitt is None and s.pk not in mit_noten and not nur_zeugnisnote:
            zeile.update(status="fehler", text=_("Keine Einzelnoten vorhanden. Eine Zeugnisnote ohne Einzelnoten ist für dieses Fach "
                                                 "und diesen Jahrgang nicht freigegeben (Schulleitung › Notenregeln)."))
        elif z is not None and ((art == "vermerk" and z.vermerk == wert) or (art == "stufe" and not z.vermerk and z.stufe_id == wert.pk)):
            zeile["status"] = "gleich"
        elif z is not None:
            zeile["status"] = "geaendert"
        ergebnis.append(zeile)
    return ergebnis


def speichern(u, zeilen, quelle, begruendungen=None):
    """Speichert die Zeilen aus `pruefen` mit Status neu/geaendert. Gibt die Anzahl gespeicherter Noten zurück."""
    begruendungen = begruendungen or {}
    gespeichert = 0
    for zeile in zeilen:
        if zeile["status"] not in ("neu", "geaendert"):
            continue
        s = zeile["s"]
        z = zeile["z"] or Zeugnisnote(unterricht=u, schueler=s)
        z.vorschlag = zeile["vorschlag"]
        if zeile["art"] == "vermerk":
            z.vermerk, z.stufe = zeile["wert"], None
        else:
            z.vermerk, z.stufe = "", zeile["wert"]
        if s.pk in begruendungen:
            z.begruendung = begruendungen[s.pk]
        z.quelle = quelle
        try:
            z.full_clean()
        except ValidationError as e:
            zeile.update(status="fehler", text=" ".join(e.messages))
            continue
        z.save()
        gespeichert += 1
    return gespeichert


AUTO = "auto"


def automatisch(u):
    """
    Zeugnisnote = gerundeter Vorschlag aus den Einzelnoten, solange niemand sie selbst festgesetzt hat (ab 0.4.15.0).
    Ohne eigene Einzelnoten in diesem Unterricht gibt es keine automatische Note (eine vorhandene wird entfernt).
    Festgesetzte Noten (Excel, Klassenübersicht, Zeugnisnoten-Seite), gesperrte Schüler:innen und freigegebene
    Zeugnisse bleiben unverändert. Gibt die Zahl der geänderten Zeugnisnoten zurück.
    """
    schueler = list(u.schueler())
    ids = [s.pk for s in schueler]
    if not ids:
        return 0
    bestehend = aktuell(u, ids)
    sperre = gesperrt(u, ids)
    stufen = ganze_stufen(u.skala)
    baum = Baum(u)
    jahr = Vorhalbjahr(u) if u.mit_jahresnote else False
    noten_je = defaultdict(list)
    for n in Note.objects.filter(leistungsnachweis__unterricht=u, schueler__in=ids).select_related("stufe"):
        noten_je[n.schueler_id].append(n)
    geaendert = 0
    for s in schueler:
        z = bestehend.get(s.pk)
        if s.pk in sperre or (z is not None and z.quelle != AUTO):
            continue
        noten = noten_je.get(s.pk, [])
        stufe = schnitt = None
        if any(n.stufe_id or n.sonderstatus == "unentschuldigt" for n in noten):
            schnitt = vorschlagsnote(u, s, noten, baum, jahr=jahr).schnitt
            ganz = u.skala.ganz_runden(schnitt)
            stufe = stufen.get(int(ganz)) if ganz is not None else None
        if stufe is None:
            if z is not None:
                z.delete()
                geaendert += 1
            continue
        schnitt = Decimal(schnitt).quantize(Decimal("0.01"))
        if z is not None and z.stufe_id == stufe.pk and not z.vermerk and z.vorschlag == schnitt:
            continue
        z = z or Zeugnisnote(unterricht=u, schueler=s)
        z.stufe, z.vermerk, z.vorschlag, z.quelle = stufe, "", schnitt, AUTO
        z.save()
        geaendert += 1
    return geaendert
