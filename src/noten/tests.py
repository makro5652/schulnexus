from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from stammdaten.models import Abschnitt, Fach, Gruppe, Mitgliedschaft, Person, Personalprofil, Schuelerprofil, Schuljahr

from .berechnung import gewichteter_schnitt, nominale_anteile, vorschlagsnote
from .models import (
    Bewertungsordner,
    Gewichtungsvorlage,
    Leistungskategorie,
    Leistungsnachweis,
    Note,
    Notenschluessel,
    Notenskala,
    Schluesselschwelle,
    Unterricht,
    Zeugnisnote,
)


class GewichteterSchnittTest(TestCase):
    def test_leer(self):
        self.assertIsNone(gewichteter_schnitt([]))

    def test_gewichtung(self):
        # (2*1 + 4*0.5) / 1.5 = 2,666...
        self.assertAlmostEqual(gewichteter_schnitt([(Decimal(2), Decimal(1)), (Decimal(4), Decimal("0.5"))]), Decimal("2.6667"), places=4)


class NotenFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("grundeinrichtung", verbosity=0, stdout=open("/dev/null", "w"))
        cls.skala = Notenskala.objects.get(name__startswith="Sek I –")
        cls.st = {s.bezeichnung: s for s in cls.skala.stufen.all()}
        sj = Schuljahr.objects.create(name="2026/27", beginn=date(2026, 8, 17), ende=date(2027, 6, 25), aktiv=True)
        cls.hj = Abschnitt.objects.create(schuljahr=sj, name="1. HJ", nummer=1, beginn=date(2026, 8, 17), ende=date(2027, 1, 29))
        lk = Personalprofil.objects.create(person=Person.objects.create(vorname="L", nachname="K"), kuerzel="LK")
        klasse = Gruppe.objects.create(schuljahr=sj, name="9a", jahrgang=9)
        cls.s1 = Schuelerprofil.objects.create(person=Person.objects.create(vorname="A", nachname="A"), schuelernummer="1")
        cls.s2 = Schuelerprofil.objects.create(person=Person.objects.create(vorname="B", nachname="B"), schuelernummer="2")
        for s in (cls.s1, cls.s2):
            Mitgliedschaft.objects.create(gruppe=klasse, schueler=s, von=sj.beginn)
        cls.vorlage = Gewichtungsvorlage.objects.create(name="NaWi")
        Leistungskategorie.objects.create(vorlage=cls.vorlage, name="Schriftlich", anteil=50)
        Leistungskategorie.objects.create(vorlage=cls.vorlage, name="Sonstige", anteil=50)
        cls.u = Unterricht.objects.create(abschnitt=cls.hj, gruppe=klasse, fach=Fach.objects.create(kuerzel="CH", name="Chemie"),
                                          lehrkraft=lk, skala=cls.skala, gewichtung=cls.vorlage)
        # Aus der Startvorlage werden automatisch die obersten Ordner angelegt.
        cls.schr = cls.u.bewertungsordner.get(name="Schriftlich")
        cls.sonst = cls.u.bewertungsordner.get(name="Sonstige")
        cls.schluessel = Notenschluessel.objects.create(name="Test", skala=cls.skala)
        for b, ab in [("1", 90), ("2", 75), ("3", 60), ("4", 45), ("5", 20), ("6", 0)]:
            Schluesselschwelle.objects.create(schluessel=cls.schluessel, min_prozent=ab, stufe=cls.st[b])


