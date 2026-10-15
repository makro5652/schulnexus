"""Tests ab 0.4.8.0: Rundung, unentschuldigt, Datum, Jahresnote, Klausurregeln, Notensperre, Excel/PDF."""
import io
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from sicherung.models import Protokoll
from stammdaten.models import Abschnitt, Fach, Gruppe
from zeugnisse.models import Konferenz

from .berechnung import vorschlagsnote
from .models import (
    KAUFMAENNISCH, PROZENT, Bewertungsordner, Klausurregel, Leistungsnachweis, Note, Notensperre, Notenskala, Unterricht, Zeugnisnote,
)
from .sperre import gesperrte_schueler

PW = "Test-Passwort-123"


def sek1():
    return Notenskala.objects.get(name__startswith="Sek I –")


def sek2():
    return Notenskala.objects.get(name__startswith="Sek II –")


class RundungTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("grundeinrichtung", stdout=io.StringIO())

    def test_zugunsten_ueberall_gleich(self):
        s = sek1()
        self.assertEqual(s.rundung, "zugunsten")
        for wert, tendenz, ganz in (("2.50", "2-", 2), ("3.50", "3-", 3), ("4.50", "4-", 4), ("4.51", "5+", 5), ("1.85", "2+", 2)):
            self.assertEqual(s.naechste_stufe(Decimal(wert)).bezeichnung, tendenz, wert)
            self.assertEqual(s.ganz_runden(Decimal(wert)), ganz, wert)
        self.assertFalse(s.ist_gefaehrdet(Decimal("4.50")))     # gerundet 4 = ausreichend
        self.assertTrue(s.ist_gefaehrdet(Decimal("4.51")))
        p = sek2()
        self.assertEqual(p.ganz_runden(Decimal("4.50")), 5)     # Punkte: höher ist besser
        self.assertFalse(p.ist_gefaehrdet(Decimal("4.50")))
        self.assertTrue(p.ist_gefaehrdet(Decimal("4.49")))
        self.assertEqual(p.naechste_stufe(Decimal("10.50")).bezeichnung, "11")

    def test_kaufmaennisch_einstellbar(self):
        s = sek1()
        s.rundung = KAUFMAENNISCH
        s.save()
        self.assertEqual(s.ganz_runden(Decimal("2.50")), 3)
        self.assertEqual(s.naechste_stufe(Decimal("2.50")).bezeichnung, "3+")
        self.assertTrue(s.ist_gefaehrdet(Decimal("4.50")))

    def test_unentschuldigt_ohne_note_als_6_bzw_0(self):
        self.assertEqual(sek1().unentschuldigt_stufe.bezeichnung, "6")
        self.assertEqual(sek2().unentschuldigt_stufe.bezeichnung, "0")


class Grundlage(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))
        cls.u = Unterricht.objects.select_related("abschnitt", "skala", "gruppe").get(fach__kuerzel="CH", gruppe__name="9a",
                                                                                         abschnitt__nummer=1)
        cls.u2 = Unterricht.objects.get(fach__kuerzel="CH", gruppe__name="9a", abschnitt__nummer=2)
        cls.schueler = list(cls.u.schueler())

    def anmelden(self, name):
        self.client.logout()
        self.assertTrue(self.client.login(username=name, password=PW))

    def ordner(self, u, name):
        return Bewertungsordner.objects.get(unterricht=u, name=name)


