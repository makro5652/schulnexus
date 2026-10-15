"""Tests für Zeugnisse, Kommentare, Versetzungsregeln und Konferenzen (seit Version 0.4.2.7)."""
import os
from decimal import Decimal

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from noten.models import Notenskala, Unterricht, Zeugnisnote
from stammdaten.models import Gruppe, Schuljahr

from .models import Abzeichnung, Anmerkung, Konferenz, Zeugnis
from .noten import fachnoten, ganze_note
from .versetzung import AUSGLEICH, NICHT, VERSETZT, Fachnote, pruefen

PW = "Test-Passwort-123"
ART = {"D": (True, False), "M": (True, False), "E": (True, False), "F": (True, False), "BIO": (False, False),
       "CH": (False, False), "G": (False, False), "MU": (False, True), "SP": (False, True), "KU": (False, True)}


def noten(**abweichend):
    n = {"D": 3, "M": 3, "E": 3, "F": 3, "BIO": 4, "CH": 4, "G": 4, "MU": 2, "SP": 2, "KU": 3}
    n.update(abweichend)
    return [Fachnote(k, k, v, *ART[k]) for k, v in n.items()]


class VersetzungsregelnTest(SimpleTestCase):
    """Ziffer 5.3 der Richtlinie Sek I an Deutschen Schulen im Ausland (18.03.2026)."""

    def test_alles_ausreichend(self):
        self.assertEqual(pruefen(noten()).ergebnis, VERSETZT)

    def test_ein_nebenfach_mangelhaft_ohne_ausgleich(self):
        e = pruefen(noten(CH=5))
        self.assertEqual(e.ergebnis, VERSETZT)
        self.assertTrue(e.gefaehrdet)

    def test_kernfach_mangelhaft_ausgleich_durch_kernfach(self):
        e = pruefen(noten(D=5))
        self.assertEqual(e.ergebnis, AUSGLEICH)
        self.assertEqual(len(e.ausgleich), 1)
        self.assertIn(e.ausgleich[0], {"M", "E", "F"})

    def test_kernfach_mangelhaft_ohne_kernausgleich(self):
        e = pruefen(noten(D=5, M=4, E=4, F=4), jahrgang=8)
        self.assertEqual(e.ergebnis, NICHT)
        self.assertEqual(e.nachpruefung, ["D"])

    def test_nachpruefung_erst_ab_jahrgang_7(self):
        self.assertEqual(pruefen(noten(D=5, M=4, E=4, F=4), jahrgang=6).nachpruefung, [])

    def test_kern_und_nebenfach_mangelhaft(self):
        self.assertEqual(pruefen(noten(D=5, CH=5)).ergebnis, AUSGLEICH)
        # Ausgleich nur durch Kunst/Musik/Sport reicht nicht (höchstens eines, mindestens ein Kernfach)
        self.assertEqual(pruefen(noten(D=5, CH=5, M=4, E=4, F=4)).ergebnis, NICHT)

    def test_zwei_nebenfaecher_mangelhaft(self):
        self.assertEqual(pruefen(noten(CH=5, BIO=5)).ergebnis, AUSGLEICH)
        e = pruefen(noten(CH=5, BIO=5, D=4, M=4, E=4, F=4, KU=4))     # nur MU, SP gut – beide musisch
        self.assertEqual(e.ergebnis, NICHT)

    def test_nebenfach_ungenuegend_braucht_drei_mit_kernfach(self):
        e = pruefen(noten(CH=6))
        self.assertEqual(e.ergebnis, AUSGLEICH)
        self.assertEqual(len(e.ausgleich), 3)
        self.assertTrue(any(f in {"D", "M", "E", "F"} for f in e.ausgleich))

    def test_kernfach_ungenuegend_schliesst_aus(self):
        e = pruefen(noten(M=6), jahrgang=9)
        self.assertEqual(e.ergebnis, NICHT)
        self.assertEqual(e.nachpruefung, [])

    def test_ausschlussgruende(self):
        self.assertEqual(pruefen(noten(CH=5, BIO=5, G=5)).ergebnis, NICHT)
        self.assertEqual(pruefen(noten(CH=5, BIO=6)).ergebnis, NICHT)
        self.assertEqual(pruefen(noten(CH=6, BIO=6)).ergebnis, NICHT)
        self.assertEqual(pruefen(noten(D=5, M=5)).ergebnis, NICHT)

    def test_nicht_bewertet_bleibt_ausser_betracht(self):
        self.assertEqual(pruefen(noten(CH=None, BIO=None)).ergebnis, VERSETZT)


class ZeugnisTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open(os.devnull, "w"))
        cls.sj = Schuljahr.aktuelles()
        cls.hj1 = cls.sj.abschnitte.get(nummer=1)
        cls.kl9a = Gruppe.objects.get(schuljahr=cls.sj, name="9a")
        cls.schueler = list(cls.kl9a.aktuelle_mitglieder().order_by("person__nachname", "person__vorname"))
        cls.ch9a = Unterricht.objects.get(abschnitt=cls.hj1, gruppe=cls.kl9a, fach__kuerzel="CH")
        cls.m9a = Unterricht.objects.get(abschnitt=cls.hj1, gruppe=cls.kl9a, fach__kuerzel="M")

    def anmelden(self, name):
        self.client.logout()
        self.assertTrue(self.client.login(username=name, password=PW))

    def zeugnis(self, i=0):
        return Zeugnis.objects.get(schueler=self.schueler[i], abschnitt=self.hj1)

    # ------------------------------------------------------------ Noten
    def test_ganze_noten_und_reihenfolge(self):
        sek1 = Notenskala.objects.get(name__startswith="Sek I –")
        self.assertEqual(ganze_note(sek1.stufen.get(bezeichnung="2+")), (2, False))
        self.assertEqual(ganze_note(sek1.stufen.get(bezeichnung="4-")), (4, False))
        zeilen = fachnoten(self.schueler[0], self.hj1, Zeugnis.HALBJAHR)
        links = [e["fach"].kuerzel for e in zeilen if e["fach"].zeugnisspalte == 1]
        rechts = [e["fach"].kuerzel for e in zeilen if e["fach"].zeugnisspalte == 2]
        self.assertEqual(links[:2], ["D", "E"])
        self.assertLess(links.index("G"), max(links.index(k) for k in links if k in ("ETH", "REL")))
        self.assertEqual(rechts[0], "M")
        self.assertEqual(rechts[-1], "SPO")

    def test_zeugnisnote_ganze_note_ohne_begruendung(self):
        sek1 = self.ch9a.skala
        s = self.schueler[0]
        z = Zeugnisnote(unterricht=self.ch9a, schueler=s, vorschlag=Decimal("2.30"), stufe=sek1.stufen.get(bezeichnung="2"))
        z.clean()                                                       # 2,3 → ganze Note 2: keine Abweichung
        self.assertFalse(z.abweichung)
        z.stufe = sek1.stufen.get(bezeichnung="3")
        z.clean()                                                       # ab 0.4.8.1: erlaubt, nur markiert
        self.assertTrue(z.abweichung)
        z.stufe, z.vermerk = None, "nb"
        z.clean()

    def test_noten_festsetzen_im_portal(self):
        self.anmelden("lehrkraft")                                     # Krause unterrichtet Chemie 9a
        url = reverse("zeugnis_unterricht", args=[self.ch9a.pk])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        s = self.schueler[0]
        drei = self.ch9a.skala.stufen.get(bezeichnung="3")
        r = self.client.post(url, {"aktion": "noten", f"note-{s.pk}": drei.pk, f"begruendung-{s.pk}": "Mündliche Leistungen im Aufwind"})
        self.assertEqual(Zeugnisnote.objects.get(unterricht=self.ch9a, schueler=s).stufe, drei)
        r = self.client.post(url, {"aktion": "noten", f"note-{s.pk}": "nb"})
        self.assertEqual(Zeugnisnote.objects.get(unterricht=self.ch9a, schueler=s).vermerk, "nb")
        # Fremder Kurs: keine Notenvergabe
        self.anmelden("lehrkraft")
        self.assertEqual(self.client.post(reverse("zeugnis_unterricht", args=[self.m9a.pk]), {"aktion": "noten"}).status_code, 403)

    # ------------------------------------------------------------ Kommentar
    def test_kommentar_abzeichnen_und_veralten(self):
        z = self.zeugnis(3)
        self.anmelden("mittelstufe")                                   # Sabine Müller unterrichtet Mathematik 9a
        r = self.client.post(reverse("zeugnis_kommentar", args=[z.pk]), {"aktion": "abzeichnen"})
        self.assertEqual(r.status_code, 302)
        a = Abzeichnung.objects.get(zeugnis=z, lehrkraft__kuerzel="MUE")
        self.assertTrue(a.aktuell)
        self.client.post(reverse("zeugnis_kommentar", args=[z.pk]), {"aktion": "anmerkung", "text": "Bitte Wettbewerb erwähnen."})
        self.assertTrue(Anmerkung.objects.filter(zeugnis=z, text__startswith="Bitte Wettbewerb").exists())
        # Klassenleitung ändert den Text → Abzeichnung veraltet
        self.anmelden("lehrkraft")
        self.client.post(reverse("zeugnis", args=[z.pk]), {"aktion": "kommentar", "kommentar": z.kommentar + " Ergänzung."})
        a.refresh_from_db()
        self.assertFalse(a.aktuell)
        # Gleicher Text erneut gespeichert → keine Änderung
        z.refresh_from_db()
        stand = z.kommentar_geaendert
        self.client.post(reverse("zeugnis", args=[z.pk]), {"aktion": "kommentar", "kommentar": z.kommentar})
        z.refresh_from_db()
        self.assertEqual(z.kommentar_geaendert, stand)

    def test_zugriff_auf_kommentar(self):
        z = self.zeugnis(0)
        self.anmelden("personal")
        self.assertEqual(self.client.get(reverse("zeugnis", args=[z.pk])).status_code, 403)
        self.anmelden("finanzen")
        self.assertEqual(self.client.get(reverse("zeugnis", args=[z.pk])).status_code, 403)
        self.anmelden("mittelstufe")                                   # unterrichtet, aber kein Kommentarrecht als Lehrkraft …
        r = self.client.get(reverse("zeugnis", args=[z.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.context["darf"]["kommentar"])                # … als Stufenkoordination 5–10 jedoch schon
        self.anmelden("oberstufe")                                     # Peter Brandt unterrichtet Religion
        r = self.client.get(reverse("zeugnis", args=[z.pk]))
        if r.status_code == 200:
            self.assertFalse(r.context["darf"]["kommentar"])

    # ------------------------------------------------------------ Freigabe und Druck
    def test_freigabe_und_druck(self):
        letzter = self.zeugnis(len(self.schueler) - 1)                 # Kunst fehlt
        self.anmelden("schulleitung")
        self.client.post(reverse("zeugnis", args=[letzter.pk]), {"aktion": "freigeben"})
        letzter.refresh_from_db()
        self.assertFalse(letzter.freigegeben)
        z = self.zeugnis(0)
        self.client.post(reverse("zeugnis", args=[z.pk]), {"aktion": "freigeben"})
        z.refresh_from_db()
        self.assertTrue(z.freigegeben)
        self.assertTrue(z.fachnoten.exists())
        r = self.client.get(reverse("zeugnis_druck", args=[z.pk]))
        self.assertContains(r, "HALBJAHRESZEUGNIS")
        self.assertNotContains(r, "wasserzeichen")
        self.assertContains(r, "Beiblatt zum Zeugnis")
        # Nach der Freigabe: keine Notenänderung im Kurs
        self.anmelden("lehrkraft")
        s = self.schueler[0]
        alt = Zeugnisnote.objects.get(unterricht=self.ch9a, schueler=s).stufe_id
        self.client.post(reverse("zeugnis_unterricht", args=[self.ch9a.pk]), {"aktion": "noten", f"note-{s.pk}": "nb"})
        self.assertEqual(Zeugnisnote.objects.get(unterricht=self.ch9a, schueler=s).stufe_id, alt)
        self.assertEqual(self.client.post(reverse("zeugnis", args=[z.pk]), {"aktion": "speichern"}).status_code, 403)
        # Klassendruck durch das Sekretariat
        self.anmelden("verwaltung")
        r = self.client.get(reverse("zeugnis_klasse_druck", args=[self.kl9a.pk, self.hj1.pk]))
        self.assertEqual(len(r.context["seiten"]), len(self.schueler))
        self.anmelden("schulleitung")
        self.client.post(reverse("zeugnis", args=[z.pk]), {"aktion": "aufheben"})
        z.refresh_from_db()
        self.assertFalse(z.freigegeben)

    def test_klassenuebersicht_und_uebersicht(self):
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("zeugnis_klasse", args=[self.kl9a.pk, self.hj1.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context["zeilen"]), len(self.schueler))
        r = self.client.get(reverse("zeugnisse"))
        self.assertTrue(r.context["unterrichte"])
        self.assertContains(self.client.get(reverse("start")), 'id="zeugnisse"')

    # ------------------------------------------------------------ Konferenz
    def test_konferenz_halbjahr_und_versetzung(self):
        k = Konferenz.objects.get(klasse=self.kl9a, abschnitt=self.hj1)
        self.anmelden("lehrkraft")                                     # Mitglied, aber nicht Leitung
        self.assertEqual(self.client.get(reverse("konferenz", args=[k.pk])).status_code, 200)
        self.assertEqual(self.client.post(reverse("konferenz", args=[k.pk]), {"aktion": "speichern"}).status_code, 403)
        self.anmelden("mittelstufe")
        r = self.client.get(reverse("konferenz", args=[k.pk]))
        zeilen = r.context["zeilen"]
        gefaehrdet = [zl for zl in zeilen if zl["ergebnis"] and zl["ergebnis"].gefaehrdet]
        self.assertGreaterEqual(len(gefaehrdet), 3)                    # Demo: M 5; CH+PH 5; E 6
        self.assertContains(self.client.get(reverse("konferenz_gefaehrdung", args=[k.pk])), "Gefährdung der Versetzung")
        # Als Versetzungskonferenz abschließen: Nichtversetzung braucht Begründung
        daten = {"aktion": "abschliessen", "art": "versetzung", "datum": "2027-01-22",
                 "teilnehmende": list(k.teilnehmende.values_list("pk", flat=True))}
        for zl in zeilen:
            daten[f"b-{zl['s'].pk}-entscheidung"] = "versetzt"
        umar = next(zl for zl in zeilen if zl["ergebnis"] and zl["ergebnis"].ergebnis == NICHT)
        daten[f"b-{umar['s'].pk}-entscheidung"] = "nicht_versetzt"
        r = self.client.post(reverse("konferenz", args=[k.pk]), daten)
        self.assertTrue(r.context["hindernisse"])
        daten[f"b-{umar['s'].pk}-begruendung"] = "Ungenügend im Kernfach Englisch; kein Ausgleich möglich."
        self.client.post(reverse("konferenz", args=[k.pk]), daten)
        k.refresh_from_db()
        self.assertTrue(k.abgeschlossen)
        self.assertEqual(Zeugnis.objects.get(schueler=umar["s"], abschnitt=self.hj1).versetzung, "nicht_versetzt")
        r = self.client.get(reverse("konferenz_protokoll", args=[k.pk]))
        self.assertContains(r, "Ungenügend im Kernfach Englisch")

    def test_englische_druckfassung(self):
        self.anmelden("verwaltung")
        r = self.client.get(reverse("zeugnis_druck", args=[self.zeugnis(0).pk]) + "?sprache=en")
        self.assertContains(r, "HALF-YEAR REPORT")
        self.assertContains(r, "Translation")
