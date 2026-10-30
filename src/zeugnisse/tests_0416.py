"""Tests 0.4.16.0: Textbausteine und Zeichengrenze für Kommentare, Unterzeichnung auf dem Zeugnis."""
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from stammdaten.models import Abschnitt, Gruppe, Personalprofil, Schuljahr

from .ansichten import zeugnis_fuer
from .models import Textbaustein, Unterzeichner

PW = "Test-Passwort-123"


class Version0416ZeugnisTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))
        sj = Schuljahr.aktuelles()
        cls.hj2 = Abschnitt.objects.get(schuljahr=sj, nummer=2)
        cls.kl9a = Gruppe.objects.get(schuljahr=sj, name="9a")
        cls.s = cls.kl9a.aktuelle_mitglieder(sj.stichtag()).first()
        cls.z = zeugnis_fuer(cls.s, cls.hj2, cls.kl9a)
        Textbaustein.objects.create(titel="Fleißig", kategorie="Arbeitsverhalten", text="{vorname} arbeitet stets sorgfältig.")
        Textbaustein.objects.create(titel="Nur Oberstufe", text="Oberstufe", jahrgang_von=11)

    def anmelden(self, name):
        self.assertTrue(self.client.login(username=name, password=PW))

    def test_textbausteine_passend_zum_jahrgang_und_personalisiert(self):
        self.assertEqual(list(Textbaustein.fuer(9).values_list("titel", flat=True)), ["Fleißig"])
        self.anmelden("lehrkraft")                       # Klassenleitung 9a
        r = self.client.get(reverse("zeugnis", args=[self.z.pk]))
        self.assertContains(r, "Textbausteine einfügen")
        name = self.s.person.rufname or self.s.person.vorname
        self.assertContains(r, f"{name} arbeitet stets sorgfältig.")
        self.assertNotContains(r, "Nur Oberstufe")

    @override_settings(ZEUGNIS_KOMMENTAR_MAX=20)
    def test_zeichengrenze(self):
        self.anmelden("lehrkraft")
        r = self.client.post(reverse("zeugnis", args=[self.z.pk]), {"aktion": "kommentar", "kommentar": "x" * 30}, follow=True)
        self.assertContains(r, "höchstens 20 Zeichen")
        self.z.refresh_from_db()
        self.assertNotEqual(self.z.kommentar, "x" * 30)

    def test_unterzeichner_auf_dem_druck(self):
        sl = Personalprofil.objects.filter(person__nachname="Vogt").first()
        Unterzeichner.objects.create(person=sl, funktion="Schulleiterin", jahrgang_von=5, jahrgang_bis=12)
        self.anmelden("schulleitung")
        r = self.client.get(reverse("zeugnis_druck", args=[self.z.pk]))
        self.assertContains(r, "Schulleiterin")
        self.assertContains(r, sl.person.anzeigename)
