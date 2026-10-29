"""Tests: Notenliste je Klasse wie in der Konferenz, auch für vergangene Schuljahre (ab 0.4.15.0)."""
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from stammdaten.models import Abschnitt, Gruppe, Schuljahr

from .models import Zeugnis

PW = "Test-Passwort-123"


class NotenlisteTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))
        cls.sj = Schuljahr.aktuelles()
        cls.hj1 = Abschnitt.objects.get(schuljahr=cls.sj, nummer=1)
        cls.kl9a = Gruppe.objects.get(schuljahr=cls.sj, name="9a")
        cls.kl9b = Gruppe.objects.get(schuljahr=cls.sj, name="9b")

    def anmelden(self, name):
        self.assertTrue(self.client.login(username=name, password=PW))

    def url(self, **q):
        return reverse("notenliste") + "?" + "&".join(f"{k}={v}" for k, v in q.items())

    def test_sekretariat_sieht_notenliste_ohne_zeugnisse_anzulegen(self):
        self.anmelden("verwaltung")
        vorher = Zeugnis.objects.count()
        r = self.client.get(self.url(sj=self.sj.pk, abschnitt=self.hj1.pk, klasse=self.kl9a.pk))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context["zeilen"]), len(self.kl9a.aktuelle_mitglieder(self.sj.stichtag())))
        self.assertTrue(r.context["spalten"])
        self.assertContains(r, 'class="zg-matrix nl-matrix"')
        self.assertEqual(Zeugnis.objects.count(), vorher)

    def test_klassenleitung_nur_eigene_klasse(self):
        self.anmelden("lehrkraft")                       # Klassenleitung 9a
        r = self.client.get(self.url(sj=self.sj.pk, klasse=self.kl9b.pk))
        self.assertIn(self.kl9a, r.context["klassen"])
        self.assertNotIn(self.kl9b, r.context["klassen"])
        self.assertIsNone(r.context["klasse"])

    def test_vergangenes_schuljahr_waehlbar(self):
        self.anmelden("schulleitung")
        alt = Schuljahr.objects.exclude(pk=self.sj.pk).order_by("beginn").first()
        r = self.client.get(self.url(sj=alt.pk))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["sj"], alt)

    def test_ohne_recht_kein_zugriff(self):
        self.anmelden("finanzen")
        self.assertEqual(self.client.get(reverse("notenliste")).status_code, 403)
