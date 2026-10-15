"""Tests ab 0.4.7.0: Schnelleingabe, Bewertungsstruktur mit Gewichtsart, Leistungsvorgaben."""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from stammdaten.models import Mitgliedschaft, Person, Schuelerprofil

from . import eingabe as E
from . import vorgaben as V
from .berechnung import vorschlagsnote
from .models import PROZENT, Bewertungsordner, Leistungsnachweis, Leistungsvorgabe, Note, Notenskala, Unterricht

PW = "Test-Passwort-123"


class DeutenTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("grundeinrichtung", stdout=open("/dev/null", "w"))
        cls.sek1 = E.stufen_verzeichnis(Notenskala.objects.get(name__startswith="Sek I –"))
        cls.sek2 = E.stufen_verzeichnis(Notenskala.objects.get(name__startswith="Sek II –"))

    ohne = SimpleNamespace(schluessel_id=None, max_be=None)
    mit_be = SimpleNamespace(schluessel_id=1, max_be=Decimal(40))

    def test_noten_mit_tendenzen(self):
        for text, erwartet in (("2+", "2+"), (" 2 - ", "2-"), ("2−", "2-"), ("2–", "2-"), ("1", "1"), ("6", "6")):
            self.assertEqual(E.deuten(text, self.ohne, self.sek1).stufe.bezeichnung, erwartet, text)
        for falsch in ("7", "0", "6+", "abc", "2++"):
            with self.assertRaises(E.EingabeFehler, msg=falsch):
                E.deuten(falsch, self.ohne, self.sek1)
        self.assertTrue(E.deuten("  ", self.ohne, self.sek1).leer)

    def test_kuerzel(self):
        self.assertEqual(E.deuten("e", self.ohne, self.sek1).status, "entschuldigt")
        self.assertEqual(E.deuten("NB", self.ohne, self.sek1).status, "nicht_bewertbar")
        self.assertEqual(E.deuten("b", self.ohne, self.sek1).status, "befreit")
        g = E.deuten("u 6", self.ohne, self.sek1)
        self.assertEqual((g.status, g.stufe.bezeichnung), ("unentschuldigt", "6"))
        self.assertEqual(E.deuten("u", self.ohne, self.sek1).stufe, None)

    def test_be_und_direkte_note(self):
        self.assertEqual(E.deuten("34,5", self.mit_be, self.sek1).be, Decimal("34.5"))
        self.assertEqual(E.deuten("=2+", self.mit_be, self.sek1).stufe.bezeichnung, "2+")
        for falsch in ("41", "-1", "2+", "3,333"):
            with self.assertRaises(E.EingabeFehler, msg=falsch):
                E.deuten(falsch, self.mit_be, self.sek1)

    def test_punkte(self):
        self.assertEqual(E.deuten("05", self.ohne, self.sek2).stufe.bezeichnung, "5")
        self.assertEqual(E.deuten("15", self.ohne, self.sek2).stufe.bezeichnung, "15")
        with self.assertRaises(E.EingabeFehler):
            E.deuten("16", self.ohne, self.sek2)


class Grundlage(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))
        cls.u = Unterricht.objects.get(fach__kuerzel="CH", gruppe__name="9a", abschnitt__nummer=1)
        cls.q1 = Bewertungsordner.objects.get(unterricht=cls.u, name="Quartal 1")
        cls.schriftlich = Bewertungsordner.objects.get(unterricht=cls.u, name="Schriftlich", eltern=None)
        cls.schueler = list(cls.u.schueler())

    def setUp(self):
        from django.utils import translation

        translation.activate("de")
        self.addCleanup(translation.deactivate)

    def anmelden(self, name):
        self.client.logout()
        self.assertTrue(self.client.login(username=name, password=PW))

    def eingabe_daten(self, **kopf):
        daten = {"ordner": self.q1.pk, "titel": "Mitarbeit 14.10.", "datum": "2026-10-14", "gewicht": "1", "schluessel": "", "max_be": ""}
        daten.update(kopf)
        return daten


