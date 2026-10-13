"""Tests für die Designauswahl (Standard, Catppuccin Latte, Catppuccin Mocha) – seit Version 0.4.2.8."""
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import DESIGN_COOKIE, DESIGNS, Benutzereinstellung

PW = "Test-Passwort-123"
STATIC = Path(settings.BASE_DIR) / "static"


class DesignwahlTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.chef = User.objects.create_superuser("chef", "", PW)
        cls.zweite = User.objects.create_superuser("zweite", "", PW)

    def waehlen(self, design, ziel="/"):
        return self.client.post(reverse("design_wechseln"), {"design": design, "next": ziel})

    def test_drei_designs(self):
        self.assertEqual([c for c, _ in DESIGNS], ["standard", "latte", "mocha"])

    def test_standard_ohne_wahl(self):
        r = self.client.get(reverse("login"))
        self.assertContains(r, 'data-design="standard"')
        self.assertContains(r, 'class="sprachmenue designmenue"')
        self.assertContains(r, "Catppuccin Latte")
        self.assertContains(r, "Catppuccin Mocha")

    def test_menue_neben_sprachauswahl(self):
        html = self.client.get(reverse("login")).content.decode()
        sprache, design = html.index('class="sprachmenue"'), html.index('class="sprachmenue designmenue"')
        self.assertLess(sprache, design)
        self.assertNotIn("mb-konto", html[sprache:design])

    def test_wahl_ohne_anmeldung_per_cookie(self):
        r = self.waehlen("mocha", reverse("login"))
        self.assertRedirects(r, reverse("login"), fetch_redirect_response=False)
        self.assertEqual(r.cookies[DESIGN_COOKIE].value, "mocha")
        self.assertTrue(r.cookies[DESIGN_COOKIE]["httponly"])
        self.assertContains(self.client.get(reverse("login")), 'data-design="mocha"')

    def test_nur_post_und_nur_bekannte_designs(self):
        self.assertEqual(self.client.get(reverse("design_wechseln")).status_code, 405)
        r = self.waehlen("neon")
        self.assertNotIn(DESIGN_COOKIE, r.cookies)
        self.client.cookies[DESIGN_COOKIE] = "<script>"
        self.assertContains(self.client.get(reverse("login")), 'data-design="standard"')

    def test_kein_offener_redirect(self):
        self.assertEqual(self.waehlen("latte", "https://boese.example.com/").url, "/")

    def test_wahl_wird_im_konto_gespeichert_und_gilt_ueberall(self):
        self.client.login(username="chef", password=PW)
        self.waehlen("latte")
        self.assertEqual(User.objects.get(username="chef").einstellung.design, "latte")
        self.client.cookies.pop(DESIGN_COOKIE, None)          # anderes Gerät: Konto entscheidet
        r = self.client.get(reverse("start"))
        self.assertContains(r, 'data-design="latte"')
        self.assertContains(r, 'value="latte" aria-current="true"')
        r = self.client.get(reverse("admin:index"))
        self.assertContains(r, 'data-design="latte"')
        self.assertContains(r, "design.js")
        self.assertContains(r, 'class="sprachmenue designmenue"')

    def test_konto_hat_vorrang_vor_cookie(self):
        Benutzereinstellung.objects.update_or_create(benutzer=self.zweite, defaults={"design": "standard"})
        self.client.cookies[DESIGN_COOKIE] = "mocha"
        self.client.login(username="zweite", password=PW)
        self.assertContains(self.client.get(reverse("start")), 'data-design="standard"')

    def test_erste_anmeldung_uebernimmt_gewaehltes_design(self):
        self.waehlen("mocha", reverse("login"))
        self.client.post(reverse("login"), {"username": "zweite", "password": PW})
        self.assertEqual(User.objects.get(username="zweite").einstellung.design, "mocha")

    def test_druckansichten_tragen_design(self):
        for name in ("druck.html", "protokoll.html", "gefaehrdung.html"):
            text = (Path(settings.BASE_DIR) / "templates" / "zeugnisse" / name).read_text()
            self.assertIn("data-design=", text, name)

    def test_css_enthaelt_alle_designs(self):
        for datei in ("portal.css", "menueband.css", "verwaltung.css"):
            css = (STATIC / datei).read_text()
            for code in ("latte", "mocha"):
                self.assertIn(f'[data-design="{code}"]', css, datei)
        portal = (STATIC / "portal.css").read_text()
        # Catppuccin-Grundfarben: Latte base/text/mauve, Mocha base/text/mauve
        for farbe in ("#eff1f5", "#4c4f69", "#8839ef", "#1e1e2e", "#cdd6f4", "#cba6f7"):
            self.assertIn(farbe, portal)