class BerechnungTest(Grundlage):
    def test_unentschuldigt_zaehlt_mit_6(self):
        u = self.u
        s = self.schueler[0]
        o = self.ordner(u, "Sonstige Mitarbeit")
        ln = Leistungsnachweis.objects.create(ordner=o, titel="Test u", datum=u.abschnitt.beginn + timedelta(days=30), gewicht=Decimal(1000))
        Note.objects.create(leistungsnachweis=ln, schueler=s, sonderstatus="unentschuldigt")
        v = vorschlagsnote(u, s)
        mitarbeit = next(e for e in v.alle_ordner if e.name == "Sonstige Mitarbeit")
        self.assertGreater(mitarbeit.schnitt, Decimal("5.9"))      # nahezu nur die 6 (Gewicht 1000)
        self.anmelden("lehrkraft")
        self.assertContains(self.client.get(reverse("notenuebersicht", args=[u.pk])), "(6)")

    def test_datum_muss_im_halbjahr_liegen(self):
        o = self.ordner(self.u, "Sonstige Mitarbeit")
        ln = Leistungsnachweis(ordner=o, titel="Zu spät", datum=self.u.abschnitt.ende + timedelta(days=3))
        with self.assertRaises(ValidationError):
            ln.full_clean()
        self.anmelden("lehrkraft")
        r = self.client.post(reverse("noten_eintragen", args=[self.u.pk]), {
            "ordner": o.pk, "titel": "Zu spät", "datum": (self.u.abschnitt.ende + timedelta(days=3)).isoformat(), "gewicht": "1"})
        self.assertContains(r, "Das Datum muss im Halbjahr liegen")
        self.assertFalse(Leistungsnachweis.objects.filter(titel="Zu spät").exists())

    def test_vorlaeufig_bei_prozentordner_unter_100(self):
        o = self.ordner(self.u, "Sonstige Mitarbeit")
        o.gewichtsart = PROZENT
        o.save()
        Bewertungsordner.objects.filter(eltern=o).update(gewicht=Decimal(30))
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("notenuebersicht", args=[self.u.pk]))
        self.assertContains(r, "ist erst zu 60 % belegt")

    def test_zeugnisvorschlag_rundet_zugunsten(self):
        z = Zeugnisnote(unterricht=self.u, schueler=self.schueler[0], vorschlag=Decimal("2.50"),
                        stufe=self.u.skala.stufen.get(bezeichnung="2"))
        z.clean()                                                     # 2 entspricht dem Vorschlag – keine Begründung nötig
        z.stufe = self.u.skala.stufen.get(bezeichnung="3")
        with self.assertRaises(ValidationError):
            z.clean()                                                 # 3 weicht ab


class JahresnoteTest(Grundlage):
    def test_voreinstellung_und_verrechnung(self):
        u2 = self.u2
        self.assertEqual(u2.anteil_vorhalbjahr, Decimal(40))
        s = self.schueler[1]
        hj1 = vorschlagsnote(self.u, s, jahr=False).schnitt
        self.assertIsNotNone(hj1)
        v = vorschlagsnote(u2, s)
        self.assertEqual(v.schnitt, hj1)                              # noch keine Note im 2. Halbjahr
        self.assertTrue(any("1. Halbjahr" in w for w in v.warnungen))
        o = Bewertungsordner.objects.get(unterricht=u2, vorgegeben=Bewertungsordner.MITARBEIT)
        ln = Leistungsnachweis.objects.create(ordner=o, titel="Mitarbeit Februar", datum=u2.abschnitt.beginn + timedelta(days=5))
        Note.objects.create(leistungsnachweis=ln, schueler=s, stufe=u2.skala.stufen.get(bezeichnung="1"))
        v = vorschlagsnote(u2, s)
        self.assertEqual(v.halbjahr_schnitt, Decimal("1.00"))
        self.assertEqual(v.schnitt, u2.skala.runden(Decimal("0.4") * hj1 + Decimal("0.6") * 1))
        # Lehrkraft ändert den Anteil
        self.anmelden("lehrkraft")
        r = self.client.post(reverse("bewertungsstruktur", args=[u2.pk]), {"aktion": "speichern", "anteil_vorhalbjahr": "0",
                                                                          "vorhalbjahr_basis": "schnitt"})
        self.assertRedirects(r, reverse("bewertungsstruktur", args=[u2.pk]))
        u2.refresh_from_db()
        self.assertEqual(vorschlagsnote(u2, s).schnitt, Decimal("1.00"))
        r = self.client.get(reverse("notenuebersicht", args=[self.u2.pk]))
        self.assertNotContains(r, "Jahresvorschlag")

    def test_grundlage_zeugnisnote(self):
        u2 = self.u2
        s = self.schueler[1]
        Zeugnisnote.objects.update_or_create(unterricht=self.u, schueler=s, defaults={"stufe": self.u.skala.stufen.get(bezeichnung="5")})
        u2.vorhalbjahr_basis = Unterricht.ZEUGNISNOTE
        u2.save()
        self.assertEqual(vorschlagsnote(u2, s).vorhalbjahr, Decimal("5.00"))

    def test_nur_jahrgang_5_bis_10(self):
        hj2 = Abschnitt.objects.get(schuljahr=self.u.abschnitt.schuljahr, nummer=2)
        g = Gruppe.objects.create(name="11Test", schuljahr=self.u.abschnitt.schuljahr, typ=Gruppe.STAMMKLASSE, jahrgang=11)
        u = Unterricht.objects.create(abschnitt=hj2, gruppe=g, fach=Fach.objects.get(kuerzel="CH"), lehrkraft=self.u.lehrkraft, skala=sek2())
        self.assertIsNone(u.anteil_vorhalbjahr)
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("notenuebersicht", args=[self.u2.pk]))
        self.assertContains(r, "Jahresvorschlag")
        self.assertContains(r, "1. Halbjahr (40 %)")