class SchnelleingabeTest(Grundlage):
    def test_neuer_leistungsnachweis_mit_noten(self):
        self.anmelden("lehrkraft")
        url = reverse("noten_eintragen", args=[self.u.pk])
        r = self.client.get(url + f"?ordner={self.q1.pk}")
        self.assertContains(r, 'class="ne-note"', count=len(self.schueler))
        s1, s2, s3 = self.schueler[:3]
        daten = self.eingabe_daten(**{f"n_{s1.pk}": "2+", f"k_{s1.pk}": "sehr aktiv", f"n_{s2.pk}": "e", f"n_{s3.pk}": "u 5"})
        r = self.client.post(url, daten)
        self.assertRedirects(r, reverse("notenuebersicht", args=[self.u.pk]))
        ln = Leistungsnachweis.objects.get(unterricht=self.u, titel="Mitarbeit 14.10.")
        self.assertEqual(ln.ordner, self.q1)
        self.assertEqual(ln.noten.count(), len(self.schueler))                 # Notenzeilen für alle
        n1, n2, n3 = (Note.objects.get(leistungsnachweis=ln, schueler=s) for s in (s1, s2, s3))
        self.assertEqual((n1.stufe.bezeichnung, n1.kommentar), ("2+", "sehr aktiv"))
        self.assertEqual((n2.sonderstatus, n2.stufe), ("entschuldigt", None))
        self.assertEqual((n3.sonderstatus, n3.stufe.bezeichnung), ("unentschuldigt", "5"))

    def test_ungueltige_eingabe_speichert_nichts(self):
        self.anmelden("lehrkraft")
        s1, s2 = self.schueler[:2]
        r = self.client.post(reverse("noten_eintragen", args=[self.u.pk]),
                             self.eingabe_daten(**{f"n_{s1.pk}": "2", f"n_{s2.pk}": "7"}))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "keine Note dieser Skala")
        self.assertContains(r, 'value="7"')                                   # Eingaben bleiben erhalten
        self.assertFalse(Leistungsnachweis.objects.filter(titel="Mitarbeit 14.10.").exists())

    def test_bearbeiten_aendern_und_leeren(self):
        ln = Leistungsnachweis.objects.get(unterricht=self.u, titel="Mitarbeit September")
        s1, s2 = self.schueler[:2]
        self.anmelden("lehrkraft")
        url = reverse("noten_bearbeiten", args=[self.u.pk, ln.pk])
        r = self.client.get(url)
        alt = Note.objects.get(leistungsnachweis=ln, schueler=s1)
        self.assertContains(r, f'value="{alt.stufe.bezeichnung}"')
        daten = {"ordner": ln.ordner_id, "titel": ln.titel, "datum": ln.datum.isoformat(), "gewicht": "1", "schluessel": "", "max_be": ""}
        for n in Note.objects.filter(leistungsnachweis=ln).select_related("stufe", "leistungsnachweis"):
            daten[f"n_{n.schueler_id}"] = E.anzeige(n)
        daten[f"n_{s1.pk}"] = "1-"
        daten[f"n_{s2.pk}"] = ""
        r = self.client.post(url, daten)
        self.assertRedirects(r, reverse("notenuebersicht", args=[self.u.pk]))
        self.assertEqual(Note.objects.get(leistungsnachweis=ln, schueler=s1).stufe.bezeichnung, "1-")
        self.assertIsNone(Note.objects.get(leistungsnachweis=ln, schueler=s2).stufe)
        self.assertEqual(Note.history.filter(leistungsnachweis_id=ln.pk, schueler_id=s1.pk).count(), 2)  # angelegt + geändert

    def test_be_mit_notenschluessel(self):
        ka = Leistungsnachweis.objects.get(unterricht=self.u, titel="1. Klassenarbeit")
        s1 = self.schueler[0]
        self.anmelden("lehrkraft")
        daten = {"ordner": ka.ordner_id, "titel": ka.titel, "datum": ka.datum.isoformat(), "gewicht": "1",
                 "schluessel": ka.schluessel_id, "max_be": "40", f"n_{s1.pk}": "40"}
        self.client.post(reverse("noten_bearbeiten", args=[self.u.pk, ka.pk]), daten)
        n = Note.objects.get(leistungsnachweis=ka, schueler=s1)
        self.assertEqual(n.erreichte_be, Decimal(40))
        self.assertEqual(n.stufe, ka.schluessel.stufe_fuer_prozent(Decimal(100)))

    def test_einzelgewicht_braucht_begruendung(self):
        s1 = self.schueler[0]
        self.anmelden("lehrkraft")
        url = reverse("noten_eintragen", args=[self.u.pk])
        r = self.client.post(url, self.eingabe_daten(**{f"n_{s1.pk}": "3", f"g_{s1.pk}": "0,5"}))
        self.assertContains(r, "Abweichendes Gewicht bitte begründen")
        r = self.client.post(url, self.eingabe_daten(**{f"n_{s1.pk}": "3", f"g_{s1.pk}": "0,5", f"b_{s1.pk}": "Nachschreibtest verkürzt"}))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Note.objects.get(leistungsnachweis__titel="Mitarbeit 14.10.", schueler=s1).gewicht_individuell, Decimal("0.5"))

    def test_speichern_und_naechster(self):
        self.anmelden("lehrkraft")
        r = self.client.post(reverse("noten_eintragen", args=[self.u.pk]), {**self.eingabe_daten(), "weiter": "neu"})
        self.assertRedirects(r, reverse("noten_eintragen", args=[self.u.pk]) + f"?ordner={self.q1.pk}")

    def test_rechte(self):
        url = reverse("noten_eintragen", args=[self.u.pk])
        for name, erwartet in (("verwaltung", 403), ("verwaltungsleitung", 403), ("schulleitung", 200), ("lehrkraft", 200)):
            self.anmelden(name)
            self.assertEqual(self.client.get(url).status_code, erwartet, name)
        fremd = Unterricht.objects.get(fach__kuerzel="M", gruppe__name="9a")
        self.anmelden("lehrkraft")
        self.assertEqual(self.client.get(reverse("noten_eintragen", args=[fremd.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("bewertungsstruktur", args=[fremd.pk])).status_code, 403)

    def test_notenuebersicht_verlinkt_schnelleingabe(self):
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("notenuebersicht", args=[self.u.pk]))
        self.assertContains(r, reverse("noten_eintragen", args=[self.u.pk]))
        ln = Leistungsnachweis.objects.filter(unterricht=self.u).first()
        self.assertContains(r, reverse("noten_bearbeiten", args=[self.u.pk, ln.pk]))
        self.assertNotContains(r, 'class="ln-titel" href="/verwaltung/')


class StrukturTest(Grundlage):
    def struktur_daten(self, **extra):
        daten = {"aktion": "speichern"}
        daten.update(extra)
        return daten

    def test_prozent_gewichte_rechnen_wie_relative(self):
        mitarbeit = Bewertungsordner.objects.get(unterricht=self.u, name="Sonstige Mitarbeit", eltern=None)
        q2 = Bewertungsordner.objects.get(unterricht=self.u, name="Quartal 2")
        vorher = [vorschlagsnote(self.u, s).schnitt for s in self.schueler]
        self.anmelden("lehrkraft")
        r = self.client.post(reverse("bewertungsstruktur", args=[self.u.pk]), self.struktur_daten(**{
            f"art_{mitarbeit.pk}": PROZENT, f"gewicht_{self.q1.pk}": "50", f"gewicht_{q2.pk}": "50"}))
        self.assertRedirects(r, reverse("bewertungsstruktur", args=[self.u.pk]))
        mitarbeit.refresh_from_db()
        self.assertEqual(mitarbeit.gewichtsart, PROZENT)
        self.assertEqual([vorschlagsnote(self.u, s).schnitt for s in self.schueler], vorher)   # 1:1 = 50:50
        r = self.client.get(reverse("notenuebersicht", args=[self.u.pk]))
        self.assertContains(r, "50 %")

    def test_prozent_hoechstens_100_und_nichts_halb_gespeichert(self):
        mitarbeit = Bewertungsordner.objects.get(unterricht=self.u, name="Sonstige Mitarbeit", eltern=None)
        self.anmelden("lehrkraft")
        r = self.client.post(reverse("bewertungsstruktur", args=[self.u.pk]), self.struktur_daten(**{
            f"art_{mitarbeit.pk}": PROZENT, f"name_{mitarbeit.pk}": "Mitarbeit neu", f"gewicht_{self.q1.pk}": "120"}), follow=True)
        self.assertContains(r, "höchstens 100")
        mitarbeit.refresh_from_db()
        self.assertEqual((mitarbeit.name, mitarbeit.gewichtsart), ("Sonstige Mitarbeit", "relativ"))

    def test_summenhinweis(self):
        mitarbeit = Bewertungsordner.objects.get(unterricht=self.u, name="Sonstige Mitarbeit", eltern=None)
        mitarbeit.gewichtsart = PROZENT
        mitarbeit.save()
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("bewertungsstruktur", args=[self.u.pk]))
        self.assertContains(r, "es fehlen 98 %")                             # Quartal 1 und 2 je Gewicht 1

    def test_ordner_anlegen_loeschen_und_ln_loeschen(self):
        url = reverse("bewertungsstruktur", args=[self.u.pk])
        self.anmelden("lehrkraft")
        # oberste Ebene ist durch die Klausurregel der Demo-Daten vorgegeben (ab 0.4.8.0) – daher in „Sonstige Mitarbeit“
        mitarbeit = Bewertungsordner.objects.get(unterricht=self.u, name="Sonstige Mitarbeit", eltern=None)
        self.client.post(url, {"aktion": "ordner_neu", "name": "Referate", "eltern": str(mitarbeit.pk), "gewicht": "10"})
        neu = Bewertungsordner.objects.get(unterricht=self.u, name="Referate")
        self.assertEqual((neu.eltern, neu.gewicht), (mitarbeit, Decimal(10)))
        r = self.client.post(url, {"aktion": f"ordner_loeschen:{self.q1.pk}"}, follow=True)
        self.assertContains(r, "Nur leere Ordner")
        self.client.post(url, {"aktion": f"ordner_loeschen:{neu.pk}"})
        self.assertFalse(Bewertungsordner.objects.filter(pk=neu.pk).exists())
        ln = Leistungsnachweis.objects.get(unterricht=self.u, titel="Protokoll Flammenfärbung")
        self.client.post(url, {"aktion": f"ln_loeschen:{ln.pk}"})
        self.assertFalse(Leistungsnachweis.objects.filter(pk=ln.pk).exists())
        # doppelter Name auf derselben Ebene
        r = self.client.post(url, {"aktion": "ordner_neu", "name": "Schriftlich", "eltern": ""}, follow=True)
        self.assertEqual(Bewertungsordner.objects.filter(unterricht=self.u, name="Schriftlich").count(), 1)


