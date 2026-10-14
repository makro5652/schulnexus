from django.core.management.base import BaseCommand

from elternkontakt.pruefung import schueler_pruefen
from stammdaten.models import Gruppe, Mitgliedschaft


class Command(BaseCommand):
    help = "Prüft die Benachrichtigungsregeln für alle Schüler:innen mit Stammklasse (z. B. täglich per Zeitplan)."

    def handle(self, *args, **opts):
        ids = set(Mitgliedschaft.objects.aktiv().filter(gruppe__typ=Gruppe.STAMMKLASSE).values_list("schueler_id", flat=True))
        from stammdaten.models import Schuelerprofil

        n = sum(len(schueler_pruefen(s)) for s in Schuelerprofil.objects.filter(pk__in=ids).select_related("person"))
        self.stdout.write(f"{n} Benachrichtigung(en) ausgelöst.")
