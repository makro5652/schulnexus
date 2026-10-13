"""
Grundeinrichtung: Rollen (Benutzergruppen) mit Rechten und Standard-Notenskalen.
Kann gefahrlos mehrfach ausgeführt werden.
"""
from decimal import Decimal

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from aufnahme.models import ChecklistenVorlage, VorlagenPunkt
from foerderung.models import Ausgleichsmassnahme, Foerderschwerpunkt
from noten.models import Notenskala, Notenstufe
from portal import rollen as R
from stammdaten.models import Abschlussart, Bildungsgang, Nachweisart, Personalbereich

# Voreinstellungen – in der Verwaltung frei änderbar (Stammdaten › Bildungsgänge / Abschlussarten).
# (Kürzel, Name, Name englisch, angestrebter Abschluss, … englisch, ab Jahrgang, bis Jahrgang)
BILDUNGSGAENGE = [
    ("KG", "Kindergarten / Vorschule", "Kindergarten / Pre-school", "", "", None, None),
    ("GS", "Grundschule", "Primary school", "", "", 1, 4),
    ("HS", "Hauptschulbildungsgang", "Hauptschule track",
     "Erster allgemeinbildender Schulabschluss (Hauptschulabschluss)",
     "First general school-leaving certificate (Hauptschulabschluss)", 5, 10),
    ("RS", "Realschulbildungsgang", "Realschule track",
     "Mittlerer Schulabschluss (Realschulabschluss)", "Intermediate school-leaving certificate (Realschulabschluss)", 5, 10),
    ("GYM", "Gymnasialer Bildungsgang (Sek I)", "Gymnasium track (lower secondary)",
     "Berechtigung zum Besuch der gymnasialen Oberstufe", "Entitlement to enter the Gymnasium upper level", 5, 10),
    ("GOS", "Gymnasiale Oberstufe", "Gymnasium upper level (Oberstufe)",
     "Allgemeine Hochschulreife", "General higher education entrance qualification (Abitur)", 11, 12),
]
ABSCHLUSSARTEN = [
    ("ESA", "Erster allgemeinbildender Schulabschluss (Hauptschulabschluss)", "First general school-leaving certificate (Hauptschulabschluss)"),
    ("EESA", "Erweiterter erster allgemeinbildender Schulabschluss", "Extended first general school-leaving certificate"),
    ("MSA", "Mittlerer Schulabschluss (Realschulabschluss)", "Intermediate school-leaving certificate (Realschulabschluss)"),
    ("OS", "Berechtigung zum Besuch der gymnasialen Oberstufe", "Entitlement to enter the Gymnasium upper level"),
    ("FHR", "Fachhochschulreife (schulischer Teil)", "Entrance qualification for universities of applied sciences (school part)"),
    ("AHR", "Allgemeine Hochschulreife (Abitur)", "General higher education entrance qualification (Abitur)"),
    ("DIA", "Deutsches Internationales Abitur (DIA)", "German International Abitur (DIA)"),
    ("DSD1", "Deutsches Sprachdiplom Stufe I (DSD I)", "German Language Certificate Level I (DSD I)"),
    ("DSD2", "Deutsches Sprachdiplom Stufe II (DSD II)", "German Language Certificate Level II (DSD II)"),
    ("SONST", "Sonstiges Zertifikat", "Other certificate"),
]

SEK1 = [
    ("1+", "0.7"), ("1", "1.0"), ("1-", "1.3"), ("2+", "1.7"), ("2", "2.0"), ("2-", "2.3"),
    ("3+", "2.7"), ("3", "3.0"), ("3-", "3.3"), ("4+", "3.7"), ("4", "4.0"), ("4-", "4.3"),
    ("5+", "4.7"), ("5", "5.0"), ("5-", "5.3"), ("6", "6.0"),
]