class KlausurregelTest(Grundlage):
    def test_demo_regel_angewendet(self):
        regel = Klausurregel.objects.get()
        self.assertEqual(Klausurregel.fuer(self.u), regel)
        oben = {o.vorgegeben: o for o in Bewertungsordner.objects.filter(unterricht=self.u, eltern=None)}
        self.assertEqual(set(oben), {Bewertungsordner.KLAUSUR, Bewertungsordner.MITARBEIT})
        self.assertEqual(oben[Bewertungsordner.KLAUSUR].gewicht, Decimal(50))
        self.u.refresh_from_db()
        self.assertEqual(self.u.gewichtsart, PROZENT)

    def test_lehrkraft_kann_vorgabe_nicht_aendern(self):
        k = Bewertungsordner.objects.get(unterricht=self.u, vorgegeben=Bewertungsordner.KLAUSUR)
        self.anmelden("lehrkraft")
        self.client.post(reverse("bewertungsstruktur", args=[self.u.pk]), {
            "aktion": "speichern", f"name_{k.pk}": "Umbenannt", f"gewicht_{k.pk}": "80", "art_wurzel": "relativ"})
        k.refresh_from_db()
        self.assertEqual((k.name, k.gewicht), ("Schriftlich", Decimal(50)))
        r = self.client.post(reverse("bewertungsstruktur", args=[self.u.pk]), {"aktion": "ordner_neu", "name": "Referate", "eltern": ""},
                             follow=True)
        self.assertContains(r, "Klausurregel")
        self.assertFalse(Bewertungsordner.objects.filter(unterricht=self.u, name="Referate").exists())
        self.client.post(reverse("bewertungsstruktur", args=[self.u.pk]), {"aktion": f"ordner_loeschen:{k.pk}"})
        self.assertTrue(Bewertungsordner.objects.filter(pk=k.pk).exists())
        self.assertEqual(self.client.get(reverse("klausurregeln")).status_code, 403)

    def test_regel_anlegen_verschiebt_und_loeschen_gibt_frei(self):
        u = Unterricht.objects.select_related("gruppe").filter(abschnitt=self.u.abschnitt, gruppe__name="9a").exclude(
            fach__klausurregeln__isnull=False).first()
        self.assertIsNotNone(u)
        frei = Bewertungsordner.objects.create(unterricht=u, name="Referate", gewicht=Decimal(1))
        self.anmelden("schulleitung")
        r = self.client.post(reverse("klausurregeln"), {"faecher": [u.fach_id], "jahrgang_von": 9, "jahrgang_bis": 9,
                                                        "anteil_klausur": "40", "name_klausur": "Klausuren",
                                                        "name_mitarbeit": "Sonstige Mitarbeit", "bemerkung": ""})
        self.assertRedirects(r, reverse("klausurregeln"))
        frei.refresh_from_db()
        mitarbeit = Bewertungsordner.objects.get(unterricht=u, vorgegeben=Bewertungsordner.MITARBEIT)
        self.assertEqual(frei.eltern_id, mitarbeit.pk)
        self.assertEqual(mitarbeit.gewicht, Decimal(60))
        # Überschneidung wird abgelehnt
        r = self.client.post(reverse("klausurregeln"), {"faecher": [u.fach_id], "jahrgang_von": 8, "jahrgang_bis": 10,
                                                        "anteil_klausur": "50", "name_klausur": "K", "name_mitarbeit": "S"})
        self.assertContains(r, "schon eine Regel")
        regel = Klausurregel.objects.get(faecher=u.fach, jahrgang_von=9)
        self.client.post(reverse("klausurregel_loeschen", args=[regel.pk]))
        self.assertFalse(Bewertungsordner.objects.filter(unterricht=u).exclude(vorgegeben="").exists())

    def test_stellvertretung_darf(self):
        self.anmelden("stellvertretung")
        self.assertEqual(self.client.get(reverse("klausurregeln")).status_code, 200)

    def test_ordner_verschieben(self):
        quartal2 = Bewertungsordner.objects.get(unterricht=self.u, name="Quartal 2")
        klausur = Bewertungsordner.objects.get(unterricht=self.u, vorgegeben=Bewertungsordner.KLAUSUR)
        self.anmelden("lehrkraft")
        self.client.post(reverse("bewertungsstruktur", args=[self.u.pk]), {"aktion": "speichern", f"eltern_{quartal2.pk}": str(klausur.pk)})
        quartal2.refresh_from_db()
        self.assertEqual(quartal2.eltern_id, klausur.pk)
        # Zyklus wird abgelehnt
        quartal1 = Bewertungsordner.objects.get(unterricht=self.u, name="Quartal 1")
        r = self.client.post(reverse("bewertungsstruktur", args=[self.u.pk]),
                             {"aktion": "speichern", f"eltern_{quartal2.pk}": str(quartal1.pk), f"eltern_{quartal1.pk}": str(quartal2.pk)},
                             follow=True)
        self.assertContains(r, "nicht in sich selbst")


