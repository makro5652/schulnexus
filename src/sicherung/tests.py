"""Tests: Modulsicherung, Wiederherstellung, PDF-Export, IT-Rolle und Einzelrechte (seit Version 0.4.3.0)."""
import io
import json
import zipfile
from datetime import date

from django.contrib.auth.models import Group, Permission, User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from fehlzeiten.models import Fehlzeit
from portal import krypto, rollen as R
from stammdaten.models import Dokument, Person, Schuelerprofil

from . import archiv
from .models import Exportauftrag, Protokoll, Sicherung
from .module import SCHLUESSEL

PW = "Test-Passwort-123"


def inhalt(antwort):
    return b"".join(antwort.streaming_content)


class Grundlage(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))
        cls.it = User.objects.get(username="it")
        cls.sl = User.objects.get(username="schulleitung")

    def setUp(self):
        # Andere Tests schalten im selben Prozess auf Englisch um (sprache_wechseln); Meldungen hier deutsch prüfen.
        from django.utils import translation

        translation.activate("de")
        self.addCleanup(translation.deactivate)

    def anmelden(self, name):
        self.client.logout()
        self.assertTrue(self.client.login(username=name, password=PW))


class ZugriffTest(Grundlage):
    def test_nur_schulleitung_und_it(self):
        seiten = ["sicherungen", "pdf_export"]
        for name in ("lehrkraft", "verwaltung", "mittelstufe", "verwaltungsleitung"):
            self.anmelden(name)
            for s in seiten + ["benutzerverwaltung", "systemprotokoll"]:
                self.assertEqual(self.client.get(reverse(s)).status_code, 403, (name, s))
        self.anmelden("schulleitung")
        for s in seiten + ["systemprotokoll"]:
            self.assertEqual(self.client.get(reverse(s)).status_code, 200, s)
        self.assertEqual(self.client.get(reverse("benutzerverwaltung")).status_code, 403)
        self.anmelden("it")
        for s in seiten + ["benutzerverwaltung", "systemprotokoll"]:
            self.assertEqual(self.client.get(reverse(s)).status_code, 200, s)

    def test_menueband(self):
        self.anmelden("schulleitung")
        r = self.client.get(reverse("start"))
        self.assertContains(r, reverse("sicherungen"))
        self.assertNotContains(r, reverse("benutzerverwaltung"))
        self.anmelden("it")
        self.assertContains(self.client.get(reverse("start")), reverse("benutzerverwaltung"))
        self.anmelden("lehrkraft")
        self.assertNotContains(self.client.get(reverse("start")), reverse("sicherungen"))

    def test_it_rolle_in_rollenuebersicht(self):
        self.anmelden("schulleitung")
        self.assertContains(self.client.get(reverse("rollen")), "IT-Administration")
        self.assertTrue(self.it.is_superuser)
        self.assertTrue(self.it.groups.filter(name=R.IT).exists())


