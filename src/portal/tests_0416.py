"""Tests 0.4.16.0: stellvertretende Klassenleitung, Klassenraum/Höchstzahl, Fachleitung, Stundentafel und Stunden."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from noten.models import Unterricht
from stammdaten.models import Abschnitt, Fach, Fachbereich, Gruppe, Personalprofil, Schuljahr, Stundentafel

from .klassenunterricht import speichern
from .rechte import darf_unterricht_sehen

PW = "Test-Passwort-123"


class KlassendetailsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))
        cls.sj = Schuljahr.aktuelles()
        cls.hj1 = Abschnitt.objects.get(schuljahr=cls.sj, nummer=1)
        cls.kl9a = Gruppe.objects.get(schuljahr=cls.sj, name="9a")
        cls.kl9b = Gruppe.objects.get(schuljahr=cls.sj, name="9b")
        cls.kra = Personalprofil.objects.get(kuerzel="KRA")
        cls.user = User.objects.get(username="lehrkraft")

    def anmelden(self, name):
        self.assertTrue(self.client.login(username=name, password=PW))

    def test_stellvertretende_klassenleitung_hat_rechte_der_klassenleitung(self):
        mue = Personalprofil.objects.get(kuerzel="MUE")
        hj1 = self.hj1
        fach = Fach.objects.exclude(unterrichte__gruppe=self.kl9b).first()
        speichern(self.kl9b, {(fach.pk, hj1.pk): (None, mue.pk)})
        fremd = Unterricht.objects.get(gruppe=self.kl9b, fach=fach, abschnitt=hj1)
        self.assertFalse(darf_unterricht_sehen(self.user, fremd))
        self.kl9b.leitung2 = self.kra
        self.kl9b.save()
        fremd = Unterricht.objects.get(pk=fremd.pk)
        self.assertTrue(darf_unterricht_sehen(User.objects.get(pk=self.user.pk), fremd))
        self.anmelden("lehrkraft")
        self.assertEqual(self.client.get(reverse("klassenliste", args=[self.kl9b.pk])).status_code, 200)

    def test_klassenraum_hoechstzahl_und_warnung(self):
        self.anmelden("verwaltung")
        r = self.client.post(reverse("gruppe_bearbeiten", args=[self.kl9b.pk]), {
            "bearb-name": "9b", "bearb-jahrgang": 9, "bearb-leitung": self.kl9b.leitung_id, "bearb-raum": "B 104",
            "bearb-kapazitaet": 2})
        self.assertEqual(r.status_code, 302)
        self.kl9b.refresh_from_db()
        self.assertEqual((self.kl9b.raum, self.kl9b.kapazitaet), ("B 104", 2))
        neu = self.kl9a.aktuelle_mitglieder().first()
        r = self.client.post(reverse("zuordnung_aktion", args=[self.kl9b.pk]), {"aktion": "hinzufuegen", "schueler": [neu.pk]},
                             follow=True)
        self.assertContains(r, "mehr als die Höchstzahl von 2")

    def test_fachleitung_sieht_kurse_ihres_fachbereichs(self):
        u = Unterricht.objects.exclude(gruppe=self.kl9a).exclude(lehrkraft=self.kra).select_related("fach").first()
        self.assertFalse(darf_unterricht_sehen(self.user, u))
        fb = Fachbereich.objects.create(name="Testbereich", leitung=self.kra)
        u.fach.fachbereich = fb
        u.fach.save()
        u = Unterricht.objects.select_related("fach__fachbereich").get(pk=u.pk)
        self.assertTrue(darf_unterricht_sehen(User.objects.get(pk=self.user.pk), u))

    def test_stundentafel_seite_und_stunden_im_unterricht(self):
        fach = Fach.objects.exclude(unterrichte__gruppe=self.kl9a).first()
        self.anmelden("schulleitung")
        r = self.client.post(reverse("stundentafel"), {f"st_{fach.pk}_9": "3,5"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Stundentafel.stunden(fach.pk, 9), Decimal("3.5"))
        speichern(self.kl9a, {(fach.pk, self.hj1.pk): (None, self.kra.pk)})
        self.assertEqual(Unterricht.objects.get(gruppe=self.kl9a, fach=fach, abschnitt=self.hj1).wochenstunden, Decimal("3.5"))
        r = self.client.get(reverse("zuordnung") + f"?gruppe={self.kl9a.pk}&ansicht=faecher")
        self.assertContains(r, "Stunden der Lehrkräfte")
        self.assertTrue(any(d["p"] == self.kra for d in r.context["unterricht"]["deputate"]))

    def test_stundentafel_ungueltig_und_ohne_recht(self):
        fach = Fach.objects.first()
        self.anmelden("schulleitung")
        r = self.client.post(reverse("stundentafel"), {f"st_{fach.pk}_9": "abc"}, follow=True)
        self.assertContains(r, "Nicht gespeichert")
        self.client.logout()
        self.anmelden("lehrkraft")
        self.assertEqual(self.client.post(reverse("stundentafel"), {f"st_{fach.pk}_9": "2"}).status_code, 403)
