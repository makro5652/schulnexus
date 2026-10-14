"""Tests: Schulkalender, Räume, Elternsprechtag und LEG (seit 0.4.5.0)."""
from datetime import date, time, timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from stammdaten.models import Gruppe, Schuljahr

from . import sprechtag as S
from .ansichten import serie_buchen
from .models import Gespraechstermin, Raum, Raumbuchung, Sprechtag, Teilnahme, Termin, Zeitfenster

PW = "Test-Passwort-123"


class Grundlage(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))
        cls.sj = Schuljahr.objects.get(name="2026/27")
        cls.stv = User.objects.get(username="stellvertretung")
        cls.k9a = Gruppe.objects.get(schuljahr=cls.sj, name="9a")
        # eigener Sprechtag in der Zukunft (unabhängig vom Datum des Testlaufs)
        cls.tag = cls.sj.stichtag() + timedelta(days=1)
        cls.st = Sprechtag.objects.create(art=Sprechtag.ELTERNSPRECHTAG, titel="Test-Sprechtag", schuljahr=cls.sj, jahrgang_von=9,
                                          jahrgang_bis=9, slot_minuten=10, puffer_minuten=5, max_je_kind=2, status=Sprechtag.BUCHUNG)
        Zeitfenster.objects.create(sprechtag=cls.st, datum=cls.tag, von=time(14, 0), bis=time(15, 0))
        Zeitfenster.objects.create(sprechtag=cls.st, datum=cls.tag, von=time(15, 30), bis=time(16, 0))
        S.teilnahmen_ergaenzen(cls.st)

    def anmelden(self, name):
        self.client.logout()
        self.assertTrue(self.client.login(username=name, password=PW))

    def kind_und_lk(self):
        s = self.k9a.aktuelle_mitglieder(S.stichtag(self.st)).first()
        t = S.teilnahmen_fuer_schueler(self.st, s).first()
        return s, t


class RasterTest(Grundlage):
    def test_slots_mit_wechselzeit(self):
        # 14:00–15:00 mit 10 + 5 Minuten: 14:00, 14:15, 14:30, 14:45 · 15:30–16:00: 15:30, 15:45
        zeiten = [timezone.localtime(b).strftime("%H:%M") for b, _e in self.st.slots()]
        self.assertEqual(zeiten, ["14:00", "14:15", "14:30", "14:45", "15:30", "15:45"])

    def test_teilnehmende(self):
        ids = set(self.st.teilnahmen.values_list("lehrkraft_id", flat=True))
        self.assertIn(self.k9a.leitung_id, ids)
        self.assertGreater(len(ids), 1)                          # auch Fachlehrkräfte
        leg = Sprechtag.objects.create(art=Sprechtag.LEG, titel="LEG 9", schuljahr=self.sj, jahrgang_von=9, jahrgang_bis=9)
        Zeitfenster.objects.create(sprechtag=leg, datum=self.tag, von=time(14, 0), bis=time(15, 0))
        S.teilnahmen_ergaenzen(leg)
        leitungen = set(Gruppe.objects.filter(schuljahr=self.sj, jahrgang=9, typ=Gruppe.STAMMKLASSE)
                        .exclude(leitung=None).values_list("leitung_id", flat=True))
        self.assertEqual(set(leg.teilnahmen.values_list("lehrkraft_id", flat=True)), leitungen)

    def test_verfuegbarkeit(self):
        s, t = self.kind_und_lk()
        S.nur_verfuegbar(t, self.tag, time(14, 15), time(14, 45))
        status = {timezone.localtime(z["beginn"]).strftime("%H:%M"): z["status"] for z in S.raster(t)}
        self.assertEqual(status["14:00"], "gesperrt")
        self.assertEqual(status["14:15"], "frei")
        self.assertEqual(status["14:45"], "gesperrt")            # endet 14:55 > 14:45
        self.assertEqual(status["15:30"], "gesperrt")             # zweites Fenster desselben Tages liegt außerhalb
        S.sperren_setzen(t, [])
        g = S.buchen(t, self.st.slots()[0][0], s)
        S.sperren_setzen(t, [Teilnahme.schluessel(g.beginn)])
        t.refresh_from_db()
        self.assertEqual(t.gesperrt, [])                          # gebuchte Zeit lässt sich nicht sperren


