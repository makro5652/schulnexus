from django.conf import settings
from django.core.management.base import BaseCommand

from sicherung.archiv import sicherung_erstellen, sicherung_loeschen
from sicherung.models import Sicherung
from sicherung.module import SCHLUESSEL


class Command(BaseCommand):
    help = "Legt eine Modulsicherung an (z. B. täglich per Zeitplan) und löscht ältere automatische Sicherungen."

    def add_arguments(self, parser):
        parser.add_argument("module", nargs="*", help=f"Module (Standard: alle): {', '.join(SCHLUESSEL)}")
        parser.add_argument("--mit-dateien", action="store_true", help="hochgeladene Dateien einschließen")
        parser.add_argument("--behalten", type=int, default=settings.SICHERUNG_BEHALTEN_AUTOMATISCH,
                            help="Anzahl automatischer Sicherungen, die aufbewahrt werden")

    def handle(self, *args, **opts):
        unbekannt = set(opts["module"]) - set(SCHLUESSEL)
        if unbekannt:
            self.stderr.write(f"Unbekannte Module: {', '.join(sorted(unbekannt))}")
            return
        s = sicherung_erstellen(opts["module"] or SCHLUESSEL, art=Sicherung.AUTOMATISCH, mit_dateien=opts["mit_dateien"])
        self.stdout.write(f"Sicherung erstellt: {s.datei} ({s.gesamt} Einträge, {s.groesse} Bytes)")
        alte = list(Sicherung.objects.filter(art=Sicherung.AUTOMATISCH).order_by("-erstellt_am")[max(opts["behalten"], 1):])
        for a in alte:
            sicherung_loeschen(a, None)
        if alte:
            self.stdout.write(f"{len(alte)} ältere automatische Sicherung(en) gelöscht.")