class VorschlagsnoteTest(NotenFixture):
    def ln(self, ordner, gewicht="1", **kw):
        return Leistungsnachweis.objects.create(ordner=ordner, titel="x", datum=date(2026, 9, 1), gewicht=Decimal(gewicht), **kw)

    def test_kategorien_und_gewichte(self):
        ka, test = self.ln(self.schr), self.ln(self.schr, "0.5")
        m1, m2 = self.ln(self.sonst), self.ln(self.sonst)
        Note.objects.create(leistungsnachweis=ka, schueler=self.s1, stufe=self.st["2"])
        Note.objects.create(leistungsnachweis=test, schueler=self.s1, stufe=self.st["4"])
        Note.objects.create(leistungsnachweis=m1, schueler=self.s1, stufe=self.st["1"])
        Note.objects.create(leistungsnachweis=m2, schueler=self.s1, stufe=self.st["2"])
        v = vorschlagsnote(self.u, self.s1)
        # schriftlich: (2*1 + 4*0.5)/1.5 = 2,67 ; sonstige: 1,5 ; gesamt: (2,6667+1,5)/2 = 2,08
        self.assertEqual(v.hauptordner[0].schnitt, Decimal("2.67"))
        self.assertEqual(v.hauptordner[1].schnitt, Decimal("1.50"))
        self.assertEqual(v.schnitt, Decimal("2.08"))
        self.assertEqual(v.stufe.bezeichnung, "2")
        self.assertFalse(v.warnungen)
        self.assertFalse(v.gefaehrdet)

    def test_leerer_hauptordner_gibt_warnung(self):
        Note.objects.create(leistungsnachweis=self.ln(self.schr), schueler=self.s1, stufe=self.st["3"])
        v = vorschlagsnote(self.u, self.s1)
        self.assertEqual(v.schnitt, Decimal("3.00"))
        self.assertEqual(len(v.warnungen), 1)

    def test_sonderstatus_zaehlt_nicht(self):
        ln = self.ln(self.schr)
        Note.objects.create(leistungsnachweis=ln, schueler=self.s1, sonderstatus="entschuldigt", stufe=self.st["6"])
        Note.objects.create(leistungsnachweis=self.ln(self.schr), schueler=self.s1, stufe=self.st["2"])
        self.assertEqual(vorschlagsnote(self.u, self.s1).schnitt, Decimal("2.00"))

    def test_gefaehrdung(self):
        Note.objects.create(leistungsnachweis=self.ln(self.schr), schueler=self.s1, stufe=self.st["5"])
        Note.objects.create(leistungsnachweis=self.ln(self.sonst), schueler=self.s1, stufe=self.st["4"])
        v = vorschlagsnote(self.u, self.s1)
        self.assertEqual(v.schnitt, Decimal("4.50"))
        self.assertFalse(v.gefaehrdet)       # ab 0.4.8.0: Gleichstand zugunsten → gerundet 4 (ausreichend)
        Note.objects.create(leistungsnachweis=self.ln(self.sonst), schueler=self.s1, stufe=self.st["6"])
        v = vorschlagsnote(self.u, self.s1)
        self.assertGreater(v.schnitt, Decimal("4.50"))
        self.assertTrue(v.gefaehrdet)

    def test_keine_noten(self):
        v = vorschlagsnote(self.u, self.s2)
        self.assertIsNone(v.schnitt)


class NotenschluesselTest(NotenFixture):
    def test_be_werden_umgerechnet(self):
        ln = Leistungsnachweis.objects.create(ordner=self.schr, titel="KA", datum=date(2026, 9, 1),
                                              schluessel=self.schluessel, max_be=40)
        n = Note.objects.create(leistungsnachweis=ln, schueler=self.s1, erreichte_be=Decimal(30))  # 75 %
        self.assertEqual(n.stufe.bezeichnung, "2")
        n.erreichte_be = Decimal("29.5")  # 73,75 %
        n.save()
        self.assertEqual(n.stufe.bezeichnung, "3")

    def test_zu_viele_be(self):
        ln = Leistungsnachweis.objects.create(ordner=self.schr, titel="KA", datum=date(2026, 9, 1),
                                              schluessel=self.schluessel, max_be=40)
        with self.assertRaises(ValidationError):
            Note(leistungsnachweis=ln, schueler=self.s1, erreichte_be=Decimal(41)).full_clean()

    def test_unterricht_kommt_aus_ordner(self):
        ln = Leistungsnachweis.objects.create(ordner=self.schr, titel="x", datum=date(2026, 9, 1))
        self.assertEqual(ln.unterricht, self.u)


