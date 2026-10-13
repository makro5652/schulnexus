"""
Demo-Datensatz mit ERFUNDENEN Personen zum Ausprobieren.
Niemals auf einem System mit echten Schülerdaten ausführen.
"""
import os
import random
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from fehlzeiten.models import Fehlzeit, Stunde
from nachmittag.models import AGAngebot, AGWahl
from nachmittag.zuteilung import lose_zuteilen
from noten.models import (
    Bewertungsordner,
    Gewichtungsvorlage,
    Leistungskategorie,
    Leistungsnachweis,
    Note,
    Notenschluessel,
    Notenskala,
    Schluesselschwelle,
    Unterricht,
)
from stammdaten.models import (
    Abschnitt,
    Dienstleister,
    Nachweis,
    Nachweisart,
    Personalabwesenheit,
    Personalbereich,
    Zusatzfeld,
    Bildungsgang,
    Elternprofil,
    Fortbildung,
    Gesundheitsangaben,
    Laufbahnabschnitt,
    Notfallkontakt,
    Sprachenfolge,
    VorherigeSchule,
    Beziehung,
    Einwilligung,
    Fach,
    Gruppe,
    Mitgliedschaft,
    Person,
    Personalprofil,
    Schuelerprofil,
    Schuljahr,
)

VORNAMEN = [
    "Amani", "Ben", "Clara", "David", "Elif", "Finn", "Grace", "Hannah", "Imani", "Jonas", "Kiara", "Leon",
    "Malia", "Noah", "Olivia", "Paul", "Rehema", "Samuel", "Tara", "Umar", "Valentina", "Wanjiru", "Yusuf", "Zoe",
    "Aiden", "Baraka", "Charlotte", "Daniel", "Emma", "Felix", "Jabari", "Lena", "Mia", "Nia", "Otieno", "Sophie",
]
VORNAMEN_W = ["Amani", "Clara", "Elif", "Grace", "Hannah", "Imani", "Kiara", "Malia", "Olivia", "Rehema", "Tara",
              "Valentina", "Wanjiru", "Zoe", "Charlotte", "Emma", "Lena", "Mia", "Nia", "Sophie"]
VORNAMEN_M = ["Ben", "David", "Finn", "Jonas", "Leon", "Noah", "Paul", "Samuel", "Umar", "Yusuf", "Aiden", "Baraka",
              "Daniel", "Felix", "Jabari", "Otieno"]
NACHNAMEN = [
    "Achieng", "Bauer", "Chege", "Dietrich", "Engel", "Fischer", "Gitau", "Hoffmann", "Imbuga", "Jung",
    "Kamau", "Lehmann", "Mwangi", "Neumann", "Odhiambo", "Peters", "Ruto", "Schmidt", "Thiong'o", "Ullrich",
    "Vogel", "Wanjiku", "Zimmermann", "Becker", "Kariuki", "Meyer", "Njoroge", "Schulz", "Wagner", "Kiprop",
]
SCHLUESSEL = [
    ("1+", 95), ("1", 90), ("1-", 85), ("2+", 80), ("2", 75), ("2-", 70), ("3+", 65), ("3", 60), ("3-", 55),
    ("4+", 50), ("4", 45), ("4-", 40), ("5+", 33), ("5", 26), ("5-", 20), ("6", 0),
]


