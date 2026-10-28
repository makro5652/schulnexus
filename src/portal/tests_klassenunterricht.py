"""Tests: Klassen und Gruppen – Fächer und Lehrkräfte, Gruppe bearbeiten, neue Schüler:innen (ab 0.4.14.0)."""
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from noten.models import Unterricht
from stammdaten.models import Abschnitt, Fach, Gruppe, Mitgliedschaft, Personalprofil, Schuelerprofil, Schuljahr

from .klassenunterricht import speichern

PW = "Test-Passwort-123"


class KlassenunterrichtTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))
        cls.sj = Schuljahr.aktuelles()
        cls.kl9a = Gruppe.objects.get(schuljahr=cls.sj, name="9a")
        cls.hj1 = Abschnitt.objects.get(schuljahr=cls.sj, nummer=1)
        cls.hj2 = Abschnitt.objects.get(schuljahr=cls.sj, nummer=2)
        cls.ch = Unterricht.objects.get(gruppe=cls.kl9a, fach__kuerzel="CH", abschnitt=cls.hj1)   # mit Noten
        cls.frei = Fach.objects.exclude(unterrichte__gruppe=cls.kl9a).first()
        cls.lk = Personalprofil.objects.filter(aktiv=True, bereich__unterrichtet=True).exclude(pk=cls.ch.lehrkraft_id).first()

    def anmelden(self, name):
        self.client.logout()
        self.assertTrue(self.client.login(username=name, password=PW))

    def senden(self, gruppe, felder):
        """felder: {(fach, abschnitt): (vorher, neu)} → Formulardaten wie von der Seite."""
        daten = {}
        for (f, a), (vorher, neu) in felder.items():
            daten[f"l_{f.pk}_{a.pk}"] = neu.pk if neu else ""
            daten[f"vorher_l_{f.pk}_{a.pk}"] = vorher.pk if vorher else ""
        return self.client.post(reverse("zuordnung_unterricht", args=[gruppe.pk]), daten)

    # ------------------------------------------------------------ Kernlogik
    def test_neuer_unterricht_mit_skala_des_jahrgangs(self):
        e = speichern(self.kl9a, {(self.frei.pk, self.hj1.pk): (None, self.lk.pk)})
        self.assertEqual(e["neu"], 1)
        u = Unterricht.objects.get(gruppe=self.kl9a, fach=self.frei, abschnitt=self.hj1)
        self.assertEqual(u.lehrkraft, self.lk)
        self.assertEqual(u.skala_id, self.ch.skala_id)

    def test_lehrkraft_wechseln_auch_mit_noten(self):
        e = speichern(self.kl9a, {(self.ch.fach_id, self.hj1.pk): (self.ch.lehrkraft_id, self.lk.pk)})
        self.assertEqual(e["geaendert"], 1)
        self.ch.refresh_from_db()
        self.assertEqual(self.ch.lehrkraft, self.lk)

    def test_unterricht_mit_noten_wird_nicht_geloescht(self):
        e = speichern(self.kl9a, {(self.ch.fach_id, self.hj1.pk): (self.ch.lehrkraft_id, None)})
        self.assertEqual(e["entfernt"], 0)
        self.assertEqual(len(e["fehler"]), 1)
        self.assertTrue(Unterricht.objects.filter(pk=self.ch.pk).exists())

    def test_unterricht_ohne_noten_wird_entfernt(self):
        speichern(self.kl9a, {(self.frei.pk, self.hj2.pk): (None, self.lk.pk)})
        e = speichern(self.kl9a, {(self.frei.pk, self.hj2.pk): (self.lk.pk, None)})
        self.assertEqual(e["entfernt"], 1)
        self.assertFalse(Unterricht.objects.filter(gruppe=self.kl9a, fach=self.frei, abschnitt=self.hj2).exists())

    def test_inzwischen_geaendert_wird_nicht_ueberschrieben(self):
        e = speichern(self.kl9a, {(self.ch.fach_id, self.hj1.pk): (self.lk.pk, None)})   # veralteter Stand
        self.assertEqual(len(e["fehler"]), 1)
        self.ch.refresh_from_db()
        self.assertNotEqual(self.ch.lehrkraft, self.lk)

    # ------------------------------------------------------------ Seite und Rechte
    def test_seite_faecher_sekretariat(self):
        self.anmelden("verwaltung")
        r = self.client.get(reverse("zuordnung") + f"?gruppe={self.kl9a.pk}&ansicht=faecher")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["darf_unterricht"])
        self.assertContains(r, 'id="zo-faecherform"')
        self.assertContains(r, "Noten vorhanden")

    def test_sekretariat_speichert_ueber_formular(self):
        self.anmelden("verwaltung")
        r = self.senden(self.kl9a, {(self.frei, self.hj1): (None, self.lk), (self.frei, self.hj2): (None, self.lk)})
        self.assertEqual(r.status_code, 302)
        self.assertIn("ansicht=faecher", r.url)
        self.assertEqual(Unterricht.objects.filter(gruppe=self.kl9a, fach=self.frei).count(), 2)

    def test_mittelstufe_darf_eigene_stufe(self):
        self.anmelden("mittelstufe")
        r = self.senden(self.kl9a, {(self.frei, self.hj1): (None, self.lk)})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Unterricht.objects.filter(gruppe=self.kl9a, fach=self.frei).exists())

    def test_oberstufe_nicht_fuer_mittelstufenklasse(self):
        self.anmelden("oberstufe")
        self.assertEqual(self.senden(self.kl9a, {(self.frei, self.hj1): (None, self.lk)}).status_code, 403)

    def test_lehrkraft_ohne_zugriff(self):
        self.anmelden("lehrkraft")
        self.assertEqual(self.client.get(reverse("zuordnung")).status_code, 403)
        self.assertEqual(self.senden(self.kl9a, {(self.frei, self.hj1): (None, self.lk)}).status_code, 403)

    def test_it_administration(self):
        self.anmelden("it")
        r = self.client.get(reverse("zuordnung") + f"?gruppe={self.kl9a.pk}&ansicht=faecher")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["darf_unterricht"])

    # ------------------------------------------------------------ Klasse anlegen, bearbeiten, Schüler:innen
    def test_klasse_anlegen_und_bearbeiten(self):
        self.anmelden("verwaltung")
        r = self.client.post(reverse("gruppe_anlegen"), {"sj": self.sj.pk, "neu-name": "5c", "neu-typ": Gruppe.STAMMKLASSE,
                                                         "neu-jahrgang": 5})
        self.assertEqual(r.status_code, 302)
        g = Gruppe.objects.get(schuljahr=self.sj, name="5c")
        r = self.client.post(reverse("gruppe_bearbeiten", args=[g.pk]), {"bearb-name": "5d", "bearb-jahrgang": 5,
                                                                          "bearb-leitung": self.lk.pk})
        self.assertEqual(r.status_code, 302)
        g.refresh_from_db()
        self.assertEqual((g.name, g.leitung, g.typ), ("5d", self.lk, Gruppe.STAMMKLASSE))

    def test_neue_schuelerin_anlegen_und_zuordnen(self):
        self.anmelden("verwaltung")
        url = reverse("zuordnung_schueler_anlegen", args=[self.kl9a.pk])
        r = self.client.post(url, {"sn-vorname": "Amani", "sn-nachname": "Quellenberg-Testfall", "sn-geschlecht": "w"})
        self.assertEqual(r.status_code, 302)
        s = Schuelerprofil.objects.get(person__nachname="Quellenberg-Testfall")
        self.assertEqual(s.stammklasse(), self.kl9a)
        self.assertEqual(s.status, "aktiv")
        # gleichnamige Person: nur mit „Trotzdem anlegen“
        self.client.post(url, {"sn-vorname": "Amani", "sn-nachname": "Quellenberg-Testfall"})
        self.assertEqual(Schuelerprofil.objects.filter(person__nachname="Quellenberg-Testfall").count(), 1)
        self.client.post(url, {"sn-vorname": "Amani", "sn-nachname": "Quellenberg-Testfall", "sn-trotzdem": "on"})
        self.assertEqual(Schuelerprofil.objects.filter(person__nachname="Quellenberg-Testfall").count(), 2)

    def test_koordination_legt_keine_schueler_an(self):
        self.anmelden("mittelstufe")
        r = self.client.get(reverse("zuordnung") + f"?gruppe={self.kl9a.pk}")
        self.assertIsNone(r.context["schueler_form"])
        r = self.client.post(reverse("zuordnung_schueler_anlegen", args=[self.kl9a.pk]), {"sn-vorname": "X", "sn-nachname": "Y"})
        self.assertEqual(r.status_code, 403)

    def test_abmelden_beendet_mitgliedschaft(self):
        self.anmelden("verwaltung")
        s = self.kl9a.aktuelle_mitglieder().first()
        self.client.post(reverse("zuordnung_aktion", args=[self.kl9a.pk]), {"aktion": "entfernen", "schueler": [s.pk]})
        self.assertFalse(Mitgliedschaft.objects.aktiv().filter(gruppe=self.kl9a, schueler=s).exists())

    def test_stammklassen_zuerst_ags_ohne_faecher(self):
        self.anmelden("verwaltung")
        r = self.client.get(reverse("zuordnung"))
        self.assertEqual(r.context["gruppe"].typ, Gruppe.STAMMKLASSE)
        ag = Gruppe.objects.get(schuljahr=self.sj, name="AG Robotik")
        r = self.client.get(reverse("zuordnung") + f"?gruppe={ag.pk}&ansicht=faecher")
        self.assertEqual(r.context["ansicht"], "schueler")
        self.assertNotContains(r, 'class="zo-reiter"')
