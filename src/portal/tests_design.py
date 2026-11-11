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

    def test_designs_und_gruppen(self):
        from .models import DESIGN_GRUPPEN, design_gruppen

        codes = [c for c, _ in DESIGNS]
        self.assertEqual(codes[0], "standard")
        self.assertTrue({"standard", "latte", "mocha", "hell", "dunkel", "ozean", "sepia", "kontrast", "nord", "frappe", "macchiato"}
                        <= set(codes))
        self.assertEqual(len(codes), len(set(codes)))
        self.assertTrue(all(len(c) <= 12 for c in codes))            # Länge des Datenbankfeldes
        gruppiert = [c for _t, liste in DESIGN_GRUPPEN for c in liste]
        self.assertEqual(sorted(gruppiert), sorted(codes))           # jedes Design steht genau einmal im Menü
        self.assertEqual([len(l) for _t, l in design_gruppen()], [1, 5, 5])

    def test_menue_zeigt_alle_designs_in_gruppen(self):
        r = self.client.get(reverse("login"))
        for code, name in DESIGNS:
            self.assertContains(r, f'name="design" value="{code}"')
            self.assertContains(r, f"design-muster-{code}")
        self.assertContains(r, 'class="designmenue-gruppe"', count=3)

    def test_jedes_design_laesst_sich_waehlen(self):
        self.client.login(username="chef", password=PW)
        for code, _name in DESIGNS:
            self.waehlen(code)
            self.assertEqual(User.objects.get(username="chef").einstellung.design, code)
            for url in (reverse("start"), reverse("admin:index")):
                self.assertContains(self.client.get(url), f'data-design="{code}"')

    def test_erzeugte_designs_aktuell_und_kontrastreich(self):
        import importlib.util

        pfad = Path(settings.BASE_DIR).parent / "tools" / "designs_erzeugen.py"
        if not pfad.exists():                                         # im Container liegt nur src/
            self.skipTest("tools/designs_erzeugen.py nicht vorhanden")
        spec = importlib.util.spec_from_file_location("designs_erzeugen", pfad)
        modul = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modul)
        self.assertEqual(modul.kontrast_maengel(), [])
        self.assertEqual(set(modul.PALETTEN), {c for c, _ in DESIGNS} - {"standard", "latte", "mocha"})
        for datei, erzeuger in modul.DATEIEN.items():
            text = (STATIC / datei).read_text(encoding="utf-8")
            self.assertEqual(modul.neuer_inhalt(text, erzeuger()), text, f"{datei} veraltet – tools/designs_erzeugen.py ausführen")

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
            for code, _name in DESIGNS:
                if code != "standard":
                    self.assertIn(f'[data-design="{code}"]', css, datei)
        portal = (STATIC / "portal.css").read_text()
        # Catppuccin-Grundfarben: Latte base/text/mauve, Mocha base/text/mauve
        for farbe in ("#eff1f5", "#4c4f69", "#8839ef", "#1e1e2e", "#cdd6f4", "#cba6f7"):
            self.assertIn(farbe, portal)