class SicherungTest(Grundlage):
    def test_erstellen_ueber_die_seite(self):
        self.anmelden("schulleitung")
        r = self.client.post(reverse("sicherungen"), {"module": ["fehlzeiten", "noten"], "bemerkung": "Test"})
        self.assertRedirects(r, reverse("sicherungen"))
        s = Sicherung.objects.get()
        self.assertEqual(s.module, ["noten", "fehlzeiten"])
        self.assertTrue(s.datei.endswith(".zip.enc"))
        self.assertEqual(s.pfad.read_bytes()[:6], krypto.MAGIC)        # auf dem Datenträger verschlüsselt
        with zipfile.ZipFile(io.BytesIO(krypto.ablage_lesen(s.pfad))) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            self.assertEqual(set(manifest["module"]), {"noten", "fehlzeiten"})
            daten = json.loads(zf.read("daten/fehlzeiten.json"))
        self.assertEqual(sum(1 for o in daten if o["model"] == "fehlzeiten.fehlzeit"), Fehlzeit.objects.count())
        self.assertTrue(Protokoll.objects.filter(aktion="sicherung", benutzer=self.sl).exists())
        self.assertContains(self.client.get(reverse("sicherungen")), s.datei)
        r = self.client.get(reverse("sicherung_herunterladen", args=[s.pk]))
        self.assertEqual(inhalt(r)[:2], b"PK")

    def test_wiederherstellen_mit_vorschau_und_bestaetigung(self):
        s = archiv.sicherung_erstellen(["fehlzeiten"], self.sl)
        erste = Fehlzeit.objects.order_by("pk").first()
        erste.grund = "GEÄNDERT"
        erste.save()
        weg = list(Fehlzeit.objects.order_by("pk").values_list("pk", flat=True)[1:3])
        Fehlzeit.objects.filter(pk__in=weg).delete()
        neu = Fehlzeit.objects.create(schueler=Schuelerprofil.objects.first(), art=Fehlzeit.VERSPAETUNG, datum_von=date(2026, 10, 1), minuten=5)
        self.anmelden("schulleitung")
        url = reverse("wiederherstellen", args=[s.pk])
        r = self.client.post(url, {"module": ["fehlzeiten"], "aktion": "vorschau"})
        zeile = r.context["plan"]["module"][0]
        self.assertGreaterEqual(zeile["neu"], 2)
        self.assertGreaterEqual(zeile["geaendert"], 1)
        self.assertGreaterEqual(zeile["loeschen"], 1)
        # ohne Bestätigung passiert nichts
        r = self.client.post(url, {"module": ["fehlzeiten"], "aktion": "ausfuehren", "bestaetigung": "falsch"})
        self.assertTrue(Fehlzeit.objects.filter(pk=neu.pk).exists())
        self.assertContains(r, "Sicherheitsabfrage")
        r = self.client.post(url, {"module": ["fehlzeiten"], "aktion": "ausfuehren", "bestaetigung": "wiederherstellen", "verstanden": "1"})
        self.assertContains(r, "zurückgesetzt")
        self.assertFalse(Fehlzeit.objects.filter(pk=neu.pk).exists())
        self.assertTrue(Fehlzeit.objects.filter(pk__in=weg).count() == 2)
        erste.refresh_from_db()
        self.assertNotEqual(erste.grund, "GEÄNDERT")
        vorher = Sicherung.objects.get(art=Sicherung.VOR_WIEDERHERSTELLUNG)
        self.assertEqual(set(vorher.module), set(SCHLUESSEL))
        self.assertTrue(Protokoll.objects.filter(aktion="wiederhergestellt").exists())
        # neue Einträge erhalten danach freie Primärschlüssel
        Fehlzeit.objects.create(schueler=Schuelerprofil.objects.first(), art=Fehlzeit.VERSPAETUNG, datum_von=date(2026, 10, 2), minuten=5)

    def test_kaskade_in_andere_module(self):
        s = archiv.sicherung_erstellen(["stammdaten"], self.sl)
        p = Person.objects.create(vorname="Neu", nachname="Nachher")
        kind = Schuelerprofil.objects.create(person=p, schuelernummer="NEU-1")
        fz = Fehlzeit.objects.create(schueler=kind, datum_von=date(2026, 10, 5))
        plan = archiv.planen(s.pfad, ["stammdaten"], self.sl)
        self.assertEqual(plan["blockiert"], [])
        self.assertIn("Fehlzeiten", [k["name"] for k in plan["kaskade"]])
        archiv.wiederherstellen(s, ["stammdaten"], self.sl)
        self.assertFalse(Fehlzeit.objects.filter(pk=fz.pk).exists())
        self.assertFalse(Person.objects.filter(pk=p.pk).exists())

    def test_fehlende_bezuege_blockieren(self):
        s = archiv.sicherung_erstellen(["fehlzeiten"], self.sl)
        kind = Fehlzeit.objects.first().schueler
        kind.person.delete()
        plan = archiv.planen(s.pfad, ["fehlzeiten"], self.sl)
        self.assertTrue(plan["blockiert"])
        with self.assertRaises(archiv.SicherungFehler):
            archiv.wiederherstellen(s, ["fehlzeiten"], self.sl)
        self.assertFalse(Sicherung.objects.filter(art=Sicherung.VOR_WIEDERHERSTELLUNG).exists())

    def test_eigenes_konto_bleibt_erhalten(self):
        s = archiv.sicherung_erstellen(["konten"], self.sl)
        neu = User.objects.create_user("it2", password=PW, is_superuser=True, is_staff=True)
        neu.groups.add(Group.objects.get(name=R.IT))
        plan = archiv.planen(s.pfad, ["konten"], neu)
        self.assertTrue(any("eigenes Benutzerkonto" in str(h) for h in plan["hinweise"]))
        archiv.wiederherstellen(s, ["konten"], neu)
        self.assertTrue(User.objects.filter(pk=neu.pk).exists())

    def test_dateien_werden_wiederhergestellt(self):
        person = Schuelerprofil.objects.first().person
        d = Dokument.objects.create(person=person, titel="Attest", datei=ContentFile(b"%PDF-1.4 test", name="attest.pdf"))
        name = d.datei.name
        s = archiv.sicherung_erstellen(["stammdaten"], self.sl, mit_dateien=True)
        d.datei.storage.delete(name)
        self.assertFalse(d.datei.storage.exists(name))
        archiv.wiederherstellen(s, ["stammdaten"], self.sl)
        self.assertTrue(d.datei.storage.exists(name))

    def test_hochladen_pruefen_und_wiederherstellen(self):
        s = archiv.sicherung_erstellen(["fehlzeiten"], self.sl)
        daten = krypto.ablage_lesen(s.pfad)
        self.anmelden("it")
        r = self.client.post(reverse("sicherungen"), {"aktion": "hochladen", "datei": SimpleUploadedFile("x.zip", daten)})
        self.assertRedirects(r, reverse("sicherungen"))
        hoch = Sicherung.objects.get(art=Sicherung.HOCHGELADEN)
        self.assertEqual(hoch.module, ["fehlzeiten"])
        # keine Sicherung
        r = self.client.post(reverse("sicherungen"), {"aktion": "hochladen", "datei": SimpleUploadedFile("y.zip", b"kein zip")})
        self.assertContains(r, "keine gültige Sicherung")
        # beschädigt: Prüfsumme stimmt nicht
        puffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(daten)) as alt, zipfile.ZipFile(puffer, "w") as neu:
            for n in alt.namelist():
                neu.writestr(n, alt.read(n) + (b" " if n.startswith("daten/") else b""))
        r = self.client.post(reverse("sicherungen"), {"aktion": "hochladen", "datei": SimpleUploadedFile("z.zip", puffer.getvalue())})
        self.assertContains(r, "beschädigt")
        self.assertEqual(Sicherung.objects.filter(art=Sicherung.HOCHGELADEN).count(), 1)

    def test_herunterladen_mit_passwort_und_wieder_hochladen(self):
        s = archiv.sicherung_erstellen(["fehlzeiten"], self.sl)
        self.anmelden("it")
        url = reverse("sicherung_herunterladen", args=[s.pk])
        # zu kurzes Passwort
        r = self.client.post(url, {"passwort": "kurz"})
        self.assertRedirects(r, reverse("sicherungen"))
        r = self.client.post(url, {"passwort": "Ein-langes-Passwort"})
        self.assertEqual(r["Content-Disposition"].split("filename=")[1].strip('"'), s.datei)    # …zip.enc
        daten = inhalt(r)
        self.assertEqual(daten[:7], krypto.MAGIC + bytes([krypto.PASSWORT]))
        self.assertTrue(Protokoll.objects.filter(aktion="heruntergeladen", text__contains="Passwort").exists())
        # ohne Passwort abgelehnt, mit falschem abgelehnt, mit richtigem angenommen
        r = self.client.post(reverse("sicherungen"), {"aktion": "hochladen", "datei": SimpleUploadedFile("a.enc", daten)})
        self.assertContains(r, "Passwort")
        r = self.client.post(reverse("sicherungen"), {"aktion": "hochladen", "datei": SimpleUploadedFile("a.enc", daten), "passwort": "falsch-falsch-falsch"})
        self.assertContains(r, "Entschlüsselung fehlgeschlagen")
        r = self.client.post(reverse("sicherungen"), {"aktion": "hochladen", "datei": SimpleUploadedFile("a.enc", daten), "passwort": "Ein-langes-Passwort"})
        self.assertRedirects(r, reverse("sicherungen"))
        hoch = Sicherung.objects.get(art=Sicherung.HOCHGELADEN)
        self.assertEqual(hoch.pfad.read_bytes()[:7], krypto.MAGIC + bytes([krypto.SERVER]))   # wieder mit Serverschlüssel
        self.assertEqual(hoch.module, ["fehlzeiten"])
        # Datei mit dem Serverschlüssel dieser Installation (z. B. vom Datenträger kopiert)
        r = self.client.post(reverse("sicherungen"), {"aktion": "hochladen", "datei": SimpleUploadedFile("b.zip.enc", s.pfad.read_bytes())})
        self.assertRedirects(r, reverse("sicherungen"))
        self.assertEqual(Sicherung.objects.filter(art=Sicherung.HOCHGELADEN).count(), 2)

    def test_anderer_programmstand_wird_abgelehnt(self):
        s = archiv.sicherung_erstellen(["fehlzeiten"], self.sl)
        puffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(krypto.ablage_lesen(s.pfad))) as alt, zipfile.ZipFile(puffer, "w") as neu:
            for n in alt.namelist():
                inhalt_ = alt.read(n)
                if n == "manifest.json":
                    m = json.loads(inhalt_)
                    m["module"]["fehlzeiten"]["migrationen"] = {"fehlzeiten": ["9999_zukunft"]}
                    m["version"] = "0.1"
                    inhalt_ = json.dumps(m).encode()
                neu.writestr(n, inhalt_)
        s.pfad.write_bytes(puffer.getvalue())
        krypto.ablage_verschluesseln(s.pfad)
        plan = archiv.planen(s.pfad, ["fehlzeiten"], self.sl)
        self.assertTrue(any("Programmstand" in str(b) for b in plan["blockiert"]))

    def test_loeschen_und_automatische_sicherung(self):
        call_command("modulsicherung", "fehlzeiten", "--behalten", "1", stdout=io.StringIO())
        call_command("modulsicherung", "fehlzeiten", "--behalten", "1", stdout=io.StringIO())
        self.assertEqual(Sicherung.objects.filter(art=Sicherung.AUTOMATISCH).count(), 1)
        s = Sicherung.objects.get()
        self.anmelden("schulleitung")
        self.assertContains(self.client.get(reverse("sicherungen")), "automatisch")     # ohne Ersteller:in
        self.client.post(reverse("sicherung_loeschen", args=[s.pk]))
        self.assertFalse(Sicherung.objects.exists())
        self.assertFalse(s.pfad.exists())


