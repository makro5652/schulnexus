"""
Grundeinrichtung: Rollen (Benutzergruppen) mit Rechten und Standard-Notenskalen.
Kann gefahrlos mehrfach ausgeführt werden.
"""
from decimal import Decimal

from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from foerderung.models import Ausgleichsmassnahme, Foerderschwerpunkt
from noten.models import Notenskala, Notenstufe
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

# Förderunterlagen sind vertraulich: das Sekretariat sieht nur Nachteilsausgleiche (Prüfungsorganisation).
VERWALTUNG_FOERDERRECHTE = {"view_nachteilsausgleich", "view_foerderschwerpunkt", "view_ausgleichsmassnahme"}

# Rechte, die NUR Personalverwaltung und Schulleitung erhalten (nicht das Sekretariat)
HR_RECHTE = {"view_hr_daten"} | {f"{a}_{m}" for a in ("add", "change", "delete", "view")
                                  for m in ("nachweis", "nachweisart", "personalabwesenheit")}

ROLLEN = {
    "Verwaltung": "__alle_ausser_hr__",
    "Schulleitung": "__alle__",
    "Personalverwaltung": [
        f"{a}_{m}" for a in ("add", "change", "view", "delete")
        for m in ("personalprofil", "personalbereich", "dienstleister", "nachweisart", "nachweis",
                  "personalabwesenheit", "fortbildung", "notfallkontakt", "dokument")
    ] + ["add_person", "change_person", "view_person", "view_fach", "view_hr_daten",
         "add_zusatzfeld", "change_zusatzfeld", "view_zusatzfeld"],
    "Lehrkraft": [
        "view_person", "view_schuelerprofil", "view_gruppe", "view_mitgliedschaft", "view_fach", "view_beziehung",
        "view_unterricht", "view_notenskala", "view_notenstufe", "view_notenschluessel", "view_gewichtungsvorlage",
        "view_leistungskategorie",
        "view_laufbahnabschnitt", "view_abschluss", "view_sprachenfolge", "view_vorherigeschule",
        "view_elternprofil", "view_bildungsgang", "view_abschlussart", "view_einwilligung",
        "add_bewertungsordner", "change_bewertungsordner", "view_bewertungsordner", "delete_bewertungsordner",
        "add_leistungsnachweis", "change_leistungsnachweis", "view_leistungsnachweis", "delete_leistungsnachweis",
        "add_note", "change_note", "view_note",
        "add_zeugnisnote", "change_zeugnisnote", "view_zeugnisnote",
        "add_fehlzeit", "change_fehlzeit", "view_fehlzeit", "view_stunde",
        "view_agangebot", "view_agwahl", "view_agzuteilung",
        # Anhänge (sichtbar nur nach Zugriffsstufe) und Förderung (zeilenweise: eigene Klasse / eigene Schüler:innen)
        "add_dokument", "view_dokument",
        "add_foerderplan", "change_foerderplan", "view_foerderplan",
        "add_foerderziel", "change_foerderziel", "view_foerderziel", "delete_foerderziel",
        "add_foerdereintrag", "change_foerdereintrag", "view_foerdereintrag",
        "add_nachteilsausgleich", "change_nachteilsausgleich", "view_nachteilsausgleich",
        "add_aushaendigung", "change_aushaendigung", "view_aushaendigung",
        "view_foerderschwerpunkt", "view_ausgleichsmassnahme",
    ],
    "Förderkoordination": "__foerderung__",
}

FACH_APPS = ["stammdaten", "noten", "fehlzeiten", "nachmittag", "foerderung"]

# Grundlegende Leserechte der Förderkoordination außerhalb des Förderbereichs
FOERDERKOORDINATION_EXTRA = [
    "view_person", "view_schuelerprofil", "view_gruppe", "view_mitgliedschaft", "view_fach", "view_beziehung",
    "view_elternprofil", "view_laufbahnabschnitt", "view_bildungsgang", "view_sprachenfolge", "view_personalprofil",
    "view_unterricht", "add_dokument", "change_dokument", "view_dokument", "delete_dokument",
]


def englisch_ergaenzen(obj, **felder):
    """Setzt englische Bezeichnungen nur, wenn sie noch leer sind – eigene Anpassungen bleiben erhalten."""
    geaendert = [f for f, wert in felder.items() if wert and not getattr(obj, f)]
    for f in geaendert:
        setattr(obj, f, felder[f])
    if geaendert:
        obj.save(update_fields=geaendert)


class Command(BaseCommand):
    help = "Legt Rollen und Standard-Notenskalen an (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        # Rechte werden nur ERGÄNZT, nie entfernt: Anpassungen in der Verwaltung bleiben erhalten.
        for rolle, rechte in ROLLEN.items():
            gruppe, _ = Group.objects.get_or_create(name=rolle)
            perms = Permission.objects.filter(content_type__app_label__in=FACH_APPS)
            if rechte == "__alle_ausser_hr__":
                perms = perms.exclude(codename__in=HR_RECHTE).exclude(
                    Q(content_type__app_label="foerderung") & ~Q(codename__in=VERWALTUNG_FOERDERRECHTE))
            elif rechte == "__foerderung__":
                perms = perms.filter(Q(content_type__app_label="foerderung") | Q(codename__in=FOERDERKOORDINATION_EXTRA))
            elif rechte != "__alle__":
                perms = perms.filter(codename__in=rechte)
            gruppe.permissions.add(*perms)
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
