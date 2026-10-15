"""Kursauswahl „Mein Unterricht“ (ab 0.4.7.1): Menüband, Startseite, Kurs wechseln, viele Kurse."""
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from stammdaten.models import Fach, Gruppe, Personalprofil

from . import kurswahl
from .models import Notenskala, Unterricht

PW = "Test-Passwort-123"


class KurswahlTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))
        cls.u1 = Unterricht.objects.select_related("lehrkraft", "abschnitt").get(fach__kuerzel="CH", gruppe__name="9a")
        cls.lk = cls.u1.lehrkraft
        # viele Kurse: dieselbe Lehrkraft unterrichtet zusätzlich weitere Fächer in 9a und 9b
        skala = Notenskala.objects.get(name__startswith="Sek I –")
        belegt = set(Unterricht.objects.filter(abschnitt=cls.u1.abschnitt).values_list("gruppe_id", "fach_id"))
        cls.neu = []
        for g in Gruppe.objects.filter(name__in=["9a", "9b"], schuljahr=cls.u1.abschnitt.schuljahr):
            for f in Fach.objects.order_by("reihenfolge")[:12]:
                if (g.pk, f.pk) not in belegt and len(cls.neu) < 8:
                    cls.neu.append(Unterricht.objects.create(abschnitt=cls.u1.abschnitt, gruppe=g, fach=f, lehrkraft=cls.lk, skala=skala))

    def setUp(self):
        self.assertTrue(self.client.login(username="lehrkraft", password=PW))

    def test_viele_kurse_als_auswahlliste(self):
        anzahl = Unterricht.objects.filter(lehrkraft=self.lk, abschnitt__schuljahr=self.u1.abschnitt.schuljahr).count()
        self.assertGreater(anzahl, 8)
        r = self.client.get(reverse("start"))
        self.assertContains(r, 'id="kw-start"')                              # Startseite
        self.assertContains(r, 'id="kw-band"')                               # Menüband
        self.assertContains(r, f'<option value="{self.neu[-1].pk}"', count=2)
        self.assertContains(r, "<optgroup", count=2)
        self.assertNotContains(r, 'class="mb-gross" href="/noten/unterricht/')  # keine Kachel je Kurs mehr

    def test_oeffnen_merkt_letzten_kurs(self):
        ziel = self.neu[2]
        for z, name in (("uebersicht", "notenuebersicht"), ("eintragen", "noten_eintragen"), ("zeugnis", "zeugnis_unterricht"),
                        ("unbekannt", "notenuebersicht")):
            r = self.client.get(reverse("kurs_oeffnen"), {"u": ziel.pk, "ziel": z})
            self.assertRedirects(r, reverse(name, args=[ziel.pk]), fetch_redirect_response=False)
        self.assertEqual(self.client.session[kurswahl.SITZUNG], ziel.pk)
        r = self.client.get(reverse("start"))
        self.assertContains(r, f'<option value="{ziel.pk}" selected>')
        self.assertEqual(self.client.get(reverse("kurs_oeffnen"), {"u": 999999}).status_code, 404)

    def test_kurs_wechseln_auf_kursseiten(self):
        for url, ziel in ((reverse("notenuebersicht", args=[self.u1.pk]), "uebersicht"),
                          (reverse("noten_eintragen", args=[self.u1.pk]), "eintragen"),
                          (reverse("bewertungsstruktur", args=[self.u1.pk]), "struktur"),
                          (reverse("zeugnis_unterricht", args=[self.u1.pk]), "zeugnis")):
            r = self.client.get(url)
            self.assertContains(r, f'id="kw-wechsel-{ziel}"', msg_prefix=url)
            self.assertContains(r, f'<option value="{self.u1.pk}" selected>', msg_prefix=url)

    def test_fremder_kurs_ohne_wechsel(self):
        """Wer einen fremden Kurs ansieht (z. B. Schulleitung), bekommt keinen „Kurs wechseln“ mit fremder Vorauswahl."""
        self.client.logout()
        self.assertTrue(self.client.login(username="schulleitung", password=PW))
        r = self.client.get(reverse("notenuebersicht", args=[self.u1.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'id="kw-wechsel-uebersicht"')

    def test_ohne_unterricht_keine_auswahl(self):
        self.client.logout()
        self.assertTrue(self.client.login(username="verwaltung", password=PW))
        r = self.client.get(reverse("start"))
        self.assertNotContains(r, 'id="kw-start"')
        self.assertNotContains(r, 'id="kw-band"')
