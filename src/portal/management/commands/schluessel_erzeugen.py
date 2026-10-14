from django.core.management.base import BaseCommand

from portal.krypto import neuer_schluessel


class Command(BaseCommand):
    help = "Erzeugt einen neuen DATEN_SCHLUESSEL für die .env (Verschlüsselung von Anhängen und Sicherungen)."

    def handle(self, *args, **opts):
        self.stdout.write(neuer_schluessel())
