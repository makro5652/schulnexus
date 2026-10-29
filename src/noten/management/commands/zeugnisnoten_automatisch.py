"""Automatische Zeugnisnoten für alle Unterrichte nachziehen (ab 0.4.15.0; läuft beim Start des Containers)."""
from django.core.management.base import BaseCommand

from noten.automatik import aktualisieren
from noten.models import Unterricht


class Command(BaseCommand):
    help = "Setzt fehlende Zeugnisnoten automatisch aus den Einzelnoten; festgesetzte Noten bleiben unverändert."

    def handle(self, *args, **options):
        n = aktualisieren(Unterricht.objects.values_list("pk", flat=True))
        self.stdout.write(self.style.SUCCESS(f"Automatische Zeugnisnoten: {n} gesetzt oder aktualisiert."))
