"""Tests 0.4.16.0: Notenschluss zu einem Datum, Bewertungsstruktur kopieren, Fächer als Kacheln."""
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from portal.klassenunterricht import speichern
from stammdaten.models import Abschnitt, Fach, Gruppe, Personalprofil, Schuljahr

from . import strukturkopie as K
from .models import Bewertungsordner, Leistungsnachweis, Notenschluss, Notensperre, Unterricht
from .sperre import Sperrstand, gesperrte_schueler

PW = "Test-Passwort-123"


class Version0416Test(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))
        cls.sj = Schuljahr.aktuelles()
        cls.hj1 = Abschnitt.objects.get(schuljahr=cls.sj, nummer=1)
        cls.kl8a = Gruppe.objects.get(schuljahr=cls.sj, name="8a")
        cls.kra = Personalprofil.objects.get(kuerzel="KRA")
        cls.ch9a = Unterricht.objects.get(gruppe__name="9a", gruppe__schuljahr=cls.sj, fach__kuerzel="CH", abschnitt=cls.hj1)
        fach = Fach.objects.get(kuerzel="CH")
        Unterricht.objects.filter(gruppe=cls.kl8a, fach=fach, abschnitt=cls.hj1).delete()
        speichern(cls.kl8a, {(fach.pk, cls.hj1.pk): (None, cls.kra.pk)})
        cls.ziel = Unterricht.objects.get(gruppe=cls.kl8a, fach=fach, abschnitt=cls.hj1)

    def anmelden(self, name):
        self.assertTrue(self.client.login(username=name, password=PW))

    # ------------------------------------------------------------ Notenschluss
    def test_notenschluss_sperrt_nach_dem_datum(self):
        Notensperre.objects.filter(abschnitt=self.hj1, klasse=self.kl8a).delete()
        heute = timezone.localdate()
        n = Notenschluss.objects.create(abschnitt=self.hj1, jahrgang_von=8, jahrgang_bis=8, datum=heute)
        self.assertFalse(Sperrstand(self.hj1).klasse_gesperrt(self.kl8a.pk))       # am Tag selbst noch offen
        n.datum = heute - timedelta(days=1)
        n.save()
        self.assertTrue(Sperrstand(self.hj1).klasse_gesperrt(self.kl8a.pk))
        self.assertTrue(gesperrte_schueler(self.ziel))
        Notensperre.objects.create(abschnitt=self.hj1, klasse=self.kl8a, gesperrt=False)  # zur Korrektur freigegeben
        self.assertFalse(Sperrstand(self.hj1).klasse_gesperrt(self.kl8a.pk))

    def test_notenschluss_seite(self):
        self.anmelden("schulleitung")
        r = self.client.post(reverse("notensperre"), {"aktion": "schluss_neu", "abschnitt": self.hj1.pk, "von": 5, "bis": 10,
                                                      "datum": self.hj1.ende.isoformat()}, follow=True)
        self.assertContains(r, "Notenschluss gespeichert")
        n = Notenschluss.objects.get(abschnitt=self.hj1)
        self.client.logout()
        self.anmelden("oberstufe")                      # Jahrgänge 5–10 gehören nicht zur eigenen Stufe
        r = self.client.post(reverse("notensperre"), {"aktion": "schluss_loeschen", "abschnitt": self.hj1.pk, "schluss": n.pk})
        self.assertEqual(r.status_code, 403)

    # ------------------------------------------------------------ Struktur kopieren
    def test_struktur_mit_leistungsnachweisen_kopieren(self):
        quelle_ordner = Bewertungsordner.objects.filter(unterricht=self.ch9a).count()
        n_o, n_ln, ueber = K.kopieren(self.ch9a, self.ziel, mit_nachweisen=True)
        self.assertEqual(ueber, [])
        self.assertEqual(Bewertungsordner.objects.filter(unterricht=self.ziel).count(), quelle_ordner)
        self.assertEqual(n_ln, self.ch9a.leistungsnachweise.count())
        self.assertFalse(self.ziel.leistungsnachweise.filter(noten__stufe__isnull=False).exists())   # keine Noten kopiert
        with self.assertRaises(ValueError):                                                          # jetzt mit Leistungsnachweisen
            K.kopieren(self.ch9a, self.ziel)

    def test_struktur_uebertragen_ueber_die_seite(self):
        self.anmelden("lehrkraft")
        url = reverse("bewertungsstruktur", args=[self.ch9a.pk])
        r = self.client.get(url)
        self.assertIn(self.ziel, r.context["kopierziele"])
        r = self.client.post(url, {"aktion": "uebertragen", "ziel": [self.ziel.pk], "mit_nachweisen": "1"}, follow=True)
        self.assertContains(r, "Struktur übernommen")
        self.assertTrue(Leistungsnachweis.objects.filter(unterricht=self.ziel).exists())

    def test_kacheln_in_noten_nach_klasse(self):
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("noten_klassen") + f"?abschnitt={self.hj1.pk}&klasse={self.ch9a.gruppe_id}")
        self.assertContains(r, 'class="nk-kachel nk-kachel-klasse aktiv"')
        self.assertContains(r, "CH KRA")