class NotensperreTest(Grundlage):
    def konferenz_durchfuehren(self):
        k = Konferenz.objects.get(klasse=self.u.gruppe, abschnitt=self.u.abschnitt)
        k.status = Konferenz.DURCHGEFUEHRT
        k.save()

    def test_automatisch_nach_konferenz(self):
        self.assertEqual(gesperrte_schueler(self.u), set())
        self.konferenz_durchfuehren()
        self.assertEqual(gesperrte_schueler(self.u), {s.pk for s in self.schueler})
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("noten_eintragen", args=[self.u.pk]))
        self.assertRedirects(r, reverse("notenuebersicht", args=[self.u.pk]))
        ln = Leistungsnachweis.objects.filter(unterricht=self.u).first()
        r = self.client.post(reverse("bewertungsstruktur", args=[self.u.pk]), {"aktion": "speichern"}, follow=True)
        self.assertContains(r, "gesperrt")
        self.client.post(reverse("bewertungsstruktur", args=[self.u.pk]), {"aktion": f"ln_loeschen:{ln.pk}"})
        self.assertTrue(Leistungsnachweis.objects.filter(pk=ln.pk).exists())
        r = self.client.get(reverse("zeugnis_unterricht", args=[self.u.pk]))
        self.assertTrue(all(z["gesperrt"] for z in r.context["zeilen"]))
        r = self.client.get(reverse("admin:noten_note_change", args=[Note.objects.filter(leistungsnachweis=ln).first().pk]))
        self.assertNotContains(r, 'name="_save"')

    def test_freigabe_und_handsperre_durch_koordination(self):
        self.konferenz_durchfuehren()
        self.anmelden("lehrkraft")
        self.assertEqual(self.client.post(reverse("notensperre"), {"abschnitt": self.u.abschnitt_id, "klasse": self.u.gruppe_id,
                                                                    "aktion": "freigeben"}).status_code, 403)
        self.anmelden("mittelstufe")
        self.assertContains(self.client.get(reverse("notensperre")), self.u.gruppe.name)
        self.client.post(reverse("notensperre"), {"abschnitt": self.u.abschnitt_id, "klasse": self.u.gruppe_id, "aktion": "freigeben",
                                                  "grund": "Korrektur Klassenarbeit"})
        self.assertEqual(gesperrte_schueler(self.u), set())
        self.assertTrue(Protokoll.objects.filter(aktion="noten", text__contains="Korrektur").exists())
        self.client.post(reverse("notensperre"), {"abschnitt": self.u.abschnitt_id, "klasse": self.u.gruppe_id, "aktion": "sperren"})
        self.assertEqual(len(gesperrte_schueler(self.u)), len(self.schueler))
        self.client.post(reverse("notensperre"), {"abschnitt": self.u.abschnitt_id, "klasse": self.u.gruppe_id, "aktion": "automatik"})
        self.assertFalse(Notensperre.objects.exists())
        self.assertEqual(len(gesperrte_schueler(self.u)), len(self.schueler))   # Konferenz durchgeführt

    def test_einzelne_freigegebene_zeugnisse(self):
        from zeugnisse.ansichten import zeugnis_fuer

        s = self.schueler[0]
        z = zeugnis_fuer(s, self.u.abschnitt)
        z.status = z.FREIGEGEBEN
        z.save()
        self.assertEqual(gesperrte_schueler(self.u), {s.pk})
        self.anmelden("lehrkraft")
        ln = Leistungsnachweis.objects.filter(unterricht=self.u, schluessel__isnull=True).exclude(
            noten__schueler=s, noten__stufe__isnull=True).first()
        vorher = Note.objects.get(leistungsnachweis=ln, schueler=s).stufe_id
        self.assertIsNotNone(vorher)
        daten = {"ordner": ln.ordner_id, "titel": ln.titel, "datum": ln.datum.isoformat(), "gewicht": "7",
                 "schluessel": ln.schluessel_id or "", "max_be": ""}
        for x in self.schueler:
            daten[f"n_{x.pk}"] = "1"
        r = self.client.post(reverse("noten_bearbeiten", args=[self.u.pk, ln.pk]), daten, follow=True)
        self.assertContains(r, "bleiben unverändert")
        self.assertEqual(Note.objects.get(leistungsnachweis=ln, schueler=s).stufe_id, vorher)   # gesperrt: unverändert
        self.assertEqual(Note.objects.get(leistungsnachweis=ln, schueler=self.schueler[1]).stufe.bezeichnung, "1")
        ln.refresh_from_db()
        self.assertNotEqual(ln.gewicht, Decimal(7))


