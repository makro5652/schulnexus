"""Tests 0.7.0: Hilfe und Dokumentation (Hilfetexte, Einblendung, passende Hilfe je Seite) und Versionshinweis unten."""
import re

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import formats
from django.core.management import call_command

from config.version import VERSION, VERSION_DATUM

from . import hilfe as H

PW = "Test-Passwort-123"
DYNAMISCH = {"Meine Klassen", "Stufenkoordination", "Mein Unterricht"}     # Gruppen mit Befehlen je Klasse oder Kurs


class HilfetexteTest(TestCase):
    def test_alle_themen_vollstaendig(self):
        themen = H.alle()
        self.assertGreaterEqual(len(themen), 25)
        for t in themen.values():
            self.assertIn(t.art, H.ARTEN, t.slug)
            self.assertTrue(t.titel and t.kurz, t.slug)
            self.assertGreater(len(t.text), 400, f"{t.slug}: zu kurz")
            self.assertNotIn("<script", t.html)
        self.assertIn(H.STANDARD, themen)
        self.assertIn("schuljahreswechsel", themen)

    def test_verweise_zeigen_auf_vorhandene_themen(self):
        themen = H.alle()
        for t in themen.values():
            for ziel in re.findall(r'data-hilfe="([^"]+)"', t.html):
                self.assertIn(ziel, themen, f"{t.slug} verweist auf unbekanntes Thema {ziel}")

    def test_umwandeln_ist_sicher(self):
        html, abschnitte = H.umwandeln('## Titel\n\nText <script>x</script> [a](https://boese.example) [b](/noten/) [c](//x) '
                                       '**f** `c` [[Strg]]\n\n1. eins\n   - unter\n2. zwei\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n> Hinweis')
        self.assertNotIn("<script", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("boese.example", html)
        self.assertNotIn('href="//x"', html)
        self.assertIn('<a href="/noten/">b</a>', html)
        self.assertIn("<kbd>Strg</kbd>", html)
        self.assertIn("<ol><li>", html)
        self.assertIn("<ul><li>", html)
        self.assertIn("<table>", html)
        self.assertIn('class="hp-hinweis"', html)
        self.assertEqual(abschnitte, [("titel", "Titel")])

    def test_passendes_thema_je_seite(self):
        self.assertEqual(H.thema_fuer("/laufbahn/"), "schuljahreswechsel")
        self.assertEqual(H.thema_fuer("/laufbahn/wechsel/3/"), "schuljahreswechsel")
        self.assertEqual(H.thema_fuer("/laufbahn/archiv/"), "abgang-und-archiv")
        self.assertEqual(H.thema_fuer("/noten/unterricht/7/eintragen/"), "noten-eintragen")
        self.assertEqual(H.thema_fuer("/noten/unterricht/7/notentabelle/"), "excel-notentabelle")
        self.assertEqual(H.thema_fuer("/zeugnisse/konferenz/2/"), "konferenz")
        self.assertEqual(H.thema_fuer("/zeugnisse/12/"), "zeugnisse")
        self.assertEqual(H.thema_fuer("/"), "menue-start")
        self.assertEqual(H.thema_fuer("/verwaltung/fehlzeiten/fehlzeit/"), "fehlzeiten")
        self.assertEqual(H.thema_fuer("/gibt/es/nicht/", "personal"), "menue-personal")
        self.assertEqual(H.thema_fuer("/gibt/es/nicht/", ""), H.STANDARD)


class HilfeSeitenTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))

    def anmelden(self, name):
        self.client.logout()
        self.assertTrue(self.client.login(username=name, password=PW))

    def test_nur_angemeldet(self):
        r = self.client.get(reverse("hilfe"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("login"), r.url)

    def test_seiten_und_teile(self):
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("hilfe"))
        self.assertContains(r, "Hilfe und Anleitungen")
        for slug in H.alle():
            r = self.client.get(reverse("hilfe_thema", args=[slug]))
            self.assertEqual(r.status_code, 200, slug)
            teil = self.client.get(reverse("hilfe_thema", args=[slug]), {"teil": "1"})
            self.assertNotContains(teil, "<html")
            self.assertContains(teil, f'data-slug="{slug}"')
        self.assertEqual(self.client.get(reverse("hilfe_thema", args=["gibt-es-nicht"])).status_code, 404)
        daten = self.client.get(reverse("hilfe_suche")).json()
        self.assertEqual({t["slug"] for t in daten["themen"]}, set(H.alle()))
        self.assertTrue(all(t["text"] for t in daten["themen"]))

    def test_knopf_und_einblendung_auf_jeder_seite(self):
        self.anmelden("lehrkraft")
        for url, thema in ((reverse("start"), "menue-start"), (reverse("noten_klassen"), "noten-eintragen"),
                           (reverse("admin:index"), "menue-verwaltung")):
            r = self.client.get(url)
            self.assertContains(r, 'id="hp-knopf"', msg_prefix=url)
            self.assertContains(r, 'id="hp"', msg_prefix=url)
            self.assertContains(r, f'data-thema="{thema}"', msg_prefix=url)
            self.assertContains(r, "hilfe.js", msg_prefix=url)

    def test_jedes_menue_ist_erklaert(self):
        """Für jede Karte des Menübands gibt es ein Hilfethema, das jede Gruppe und jeden Befehl nennt."""
        from .navigation import menueband

        self.anmelden("it")
        mb = menueband(self.client.get(reverse("start")).wsgi_request)
        menues = {t.karte: t for t in H.alle().values() if t.art == "menue"}
        for karte in mb["karten"]:
            self.assertIn(karte["schluessel"], menues, f"Kein Hilfethema für die Karte {karte['titel']}")
            text = menues[karte["schluessel"]].text
            for g in karte["gruppen"]:
                self.assertIn(str(g.titel), text, f"{karte['schluessel']}: Gruppe {g.titel} fehlt")
                if str(g.titel) in DYNAMISCH:
                    continue
                for b in g.befehle:
                    self.assertIn(str(b["titel"]), text, f"{karte['schluessel']}: Befehl {b['titel']} fehlt")

    def test_hilfe_als_befehl_im_menueband(self):
        self.anmelden("lehrkraft")
        self.assertContains(self.client.get(reverse("start")), f'href="{reverse("hilfe")}"')

    def test_version_und_datum_unten(self):
        datum = formats.date_format(VERSION_DATUM, "SHORT_DATE_FORMAT")
        r = self.client.get(reverse("login"))
        self.assertContains(r, f"Version {VERSION}")
        self.assertContains(r, datum)
        self.assertContains(r, f'datetime="{VERSION_DATUM.isoformat()}"')
        self.anmelden("it")
        r = self.client.get(reverse("admin:index"))
        self.assertContains(r, f"Version {VERSION}")
        self.assertContains(r, datum)
        self.assertEqual(User.objects.filter(username="it").count(), 1)
