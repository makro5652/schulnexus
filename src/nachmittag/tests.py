from datetime import date, time

from django.test import TestCase

from stammdaten.models import Abschnitt, Mitgliedschaft, Person, Schuelerprofil, Schuljahr

from .models import AGAngebot, AGWahl, AGZuteilung
from .zuteilung import lose_zuteilen


class LosverfahrenTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        sj = Schuljahr.objects.create(name="2026/27", beginn=date(2026, 8, 17), ende=date(2027, 6, 25), aktiv=True)
        cls.hj = Abschnitt.objects.create(schuljahr=sj, name="1. HJ", nummer=1, beginn=date(2026, 8, 17), ende=date(2027, 1, 29))
        cls.robotik = AGAngebot.objects.create(abschnitt=cls.hj, titel="Robotik", wochentag=1, beginn=time(14), ende=time(15), kapazitaet=2)
        cls.chor = AGAngebot.objects.create(abschnitt=cls.hj, titel="Chor", wochentag=2, beginn=time(14), ende=time(15), kapazitaet=10)
        cls.schueler = [
            Schuelerprofil.objects.create(person=Person.objects.create(vorname=f"S{i}", nachname="X"), schuelernummer=str(i))
            for i in range(5)
        ]
        for s in cls.schueler:
            AGWahl.objects.create(schueler=s, angebot=cls.robotik, prioritaet=1)
            AGWahl.objects.create(schueler=s, angebot=cls.chor, prioritaet=2)

    def test_kapazitaet_und_zweitwunsch(self):
        e = lose_zuteilen(self.hj, seed=1)
        self.assertEqual(e.zugeteilt, {1: 2, 2: 3, 3: 0})
        self.assertEqual(self.robotik.zuteilungen.count(), 2)
        self.assertEqual(self.chor.zuteilungen.count(), 3)
        self.assertEqual(e.ohne_platz, [])

    def test_ag_gruppe_und_mitgliedschaften(self):
        lose_zuteilen(self.hj, seed=1)
        self.assertEqual(Mitgliedschaft.objects.filter(gruppe=self.robotik.gruppe).count(), 2)

    def test_wiederholung_aendert_nichts(self):
        lose_zuteilen(self.hj, seed=1)
        e = lose_zuteilen(self.hj, seed=2)
        self.assertEqual(e.zugeteilt, {1: 0, 2: 0, 3: 0})
        self.assertEqual(AGZuteilung.objects.count(), 5)
