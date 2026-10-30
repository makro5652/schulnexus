"""
Notensperre (ab 0.4.8.0).

Die Noten einer Schülerin / eines Schülers in einem Halbjahr sind gesperrt, wenn
- für die Stammklasse und das Halbjahr eine ausdrückliche Notensperre gesetzt ist (geht allem anderen vor; eine
  ausdrückliche *Freigabe* hebt umgekehrt die automatische Sperre auf), sonst
- die Zeugniskonferenz der Klasse durchgeführt oder abgeschlossen ist, oder
- der Notenschluss für den Jahrgang vorbei ist (ab 0.4.16.0: Termin auf der Seite „Notensperre“), oder
- das Zeugnis der Schülerin / des Schülers freigegeben ist.

Gesperrt heißt: keine Noten eintragen oder ändern, keine Gewichte ändern, keine Leistungsnachweise mit diesen Noten
löschen, keine Zeugnisnote ändern. Sperren und freigeben dürfen Schulleitung, Stellvertretung und Stufenkoordination.
"""
from django.db.models import Q
from django.utils import timezone

from stammdaten.models import Gruppe, Mitgliedschaft

from .models import Notenschluss, Notensperre

AUTOMATIK, GESPERRT, OFFEN = "automatik", "gesperrt", "offen"


class Sperrstand:
    """Sperrstand aller Klassen eines Halbjahres (einmal geladen)."""

    def __init__(self, abschnitt):
        from zeugnisse.models import Konferenz, Zeugnis

        self.abschnitt = abschnitt
        self.explizit = {s.klasse_id: s for s in Notensperre.objects.filter(abschnitt=abschnitt).select_related("geaendert_von")}
        self.konferenz = {k.klasse_id: k for k in Konferenz.objects.filter(abschnitt=abschnitt)}
        self.freigegeben = set(Zeugnis.objects.filter(abschnitt=abschnitt, status=Zeugnis.FREIGEGEBEN).values_list("schueler_id", flat=True))
        self.schluesse = list(Notenschluss.objects.filter(abschnitt=abschnitt).order_by("datum"))
        self.jahrgang = dict(Gruppe.objects.filter(schuljahr_id=abschnitt.schuljahr_id, typ=Gruppe.STAMMKLASSE)
                             .values_list("pk", "jahrgang")) if self.schluesse else {}

    def notenschluss(self, klasse_id):
        jg = self.jahrgang.get(klasse_id)
        return next((n for n in self.schluesse if jg is not None and n.jahrgang_von <= jg <= n.jahrgang_bis), None)

    def schluss_vorbei(self, klasse_id):
        n = self.notenschluss(klasse_id)
        return n is not None and timezone.localdate() > n.datum

    def konferenz_gehalten(self, klasse_id):
        k = self.konferenz.get(klasse_id)
        return k is not None and k.status in (k.DURCHGEFUEHRT, k.ABGESCHLOSSEN)

    def klasse_gesperrt(self, klasse_id):
        if klasse_id in self.explizit:
            return self.explizit[klasse_id].gesperrt
        return self.konferenz_gehalten(klasse_id) or self.schluss_vorbei(klasse_id)

    def schueler_gesperrt(self, schueler_id, klasse_id):
        if klasse_id in self.explizit:
            return self.explizit[klasse_id].gesperrt
        return self.konferenz_gehalten(klasse_id) or self.schluss_vorbei(klasse_id) or schueler_id in self.freigegeben


def stammklassen(schueler_ids, abschnitt):
    """{schueler_id: klasse_id} – Stammklasse im Halbjahr (Stand am Ende bzw. heute)."""
    stichtag = min(max(timezone.localdate(), abschnitt.beginn), abschnitt.ende)
    erg = {}
    for sid, gid in (Mitgliedschaft.objects.filter(schueler_id__in=schueler_ids, gruppe__typ=Gruppe.STAMMKLASSE,
                                                   gruppe__schuljahr_id=abschnitt.schuljahr_id, von__lte=stichtag)
                     .filter(Q(bis__isnull=True) | Q(bis__gte=stichtag)).values_list("schueler_id", "gruppe_id")):
        erg[sid] = gid
    rest = [s for s in schueler_ids if s not in erg]
    if rest:   # z. B. nach Abgang: letzte Stammklasse im Schuljahr
        for sid, gid in (Mitgliedschaft.objects.filter(schueler_id__in=rest, gruppe__typ=Gruppe.STAMMKLASSE,
                                                       gruppe__schuljahr_id=abschnitt.schuljahr_id)
                         .order_by("von").values_list("schueler_id", "gruppe_id")):
            erg[sid] = gid
    return erg


def gesperrte_schueler(unterricht, schueler_ids=None, stand=None):
    """Menge der Schüler-IDs, deren Noten in diesem Unterricht gesperrt sind."""
    if schueler_ids is None:
        schueler_ids = list(unterricht.schueler().values_list("pk", flat=True))
    stand = stand or Sperrstand(unterricht.abschnitt)
    klassen = stammklassen(schueler_ids, unterricht.abschnitt)
    return {sid for sid in schueler_ids if stand.schueler_gesperrt(sid, klassen.get(sid))}


def ist_gesperrt(note_oder_schueler_id, unterricht):
    sid = getattr(note_oder_schueler_id, "schueler_id", note_oder_schueler_id)
    return sid in gesperrte_schueler(unterricht, [sid])
