"""Tests: Schuljahreswechsel, Laufbahnänderungen, Abgang mit Abgangszeugnis, Archiv und Löschfristen (seit 0.4.4.0)."""
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from fehlzeiten.models import Fehlzeit
from stammdaten.models import Gruppe, Laufbahnabschnitt, Mitgliedschaft, Person, Schuelerprofil, Schuljahr
from zeugnisse.models import Beschluss, Konferenz, Zeugnis

from . import ereignisse, loeschung, wechsel as W
from .models import Laufbahnereignis, Loeschfrist, Loeschvorgang, Schuljahreswechsel, Wechselposten

PW = "Test-Passwort-123"


class Grundlage(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))
        cls.sl = User.objects.get(username="schulleitung")
        cls.sj = Schuljahr.objects.get(name="2026/27")
        cls.neu = Schuljahr.objects.get(name="2027/28")

    def anmelden(self, name):
        self.client.logout()
        self.assertTrue(self.client.login(username=name, password=PW))

    def klasse(self, name, sj=None):
        return Gruppe.objects.get(schuljahr=sj or self.sj, name=name)


class HilfenTest(TestCase):
    def test_folgename(self):
        self.assertEqual(W.folgename("2026/27"), "2027/28")
        self.assertEqual(W.folgename("2099/00"), "2100/01")
        self.assertEqual(W.folgename("2026-2027"), "2027-2028")
        self.assertEqual(W.folgename("Sommer"), "")

    def test_folgeklasse(self):
        self.assertEqual(W.folgeklasse("9a", 9), "10a")
        self.assertEqual(W.folgeklasse("Klasse 9b", 9), "Klasse 10b")
        self.assertEqual(W.folgeklasse("19a", 9), "19a")
        self.assertEqual(W.folgeklasse("AG", None), "AG")


class SchuljahrTest(Grundlage):
    def test_demo_folgejahr_mit_halbjahren(self):
        self.assertEqual(self.neu.abschnitte.count(), 2)
        a1, a2 = self.neu.abschnitte.order_by("nummer")
        self.assertEqual(a1.beginn, self.neu.beginn)
        self.assertEqual(a2.ende, self.neu.ende)
        self.assertLess(a1.ende, a2.beginn)

    def test_stichtag_im_schuljahr(self):
        self.assertEqual(self.neu.stichtag(date(2026, 10, 1)), self.neu.beginn)
        self.assertEqual(self.neu.stichtag(date(2030, 1, 1)), self.neu.ende)

    def test_aktivieren(self):
        W.aktivieren(self.neu)
        self.assertEqual(Schuljahr.aktuelles(), self.neu)
        W.aktivieren(self.sj)
        self.assertEqual(Schuljahr.objects.filter(aktiv=True).count(), 1)

    def test_seite_und_anlegen(self):
        self.anmelden("verwaltung")
        r = self.client.get(reverse("schuljahre"))
        self.assertContains(r, "2027/28")
        self.assertContains(r, "2028/29")                     # Vorschlag für das nächste Schuljahr
        r = self.client.post(reverse("schuljahre"), {"aktion": "anlegen", "name": "2028/29", "beginn": "2028-08-14",
                                                     "ende": "2029-06-22", "vorlage": self.neu.pk})
        self.assertRedirects(r, reverse("schuljahre"))
        self.assertEqual(Schuljahr.objects.get(name="2028/29").abschnitte.count(), 2)
        r = self.client.post(reverse("schuljahre"), {"aktion": "anlegen", "name": "X", "beginn": "2028-09-01", "ende": "2029-01-01"})
        self.assertContains(r, "überschneidet")

    def test_rechte(self):
        for name in ("lehrkraft", "mittelstufe", "finanzen"):
            self.anmelden(name)
            self.assertEqual(self.client.get(reverse("schuljahre")).status_code, 403, name)
            self.assertEqual(self.client.get(reverse("archiv")).status_code, 403, name)
            self.assertEqual(self.client.get(reverse("loeschfristen")).status_code, 403, name)
        self.anmelden("verwaltung")
        self.assertEqual(self.client.get(reverse("archiv")).status_code, 200)
        self.assertEqual(self.client.get(reverse("loeschfristen")).status_code, 403)
        self.anmelden("verwaltungsleitung")
        r = self.client.get(reverse("loeschfristen"))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.context["darf_aendern"])
        self.assertEqual(self.client.post(reverse("loeschfristen"), {"aktion": "fristen"}).status_code, 403)