class BewertungsordnerTest(NotenFixture):
    """Frei benennbare, verschachtelte Ordner wie „Sonstige Mitarbeit › Quartal 1“."""

    def ln(self, ordner, gewicht="1"):
        return Leistungsnachweis.objects.create(ordner=ordner, titel="x", datum=date(2026, 9, 1), gewicht=Decimal(gewicht))

    def test_verschachtelte_berechnung(self):
        q1 = Bewertungsordner.objects.create(unterricht=self.u, eltern=self.sonst, name="Quartal 1", gewicht=1)
        q2 = Bewertungsordner.objects.create(unterricht=self.u, eltern=self.sonst, name="Quartal 2", gewicht=1)
        Note.objects.create(leistungsnachweis=self.ln(self.schr), schueler=self.s1, stufe=self.st["3"])
        Note.objects.create(leistungsnachweis=self.ln(q1), schueler=self.s1, stufe=self.st["1"])
        Note.objects.create(leistungsnachweis=self.ln(q1, "0.5"), schueler=self.s1, stufe=self.st["4"])
        Note.objects.create(leistungsnachweis=self.ln(q2), schueler=self.s1, stufe=self.st["2"])
        v = vorschlagsnote(self.u, self.s1)
        werte = {e.pfad: e.schnitt for e in v.alle_ordner}
        # Q1: (1*1 + 4*0,5)/1,5 = 2,00 ; Q2: 2,00 ; Sonstige: 2,00 ; gesamt: (3 + 2)/2 = 2,50
        self.assertEqual(werte["Sonstige › Quartal 1"], Decimal("2.00"))
        self.assertEqual(werte["Sonstige › Quartal 2"], Decimal("2.00"))
        self.assertEqual(werte["Sonstige"], Decimal("2.00"))
        self.assertEqual(v.schnitt, Decimal("2.50"))

    def test_leerer_unterordner_wird_uebersprungen(self):
        q1 = Bewertungsordner.objects.create(unterricht=self.u, eltern=self.sonst, name="Quartal 1", gewicht=1)
        Bewertungsordner.objects.create(unterricht=self.u, eltern=self.sonst, name="Quartal 2", gewicht=1)
        Note.objects.create(leistungsnachweis=self.ln(self.schr), schueler=self.s1, stufe=self.st["2"])
        Note.objects.create(leistungsnachweis=self.ln(q1), schueler=self.s1, stufe=self.st["4"])
        v = vorschlagsnote(self.u, self.s1)
        self.assertEqual(v.schnitt, Decimal("3.00"))
        self.assertFalse(v.warnungen)

    def test_ordner_und_nachweise_auf_einer_ebene(self):
        # Ein Ordner darf direkt Leistungsnachweise UND Unterordner enthalten.
        unter = Bewertungsordner.objects.create(unterricht=self.u, eltern=self.sonst, name="Referate", gewicht=2)
        Note.objects.create(leistungsnachweis=self.ln(self.sonst, "1"), schueler=self.s1, stufe=self.st["1"])
        Note.objects.create(leistungsnachweis=self.ln(unter), schueler=self.s1, stufe=self.st["4"])
        werte = {e.pfad: e.schnitt for e in vorschlagsnote(self.u, self.s1).alle_ordner}
        self.assertEqual(werte["Sonstige"], Decimal("3.00"))  # (1*1 + 4*2) / 3

    def test_nominale_anteile(self):
        q1 = Bewertungsordner.objects.create(unterricht=self.u, eltern=self.sonst, name="Quartal 1", gewicht=1)
        Bewertungsordner.objects.create(unterricht=self.u, eltern=self.sonst, name="Quartal 2", gewicht=1)
        ka, test, m = self.ln(self.schr, "2"), self.ln(self.schr, "1"), self.ln(q1)
        anteil_o, anteil_ln = nominale_anteile(Bewertungsordner.objects.filter(unterricht=self.u), Leistungsnachweis.objects.all())
        self.assertAlmostEqual(float(anteil_o[self.sonst.pk]), 50.0)
        self.assertAlmostEqual(float(anteil_o[q1.pk]), 25.0)
        self.assertAlmostEqual(float(anteil_ln[ka.pk]), 100 / 3, places=4)
        self.assertAlmostEqual(float(anteil_ln[test.pk]), 50 / 3, places=4)
        self.assertAlmostEqual(float(anteil_ln[m.pk]), 25.0)

    def test_keine_zyklen(self):
        a = Bewertungsordner.objects.create(unterricht=self.u, eltern=self.sonst, name="A")
        b = Bewertungsordner.objects.create(unterricht=self.u, eltern=a, name="B")
        a.eltern = b
        with self.assertRaises(ValidationError):
            a.full_clean()

    def test_elternordner_aus_anderem_unterricht_verboten(self):
        anderer = Unterricht.objects.create(abschnitt=self.hj, gruppe=self.u.gruppe, fach=Fach.objects.create(kuerzel="BIO", name="Bio"),
                                            lehrkraft=self.u.lehrkraft, skala=self.skala)
        with self.assertRaises(ValidationError):
            Bewertungsordner(unterricht=anderer, eltern=self.sonst, name="X").full_clean()

    def test_ohne_startvorlage_keine_ordner(self):
        u = Unterricht.objects.create(abschnitt=self.hj, gruppe=self.u.gruppe, fach=Fach.objects.create(kuerzel="PH", name="Physik"),
                                      lehrkraft=self.u.lehrkraft, skala=self.skala)
        self.assertFalse(u.bewertungsordner.exists())
        self.assertEqual(vorschlagsnote(u, self.s1).schnitt, None)


