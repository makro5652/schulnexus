"""
Notenliste einer Klasse (ab 0.4.15.0): Schuljahr, Halbjahr und Klasse wählen – auch vergangene und gesperrte –
und alle Zeugnisnoten sehen wie in der Konferenz (Kernfächer, 5/6 markiert, Schnitt, Gefährdung bzw. Versetzung).
Nur lesend: Es werden keine Zeugnisse angelegt.
"""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from stammdaten.models import Abschnitt, Gruppe, Schuljahr

from . import rechte
from .ansichten import art_fuer, schnitt
from .models import Konferenz, Zeugnis
from .noten import WORTE, fach_sortierung, fachnoten, kernfach_ids, klassen_mitglieder, laufbahn, versetzungsvorschlag


def zeilen_fuer(klasse, abschnitt):
    """(zeilen, spalten) wie in der Konferenz, ohne Beschlüsse."""
    art = art_fuer(abschnitt)
    mitglieder = klassen_mitglieder(klasse, abschnitt)
    zeugnisse = {z.schueler_id: z for z in Zeugnis.objects.filter(abschnitt=abschnitt, schueler__in=mitglieder)
                 .select_related("bildungsgang")}
    zeilen, faecher = [], {}
    for s in mitglieder:
        z = zeugnisse.get(s.pk)
        if z is not None and z.freigegeben:
            bg, jg = z.bildungsgang, z.jahrgang
        else:
            bg, jg = laufbahn(s, abschnitt)
            jg = jg or klasse.jahrgang
        fn = fachnoten(s, abschnitt, art)
        ergebnis, hinweis = versetzungsvorschlag(s, bg, jg, fn)
        kern = kernfach_ids(s, bg, fn) or set()
        for e in fn:
            faecher[e["fach"].pk] = e["fach"]
        zeilen.append({"s": s, "z": z, "bg": bg, "jg": jg, "fn": {e["fach"].pk: e for e in fn}, "kern": kern,
                       "ergebnis": ergebnis, "hinweis": hinweis, "schnitt": schnitt(fn),
                       "fehlen": sum(1 for e in fn if e["fehlt"]),
                       "defizite": ", ".join(f"{name} ({WORTE[note]})" for name, note in (ergebnis.defizite if ergebnis else []))})
    spalten = sorted(faecher.values(), key=fach_sortierung)
    for zl in zeilen:
        zl["zellen"] = [{"e": zl["fn"].get(f.pk), "kern": f.pk in zl["kern"]} for f in spalten]
    return zeilen, spalten


def _klassen(user, sj):
    qs = Gruppe.objects.filter(schuljahr=sj, typ=Gruppe.STAMMKLASSE).select_related("leitung__person").order_by("jahrgang", "name")
    return [k for k in qs if rechte.darf_klasse_sehen(user, k)]


@login_required
def notenliste(request):
    if not request.user.has_perm("zeugnisse.view_zeugnis"):
        raise PermissionDenied
    schuljahre = list(Schuljahr.objects.order_by("-beginn"))
    sj = next((s for s in schuljahre if str(s.pk) == request.GET.get("sj")), None) or Schuljahr.aktuelles() or (schuljahre[0] if schuljahre else None)
    abschnitte = list(Abschnitt.objects.filter(schuljahr=sj).order_by("nummer")) if sj else []
    abschnitt = next((a for a in abschnitte if str(a.pk) == request.GET.get("abschnitt")), None)
    if abschnitt is None and abschnitte:
        laufend = [a for a in abschnitte if a.beginn <= sj.stichtag() <= a.ende]
        abschnitt = laufend[0] if laufend else abschnitte[-1]
    klassen = _klassen(request.user, sj) if sj else []
    klasse = next((k for k in klassen if str(k.pk) == request.GET.get("klasse")), None)
    zeilen, spalten, konferenz = [], [], None
    if klasse and abschnitt:
        zeilen, spalten = zeilen_fuer(klasse, abschnitt)
        konferenz = Konferenz.objects.filter(klasse=klasse, abschnitt=abschnitt).order_by("-pk").first()
    return render(request, "zeugnisse/notenliste.html", {
        "schuljahre": schuljahre, "sj": sj, "abschnitte": abschnitte, "abschnitt": abschnitt, "klassen": klassen,
        "klasse": klasse, "zeilen": zeilen, "spalten": spalten, "konferenz": konferenz,
        "halbjahr": abschnitt is not None and art_fuer(abschnitt) == Zeugnis.HALBJAHR,
        "gefaehrdet": sum(1 for zl in zeilen if zl["ergebnis"] and zl["ergebnis"].gefaehrdet),
        "fehlen": sum(zl["fehlen"] for zl in zeilen),
    })
