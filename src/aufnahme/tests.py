"""Tests für Neuanmeldungen (seit Version 0.4.2.5)."""
import os
from datetime import date

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from stammdaten.models import Beziehung, Dokument, Gruppe, Mitgliedschaft, Person, Schuelerprofil, Schuljahr

from .models import AnmeldeDatei, AnmeldePunkt, Anmeldung, ChecklistenVorlage
from .uebernahme import hindernisse, naechste_schuelernummer, uebernehmen

PW = "Test-Passwort-123"


class AufnahmeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open(os.devnull, "w"))
        cls.sj = Schuljahr.aktuelles()
        cls.lena = Anmeldung.objects.get(nachname="Hoffmann")       # Jg. 9, in Prüfung, vorläufig 9a
        cls.jonas = Anmeldung.objects.get(vorname="Jonas")          # Jg. 9, zugesagt, Pflichtpunkte erledigt, 9b
        cls.mia = Anmeldung.objects.get(nachname="Schneider")       # Jg. 11, Warteliste

    def anmelden(self, name):
        self.client.logout()
        self.assertTrue(self.client.login(username=name, password=PW))

    def aktion(self, a, **daten):
        return self.client.post(reverse("anmeldung_aktion", args=[a.pk]), daten)

    # ------------------------------------------------------------ Grundlagen
    def test_vorlagen_und_demodaten(self):
        self.assertTrue(ChecklistenVorlage.objects.filter(name="Standard", standard=True).exists())
        self.assertEqual(Anmeldung.objects.count(), 5)
        self.assertEqual(sorted(Anmeldung.objects.values_list("nummer", flat=True))[0][:6], f"A{self.lena.eingang.year}-"[:6])
        self.assertFalse(self.jonas.fortschritt()["offen_pflicht"])
        self.assertEqual(hindernisse(self.jonas), [])

    def test_nummer_fortlaufend(self):
        a = Anmeldung.objects.create(schuljahr=self.sj, vorname="Test", nachname="Kind", eingang=date(2030, 1, 5))
        b = Anmeldung.objects.create(schuljahr=self.sj, vorname="Test", nachname="Kind2", eingang=date(2030, 2, 5))
        self.assertEqual((a.nummer, b.nummer), ("A2030-001", "A2030-002"))

    def test_vorlage_ohne_doppelte_punkte(self):
        vorher = self.lena.punkte.count()
        self.assertEqual(self.lena.punkte_aus_vorlage(ChecklistenVorlage.objects.get(name="Standard")), 0)
        self.assertEqual(self.lena.punkte_aus_vorlage(ChecklistenVorlage.objects.get(name="Oberstufe")), 3)
        self.assertEqual(self.lena.punkte.count(), vorher + 3)

    # ------------------------------------------------------------ Rechte
    def test_lehrkraft_und_hr_ohne_zugang(self):
        for name in ("lehrkraft", "personal"):
            self.anmelden(name)
            self.assertEqual(self.client.get(reverse("anmeldungen")).status_code, 403)
            self.assertEqual(self.client.get(reverse("anmeldung", args=[self.lena.pk])).status_code, 403)

    def test_stufenkoordination_nur_eigene_jahrgaenge(self):
        self.anmelden("mittelstufe")
        r = self.client.get(reverse("anmeldungen") + "?status=alle")
        self.assertNotIn(self.mia, r.context["zeilen"])
        self.assertIn(self.lena, r.context["zeilen"])
        self.assertEqual(self.client.get(reverse("anmeldung", args=[self.mia.pk])).status_code, 403)
        # Klassen nur der eigenen Stufe, keine Übernahme
        r = self.client.get(reverse("anmeldung", args=[self.lena.pk]))
        self.assertTrue(r.context["darf"]["bearbeiten"])
        self.assertFalse(r.context["darf"]["uebernehmen"])
        self.assertEqual(self.client.get(reverse("anmeldung_uebernahme", args=[self.jonas.pk])).status_code, 403)
        self.anmelden("oberstufe")
        self.assertEqual(self.client.get(reverse("anmeldung", args=[self.lena.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("anmeldung", args=[self.mia.pk])).status_code, 200)

    def test_finanzen_hakt_ab_aendert_aber_keinen_status(self):
        self.anmelden("finanzen")
        r = self.client.get(reverse("anmeldung", args=[self.mia.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["darf"]["abhaken"])
        self.assertFalse(r.context["darf"]["bearbeiten"])
        p = self.mia.punkte.filter(zustaendig="finanzen", erledigt=False).first()
        self.aktion(self.mia, aktion="abhaken", punkt=p.pk)
        p.refresh_from_db()
        self.assertTrue(p.erledigt)
        self.assertEqual(p.erledigt_von.username, "finanzen")
        self.assertEqual(self.aktion(self.mia, aktion="status", status="zugesagt").status_code, 403)
        self.assertEqual(self.aktion(self.mia, aktion="punkt_neu", **{"punkt-text": "x"}).status_code, 403)
        self.assertEqual(self.client.get(reverse("anmeldung_uebernahme", args=[self.jonas.pk])).status_code, 403)

    # ------------------------------------------------------------ Erfassen
    def test_neue_anmeldung_mit_zeugnissen_und_vorlagen(self):
        self.anmelden("verwaltung")
        standard = ChecklistenVorlage.objects.get(name="Standard")
        daten = {
            "eingang": "2026-10-01", "schuljahr": self.sj.pk, "jahrgang": "7", "vorname": "Ella", "nachname": "Neu",
            "geschlecht": "w", "geburtsdatum": "2014-03-03", "land": "Kenia", "religionsunterricht": "",
            "kontakt-TOTAL_FORMS": "2", "kontakt-INITIAL_FORMS": "0", "kontakt-MIN_NUM_FORMS": "0", "kontakt-MAX_NUM_FORMS": "6",
            "kontakt-0-art": "mutter", "kontakt-0-vorname": "Eva", "kontakt-0-nachname": "Neu", "kontakt-0-sprache": "de",
            "kontakt-0-korrespondenzweg": "email", "kontakt-0-sorgerecht": "on", "kontakt-0-adresse_wie_kind": "on",
            "kontakt-1-art": "vater", "kontakt-1-sprache": "de", "kontakt-1-korrespondenzweg": "email",
            "kontakt-1-sorgerecht": "on", "kontakt-1-abholberechtigt": "on", "kontakt-1-adresse_wie_kind": "on",
            "vorlagen": [standard.pk],
            "zeugnisse": [SimpleUploadedFile("Zeugnis 6.pdf", b"%PDF-1.4 a", content_type="application/pdf"),
                          SimpleUploadedFile("Zeugnis 5.pdf", b"%PDF-1.4 b", content_type="application/pdf")],
        }
        r = self.client.post(reverse("anmeldung_neu"), daten)
        a = Anmeldung.objects.get(vorname="Ella")
        self.assertRedirects(r, reverse("anmeldung", args=[a.pk]))
        self.assertEqual(a.kontakte.count(), 1)                      # leeres zweites Formular wird übergangen
        self.assertEqual(a.punkte.count(), standard.punkte.count())
        self.assertEqual(sorted(a.dateien.values_list("titel", flat=True)), ["Zeugnis 5", "Zeugnis 6"])
        d = a.dateien.first()
        self.assertEqual(d.inhaltstyp, "application/pdf")
        self.assertTrue(d.datei.name.startswith("aufnahme/"))
        # Download: rechtegeprüft, mit Schutz-Kopfzeilen
        r = self.client.get(reverse("aufnahme_datei", args=[d.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertIn("sandbox", r["Content-Security-Policy"])
        self.anmelden("lehrkraft")
        self.assertEqual(self.client.get(reverse("aufnahme_datei", args=[d.pk])).status_code, 403)

    def test_stufenkoordination_nur_eigene_jahrgaenge_beim_anlegen(self):
        self.anmelden("mittelstufe")
        r = self.client.post(reverse("anmeldung_neu"), {
            "eingang": "2026-10-01", "schuljahr": self.sj.pk, "jahrgang": "11", "vorname": "Zu", "nachname": "Alt", "land": "Kenia",
            "kontakt-TOTAL_FORMS": "0", "kontakt-INITIAL_FORMS": "0", "kontakt-MIN_NUM_FORMS": "0", "kontakt-MAX_NUM_FORMS": "6"})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Anmeldung.objects.filter(vorname="Zu").exists())

    # ------------------------------------------------------------ Bewerbungsakte
    def test_checkliste_zusammenstellen_und_klasse(self):
        self.anmelden("verwaltung")
        self.aktion(self.lena, aktion="punkt_neu", **{"punkt-text": "Probeunterricht", "punkt-zustaendig": "koordination", "punkt-pflicht": "on"})
        p = self.lena.punkte.get(text="Probeunterricht")
        self.assertTrue(p.pflicht)
        self.aktion(self.lena, aktion="pflicht", punkt=p.pk)
        p.refresh_from_db()
        self.assertFalse(p.pflicht)
        self.aktion(self.lena, aktion="punkt_loeschen", punkt=p.pk)
        self.assertFalse(AnmeldePunkt.objects.filter(pk=p.pk).exists())
        kl9b = Gruppe.objects.get(schuljahr=self.sj, name="9b")
        self.aktion(self.lena, aktion="klasse", klasse=kl9b.pk)
        self.lena.refresh_from_db()
        self.assertEqual(self.lena.vorlaeufige_klasse, kl9b)
        self.assertEqual(Mitgliedschaft.objects.filter(gruppe=kl9b, schueler__person__vorname="Lena", schueler__person__nachname="Hoffmann").count(), 0)
        self.aktion(self.lena, aktion="status", status="zugesagt")
        self.lena.refresh_from_db()
        self.assertEqual(self.lena.status, "zugesagt")
        self.assertTrue(hindernisse(self.lena))                      # Pflichtpunkte offen
        r = self.client.get(reverse("anmeldung_uebernahme", args=[self.lena.pk]))
        self.assertTrue(r.context["hindernisse"])
        self.client.post(reverse("anmeldung_uebernahme", args=[self.lena.pk]))
        self.assertFalse(Person.objects.filter(nachname="Hoffmann", vorname="Lena").exists())

    def test_seiten_und_menueband(self):
        self.anmelden("verwaltung")
        r = self.client.get(reverse("anmeldungen"))
        self.assertEqual(r.context["MENUEBAND"]["aktiv"], "schueler")
        self.assertEqual(len(r.context["zeilen"]), 4)                 # offen: alle außer „zurückgezogen“
        self.assertContains(r, reverse("anmeldung_neu"))
        r = self.client.get(reverse("anmeldung", args=[self.lena.pk]))
        self.assertContains(r, "Jahreszeugnis Klasse 8")
        self.assertContains(self.client.get(reverse("start")), 'id="neuanmeldungen"')
        self.assertEqual(self.client.get(reverse("anmeldung_neu")).status_code, 200)

    # ------------------------------------------------------------ Übernahme
    def test_uebernahme(self):
        self.anmelden("verwaltung")
        kontakt = self.jonas.kontakte.get()
        vorhandene = Person.objects.filter(email__iexact=kontakt.email).exclude(elternprofil=None).first()
        self.assertIsNotNone(vorhandene)                              # Elternteil eines Geschwisterkindes
        r = self.client.get(reverse("anmeldung_uebernahme", args=[self.jonas.pk]))
        self.assertIn(vorhandene, r.context["kontakte"][0].kandidaten)
        personen_vorher = Person.objects.count()
        r = self.client.post(reverse("anmeldung_uebernahme", args=[self.jonas.pk]),
                             {f"kontakt-{kontakt.pk}": vorhandene.pk, "dateien": "1"})
        self.jonas.refresh_from_db()
        s = self.jonas.schueler
        self.assertRedirects(r, reverse("schuelerakte", args=[s.pk]))
        self.assertEqual(self.jonas.status, Anmeldung.UEBERNOMMEN)
        self.assertEqual(Person.objects.count(), personen_vorher + 1)  # nur das Kind ist neu
        self.assertTrue(Beziehung.objects.filter(schueler=s, person=vorhandene, sorgerecht=True).exists())
        m = Mitgliedschaft.objects.get(schueler=s)
        self.assertEqual((m.gruppe.name, m.von), ("9b", self.jonas.eintritt))
        self.assertEqual(s.laufbahn.get().jahrgang, 9)
        self.assertEqual(s.vorherige_schulen.get().name, "Deutsche Schule Kapstadt")
        docs = Dokument.objects.filter(person=s.person)
        self.assertEqual(docs.count(), self.jonas.dateien.count() + 1)  # Dateien + Checklistenprotokoll
        for d in docs.exclude(datei=""):
            self.assertTrue(d.datei.storage.exists(d.datei.name))
            self.assertNotIn(d.datei.name, AnmeldeDatei.objects.values_list("datei", flat=True))
        self.assertEqual(docs.get(titel__startswith="Aufnahmecheckliste").zugriffsstufe, "verwaltung")
        # abgeschlossen: keine Änderungen mehr, Link in der Schülerakte
        self.assertEqual(self.aktion(self.jonas, aktion="status", status="pruefung").status_code, 403)
        self.assertContains(self.client.get(reverse("schuelerakte", args=[s.pk])), self.jonas.nummer)
        with self.assertRaises(Exception):
            uebernehmen(self.jonas, None)

    def test_uebernahme_dublette_braucht_bestaetigung(self):
        vorhanden = Schuelerprofil.objects.select_related("person").first()
        self.lena.vorname, self.lena.nachname = vorhanden.person.vorname, vorhanden.person.nachname
        self.lena.status = Anmeldung.ZUGESAGT
        self.lena.save()
        for p in self.lena.punkte.all():
            p.abhaken(None)
        self.anmelden("verwaltung")
        url = reverse("anmeldung_uebernahme", args=[self.lena.pk])
        r = self.client.post(url, {})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["fehler"])
        r = self.client.post(url, {"dubletten_geprueft": "1", "dateien": "0"})
        self.lena.refresh_from_db()
        self.assertEqual(self.lena.status, Anmeldung.UEBERNOMMEN)
        self.assertFalse(Dokument.objects.filter(person=self.lena.schueler.person).exclude(datei="").exists())

    def test_schuelernummer(self):
        n = naechste_schuelernummer()
        self.assertFalse(Schuelerprofil.objects.filter(schuelernummer=n).exists())
        self.assertTrue(n.isdigit())

    def test_loeschen_entfernt_dateien(self):
        self.anmelden("verwaltung")
        namen = [d.datei.name for d in self.lena.dateien.all()]
        speicher = self.lena.dateien.first().datei.storage
        self.assertTrue(all(speicher.exists(n) for n in namen))
        self.client.post(reverse("anmeldung_loeschen", args=[self.lena.pk]))
        self.assertFalse(Anmeldung.objects.filter(pk=self.lena.pk).exists())
        self.assertFalse(any(speicher.exists(n) for n in namen))

    def test_englisch(self):
        self.anmelden("verwaltung")
        self.client.post(reverse("sprache_wechseln"), {"sprache": "en", "next": "/"})
        r = self.client.get(reverse("anmeldung", args=[self.lena.pk]))
        self.assertContains(r, "Checklist")
        self.assertContains(r, "Application form complete and signed")
        self.assertContains(self.client.get(reverse("anmeldungen")), "Admissions")
