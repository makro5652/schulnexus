"""Sicherheit (ab 0.4.6.0): Verschlüsselung, Zwei-Faktor-Anmeldung, Sicherheitsköpfe, Office-Seite."""
import io
import time
from unittest import mock

from django.contrib.auth.models import Group, User
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from portal import krypto, rollen as R, zweifaktor as Z
from portal.models import OfficeKachel, Zweifaktor
from sicherung.models import Protokoll
from stammdaten.models import Dokument, Person

PW = "Test-Passwort-123"


class KryptoTest(TestCase):
    def test_strom_mehrere_abschnitte_und_manipulation(self):
        daten = bytes(range(256)) * 50
        schluessel = krypto.teilschluessel("dateien")
        with mock.patch.object(krypto, "ABSCHNITT", 1000):
            aus = io.BytesIO()
            krypto.verschluesseln(io.BytesIO(daten), aus, schluessel)
            geheim = aus.getvalue()
            self.assertEqual(geheim[:6], krypto.MAGIC)
            self.assertNotIn(daten[:64], geheim)
            self.assertEqual(krypto.bytes_entschluesseln(geheim), daten)
            # ein verändertes Byte fällt auf
            kaputt = bytearray(geheim)
            kaputt[200] ^= 1
            with self.assertRaises(krypto.KryptoFehler):
                krypto.bytes_entschluesseln(bytes(kaputt))
            # abgeschnittene Datei (letzter Abschnitt fehlt) fällt auf
            laenge_letzter = 4 + 12 + (len(daten) % 1000 or 1000) + 16
            with self.assertRaises(krypto.KryptoFehler):
                krypto.bytes_entschluesseln(geheim[:-laenge_letzter])

    def test_passwort_und_anderer_schluessel(self):
        quelle, ziel, zurueck = (self._tmp(n) for n in ("a", "b", "c"))
        quelle.write_bytes(b"PK geheimer Inhalt")
        krypto.datei_verschluesseln(quelle, ziel, passwort="richtiges-passwort")
        self.assertEqual(krypto.modus_datei(ziel), krypto.PASSWORT)
        with self.assertRaises(krypto.KryptoFehler):
            krypto.datei_entschluesseln(ziel, zurueck)                      # ohne Passwort
        with self.assertRaises(krypto.KryptoFehler):
            krypto.datei_entschluesseln(ziel, zurueck, passwort="falsches-passwort")
        krypto.datei_entschluesseln(ziel, zurueck, passwort="richtiges-passwort")
        self.assertEqual(zurueck.read_bytes(), b"PK geheimer Inhalt")
        # mit dem Serverschlüssel verschlüsselt, mit einem anderen Schlüssel nicht lesbar
        krypto.datei_verschluesseln(quelle, ziel)
        with override_settings(DATEN_SCHLUESSEL=krypto.neuer_schluessel()):
            with self.assertRaises(krypto.KryptoFehler):
                krypto.ablage_lesen(ziel)
        self.assertEqual(krypto.ablage_lesen(ziel), b"PK geheimer Inhalt")

    def _tmp(self, name):
        import tempfile
        from pathlib import Path

        ordner = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(ordner, ignore_errors=True))
        return ordner / name

    def test_ungueltiger_schluessel(self):
        with override_settings(DATEN_SCHLUESSEL="zu-kurz"):
            with self.assertRaises(krypto.KryptoFehler):
                krypto.aktiv()
            from portal.checks import sicherheit_pruefen
            self.assertIn("portal.E001", [m.id for m in sicherheit_pruefen(None)])

    def test_pruefungen_beim_start(self):
        from portal.checks import sicherheit_pruefen

        with override_settings(DATEN_SCHLUESSEL="", DEBUG=False, HTTPS=False):
            ids = [m.id for m in sicherheit_pruefen(None)]
        self.assertIn("portal.W001", ids)
        self.assertIn("portal.W003", ids)
        with override_settings(HTTPS=True, DEBUG=False, CSRF_TRUSTED_ORIGINS=["http://tower:8010"]):
            self.assertIn("portal.W002", [m.id for m in sicherheit_pruefen(None)])
        with override_settings(HTTPS=True, DEBUG=False, CSRF_TRUSTED_ORIGINS=["https://tower.tail1234.ts.net"]):
            self.assertEqual([m.id for m in sicherheit_pruefen(None)], [])

    def test_anhaenge_verschluesselt_abgelegt(self):
        p = Person.objects.create(vorname="Erfunden", nachname="Testperson")
        d = Dokument.objects.create(person=p, titel="Attest", datei=ContentFile(b"%PDF-1.4 vertraulich", name="attest.pdf"))
        roh = open(d.datei.path, "rb").read()
        self.assertEqual(roh[:6], krypto.MAGIC)
        self.assertNotIn(b"vertraulich", roh)
        d.datei.open("rb")
        self.assertEqual(d.datei.read(), b"%PDF-1.4 vertraulich")
        d.datei.close()

    def test_altbestand_nachtraeglich_verschluesseln(self):
        p = Person.objects.create(vorname="Erfunden", nachname="Altbestand")
        with override_settings(DATEN_SCHLUESSEL=""):
            d = Dokument.objects.create(person=p, titel="Alt", datei=ContentFile(b"%PDF-1.4 alt", name="alt.pdf"))
        self.assertEqual(open(d.datei.path, "rb").read(), b"%PDF-1.4 alt")
        aus = io.StringIO()
        call_command("dateien_verschluesseln", stdout=aus)
        self.assertEqual(open(d.datei.path, "rb").read()[:6], krypto.MAGIC)
        d.datei.open("rb")
        self.assertEqual(d.datei.read(), b"%PDF-1.4 alt")
        d.datei.close()
        # zweiter Lauf ändert nichts
        aus = io.StringIO()
        call_command("dateien_verschluesseln", stdout=aus)
        self.assertIn("verschlüsselt: 0", aus.getvalue())

    def test_kurze_geheimnisse(self):
        token = krypto.geheim_verschluesseln("JBSWY3DPEHPK3PXP")
        self.assertNotIn("JBSWY3DPEHPK3PXP", token)
        self.assertEqual(krypto.geheim_entschluesseln(token), "JBSWY3DPEHPK3PXP")


