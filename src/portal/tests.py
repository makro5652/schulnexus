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

    def test_schuelerakte(self):
        from stammdaten.models import Gruppe

        s_9a = Gruppe.objects.get(name="9a").aktuelle_mitglieder().first()
        s_9b = Gruppe.objects.get(name="9b").aktuelle_mitglieder().first()
        self.client.login(username="lehrkraft", password="Test-Passwort-123")
        r = self.client.get(reverse("schuelerakte", args=[s_9a.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Schullaufbahn")
        self.assertContains(r, "Eltern und Kontaktpersonen")
        self.assertNotContains(r, "Gesundheitsangaben")  # Lehrkräfte sehen Gesundheitsdaten standardmäßig nicht
        self.assertEqual(self.client.get(reverse("schuelerakte", args=[s_9b.pk])).status_code, 403)

    def test_verwaltung_sieht_gesundheitsangaben(self):
        from stammdaten.models import Gesundheitsangaben

        g = Gesundheitsangaben.objects.first()
        self.client.login(username="verwaltung", password="Test-Passwort-123")
        r = self.client.get(reverse("schuelerakte", args=[g.schueler_id]))
        self.assertContains(r, "Gesundheitsangaben")
        self.assertContains(r, g.allergien)

    def test_lehrkraft_sieht_nur_eigene_personalakte(self):
        self.client.login(username="lehrkraft", password="Test-Passwort-123")
        r = self.client.get(reverse("admin:stammdaten_personalprofil_changelist"))
        # Lehrkräfte haben kein Recht auf die Personalverwaltung
        self.assertEqual(r.status_code, 403)

    def test_admin_seiten_laden(self):
        User.objects.create_superuser("chef", password="x-Passwort-123")
        self.client.login(username="chef", password="x-Passwort-123")
        for name in ["stammdaten_person", "stammdaten_schuelerprofil", "stammdaten_gruppe", "noten_unterricht",
                     "noten_leistungsnachweis", "noten_note", "fehlzeiten_fehlzeit", "nachmittag_agangebot",
                     "stammdaten_personalprofil", "stammdaten_laufbahnabschnitt", "stammdaten_elternprofil",
                     "stammdaten_abschluss", "stammdaten_gesundheitsangaben", "noten_bewertungsordner",
                     "stammdaten_personalbereich", "stammdaten_dienstleister", "stammdaten_nachweisart",
                     "stammdaten_nachweis", "stammdaten_personalabwesenheit", "stammdaten_zusatzfeld"]:
            self.assertEqual(self.client.get(reverse(f"admin:{name}_changelist")).status_code, 200, name)
            self.assertEqual(self.client.get(reverse(f"admin:{name}_add")).status_code, 200, name)
        # Detailseiten mit allen Inlines
        from stammdaten.models import Person, Personalprofil, Schuelerprofil

        for obj, name in [(Schuelerprofil.objects.first(), "stammdaten_schuelerprofil"), (Personalprofil.objects.first(), "stammdaten_personalprofil"),
                          (Person.objects.filter(elternprofil__isnull=False).first(), "stammdaten_person")]:
            self.assertEqual(self.client.get(reverse(f"admin:{name}_change", args=[obj.pk])).status_code, 200, name)

    def test_hr_startseite(self):
        self.client.login(username="personal", password="Test-Passwort-123")
        r = self.client.get(reverse("start"))
        self.assertContains(r, "Nachweise mit Handlungsbedarf")
        self.assertContains(r, "abgelaufen")
        self.assertContains(r, "Heute abwesend")
        self.client.login(username="verwaltung", password="Test-Passwort-123")
        self.assertNotContains(self.client.get(reverse("start")), "Nachweise mit Handlungsbedarf")

    def test_personalliste_mit_zusatzspalte_und_filter(self):
        self.client.login(username="personal", password="Test-Passwort-123")
        r = self.client.get(reverse("admin:stammdaten_personalprofil_changelist") + "?nachweise=offen")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Schlüsselberechtigungen")
        self.assertContains(r, "Wekesa")      # Erste Hilfe abgelaufen
        self.assertContains(r, "Chebet")      # Führungszeugnis fehlt
        self.assertNotContains(r, "Kiprono")  # alles gültig

    def test_schuelerakte_zeigt_zusatzfelder(self):
        from stammdaten.models import Gruppe

        s = Gruppe.objects.get(name="9a").aktuelle_mitglieder().first()
        self.client.login(username="lehrkraft", password="Test-Passwort-123")
        r = self.client.get(reverse("schuelerakte", args=[s.pk]))
        self.assertContains(r, "Schulhaus (House)")
        self.assertNotContains(r, "Schulgeld-Ermäßigung")  # nur für Verwaltung sichtbar

    def test_lehrkraft_admin_nur_eigene_leistungsnachweise(self):
        self.client.login(username="lehrkraft", password="Test-Passwort-123")
        r = self.client.get(reverse("admin:noten_leistungsnachweis_changelist"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "1. Klassenarbeit")