# Personalbereiche: (Kürzel, Bezeichnung, unterrichtend)
PERSONALBEREICHE = [
    ("SL", "Schulleitung", "School management", True),
    ("LK", "Lehrkräfte", "Teaching staff", True),
    ("KITA", "Kindergarten / Vorschule", "Kindergarten / Pre-school", False),
    ("NACHM", "Nachmittagsbereich / Coaches", "Afternoon programme / Coaches", False),
    ("VERW", "Verwaltung / Sekretariat", "Administration / School office", False),
    ("HR", "Personalverwaltung (HR)", "Human resources (HR)", False),
    ("FIN", "Finanzen / Buchhaltung", "Finance / Accounting", False),
    ("IT", "IT", "IT", False),
    ("FAC", "Facility Management / Haustechnik", "Facility management / Maintenance", False),
    ("REIN", "Reinigung", "Cleaning", False),
    ("SICH", "Sicherheit", "Security", False),
    ("KUE", "Küche / Cafeteria", "Kitchen / Cafeteria", False),
    ("TRANS", "Transport / Fahrdienst", "Transport / Drivers", False),
    ("GES", "Schulgesundheit / Krankenstation", "School health / Sick bay", False),
    ("BIB", "Bibliothek", "Library", False),
]
# Nachweisarten: (Bezeichnung, Gültigkeit in Monaten, Pflicht für Bereiche – "*" = alle)
NACHWEISARTEN = [
    ("Polizeiliches Führungszeugnis / Certificate of Good Conduct", "Police clearance / Certificate of Good Conduct", None, ["*"]),
    ("Kinderschutz-Schulung (Child Safeguarding)", "Child safeguarding training", 24, ["*"]),
    ("Erste-Hilfe-Kurs", "First aid course", 24, ["NACHM", "SICH", "TRANS", "KITA"]),
    ("Arbeitserlaubnis / Work Permit", "Work permit", None, []),
    ("Gesundheitszeugnis Lebensmittel (Food Handler)", "Food handler's certificate", 12, ["KUE"]),
    ("Fahrerlaubnis (Personenbeförderung)", "Driving licence (passenger transport)", None, ["TRANS"]),
    ("Rettungsschwimmer-Nachweis", "Lifeguard certificate", 24, []),
    ("Trainerlizenz / Coaching-Qualifikation", "Coaching licence / qualification", None, []),
]

# Förderung: Voreinstellungen, in der Verwaltung frei änderbar (Förderung › Förderschwerpunkte / Ausgleichsmaßnahmen).
FOERDERSCHWERPUNKTE = [
    ("Lesen und Rechtschreiben", "Reading and spelling"),
    ("Rechnen", "Mathematics / numeracy"),
    ("Deutsch als Zweitsprache (DaZ/DaF)", "German as a second language"),
    ("Lernen", "Learning"),
    ("Sprache und Kommunikation", "Speech, language and communication"),
    ("Emotionale und soziale Entwicklung", "Emotional and social development"),
    ("Aufmerksamkeit und Konzentration", "Attention and concentration"),
    ("Arbeits- und Lernverhalten", "Work and learning habits"),
    ("Körperliche und motorische Entwicklung", "Physical and motor development"),
    ("Sehen", "Vision"),
    ("Hören", "Hearing"),
    ("Autismus-Spektrum", "Autism spectrum"),
    ("Begabtenförderung", "Gifted and talented"),
]
# (Name, Name englisch, Notenschutz)
AUSGLEICHSMASSNAHMEN = [
    ("Zusätzliche Pausen", "Additional breaks", False),
    ("Separater, ruhiger Raum", "Separate, quiet room", False),
    ("Vorlesen der Aufgabenstellung", "Questions read aloud", False),
    ("Vergrößerte oder angepasste Arbeitsblätter", "Enlarged or adapted worksheets", False),
    ("Laptop / technische Hilfsmittel", "Laptop / assistive technology", False),
    ("Wörterbuch zugelassen", "Dictionary permitted", False),
    ("Strukturierungshilfen (Gliederung, Checklisten)", "Structuring aids (outlines, checklists)", False),
    ("Teilweise mündlich statt schriftlich", "Partly oral instead of written", False),
    ("Bevorzugter Sitzplatz", "Preferential seating", False),
    ("Lärmschutz-Kopfhörer", "Ear defenders / noise-cancelling headphones", False),
    ("Rechtschreibung wird nicht bewertet", "Spelling not assessed", True),
    ("Vorlesen wird nicht bewertet", "Reading aloud not assessed", True),
    ("Stärkere Gewichtung mündlicher Leistungen", "Greater weighting of oral work", True),
]