class ExportTest(Grundlage):
    def test_excel_und_pdf(self):
        from openpyxl import load_workbook

        self.anmelden("lehrkraft")
        r = self.client.get(reverse("noten_excel", args=[self.u.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertIn("spreadsheetml", r["Content-Type"])
        wb = load_workbook(io.BytesIO(r.content))
        werte = [c for zeile in wb.worksheets[0].iter_rows(values_only=True) for c in zeile if c]
        self.assertIn(self.schueler[0].person.anzeigename, werte)
        self.assertEqual(len(wb.worksheets), 3)
        r = self.client.get(reverse("notenbogen", args=[self.u.pk]))
        self.assertEqual(r.content[:4], b"%PDF")
        einzeln = self.client.get(reverse("notenbogen", args=[self.u.pk]) + f"?schueler={self.schueler[0].pk}")
        self.assertEqual(einzeln.content[:4], b"%PDF")
        self.assertLess(len(einzeln.content), len(r.content))
        self.assertTrue(Protokoll.objects.filter(aktion="pdf", text__contains="Notenbogen").exists())
        r = self.client.get(reverse("notenbogen", args=[self.u2.pk]))
        self.assertEqual(r.status_code, 200)

    def test_fremde_lehrkraft_darf_nicht(self):
        fremd = User.objects.create_user("fremdlk", password=PW, is_staff=False)
        self.client.logout()
        self.client.force_login(fremd)
        self.assertNotEqual(self.client.get(reverse("noten_excel", args=[self.u.pk])).status_code, 200)

    def test_knopfe_in_der_notenuebersicht(self):
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("notenuebersicht", args=[self.u.pk]))
        self.assertContains(r, reverse("noten_excel", args=[self.u.pk]))
        self.assertContains(r, reverse("notenbogen", args=[self.u.pk]))