class Command(BaseCommand):
    help = "Legt einen Demo-Datensatz mit erfundenen Personen an."

    # Englische Bezeichnungen der Demo-Daten; werden bei Installationen aus Version 0.4 nachgetragen.
    FAECHER_EN = {"D": "German", "E": "English", "M": "Mathematics", "CH": "Chemistry", "BIO": "Biology", "PH": "Physics",
                  "ETH": "Ethics", "REL": "Religious education", "SW": "Kiswahili", "F": "French"}
    ABSCHNITTE_EN = {"1. Halbjahr": "1st semester", "2. Halbjahr": "2nd semester"}
    ZUSATZFELDER_EN = {
        "Schulhaus (House)": {"name_en": "House", "abschnitt_en": "School life"},
        "Instrument": {"name_en": "Instrument", "abschnitt_en": "School life"},
        "Darf allein nach Hause gehen": {"name_en": "May go home alone", "abschnitt_en": "Pick-up",
                                         "hilfetext_en": "Written permission from the parents or guardians must be on file."},
        "Schulgeld-Ermäßigung bis": {"name_en": "School fee reduction until", "abschnitt_en": "Administration"},
        "T-Shirt-Größe": {"name_en": "T-shirt size", "abschnitt_en": "Equipment"},
        "Schlüsselberechtigungen": {"name_en": "Key access", "abschnitt_en": "Equipment",
                                    "optionen_en": "Main building\nScience block\nSports hall\nServer room\nKitchen"},
        "Aufenthaltstitel / Visum": {"name_en": "Residence permit / Visa", "abschnitt_en": "Personnel file"},
        "Bereitschaft zur Mithilfe": {"name_en": "Willing to help with",
                                      "optionen_en": "School fair\nLibrary\nAccompanying trips\nSports day"},
    }

    def englisch_nachtragen(self):
        """Füllt nur leere englische Felder; eigene Eingaben bleiben unangetastet."""
        anzahl = 0

        def ergaenzen(obj, felder):
            nonlocal anzahl
            geaendert = [f for f, wert in felder.items() if not getattr(obj, f) and wert]
            for f in geaendert:
                setattr(obj, f, felder[f])
            if geaendert:
                obj.save(update_fields=geaendert)
                anzahl += len(geaendert)

        for fach in Fach.objects.filter(kuerzel__in=self.FAECHER_EN):
            ergaenzen(fach, {"name_en": self.FAECHER_EN[fach.kuerzel]})
        for abschnitt in Abschnitt.objects.filter(name__in=self.ABSCHNITTE_EN):
            ergaenzen(abschnitt, {"name_en": self.ABSCHNITTE_EN[abschnitt.name]})
        for feld in Zusatzfeld.objects.filter(name__in=self.ZUSATZFELDER_EN):
            ergaenzen(feld, self.ZUSATZFELDER_EN[feld.name])
        return anzahl

    def add_arguments(self, parser):
        parser.add_argument("--passwort", default=os.environ.get("DEMO_PASSWORT", "Schule-Demo-2026"))

    @transaction.atomic
    def handle(self, *args, **opts):
        if Schuljahr.objects.filter(name="2026/27").exists():
            n = self.englisch_nachtragen()
            self.stdout.write(f"Demo-Daten sind bereits vorhanden – {n} englische Bezeichnungen ergänzt.")
            if not User.objects.filter(username="foerderung").exists():
                call_command("grundeinrichtung", stdout=self.stdout)
                self.foerderung_anlegen(opts["passwort"])
                self.stdout.write("Beispiele für Förderung und Anhänge ergänzt.")
            if not User.objects.filter(username="schulleitung").exists():
                call_command("grundeinrichtung", stdout=self.stdout)
                self.rollen_anlegen(opts["passwort"])
                self.stdout.write("Demo-Konten für alle Rollen ergänzt.")
            from portal.models import Notiz

            if not Notiz.objects.exists():
                self.startseite_anlegen()
                self.stdout.write("Beispiele für Notizen und Geburtstage ergänzt.")
            return

        call_command("grundeinrichtung", stdout=self.stdout)
        rng = random.Random(42)
        pw = opts["passwort"]

        sj = Schuljahr.objects.create(name="2026/27", beginn=date(2026, 8, 17), ende=date(2027, 6, 25), aktiv=True)
        hj1 = Abschnitt.objects.create(schuljahr=sj, name="1. Halbjahr", name_en="1st semester", nummer=1, beginn=date(2026, 8, 17), ende=date(2027, 1, 29))
        Abschnitt.objects.create(schuljahr=sj, name="2. Halbjahr", name_en="2nd semester", nummer=2, beginn=date(2027, 2, 1), ende=date(2027, 6, 25))

        raster = [((7, 40), (8, 25)), ((8, 30), (9, 15)), ((9, 35), (10, 20)), ((10, 25), (11, 10)),
                  ((11, 30), (12, 15)), ((12, 20), (13, 5)), ((13, 45), (14, 30)), ((14, 35), (15, 20))]
        for i, (b, e) in enumerate(raster, start=1):
            Stunde.objects.create(schuljahr=sj, nummer=i, beginn=time(*b), ende=time(*e))

        faecher = {}
        for i, (k, n, en) in enumerate([("D", "Deutsch", "German"), ("E", "Englisch", "English"), ("M", "Mathematik", "Mathematics"),
                                        ("CH", "Chemie", "Chemistry"), ("BIO", "Biologie", "Biology"), ("PH", "Physik", "Physics"),
                                        ("ETH", "Ethik", "Ethics"), ("REL", "Religion", "Religious education"),
                                        ("SW", "Kiswahili", "Kiswahili"), ("F", "Französisch", "French")]):
            faecher[k], _ = Fach.objects.get_or_create(kuerzel=k, defaults={"name": n, "name_en": en, "reihenfolge": (i + 1) * 10})

        # Frühere Schuljahre (für die Schullaufbahn)
        sj_alt = {
            2024: Schuljahr.objects.create(name="2024/25", beginn=date(2024, 8, 19), ende=date(2025, 6, 27)),
            2025: Schuljahr.objects.create(name="2025/26", beginn=date(2025, 8, 18), ende=date(2026, 6, 26)),
        }
        bg = {b.kuerzel: b for b in Bildungsgang.objects.all()}

        # Personal aller Bereiche mit Personalakte
        bereich = {b.kuerzel: b for b in Personalbereich.objects.all()}
        heute = timezone.localdate()
        sicherheitsfirma = Dienstleister.objects.create(
            name="SafeGuard Security Ltd.", leistung="Sicherheitsdienst (Tor, Nachtwache)", ansprechperson="John Mutua",
            telefon="+254 711 000 111", vertrag_bis=date(2027, 7, 31))
        reinigungsfirma = Dienstleister.objects.create(
            name="CleanPro Kenya", leistung="Gebäudereinigung", ansprechperson="Agnes Wairimu",
            telefon="+254 722 000 222", vertrag_bis=date(2026, 12, 31))

        def personal(vorname, nachname, bereich_k, stelle="", kuerzel=None, benutzername=None, rolle="Lehrer:in",
                     anstellung="ortskraft", faecher_k=(), stunden=None, beginn=2022, funktionen="", anrede="Frau",
                     firma=None, schicht="", nachweise="vollstaendig"):
            user = None
            if benutzername:
                user = User.objects.create_user(benutzername, password=pw, is_staff=True, first_name=vorname, last_name=nachname)
                user.groups.add(Group.objects.get(name=rolle))
            p = Person.objects.create(anrede=anrede, vorname=vorname, nachname=nachname,
                                      email=f"{vorname.lower()}.{nachname.lower()}@privat.example",
                                      mobil=f"+254 7{rng.randint(10, 99)} {rng.randint(100, 999)} {rng.randint(100, 999)}",
                                      ort="Nairobi", benutzer=user)
            pp = Personalprofil.objects.create(
                person=p, bereich=bereich[bereich_k], stellenbezeichnung=stelle, kuerzel=kuerzel,
                personalnummer=f"P-{rng.randint(1000, 9999)}" if not firma else "",
                anstellungsart="dienstleister" if firma else anstellung, dienstleister=firma, dienstbeginn=date(beginn, 8, 1),
                vertragsende=date(beginn + 6, 7, 31) if anstellung in {"adlk", "bplk"} else None,
                wochenstunden=stunden, weitere_funktionen=funktionen, arbeitszeit=schicht,
                dienst_email=f"{(kuerzel or vorname).lower()}@schule.example" if not firma else "",
                arbeitserlaubnis_bis=date(beginn + 3, 7, 31) if anstellung in {"adlk", "bplk", "lplk"} else None,
                ausweisnummer=f"DSN-{rng.randint(100, 999)}",
            )
            pp.lehrbefaehigungen.set([faecher[k] for k in faecher_k])
            Notfallkontakt.objects.create(personal=pp, name=f"{rng.choice(VORNAMEN)} {nachname}", beziehung="Partner:in",
                                          telefon=f"+254 7{rng.randint(10, 99)} {rng.randint(100, 999)} {rng.randint(100, 999)}")
            # Nachweise: vollständig, eines läuft bald ab, eines abgelaufen oder fehlt
            for art in pp.bereich.pflichtnachweise.all():
                if nachweise == "fehlt" and art.name.startswith("Polizeiliches"):
                    continue
                ausgestellt = heute - timedelta(days=rng.randint(30, 300))
                if nachweise == "abgelaufen" and art.name.startswith("Erste"):
                    ausgestellt = heute - timedelta(days=800)  # 24 Monate gültig -> abgelaufen
                if nachweise == "laeuft_ab" and art.name.startswith("Kinderschutz"):
                    ausgestellt = heute - timedelta(days=700)  # läuft in gut einem Monat ab
                Nachweis.objects.create(personal=pp, art=art, ausgestellt_am=ausgestellt)
            if pp.ist_lehrkraft:
                Fortbildung.objects.create(personal=pp, titel="Sprachsensibler Fachunterricht", anbieter="ZfA Region Afrika",
                                           datum=date(2025, 11, rng.randint(3, 28)), umfang_stunden=Decimal(12), nachweis_liegt_vor=True)
            return pp

        kro = personal("Martin", "Krause", "LK", "Lehrkraft Chemie/Biologie", "KRA", benutzername="lehrkraft", anstellung="adlk",
                       faecher_k=("CH", "BIO"), stunden=Decimal(25), beginn=2024, funktionen="Fachleitung Naturwissenschaften", anrede="Herr")
        mue = personal("Sabine", "Müller", "LK", "Lehrkraft Mathematik/Physik", "MUE", anstellung="bplk", faecher_k=("M", "PH"),
                       stunden=Decimal(26), beginn=2021, nachweise="laeuft_ab")
        sch = personal("Thomas", "Schwarz", "LK", "Lehrkraft Deutsch/Englisch", "SCH", anstellung="adlk", faecher_k=("D", "E"),
                       stunden=Decimal(23), beginn=2021, anrede="Herr")
        oko = personal("Grace", "Okoth", "LK", "Lehrkraft Ethik/Englisch", "OKO", anstellung="olk", faecher_k=("ETH", "E", "SW"),
                       stunden=Decimal(20), beginn=2019)
        bra = personal("Peter", "Brandt", "LK", "Lehrkraft Religion/Deutsch", "BRA", anstellung="lplk", faecher_k=("REL", "D"),
                       stunden=Decimal(26), beginn=2025, anrede="Herr")
        personal("Mercy", "Wambui", "VERW", "Schulsekretärin", benutzername="verwaltung", rolle="Sekretariat",
                 stunden=Decimal(40), beginn=2018, schicht="Mo–Fr 7:00–15:30")
        hr_leitung = personal("Esther", "Njeri", "HR", "HR-Managerin", benutzername="personal", rolle="HR-Management",
                              stunden=Decimal(40), beginn=2020)
        fm = personal("Joseph", "Ochieng", "FAC", "Facility Manager", stunden=Decimal(45), beginn=2017, anrede="Herr",
                      schicht="Mo–Fr 6:30–15:30")
        personal("Kevin", "Mutiso", "FAC", "Haustechniker", stunden=Decimal(45), beginn=2022, anrede="Herr", schicht="Mo–Fr 7:00–16:00")
        personal("Daniel", "Kimani", "IT", "IT-Administrator", stunden=Decimal(40), beginn=2023, anrede="Herr")
        personal("Lucy", "Akinyi", "FIN", "Buchhalterin", stunden=Decimal(40), beginn=2016)
        for vn, nn, schicht, nw in [("Peter", "Kiprono", "Tagschicht 6–18 Uhr, Haupttor", "vollstaendig"),
                                    ("Samuel", "Wekesa", "Nachtschicht 18–6 Uhr", "abgelaufen"),
                                    ("Ruth", "Chebet", "Tagschicht 6–18 Uhr, Eingang Kindergarten", "fehlt")]:
            personal(vn, nn, "SICH", "Sicherheitskraft", firma=sicherheitsfirma, stunden=Decimal(60), beginn=2024,
                     anrede="Frau" if vn == "Ruth" else "Herr", schicht=schicht, nachweise=nw)
        for vn, nn in [("Mary", "Atieno"), ("Jane", "Wanjiru"), ("Rose", "Nduta")]:
            personal(vn, nn, "REIN", "Reinigungskraft", firma=reinigungsfirma, stunden=Decimal(45), beginn=2025, schicht="Mo–Fr 14–20 Uhr")
        personal("Alice", "Muthoni", "KUE", "Köchin Cafeteria", stunden=Decimal(45), beginn=2019)
        personal("George", "Omondi", "TRANS", "Busfahrer Linie 1", stunden=Decimal(40), beginn=2021, anrede="Herr", nachweise="abgelaufen")
        personal("Faith", "Wairimu", "GES", "Schulkrankenschwester", stunden=Decimal(40), beginn=2020)
        coach_fb = personal("Brian", "Otieno", "NACHM", "Fußballcoach", anstellung="honorar", stunden=Decimal(6), beginn=2024,
                            anrede="Herr", schicht="Di + Do 14:45–16:15")
        coach_sw = personal("Nicole", "Achieng", "NACHM", "Schwimmcoach", anstellung="honorar", stunden=Decimal(4), beginn=2025,
                            schicht="Mi 14:45–16:15")
        Nachweis.objects.create(personal=coach_sw, art=Nachweisart.objects.get(name__startswith="Rettungsschwimmer"),
                                ausgestellt_am=heute - timedelta(days=120))
        for pp in Personalprofil.objects.exclude(pk=hr_leitung.pk).filter(bereich__kuerzel__in=["FAC", "IT", "REIN", "SICH"]):
            if pp.bereich.kuerzel in {"FAC", "IT"}:
                pp.vorgesetzt = fm if pp != fm else hr_leitung
                pp.save(update_fields=["vorgesetzt"])

        # Personalabwesenheiten
        Personalabwesenheit.objects.create(personal=sch, art="fortbildung", von=heute, bis=heute + timedelta(days=2), bemerkung="Regionale Fortbildung")
        Personalabwesenheit.objects.create(personal=fm, art="krank", von=heute - timedelta(days=1), bis=heute + timedelta(days=1))
        Personalabwesenheit.objects.create(personal=mue, art="urlaub", von=date(2026, 12, 14), bis=date(2026, 12, 18), status="beantragt")

        # Beispiel-Zusatzfelder (frei definierbar unter Stammdaten › Zusatzfelder)
        Zusatzfeld.objects.create(zielgruppe="schueler", name="Schulhaus (House)", name_en="House", typ="auswahl",
                                  optionen="Kilimanjaro\nKenya\nElgon\nMeru", abschnitt="Schulleben", abschnitt_en="School life",
                                  sichtbarkeit="alle", in_liste=True, reihenfolge=10)
        Zusatzfeld.objects.create(zielgruppe="schueler", name="Instrument", name_en="Instrument", typ="text", abschnitt="Schulleben",
                                  abschnitt_en="School life", sichtbarkeit="alle", reihenfolge=20)
        Zusatzfeld.objects.create(zielgruppe="schueler", name="Darf allein nach Hause gehen", name_en="May go home alone", typ="janein",
                                  abschnitt="Abholung", abschnitt_en="Pick-up", sichtbarkeit="alle", reihenfolge=10,
                                  hilfetext="Schriftliche Erlaubnis der Erziehungsberechtigten muss vorliegen.",
                                  hilfetext_en="Written permission from the parents or guardians must be on file.")
        Zusatzfeld.objects.create(zielgruppe="schueler", name="Schulgeld-Ermäßigung bis", name_en="School fee reduction until", typ="datum",
                                  abschnitt="Verwaltung", abschnitt_en="Administration", sichtbarkeit="verwaltung", reihenfolge=10)
        Zusatzfeld.objects.create(zielgruppe="personal", name="T-Shirt-Größe", name_en="T-shirt size", typ="auswahl", optionen="S\nM\nL\nXL\nXXL",
                                  abschnitt="Ausstattung", abschnitt_en="Equipment", sichtbarkeit="verwaltung", reihenfolge=10)
        Zusatzfeld.objects.create(zielgruppe="personal", name="Schlüsselberechtigungen", name_en="Key access", typ="mehrfach",
                                  optionen="Hauptgebäude\nNaturwissenschaften\nSporthalle\nServerraum\nKüche",
                                  optionen_en="Main building\nScience block\nSports hall\nServer room\nKitchen",
                                  abschnitt="Ausstattung", abschnitt_en="Equipment", sichtbarkeit="verwaltung", in_liste=True, reihenfolge=20)
        Zusatzfeld.objects.create(zielgruppe="personal", name="Aufenthaltstitel / Visum", name_en="Residence permit / Visa", typ="text",
                                  abschnitt="Personalakte", abschnitt_en="Personnel file", sichtbarkeit="hr", reihenfolge=10)
        Zusatzfeld.objects.create(zielgruppe="eltern", name="Bereitschaft zur Mithilfe", name_en="Willing to help with", typ="mehrfach",
                                  optionen="Schulfest\nBibliothek\nAusflugsbegleitung\nSportfest",
                                  optionen_en="School fair\nLibrary\nAccompanying trips\nSports day", sichtbarkeit="verwaltung")
        schluessel_opt = ["Hauptgebäude", "Naturwissenschaften", "Sporthalle", "Serverraum", "Küche"]
        for pp in Personalprofil.objects.all():
            pp.zusatzfelder = {"t_shirt_groesse": rng.choice(["S", "M", "L", "XL"]),
                               "schluesselberechtigungen": rng.sample(schluessel_opt, k=rng.randint(1, 3))}
            pp.save(update_fields=["zusatzfelder"])

        # Klassen und Schüler:innen
        klassen = {
            "8a": (8, mue, 10), "9a": (9, kro, 13), "9b": (9, sch, 12),
        }
        gruppen, nr = {}, 2026000
        namen_pool = [(v, n) for v in VORNAMEN for n in NACHNAMEN]
        rng.shuffle(namen_pool)
        for name, (jg, leitung, anzahl) in klassen.items():
            g = Gruppe.objects.create(schuljahr=sj, typ=Gruppe.STAMMKLASSE, name=name, kuerzel=name, jahrgang=jg, leitung=leitung)
            gruppen[name] = g
            for _ in range(anzahl):
                vorname, nachname = namen_pool.pop()
                nr += 1
                geb = date(2026 - jg - 6, rng.randint(1, 12), rng.randint(1, 28))
                geschlecht = rng.choice(["w", "m"])
                p = Person.objects.create(
                    vorname=vorname, nachname=nachname, geburtsdatum=geb, geschlecht=geschlecht, ort="Nairobi",
                    strasse=f"{rng.choice(['Runda', 'Kitisuru', 'Gigiri', 'Lavington', 'Karen'])} Estate, House {rng.randint(1, 80)}",
                    postfach=f"P.O. Box {rng.randint(10000, 99999)}-00100", geburtsort=rng.choice(["Nairobi", "Berlin", "München", "Mombasa", "Hamburg"]),
                    staatsangehoerigkeiten=rng.choice(["deutsch", "kenianisch", "deutsch, kenianisch", "österreichisch", "deutsch, britisch"]),
                )
                eintritt_jg = rng.choice([1, 1, 1, 5, jg - 1])
                s = Schuelerprofil.objects.create(
                    person=p, schuelernummer=str(nr), eintrittsdatum=date(2026 - (jg - eintritt_jg), 8, 15), eintritt_jahrgang=eintritt_jg,
                    muttersprache=rng.choice(["Deutsch", "Deutsch", "Englisch", "Kiswahili, Englisch", "Deutsch, Englisch"]),
                    familiensprache=rng.choice(["Deutsch", "Deutsch, Englisch", "Englisch"]),
                    daz=rng.random() < 0.15, nachteilsausgleich=rng.random() < 0.08,
                    religionsunterricht=rng.choice(["ev", "kath", "ethik"]),
                    lebt_bei="beiden Eltern", schulweg=rng.choice(["bus", "abgeholt", "abgeholt"]),
                )
                if s.schulweg == "bus":
                    s.buslinie = f"Linie {rng.randint(1, 6)}"
                    s.save(update_fields=["buslinie"])
                Mitgliedschaft.objects.create(gruppe=g, schueler=s, von=sj.beginn)

                # Schullaufbahn: zwei Vorjahre + aktuelles Jahr
                bildungsgang = rng.choices(["GYM", "RS", "HS"], weights=[70, 20, 10])[0]
                wechsel = bildungsgang == "GYM" and rng.random() < 0.12  # Aufstieg RS -> GYM
                for jahr, schuljahr in sj_alt.items():
                    jg_damals = jg - (2026 - jahr)
                    if jg_damals < eintritt_jg:
                        continue
                    bg_damals = "RS" if wechsel and jahr == 2024 else bildungsgang
                    ergebnis = "wechsel" if wechsel and jahr == 2024 else "versetzt"
                    Laufbahnabschnitt.objects.create(
                        schueler=s, schuljahr=schuljahr, jahrgang=jg_damals, bildungsgang=bg[bg_damals], ergebnis=ergebnis,
                        bemerkung="Wechsel in den gymnasialen Bildungsgang (Konferenzbeschluss)" if ergebnis == "wechsel" else "",
                    )
                Laufbahnabschnitt.objects.create(schueler=s, schuljahr=sj, jahrgang=jg, bildungsgang=bg[bildungsgang], stammklasse=g)
                Sprachenfolge.objects.create(schueler=s, position=1, fach=faecher["E"], ab_jahrgang=1 if eintritt_jg <= 3 else 5)
                if bildungsgang == "GYM":
                    Sprachenfolge.objects.create(schueler=s, position=2, fach=rng.choice([faecher["F"], faecher["SW"]]), ab_jahrgang=6)
                if eintritt_jg > 1:
                    VorherigeSchule.objects.create(
                        schueler=s, name=rng.choice(["Hillcrest School", "Grundschule am See", "Brookhouse School", "Peponi School"]),
                        ort=rng.choice(["Nairobi", "Hamburg", "Karen"]), land=rng.choice(["Kenia", "Deutschland"]),
                        letzter_jahrgang=str(eintritt_jg - 1), schulform=rng.choice(["CBC (KE)", "Grundschule (DE)", "British Curriculum"]),
                    )
                if rng.random() < 0.25:
                    Gesundheitsangaben.objects.create(
                        schueler=s, allergien=rng.choice(["Erdnüsse", "Bienenstiche", "Laktose", "Pollen"]),
                        medikamente=rng.choice(["", "Notfallset (Adrenalin-Pen) im Sekretariat", "Asthmaspray"]),
                        arzt="Dr. Kamau, +254 20 123 4567", krankenversicherung=rng.choice(["AAR", "Jubilee", "Allianz Care"]),
                    )
                eltern = []
                for art, vn in [("mutter", rng.choice(VORNAMEN_W)), ("vater", rng.choice(VORNAMEN_M))][: rng.choice([1, 2, 2])]:
                    e = Person.objects.create(
                        anrede="Frau" if art == "mutter" else "Herr", vorname=vn, nachname=nachname,
                        email=f"{vn.lower()}.{nachname.lower().replace(chr(39), '')}@eltern.example",
                        mobil=f"+254 7{rng.randint(10, 99)} {rng.randint(100, 999)} {rng.randint(100, 999)}",
                        strasse=p.strasse, postfach=p.postfach, ort="Nairobi",
                        sprache=rng.choice(["de", "de", "en"]),
                    )
                    Elternprofil.objects.create(
                        person=e, beruf=rng.choice(["Diplomatin", "Ingenieur", "Ärztin", "Lehrer", "Projektleiterin", "Unternehmer", "Journalistin"]),
                        arbeitgeber=rng.choice(["Deutsche Botschaft", "GIZ", "UN-Habitat", "UNEP", "Safaricom", "selbstständig", ""]),
                        korrespondenzweg=rng.choice(["email", "email", "app"]), schulverein_mitglied=rng.random() < 0.7,
                        kontaktdaten_weitergabe=rng.random() < 0.6,
                    )
                    Beziehung.objects.create(schueler=s, person=e, art=art, notfallkontakt=not eltern, rechnungsempfaenger=not eltern)
                    eltern.append(e)
                if rng.random() < 0.8:
                    Einwilligung.objects.create(schueler=s, zweck="foto_intern", erteilt_durch=eltern[0], erteilt_am=date(2026, 8, 20))

        # Lerngruppen Ethik / Religion aus 9a + 9b
        ethik = Gruppe.objects.create(schuljahr=sj, typ=Gruppe.LERNGRUPPE, name="Ethik 9", jahrgang=9, leitung=oko)
        reli = Gruppe.objects.create(schuljahr=sj, typ=Gruppe.LERNGRUPPE, name="Religion 9", jahrgang=9, leitung=bra)
        for lg in (ethik, reli):
            lg.gebildet_aus.set([gruppen["9a"], gruppen["9b"]])
        for k in ("9a", "9b"):
            for s in gruppen[k].aktuelle_mitglieder(stichtag=sj.beginn):
                Mitgliedschaft.objects.create(gruppe=rng.choice([ethik, reli]), schueler=s, von=sj.beginn)

        # Noten-Grundlagen
        sek1 = Notenskala.objects.get(name__startswith="Sek I –")
        schluessel = Notenschluessel.objects.create(
            name="Beispielschlüssel Sek I (bitte durch DSN-Schlüssel ersetzen)", skala=sek1,
            beschreibung="Nur zu Demonstrationszwecken.",
        )
        stufen = {s.bezeichnung: s for s in sek1.stufen.all()}
        for b, ab in SCHLUESSEL:
            Schluesselschwelle.objects.create(schluessel=schluessel, min_prozent=Decimal(ab), stufe=stufen[b])

        nawi = Gewichtungsvorlage.objects.create(name="Naturwissenschaften Sek I", beschreibung="Beispiel: 50 % schriftlich, 50 % sonstige Leistungen")
        Leistungskategorie.objects.create(vorlage=nawi, name="Schriftlich", anteil=Decimal(50))
        Leistungskategorie.objects.create(vorlage=nawi, name="Sonstige Mitarbeit", anteil=Decimal(50))
        haupt = Gewichtungsvorlage.objects.create(name="Hauptfächer Sek I", beschreibung="Beispiel: 60 % schriftlich, 40 % sonstige")
        Leistungskategorie.objects.create(vorlage=haupt, name="Schriftlich", anteil=Decimal(60))
        Leistungskategorie.objects.create(vorlage=haupt, name="Sonstige Leistungen", anteil=Decimal(40))

        def unterricht(gruppe, fach, lehrkraft, vorlage=nawi):
            return Unterricht.objects.create(abschnitt=hj1, gruppe=gruppe, fach=faecher[fach], lehrkraft=lehrkraft, skala=sek1, gewichtung=vorlage)

        ch9a = unterricht(gruppen["9a"], "CH", kro)
        ch9b = unterricht(gruppen["9b"], "CH", kro)
        unterricht(gruppen["9a"], "BIO", kro)
        unterricht(gruppen["9a"], "M", mue, haupt)
        unterricht(gruppen["9a"], "D", sch, haupt)
        unterricht(ethik, "ETH", oko)
        unterricht(reli, "REL", bra)

        # Beispielnoten in Chemie 9a und 9b
        # Ordnerstruktur: Schriftlich (50) | Sonstige Mitarbeit (50) › Quartal 1 (1), Quartal 2 (1)
        for u in (ch9a, ch9b):
            schriftlich = u.bewertungsordner.get(name="Schriftlich", eltern=None)
            mitarbeit = u.bewertungsordner.get(name="Sonstige Mitarbeit", eltern=None)
            q1 = Bewertungsordner.objects.create(unterricht=u, eltern=mitarbeit, name="Quartal 1", gewicht=1, reihenfolge=10)
            Bewertungsordner.objects.create(unterricht=u, eltern=mitarbeit, name="Quartal 2", gewicht=1, reihenfolge=20)
            ka = Leistungsnachweis.objects.create(ordner=schriftlich, titel="1. Klassenarbeit", datum=date(2026, 9, 24), schluessel=schluessel, max_be=Decimal(40))
            test = Leistungsnachweis.objects.create(ordner=schriftlich, titel="Test Atombau", datum=date(2026, 10, 8), gewicht=Decimal("0.5"), schluessel=schluessel, max_be=Decimal(20))
            muendl = Leistungsnachweis.objects.create(ordner=q1, titel="Mitarbeit September", datum=date(2026, 9, 30))
            prot = Leistungsnachweis.objects.create(ordner=q1, titel="Protokoll Flammenfärbung", datum=date(2026, 10, 2), gewicht=Decimal("0.5"))
            muendlich_stufen = [s for s in sek1.stufen.all() if s.bezeichnung in {"1", "1-", "2+", "2", "2-", "3+", "3", "3-", "4", "4-", "5"}]
            for i, s in enumerate(u.schueler()):
                staerke = rng.gauss(0.68, 0.15) if i else 0.30  # erste Person: Gefährdungsbeispiel
                for ln in (ka, test):
                    if ln is ka and i == 3:
                        Note.objects.create(leistungsnachweis=ln, schueler=s, sonderstatus="entschuldigt", kommentar="Attest liegt vor")
                        continue
                    anteil = min(max(rng.gauss(staerke, 0.08), 0.05), 1)
                    Note.objects.create(leistungsnachweis=ln, schueler=s, erreichte_be=(ln.max_be * Decimal(str(round(anteil, 3)))).quantize(Decimal("0.5")))
                for ln in (muendl, prot):
                    idx = min(max(int(rng.gauss((1 - staerke) * len(muendlich_stufen), 1.5)), 0), len(muendlich_stufen) - 1)
                    Note.objects.create(leistungsnachweis=ln, schueler=s, stufe=muendlich_stufen[idx])

        # Fehlzeiten
        alle = list(Schuelerprofil.objects.all())
        sekretariat = User.objects.get(username="verwaltung")
        start_tag = date(2026, 9, 1)
        for _ in range(40):
            s = rng.choice(alle)
            tag = start_tag + timedelta(days=rng.randint(0, 40))
            while tag.weekday() >= 5:
                tag += timedelta(days=1)
            art = rng.choice([Fehlzeit.GANZTAEGIG, Fehlzeit.GANZTAEGIG, Fehlzeit.STUNDEN, Fehlzeit.VERSPAETUNG])
            fz = Fehlzeit(schueler=s, art=art, datum_von=tag, erfasst_von=sekretariat,
                          status=rng.choice(["entschuldigt", "entschuldigt", "unentschuldigt", "offen"]),
                          quelle=rng.choice(["lehrkraft", "eltern", "sekretariat"]))
            if art == Fehlzeit.GANZTAEGIG:
                fz.datum_bis = tag + timedelta(days=rng.choice([0, 0, 1, 2]))
                fz.grund = rng.choice(["Krankheit", "Arzttermin", "Familiäre Gründe", ""])
            elif art == Fehlzeit.STUNDEN:
                fz.stunde_von = rng.randint(1, 5)
                fz.stunde_bis = fz.stunde_von + rng.randint(0, 2)
                fz.grund = rng.choice(["Arzttermin", "Unwohlsein", ""])
            else:
                fz.minuten = rng.choice([5, 10, 15, 25])
                fz.grund = rng.choice(["Verkehr", "Bus verspätet", ""])
            fz.full_clean()
            fz.save()

        # Nachmittagsprogramm mit Wünschen und Losverfahren
        ags = [
            AGAngebot.objects.create(abschnitt=hj1, titel="Robotik", leitung=kro, wochentag=1, beginn=time(14, 45), ende=time(16, 15), raum="NW-Labor", kapazitaet=8, jahrgang_min=7, jahrgang_max=10),
            AGAngebot.objects.create(abschnitt=hj1, titel="Theater", leitung=sch, wochentag=2, beginn=time(14, 45), ende=time(16, 15), raum="Aula", kapazitaet=12),
            AGAngebot.objects.create(abschnitt=hj1, titel="Fußball", leitung=coach_fb, wochentag=3, beginn=time(14, 45), ende=time(16, 15), raum="Sportplatz", kapazitaet=14),
            AGAngebot.objects.create(abschnitt=hj1, titel="Chor", leitung=bra, wochentag=0, beginn=time(14, 45), ende=time(15, 45), raum="Musikraum", kapazitaet=10),
        ]
        beliebtheit = [5, 2, 3, 1]
        for s in alle:
            wahl = []
            pool = list(ags)
            gewichte = list(beliebtheit)
            for prio in (1, 2, 3):
                a = rng.choices(pool, weights=gewichte)[0]
                i = pool.index(a)
                pool.pop(i)
                gewichte.pop(i)
                wahl.append(AGWahl(schueler=s, angebot=a, prioritaet=prio))
            AGWahl.objects.bulk_create(wahl)
        ergebnis = lose_zuteilen(hj1, seed=7)

        for s_ in Schuelerprofil.objects.all():
            s_.zusatzfelder = {"schulhaus_house": rng.choice(["Kilimanjaro", "Kenya", "Elgon", "Meru"]),
                               "darf_allein_nach_hause_gehen": rng.random() < 0.3}
            if rng.random() < 0.3:
                s_.zusatzfelder["instrument"] = rng.choice(["Klavier", "Gitarre", "Geige", "Schlagzeug"])
            s_.save(update_fields=["zusatzfelder"])

        self.foerderung_anlegen(pw)
        self.startseite_anlegen()
        self.rollen_anlegen(pw)

        self.stdout.write(self.style.SUCCESS(
            f"Demo-Daten angelegt: {len(alle)} Schüler:innen, {Person.objects.count()} Personen, "
            f"{Fehlzeit.objects.count()} Fehlzeiten, AG-Zuteilung {ergebnis.zugeteilt} "
            f"({len(ergebnis.ohne_platz)} ohne Platz)."
        ))
        self.stdout.write(f"Demo-Konten: 'lehrkraft' (Klassenleitung 9a, Chemie), 'verwaltung' (Sekretariat), "
                          f"'personal' (HR), 'foerderung' (Förderkoordination), 'mittelstufe', 'oberstufe', 'schulleitung', "
                          f"'verwaltungsleitung', 'finanzen' – Passwort: {pw}")

    # ------------------------------------------------------------ Förderung und Anhänge (ab Version 0.4.2.0)
    def foerderung_anlegen(self, pw):
        from django.core.files.base import ContentFile

        from foerderung.models import (
            Aushaendigung, Ausgleichsmassnahme, Foerdereintrag, Foerderplan, Foerderschwerpunkt, Foerderziel, Nachteilsausgleich,
        )
        from stammdaten.models import Dokument

        heute = timezone.localdate()
        sj = Schuljahr.objects.get(name="2026/27")
        kl9a = Gruppe.objects.get(schuljahr=sj, name="9a")
        kl9b = Gruppe.objects.get(schuljahr=sj, name="9b")
        kro, sch = kl9a.leitung, kl9b.leitung
        lehrkraft = User.objects.get(username="lehrkraft")

        # Förderkoordination: Thomas Schwarz (zugleich Klassenleitung 9b)
        konto = User.objects.create_user("foerderung", password=pw, is_staff=True, first_name="Thomas", last_name="Schwarz")
        konto.groups.add(Group.objects.get(name="Förderkoordination"), Group.objects.get(name="Lehrer:in"))
        sch.person.benutzer = konto
        sch.person.save(update_fields=["benutzer"])
        sch.weitere_funktionen = "Förderkoordination"
        sch.save(update_fields=["weitere_funktionen"])

        sp = {f.name: f for f in Foerderschwerpunkt.objects.all()}
        ma = {m.name: m for m in Ausgleichsmassnahme.objects.all()}
        fach = {f.kuerzel: f for f in Fach.objects.all()}
        s9a = list(kl9a.aktuelle_mitglieder().order_by("person__nachname"))
        s9b = list(kl9b.aktuelle_mitglieder().order_by("person__nachname"))

        def elternteil(s):
            b = s.beziehungen.filter(sorgerecht=True).select_related("person").first()
            return b.person if b else None

        # 1) Lesen und Rechtschreiben, 9a: Plan aktiv, Eltern haben bestätigt; Nachteilsausgleich mit Notenschutz
        a = s9a[1]
        plan = Foerderplan.objects.create(
            schueler=a, schuljahr=sj, titel="Lesen und Rechtschreiben", status=Foerderplan.AKTIV,
            gueltig_von=date(2026, 9, 1), gueltig_bis=date(2027, 1, 29), evaluation_am=date(2027, 1, 15),
            verantwortlich=kro, erstellt_von=lehrkraft,
            ausgangslage="Lesetempo deutlich unter Klassenniveau; viele Fehler bei Dehnung und Doppelkonsonanten. "
                         "Mündlich sehr sicher und engagiert.",
            staerken="Sehr gutes Sachwissen in den Naturwissenschaften, hilfsbereit, arbeitet gern in Gruppen.",
            grundlagen="Gutachten Kinder- und Jugendpsychiatrie (Nairobi) vom 12.05.2026; HSP 7-9 im September 2026.",
            vereinbarungen="Wöchentlich 20 Minuten Lesetraining zu Hause; Nutzung der Rechtschreibkartei im Unterricht.",
        )
        plan.schwerpunkte.set([sp["Lesen und Rechtschreiben"]])
        plan.beteiligte.set([sch])
        Foerderziel.objects.create(plan=plan, fach=fach["D"], reihenfolge=1,
                                   ziel="Liest einen unbekannten Sachtext (ca. 250 Wörter) in höchstens 3 Minuten und beantwortet 4 von 5 Verständnisfragen.",
                                   massnahmen="Lautlesetandem zweimal pro Woche; Lesestrategien (Überschriften, Schlüsselwörter).",
                                   zustaendig="Deutschlehrkraft, Eltern", bis=date(2027, 1, 15))
        Foerderziel.objects.create(plan=plan, bereich="Rechtschreibung", reihenfolge=2,
                                   ziel="Wendet die Regeln zu Dehnung und Schärfung in eigenen Texten zu 80 % richtig an.",
                                   massnahmen="Rechtschreibkartei, Fehleranalyse nach jeder Klassenarbeit.",
                                   zustaendig="Deutschlehrkraft, Schüler:in", bis=date(2027, 1, 15), ergebnis=Foerderziel.TEILWEISE,
                                   bewertung="Deutliche Fortschritte bei Doppelkonsonanten, Dehnung noch unsicher.")
        for tage, art, text, wer in [
            (40, "gespraech_eltern", "Elterngespräch zur Vorstellung des Förderplans; Eltern unterstützen das Lesetraining.", lehrkraft),
            (21, "beobachtung", "Liest im Chemieunterricht Arbeitsaufträge inzwischen selbstständig; braucht etwas mehr Zeit.", lehrkraft),
            (7, "massnahme", "Lautlesetandem gestartet (Partnerin aus der Klasse).", konto),
        ]:
            Foerdereintrag.objects.create(schueler=a, plan=plan, datum=heute - timedelta(days=tage), art=art, text=text, verfasst_von=wer)
        mutter = elternteil(a)
        if mutter:
            Aushaendigung.objects.create(foerderplan=plan, empfaenger=mutter, ausgehaendigt_am=date(2026, 9, 3), weg="gespraech",
                                         bestaetigt_am=date(2026, 9, 7), bestaetigung="unterschrift", erfasst_von=lehrkraft,
                                         bestaetigt_durch_konto=lehrkraft)
        nta = Nachteilsausgleich.objects.create(
            schueler=a, begruendung="Lese-Rechtschreib-Schwierigkeit laut Gutachten vom 12.05.2026; Beschluss der Klassenkonferenz.",
            zeitverlaengerung=25, gueltig_von=date(2026, 9, 1), gueltig_bis=date(2027, 7, 31), status=Nachteilsausgleich.GENEHMIGT,
            beschlossen_am=date(2026, 8, 28), beschlossen_durch="Klassenkonferenz 9a", foerderplan=plan, erstellt_von=konto,
        )
        nta.massnahmen.set([ma["Rechtschreibung wird nicht bewertet"], ma["Vorlesen der Aufgabenstellung"]])
        nta.faecher.set([fach["D"], fach["E"]])
        nta.schwerpunkte.set([sp["Lesen und Rechtschreiben"]])
        if mutter:
            Aushaendigung.objects.create(nachteilsausgleich=nta, empfaenger=mutter, ausgehaendigt_am=heute - timedelta(days=5),
                                         weg="email", erfasst_von=konto)

        # 2) Aufmerksamkeit, 9a: Plan aktiv, noch nicht ausgehändigt, Evaluation bald; Nachteilsausgleich beantragt
        b = s9a[4]
        plan2 = Foerderplan.objects.create(
            schueler=b, schuljahr=sj, titel="Arbeitsorganisation", status=Foerderplan.AKTIV,
            gueltig_von=heute - timedelta(days=30), evaluation_am=heute + timedelta(days=9), verantwortlich=kro, erstellt_von=lehrkraft,
            ausgangslage="Verliert bei längeren Arbeitsphasen den Faden; Hausaufgaben häufig unvollständig.",
            staerken="Kreativ, gute Ideen im Experimentalunterricht.",
        )
        plan2.schwerpunkte.set([sp["Aufmerksamkeit und Konzentration"], sp["Arbeits- und Lernverhalten"]])
        Foerderziel.objects.create(plan=plan2, bereich="Arbeitsverhalten", reihenfolge=1,
                                   ziel="Notiert alle Hausaufgaben im Planer und hakt sie ab (Kontrolle freitags durch die Klassenleitung).",
                                   massnahmen="Wochenplaner, kurze Rückmeldung am Freitag.", zustaendig="Klassenleitung, Eltern")
        n2 = Nachteilsausgleich.objects.create(
            schueler=b, begruendung="Beobachtungen der Fachlehrkräfte; ärztliche Stellungnahme wird nachgereicht.",
            gueltig_von=heute, status=Nachteilsausgleich.BEANTRAGT, erstellt_von=lehrkraft)
        n2.massnahmen.set([ma["Separater, ruhiger Raum"], ma["Zusätzliche Pausen"]])

        # 3) DaZ, 9b: Nachteilsausgleich läuft bald ab, Erhalt bestätigt
        c = s9b[2]
        plan3 = Foerderplan.objects.create(
            schueler=c, schuljahr=sj, titel="Deutsch als Zweitsprache", status=Foerderplan.AKTIV,
            gueltig_von=date(2026, 8, 17), evaluation_am=date(2027, 1, 20), verantwortlich=sch, erstellt_von=konto,
            ausgangslage="Seit März 2026 an der Schule; Deutsch auf Niveau A2, Englisch sehr gut.",
            staerken="Sehr gute Mathematikkenntnisse, schnelle Auffassungsgabe.",
        )
        plan3.schwerpunkte.set([sp["Deutsch als Zweitsprache (DaZ/DaF)"]])
        Foerderziel.objects.create(plan=plan3, fach=fach["D"], reihenfolge=1,
                                   ziel="Erreicht bis Januar das Niveau B1 im Bereich Leseverstehen.",
                                   massnahmen="DaZ-Kurs (2 Stunden/Woche), Wortschatzlisten je Fach.", zustaendig="DaZ-Lehrkraft")
        n3 = Nachteilsausgleich.objects.create(
            schueler=c, begruendung="Zweitsprachenerwerb; Beschluss der Schulleitung.", zeitverlaengerung=15,
            gueltig_von=date(2026, 3, 1), gueltig_bis=heute + timedelta(days=20), status=Nachteilsausgleich.GENEHMIGT,
            beschlossen_am=date(2026, 2, 25), beschlossen_durch="Schulleitung", foerderplan=plan3, erstellt_von=konto)
        n3.massnahmen.set([ma["Wörterbuch zugelassen"]])
        eltern_c = elternteil(c)
        if eltern_c:
            Aushaendigung.objects.create(nachteilsausgleich=n3, empfaenger=eltern_c, ausgehaendigt_am=date(2026, 3, 2),
                                         weg="persoenlich", bestaetigt_am=date(2026, 3, 4), bestaetigung="unterschrift",
                                         erfasst_von=konto, bestaetigt_durch_konto=konto)
            Aushaendigung.objects.create(foerderplan=plan3, empfaenger=eltern_c, ausgehaendigt_am=date(2026, 9, 10),
                                         weg="gespraech", erfasst_von=konto)
        Schuelerprofil.objects.filter(pk__in=[a.pk, c.pk]).update(nachteilsausgleich=True)

        # Anhänge (Beispieldateien) – Upload-Zeitpunkte gestaffelt, damit die Sortierung sichtbar wird
        verwaltung = User.objects.get(username="verwaltung")
        jetzt = timezone.now()
        beispiele = [
            (a, "Zeugnis 8. Klasse, 2. Halbjahr", "zeugnis", "akte", "zeugnis_2025-26.pdf", verwaltung, 120),
            (a, "Gutachten Lese-Rechtschreib-Schwierigkeit", "diagnostik", "foerderung", "gutachten_lrs.pdf", konto, 150),
            (a, "Rückmeldung der Mutter zum Lesetraining", "korrespondenz", "akte", None, lehrkraft, 6),
            (a, "Unterschriebener Rücklauf Förderplan", "foerderung", "foerderung", "ruecklauf_foerderplan.pdf", lehrkraft, 36),
            (b, "Anmeldeformular", "vertrag", "verwaltung", "anmeldung.pdf", verwaltung, 400),
            (c, "Einstufungstest Deutsch (A2)", "diagnostik", "foerderung", "einstufung_daz.pdf", konto, 220),
        ]
        for schueler, titel, kategorie, stufe, datei, wer, tage in beispiele:
            d = Dokument(person=schueler.person, titel=titel, kategorie=kategorie, zugriffsstufe=stufe, hochgeladen_von=wer)
            if datei:
                d.datei = ContentFile(beispiel_pdf(titel, schueler.person.anzeigename), name=datei)
            else:
                d.notiz = ("Mutter berichtet per E-Mail, dass das tägliche Lesetraining gut klappt; "
                           "bittet um Rückmeldung zur nächsten Klassenarbeit.")
            d.save()
            Dokument.objects.filter(pk=d.pk).update(hochgeladen_am=jetzt - timedelta(days=tage))

    # ------------------------------------------------------------ Startseite: Geburtstage und Notizen (ab 0.4.2.1)
    def startseite_anlegen(self):
        from portal.models import Notiz

        heute = timezone.localdate()
        sj = Schuljahr.objects.get(name="2026/27")

        def geburtstag_in(person, tage):
            ziel = heute + timedelta(days=tage)
            g = person.geburtsdatum or date(1985, 1, 1)
            tag = 28 if (ziel.month == 2 and ziel.day == 29) else ziel.day
            person.geburtsdatum = g.replace(month=ziel.month, day=tag)
            person.save(update_fields=["geburtsdatum"])

        s9a = list(Gruppe.objects.get(schuljahr=sj, name="9a").aktuelle_mitglieder().order_by("person__nachname"))
        s8a = list(Gruppe.objects.get(schuljahr=sj, name="8a").aktuelle_mitglieder().order_by("person__nachname"))
        geburtstag_in(s9a[0].person, 0)
        geburtstag_in(s9a[6].person, 2)
        geburtstag_in(s8a[1].person, 1)
        for kuerzel, tage in (("MUE", 3), ("BRA", 0)):
            pp = Personalprofil.objects.filter(kuerzel=kuerzel).select_related("person").first()
            if pp:
                geburtstag_in(pp.person, tage)
        fm = Personalprofil.objects.filter(stellenbezeichnung="Facility Manager").select_related("person").first()
        if fm:
            geburtstag_in(fm.person, 6)

        lehrkraft = User.objects.get(username="lehrkraft")
        verwaltung = User.objects.get(username="verwaltung")
        Notiz.objects.create(besitzer=lehrkraft, text="Elternabend 9a vorbereiten: Einladung an alle Eltern bis Freitag verschicken.",
                             farbe="gelb", angeheftet=True, datum=heute + timedelta(days=3))
        Notiz.objects.create(besitzer=lehrkraft, text="Chemikalienbestellung an die Fachleitung: Kupfer(II)-sulfat, Magnesiumband, Universalindikator.",
                             farbe="gruen")
        Notiz.objects.create(besitzer=lehrkraft, text="Förderplan Arbeitsorganisation: Evaluationstermin mit den Eltern abstimmen.",
                             farbe="blau", datum=heute)
        Notiz.objects.create(besitzer=lehrkraft, text="Protokolle Flammenfärbung 9b einsammeln.", farbe="grau", erledigt=True)
        Notiz.objects.create(besitzer=verwaltung, sichtbarkeit=Notiz.ALLE, farbe="rosa", angeheftet=True,
                             text="Am Freitag entfällt die 7. Stunde wegen der Gesamtkonferenz (Aula, 13:45 Uhr).",
                             datum=heute + timedelta(days=4))

    # ------------------------------------------------------------ Demo-Konten für alle Rollen (ab 0.4.2.3)
    def rollen_anlegen(self, pw):
        from portal import rollen as R
        from stammdaten.models import Personalbereich

        heute = timezone.localdate()

        def konto(name, person, *rollen, personal=True):
            user = User.objects.create_user(name, password=pw, is_staff=personal, first_name=person.vorname,
                                            last_name=person.nachname)
            user.groups.add(*[Group.objects.get(name=r) for r in rollen])
            person.benutzer = user
            person.save(update_fields=["benutzer"])
            return user

        def neues_personal(vorname, nachname, bereich, stelle, anrede, beginn):
            p = Person.objects.create(anrede=anrede, vorname=vorname, nachname=nachname, ort="Nairobi",
                                      email=f"{vorname.lower()}.{nachname.lower()}@privat.example",
                                      geburtsdatum=date(1975, 3, 14))
            return Personalprofil.objects.create(
                person=p, bereich=Personalbereich.objects.get(kuerzel=bereich), stellenbezeichnung=stelle,
                anstellungsart="adlk" if bereich == "SL" else "ortskraft", dienstbeginn=date(beginn, 8, 1),
                dienst_email=f"{vorname.lower()}.{nachname.lower()}@schule.example", personalnummer=f"P-{beginn}{len(nachname)}",
                kuerzel=nachname[:3].upper() if bereich == "SL" else None,
            )

        for kuerzel, name, rolle in (("MUE", "mittelstufe", R.MITTELSTUFE), ("BRA", "oberstufe", R.OBERSTUFE)):
            pp = Personalprofil.objects.filter(kuerzel=kuerzel).select_related("person").first()
            if pp and not pp.person.benutzer_id:
                konto(name, pp.person, R.LEHRER, rolle)
                pp.weitere_funktionen = ", ".join(filter(None, [pp.weitere_funktionen, str(R.ANZEIGE[rolle])]))
                pp.save(update_fields=["weitere_funktionen"])
        sl = neues_personal("Katharina", "Vogt", "SL", "Schulleiterin", "Frau", 2023)
        konto("schulleitung", sl.person, R.SCHULLEITUNG)
        vl = neues_personal("James", "Mwangi", "VERW", "Verwaltungsleiter", "Herr", 2019)
        konto("verwaltungsleitung", vl.person, R.VERWALTUNGSLEITUNG)
        fin = Personalprofil.objects.filter(stellenbezeichnung="Buchhalterin").select_related("person").first()
        if fin and not fin.person.benutzer_id:
            konto("finanzen", fin.person, R.FINANZEN)

        # Vorbereitete Konten ohne Portalzugang (Stundenplan bzw. Elternkommunikation folgen später)
        s = Schuelerprofil.objects.filter(status="aktiv").select_related("person").order_by("person__nachname").first()
        if s:
            konto("schueler", s.person, R.SCHUELER, personal=False)
            eltern = s.beziehungen.select_related("person").first()
            if eltern:
                konto("eltern", eltern.person, R.ELTERN, personal=False)
        Personalprofil.objects.filter(person__in=[sl.person, vl.person]).update(arbeitserlaubnis_bis=heute.replace(year=heute.year + 2))


def beispiel_pdf(titel, name):
    """Kleines, gültiges PDF mit einer Textzeile – nur für Demo-Anhänge."""
    def esc(t):
        return t.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("latin-1", "replace").decode("latin-1")

    text = f"BT /F1 16 Tf 60 760 Td ({esc(titel)}) Tj 0 -26 Td /F1 11 Tf (Demo-Dokument fuer {esc(name)} - keine echten Daten) Tj ET"
    objekte = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        f"<< /Length {len(text.encode('latin-1'))} >>\nstream\n{text}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
    ]
    aus = "%PDF-1.4\n"
    positionen = []
    for i, obj in enumerate(objekte, start=1):
        positionen.append(len(aus.encode("latin-1")))
        aus += f"{i} 0 obj\n{obj}\nendobj\n"
    xref = len(aus.encode("latin-1"))
    aus += f"xref\n0 {len(objekte) + 1}\n0000000000 65535 f \n"
    aus += "".join(f"{p:010d} 00000 n \n" for p in positionen)
    aus += f"trailer\n<< /Size {len(objekte) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    return aus.encode("latin-1")