class ZeugnisnoteTest(NotenFixture):
    def test_abweichung_braucht_begruendung(self):
        z = Zeugnisnote(unterricht=self.u, schueler=self.s1, vorschlag=Decimal("2.10"), stufe=self.st["3"])
        with self.assertRaises(ValidationError):
            z.full_clean()
        z.begruendung = "Deutliche Leistungssteigerung im Halbjahr, aber ..."
        z.full_clean()

    def test_passende_note_ohne_begruendung(self):
        Zeugnisnote(unterricht=self.u, schueler=self.s1, vorschlag=Decimal("2.10"), stufe=self.st["2"]).full_clean()


class EinzelgewichtTest(NotenFixture):
    """Gewichtung pro einzelner Note (z. B. Nachschreibarbeit)."""

    def test_individuelles_gewicht_wirkt(self):
        a = Leistungsnachweis.objects.create(ordner=self.schr, titel="KA 1", datum=date(2026, 9, 1), gewicht=1)
        b = Leistungsnachweis.objects.create(ordner=self.schr, titel="KA 2", datum=date(2026, 10, 1), gewicht=1)
        Note.objects.create(leistungsnachweis=a, schueler=self.s1, stufe=self.st["1"])
        Note.objects.create(leistungsnachweis=b, schueler=self.s1, stufe=self.st["4"],
                            gewicht_individuell=Decimal("0.5"), gewicht_begruendung="Verkürzte Nachschreibarbeit")
        # (1*1 + 4*0,5) / 1,5 = 2,00 statt 2,50
        self.assertEqual(vorschlagsnote(self.u, self.s1).schnitt, Decimal("2.00"))
        # Andere Schüler:innen sind nicht betroffen
        Note.objects.create(leistungsnachweis=a, schueler=self.s2, stufe=self.st["1"])
        Note.objects.create(leistungsnachweis=b, schueler=self.s2, stufe=self.st["4"])
        self.assertEqual(vorschlagsnote(self.u, self.s2).schnitt, Decimal("2.50"))

    def test_abweichung_braucht_begruendung(self):
        a = Leistungsnachweis.objects.create(ordner=self.schr, titel="KA", datum=date(2026, 9, 1), gewicht=1)
        n = Note(leistungsnachweis=a, schueler=self.s1, stufe=self.st["2"], gewicht_individuell=Decimal(2))
        with self.assertRaises(ValidationError):
            n.full_clean()
        n.gewicht_begruendung = "Ersatzleistung für zwei Tests"
        n.full_clean()
