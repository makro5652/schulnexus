"""Tests 0.8.0: Oberfläche „Skizzenbuch“ – Design, Kopfzeile, Bereichsleiste, Kacheln, Bereichsseite, Befehlsverzeichnis, Schriften."""
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import DESIGNS

PW = "Test-Passwort-123"
STATIC = Path(settings.BASE_DIR) / "static"


def verzeichnis_urls(html):
    block = html[html.index('class="sk-verzeichnis"'):html.index("</header>")]
    return re.findall(r'<a href="([^"]+)"', block.split('class="bs"')[0])


def menueband_urls(html):
    block = html[html.index('id="menueband"'):html.index("</header>")]
    block = block.split('<aside class="hp"')[0]
    return re.findall(r'<a class="[^"]*" href="([^"]+)" title=', block)


class SkizzeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))

    def anmelden(self, name="lehrkraft", design=None):
        self.client.logout()
        self.assertTrue(self.client.login(username=name, password=PW))
        if design:
            self.client.post(reverse("design_wechseln"), {"design": design, "next": "/"})

    def test_design_waehlbar_und_im_menue(self):
        self.assertIn("skizze", dict(DESIGNS))
        self.anmelden()
        self.client.post(reverse("design_wechseln"), {"design": "skizze", "next": "/"})
        self.assertEqual(User.objects.get(username="lehrkraft").einstellung.design, "skizze")
        r = self.client.get(reverse("start"))
        self.assertContains(r, 'data-design="skizze"')
        self.assertContains(r, 'value="skizze" aria-current="true"')       # Rückweg: das Menü zeigt die Wahl und alle anderen
        self.assertContains(r, 'name="design" value="standard"')
        self.assertContains(r, "design-muster-skizze")
        self.assertIn("design-muster-skizze", (STATIC / "menueband.css").read_text())

    def test_startseite_im_skizzenbuch(self):
        self.anmelden(design="skizze")
        r = self.client.get(reverse("start"))
        for teil in ('class="sk-kopf"', 'class="sk-bereiche"', 'class="sk-kacheln"', 'id="mb-befehle-oeffnen"', 'id="hp-knopf"',
                     'id="bs"', 'id="mb-schnell"', "skizze.css", "skizze_start.css", "skizze_seiten.css", '<body class="sk">'):
            self.assertContains(r, teil)
        self.assertNotContains(r, 'class="mb-reiter"')
        self.assertNotContains(r, '<header class="mb"')
        self.assertContains(r, "Was möchten Sie tun?")
        self.assertNotContains(r, 'class="sk-weg')                           # auf der Startseite keine Wegleiste

    def test_anderes_design_unveraendert(self):
        for design in ("standard", "hell", "mocha"):
            self.anmelden(design=design)
            r = self.client.get(reverse("start"))
            self.assertContains(r, 'class="mb-reiter"')
            self.assertNotContains(r, "sk-kopf")
            self.assertNotContains(r, "sk-kacheln")
            self.assertNotContains(r, "skizze.css")

    def test_anmeldeseite_nur_marke_sprache_design(self):
        self.client.cookies["design"] = "skizze"
        r = self.client.get(reverse("login"))
        self.assertContains(r, 'class="sk-kopf"')
        self.assertContains(r, 'class="sk-m1"')
        self.assertContains(r, 'class="sprachmenue designmenue"')
        for teil in ("sk-bereiche", "sk-suche", "sk-weg", 'id="bs"', 'id="hp"'):
            self.assertNotContains(r, teil)

    def test_bereichsleiste_und_marke(self):
        self.anmelden("schulleitung", "skizze")
        r = self.client.get(reverse("start"))
        html = r.content.decode()
        leiste = html[html.index('class="sk-bereiche"'):]
        leiste = leiste[:leiste.index("</nav>")]
        farben = re.findall(r'sk-farbe-(\d)', leiste)
        self.assertGreaterEqual(len(farben), 4)
        self.assertTrue(all("1" <= f <= "7" for f in farben))
        self.assertEqual(len(re.findall(r'aria-current="true"', leiste)), 1)
        self.assertIn(f'href="{reverse("start")}"', leiste)
        self.assertIn(f'href="{reverse("bereich", args=["unterricht"])}"', leiste)
        self.assertContains(r, 'class="sk-m1">Schul<')
        self.assertContains(r, 'class="sk-m3">xus<')
        self.assertContains(r, 'aria-label="Schulnexus"')
        self.assertContains(r, 'class="sk-marke-unter"')

    def test_kacheln(self):
        self.anmelden("schulleitung", "skizze")
        html = self.client.get(reverse("start")).content.decode()
        kacheln = re.findall(r'<article class="sk-kachel sk-farbe-\d">(.*?)</article>', html, re.S)
        self.assertGreaterEqual(len(kacheln), 4)
        for k in kacheln:
            self.assertIn("sk-kachel-alle", k)
            self.assertLessEqual(k.count("<li>"), 4)
        self.assertNotIn(f'href="{reverse("bereich", args=["start"])}"', html)

    def test_farbe_je_karte_ueberall_gleich(self):
        self.anmelden("schulleitung", "skizze")
        start = self.client.get(reverse("start")).content.decode()
        bereich = self.client.get(reverse("bereich", args=["unterricht"])).content.decode()
        f_leiste = re.search(r'sk-bereich sk-farbe-(\d)[^>]*href="/bereich/unterricht/"', start).group(1)
        f_kachel = re.search(r'<article class="sk-kachel sk-farbe-(\d)">\s*<h3><a href="/bereich/unterricht/"', start).group(1)
        f_seite = re.search(r'<header class="sk-bereichskopf sk-farbe-(\d)">', bereich).group(1)
        self.assertEqual({f_leiste, f_kachel, f_seite}, {f_leiste})

    def test_bereichsseite(self):
        self.anmelden("lehrkraft", "skizze")
        r = self.client.get(reverse("bereich", args=["unterricht"]))
        self.assertEqual(r.status_code, 200)
        for teil in ('class="sk-bereichskopf', "<h1>", 'class="sk-gruppe"', 'class="sk-befehlskarten"', 'class="sk-befehlskarte'):
            self.assertContains(r, teil)
        self.assertContains(r, 'class="sk-befehlskarte gross"')
        self.assertContains(r, 'class="sk-weg')                              # Wegleiste: Bereich ohne Befehle
        self.assertContains(r, 'class="sk-weg-bereich"')
        html = r.content.decode()
        self.assertEqual(len(re.findall(r'aria-current="true"', html[html.index('class="sk-bereiche"'):html.index('class="sk-weg')])), 1)
        self.assertEqual(self.client.get(reverse("bereich", args=["gibt-es-nicht"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("bereich", args=["system"])).status_code, 404)    # Lehrkraft hat keine Karte „System“

    def test_bereichsseite_start_leitet_um(self):
        self.anmelden()
        self.assertRedirects(self.client.get(reverse("bereich", args=["start"])), reverse("start"))

    def test_bereichsseite_nur_angemeldet(self):
        r = self.client.get(reverse("bereich", args=["unterricht"]))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("login"), r.url)

    def test_bereichsseite_auch_mit_menueband(self):
        self.anmelden("lehrkraft", "standard")
        r = self.client.get(reverse("bereich", args=["unterricht"]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'class="mb-reiter"')

    def test_wegleiste_zeigt_gruppe_des_aktiven_befehls(self):
        self.anmelden("lehrkraft", "skizze")
        r = self.client.get(reverse("noten_klassen"))
        html = r.content.decode()
        weg = html[html.index('class="sk-weg'):]
        weg = weg[:weg.index("</nav>")]
        self.assertIn('class="sk-weg-bereich"', weg)
        self.assertIn(">Unterricht<", weg)
        aktiv = re.findall(r'<a class="sk-weg-befehl aktiv" href="([^"]+)"[^>]*aria-current="page"', weg)
        self.assertEqual(aktiv, [reverse("noten_klassen")])
        self.assertIn(reverse("leistungsvorgaben"), weg)                     # Geschwister derselben Gruppe
        self.assertNotIn(reverse("zeugnisse"), weg)                          # andere Gruppe

    def test_befehlsverzeichnis_wie_menueband(self):
        self.anmelden("schulleitung", "skizze")
        skizze = verzeichnis_urls(self.client.get(reverse("start")).content.decode())
        self.anmelden("schulleitung", "standard")
        band = menueband_urls(self.client.get(reverse("start")).content.decode())
        self.assertGreater(len(band), 20)
        self.assertEqual(sorted(skizze), sorted(band))
        r = self.client.get(reverse("start"))
        self.assertNotContains(r, "sk-verzeichnis")

    def test_verzeichnis_hat_struktur_fuer_befehle_js(self):
        self.anmelden("schulleitung", "skizze")
        html = self.client.get(reverse("start")).content.decode()
        verz = html[html.index('class="sk-verzeichnis"'):]
        self.assertIn('id="mb-reiter-unterricht">', verz)
        self.assertIn('class="mb-band" aria-labelledby="mb-reiter-unterricht"', verz)
        self.assertIn('class="mb-gruppentitel"', verz)
        self.assertRegex(verz, r'<a href="[^"]+" title="[^"]*"><svg viewBox="0 0 24 24" aria-hidden="true"><use href="#s-\w+"/></svg><span>')

    def test_verwaltungsoberflaeche_laedt_skizze_css(self):
        self.anmelden("verwaltung", "skizze")
        r = self.client.get(reverse("admin:index"))
        self.assertContains(r, "skizze.css")
        self.assertContains(r, 'class="sk-kopf"')
        self.assertContains(r, 'data-design="skizze"')
        self.assertNotContains(r, 'class="mb-reiter"')

    def test_hilfethema_vorhanden(self):
        from . import hilfe

        self.assertIn("oberflaeche-skizzenbuch", hilfe.alle())
        self.anmelden("lehrkraft", "skizze")
        self.assertContains(self.client.get(reverse("bereich", args=["termine"])), 'data-thema="menue-termine"')

    def test_schriften_und_css_vorhanden(self):
        css = (STATIC / "skizze.css").read_text()
        dateien = re.findall(r'url\("(schrift/[^"]+)"\)', css)
        self.assertEqual(len(dateien), 7)
        for d in dateien:
            self.assertTrue((STATIC / d).is_file(), d)
        for name in ("skizze_start.css", "skizze_seiten.css"):
            self.assertTrue((STATIC / name).is_file(), name)
        for variable in ("--sk-papier", "--sk-tinte", "--sk-marker", "--sk-schrift", "--sk-hand", "--sk-tuerkis-kraeftig"):
            self.assertIn(variable + ":", css)
        for n in range(1, 8):
            self.assertIn(f".sk-farbe-{n} ", css)
