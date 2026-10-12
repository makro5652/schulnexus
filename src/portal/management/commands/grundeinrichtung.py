"""
Grundeinrichtung: Rollen (Benutzergruppen) mit Rechten und Standard-Notenskalen.
Kann gefahrlos mehrfach ausgeführt werden.
"""
from decimal import Decimal

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from noten.models import Notenskala, Notenstufe

SEK1 = [
    ("1+", "0.7"), ("1", "1.0"), ("1-", "1.3"), ("2+", "1.7"), ("2", "2.0"), ("2-", "2.3"),
    ("3+", "2.7"), ("3", "3.0"), ("3-", "3.3"), ("4+", "3.7"), ("4", "4.0"), ("4-", "4.3"),
    ("5+", "4.7"), ("5", "5.0"), ("5-", "5.3"), ("6", "6.0"),
]

ROLLEN = {
    "Verwaltung": "__alle__",
    "Schulleitung": "__alle__",
    "Lehrkraft": [
        "view_person", "view_schuelerprofil", "view_gruppe", "view_mitgliedschaft", "view_fach", "view_beziehung",
        "view_unterricht", "view_notenskala", "view_notenstufe", "view_notenschluessel", "view_gewichtungsvorlage",
        "view_leistungskategorie",
        "add_bewertungsordner", "change_bewertungsordner", "view_bewertungsordner", "delete_bewertungsordner",
        "add_leistungsnachweis", "change_leistungsnachweis", "view_leistungsnachweis", "delete_leistungsnachweis",
        "add_note", "change_note", "view_note",
        "add_zeugnisnote", "change_zeugnisnote", "view_zeugnisnote",
        "add_fehlzeit", "change_fehlzeit", "view_fehlzeit", "view_stunde",
        "view_agangebot", "view_agwahl", "view_agzuteilung",
    ],
}

FACH_APPS = ["stammdaten", "noten", "fehlzeiten", "nachmittag"]


class Command(BaseCommand):
    help = "Legt Rollen und Standard-Notenskalen an (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        for rolle, rechte in ROLLEN.items():
            gruppe, _ = Group.objects.get_or_create(name=rolle)
            if rechte == "__alle__":
                perms = Permission.objects.filter(content_type__app_label__in=FACH_APPS)
            else:
                perms = Permission.objects.filter(content_type__app_label__in=FACH_APPS, codename__in=rechte)
            gruppe.permissions.set(perms)
        self.stdout.write("Rollen eingerichtet: " + ", ".join(ROLLEN))

        sek1, neu = Notenskala.objects.get_or_create(
            name="Sek I – Noten 1 bis 6 mit Tendenzen",
            defaults={
                "hoeher_ist_besser": False,
                "nachkommastellen": 2,
                "gefaehrdung_ab": Decimal("4.50"),
                "beschreibung": "Tendenzwerte (z. B. 2+ = 1,7) sind Voreinstellungen und können angepasst werden.",
            },
        )
        if neu:
            Notenstufe.objects.bulk_create(
                [Notenstufe(skala=sek1, bezeichnung=b, wert=Decimal(w), reihenfolge=i) for i, (b, w) in enumerate(SEK1)]
            )

        sek2, neu = Notenskala.objects.get_or_create(
            name="Sek II – Punkte 0 bis 15",
            defaults={"hoeher_ist_besser": True, "nachkommastellen": 2, "gefaehrdung_ab": Decimal("4.49")},
        )
        if neu:
            Notenstufe.objects.bulk_create(
                [Notenstufe(skala=sek2, bezeichnung=str(p), wert=Decimal(p), reihenfolge=15 - p) for p in range(15, -1, -1)]
            )
        self.stdout.write(self.style.SUCCESS("Notenskalen eingerichtet."))