class BuchenTest(Grundlage):
    def test_regeln(self):
        s, t = self.kind_und_lk()
        erste = self.st.slots()[0][0]
        g = S.buchen(t, erste, s)
        self.assertEqual(g.ende - g.beginn, timedelta(minutes=10))
        anderer = self.k9a.aktuelle_mitglieder(S.stichtag(self.st)).exclude(pk=s.pk).first()
        with self.assertRaises(ValidationError):
            S.buchen(t, erste, anderer)                            # Zeit vergeben
        with self.assertRaises(ValidationError):
            S.buchen(t, self.st.slots()[1][0], s)                  # dieselbe Lehrkraft zweimal
        andere_lk = S.teilnahmen_fuer_schueler(self.st, s).exclude(pk=t.pk).first()
        with self.assertRaises(ValidationError):
            S.buchen(andere_lk, erste, s)                          # Kind hat zu dieser Zeit schon ein Gespräch
        S.buchen(andere_lk, self.st.slots()[1][0], s)
        dritte = S.teilnahmen_fuer_schueler(self.st, s).exclude(pk__in=[t.pk, andere_lk.pk]).first()
        if dritte:
            with self.assertRaises(ValidationError):
                S.buchen(dritte, self.st.slots()[2][0], s)         # Höchstzahl 2
        # gesperrte Zeit
        S.sperren_setzen(t, [Teilnahme.schluessel(self.st.slots()[3][0])])
        with self.assertRaises(ValidationError):
            S.buchen(t, self.st.slots()[3][0], anderer)
        # nicht vorgesehene Lehrkraft (Jahrgang 8)
        k8 = Gruppe.objects.get(schuljahr=self.sj, name="8a").aktuelle_mitglieder(S.stichtag(self.st)).first()
        with self.assertRaises(ValidationError):
            S.buchen(t, self.st.slots()[4][0], k8)

    def test_portal_nur_bei_offener_buchung(self):
        s, t = self.kind_und_lk()
        eltern = s.beziehungen.filter(sorgerecht=True).first().person
        self.st.buchung_bis = timezone.now() - timedelta(hours=1)
        self.st.save()
        with self.assertRaises(ValidationError):
            S.buchen(t, self.st.slots()[0][0], s, eltern=eltern, ueber=Gespraechstermin.PORTAL)
        self.st.buchung_bis = None
        self.st.save()
        fremd = self.k9a.aktuelle_mitglieder(S.stichtag(self.st)).exclude(beziehungen__person=eltern).first()
        with self.assertRaises(ValidationError):
            S.buchen(t, self.st.slots()[0][0], fremd, eltern=eltern, ueber=Gespraechstermin.PORTAL)
        g = S.buchen(t, self.st.slots()[0][0], s, eltern=eltern, ueber=Gespraechstermin.PORTAL)
        self.assertTrue(S.darf_absagen_eltern(g, eltern))
        self.st.status = Sprechtag.GESCHLOSSEN
        self.st.save()
        self.assertFalse(S.darf_absagen_eltern(g, eltern))