class PdfTest(Grundlage):
    def text(self, pfad):
        from pypdf import PdfReader

        roh = pfad.read_bytes()
        self.assertEqual(roh[:6], krypto.MAGIC)                         # PDF-Exporte liegen verschlüsselt
        return "\n".join(seite.extract_text() for seite in PdfReader(io.BytesIO(krypto.ablage_lesen(pfad))).pages)

    def test_export_mit_zeitraum_und_monatsaufteilung(self):
        self.anmelden("schulleitung")
        r = self.client.post(reverse("pdf_export"), {"module": ["fehlzeiten"], "zeitraum": "eigen", "von": "2026-08-01",
                                                     "bis": "2027-01-31", "aufteilung": "monat", "mit_bestand": "on"})
        self.assertRedirects(r, reverse("pdf_export"))
        a = Exportauftrag.objects.get()
        self.assertEqual(a.status, Exportauftrag.FERTIG, a.fehler)
        monate = [d for d in a.dateien if "bestand" not in d["name"]]
        self.assertGreaterEqual(len(monate), 2)
        self.assertTrue(any("bestand" in d["name"] for d in a.dateien))
        f = Fehlzeit.objects.filter(datum_von__gte=date(2026, 8, 1)).order_by("datum_von").first()
        alle = "\n".join(self.text(a.ordner / d["name"]) for d in monate)
        self.assertIn(f.schueler.person.nachname, alle)
        self.assertIn("Vertraulich", alle)
        # Einzeldatei und ZIP
        r = self.client.get(reverse("pdf_datei", args=[a.pk, a.dateien[0]["name"]]))
        self.assertEqual(inhalt(r)[:4], b"%PDF")
        r = self.client.get(reverse("pdf_zip", args=[a.pk]))
        with zipfile.ZipFile(io.BytesIO(inhalt(r))) as zf:
            self.assertEqual(len(zf.namelist()), len(a.dateien))
        self.assertEqual(self.client.get(reverse("pdf_datei", args=[a.pk, "nicht-vorhanden.pdf"])).status_code, 404)

    @override_settings(PDF_EINTRAEGE_JE_DATEI=50)
    def test_viele_daten_mehrere_dateien(self):
        from .pdf import export_ausfuehren

        a = Exportauftrag.objects.create(module=["stammdaten"], aufteilung="keine", mit_bestand=True, erstellt_von=self.sl)
        export_ausfuehren(a.pk)
        a.refresh_from_db()
        teile = [d for d in a.dateien if "bestand" in d["name"]]
        self.assertGreater(len(teile), 2)
        self.assertTrue(all(d["eintraege"] <= 50 for d in a.dateien))
        self.assertIn("Teil 1 von", self.text(a.ordner / teile[0]["name"]))

    def test_keine_passwoerter_im_pdf(self):
        from .pdf import export_ausfuehren

        a = Exportauftrag.objects.create(module=["konten"], erstellt_von=self.sl)
        export_ausfuehren(a.pk)
        a.refresh_from_db()
        text = "\n".join(self.text(a.ordner / d["name"]) for d in a.dateien)
        self.assertIn("lehrkraft", text)
        self.assertNotIn("argon2", text)
        self.assertNotIn("pbkdf2", text)

    def test_protokoll_im_zeitraum(self):
        from .pdf import export_ausfuehren

        a = Exportauftrag.objects.create(module=["fehlzeiten"], mit_protokoll=True, mit_bestand=False, erstellt_von=self.sl)
        export_ausfuehren(a.pk)
        a.refresh_from_db()
        self.assertIn("Änderungsprotokoll", "\n".join(self.text(a.ordner / d["name"]) for d in a.dateien))