class WechselTest(Grundlage):
    def setUp(self):
        self.w = W.wechsel_anlegen(self.sj, self.neu, self.sl)
        self.k8a, self.k9a = self.klasse("8a"), self.klasse("9a")

    def anlegen_alle(self):
        for z in W.klassenplan_zeilen(self.w):
            if not z["plan"].neu and not z["auslaufend"]:
                g, neu = W.klasse_anlegen(self.w, z["vorschlag"], z["jahrgang"], z["plan"].alt.leitung, z["plan"].alt)
                z["plan"].neu, z["plan"].neu_angelegt = g, neu
                z["plan"].save()
        W.posten_aktualisieren(self.w)

    def test_klassenplan_und_vorschlaege(self):
        zeilen = {z["plan"].alt.name: z for z in W.klassenplan_zeilen(self.w)}
        self.assertEqual(zeilen["9a"]["vorschlag"], "10a")
        self.assertEqual(zeilen["8a"]["jahrgang"], 9)
        n = self.k9a.aktuelle_mitglieder().count() + self.klasse("9b").aktuelle_mitglieder().count() + self.k8a.aktuelle_mitglieder().count()
        self.assertEqual(self.w.posten.count(), n)
        self.assertTrue(all(p.entscheidung == "versetzt" for p in self.w.posten.all()))
        # ohne Klassen im neuen Jahr fehlt die Zielklasse
        self.assertTrue(all(W.hindernis(p) for p in self.w.posten.all()))
        self.anlegen_alle()
        p = self.w.posten.filter(alte_klasse=self.k9a).first()
        self.assertEqual(p.neue_klasse.name, "10a")
        self.assertEqual(p.neue_klasse.vorgaenger, self.k9a)
        self.assertEqual(p.neue_klasse.leitung, self.k9a.leitung)
        self.assertEqual(W.hindernis(p), "")

    def test_vorschlag_aus_konferenz(self):
        s = self.k9a.aktuelle_mitglieder().first()
        abschnitt = self.sj.abschnitte.get(nummer=2)
        k = Konferenz.objects.create(klasse=self.k9a, abschnitt=abschnitt, art=Konferenz.VERSETZUNG)
        Beschluss.objects.create(konferenz=k, schueler=s, entscheidung="nicht_versetzt")
        self.w.posten.filter(schueler=s).delete()
        W.posten_aktualisieren(self.w)
        p = self.w.posten.get(schueler=s)
        self.assertEqual(p.entscheidung, "nicht_versetzt")
        self.assertIn("Versetzungskonferenz", p.grundlage)
        self.assertEqual(p.neuer_jahrgang, 9)

    def test_durchfuehren_und_zuruecknehmen(self):
        self.anlegen_alle()
        bleibt = self.w.posten.filter(alte_klasse=self.k9a).first()
        bleibt.entscheidung = "nicht_versetzt"
        bleibt.neue_klasse = Gruppe.objects.get(schuljahr=self.neu, name="9a")      # Nachfolger der 8a
        bleibt.save()
        geht = self.w.posten.filter(alte_klasse=self.k9a).exclude(pk=bleibt.pk).first()
        geht.entscheidung, geht.neue_klasse = "abgang", None
        geht.save()
        normal = self.w.posten.filter(alte_klasse=self.k8a).first()
        alte_m = Mitgliedschaft.objects.get(schueler=normal.schueler, gruppe=self.k8a)

        ok, offen = W.wechsel_durchfuehren(self.w, self.sl)
        self.assertEqual(offen, 0)
        self.assertEqual(ok, self.w.posten.count())
        self.w.refresh_from_db()
        self.assertTrue(self.w.durchgefuehrt and self.w.aktiv_umgestellt)
        self.assertEqual(Schuljahr.aktuelles(), self.neu)

        alte_m.refresh_from_db()
        self.assertEqual(alte_m.bis, self.sj.ende)
        neu_m = Mitgliedschaft.objects.get(schueler=normal.schueler, gruppe__schuljahr=self.neu)
        self.assertEqual((neu_m.gruppe.name, neu_m.von), ("9a", self.neu.beginn))
        lb = Laufbahnabschnitt.objects.get(schueler=normal.schueler, schuljahr=self.neu)
        self.assertEqual(lb.jahrgang, 9)
        self.assertEqual(Laufbahnabschnitt.objects.get(schueler=normal.schueler, schuljahr=self.sj).ergebnis, "versetzt")
        self.assertEqual(Laufbahnabschnitt.objects.get(schueler=bleibt.schueler, schuljahr=self.neu).jahrgang, 9)
        geht.schueler.refresh_from_db()
        self.assertEqual((geht.schueler.status, geht.schueler.austrittsdatum), ("abgang", self.sj.ende))
        # Stammklasse im neuen Schuljahr ist auch vor dessen Beginn sichtbar (Stichtag im Schuljahr)
        self.assertEqual(normal.schueler.stammklasse(self.neu).name, "9a")

        # einzelne Rücknahme
        normal.refresh_from_db()
        self.assertTrue(W.posten_zuruecknehmen(normal))
        alte_m.refresh_from_db()
        self.assertIsNone(alte_m.bis)
        self.assertFalse(Laufbahnabschnitt.objects.filter(schueler=normal.schueler, schuljahr=self.neu).exists())
        self.assertEqual(Laufbahnabschnitt.objects.get(schueler=normal.schueler, schuljahr=self.sj).ergebnis, "laufend")
        normal.refresh_from_db()
        self.assertEqual(normal.status, Wechselposten.OFFEN)
        # erneut durchführen
        ok, offen = W.wechsel_durchfuehren(self.w, self.sl)
        self.assertEqual((ok, offen), (1, 0))

        # gesamter Wechsel zurück
        n, geloescht = W.wechsel_zuruecknehmen(self.w)
        self.assertEqual(n, self.w.posten.count())
        self.assertEqual(Schuljahr.aktuelles(), self.sj)
        self.assertFalse(Mitgliedschaft.objects.filter(gruppe__schuljahr=self.neu).exists())
        self.assertEqual(geloescht, 3)                      # 9a, 10a, 10b waren leer und neu
        geht.schueler.refresh_from_db()
        self.assertEqual(geht.schueler.status, "aktiv")
        self.assertIsNone(geht.schueler.austrittsdatum)
        self.assertEqual(Schuljahreswechsel.objects.get(pk=self.w.pk).status, Schuljahreswechsel.VORBEREITET)

    def test_hoechster_jahrgang_abschluss(self):
        s = self.k9a.aktuelle_mitglieder().first()
        Laufbahnabschnitt.objects.filter(schueler=s, schuljahr=self.sj).update(jahrgang=12)
        self.w.posten.filter(schueler=s).delete()
        W.posten_aktualisieren(self.w)
        self.assertEqual(self.w.posten.get(schueler=s).entscheidung, "abschluss")

    def test_assistent_ueber_oberflaeche(self):
        self.anmelden("verwaltung")
        url = reverse("schuljahreswechsel", args=[self.w.pk])
        for schritt in ("klassen", "schueler", "durchfuehren"):
            self.assertEqual(self.client.get(url + "?schritt=" + schritt).status_code, 200, schritt)
        daten = {"aktion": "klassen_anlegen"}
        for z in W.klassenplan_zeilen(self.w):
            daten[f"anlegen-{z['plan'].pk}"] = "1"
            daten[f"name-{z['plan'].pk}"] = z["vorschlag"]
        self.client.post(url, daten)
        self.assertEqual(Gruppe.objects.filter(schuljahr=self.neu, typ=Gruppe.STAMMKLASSE).count(), 3)
        p = self.w.posten.filter(alte_klasse=self.k8a).first()
        r = self.client.post(url, {"aktion": "entscheidungen", f"e-{p.pk}": "ueberspringen", f"k-{p.pk}": p.neue_klasse_id})
        p.refresh_from_db()
        self.assertEqual((p.entscheidung, p.neue_klasse.name), ("ueberspringen", "10a"))
        r = self.client.post(url, {"aktion": "durchfuehren"})
        self.assertFalse(Wechselposten.objects.filter(status="durchgefuehrt").exists())   # ohne Bestätigung
        r = self.client.post(url, {"aktion": "durchfuehren", "bestaetigt": "1", "aktivieren": "1"}, follow=True)
        self.assertContains(r, "übertragen")
        self.assertEqual(Schuljahr.aktuelles(), self.neu)
        r = self.client.post(url, {"aktion": "zuruecknehmen", "bestaetigt": "1", "klassen_loeschen": "1"}, follow=True)
        self.assertEqual(Schuljahr.aktuelles(), self.sj)
        self.assertFalse(Wechselposten.objects.filter(status="durchgefuehrt").exists())


