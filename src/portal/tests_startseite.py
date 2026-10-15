"""Tests für die Startseite: Geburtstage, Notizen, Mitteilungen, Suche (seit Version 0.4.2.1)."""
from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from stammdaten.models import Gruppe, Personalprofil, Schuelerprofil

from .models import Notiz
from .startseite import _naechster_geburtstag, geburtstage

PW = "Test-Passwort-123"


class NaechsterGeburtstagTest(SimpleTestCase):
    def test_heute_und_spaeter(self):
        self.assertEqual(_naechster_geburtstag(date(2011, 10, 13), date(2026, 10, 13)), date(2026, 10, 13))
        self.assertEqual(_naechster_geburtstag(date(2011, 10, 12), date(2026, 10, 13)), date(2027, 10, 12))

    def test_jahreswechsel(self):
        self.assertEqual(_naechster_geburtstag(date(2010, 1, 2), date(2026, 12, 30)), date(2027, 1, 2))

    def test_29_februar(self):
        self.assertEqual(_naechster_geburtstag(date(2012, 2, 29), date(2027, 2, 20)), date(2027, 2, 28))
        self.assertEqual(_naechster_geburtstag(date(2012, 2, 29), date(2028, 2, 20)), date(2028, 2, 29))


class StartseiteTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))
        cls.fremd = User.objects.create_user("fremd", password=PW, is_staff=True)
        cls.fremd.groups.add(Group.objects.get(name="Lehrer:in"))
        cls.heute = timezone.localdate()
        cls.s9a = Gruppe.objects.get(name="9a").aktuelle_mitglieder().order_by("person__nachname").first()

    def anmelden(self, name):
        self.client.logout()
        self.assertTrue(self.client.login(username=name, password=PW))

    def namen(self, user):
        return {e["name"] for g in geburtstage(user, self.heute) for e in g["eintraege"]}

    # --------------------------------------------------------------- Geburtstage
    def test_geburtstag_heute_mit_alter(self):
        gruppen = geburtstage(User.objects.get(username="lehrkraft"), self.heute)
        self.assertEqual(gruppen[0]["abstand"], 0)
        eintrag = next(e for e in gruppen[0]["eintraege"] if e["name"] == self.s9a.person.anzeigename)
        self.assertEqual(eintrag["alter"], self.heute.year - self.s9a.person.geburtsdatum.year)
        self.assertTrue(eintrag["url"])  # Klassenleitung darf die Akte öffnen

    def test_nur_sieben_tage(self):
        for g in geburtstage(User.objects.get(username="verwaltung"), self.heute):
            self.assertTrue(0 <= g["abstand"] <= 7)

    def test_sichtbarkeit_schueler(self):
        alle = self.namen(User.objects.get(username="verwaltung"))
        fremd = self.namen(self.fremd)
        schueler_namen = {s.person.anzeigename for s in Schuelerprofil.objects.all()}
        self.assertTrue(alle & schueler_namen)
        self.assertFalse(fremd & schueler_namen)  # Lehrkraft ohne Klassen und Kurse sieht keine Schüler:innen
        # Kolleg:innen sieht jedes Personal-Konto, aber ohne Altersangabe
        kollegen = [e for g in geburtstage(self.fremd, self.heute) for e in g["eintraege"]]
        self.assertTrue(kollegen)
        self.assertTrue(all(e["alter"] is None for e in kollegen))

    def test_widerspruch_blendet_aus(self):
        p = self.s9a.person
        p.geburtstag_anzeigen = False
        p.save()
        self.assertNotIn(p.anzeigename, self.namen(User.objects.get(username="verwaltung")))

    def test_abgegangene_und_inaktive_nicht(self):
        Schuelerprofil.objects.filter(pk=self.s9a.pk).update(status="abgang")
        self.assertNotIn(self.s9a.person.anzeigename, self.namen(User.objects.get(username="verwaltung")))
        pp = Personalprofil.objects.get(kuerzel="MUE")
        pp.aktiv = False
        pp.save()
        self.assertNotIn(pp.person.anzeigename, self.namen(User.objects.get(username="verwaltung")))

    def test_karte_auf_startseite(self):
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("start"))
        self.assertContains(r, 'id="geburtstage"')
        self.assertContains(r, "Heute")
        self.assertContains(r, self.s9a.person.anzeigename)

    # --------------------------------------------------------------- Notizen
    def test_notiz_anlegen_und_privat(self):
        self.anmelden("lehrkraft")
        self.client.post(reverse("notiz_anlegen"), {"notiz-text": "Kreide kaufen", "notiz-farbe": "blau"})
        n = Notiz.objects.get(text="Kreide kaufen")
        self.assertEqual(n.besitzer.username, "lehrkraft")
        self.assertEqual(n.sichtbarkeit, Notiz.PRIVAT)
        self.assertContains(self.client.get(reverse("start")), "Kreide kaufen")
        self.anmelden("verwaltung")
        self.assertNotContains(self.client.get(reverse("start")), "Kreide kaufen")
        self.assertEqual(self.client.post(reverse("notiz_aktion", args=[n.pk]), {"aktion": "loeschen"}).status_code, 403)
        self.assertTrue(Notiz.objects.filter(pk=n.pk).exists())

    def test_leere_notiz_wird_abgelehnt(self):
        self.anmelden("lehrkraft")
        vorher = Notiz.objects.count()
        self.client.post(reverse("notiz_anlegen"), {"notiz-text": "", "notiz-farbe": "gelb"})
        self.assertEqual(Notiz.objects.count(), vorher)

    def test_erledigt_anheften_bearbeiten_loeschen(self):
        self.anmelden("lehrkraft")
        n = Notiz.objects.create(besitzer=User.objects.get(username="lehrkraft"), text="Test")
        url = reverse("notiz_aktion", args=[n.pk])
        self.client.post(url, {"aktion": "anheften"})
        n.refresh_from_db()
        self.assertTrue(n.angeheftet)
        self.client.post(url, {"aktion": "erledigt"})
        n.refresh_from_db()
        self.assertTrue(n.erledigt)
        self.assertFalse(n.angeheftet)
        self.client.post(reverse("notiz_aendern", args=[n.pk]), {f"n{n.pk}-text": "Geändert", f"n{n.pk}-farbe": "rosa",
                                                                 f"n{n.pk}-datum": self.heute.isoformat()})
        n.refresh_from_db()
        self.assertEqual((n.text, n.farbe, n.datum), ("Geändert", "rosa", self.heute))
        self.client.post(reverse("notizen_erledigte_loeschen"))
        self.assertFalse(Notiz.objects.filter(pk=n.pk).exists())

    def test_faellige_notiz(self):
        n = Notiz.objects.create(besitzer=User.objects.get(username="lehrkraft"), text="x", datum=self.heute - timedelta(days=1))
        self.assertTrue(n.faellig)
        n.datum = self.heute + timedelta(days=1)
        self.assertFalse(n.faellig)

    def test_mitteilung_nur_durch_verwaltung(self):
        self.anmelden("lehrkraft")
        self.client.post(reverse("notiz_anlegen"), {"notiz-text": "An alle?", "notiz-farbe": "gelb", "notiz-sichtbarkeit": "alle"})
        self.assertEqual(Notiz.objects.get(text="An alle?").sichtbarkeit, Notiz.PRIVAT)
        self.anmelden("verwaltung")
        self.client.post(reverse("notiz_anlegen"), {"notiz-text": "Schulfest am Samstag", "notiz-farbe": "gruen",
                                                    "notiz-sichtbarkeit": "alle"})
        m = Notiz.objects.get(text="Schulfest am Samstag")
        self.assertEqual(m.sichtbarkeit, Notiz.ALLE)
        self.anmelden("fremd")
        r = self.client.get(reverse("start"))
        self.assertContains(r, "Schulfest am Samstag")
        self.assertEqual(self.client.post(reverse("notiz_aktion", args=[m.pk]), {"aktion": "loeschen"}).status_code, 403)

    def test_abgelaufene_mitteilung_verschwindet(self):
        Notiz.objects.create(besitzer=User.objects.get(username="verwaltung"), text="Alte Mitteilung",
                             sichtbarkeit=Notiz.ALLE, datum=self.heute - timedelta(days=1))
        self.anmelden("lehrkraft")
        self.assertNotContains(self.client.get(reverse("start")), "Alte Mitteilung")

    # --------------------------------------------------------------- Suche
    def test_suche_klassenleitung(self):
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("suche"), {"q": self.s9a.person.nachname})
        self.assertIn(self.s9a.pk, [e["s"].pk for e in r.context["schueler"]])
        self.assertTrue(all(e["akte"] or e["s"].pk != self.s9a.pk for e in r.context["schueler"]))

    def test_suche_fremde_lehrkraft_findet_keine_schueler(self):
        self.anmelden("fremd")
        r = self.client.get(reverse("suche"), {"q": self.s9a.person.nachname})
        self.assertEqual(r.context["schueler"], [])

    def test_suche_kollegium_und_mindestlaenge(self):
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("suche"), {"q": "Müller"})
        self.assertTrue(any(e["pp"].kuerzel == "MUE" for e in r.context["personal"]))
        self.assertTrue(self.client.get(reverse("suche"), {"q": "M"}).context["zu_kurz"])

    # --------------------------------------------------------------- Darstellung
    def test_startseite_fuer_alle_rollen_und_sprachen(self):
        for name in ("lehrkraft", "verwaltung", "personal", "foerderung", "fremd"):
            for sprache in ("de", "en"):
                self.anmelden(name)
                self.client.post(reverse("sprache_wechseln"), {"sprache": sprache, "next": "/"})
                r = self.client.get(reverse("start"))
                self.assertEqual(r.status_code, 200, (name, sprache))
                self.assertContains(r, "kalenderblatt")
        r = self.client.get(reverse("start"))
        self.assertContains(r, "Birthdays")
        self.assertContains(r, "Notes")

    def test_schnellzugriff_kacheln(self):
        self.anmelden("lehrkraft")
        sz = self.client.get(reverse("start")).context["schnellzugriff"]
        self.assertIn("9a", [k["titel"] for k in sz["klassen"]])
        self.assertTrue(any(k["titel"].startswith("Chemie") for k in sz["kurse"]))


class MenuebandTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))

    def anmelden(self, name):
        self.client.logout()
        self.assertTrue(self.client.login(username=name, password=PW))

    def band(self, url="/"):
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        return r.context["MENUEBAND"], r

    def befehle(self, mb):
        return {b["titel"]: b for k in mb["karten"] for g in k["gruppen"] for b in g.befehle}

    def test_karten_je_rolle(self):
        erwartet = {
            "lehrkraft": {"start", "termine", "schueler", "unterricht", "foerderung"},
            "verwaltung": {"start", "termine", "schueler", "unterricht", "foerderung", "personal", "verwaltung"},
            "personal": {"start", "termine", "schueler", "personal", "verwaltung", "system"},
            "foerderung": {"start", "termine", "schueler", "unterricht", "foerderung"},
            "schulleitung": {"start", "termine", "schueler", "unterricht", "foerderung", "schulleitung", "verwaltung", "personal", "system"},
            "finanzen": {"start", "termine", "schueler", "verwaltung"},
            "stellvertretung": {"start", "termine", "schueler", "unterricht", "foerderung"},
        }
        for name, karten in erwartet.items():
            self.anmelden(name)
            mb, _ = self.band()
            self.assertEqual({k["schluessel"] for k in mb["karten"]}, karten, name)

    def test_rechte_im_band(self):
        self.anmelden("lehrkraft")
        mb, r = self.band()
        b = self.befehle(mb)
        auswahl = [g.auswahl for k in mb["karten"] for g in k["gruppen"] if g.auswahl]
        self.assertEqual(len(auswahl), 1)      # eigener Unterricht als Auswahlliste (ab 0.4.7.1)
        self.assertIn("Chemie 9a", [kurs["titel"] for g in auswahl[0]["gruppen"] for kurs in g["kurse"]])
        self.assertIn("9a", b)                 # eigene Klasse
        self.assertNotIn("Personalliste", b)
        self.assertNotIn("Alle Schüler:innen", b)
        self.assertNotIn("Unterrichtsverteilung", b)
        self.assertContains(r, 'role="tablist"')
        self.anmelden("verwaltung")
        mb = self.band()[0]
        b = self.befehle(mb)
        for titel in ("Alle Schüler:innen", "Schüler:in anlegen", "AG-Angebote", "Personalliste", "Archiv"):
            self.assertIn(titel, b)
        self.assertNotIn("Förderpläne", b)    # Förderpläne sind dem Förderteam vorbehalten
        # Sekretariat: Verwaltung (Administration), aber nicht die akademische Verwaltung der Schulleitung
        self.assertNotIn("schulleitung", {k["schluessel"] for k in mb["karten"]})
        for titel in ("Schuljahreswechsel", "Unterrichtsverteilung", "Löschfristen"):
            self.assertNotIn(titel, b)
        self.anmelden("schulleitung")
        mb = self.band()[0]
        karten = {k["schluessel"]: {bf["titel"] for g in k["gruppen"] for bf in g.befehle} for k in mb["karten"]}
        self.assertTrue({"Schuljahreswechsel", "Schuljahre", "Unterrichtsverteilung", "Archiv", "Löschfristen"} <= karten["schulleitung"])
        self.assertTrue({"Schüler:in anlegen", "AG-Angebote", "Rechnungsempfänger"} <= karten["verwaltung"])
        self.assertTrue({"Benutzerkonten", "Sicherung"} <= karten["system"])

    def test_aktive_karte_nach_seite(self):
        from noten.models import Unterricht

        self.anmelden("lehrkraft")
        u = Unterricht.objects.get(fach__kuerzel="CH", gruppe__name="9a")
        self.assertEqual(self.band(reverse("notenuebersicht", args=[u.pk]))[0]["aktiv"], "unterricht")
        self.assertEqual(self.band(reverse("admin:noten_leistungsnachweis_changelist"))[0]["aktiv"], "unterricht")
        self.assertEqual(self.band(reverse("admin:foerderung_foerderplan_changelist"))[0]["aktiv"], "foerderung")
        mb, r = self.band(reverse("admin:noten_leistungsnachweis_changelist"))
        self.assertTrue(self.befehle(mb)["Leistungsnachweise"]["aktiv"])
        self.assertContains(r, 'aria-current="page"')
        self.assertEqual(self.band("/")[0]["aktiv"], "start")

    def test_band_auch_in_der_verwaltungsoberflaeche(self):
        self.anmelden("verwaltung")
        r = self.client.get(reverse("admin:index"))
        self.assertContains(r, 'id="menueband"')
        self.assertContains(r, "menueband.js")

    def test_englisch(self):
        self.anmelden("lehrkraft")
        self.client.post(reverse("sprache_wechseln"), {"sprache": "en", "next": "/"})
        mb, r = self.band()
        self.assertEqual([k["titel"] for k in mb["karten"]][:3], ["Home", "Calendar", "Students"])
        self.assertContains(r, "Hide ribbon")

    def test_begriff_unterricht(self):
        self.anmelden("verwaltung")
        r = self.client.get("/")
        self.assertNotContains(r, "Unterrichte")
        self.assertContains(r, "Unterricht im Schuljahr")


class NurPersonalTest(TestCase):
    def setUp(self):
        self.konto = User.objects.create_user("elternteil", password=PW)  # weder Personal noch Verwaltung

    def test_anmeldung_abgelehnt(self):
        r = self.client.post(reverse("login"), {"username": "elternteil", "password": PW})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "nur für Beschäftigte")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_bestehende_sitzung_wird_beendet(self):
        self.client.force_login(self.konto)
        r = self.client.get(reverse("start"))
        self.assertRedirects(r, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_personal_ohne_verwaltungszugang_darf(self):
        from stammdaten.models import Person, Personalbereich

        call_command("grundeinrichtung", stdout=open("/dev/null", "w"))
        p = Person.objects.create(vorname="Ann", nachname="Wanjiru", benutzer=self.konto)
        Personalprofil.objects.create(person=p, bereich=Personalbereich.objects.first())
        self.client.force_login(self.konto)
        self.assertEqual(self.client.get(reverse("start")).status_code, 200)