# Neuanmeldung: Checklisten-Vorlagen (Beispiele, in der Verwaltung frei änderbar; Punkte nur beim ersten Anlegen).
# (Name, Name englisch, Beschreibung, ab Jg., bis Jg., immer vorschlagen, [(Punkt, englisch, zuständig, Pflicht)])
CHECKLISTEN = [
    ("Standard", "Standard", "Grundausstattung jeder Anmeldung", None, None, True, [
        ("Anmeldeformular vollständig und unterschrieben", "Application form complete and signed", "sekretariat", True),
        ("Pass oder Geburtsurkunde des Kindes (Kopie)", "Child's passport or birth certificate (copy)", "sekretariat", True),
        ("Letzte zwei Zeugnisse liegen vor", "Last two school reports received", "sekretariat", True),
        ("Impfnachweis liegt vor", "Immunisation record received", "sekretariat", True),
        ("Aufnahmegespräch geführt", "Admission interview held", "koordination", True),
        ("Einstufung und Klasse festgelegt", "Placement and class decided", "koordination", True),
        ("Aufnahmeentscheidung der Schulleitung", "Admission decision by the head of school", "schulleitung", True),
        ("Schulvertrag unterschrieben zurück", "Signed school contract returned", "finanzen", True),
        ("Aufnahmegebühr bzw. Kaution eingegangen", "Admission fee or deposit received", "finanzen", True),
        ("Rechnungsempfänger:in geklärt", "Invoice recipient confirmed", "finanzen", True),
        ("Einwilligungen (Fotos, Datenverarbeitung) erhalten", "Consent forms (photos, data processing) received", "sekretariat", False),
        ("Begrüßungsunterlagen versandt", "Welcome pack sent", "sekretariat", False),
    ]),
    ("Mittelstufe", "Lower secondary", "Zusätzlich für die Jahrgänge 5 bis 10", 5, 10, False, [
        ("Bildungsgang (Haupt-, Realschule, Gymnasium) zugeordnet", "Track (Hauptschule, Realschule, Gymnasium) assigned", "koordination", True),
        ("Fremdsprachenfolge geklärt", "Foreign language sequence clarified", "koordination", False),
    ]),
    ("Oberstufe", "Upper secondary", "Zusätzlich für die Jahrgänge 11 und 12", 11, 12, False, [
        ("Anerkennung der bisherigen Abschlüsse geprüft", "Recognition of previous qualifications checked", "koordination", True),
        ("Kurswahl festgelegt", "Course choices confirmed", "koordination", True),
        ("Beratung zu den Abiturbedingungen dokumentiert", "Counselling on Abitur requirements documented", "koordination", False),
    ]),
    ("Geringe Deutschkenntnisse", "Limited German", "Quereinstieg mit DaZ-/DaF-Bedarf", None, None, False, [
        ("Sprachstandsfeststellung Deutsch durchgeführt", "German language assessment carried out", "koordination", True),
        ("DaZ-/DaF-Förderung eingeplant", "German support (DaZ/DaF) scheduled", "koordination", True),
    ]),
]

# Rollen und ihre Standardrechte stehen in portal/rollen.py.


def englisch_ergaenzen(obj, **felder):
    """Setzt englische Bezeichnungen nur, wenn sie noch leer sind – eigene Anpassungen bleiben erhalten."""
    geaendert = [f for f, wert in felder.items() if wert and not getattr(obj, f)]
    for f in geaendert:
        setattr(obj, f, felder[f])
    if geaendert:
        obj.save(update_fields=geaendert)


