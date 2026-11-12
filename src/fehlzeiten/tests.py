"""Tests 0.7.1: Fehlzeiten nach Klasse – Klassenwahl, alphabetische Eingabe, offene Entschuldigungen, Übersicht."""
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from stammdaten.models import Gruppe, Schuljahr

from .models import Fehlzeit

PW = "Test-Passwort-123"


class FehlzeitenSeiteTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))
        cls.sj = Schuljahr.aktuelles()
        cls.klasse = Gruppe.objects.get(schuljahr=cls.sj, typ=Gruppe.STAMMKLASSE, name="9a")
        cls.tag = cls.sj.stichtag()

    def anmelden(self, name):
        self.client.logout()
        self.assertTrue(self.client.login(username=name, password=PW))

    def url(self, **kw):
        teile = "&".join(f"{k}={v}" for k, v in kw.items())
        return reverse("fehlzeiten") + (f"?{teile}" if teile else "")

    def test_klassenwahl_sortiert_und_nach_rolle(self):
        self.anmelden("verwaltung")
        r = self.client.get(self.url())
        alle = list(Gruppe.objects.filter(schuljahr=self.sj, typ=Gruppe.STAMMKLASSE).order_by("jahrgang", "name"))
        self.assertEqual(r.context["klassen"], alle)
        self.assertContains(r, 'class="fz-kachel"', count=len(alle))
        self.anmelden("lehrkraft")                      # Klassenleitung 9a, unterrichtet Chemie in 9a und 9b
        namen = [k.name for k in self.client.get(self.url()).context["klassen"]]
        self.assertIn("9a", namen)
        self.assertNotIn("8a", namen)

    def test_fremde_klasse_verboten(self):
        self.anmelden("lehrkraft")
        fremd = Gruppe.objects.get(schuljahr=self.sj, typ=Gruppe.STAMMKLASSE, name="8a")
        self.assertEqual(self.client.get(self.url(gruppe=fremd.pk)).status_code, 403)

    def test_klasse_alphabetisch(self):
        self.anmelden("lehrkraft")
        r = self.client.get(self.url(gruppe=self.klasse.pk, datum=self.tag.isoformat()))
        namen = [(z["s"].person.nachname.lower(), (z["s"].person.rufname or z["s"].person.vorname).lower()) for z in r.context["zeilen"]]
        self.assertTrue(namen)
        self.assertEqual(namen, sorted(namen))
        self.assertContains(r, 'name="art_')
        self.assertContains(r, "fehlzeiten.js")

    def test_eintragen_aller_arten(self):
        self.anmelden("lehrkraft")
        s1, s2, s3 = [z["s"] for z in self.client.get(self.url(gruppe=self.klasse.pk, datum=self.tag.isoformat())).context["zeilen"][:3]]
        vorher = Fehlzeit.objects.count()
        r = self.client.post(reverse("fehlzeiten"), {
            "aktion": "erfassen", "gruppe": self.klasse.pk, "datum": self.tag.isoformat(), "quelle": "eltern",
            f"art_{s1.pk}": "ganztaegig", f"bis_{s1.pk}": (self.tag + timedelta(days=1)).isoformat(), f"grund_{s1.pk}": "krank",
            f"art_{s2.pk}": "stunden", f"von_{s2.pk}": "3", f"bisstd_{s2.pk}": "",
            f"art_{s3.pk}": "verspaetung", f"min_{s3.pk}": "15", f"status_{s3.pk}": "unentschuldigt",
        })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Fehlzeit.objects.count(), vorher + 3)
        f1 = Fehlzeit.objects.get(schueler=s1, datum_von=self.tag, art="ganztaegig")
        self.assertEqual((f1.datum_bis, f1.grund, f1.quelle, f1.status), (self.tag + timedelta(days=1), "krank", "eltern", "offen"))
        self.assertEqual(f1.erfasst_von.username, "lehrkraft")
        f2 = Fehlzeit.objects.get(schueler=s2, datum_von=self.tag, art="stunden")
        self.assertEqual((f2.stunde_von, f2.stunde_bis), (3, 3))
        f3 = Fehlzeit.objects.get(schueler=s3, datum_von=self.tag, art="verspaetung")
        self.assertEqual((f3.minuten, f3.status), (15, "unentschuldigt"))
        r = self.client.get(self.url(gruppe=self.klasse.pk, datum=self.tag.isoformat()))
        zeile = next(z for z in r.context["zeilen"] if z["s"].pk == s1.pk)
        self.assertIn(f1, zeile["heute"])

    def test_ungueltige_zeile_speichert_nichts(self):
        self.anmelden("lehrkraft")
        s1, s2 = [z["s"] for z in self.client.get(self.url(gruppe=self.klasse.pk, datum=self.tag.isoformat())).context["zeilen"][:2]]
        vorher = Fehlzeit.objects.count()
        r = self.client.post(reverse("fehlzeiten"), {
            "aktion": "erfassen", "gruppe": self.klasse.pk, "datum": self.tag.isoformat(),
            f"art_{s1.pk}": "ganztaegig", f"art_{s2.pk}": "stunden"}, follow=True)
        self.assertEqual(Fehlzeit.objects.count(), vorher)
        self.assertContains(r, "Es wurde nichts gespeichert")

    def test_nur_mitglieder_der_klasse(self):
        self.anmelden("verwaltung")
        fremd = Gruppe.objects.get(schuljahr=self.sj, typ=Gruppe.STAMMKLASSE, name="8a").aktuelle_mitglieder().first()
        vorher = Fehlzeit.objects.count()
        self.client.post(reverse("fehlzeiten"), {"aktion": "erfassen", "gruppe": self.klasse.pk, "datum": self.tag.isoformat(),
                                                 f"art_{fremd.pk}": "ganztaegig"})
        self.assertEqual(Fehlzeit.objects.count(), vorher)

    def test_offene_entschuldigungen_abarbeiten(self):
        self.anmelden("verwaltung")
        ids = set(self.klasse.aktuelle_mitglieder().values_list("pk", flat=True))
        offen = list(Fehlzeit.objects.filter(status="offen", schueler_id__in=ids)[:2])
        self.assertTrue(offen)
        r = self.client.get(self.url(offen=1))
        self.assertContains(r, f'value="{offen[0].pk}"')
        r = self.client.get(self.url(gruppe=self.klasse.pk))
        self.assertTrue(all(f in r.context["offene"] for f in offen))
        self.client.post(reverse("fehlzeiten"), {"aktion": "entschuldigt", "gruppe": self.klasse.pk, "fehlzeit": [f.pk for f in offen]})
        for f in offen:
            f.refresh_from_db()
            self.assertEqual(f.status, "entschuldigt")

    def test_uebersicht_zaehlt(self):
        self.anmelden("verwaltung")
        s = self.klasse.aktuelle_mitglieder().first()
        Fehlzeit.objects.filter(schueler=s).delete()
        Fehlzeit.objects.create(schueler=s, art="stunden", datum_von=self.tag, stunde_von=1, stunde_bis=2, status="unentschuldigt")
        Fehlzeit.objects.create(schueler=s, art="verspaetung", datum_von=self.tag, minuten=10)
        r = self.client.get(self.url(gruppe=self.klasse.pk, datum=self.tag.isoformat()))
        summe = next(z for z in r.context["zeilen"] if z["s"].pk == s.pk)["summe"]
        self.assertEqual((summe["stunden"], summe["unentsch"], summe["verspaetung"], summe["minuten"], summe["offen"]), (2, 2, 1, 10, 1))

    def test_menueband_und_klassenliste_fuehren_hierher(self):
        self.anmelden("lehrkraft")
        self.assertContains(self.client.get(reverse("start")), f'href="{reverse("fehlzeiten")}"')
        r = self.client.get(reverse("klassenliste", args=[self.klasse.pk]))
        self.assertContains(r, f'{reverse("fehlzeiten")}?gruppe={self.klasse.pk}')

    def test_ohne_recht_kein_zugang(self):
        self.anmelden("personal")               # HR-Management: keine Fehlzeiten
        self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_heute_als_standard(self):
        self.anmelden("verwaltung")
        self.assertEqual(self.client.get(self.url()).context["datum"], timezone.localdate())