class EreignisTest(Grundlage):
    def test_umstufen_und_zuruecknehmen(self):
        k8a, k9a = self.klasse("8a"), self.klasse("9a")
        s = k8a.aktuelle_mitglieder().first()
        tag = self.sj.beginn + timedelta(days=40)
        e = ereignisse.umstufen(s, k9a, tag, self.sl, "Konferenzbeschluss")
        self.assertEqual(e.art, Laufbahnereignis.HOCHGESTUFT)
        self.assertEqual(s.stammklasse(stichtag=tag), k9a)
        teile = list(s.laufbahn.filter(schuljahr=self.sj).order_by("pk"))
        self.assertEqual([t.jahrgang for t in teile], [8, 9])
        self.assertEqual(teile[0].ergebnis, "uebersprungen")
        self.assertEqual(teile[0].bis, tag - timedelta(days=1))
        ereignisse.zuruecknehmen(e)
        self.assertEqual(s.stammklasse(stichtag=tag), k8a)
        self.assertEqual(s.laufbahn.filter(schuljahr=self.sj).count(), 1)
        self.assertEqual(s.laufbahn.get(schuljahr=self.sj).ergebnis, "laufend")
        with self.assertRaises(ValidationError):
            ereignisse.zuruecknehmen(e)

    def test_klassenwechsel_parallel(self):
        k9a, k9b = self.klasse("9a"), self.klasse("9b")
        s = k9a.aktuelle_mitglieder().first()
        e = ereignisse.umstufen(s, k9b, self.sj.beginn + timedelta(days=10))
        self.assertEqual(e.art, Laufbahnereignis.KLASSENWECHSEL)
        self.assertEqual(s.laufbahn.get(schuljahr=self.sj).stammklasse, k9b)

    def test_abgang_mit_abgangszeugnis(self):
        k9a = self.klasse("9a")
        s = k9a.aktuelle_mitglieder().first()
        konto = User.objects.create_user("schueler-test", password=PW)
        s.person.benutzer = konto
        s.person.save()
        tag = date(2026, 12, 4)
        e, z, hinweis = ereignisse.abgang_erfassen(s, tag, "umzug", "Umzug nach Mombasa", self.sl, True, "wegen Umzugs")
        s.refresh_from_db()
        self.assertTrue(s.archiviert)
        self.assertEqual(s.austrittsdatum, tag)
        self.assertFalse(Mitgliedschaft.objects.aktiv(tag + timedelta(days=1)).filter(schueler=s).exists())
        self.assertNotIn(s, k9a.aktuelle_mitglieder(tag + timedelta(days=1)))
        konto.refresh_from_db()
        self.assertFalse(konto.is_active)
        self.assertEqual(z.art, Zeugnis.ABGANG)
        self.assertEqual(z.zeugnisdatum, tag)
        self.assertEqual(s.laufbahn.get(schuljahr=self.sj).ergebnis, "abgang")
        # Druck: Titel und Abgangsvermerk
        self.client.force_login(self.sl)
        r = self.client.get(reverse("zeugnis_druck", args=[z.pk]))
        self.assertContains(r, "ABGANGSZEUGNIS")
        self.assertContains(r, "verlässt die Schule am")
        # Archiv und Akte
        r = self.client.get(reverse("archiv"))
        self.assertContains(r, s.person.nachname)
        r = self.client.get(reverse("schuelerakte", args=[s.pk]))
        self.assertContains(r, "Archiv")
        self.assertIsNone(r.context["anhang_form"])
        # Lehrkraft (Klassenleitung) sieht die Akte nicht mehr
        # Rücknahme stellt alles wieder her
        ereignisse.zuruecknehmen(e)
        s.refresh_from_db()
        self.assertEqual(s.status, "aktiv")
        self.assertIn(s, k9a.aktuelle_mitglieder(tag + timedelta(days=1)))
        self.assertFalse(Zeugnis.objects.filter(pk=z.pk, art=Zeugnis.ABGANG).exists())
        konto.refresh_from_db()
        self.assertTrue(konto.is_active)

    def test_abgang_ueber_oberflaeche(self):
        s = self.klasse("9b").aktuelle_mitglieder().first()
        self.anmelden("verwaltung")
        url = reverse("laufbahn_schueler", args=[s.pk])
        self.assertContains(self.client.get(url), "Abgang erfassen")
        r = self.client.post(url, {"aktion": "abgang", "datum": "2027-06-25", "art": "schulwechsel", "grund": "DS Kapstadt",
                                   "zeugnis": "on", "vermerk": ""}, follow=True)
        self.assertContains(r, "Abgang zum")
        s.refresh_from_db()
        self.assertEqual(s.status, "abgang")
        self.assertTrue(Zeugnis.objects.filter(schueler=s, art=Zeugnis.ABGANG).exists())
        self.assertNotContains(self.client.get(url), 'value="abgang"')       # im Archiv kein zweiter Abgang
        self.anmelden("lehrkraft")
        self.assertEqual(self.client.get(url).status_code, 403)


