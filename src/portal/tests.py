from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from noten.models import Unterricht


class PortalTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort="Test-Passwort-123", stdout=open("/dev/null", "w"))

    def test_gesundheit(self):
        self.assertEqual(self.client.get(reverse("gesundheit")).json(), {"status": "ok"})

    def test_start_erfordert_anmeldung(self):
        r = self.client.get(reverse("start"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("login"), r.url)

    def test_lehrkraft_sieht_eigenen_unterricht(self):
        self.client.login(username="lehrkraft", password="Test-Passwort-123")
        u = Unterricht.objects.get(fach__kuerzel="CH", gruppe__name="9a")
        r = self.client.get(reverse("notenuebersicht", args=[u.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Vorschlag")

    def test_lehrkraft_sieht_fremden_unterricht_nicht(self):
        self.client.login(username="lehrkraft", password="Test-Passwort-123")
        u = Unterricht.objects.get(fach__kuerzel="M", gruppe__name="9a")
        # Mathematik 9a: fremde Lehrkraft, aber Klassenleitung 9a -> Einsicht erlaubt
        self.assertEqual(self.client.get(reverse("notenuebersicht", args=[u.pk])).status_code, 200)
        u = Unterricht.objects.get(fach__kuerzel="ETH")
        self.assertEqual(self.client.get(reverse("notenuebersicht", args=[u.pk])).status_code, 403)

    def test_verwaltung_sieht_alles(self):
        self.client.login(username="verwaltung", password="Test-Passwort-123")
        for u in Unterricht.objects.all():
            self.assertEqual(self.client.get(reverse("notenuebersicht", args=[u.pk])).status_code, 200)
        self.assertContains(self.client.get(reverse("start")), "Schüler:innen aktiv")

    def test_klassenliste(self):
        self.client.login(username="lehrkraft", password="Test-Passwort-123")
        from stammdaten.models import Gruppe

        r = self.client.get(reverse("klassenliste", args=[Gruppe.objects.get(name="9a").pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get(reverse("klassenliste", args=[Gruppe.objects.get(name="9b").pk])).status_code, 403)

    def test_admin_seiten_laden(self):
        User.objects.create_superuser("chef", password="x-Passwort-123")
        self.client.login(username="chef", password="x-Passwort-123")
        for name in ["stammdaten_person", "stammdaten_schuelerprofil", "stammdaten_gruppe", "noten_unterricht",
                     "noten_leistungsnachweis", "noten_note", "fehlzeiten_fehlzeit", "nachmittag_agangebot"]:
            self.assertEqual(self.client.get(reverse(f"admin:{name}_changelist")).status_code, 200, name)
            self.assertEqual(self.client.get(reverse(f"admin:{name}_add")).status_code, 200, name)

    def test_lehrkraft_admin_nur_eigene_leistungsnachweise(self):
        self.client.login(username="lehrkraft", password="Test-Passwort-123")
        r = self.client.get(reverse("admin:noten_leistungsnachweis_changelist"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "1. Klassenarbeit")
