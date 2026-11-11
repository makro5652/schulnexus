"""Tests für die Zweisprachigkeit (Deutsch/Englisch) – seit Version 0.4.1.1."""
from pathlib import Path

import polib
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from config.version import VERSION
from noten.models import Unterricht
from stammdaten.models import Fach, Gruppe, Zusatzfeld

from .models import Benutzereinstellung

PW = "Test-Passwort-123"
PO = Path(settings.BASE_DIR) / "locale" / "en" / "LC_MESSAGES" / "django.po"


class UebersetzungVollstaendig(TestCase):
    """Schlägt fehl, sobald ein neuer Text ohne englische Übersetzung im Katalog steht."""

    def test_alle_texte_uebersetzt(self):
        po = polib.pofile(str(PO))
        offen = [e.msgid for e in po if not e.obsolete and (not e.translated() or "fuzzy" in e.flags)]
        self.assertEqual(offen, [], "Fehlende Übersetzungen – siehe tools/sprachdateien.py")

    def test_platzhalter_stimmen_ueberein(self):
        import re

        muster = re.compile(r"%\(\w+\)s|\{\{\s*\w+\s*\}\}")
        for e in polib.pofile(str(PO)):
            if e.msgid_plural:
                continue
            self.assertEqual(sorted(muster.findall(e.msgid)), sorted(muster.findall(e.msgstr)), e.msgid)

    def test_mo_datei_aktuell(self):
        mo = PO.with_suffix(".mo")
        self.assertTrue(mo.exists())
        katalog = {(e.msgctxt, e.msgid): e.msgstr for e in polib.mofile(str(mo))}
        for e in polib.pofile(str(PO)):
            if not e.msgid_plural:
                self.assertEqual(katalog.get((e.msgctxt, e.msgid)), e.msgstr, f"django.mo veraltet: {e.msgid!r} – bitte kompilieren")


class SprachwahlTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))

    def tearDown(self):
        translation.activate(settings.LANGUAGE_CODE)

    def englisch_waehlen(self, ziel="/"):
        return self.client.post(reverse("sprache_wechseln"), {"sprache": "en", "next": ziel})

    def test_standard_ist_deutsch(self):
        r = self.client.get(reverse("login"))
        self.assertContains(r, 'lang="de"')
        self.assertContains(r, "Benutzername")
        self.assertContains(r, f"Version {VERSION}")

    def test_versionsnummer(self):
        self.assertTrue(VERSION.startswith("0.7"))

    def test_sprachmenue_vorhanden(self):
        r = self.client.get(reverse("login"))
        self.assertContains(r, 'class="sprachmenue"')
        self.assertContains(r, "English")

    def test_wechsel_ohne_anmeldung_setzt_cookie(self):
        r = self.englisch_waehlen(reverse("login"))
        self.assertRedirects(r, reverse("login"), fetch_redirect_response=False)
        self.assertEqual(r.cookies[settings.LANGUAGE_COOKIE_NAME].value, "en")
        r = self.client.get(reverse("login"))
        self.assertContains(r, 'lang="en"')
        self.assertContains(r, "Username")
        self.assertContains(r, "Log in")

    def test_nur_post_erlaubt(self):
        self.assertEqual(self.client.get(reverse("sprache_wechseln")).status_code, 405)

    def test_unbekannte_sprache_wird_ignoriert(self):
        r = self.client.post(reverse("sprache_wechseln"), {"sprache": "fr", "next": "/"})
        self.assertNotIn(settings.LANGUAGE_COOKIE_NAME, r.cookies)

    def test_kein_offener_redirect(self):
        r = self.client.post(reverse("sprache_wechseln"), {"sprache": "en", "next": "https://boese.example.com/"})
        self.assertEqual(r.url, "/")

    def test_wahl_wird_im_konto_gespeichert(self):
        self.client.login(username="lehrkraft", password=PW)
        self.englisch_waehlen()
        nutzer = User.objects.get(username="lehrkraft")
        self.assertEqual(nutzer.einstellung.sprache, "en")

    def test_kontosprache_gilt_auf_neuem_geraet(self):
        """Ohne Cookie (anderes Gerät/Browser) wird die gespeicherte Sprache des Kontos verwendet."""
        nutzer = User.objects.get(username="lehrkraft")
        Benutzereinstellung.objects.update_or_create(benutzer=nutzer, defaults={"sprache": "en"})
        self.client.login(username="lehrkraft", password=PW)
        self.client.cookies.pop(settings.LANGUAGE_COOKIE_NAME, None)
        r = self.client.get(reverse("start"))
        self.assertContains(r, 'lang="en"')
        self.assertContains(r, "Log out")
        # ein anderes Konto bleibt Deutsch
        self.client.logout()
        self.client.login(username="verwaltung", password=PW)
        self.assertContains(self.client.get(reverse("start")), "Abmelden")

    def test_erste_anmeldung_uebernimmt_gewaehlte_sprache(self):
        self.englisch_waehlen(reverse("login"))
        self.client.post(reverse("login"), {"username": "verwaltung", "password": PW})
        self.assertEqual(User.objects.get(username="verwaltung").einstellung.sprache, "en")

    def test_zurueck_auf_deutsch(self):
        self.client.login(username="lehrkraft", password=PW)
        self.englisch_waehlen()
        self.client.post(reverse("sprache_wechseln"), {"sprache": "de", "next": "/"})
        self.assertContains(self.client.get(reverse("start")), "Abmelden")
        self.assertEqual(User.objects.get(username="lehrkraft").einstellung.sprache, "de")

    def test_portalseiten_englisch(self):
        self.client.login(username="lehrkraft", password=PW)
        self.englisch_waehlen()
        u = Unterricht.objects.get(fach__kuerzel="CH", gruppe__name="9a", abschnitt__nummer=1)
        r = self.client.get(reverse("notenuebersicht", args=[u.pk]))
        self.assertContains(r, "Chemistry")
        self.assertContains(r, "Suggestion")
        self.assertNotContains(r, "Vorschlag")
        gruppe = Gruppe.objects.get(name="9a")
        r = self.client.get(reverse("klassenliste", args=[gruppe.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'lang="en"')
        s = gruppe.aktuelle_mitglieder().first()
        r = self.client.get(reverse("schuelerakte", args=[s.pk]))
        self.assertContains(r, "School career")
        self.assertContains(r, "Parents and contacts")
        self.assertNotContains(r, "Schullaufbahn")

    def test_admin_englisch(self):
        self.client.login(username="verwaltung", password=PW)
        self.englisch_waehlen()
        r = self.client.get(reverse("admin:index"))
        self.assertContains(r, "Log out")
        self.assertContains(r, 'class="sprachmenue"')
        r = self.client.get(reverse("admin:stammdaten_schuelerprofil_changelist"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Student")

    def test_admin_seiten_laden_englisch(self):
        """Alle Listen- und Hinzufügen-Seiten müssen auch auf Englisch fehlerfrei rendern."""
        from django.contrib import admin

        from django.test import RequestFactory

        chef = User.objects.create_superuser("chef", "", PW)
        self.client.login(username="chef", password=PW)
        self.englisch_waehlen()
        anfrage = RequestFactory().get("/")
        anfrage.user = chef
        for model, model_admin in admin.site._registry.items():
            info = (model._meta.app_label, model._meta.model_name)
            for name in ("changelist", "add"):
                if name == "add" and not model_admin.has_add_permission(anfrage):
                    continue          # z. B. fehlgeschlagene Anmeldungen: nur ansehen und löschen
                url = reverse(f"admin:{info[0]}_{info[1]}_{name}")
                self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_katalognamen_englisch(self):
        fach = Fach.objects.get(kuerzel="CH")
        feld = Zusatzfeld.objects.get(name="Schlüsselberechtigungen")
        with translation.override("en"):
            self.assertEqual(str(fach), "Chemistry (CH)")
            self.assertEqual(feld.lokal_name, "Key access")
            self.assertEqual(feld.anzeigewert(["Küche", "Serverraum"]), "Kitchen, Server room")
        with translation.override("de"):
            self.assertEqual(str(fach), "Chemie (CH)")

    def test_englisch_ohne_name_en_faellt_auf_deutsch_zurueck(self):
        fach = Fach.objects.create(kuerzel="LAT", name="Latein")
        with translation.override("en"):
            self.assertEqual(fach.lokal_name, "Latein")

    def test_datumsformat(self):
        from datetime import date

        from stammdaten.sprache import datum

        with translation.override("de"):
            self.assertEqual(datum(date(2026, 10, 3)), "03.10.2026")
        with translation.override("en"):
            self.assertEqual(datum(date(2026, 10, 3)), "03/10/2026")

    def test_demodaten_nachtrag_fuellt_nur_leere_felder(self):
        Fach.objects.filter(kuerzel="CH").update(name_en="")
        Fach.objects.filter(kuerzel="BIO").update(name_en="Life science")
        out = open("/dev/null", "w")
        call_command("demodaten", passwort=PW, stdout=out)
        self.assertEqual(Fach.objects.get(kuerzel="CH").name_en, "Chemistry")
        self.assertEqual(Fach.objects.get(kuerzel="BIO").name_en, "Life science")
