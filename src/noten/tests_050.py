"""Tests 0.5.0: Noteneingabe mit Statistik, Namensfilter, Tastenkürzeln und Entwurf im Browser."""
import json
import re

from django.contrib.auth.models import User
from django.urls import reverse

from .ansichten import entwurf_schluessel
from .models import Leistungsnachweis
from .tests_eingabe import Grundlage


class KomfortTest(Grundlage):
    def seite(self):
        self.anmelden("lehrkraft")
        return self.client.get(reverse("noten_eintragen", args=[self.u.pk]) + f"?ordner={self.q1.pk}")

    def test_seite_bringt_statistik_filter_und_kuerzel(self):
        r = self.seite()
        for teil in ('id="ne-statistik"', 'id="ne-st-schnitt"', 'id="ne-filter"', 'id="ne-nur-leer"',
                     'id="ne-kuerzel"', 'id="ne-entwurf"', 'id="ne-status"'):
            self.assertContains(r, teil)

    def test_werte_der_skala_fuer_den_durchschnitt(self):
        r = self.seite()
        roh = re.search(r'<script id="ne-werte" type="application/json">(.*?)</script>', r.content.decode(), re.S).group(1)
        werte = json.loads(roh)
        stufen = {s.bezeichnung: float(s.wert) for s in self.u.skala.stufen.all()}
        self.assertEqual(werte, stufen)
        self.assertTrue(stufen)

    def test_entwurfsschluessel_je_konto_kurs_und_nachweis(self):
        r = self.seite()
        benutzer = User.objects.get(username="lehrkraft")
        schluessel = entwurf_schluessel(benutzer, self.u, None)
        self.assertEqual(schluessel, f"ne.{benutzer.pk}.{self.u.pk}.neu")
        self.assertContains(r, f'data-entwurf="{schluessel}"')
        self.assertRegex(schluessel, r"^ne\.[\w.]+$")

    def test_speichern_nennt_dem_browser_den_erledigten_entwurf(self):
        self.anmelden("lehrkraft")
        benutzer = User.objects.get(username="lehrkraft")
        s1 = self.schueler[0]
        r = self.client.post(reverse("noten_eintragen", args=[self.u.pk]), self.eingabe_daten(**{f"n_{s1.pk}": "2"}))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r.cookies["ne_gespeichert"].value, f"ne.{benutzer.pk}.{self.u.pk}.neu")
        self.assertFalse(r.cookies["ne_gespeichert"]["httponly"])      # das Skript muss ihn lesen können
        ln = Leistungsnachweis.objects.filter(unterricht=self.u).latest("pk")
        r = self.client.post(reverse("noten_bearbeiten", args=[self.u.pk, ln.pk]), self.eingabe_daten(**{f"n_{s1.pk}": "3"}))
        self.assertEqual(r.cookies["ne_gespeichert"].value, f"ne.{benutzer.pk}.{self.u.pk}.{ln.pk}")

    def test_fehlerhafte_eingabe_setzt_keinen_cookie(self):
        self.anmelden("lehrkraft")
        s1 = self.schueler[0]
        r = self.client.post(reverse("noten_eintragen", args=[self.u.pk]), self.eingabe_daten(**{f"n_{s1.pk}": "7"}))
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("ne_gespeichert", r.cookies)
