"""
Filter nach Klasse und Jahrgang für Listen der Verwaltungsoberfläche (ab 0.6.0).

Überall, wo Einträge zu Schüler:innen stehen (Fehlzeiten, AG-Wünsche, Förderpläne, Kontakte …), lässt sich die Liste
auf eine Stammklasse oder einen Jahrgang des laufenden Schuljahres einschränken – statt in der Liste der ganzen Schule
zu suchen. Mit dem Ankreuzfeld im Tabellenkopf wählt man danach die ganze Klasse für eine Sammelaktion aus.

    list_filter = [klassenfilter("schueler"), jahrgangsfilter("schueler"), …]

`pfad` ist der Weg vom Modell zum Schülerprofil ("" = das Modell ist selbst das Schülerprofil).
"""
from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Gruppe, Mitgliedschaft, Schuljahr


def _stammklassen():
    sj = Schuljahr.aktuelles()
    if not sj:
        return Gruppe.objects.none()
    return Gruppe.objects.filter(schuljahr=sj, typ=Gruppe.STAMMKLASSE).order_by("jahrgang", "name")


def _einschraenken(queryset, pfad, mitgliedschaften):
    feld = f"{pfad}__in" if pfad else "pk__in"
    return queryset.filter(**{feld: mitgliedschaften.values("schueler")})


def klassenfilter(pfad="schueler"):
    class KlassenFilter(admin.SimpleListFilter):
        title = _("Klasse (aktuell)")
        parameter_name = "klasse"

        def lookups(self, request, model_admin):
            return [(g.pk, g.name) for g in _stammklassen()]

        def queryset(self, request, queryset):
            wert = self.value()
            if wert and str(wert).isdigit():
                return _einschraenken(queryset, pfad, Mitgliedschaft.objects.aktiv().filter(gruppe_id=wert))
            return queryset

    return KlassenFilter


def jahrgangsfilter(pfad="schueler"):
    class JahrgangsFilter(admin.SimpleListFilter):
        title = _("Jahrgang (aktuell)")
        parameter_name = "jahrgang_aktuell"

        def lookups(self, request, model_admin):
            jahrgaenge = sorted({g.jahrgang for g in _stammklassen() if g.jahrgang is not None})
            return [(j, str(j)) for j in jahrgaenge]

        def queryset(self, request, queryset):
            wert = self.value()
            if wert and str(wert).isdigit():
                return _einschraenken(queryset, pfad, Mitgliedschaft.objects.aktiv().filter(
                    gruppe__in=_stammklassen().filter(jahrgang=wert)))
            return queryset

    return JahrgangsFilter


def suche_mit_klasse(queryset, suchbegriff, pfad=""):
    """
    Suchfelder für Schüler:innen (auch die Auswahlfelder mit Tippen): Ein Wort, das genau wie eine Stammklasse des
    laufenden Schuljahres heißt („9a“), schränkt auf diese Klasse ein; die übrigen Wörter suchen wie gewohnt.
    Gibt (queryset, restlicher Suchbegriff, eingeschränkt) zurück.
    """
    woerter = (suchbegriff or "").split()
    if not woerter:
        return queryset, suchbegriff, False
    namen = {g.name.lower(): g.pk for g in _stammklassen()}
    rest, klassen = [], []
    for w in woerter:
        (klassen if w.lower() in namen else rest).append(w)
    if not klassen:
        return queryset, suchbegriff, False
    for w in klassen:
        queryset = _einschraenken(queryset, pfad, Mitgliedschaft.objects.aktiv().filter(gruppe_id=namen[w.lower()]))
    return queryset, " ".join(rest), True
