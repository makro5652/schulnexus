"""Tests für die Zuordnung zu Klassen und Gruppen (seit Version 0.4.2.4)."""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from stammdaten.models import Gruppe, Mitgliedschaft, Schuljahr

from .zuordnung import entfernen, hinzufuegen

PW = "Test-Passwort-123"


class ZuordnungTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))
        cls.sj = Schuljahr.aktuelles()
        cls.kl9a = Gruppe.objects.get(schuljahr=cls.sj, name="9a")
        cls.kl9b = Gruppe.objects.get(schuljahr=cls.sj, name="9b")
        cls.heute = timezone.localdate()

    def anmelden(self, name):
        self.client.logout()
        self.assertTrue(self.client.login(username=name, password=PW))

    def aktion(self, gruppe, **daten):
        return self.client.post(reverse("zuordnung_aktion", args=[gruppe.pk]), daten)

    # ------------------------------------------------------------ Kernlogik
    def test_klassenwechsel_beendet_alte_klasse(self):
        s = self.kl9a.aktuelle_mitglieder().first()
        alt = Mitgliedschaft.objects.get(schueler=s, gruppe=self.kl9a)
        e = hinzufuegen(self.kl9b, [s], self.heute)
        self.assertEqual(e["neu"], 1)
        self.assertEqual(len(e["wechsel"]), 1)
        alt.refresh_from_db()
        self.assertEqual(alt.bis, self.heute - timedelta(days=1))   # Historie bleibt erhalten
        self.assertEqual(s.stammklasse(), self.kl9b)

    def test_doppelt_hinzufuegen_wird_erkannt(self):
        s = self.kl9a.aktuelle_mitglieder().first()
        self.assertEqual(hinzufuegen(self.kl9a, [s], self.heute)["schon"], 1)

    def test_entfernen_zum_stichtag_und_tippfehler_loeschen(self):
        ethik = Gruppe.objects.get(schuljahr=self.sj, name="Ethik 9")
        s = self.kl9a.aktuelle_mitglieder().exclude(mitgliedschaften__gruppe=ethik).first()
        hinzufuegen(ethik, [s], self.heute)
        self.assertEqual(entfernen(ethik, [s.pk], self.heute), 1)   # am selben Tag wieder entfernt → gelöscht
        self.assertFalse(Mitgliedschaft.objects.filter(gruppe=ethik, schueler=s).exists())
        m = Mitgliedschaft.objects.filter(gruppe=ethik).first()
        entfernen(ethik, [m.schueler_id], self.heute)
        m.refresh_from_db()
        self.assertEqual(m.bis, self.heute - timedelta(days=1))

    def test_stichtag_nicht_vor_schuljahresbeginn(self):
        ethik = Gruppe.objects.get(schuljahr=self.sj, name="Ethik 9")
        s = self.kl9b.aktuelle_mitglieder().exclude(mitgliedschaften__gruppe=ethik).first()
        hinzufuegen(ethik, [s], date(2000, 1, 1))
        self.assertEqual(Mitgliedschaft.objects.get(gruppe=ethik, schueler=s).von, self.sj.beginn)

    # ------------------------------------------------------------ Seite und Rechte
    def test_seite_sekretariat(self):
        self.anmelden("verwaltung")
        r = self.client.get(reverse("zuordnung") + f"?gruppe={self.kl9a.pk}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context["gruppe"], self.kl9a)
        self.assertEqual(len(r.context["mitglieder"]), 13)
        self.assertContains(r, 'id="zo-poolliste"')
        self.assertTrue(r.context["darf_bearbeiten"])

    def test_hinzufuegen_und_entfernen_ueber_formular(self):
        self.anmelden("verwaltung")
        ag = Gruppe.objects.get(schuljahr=self.sj, name="AG Robotik")
        neue = list(self.kl9b.aktuelle_mitglieder().exclude(mitgliedschaften__gruppe=ag)[:3])
        r = self.aktion(ag, aktion="hinzufuegen", datum=self.heute.isoformat(), schueler=[s.pk for s in neue])
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Mitgliedschaft.objects.aktiv().filter(gruppe=ag, schueler__in=neue).count(), 3)
        self.aktion(ag, aktion="entfernen", datum=(self.heute + timedelta(days=1)).isoformat(), schueler=[neue[0].pk])
        self.assertEqual(Mitgliedschaft.objects.get(gruppe=ag, schueler=neue[0]).bis, self.heute)

    def test_rolle_speichern(self):
        self.anmelden("verwaltung")
        m = Mitgliedschaft.objects.filter(gruppe=self.kl9a).first()
        self.aktion(self.kl9a, aktion="rolle", mitgliedschaft=m.pk, rolle="Klassensprecher:in")
        m.refresh_from_db()
        self.assertEqual(m.rolle, "Klassensprecher:in")

    def test_vorgaenger_uebernehmen(self):
        neu_sj, _neu = Schuljahr.objects.get_or_create(name="2027/28", defaults={"beginn": date(2027, 8, 16), "ende": date(2028, 6, 23)})
        kl10a = Gruppe.objects.create(schuljahr=neu_sj, name="10a", jahrgang=10, vorgaenger=self.kl9a)
        self.anmelden("verwaltung")
        r = self.client.get(reverse("zuordnung") + f"?sj={neu_sj.pk}&gruppe={kl10a.pk}")
        self.assertEqual(r.context["vorgaenger_neu"], 13)
        self.aktion(kl10a, aktion="vorgaenger", datum=neu_sj.beginn.isoformat())
        self.assertEqual(kl10a.aktuelle_mitglieder(neu_sj.beginn).count(), 13)
        self.assertEqual(Mitgliedschaft.objects.filter(gruppe=kl10a).first().von, neu_sj.beginn)

    def test_neue_gruppe(self):
        self.anmelden("verwaltung")
        r = self.client.post(reverse("gruppe_anlegen"), {"sj": self.sj.pk, "neu-name": "Rallye 9", "neu-typ": "lerngruppe",
                                                          "neu-jahrgang": 9})
        g = Gruppe.objects.get(schuljahr=self.sj, name="Rallye 9")
        self.assertIn(f"gruppe={g.pk}", r.url)
        self.client.post(reverse("gruppe_anlegen"), {"sj": self.sj.pk, "neu-name": "rallye 9", "neu-typ": "lerngruppe"})
        self.assertEqual(Gruppe.objects.filter(schuljahr=self.sj, name__iexact="rallye 9").count(), 1)

    def test_lehrkraft_ohne_zugang(self):
        self.anmelden("lehrkraft")
        self.assertEqual(self.client.get(reverse("zuordnung")).status_code, 403)
        self.assertEqual(self.aktion(self.kl9a, aktion="entfernen", schueler=[1]).status_code, 403)

    def test_stufenkoordination_nur_eigene_stufe(self):
        self.anmelden("mittelstufe")
        r = self.client.get(reverse("zuordnung"))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(all(g.jahrgang in range(5, 11) for g in r.context["gruppen"]))
        self.assertNotIn("AG Robotik", [g.name for g in r.context["gruppen"]])  # AGs ohne Jahrgang: Verwaltung
        ag = Gruppe.objects.get(schuljahr=self.sj, name="AG Robotik")
        self.assertEqual(self.aktion(ag, aktion="entfernen", schueler=[1]).status_code, 403)
        r = self.client.post(reverse("gruppe_anlegen"), {"sj": self.sj.pk, "neu-name": "Kurs 11", "neu-typ": "lerngruppe",
                                                          "neu-jahrgang": 11})
        self.assertFalse(Gruppe.objects.filter(name="Kurs 11").exists())
        self.client.post(reverse("gruppe_anlegen"), {"sj": self.sj.pk, "neu-name": "Rallye 8", "neu-typ": "lerngruppe",
                                                     "neu-jahrgang": 8})
        self.assertTrue(Gruppe.objects.filter(name="Rallye 8").exists())

    def test_menueband_und_klassenliste(self):
        self.anmelden("verwaltung")
        mb = self.client.get(reverse("zuordnung")).context["MENUEBAND"]
        self.assertEqual(mb["aktiv"], "schueler")
        r = self.client.get(reverse("klassenliste", args=[self.kl9a.pk]))
        self.assertContains(r, reverse("zuordnung"))

    def test_englisch(self):
        self.anmelden("verwaltung")
        self.client.post(reverse("sprache_wechseln"), {"sprache": "en", "next": "/"})
        r = self.client.get(reverse("zuordnung"))
        self.assertContains(r, "Classes and groups")
        self.assertContains(r, "Subjects and teachers")
        self.assertContains(r, "Add students")
        self.assertIsNotNone(User)