class OberflaecheTest(Grundlage):
    def test_planung_nur_stellvertretung_und_schulleitung(self):
        url = reverse("sprechtag", args=[self.st.pk])
        self.anmelden("stellvertretung")
        self.assertEqual(self.client.get(url).status_code, 200)
        r = self.client.post(url, {"aktion": "fenster", "datum": self.tag.isoformat(), "von": "16:30", "bis": "17:00"})
        self.assertEqual(self.st.zeitfenster.count(), 3)
        r = self.client.post(url, {"aktion": "fenster", "datum": self.tag.isoformat(), "von": "16:45", "bis": "17:15"}, follow=True)
        self.assertContains(r, "überschneidet")
        self.client.post(url, {"aktion": "status", "status": Sprechtag.GESCHLOSSEN})
        self.st.refresh_from_db()
        self.assertEqual(self.st.status, Sprechtag.GESCHLOSSEN)
        self.anmelden("schulleitung")
        self.assertEqual(self.client.get(url).status_code, 200)
        for name in ("lehrkraft", "verwaltung"):
            self.anmelden(name)
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302, name)              # weiter zur Übersicht
            self.assertEqual(self.client.post(url, {"aktion": "status", "status": "entwurf"}).status_code, 302)
        self.st.refresh_from_db()
        self.assertEqual(self.st.status, Sprechtag.GESCHLOSSEN)

    def test_neuer_sprechtag(self):
        self.anmelden("stellvertretung")
        r = self.client.post(reverse("sprechtage"), {"art": "leg", "titel": "LEG Jahrgang 9", "schuljahr": self.sj.pk,
                                                     "jahrgang_von": 9, "jahrgang_bis": 9, "slot_minuten": 20, "puffer_minuten": 5,
                                                     "eltern_buchen": "on"})
        st = Sprechtag.objects.get(titel="LEG Jahrgang 9")
        self.assertRedirects(r, reverse("sprechtag", args=[st.pk]))
        self.anmelden("lehrkraft")
        self.assertEqual(self.client.post(reverse("sprechtage"), {"titel": "x"}).status_code, 403)

    def test_lehrkraft_sperrt_und_bucht(self):
        s, t = self.kind_und_lk()
        user = t.lehrkraft.person.benutzer
        if user is None:
            user = User.objects.create_user("lk-test", password=PW, is_staff=True)
            from django.contrib.auth.models import Group
            from portal import rollen as R
            user.groups.add(Group.objects.get(name=R.LEHRER))
            t.lehrkraft.person.benutzer = user
            t.lehrkraft.person.save()
        self.client.force_login(user)
        url = reverse("sprechzeiten", args=[self.st.pk, t.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        alle = [Teilnahme.schluessel(b) for b, _e in self.st.slots()]
        self.client.post(url, {"aktion": "sperren", "zeit": alle, "gesperrt": alle[:2]})
        t.refresh_from_db()
        self.assertEqual(t.gesperrt, alle[:2])
        self.client.post(url, {"aktion": "buchen", "zeit": alle[2], "schueler": s.pk, "anliegen": "Leistungsstand"})
        self.assertTrue(Gespraechstermin.objects.filter(teilnahme=t, schueler=s).exists())
        self.client.post(url, {"aktion": "bestaetigen"})
        t.refresh_from_db()
        self.assertIsNotNone(t.bestaetigt_am)
        # fremde Teilnahme: kein Zugriff
        andere = self.st.teilnahmen.exclude(pk=t.pk).exclude(lehrkraft__person__benutzer=user).first()
        self.assertEqual(self.client.get(reverse("sprechzeiten", args=[self.st.pk, andere.pk])).status_code, 403)

    def test_sekretariat_uebersicht(self):
        s, t = self.kind_und_lk()
        g = S.buchen(t, self.st.slots()[0][0], s)
        self.anmelden("verwaltung")
        r = self.client.get(reverse("sprechtag_uebersicht", args=[self.st.pk]))
        self.assertContains(r, s.person.anzeigename)
        self.client.post(reverse("sprechtag_uebersicht", args=[self.st.pk]), {"aktion": "absagen", "termin": g.pk})
        self.assertFalse(Gespraechstermin.objects.filter(pk=g.pk).exists())

    def test_startseite_und_menueband(self):
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("start"))
        self.assertIn("termine", [k["schluessel"] for k in r.context["MENUEBAND"]["karten"]])
        self.assertContains(r, 'id="termine"')
        self.assertEqual(self.client.get(reverse("kalender")).status_code, 200)


@override_settings(ELTERNPORTAL_AKTIV=True)
class ElternportalTest(Grundlage):
    def test_buchen_und_absagen(self):
        s, t = self.kind_und_lk()
        eltern = s.beziehungen.filter(sorgerecht=True).select_related("person").first().person
        konto = User.objects.create_user("eltern-test", password=PW)
        from django.contrib.auth.models import Group
        from portal import rollen as R
        konto.groups.add(Group.objects.get(name=R.ELTERN))
        eltern.benutzer = konto
        eltern.save()
        self.client.force_login(konto)
        r = self.client.get(reverse("eltern_sprechtage"))
        self.assertContains(r, "Test-Sprechtag")
        url = reverse("eltern_sprechtag", args=[self.st.pk])
        r = self.client.get(url)
        self.assertContains(r, t.lehrkraft.person.anzeigename)
        zeit = Teilnahme.schluessel(self.st.slots()[1][0])
        r = self.client.post(url, {"aktion": "buchen", "teilnahme": t.pk, "schueler": s.pk, "zeit": zeit, "anliegen": "Hallo"})
        g = Gespraechstermin.objects.get(teilnahme=t, schueler=s)
        self.assertEqual((g.ueber, g.eltern), (Gespraechstermin.PORTAL, eltern))
        self.assertEqual(r["Referrer-Policy"], "same-origin")
        # Kind einer anderen Familie
        fremd = self.k9a.aktuelle_mitglieder(S.stichtag(self.st)).exclude(beziehungen__person=eltern).first()
        self.client.post(url, {"aktion": "buchen", "teilnahme": t.pk, "schueler": fremd.pk, "zeit": Teilnahme.schluessel(self.st.slots()[2][0])})
        self.assertFalse(Gespraechstermin.objects.filter(sprechtag=self.st, schueler=fremd).exists())
        self.client.post(url, {"aktion": "absagen", "termin": g.pk})
        self.assertFalse(Gespraechstermin.objects.filter(pk=g.pk).exists())
        # Personalseiten bleiben gesperrt
        self.assertRedirects(self.client.get(reverse("kalender")), reverse("elternportal"), fetch_redirect_response=False)

    @override_settings(ELTERNPORTAL_AKTIV=False)
    def test_ohne_portal(self):
        konto = User.objects.get(username="eltern")
        self.client.force_login(konto)
        self.assertNotEqual(self.client.get(reverse("eltern_sprechtage")).status_code, 200)


class KalenderRaumTest(Grundlage):
    def test_kalender_und_termin(self):
        self.anmelden("verwaltung")
        r = self.client.get(reverse("kalender") + "?monat=2026-12")
        self.assertContains(r, "Weihnachtsferien")
        aula = Raum.objects.get(kuerzel="AULA")
        Raumbuchung.objects.create(raum=aula, datum=date(2027, 3, 3), von=time(10, 0), bis=time(11, 0), zweck="Probe")
        daten = {"titel": "Infoabend", "art": "eltern", "beginn": "2027-03-03", "uhrzeit_von": "10:30", "uhrzeit_bis": "12:00", "raum": aula.pk}
        r = self.client.post(reverse("termin_neu"), daten)
        self.assertContains(r, "bereits gebucht")
        daten["uhrzeit_von"] = "11:00"
        self.client.post(reverse("termin_neu"), daten)
        t = Termin.objects.get(titel="Infoabend")
        self.assertEqual(t.raumbuchungen.count(), 1)
        r = self.client.get(reverse("kalender_ics"))
        self.assertEqual(r["Content-Type"], "text/calendar; charset=utf-8")
        self.assertIn(b"SUMMARY:Infoabend", r.content)
        self.anmelden("lehrkraft")
        self.assertEqual(self.client.post(reverse("termin_neu"), daten).status_code, 403)
        self.assertEqual(self.client.get(reverse("kalender")).status_code, 200)

    def test_raumbuchung_serie(self):
        raum = Raum.objects.get(kuerzel="A104")
        user = User.objects.get(username="lehrkraft")
        start = date(2027, 2, 1)
        Raumbuchung.objects.create(raum=raum, datum=start + timedelta(days=14), von=time(8, 0), bis=time(9, 0), zweck="Belegt")
        d = {"raum": raum, "datum": start, "von": time(8, 30), "bis": time(9, 30), "zweck": "AG", "woechentlich_bis": start + timedelta(days=28)}
        buchungen, konflikte = serie_buchen(d, user)
        self.assertEqual(len(konflikte), 1)
        self.assertFalse(Raumbuchung.objects.filter(zweck="AG").exists())         # alles oder nichts
        d["von"], d["bis"] = time(9, 0), time(10, 0)
        buchungen, konflikte = serie_buchen(d, user)
        self.assertEqual((len(buchungen), konflikte), (5, []))
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("raumplan") + f"?datum={start.isoformat()}")
        self.assertContains(r, "AG")
        b = Raumbuchung.objects.filter(zweck="AG").order_by("datum")[2]
        self.client.post(reverse("raumplan"), {"aktion": "loeschen", "buchung": b.pk, "serie": "1"})
        self.assertEqual(Raumbuchung.objects.filter(zweck="AG").count(), 2)
        fremd = Raumbuchung.objects.get(zweck="Belegt")
        self.assertEqual(self.client.post(reverse("raumplan"), {"aktion": "loeschen", "buchung": fremd.pk}).status_code, 403)
