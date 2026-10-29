"""Tests: Freigabe für eine ganze Klasse aufheben, Hinweise auf freigegebene Zeugnisse (ab 0.4.15.1)."""
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from noten.models import Notensperre
from stammdaten.models import Abschnitt, Gruppe, Schuljahr

from .ansichten import zeugnis_fuer
from .models import Zeugnis

PW = "Test-Passwort-123"


class FreigabeAufhebenTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))
        sj = Schuljahr.aktuelles()
        cls.hj1 = Abschnitt.objects.get(schuljahr=sj, nummer=1)
        cls.kl9b = Gruppe.objects.get(schuljahr=sj, name="9b")
        for s in cls.kl9b.aktuelle_mitglieder(sj.stichtag())[:3]:
            z = zeugnis_fuer(s, cls.hj1, cls.kl9b)
            z.status = Zeugnis.FREIGEGEBEN
            z.save()

    def anmelden(self, name):
        self.assertTrue(self.client.login(username=name, password=PW))

    def frei(self):
        return Zeugnis.objects.filter(abschnitt=self.hj1, klasse=self.kl9b, status=Zeugnis.FREIGEGEBEN).count()

    def test_schulleitung_hebt_freigabe_der_klasse_auf(self):
        self.anmelden("schulleitung")
        url = reverse("zeugnis_klasse", args=[self.kl9b.pk, self.hj1.pk])
        self.assertContains(self.client.get(url), 'value="aufheben"')
        self.client.post(url, {"aktion": "aufheben"})
        self.assertEqual(self.frei(), 0)

    def test_klassenleitung_ohne_freigaberecht_aendert_nichts(self):
        self.anmelden("foerderung")                      # Klassenleitung 9b, keine Freigaberechte
        self.client.post(reverse("zeugnis_klasse", args=[self.kl9b.pk, self.hj1.pk]), {"aktion": "aufheben"})
        self.assertEqual(self.frei(), 3)

    def test_hinweis_nach_entsperren(self):
        self.anmelden("schulleitung")
        r = self.client.post(reverse("notensperre"), {"abschnitt": self.hj1.pk, "klasse": self.kl9b.pk, "aktion": "freigeben"},
                             follow=True)
        self.assertFalse(Notensperre.objects.get(abschnitt=self.hj1, klasse=self.kl9b).gesperrt)
        self.assertContains(r, "Zeugnisse der Klasse sind freigegeben")

    def test_klassenuebersicht_nennt_freigegebene_zeugnisse(self):
        self.anmelden("schulleitung")
        r = self.client.get(reverse("noten_klassen") + f"?abschnitt={self.hj1.pk}&klasse={self.kl9b.pk}")
        self.assertEqual(r.context["uebersicht"]["freigegeben"], 3)
        self.assertContains(r, "Zeugnisse dieser Klasse sind freigegeben")
        self.assertContains(r, "Zeugnis freigegeben – erst die Freigabe aufheben")
