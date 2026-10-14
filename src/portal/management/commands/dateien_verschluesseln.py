"""
Verschlüsselt vorhandene, noch unverschlüsselte Dateien nach dem Setzen von DATEN_SCHLUESSEL:
Anhänge, Bewerbungsunterlagen, Modulsicherungen und PDF-Exporte. Bereits verschlüsselte Dateien bleiben unverändert,
daher kann der Befehl bei jedem Start laufen (docker/entrypoint.sh).
"""
from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import models

from portal.krypto import MAGIC, VerschluesselterSpeicher, aktiv, bytes_verschluesseln


class Command(BaseCommand):
    help = "Verschlüsselt alle noch unverschlüsselten hochgeladenen Dateien mit DATEN_SCHLUESSEL."

    def add_arguments(self, parser):
        parser.add_argument("--probelauf", action="store_true", help="nur zählen, nichts ändern")

    def handle(self, *args, **opts):
        if not aktiv():
            raise CommandError("DATEN_SCHLUESSEL ist nicht gesetzt.")
        neu = schon = fehlt = 0
        for model in apps.get_models():
            felder = [f for f in model._meta.concrete_fields if isinstance(f, models.FileField)]
            for f in felder:
                if not isinstance(f.storage, VerschluesselterSpeicher):
                    continue
                for name in model._default_manager.exclude(**{f.name: ""}).values_list(f.name, flat=True):
                    if not name or not f.storage.exists(name):
                        fehlt += 1
                        continue
                    pfad = f.storage.path(name)
                    with open(pfad, "rb") as d:
                        daten = d.read()
                    if daten[:len(MAGIC)] == MAGIC:
                        schon += 1
                        continue
                    if not opts["probelauf"]:
                        tmp = pfad + ".neu"
                        with open(tmp, "wb") as d:
                            d.write(bytes_verschluesseln(daten))
                        import os
                        os.replace(tmp, pfad)
                    neu += 1
        neu += self._ablage(opts["probelauf"])
        self.stdout.write(f"verschlüsselt: {neu}, bereits verschlüsselt: {schon}, Datei fehlt: {fehlt}"
                          + (" (Probelauf)" if opts["probelauf"] else ""))

    @staticmethod
    def _ablage(probelauf):
        """Modulsicherungen und PDF-Exporte (Serverschlüssel, an Ort und Stelle)."""
        from django.conf import settings

        from portal.krypto import ist_verschluesselt_datei, ablage_verschluesseln

        wurzel = settings.MODUL_SICHERUNGEN
        if not wurzel.exists():
            return 0
        n = 0
        for pfad in sorted(wurzel.rglob("*")):
            if not pfad.is_file() or pfad.suffix not in (".zip", ".pdf", ".enc") or ist_verschluesselt_datei(pfad):
                continue
            if not probelauf:
                ablage_verschluesseln(pfad)
            n += 1
        return n
