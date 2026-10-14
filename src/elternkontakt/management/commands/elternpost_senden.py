from django.conf import settings
from django.core.management.base import BaseCommand

from elternkontakt.versand import postausgang_senden


class Command(BaseCommand):
    help = "Versendet wartende und fehlgeschlagene Elternnachrichten erneut (nur mit ELTERN_EMAIL_VERSAND=1)."

    def handle(self, *args, **opts):
        if not settings.ELTERN_EMAIL_VERSAND:
            self.stdout.write("E-Mail-Versand ist ausgeschaltet (ELTERN_EMAIL_VERSAND=0) – nichts versendet.")
            return
        self.stdout.write(f"{postausgang_senden()} Nachricht(en) versendet.")