class VorgabenTest(Grundlage):
    def vorgabe(self, **kw):
        daten = {"titel": "Test-Vorgabe", "abschnitt": self.u.abschnitt, "jahrgang_von": 9, "jahrgang_bis": 9,
                 "mindestanzahl": 1, "frist": timezone.localdate() + timedelta(days=3)}
        daten.update(kw)
        return Leistungsvorgabe.objects.create(**daten)

    def test_stand(self):
        heute = date(2026, 10, 20)
        v = self.vorgabe(ordner_enthaelt="Quartal 1", frist=date(2026, 10, 30))
        self.assertEqual(V.stand(v, self.u, heute=heute).stand, V.ERFUELLT)
        v2 = self.vorgabe(ordner_enthaelt="Quartal 1", mindestanzahl=3, frist=date(2026, 10, 30))
        st = V.stand(v2, self.u, heute=heute)
        self.assertEqual((st.stand, st.vollstaendig), (V.IN_ARBEIT, 2))
        self.assertEqual(V.stand(v2, self.u, heute=date(2026, 11, 2)).stand, V.UEBERFAELLIG)
        v3 = self.vorgabe(titel_enthaelt="Referat", frist=date(2026, 10, 30))
        self.assertEqual(V.stand(v3, self.u, heute=heute).stand, V.OFFEN)
        # Leistungsnachweise nach der Frist zählen nicht
        v4 = self.vorgabe(titel_enthaelt="Test Atombau", frist=date(2026, 10, 1))
        self.assertEqual(V.stand(v4, self.u, heute=heute).stand, V.UEBERFAELLIG)

    def test_fehlende_note_und_spaeter_hinzugekommene(self):
        v = self.vorgabe(titel_enthaelt="Mitarbeit September", frist=date(2026, 10, 30))
        ln = Leistungsnachweis.objects.get(unterricht=self.u, titel="Mitarbeit September")
        heute = date(2026, 10, 20)
        # neu in der Klasse nach dem Datum des Leistungsnachweises: zählt nicht
        p = Person.objects.create(vorname="Neu", nachname="Zugezogen")
        neu = Schuelerprofil.objects.create(person=p, schuelernummer="NEU-77")
        Mitgliedschaft.objects.create(gruppe=self.u.gruppe, schueler=neu, von=date(2026, 10, 5))
        self.assertEqual(V.stand(v, self.u, heute=heute).stand, V.ERFUELLT)
        # Note einer Schülerin entfernt: nicht mehr vollständig
        Note.objects.filter(leistungsnachweis=ln, schueler=self.schueler[0]).update(stufe=None, sonderstatus="")
        self.assertEqual(V.stand(v, self.u, heute=heute).stand, V.IN_ARBEIT)
        # Vermerk zählt als eingetragen
        Note.objects.filter(leistungsnachweis=ln, schueler=self.schueler[0]).update(sonderstatus="entschuldigt")
        self.assertEqual(V.stand(v, self.u, heute=heute).stand, V.ERFUELLT)

    def test_faecher_und_jahrgaenge(self):
        v = self.vorgabe(jahrgang_von=5, jahrgang_bis=8)
        self.assertNotIn(self.u, list(v.unterrichte()))
        v = self.vorgabe()
        v.faecher.set([Unterricht.objects.get(fach__kuerzel="M", gruppe__name="9a").fach])
        self.assertNotIn(self.u, list(v.unterrichte()))
        self.assertNotIn(v, list(V.vorgaben_fuer(self.u)))
        v.faecher.add(self.u.fach)
        self.assertIn(v, list(V.vorgaben_fuer(self.u)))

    def formular(self, **kw):
        daten = {"titel": "Klassenarbeit bis Weihnachten", "titel_en": "", "abschnitt": self.u.abschnitt_id, "jahrgang_von": "5",
                 "jahrgang_bis": "10", "ordner_enthaelt": "", "titel_enthaelt": "Klassenarbeit", "mindestanzahl": "1",
                 "frist": "2026-12-18", "hinweis": ""}
        daten.update(kw)
        return daten

    def test_anlegen_und_rechte(self):
        self.anmelden("schulleitung")
        r = self.client.post(reverse("vorgabe_neu"), self.formular())
        self.assertEqual(r.status_code, 302)
        v = Leistungsvorgabe.objects.get(titel="Klassenarbeit bis Weihnachten")
        self.assertEqual(v.angelegt_von.username, "schulleitung")
        # Mittelstufe: 5–10 ja, 11–12 nein
        self.anmelden("mittelstufe")
        r = self.client.post(reverse("vorgabe_neu"), self.formular(titel="Oberstufe", jahrgang_von="11", jahrgang_bis="12"))
        self.assertContains(r, "nur für die Jahrgänge")
        self.assertEqual(self.client.post(reverse("vorgabe_bearbeiten", args=[v.pk]), self.formular(titel="geändert")).status_code, 302)
        # Oberstufe darf eine Vorgabe für 5–10 nicht ändern oder löschen
        self.anmelden("oberstufe")
        self.assertEqual(self.client.get(reverse("vorgabe_bearbeiten", args=[v.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("vorgabe_loeschen", args=[v.pk])).status_code, 403)
        # Lehrkraft: lesen ja, anlegen nein
        self.anmelden("lehrkraft")
        self.assertEqual(self.client.get(reverse("vorgabe_neu")).status_code, 403)
        self.assertEqual(self.client.get(reverse("leistungsvorgaben")).status_code, 200)
        # Stellvertretung darf löschen
        self.anmelden("stellvertretung")
        self.client.post(reverse("vorgabe_loeschen", args=[v.pk]))
        self.assertFalse(Leistungsvorgabe.objects.filter(pk=v.pk).exists())

    def test_frist_im_halbjahr(self):
        self.anmelden("schulleitung")
        r = self.client.post(reverse("vorgabe_neu"), self.formular(frist="2027-05-01"))
        self.assertContains(r, "Die Frist muss im Halbjahr liegen")

    def test_uebersicht_lehrkraft_sieht_nur_eigenen_unterricht(self):
        self.vorgabe(titel="Für alle Fächer")
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("leistungsvorgaben") + f"?abschnitt={self.u.abschnitt_id}")
        self.assertContains(r, "Für alle Fächer")
        self.assertContains(r, reverse("notenuebersicht", args=[self.u.pk]))
        fremd = Unterricht.objects.get(fach__kuerzel="M", gruppe__name="9a")
        self.assertNotContains(r, reverse("notenuebersicht", args=[fremd.pk]))
        self.anmelden("schulleitung")
        r = self.client.get(reverse("leistungsvorgaben") + f"?abschnitt={self.u.abschnitt_id}")
        self.assertContains(r, reverse("notenuebersicht", args=[fremd.pk]))

    def test_startseite_und_notenuebersicht(self):
        self.vorgabe(titel="Referat bald fällig", titel_enthaelt="Referat")
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("start"))
        self.assertContains(r, "Referat bald fällig")
        r = self.client.get(reverse("notenuebersicht", args=[self.u.pk]))
        self.assertContains(r, "Referat bald fällig")
        self.assertContains(r, 'class="nv-stand offen"')
        # Leitung: Hinweis auf überfällige Vorgaben
        self.vorgabe(titel="Längst fällig", titel_enthaelt="Referat", frist=self.u.abschnitt.beginn + timedelta(days=10))
        self.anmelden("schulleitung")
        self.assertContains(self.client.get(reverse("start")), "überfällig")
