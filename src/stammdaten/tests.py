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
