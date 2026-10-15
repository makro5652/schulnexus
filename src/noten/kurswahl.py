"""
Kursauswahl „Mein Unterricht“ (ab 0.4.7.1): Auswahlliste statt einzelner Kacheln, damit auch Lehrkräfte mit vielen
Kursen schnell zum richtigen Unterricht kommen. Verwendet im Menüband, auf der Startseite und als „Kurs wechseln“
auf den Seiten eines Unterrichts. Der zuletzt geöffnete Kurs wird in der Sitzung gemerkt und vorausgewählt.
"""
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.translation import gettext_lazy as _, pgettext

from portal.rechte import personal_von

from .models import Unterricht

# Ziel → (URL-Name, Beschriftung, Symbol)
ZIELE = {
    "uebersicht": ("notenuebersicht", _("Notenübersicht"), "liste"),
    "eintragen": ("noten_eintragen", _("Noten eintragen"), "stift"),
    "struktur": ("bewertungsstruktur", _("Bewertungsstruktur"), "ordner"),
    "zeugnis": ("zeugnis_unterricht", _("Zeugnisnoten"), "zeugnis"),
}
URLNAME_ZU_ZIEL = {url: ziel for ziel, (url, _t, _s) in ZIELE.items()}
URLNAME_ZU_ZIEL["noten_bearbeiten"] = "eintragen"
SITZUNG = "letzter_kurs"


def meine_kurse(user, sj=None):
    """Eigener Unterricht im (aktuellen) Schuljahr, nach Halbjahr, Gruppe und Fach geordnet."""
    from stammdaten.models import Schuljahr

    p = personal_von(user)
    sj = sj or Schuljahr.aktuelles()
    if p is None or sj is None:
        return []
    return list(Unterricht.objects.filter(lehrkraft=p, abschnitt__schuljahr=sj)
                .select_related("fach", "gruppe", "abschnitt__schuljahr")
                .order_by("abschnitt__nummer", "gruppe__name", "fach__reihenfolge", "fach__name"))


def auswahl(request, aktuell=None, kurse=None, nur_wenn_enthalten=False):
    """
    Daten für die Auswahlliste: {"gruppen": [{"titel", "laufend", "kurse": [{"pk", "titel"}]}], "gewaehlt", "anzahl"}.
    `aktuell`: der gerade angezeigte Unterricht (wird vorausgewählt). Mit `nur_wenn_enthalten` gibt es nur dann eine
    Auswahl, wenn `aktuell` zum eigenen Unterricht gehört und es mindestens einen weiteren Kurs gibt.
    """
    kurse = meine_kurse(request.user) if kurse is None else kurse
    if not kurse:
        return None
    pks = [u.pk for u in kurse]
    if nur_wenn_enthalten and (aktuell is None or aktuell.pk not in pks or len(kurse) < 2):
        return None
    heute = timezone.localdate()
    gewaehlt = aktuell.pk if aktuell is not None and aktuell.pk in pks else request.session.get(SITZUNG)
    if gewaehlt not in pks:
        laufend = [u for u in kurse if u.abschnitt.beginn <= heute <= u.abschnitt.ende]
        gewaehlt = (laufend or kurse)[0].pk
    gruppen = []
    for u in kurse:
        if not gruppen or gruppen[-1]["abschnitt_id"] != u.abschnitt_id:
            laufend = u.abschnitt.beginn <= heute <= u.abschnitt.ende
            titel = u.abschnitt.lokal_name + (" · " + pgettext("Halbjahr", "laufend") if laufend else "")
            gruppen.append({"abschnitt_id": u.abschnitt_id, "titel": titel, "laufend": laufend, "kurse": []})
        gruppen[-1]["kurse"].append({"pk": u.pk, "titel": f"{u.fach.lokal_name} {u.gruppe.name}"})
    return {"gruppen": gruppen, "gewaehlt": gewaehlt, "anzahl": len(kurse),
            "ziele": [{"wert": z, "titel": t, "symbol": s} for z, (_u, t, s) in ZIELE.items() if z != "struktur"]}


def merken(request, unterricht):
    request.session[SITZUNG] = unterricht.pk


@login_required
def kurs_oeffnen(request):
    """Öffnet den gewählten Kurs auf der gewünschten Seite. Die Rechte prüft die Zielseite."""
    u = get_object_or_404(Unterricht, pk=request.GET.get("u") or 0)
    ziel = request.GET.get("ziel")
    url_name = ZIELE.get(ziel, ZIELE["uebersicht"])[0]
    merken(request, u)
    return redirect(url_name, pk=u.pk)
