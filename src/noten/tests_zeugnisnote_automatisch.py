"""Tests: Zeugnisnote automatisch aus den Einzelnoten, solange niemand sie festsetzt (ab 0.4.15.0)."""
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from portal.klassenunterricht import speichern as unterricht_speichern
from stammdaten.models import Abschnitt, Fach, Gruppe, Personalprofil, Schuljahr

from .models import Bewertungsordner, Leistungsnachweis, Note, Notenstufe, Unterricht, Zeugnisnote

PW = "Test-Passwort-123"


class ZeugnisnoteAutomatischTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))
        sj = Schuljahr.aktuelles()
        cls.hj1 = Abschnitt.objects.get(schuljahr=sj, nummer=1)
        kl8a = Gruppe.objects.get(schuljahr=sj, name="8a")
        fach = Fach.objects.exclude(unterrichte__gruppe=kl8a).first()
        lk = Personalprofil.objects.filter(aktiv=True, bereich__unterrichtet=True).first()
        unterricht_speichern(kl8a, {(fach.pk, cls.hj1.pk): (None, lk.pk)})
        cls.u = Unterricht.objects.get(gruppe=kl8a, fach=fach, abschnitt=cls.hj1)
        cls.ordner = Bewertungsordner.objects.filter(unterricht=cls.u).first() or Bewertungsordner.objects.create(
            unterricht=cls.u, name="Mitarbeit")
        cls.s = cls.u.schueler().first()
        cls.stufe = {st.bezeichnung: st for st in Notenstufe.objects.filter(skala=cls.u.skala)}

    def nachweis(self, titel, tage=1):
        return Leistungsnachweis.objects.create(ordner=self.ordner, titel=titel, datum=self.hj1.beginn + timedelta(days=tage))

    def note(self, ln, bezeichnung):
        with self.captureOnCommitCallbacks(execute=True):
            return Note.objects.update_or_create(leistungsnachweis=ln, schueler=self.s,
                                                 defaults={"stufe": self.stufe[bezeichnung]})[0]

    def zn(self):
        return Zeugnisnote.objects.filter(unterricht=self.u, schueler=self.s).select_related("stufe").first()

    def test_einzelnoten_ergeben_zeugnisnote(self):
        self.assertIsNone(self.zn())
        self.note(self.nachweis("Test 1"), "2")
        z = self.zn()
        self.assertEqual((z.stufe.bezeichnung, z.quelle), ("2", "auto"))
        self.note(self.nachweis("Test 2", 2), "4")          # Schnitt 3,0
        self.assertEqual(self.zn().stufe.bezeichnung, "3")

    def test_festgesetzte_note_bleibt(self):
        ln = self.nachweis("Test 1")
        self.note(ln, "2")
        z = self.zn()
        z.stufe, z.quelle = self.stufe["1"], ""               # von der Lehrkraft festgesetzt
        with self.captureOnCommitCallbacks(execute=True):
            z.save()
        self.note(ln, "5")
        self.assertEqual((self.zn().stufe.bezeichnung, self.zn().quelle), ("1", ""))

    def test_ohne_einzelnoten_keine_zeugnisnote(self):
        n = self.note(self.nachweis("Test 1"), "2")
        with self.captureOnCommitCallbacks(execute=True):
            n.delete()
        self.assertIsNone(self.zn())

    def test_entfernte_festsetzung_wird_wieder_automatisch(self):
        self.note(self.nachweis("Test 1"), "3")
        z = self.zn()
        z.stufe, z.quelle = self.stufe["1"], "klasse"
        z.save()
        with self.captureOnCommitCallbacks(execute=True):
            z.delete()
        self.assertEqual((self.zn().stufe.bezeichnung, self.zn().quelle), ("3", "auto"))

    def test_befehl_zieht_bestehende_noten_nach(self):
        ln = self.nachweis("Test 1")
        Note.objects.create(leistungsnachweis=ln, schueler=self.s, stufe=self.stufe["4"])   # ohne Commit-Rückruf
        self.assertIsNone(self.zn())
        call_command("zeugnisnoten_automatisch", stdout=StringIO())
        self.assertEqual(self.zn().stufe.bezeichnung, "4")
