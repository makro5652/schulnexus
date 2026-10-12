from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import Gruppe, Mitgliedschaft, Person, Schuelerprofil, Schuljahr


class MitgliedschaftTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.sj = Schuljahr.objects.create(name="2026/27", beginn=date(2026, 8, 17), ende=date(2027, 6, 25), aktiv=True)
        cls.a = Gruppe.objects.create(schuljahr=cls.sj, name="9a", jahrgang=9)
        cls.b = Gruppe.objects.create(schuljahr=cls.sj, name="9b", jahrgang=9)
        cls.ethik = Gruppe.objects.create(schuljahr=cls.sj, name="Ethik 9", typ=Gruppe.LERNGRUPPE)
        cls.s = Schuelerprofil.objects.create(person=Person.objects.create(vorname="A", nachname="B"), schuelernummer="1")

    def test_nur_eine_stammklasse_gleichzeitig(self):
        Mitgliedschaft.objects.create(gruppe=self.a, schueler=self.s, von=self.sj.beginn)
        with self.assertRaises(ValidationError):
            Mitgliedschaft.objects.create(gruppe=self.b, schueler=self.s, von=date(2026, 10, 1))

    def test_klassenwechsel_nach_beenden_moeglich(self):
        m = Mitgliedschaft.objects.create(gruppe=self.a, schueler=self.s, von=self.sj.beginn)
        m.bis = date(2026, 9, 30)
        m.save()
        Mitgliedschaft.objects.create(gruppe=self.b, schueler=self.s, von=date(2026, 10, 1))
        self.assertEqual(self.s.stammklasse(stichtag=date(2026, 9, 15)), self.a)
        self.assertEqual(self.s.stammklasse(stichtag=date(2026, 11, 1)), self.b)

    def test_lerngruppe_zusaetzlich_erlaubt(self):
        Mitgliedschaft.objects.create(gruppe=self.a, schueler=self.s, von=self.sj.beginn)
        Mitgliedschaft.objects.create(gruppe=self.ethik, schueler=self.s, von=self.sj.beginn)
        self.assertIn(self.s, self.ethik.aktuelle_mitglieder(stichtag=date(2026, 9, 1)))

    def test_bis_vor_von(self):
        with self.assertRaises(ValidationError):
            Mitgliedschaft.objects.create(gruppe=self.ethik, schueler=self.s, von=date(2026, 9, 1), bis=date(2026, 8, 1))

    def test_nur_ein_aktives_schuljahr(self):
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError), transaction.atomic():
            Schuljahr.objects.create(name="2027/28", beginn=date(2027, 8, 16), ende=date(2028, 6, 23), aktiv=True)


class LaufbahnTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.core.management import call_command

        call_command("grundeinrichtung", stdout=open("/dev/null", "w"))
        cls.sj = Schuljahr.objects.create(name="2026/27", beginn=date(2026, 8, 17), ende=date(2027, 6, 25), aktiv=True)
        cls.alt = Schuljahr.objects.create(name="2025/26", beginn=date(2025, 8, 18), ende=date(2026, 6, 26))
        cls.s = Schuelerprofil.objects.create(person=Person.objects.create(vorname="A", nachname="B"), schuelernummer="1")

    def test_bildungsgaenge_eingerichtet(self):
        from .models import Abschlussart, Bildungsgang

        self.assertEqual(set(Bildungsgang.objects.values_list("kuerzel", flat=True)) >= {"HS", "RS", "GYM", "GOS"}, True)
        self.assertTrue(Abschlussart.objects.filter(kuerzel="MSA").exists())

    def test_laufbahn_und_aktueller_abschnitt(self):
        from .models import Bildungsgang, Laufbahnabschnitt

        rs, gym = Bildungsgang.objects.get(kuerzel="RS"), Bildungsgang.objects.get(kuerzel="GYM")
        Laufbahnabschnitt.objects.create(schueler=self.s, schuljahr=self.alt, jahrgang=8, bildungsgang=rs, ergebnis="wechsel")
        Laufbahnabschnitt.objects.create(schueler=self.s, schuljahr=self.sj, jahrgang=9, bildungsgang=gym)
        self.assertEqual(self.s.aktueller_laufbahnabschnitt().bildungsgang, gym)
        self.assertEqual(self.s.laufbahn.count(), 2)

    def test_jahrgang_passt_nicht_zum_bildungsgang(self):
        from .models import Bildungsgang, Laufbahnabschnitt

        gos = Bildungsgang.objects.get(kuerzel="GOS")
        with self.assertRaises(ValidationError):
            Laufbahnabschnitt(schueler=self.s, schuljahr=self.sj, jahrgang=7, bildungsgang=gos).full_clean()

    def test_stammklasse_aus_anderem_schuljahr(self):
        from .models import Bildungsgang, Laufbahnabschnitt

        klasse_alt = Gruppe.objects.create(schuljahr=self.alt, name="8a", jahrgang=8)
        with self.assertRaises(ValidationError):
            Laufbahnabschnitt(schueler=self.s, schuljahr=self.sj, jahrgang=9, bildungsgang=Bildungsgang.objects.get(kuerzel="GYM"),
                              stammklasse=klasse_alt).full_clean()
