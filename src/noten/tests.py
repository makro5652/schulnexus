from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase

from stammdaten.models import Abschnitt, Fach, Gruppe, Mitgliedschaft, Person, Personalprofil, Schuelerprofil, Schuljahr

from .berechnung import gewichteter_schnitt, vorschlagsnote
from .models import (
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
        cls.schr = Leistungskategorie.objects.create(vorlage=cls.vorlage, name="Schriftlich", anteil=50)
        cls.sonst = Leistungskategorie.objects.create(vorlage=cls.vorlage, name="Sonstige", anteil=50)
        cls.u = Unterricht.objects.create(abschnitt=cls.hj, gruppe=klasse, fach=Fach.objects.create(kuerzel="CH", name="Chemie"),
                                          lehrkraft=lk, skala=cls.skala, gewichtung=cls.vorlage)
        cls.schluessel = Notenschluessel.objects.create(name="Test", skala=cls.skala)
        for b, ab in [("1", 90), ("2", 75), ("3", 60), ("4", 45), ("5", 20), ("6", 0)]:
            Schluesselschwelle.objects.create(schluessel=cls.schluessel, min_prozent=ab, stufe=cls.st[b])


class VorschlagsnoteTest(NotenFixture):
    def ln(self, kat, gewicht="1", **kw):
        return Leistungsnachweis.objects.create(unterricht=self.u, kategorie=kat, titel="x", datum=date(2026, 9, 1), gewicht=Decimal(gewicht), **kw)

    def test_kategorien_und_gewichte(self):
        ka, test = self.ln(self.schr), self.ln(self.schr, "0.5")
        m1, m2 = self.ln(self.sonst), self.ln(self.sonst)
        Note.objects.create(leistungsnachweis=ka, schueler=self.s1, stufe=self.st["2"])
        Note.objects.create(leistungsnachweis=test, schueler=self.s1, stufe=self.st["4"])
        Note.objects.create(leistungsnachweis=m1, schueler=self.s1, stufe=self.st["1"])
        Note.objects.create(leistungsnachweis=m2, schueler=self.s1, stufe=self.st["2"])
        v = vorschlagsnote(self.u, self.s1)
        # schriftlich: (2*1 + 4*0.5)/1.5 = 2,67 ; sonstige: 1,5 ; gesamt: (2,6667+1,5)/2 = 2,08
        self.assertEqual(v.kategorien[0].schnitt, Decimal("2.67"))
        self.assertEqual(v.kategorien[1].schnitt, Decimal("1.50"))
        self.assertEqual(v.schnitt, Decimal("2.08"))
        self.assertEqual(v.stufe.bezeichnung, "2")
        self.assertFalse(v.warnungen)
        self.assertFalse(v.gefaehrdet)

    def test_fehlende_kategorie_gibt_warnung(self):
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
        self.assertTrue(v.gefaehrdet)

    def test_keine_noten(self):
        v = vorschlagsnote(self.u, self.s2)
        self.assertIsNone(v.schnitt)


class NotenschluesselTest(NotenFixture):
    def test_be_werden_umgerechnet(self):
        ln = Leistungsnachweis.objects.create(unterricht=self.u, kategorie=self.schr, titel="KA", datum=date(2026, 9, 1),
                                              schluessel=self.schluessel, max_be=40)
        n = Note.objects.create(leistungsnachweis=ln, schueler=self.s1, erreichte_be=Decimal(30))  # 75 %
        self.assertEqual(n.stufe.bezeichnung, "2")
        n.erreichte_be = Decimal("29.5")  # 73,75 %
        n.save()
        self.assertEqual(n.stufe.bezeichnung, "3")

    def test_zu_viele_be(self):
        ln = Leistungsnachweis.objects.create(unterricht=self.u, kategorie=self.schr, titel="KA", datum=date(2026, 9, 1),
                                              schluessel=self.schluessel, max_be=40)
        with self.assertRaises(ValidationError):
            Note(leistungsnachweis=ln, schueler=self.s1, erreichte_be=Decimal(41)).full_clean()

    def test_kategorie_muss_zur_vorlage_passen(self):
        andere = Leistungskategorie.objects.create(vorlage=Gewichtungsvorlage.objects.create(name="Andere"), name="X", anteil=100)
        with self.assertRaises(ValidationError):
            Leistungsnachweis(unterricht=self.u, kategorie=andere, titel="x", datum=date(2026, 9, 1)).full_clean()


class ZeugnisnoteTest(NotenFixture):
    def test_abweichung_braucht_begruendung(self):
        z = Zeugnisnote(unterricht=self.u, schueler=self.s1, vorschlag=Decimal("2.10"), stufe=self.st["3"])
        with self.assertRaises(ValidationError):
            z.full_clean()
        z.begruendung = "Deutliche Leistungssteigerung im Halbjahr, aber ..."
        z.full_clean()

    def test_passende_note_ohne_begruendung(self):
        Zeugnisnote(unterricht=self.u, schueler=self.s1, vorschlag=Decimal("2.10"), stufe=self.st["2"]).full_clean()