class RechteTest(Grundlage):
    def test_einzelrecht_entziehen_und_erteilen(self):
        lk = User.objects.get(username="lehrkraft")
        weg = Permission.objects.get(codename="add_leistungsnachweis")
        dazu = Permission.objects.get(codename="view_gesundheitsangaben")
        self.assertTrue(lk.has_perm("noten.add_leistungsnachweis"))
        self.assertFalse(lk.has_perm("stammdaten.view_gesundheitsangaben"))
        self.anmelden("it")
        r = self.client.post(reverse("benutzer_bearbeiten", args=[lk.pk]), {"aktion": "rechte", f"r_{weg.pk}": "-", f"r_{dazu.pk}": "+"})
        self.assertEqual(r.status_code, 302)
        lk = User.objects.get(pk=lk.pk)
        self.assertFalse(lk.has_perm("noten.add_leistungsnachweis"))
        self.assertTrue(lk.has_perm("stammdaten.view_gesundheitsangaben"))
        self.assertTrue(lk.has_perm("noten.view_leistungsnachweis"))
        self.assertTrue(Protokoll.objects.filter(aktion="rechte", text__contains="noten.add_leistungsnachweis").exists())
        seite = self.client.get(reverse("benutzer_bearbeiten", args=[lk.pk]))
        self.assertContains(seite, f'name="r_{weg.pk}"')
        self.assertContains(self.client.get(reverse("benutzerverwaltung")), "−1")
        # Entzug aufheben
        self.client.post(reverse("benutzer_bearbeiten", args=[lk.pk]), {"aktion": "rechte", f"r_{weg.pk}": ""})
        self.assertTrue(User.objects.get(pk=lk.pk).has_perm("noten.add_leistungsnachweis"))

    def test_it_rolle_gibt_vollzugriff(self):
        sek = User.objects.get(username="verwaltung")
        self.anmelden("it")
        rollen = list(sek.groups.values_list("name", flat=True)) + [R.IT]
        self.client.post(reverse("benutzer_bearbeiten", args=[sek.pk]), {"aktion": "konto", "rollen": rollen, "aktiv": "1"})
        sek.refresh_from_db()
        self.assertTrue(sek.is_superuser)
        self.client.post(reverse("benutzer_bearbeiten", args=[sek.pk]), {"aktion": "konto", "rollen": [R.SEKRETARIAT], "aktiv": "1"})
        sek.refresh_from_db()
        self.assertFalse(sek.is_superuser)
        self.assertEqual(list(sek.groups.values_list("name", flat=True)), [R.SEKRETARIAT])

    def test_selbstschutz(self):
        self.anmelden("it")
        r = self.client.post(reverse("benutzer_bearbeiten", args=[self.it.pk]), {"aktion": "konto", "rollen": [], "aktiv": "1"}, follow=True)
        self.assertContains(r, "nicht selbst entziehen")
        r = self.client.post(reverse("benutzer_bearbeiten", args=[self.it.pk]), {"aktion": "konto", "rollen": [R.IT]}, follow=True)
        self.assertContains(r, "nicht sperren")
        self.it.refresh_from_db()
        self.assertTrue(self.it.is_superuser and self.it.is_active)

    def test_konto_sperren(self):
        lk = User.objects.get(username="lehrkraft")
        self.anmelden("it")
        self.client.post(reverse("benutzer_bearbeiten", args=[lk.pk]), {"aktion": "konto", "rollen": [R.LEHRER]})
        self.assertFalse(self.client.login(username="lehrkraft", password=PW))

    def test_passwort_zuruecksetzen(self):
        self.anmelden("it")
        r = self.client.post(reverse("benutzer_bearbeiten", args=[User.objects.get(username="lehrkraft").pk]), {"aktion": "passwort"})
        pw = r.context["neues_passwort"]
        self.assertGreaterEqual(len(pw), 16)
        self.client.logout()
        self.assertTrue(self.client.login(username="lehrkraft", password=pw))
        self.assertTrue(Protokoll.objects.filter(aktion="passwort").exists())

    def test_schulleitung_sieht_keine_rechteprotokolle(self):
        Protokoll.schreiben(self.it, "rechte", "lehrkraft: +x")
        self.anmelden("schulleitung")
        self.assertNotContains(self.client.get(reverse("systemprotokoll")), "lehrkraft: +x")
        self.anmelden("it")
        self.assertContains(self.client.get(reverse("systemprotokoll")), "lehrkraft: +x")


class VorlagenfilterTest(TestCase):
    def test_benutzername_auch_ohne_konto(self):
        from django.template import Context, Template

        t = Template('{% load formate %}[{{ u|benutzername }}][{{ u|benutzername:"" }}]')
        self.assertEqual(t.render(Context({"u": None})), "[–][]")
        u = User(username="ohne_person")
        self.assertEqual(t.render(Context({"u": u})), "[ohne_person][ohne_person]")


class EnglischTest(Grundlage):
    def test_seiten_auf_englisch(self):
        self.anmelden("it")
        self.client.post(reverse("sprache_wechseln"), {"sprache": "en", "next": "/"})
        self.assertContains(self.client.get(reverse("sicherungen")), "Backup and restore")
        self.assertContains(self.client.get(reverse("pdf_export")), "PDF export")
        self.assertContains(self.client.get(reverse("benutzerverwaltung")), "Users and permissions")