class TotpTest(TestCase):
    GEHEIMNIS = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"      # RFC 6238, Anhang B (SHA-1), "12345678901234567890"

    def test_rfc6238_testvektoren(self):
        for zeit, code in ((59, "287082"), (1111111109, "081804"), (1234567890, "005924"), (2000000000, "279037")):
            self.assertEqual(Z.code_fuer(self.GEHEIMNIS, zeit), code, zeit)

    def test_toleranz_und_wiederverwendung(self):
        t = 1_700_000_000
        code = Z.code_fuer(self.GEHEIMNIS, t)
        schritt = Z.pruefen_geheimnis(self.GEHEIMNIS, code, zeitpunkt=t + 30)          # ein Schritt später: noch gültig
        self.assertIsNotNone(schritt)
        self.assertIsNone(Z.pruefen_geheimnis(self.GEHEIMNIS, code, letzter_schritt=schritt, zeitpunkt=t))   # schon benutzt
        self.assertIsNone(Z.pruefen_geheimnis(self.GEHEIMNIS, code, zeitpunkt=t + 95))                       # zu alt
        self.assertIsNone(Z.pruefen_geheimnis(self.GEHEIMNIS, "12345", zeitpunkt=t))


class ZweifaktorAnmeldungTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("grundeinrichtung", stdout=io.StringIO())
        cls.user = User.objects.create_user("lehrer2fa", password=PW, is_staff=True)
        cls.user.groups.add(Group.objects.get(name=R.LEHRER))
        cls.it = User.objects.create_user("itadmin", password=PW, is_staff=True, is_superuser=True)
        cls.it.groups.add(Group.objects.get(name=R.IT))

    def einrichten(self):
        z = Z.eintrag(self.user)
        g = Z.einrichten_beginnen(z)
        codes = Z.einrichten_bestaetigen(z, Z.code_fuer(g))
        self.assertEqual(len(codes), 10)
        return g, codes

    def test_ohne_zweiten_faktor_unveraendert(self):
        r = self.client.post(reverse("login"), {"username": "lehrer2fa", "password": PW})
        self.assertRedirects(r, reverse("start"), fetch_redirect_response=False)

    def test_anmeldung_mit_code(self):
        g, _codes = self.einrichten()
        r = self.client.post(reverse("login"), {"username": "lehrer2fa", "password": PW})
        self.assertRedirects(r, reverse("anmelden_code"))
        # noch nicht angemeldet
        self.assertEqual(self.client.get(reverse("start")).status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)
        r = self.client.post(reverse("anmelden_code"), {"code": "000000"})
        self.assertContains(r, "Der Code stimmt nicht")
        naechster = Z.code_fuer(g, time.time() + 30)          # der Code der Einrichtung ist bereits verbraucht
        r = self.client.post(reverse("anmelden_code"), {"code": naechster})
        self.assertRedirects(r, reverse("start"), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_ersatzcode_einmal_gueltig(self):
        _g, codes = self.einrichten()
        for erwartet in (302, 200):
            self.client.logout()
            self.client.post(reverse("login"), {"username": "lehrer2fa", "password": PW})
            r = self.client.post(reverse("anmelden_code"), {"code": codes[0].upper()})
            self.assertEqual(r.status_code, erwartet)
        self.assertEqual(len(Z.eintrag(self.user).ersatzcodes), 9)

    def test_zu_viele_versuche(self):
        self.einrichten()
        self.client.post(reverse("login"), {"username": "lehrer2fa", "password": PW})
        for _ in range(5):
            r = self.client.post(reverse("anmelden_code"), {"code": "111111"})
        self.assertRedirects(r, reverse("login"))
        self.assertRedirects(self.client.get(reverse("anmelden_code")), reverse("login"))

    def test_code_seite_ohne_ersten_schritt(self):
        self.assertRedirects(self.client.get(reverse("anmelden_code")), reverse("login"))

    def test_verwaltungsoberflaeche_fuehrt_ueber_eigene_anmeldung(self):
        r = self.client.get(reverse("admin:login") + "?next=/verwaltung/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith(reverse("login")))
        self.einrichten()
        r = self.client.post(reverse("admin:login"), {"username": "lehrer2fa", "password": PW})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_einrichten_ueber_die_seite(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse("sicherheit"), {"aktion": "beginnen"})
        self.assertContains(r, "<svg")
        g = r.context["geheimnis"]
        r = self.client.post(reverse("sicherheit"), {"aktion": "bestaetigen", "code": "123"})
        self.assertContains(r, "Der Code stimmt nicht")
        r = self.client.post(reverse("sicherheit"), {"aktion": "bestaetigen", "code": Z.code_fuer(g)})
        self.assertEqual(len(r.context["neue_codes"]), 10)
        z = Zweifaktor.objects.get(benutzer=self.user)
        self.assertTrue(z.aktiv)
        self.assertNotIn(g, z.geheimnis)                                        # verschlüsselt gespeichert
        self.assertTrue(Protokoll.objects.filter(aktion="zweifaktor").exists())
        # abschalten nur mit gültigem Code
        r = self.client.post(reverse("sicherheit"), {"aktion": "abschalten", "code": "000000"})
        self.assertTrue(Zweifaktor.objects.get(benutzer=self.user).aktiv)
        r = self.client.post(reverse("sicherheit"), {"aktion": "abschalten", "code": Z.code_fuer(g, time.time() + 30)})
        self.assertRedirects(r, reverse("sicherheit"))
        self.assertFalse(Zweifaktor.objects.get(benutzer=self.user).aktiv)

    def test_pflicht_durch_it(self):
        self.client.force_login(self.it)
        url = reverse("benutzer_bearbeiten", args=[self.user.pk])
        self.assertContains(self.client.get(url), "Zwei-Faktor-Anmeldung")
        self.client.post(url, {"aktion": "zweifaktor_pflicht", "pflicht": "1"})
        self.assertTrue(Zweifaktor.objects.get(benutzer=self.user).pflicht)
        self.assertContains(self.client.get(reverse("benutzerverwaltung")), "Pflicht, offen")
        # Konto ohne Einrichtung: alle Seiten führen zur Einrichtung, Abmelden bleibt möglich
        self.client.force_login(self.user)
        self.assertRedirects(self.client.get(reverse("start")), reverse("sicherheit"))
        r = self.client.get(reverse("sicherheit"))
        self.assertContains(r, "vorgeschrieben")
        g = self.client.post(reverse("sicherheit"), {"aktion": "beginnen"}).context["geheimnis"]
        self.client.post(reverse("sicherheit"), {"aktion": "bestaetigen", "code": Z.code_fuer(g)})
        self.assertEqual(self.client.get(reverse("start")).status_code, 200)
        # verpflichtend: selbst abschalten nicht möglich
        r = self.client.post(reverse("sicherheit"), {"aktion": "abschalten", "code": Z.code_fuer(g, time.time() + 30)})
        self.assertContains(r, "verpflichtend")
        self.assertTrue(Zweifaktor.objects.get(benutzer=self.user).aktiv)
        # IT setzt zurück (Telefon verloren)
        self.client.force_login(self.it)
        self.client.post(url, {"aktion": "zweifaktor_zuruecksetzen"})
        z = Zweifaktor.objects.get(benutzer=self.user)
        self.assertFalse(z.aktiv)
        self.assertTrue(z.pflicht)
        self.assertTrue(Protokoll.objects.filter(aktion="zweifaktor", text__contains="zurückgesetzt").exists())

    def test_nur_it_darf_pflicht_setzen(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse("benutzer_bearbeiten", args=[self.it.pk]), {"aktion": "zweifaktor_pflicht", "pflicht": "1"})
        self.assertIn(r.status_code, (302, 403))
        self.assertFalse(Zweifaktor.objects.filter(benutzer=self.it, pflicht=True).exists())


class KoepfeUndOfficeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("grundeinrichtung", stdout=io.StringIO())
        cls.user = User.objects.create_user("lehrkraft_o", password=PW, is_staff=True)
        cls.user.groups.add(Group.objects.get(name=R.LEHRER))

    def setUp(self):
        self.client.force_login(self.user)

    def test_sicherheitskoepfe(self):
        r = self.client.get(reverse("start"))
        self.assertIn("frame-ancestors 'none'", r["Content-Security-Policy"])
        self.assertEqual(r["X-Frame-Options"], "DENY")
        self.assertEqual(r["Cross-Origin-Opener-Policy"], "same-origin")
        self.assertIn("camera=()", r["Permissions-Policy"])

    def test_office_kacheln(self):
        self.assertTrue(OfficeKachel.objects.filter(titel="Outlook").exists())     # Voreinstellung aus der Migration
        r = self.client.get(reverse("office"))
        self.assertContains(r, 'href="https://outlook.office.com/mail/" target="_blank" rel="noopener noreferrer"', html=False)
        self.assertContains(r, 'id="of-umschalten"')
        self.assertContains(r, "office-ohne-menueband")
        self.assertNotContains(r, "Kacheln verwalten")
        # im Menüband (Start) und im Kontomenü
        self.assertContains(self.client.get(reverse("start")), reverse("office"))
        self.assertContains(self.client.get(reverse("start")), reverse("sicherheit"))

    def test_mandant_platzhalter(self):
        OfficeKachel.objects.create(titel="Intranet", url="https://{mandant}.sharepoint.com/sites/lehrer", symbol="gebaeude")
        with override_settings(OFFICE_MANDANT=""):
            self.assertNotContains(self.client.get(reverse("office")), "Intranet")
        with override_settings(OFFICE_MANDANT="erfundeneschule"):
            self.assertContains(self.client.get(reverse("office")), "https://erfundeneschule.sharepoint.com/sites/lehrer")

    def test_englische_titel(self):
        from django.utils import translation

        self.addCleanup(translation.activate, "de")          # sprache_wechseln aktiviert Englisch im laufenden Thread
        self.client.post(reverse("sprache_wechseln"), {"sprache": "en", "next": "/"})
        r = self.client.get(reverse("office"))
        self.assertContains(r, "Calendar")

    def test_kachel_pruefung(self):
        from django.core.exceptions import ValidationError

        k = OfficeKachel(titel="X", url="http://unsicher.example", farbe="#123456")
        with self.assertRaises(ValidationError):
            k.full_clean()
        k = OfficeKachel(titel="X", url="https://ok.example", farbe="rot")
        with self.assertRaises(ValidationError):
            k.full_clean()
