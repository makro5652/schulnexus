"""Ab 0.4.8.1: Zeugnisnote ohne Einzelnoten (Freigabe der Schulleitung), Abweichungen nur markieren, Zeugnis zeigt die Zeugnisnote."""
import io

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from portal.rechte import personal_von
from stammdaten.models import Fach
from zeugnisse.noten import fachnoten

from .berechnung import vorschlagsnote
from .models import Unterricht, Zeugnisnote, Zeugnisnotenfreigabe

PW = "Test-Passwort-123"


class ZeugnisnoteTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))
        cls.ch = Unterricht.objects.select_related("skala", "abschnitt").get(fach__kuerzel="CH", gruppe__name="9a", abschnitt__nummer=1)
        cls.schueler = list(cls.ch.schueler())
        # Musik 9a ohne Einzelnoten – für den Test unterrichtet Krause (Demo-Konto lehrkraft)
        cls.mu = Unterricht.objects.select_related("skala").get(fach__kuerzel="MU", gruppe__name="9a", abschnitt__nummer=1)
        from django.contrib.auth.models import User

        cls.mu.lehrkraft = personal_von(User.objects.get(username="lehrkraft"))
        cls.mu.save()

    def setUp(self):
        self.assertTrue(self.client.login(username="lehrkraft", password=PW))

    def stufe(self, u, b):
        return u.skala.stufen.get(bezeichnung=b)

    def test_abweichung_speichern_ohne_begruendung_und_markieren(self):
        s = self.schueler[0]
        v = vorschlagsnote(self.ch, s)
        ganz = int(self.ch.skala.ganz_runden(v.schnitt))
        anders = self.stufe(self.ch, str(ganz + 1 if ganz < 6 else ganz - 1))
        url = reverse("zeugnis_unterricht", args=[self.ch.pk])
        self.client.post(url, {"aktion": "noten", f"note-{s.pk}": anders.pk})
        zn = Zeugnisnote.objects.get(unterricht=self.ch, schueler=s)
        self.assertEqual(zn.stufe, anders)
        self.assertEqual(zn.begruendung, "")
        self.assertTrue(zn.abweichung)
        r = self.client.get(url)
        self.assertContains(r, "zg-abweichung")
        self.assertContains(r, "weicht vom rechnerischen Vorschlag ab")
        r = self.client.get(reverse("notenuebersicht", args=[self.ch.pk]))
        self.assertContains(r, "zn-abweichung")
        # Auf dem Zeugnis steht die festgesetzte Zeugnisnote, nicht der Vorschlag
        zeile = next(e for e in fachnoten(s, self.ch.abschnitt, "halbjahr") if e["fach"].kuerzel == "CH")
        self.assertEqual(zeile["note"], int(anders.wert))

    def test_ohne_einzelnoten_nur_mit_freigabe(self):
        Zeugnisnotenfreigabe.objects.all().delete()
        s = self.schueler[1]
        Zeugnisnote.objects.filter(unterricht=self.mu, schueler=s).delete()      # Demo-Daten enthalten schon Zeugnisnoten
        url = reverse("zeugnis_unterricht", args=[self.mu.pk])
        self.assertIsNone(vorschlagsnote(self.mu, s).schnitt)
        r = self.client.post(url, {"aktion": "noten", f"note-{s.pk}": self.stufe(self.mu, "2").pk})
        self.assertContains(r, "nicht freigegeben")
        self.assertFalse(Zeugnisnote.objects.filter(unterricht=self.mu, schueler=s).exists())
        self.client.post(url, {"aktion": "noten", f"note-{s.pk}": "befreit"})       # Vermerk geht immer
        self.assertEqual(Zeugnisnote.objects.get(unterricht=self.mu, schueler=s).vermerk, "befreit")
        f = Zeugnisnotenfreigabe.objects.create(jahrgang_von=9, jahrgang_bis=9)
        f.faecher.set([Fach.objects.get(kuerzel="MU")])
        r = self.client.get(reverse("notenuebersicht", args=[self.mu.pk]))
        self.assertContains(r, "auch ohne Einzelnoten")
        self.client.post(url, {"aktion": "noten", f"note-{s.pk}": self.stufe(self.mu, "2").pk})
        zn = Zeugnisnote.objects.get(unterricht=self.mu, schueler=s)
        self.assertEqual(zn.stufe.bezeichnung, "2")
        self.assertFalse(zn.abweichung)                                          # ohne Vorschlag keine Abweichung
        zeile = next(e for e in fachnoten(s, self.mu.abschnitt, "halbjahr") if e["fach"].kuerzel == "MU")
        self.assertEqual(zeile["note"], 2)

    def test_demo_freigabe_und_alle_faecher(self):
        self.assertIsNotNone(Zeugnisnotenfreigabe.fuer(self.mu))               # Demo: Musik, Kunst, Sport Jg. 5–10
        self.assertIsNone(Zeugnisnotenfreigabe.fuer(self.ch))
        Zeugnisnotenfreigabe.objects.create(jahrgang_von=5, jahrgang_bis=12)     # keine Fächer = alle
        self.assertIsNotNone(Zeugnisnotenfreigabe.fuer(self.ch))

    def test_schulleitung_verwaltet_freigaben(self):
        r = self.client.get(reverse("klausurregeln"))
        self.assertEqual(r.status_code, 403)
        self.client.logout()
        self.assertTrue(self.client.login(username="schulleitung", password=PW))
        r = self.client.post(reverse("klausurregeln"), {"aktion": "freigabe", "fg-jahrgang_von": 11, "fg-jahrgang_bis": 12,
                                                        "fg-faecher": [Fach.objects.get(kuerzel="SPO").pk], "fg-bemerkung": "Sport Sek II"})
        self.assertRedirects(r, reverse("klausurregeln"))
        f = Zeugnisnotenfreigabe.objects.get(bemerkung="Sport Sek II")
        self.assertContains(self.client.get(reverse("klausurregeln")), "Sport Sek II")
        self.client.post(reverse("zeugnisfreigabe_loeschen", args=[f.pk]))
        self.assertFalse(Zeugnisnotenfreigabe.objects.filter(pk=f.pk).exists())

    def test_export_markiert_abweichung(self):
        from openpyxl import load_workbook

        s = self.schueler[0]
        v = vorschlagsnote(self.ch, s)
        ganz = int(self.ch.skala.ganz_runden(v.schnitt))
        anders = self.stufe(self.ch, str(ganz + 1 if ganz < 6 else ganz - 1))
        Zeugnisnote.objects.update_or_create(unterricht=self.ch, schueler=s, defaults={"stufe": anders, "vorschlag": v.schnitt})
        r = self.client.get(reverse("noten_excel", args=[self.ch.pk]))
        werte = [c for zeile in load_workbook(io.BytesIO(r.content)).worksheets[0].iter_rows(values_only=True) for c in zeile if c]
        self.assertTrue(any(isinstance(w, str) and "≠" in w for w in werte))
        self.assertEqual(self.client.get(reverse("notenbogen", args=[self.ch.pk])).content[:4], b"%PDF")
