"""
Bewertungsstruktur kopieren (ab 0.4.16.0): von einem anderen Kurs übernehmen oder auf mehrere Kurse übertragen –
etwa auf die Parallelklassen oder alle Fächer eines Jahrgangs.

Ziel darf noch keine Leistungsnachweise haben und nicht gesperrt sein. Die bisherigen (nicht vorgegebenen) Ordner des
Ziels werden ersetzt; von der Schulleitung vorgegebene Ordner (Klausurregel) bleiben und erhalten die Unterordner der
gleichartigen Vorgabe der Quelle. Leistungsnachweise (ohne Noten) werden nur innerhalb desselben Halbjahres mitkopiert.
"""
from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext

from .berechnung import Baum
from .models import Bewertungsordner, Leistungsnachweis, Unterricht
from .sperre import gesperrte_schueler


def hindernis(ziel):
    """Warum die Struktur nicht in `ziel` kopiert werden kann – oder None."""
    if ziel.leistungsnachweise.exists():
        return gettext("enthält schon Leistungsnachweise")
    if gesperrte_schueler(ziel):
        return gettext("Noten gesperrt")
    return None


@transaction.atomic
def kopieren(quelle, ziel, mit_nachweisen=False):
    """Gibt (Anzahl Ordner, Anzahl Leistungsnachweise, übersprungene Ordnernamen) zurück."""
    grund = hindernis(ziel)
    if grund:
        raise ValueError(grund)
    Bewertungsordner.objects.filter(unterricht=ziel, vorgegeben="").delete()
    vorgabe = {o.vorgegeben: o for o in Bewertungsordner.objects.filter(unterricht=ziel, eltern=None).exclude(vorgegeben="")}
    zuordnung, uebersprungen, n_ordner = {}, [], 0
    for o, _ebene, _pfad in Baum(quelle).in_reihenfolge():
        if o.eltern_id is None:
            if o.vorgegeben and o.vorgegeben in vorgabe:
                zuordnung[o.pk] = vorgabe[o.vorgegeben]
                continue
            if vorgabe:             # oberste Ebene des Ziels ist durch die Klausurregel vorgegeben
                uebersprungen.append(o.name)
                continue
            eltern = None
        else:
            eltern = zuordnung.get(o.eltern_id)
            if eltern is None:
                continue
        zuordnung[o.pk] = Bewertungsordner.objects.create(
            unterricht=ziel, eltern=eltern, name=o.name, gewicht=o.gewicht, gewichtsart=o.gewichtsart,
            reihenfolge=o.reihenfolge, beschreibung=o.beschreibung)
        n_ordner += 1
    if not vorgabe and ziel.gewichtsart != quelle.gewichtsart:
        ziel.gewichtsart = quelle.gewichtsart
        ziel.save(update_fields=["gewichtsart"])
    n_ln = 0
    if mit_nachweisen and quelle.abschnitt_id == ziel.abschnitt_id:
        for ln in Leistungsnachweis.objects.filter(unterricht=quelle).order_by("datum", "pk"):
            if ln.ordner_id not in zuordnung or zuordnung[ln.ordner_id].voll():     # Höchstzahl laut Notenregel
                continue
            neu = Leistungsnachweis.objects.create(
                ordner=zuordnung[ln.ordner_id], titel=ln.titel, datum=ln.datum, gewicht=ln.gewicht,
                schluessel=ln.schluessel if quelle.skala_id == ziel.skala_id else None,
                max_be=ln.max_be if quelle.skala_id == ziel.skala_id else None)
            neu.notenzeilen_anlegen()
            n_ln += 1
    return n_ordner, n_ln, uebersprungen


def quellen(u):
    """Kurse, deren Struktur sich für `u` anbietet: gleiches Fach oder gleiche Lehrkraft, dieses oder das vorige Halbjahr."""
    abschnitte = [u.abschnitt_id] + list(u.abschnitt.schuljahr.abschnitte.filter(nummer__lt=u.abschnitt.nummer)
                                         .values_list("pk", flat=True))
    vorjahr = (Unterricht.objects.filter(fach=u.fach, gruppe__jahrgang=u.gruppe.jahrgang,
                                         abschnitt__schuljahr__beginn__lt=u.abschnitt.schuljahr.beginn,
                                         abschnitt__nummer=u.abschnitt.nummer)
               .order_by("-abschnitt__schuljahr__beginn").values_list("pk", flat=True)[:5]) if u.gruppe.jahrgang else []
    return (Unterricht.objects.filter(Q(abschnitt_id__in=abschnitte, fach=u.fach) | Q(abschnitt_id__in=abschnitte, lehrkraft=u.lehrkraft)
                                      | Q(pk__in=list(vorjahr)))
            .exclude(pk=u.pk).filter(bewertungsordner__isnull=False).distinct()
            .select_related("fach", "gruppe", "lehrkraft", "abschnitt__schuljahr")
            .order_by("-abschnitt__beginn", "fach__reihenfolge", "gruppe__name"))


def ziele(u, user):
    """Kurse desselben Halbjahres, auf die `user` die Struktur von `u` übertragen darf (eigene bzw. als Schulleitung alle des Jahrgangs)."""
    from . import rechte

    qs = (Unterricht.objects.filter(abschnitt=u.abschnitt).exclude(pk=u.pk)
          .filter(Q(lehrkraft=u.lehrkraft) | Q(fach=u.fach) | Q(gruppe__jahrgang=u.gruppe.jahrgang))
          .select_related("fach", "gruppe", "lehrkraft", "abschnitt").order_by("gruppe__name", "fach__reihenfolge"))
    erg = []
    for z in qs:
        if not rechte.darf_noten_eintragen(user, z):
            continue
        z.hindernis = hindernis(z)
        erg.append(z)
    return erg