class LoeschfristTest(Grundlage):
    def ehemalig(self):
        return Schuelerprofil.objects.get(schuelernummer="A-2019-01")

    def test_vorschlaege_angelegt(self):
        self.assertEqual(Loeschfrist.objects.count(), len(Loeschfrist.KATEGORIEN))
        self.assertEqual(Loeschfrist.objects.get(kategorie="akte").jahre, 50)

    def test_faelligkeit(self):
        f = Loeschfrist.objects.get(kategorie="fehlzeiten")
        self.assertEqual(loeschung.faellig_am(f, date(2019, 6, 28)), date(2021, 12, 31))
        f.bezug = "austritt"
        self.assertEqual(loeschung.faellig_am(f, date(2020, 2, 29)), date(2022, 2, 28))
        faellig = loeschung.faellige(mit_anzahl=True)
        kategorien = {e["frist"].kategorie for e in faellig if e["schueler"] == self.ehemalig()}
        self.assertIn("fehlzeiten", kategorien)
        self.assertIn("kontakte", kategorien)
        self.assertNotIn("akte", kategorien)
        self.assertNotIn("noten", kategorien)              # keine Daten → als leer vermerkt
        self.assertTrue(Loeschvorgang.objects.filter(schuelernummer="A-2019-01", kategorie="noten", status="leer").exists())
        # aktuelle Schüler:innen nie
        self.assertTrue(all(e["schueler"].archiviert for e in faellig))

    def test_loeschen_mit_protokoll(self):
        s = self.ehemalig()
        ids = list(Fehlzeit.objects.filter(schueler=s).values_list("pk", flat=True))
        self.assertTrue(ids)
        n = loeschung.loeschen(s, "fehlzeiten", self.sl)
        self.assertEqual(n, len(ids))
        self.assertFalse(Fehlzeit.objects.filter(pk__in=ids).exists())
        self.assertFalse(Fehlzeit.history.filter(id__in=ids).exists())
        v = Loeschvorgang.objects.get(schuelernummer="A-2019-01", kategorie="fehlzeiten")
        self.assertEqual((v.status, v.anzahl), ("erledigt", len(ids)))
        self.assertNotIn("fehlzeiten", {e["frist"].kategorie for e in loeschung.faellige() if e["schueler"] == s})

    def test_kontakte_anonymisieren(self):
        s = self.ehemalig()
        mutter = Person.objects.get(nachname="Kamau-Richter", vorname="Grace")
        loeschung.loeschen(s, "kontakte", self.sl)
        s.refresh_from_db()
        self.assertEqual(s.person.strasse, "")
        self.assertEqual(s.lebt_bei, "")
        self.assertFalse(Person.objects.filter(pk=mutter.pk).exists())
        self.assertFalse(Person.history.filter(id=mutter.pk).exists())
        self.assertEqual(s.person.nachname, "Kamau-Richter")      # Name und Laufbahn bleiben bis zur Aktenfrist

    def test_akte_loeschen(self):
        s = self.ehemalig()
        pid, sid = s.person_id, s.pk
        loeschung.loeschen(s, "akte", self.sl)
        self.assertFalse(Person.objects.filter(pk=pid).exists())
        self.assertFalse(Schuelerprofil.history.filter(id=sid).exists())
        self.assertFalse(Laufbahnabschnitt.objects.filter(schueler_id=sid).exists())
        self.assertEqual(Loeschvorgang.objects.get(schuelernummer="A-2019-01", kategorie="akte").status, "erledigt")

    def test_nur_archiv(self):
        s = Schuelerprofil.objects.filter(status="aktiv").first()
        with self.assertRaises(ValueError):
            loeschung.loeschen(s, "fehlzeiten")

    def test_oberflaeche(self):
        self.anmelden("schulleitung")
        r = self.client.get(reverse("start"))
        self.assertContains(r, "Löschungen fällig")
        r = self.client.get(reverse("loeschfristen"))
        self.assertContains(r, "Kamau-Richter")
        s = self.ehemalig()
        r = self.client.post(reverse("loeschfristen"), {"aktion": "loeschen", "schueler": s.pk, "kategorie": "fehlzeiten"})
        self.assertTrue(Fehlzeit.objects.filter(schueler=s).exists())             # ohne Bestätigung nichts
        self.client.post(reverse("loeschfristen"), {"aktion": "loeschen", "schueler": s.pk, "kategorie": "fehlzeiten", "bestaetigt": "1"})
        self.assertFalse(Fehlzeit.objects.filter(schueler=s).exists())
        self.client.post(reverse("loeschfristen"), {"aktion": "aufschieben", "schueler": s.pk, "kategorie": "kontakte",
                                                    "bis": "2030-01-01", "grund": "Anfrage der Eltern"})
        self.assertEqual(Loeschvorgang.objects.get(schuelernummer="A-2019-01", kategorie="kontakte").status, "aufgeschoben")
        f = Loeschfrist.objects.get(kategorie="gesundheit")
        daten = {"aktion": "fristen"}
        for fr in Loeschfrist.objects.all():
            daten.update({f"jahre-{fr.pk}": fr.jahre, f"bezug-{fr.pk}": fr.bezug, f"aktion-{fr.pk}": fr.aktion,
                          f"hinweis-{fr.pk}": fr.hinweis})
            if fr.aktiv:
                daten[f"aktiv-{fr.pk}"] = "1"
        daten[f"jahre-{f.pk}"] = "3"
        self.client.post(reverse("loeschfristen"), daten)
        f.refresh_from_db()
        self.assertEqual(f.jahre, 3)
        self.assertEqual(f.geaendert_von, User.objects.get(username="schulleitung"))
        # Sekretariat darf nicht löschen
        self.anmelden("verwaltung")
        r = self.client.post(reverse("loeschfristen"), {"aktion": "loeschen", "schueler": s.pk, "kategorie": "kontakte", "bestaetigt": "1"})
        self.assertEqual(r.status_code, 403)


class SchuljahrAnzeigeTest(Grundlage):
    def test_akte_vergangenes_schuljahr(self):
        s = self.klasse("9a").aktuelle_mitglieder().first()
        frueher = s.laufbahn.exclude(schuljahr=self.sj).first()
        self.client.force_login(self.sl)
        r = self.client.get(reverse("schuelerakte", args=[s.pk]))
        self.assertEqual(r.context["sj"], self.sj)
        if frueher:
            r = self.client.get(reverse("schuelerakte", args=[s.pk]) + f"?sj={frueher.schuljahr_id}")
            self.assertEqual(r.context["sj"], frueher.schuljahr)

    def test_archiv_im_admin_nur_lesend(self):
        s = Schuelerprofil.objects.get(schuelernummer="A-2019-01")
        self.anmelden("verwaltung")
        r = self.client.post(reverse("admin:stammdaten_schuelerprofil_change", args=[s.pk]), {})
        self.assertEqual(r.status_code, 403)

    def test_menueband(self):
        self.anmelden("schulleitung")
        r = self.client.get(reverse("start"))
        for name in ("schuljahre", "archiv", "loeschfristen"):
            self.assertContains(r, reverse(name))
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("start"))
        self.assertNotContains(r, reverse("schuljahre"))
