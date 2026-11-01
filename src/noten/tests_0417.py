"""Tests 0.4.17.0: Höchstzahl je Halbjahr (Notenregel), neue Spalten direkt in der Notentabelle, Gewicht im Kopf, Zeugnisnote."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from portal.klassenunterricht import speichern as unterricht_speichern
from stammdaten.models import Abschnitt, Fach, Gruppe, Personalprofil, Schuljahr

from .klassenansicht import spalte_anlegen
from .models import Bewertungsordner, Leistungsnachweis, Note, Unterricht, Zeugnisnote

PW = "Test-Passwort-123"


class Version0417Test(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))
        sj = Schuljahr.aktuelles()
        cls.hj1 = Abschnitt.objects.get(schuljahr=sj, nummer=1)
        cls.kl8a = Gruppe.objects.get(schuljahr=sj, name="8a")
        fach = Fach.objects.get(kuerzel="CH")
        Unterricht.objects.filter(gruppe=cls.kl8a, fach=fach, abschnitt=cls.hj1).delete()
        unterricht_speichern(cls.kl8a, {(fach.pk, cls.hj1.pk): (None, Personalprofil.objects.get(kuerzel="KRA").pk)})
        cls.u = Unterricht.objects.get(gruppe=cls.kl8a, fach=fach, abschnitt=cls.hj1)
        cls.ka = Bewertungsordner.objects.get(unterricht=cls.u, vorgegeben=Bewertungsordner.KLAUSUR)
        cls.somi = Bewertungsordner.objects.get(unterricht=cls.u, vorgegeben=Bewertungsordner.MITARBEIT)
        cls.s = cls.u.schueler().first()

    def url(self):
        return reverse("noten_klassen") + f"?abschnitt={self.hj1.pk}&klasse={self.kl8a.pk}&kurs={self.u.pk}"

    def test_notenregel_setzt_hoechstzahlen(self):
        self.assertEqual((self.ka.max_nachweise, self.somi.max_nachweise), (2, 30))

    def test_hoechstens_zwei_klassenarbeiten(self):
        for _ in range(2):
            ln, fehler = spalte_anlegen(self.u, self.ka.pk)
            self.assertIsNone(fehler)
        self.assertEqual(ln.titel, "Klassenarbeit 2")
        ln, fehler = spalte_anlegen(self.u, self.ka.pk)
        self.assertIsNone(ln)
        self.assertIn("höchstens 2", fehler)
        dritte = Leistungsnachweis(unterricht=self.u, ordner=self.ka, titel="KA 3", datum=self.hj1.beginn)
        with self.assertRaises(ValidationError):
            dritte.full_clean()

    def test_somi_spalte_gewicht_und_note_ueber_die_tabelle(self):
        self.client.login(username="lehrkraft", password=PW)
        r = self.client.post(self.url(), {"aktion": f"spalte:{self.somi.pk}"})
        self.assertEqual(r.status_code, 302)
        ln = Leistungsnachweis.objects.get(ordner=self.somi)
        self.assertTrue(ln.titel.startswith("SoMi"))
        self.assertTrue(r.url.endswith(f"neu={ln.pk}"))
        r = self.client.post(self.url(), {"aktion": "speichern", f"g_{ln.pk}": "0,5", f"go_{ln.pk}": "1",
                                          f"n_{ln.pk}_{self.s.pk}": "2", f"o_{ln.pk}_{self.s.pk}": ""})
        self.assertEqual(r.status_code, 302)
        ln.refresh_from_db()
        self.assertEqual(ln.gewicht, Decimal("0.5"))
        self.assertEqual(Note.objects.get(leistungsnachweis=ln, schueler=self.s).stufe.bezeichnung, "2")
        r = self.client.post(self.url(), {"aktion": "speichern", f"g_{ln.pk}": "0", f"go_{ln.pk}": "0,5"}, follow=True)
        self.assertContains(r, "nicht gültig")
        ln.refresh_from_db()
        self.assertEqual(ln.gewicht, Decimal("0.5"))

    def test_zeugnisnote_in_der_tabelle_festsetzen_und_zuruecksetzen(self):
        ln, _f = spalte_anlegen(self.u, self.somi.pk)
        Note.objects.filter(leistungsnachweis=ln, schueler=self.s).update(
            stufe=self.u.skala.stufen.get(bezeichnung="2"))
        self.client.login(username="lehrkraft", password=PW)
        r = self.client.get(self.url())
        self.assertContains(r, f'name="zk_{self.s.pk}"')
        self.client.post(self.url(), {"aktion": "speichern", f"zk_{self.s.pk}": "3", f"zko_{self.s.pk}": ""})
        z = Zeugnisnote.objects.get(unterricht=self.u, schueler=self.s)
        self.assertEqual((z.stufe.bezeichnung, z.quelle), ("3", "kurs"))
        self.client.post(self.url(), {"aktion": "speichern", f"zk_{self.s.pk}": "", f"zko_{self.s.pk}": "3"})
        self.assertFalse(Zeugnisnote.objects.filter(unterricht=self.u, schueler=self.s, quelle="kurs").exists())

    def test_notenregeln_seite_zeigt_hoechstzahlen(self):
        self.client.login(username="schulleitung", password=PW)
        r = self.client.get(reverse("klausurregeln"))
        self.assertContains(r, "Höchstens Klausuren")
        self.assertContains(r, "2 / 30")
