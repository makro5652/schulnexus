"""
Stand der Leistungsvorgaben (Pflichtnoten mit Frist) je Unterricht (ab 0.4.7.0).

Ein Leistungsnachweis zählt für eine Vorgabe, wenn
- sein Datum spätestens am Tag der Frist liegt,
- sein Ordnerpfad den Text „Ordner enthält“ enthält (falls angegeben),
- seine Bezeichnung den Text „Bezeichnung enthält“ enthält (falls angegeben).
„Vollständig“ ist er, wenn für alle Schüler:innen, die am Tag des Leistungsnachweises zur Gruppe gehörten, eine Note
oder ein Vermerk eingetragen ist (später Hinzugekommene zählen für frühere Leistungsnachweise nicht).

Stand: erfüllt (genug vollständige) · in Arbeit (begonnen, Frist läuft) · offen (nichts, Frist läuft) · überfällig.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .berechnung import Baum
from .models import Leistungsvorgabe, Note, Unterricht

ERFUELLT, IN_ARBEIT, OFFEN, UEBERFAELLIG = "erfuellt", "in_arbeit", "offen", "ueberfaellig"
STAND_TEXT = {ERFUELLT: _("erfüllt"), IN_ARBEIT: _("in Arbeit"), OFFEN: _("offen"), UEBERFAELLIG: _("überfällig")}
BALD_TAGE = 14


@dataclass
class Stand:
    vorgabe: Leistungsvorgabe
    unterricht: Unterricht
    stand: str
    vollstaendig: int
    angelegt: int
    nachweise: list = field(default_factory=list)

    @property
    def text(self):
        return STAND_TEXT[self.stand]

    @property
    def unvollstaendig(self):
        return self.angelegt - self.vollstaendig

    @property
    def erfuellt(self):
        return self.stand == ERFUELLT

    @property
    def bald(self):
        heute = timezone.localdate()
        return not self.erfuellt and heute <= self.vorgabe.frist <= heute + timedelta(days=BALD_TAGE)


def _passt(text, muster):
    return not muster or muster.strip().lower() in (text or "").lower()


def mitgliedschaften(unterricht):
    """(schueler_id, von, bis) aller Mitgliedschaften der Gruppe, die das Halbjahr berühren."""
    from stammdaten.models import Mitgliedschaft

    a = unterricht.abschnitt
    return list(Mitgliedschaft.objects.filter(gruppe=unterricht.gruppe, von__lte=a.ende)
                .filter(Q(bis__isnull=True) | Q(bis__gte=a.beginn)).values_list("schueler_id", "von", "bis"))


def mitglieder_am(mitglieder, tag):
    return {sid for sid, von, bis in mitglieder if von <= tag and (bis is None or bis >= tag)}


def stand(vorgabe, unterricht, baum=None, mitglieder=None, noten=None, heute=None):
    """Stand einer Vorgabe für einen Unterricht. `baum`, `mitglieder` und `noten` können vorab geladen werden."""
    heute = heute or timezone.localdate()
    baum = baum or Baum(unterricht)
    if mitglieder is None:
        mitglieder = mitgliedschaften(unterricht)
    pfade = {o.pk: pfad for o, _e, pfad in baum.in_reihenfolge()}
    passende = [ln for ln in baum.nachweise if ln.datum <= vorgabe.frist and _passt(pfade.get(ln.ordner_id, ""), vorgabe.ordner_enthaelt)
                and _passt(ln.titel, vorgabe.titel_enthaelt)]
    if noten is None:
        noten = Note.objects.filter(leistungsnachweis__in=passende).filter(Q(stufe__isnull=False) | ~Q(sonderstatus=""))
        bewertet = defaultdict(set)
        for ln_id, s_id in noten.values_list("leistungsnachweis_id", "schueler_id"):
            bewertet[ln_id].add(s_id)
    else:
        bewertet = noten
    vollstaendig = []
    for ln in passende:
        noetig = mitglieder_am(mitglieder, ln.datum)
        if noetig and noetig <= bewertet.get(ln.pk, set()):
            vollstaendig.append(ln)
    if len(vollstaendig) >= vorgabe.mindestanzahl:
        s = ERFUELLT
    elif heute > vorgabe.frist:
        s = UEBERFAELLIG
    elif passende:
        s = IN_ARBEIT
    else:
        s = OFFEN
    return Stand(vorgabe, unterricht, s, len(vollstaendig), len(passende), passende)


class Vorrat:
    """Lädt Bewertungsbäume, Schüler:innen und eingetragene Noten je Unterricht einmal (für Übersichten)."""

    def __init__(self):
        self._baum, self._schueler, self._bewertet = {}, {}, {}

    def stand(self, vorgabe, unterricht, heute=None):
        u = unterricht.pk
        if u not in self._baum:
            self._baum[u] = Baum(unterricht)
            self._schueler[u] = mitgliedschaften(unterricht)
            bewertet = defaultdict(set)
            for ln_id, s_id in Note.objects.filter(leistungsnachweis__unterricht=unterricht).filter(
                    Q(stufe__isnull=False) | ~Q(sonderstatus="")).values_list("leistungsnachweis_id", "schueler_id"):
                bewertet[ln_id].add(s_id)
            self._bewertet[u] = bewertet
        return stand(vorgabe, unterricht, self._baum[u], self._schueler[u], self._bewertet[u], heute)


def vorgaben_fuer(unterricht):
    """Alle Vorgaben, die für diesen Unterricht gelten."""
    j = unterricht.gruppe.jahrgang
    if j is None:
        return Leistungsvorgabe.objects.none()
    return (Leistungsvorgabe.objects.filter(abschnitt=unterricht.abschnitt, jahrgang_von__lte=j, jahrgang_bis__gte=j)
            .filter(Q(faecher__isnull=True) | Q(faecher=unterricht.fach)).distinct())


def staende_fuer_unterricht(unterricht):
    vorrat = Vorrat()
    return [vorrat.stand(v, unterricht) for v in vorgaben_fuer(unterricht)]