class Command(BaseCommand):
    help = "Legt Rollen und Standard-Notenskalen an (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument("--rechte-zuruecksetzen", action="store_true",
                            help="Rechte aller Standardrollen auf die Vorgaben aus portal/rollen.py zurücksetzen")

    @transaction.atomic
    def handle(self, *args, **options):
        # Rechte werden nur ERGÄNZT, nie entfernt: Anpassungen in der Verwaltung bleiben erhalten –
        # außer bei --rechte-zuruecksetzen.
        alle = Permission.objects.filter(content_type__app_label__in=R.APPS)
        for rolle in R.REIHENFOLGE:
            rechte = R.ROLLEN_RECHTE[rolle]
            gruppe, _ = Group.objects.get_or_create(name=rolle)
            if rechte == "__alle__":
                perms = alle
            elif rechte == "__foerderung__":
                perms = alle.filter(Q(content_type__app_label="foerderung") | Q(codename__in=R.FOERDERKOORDINATION_EXTRA))
            else:
                perms = alle.filter(codename__in=rechte)
            if options.get("rechte_zuruecksetzen"):
                gruppe.permissions.set(perms)
            else:
                gruppe.permissions.add(*perms)
        self.stdout.write("Rollen eingerichtet: " + ", ".join(R.REIHENFOLGE))

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
        englisch_ergaenzen(sek1, name_en="Lower secondary – grades 1 to 6 with +/-")

        sek2, neu = Notenskala.objects.get_or_create(
            name="Sek II – Punkte 0 bis 15",
            defaults={"hoeher_ist_besser": True, "nachkommastellen": 2, "gefaehrdung_ab": Decimal("4.49")},
        )
        if neu:
            Notenstufe.objects.bulk_create(
                [Notenstufe(skala=sek2, bezeichnung=str(p), wert=Decimal(p), reihenfolge=15 - p) for p in range(15, -1, -1)]
            )
        englisch_ergaenzen(sek2, name_en="Upper secondary – points 0 to 15")
        self.stdout.write(self.style.SUCCESS("Notenskalen eingerichtet."))

        for i, (k, name, name_en, abschluss, abschluss_en, von, bis) in enumerate(BILDUNGSGAENGE):
            obj, _ = Bildungsgang.objects.get_or_create(
                kuerzel=k, defaults={"name": name, "angestrebter_abschluss": abschluss,
                                     "jahrgang_von": von, "jahrgang_bis": bis, "reihenfolge": (i + 1) * 10},
            )
            englisch_ergaenzen(obj, name_en=name_en, angestrebter_abschluss_en=abschluss_en)
        for i, (k, name, name_en) in enumerate(ABSCHLUSSARTEN):
            obj, _ = Abschlussart.objects.get_or_create(kuerzel=k, defaults={"name": name, "reihenfolge": (i + 1) * 10})
            englisch_ergaenzen(obj, name_en=name_en)
        self.stdout.write(self.style.SUCCESS("Bildungsgänge und Abschlussarten eingerichtet."))

        bereiche = {}
        for i, (k, name, name_en, unterrichtet) in enumerate(PERSONALBEREICHE):
            bereiche[k], _ = Personalbereich.objects.get_or_create(
                kuerzel=k, defaults={"name": name, "unterrichtet": unterrichtet, "reihenfolge": (i + 1) * 10}
            )
            englisch_ergaenzen(bereiche[k], name_en=name_en)
        for i, (name, name_en, monate, pflicht) in enumerate(NACHWEISARTEN):
            art, neu = Nachweisart.objects.get_or_create(name=name, defaults={"gueltigkeit_monate": monate, "reihenfolge": (i + 1) * 10})
            englisch_ergaenzen(art, name_en=name_en)
            if neu:
                art.pflicht_fuer.set(list(bereiche.values()) if pflicht == ["*"] else [bereiche[k] for k in pflicht])
        self.stdout.write(self.style.SUCCESS("Personalbereiche und Nachweisarten eingerichtet."))

        for i, (name, name_en) in enumerate(FOERDERSCHWERPUNKTE):
            obj, _ = Foerderschwerpunkt.objects.get_or_create(name=name, defaults={"reihenfolge": (i + 1) * 10})
            englisch_ergaenzen(obj, name_en=name_en)
        for i, (name, name_en, notenschutz) in enumerate(AUSGLEICHSMASSNAHMEN):
            obj, _ = Ausgleichsmassnahme.objects.get_or_create(
                name=name, defaults={"notenschutz": notenschutz, "reihenfolge": (i + 1) * 10})
            englisch_ergaenzen(obj, name_en=name_en)
        self.stdout.write(self.style.SUCCESS("Förderschwerpunkte und Ausgleichsmaßnahmen eingerichtet."))

        for i, (name, name_en, beschreibung, von, bis, standard, punkte) in enumerate(CHECKLISTEN):
            vorlage, neu = ChecklistenVorlage.objects.get_or_create(name=name, defaults={
                "beschreibung": beschreibung, "jahrgang_von": von, "jahrgang_bis": bis, "standard": standard,
                "reihenfolge": (i + 1) * 10})
            englisch_ergaenzen(vorlage, name_en=name_en)
            if neu:
                VorlagenPunkt.objects.bulk_create([
                    VorlagenPunkt(vorlage=vorlage, text=t, text_en=t_en, zustaendig=z, pflicht=pf, reihenfolge=(j + 1) * 10)
                    for j, (t, t_en, z, pf) in enumerate(punkte)])
        self.stdout.write(self.style.SUCCESS("Checklisten-Vorlagen für Neuanmeldungen eingerichtet."))
