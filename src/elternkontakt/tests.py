"""Tests der Elternkommunikation (seit Version 0.4.2.9)."""
import re
from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.checks import run_checks
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

from fehlzeiten.models import Fehlzeit
from portal import rollen as R
from stammdaten.models import Beziehung, Gruppe, Person, Personalbereich, Personalprofil, Schuljahr

from .models import Ausloesung, Benachrichtigungsregel, Empfaenger, Gespraech
from .pruefung import kennzahl, regel_anwenden, schueler_pruefen
from .versand import gespraech_anlegen, link_token, standard_empfaenger

PW = "Test-Passwort-123"


class Grundlage(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))
        cls.sj = Schuljahr.objects.get(name="2026/27")
        cls.kl9a = Gruppe.objects.get(schuljahr=cls.sj, name="9a")
        cls.schueler = list(cls.kl9a.aktuelle_mitglieder().order_by("person__nachname", "person__vorname"))
        cls.s = next(s for s in cls.schueler if len(standard_empfaenger(s)) >= 2)
        cls.lehrkraft = User.objects.get(username="lehrkraft")         # Klassenleitung 9a
        # Lehrkraft ohne Bezug zur 9a
        p = Person.objects.create(vorname="Rita", nachname="Fremd", email="rf@privat.example")
        Personalprofil.objects.create(person=p, bereich=Personalbereich.objects.get(kuerzel="LK"), dienstbeginn=date(2024, 8, 1))
        cls.fremd = User.objects.create_user("fremd", password=PW, is_staff=False)
        cls.fremd.groups.add(Group.objects.get(name=R.LEHRER))
        p.benutzer = cls.fremd
        p.save()
        Gespraech.objects.all().delete()
        Benachrichtigungsregel.objects.all().delete()

    def anmelden(self, name):
        self.client.logout()
        self.assertTrue(self.client.login(username=name, password=PW))

    def nachricht(self, **mehr):
        daten = {"betreff": "Elternabend", "text": "Liebe Eltern, am Montag ist Elternabend.", "antworten": "on"}
        daten.update(mehr)
        return daten


class NachrichtenTest(Grundlage):
    def test_nachricht_an_eltern_ohne_versand_im_postausgang(self):
        self.anmelden("lehrkraft")
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post(reverse("elternnachricht_neu") + f"?schueler={self.s.pk}",
                                 self.nachricht(empfaenger=[b.person_id for b in standard_empfaenger(self.s)]))
        g = Gespraech.objects.get(schueler=self.s)
        self.assertRedirects(r, reverse("elterngespraech", args=[g.pk]))
        self.assertEqual(g.empfaenger.count(), len(standard_empfaenger(self.s)))
        self.assertTrue(all(e.versand_status in (Empfaenger.WARTET, Empfaenger.OHNE_EMAIL) for e in g.empfaenger.all()))
        self.assertEqual(len(mail.outbox), 0)
        self.assertContains(self.client.get(reverse("elterngespraech", args=[g.pk])), "Postausgang")

    @override_settings(ELTERN_EMAIL_VERSAND=True, ELTERN_LINK_BASIS="https://schule.example")
    def test_versand_per_email_mit_link_ohne_inhalt(self):
        personen = [b.person for b in standard_empfaenger(self.s) if b.person.email]
        with self.captureOnCommitCallbacks(execute=True):
            g = gespraech_anlegen(self.s, personen, betreff="Vertraulich", text="GEHEIMER INHALT", von=self.lehrkraft)
        self.assertEqual(len(mail.outbox), len(personen))
        m = mail.outbox[0]
        self.assertIn("https://schule.example/eltern/n/", m.body)
        self.assertNotIn("GEHEIMER INHALT", m.body)
        self.assertEqual(m.extra_headers.get("Auto-Submitted"), "auto-generated")
        self.assertTrue(all(e.versand_status == Empfaenger.VERSENDET for e in g.empfaenger.all()))

    @override_settings(ELTERN_EMAIL_VERSAND=True, EMAIL_BACKEND="elternkontakt.tests.KaputtBackend")
    def test_versandfehler_wird_vermerkt(self):
        personen = [b.person for b in standard_empfaenger(self.s) if b.person.email][:1]
        with self.captureOnCommitCallbacks(execute=True):
            g = gespraech_anlegen(self.s, personen, betreff="x", text="y", von=self.lehrkraft)
        e = g.empfaenger.get()
        self.assertEqual(e.versand_status, Empfaenger.FEHLER)
        self.assertIn("SMTP", e.versand_fehler)

    def test_email_in_sprache_der_eltern(self):
        from .versand import mail_inhalt

        person = standard_empfaenger(self.s)[0].person
        person.sprache = "en"
        person.save()
        g = gespraech_anlegen(self.s, [person], betreff="x", text="y", von=self.lehrkraft)
        betreff, text = mail_inhalt(g.empfaenger.get())
        self.assertIn("New message", betreff)
        self.assertIn("personal link", text)

    def test_ohne_auskunftsrecht_kein_empfang(self):
        b = standard_empfaenger(self.s)[0]
        Beziehung.objects.filter(pk=b.pk).update(auskunftsrecht=False)
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("elternnachricht_neu") + f"?schueler={self.s.pk}")
        self.assertNotContains(r, f'value="{b.person_id}"')
        self.assertNotIn(b.person_id, [x.person_id for x in standard_empfaenger(self.s)])

    def test_klassennachricht_je_familie_ein_gespraech(self):
        self.anmelden("lehrkraft")
        mit_kontakt = [s for s in self.schueler if standard_empfaenger(s)]
        r = self.client.post(reverse("elternnachricht_neu") + f"?gruppe={self.kl9a.pk}",
                             self.nachricht(schueler=[s.pk for s in mit_kontakt]))
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Gespraech.objects.filter(betreff="Elternabend").count(), len(mit_kontakt))

    def test_klassenliste_bietet_klassennachricht(self):
        self.anmelden("lehrkraft")
        self.assertContains(self.client.get(reverse("klassenliste", args=[self.kl9a.pk])), "?gruppe=%d" % self.kl9a.pk)


class ElternlinkTest(Grundlage):
    def setUp(self):
        self.g = gespraech_anlegen(self.s, [b.person for b in standard_empfaenger(self.s)], betreff="Bitte bestätigen",
                                   text="Text der Schule", von=self.lehrkraft, bestaetigung=True)
        self.e1, self.e2 = list(self.g.empfaenger.order_by("pk"))[:2]

    def url(self, e):
        return reverse("eltern_nachricht", args=[link_token(e)])

    def test_lesen_bestaetigen_antworten(self):
        self.client.logout()
        r = self.client.get(self.url(self.e1))
        self.assertContains(r, "Text der Schule")
        self.assertEqual(r["Referrer-Policy"], "no-referrer")
        self.assertIn("no-store", r["Cache-Control"])
        self.e1.refresh_from_db()
        self.assertIsNotNone(self.e1.gelesen_am)
        self.client.post(self.url(self.e1), {"aktion": "bestaetigen"})
        self.e1.refresh_from_db()
        self.assertIsNotNone(self.e1.bestaetigt_am)
        self.assertEqual(self.e1.bestaetigt_ueber, "link")
        self.client.post(self.url(self.e1), {"aktion": "antworten", "text": "Wir kommen gern."})
        self.g.refresh_from_db()
        self.assertTrue(self.g.ungelesen)
        self.assertEqual(self.g.beitraege.filter(von_person=self.e1.person).count(), 1)
        # Schule öffnet → gelesen
        self.anmelden("lehrkraft")
        self.assertContains(self.client.get(reverse("elterngespraech", args=[self.g.pk])), "Wir kommen gern.")
        self.g.refresh_from_db()
        self.assertFalse(self.g.ungelesen)

    def test_eltern_sehen_nur_eigene_antworten(self):
        self.client.post(self.url(self.e1), {"aktion": "antworten", "text": "Antwort von Elternteil eins"})
        r = self.client.get(self.url(self.e2))
        self.assertContains(r, "Text der Schule")
        self.assertNotContains(r, "Antwort von Elternteil eins")

    def test_manipulierter_abgelaufener_oder_erneuerter_link(self):
        token = link_token(self.e1)
        self.assertEqual(self.client.get(reverse("eltern_nachricht", args=[token[:-2] + "xx"])).status_code, 404)
        with override_settings(ELTERN_LINK_TAGE=-1):
            self.assertEqual(self.client.get(reverse("eltern_nachricht", args=[token])).status_code, 404)
        self.e1.link_erneuern()
        self.assertEqual(self.client.get(reverse("eltern_nachricht", args=[token])).status_code, 404)

    def test_abgeschlossen_keine_antwort(self):
        self.g.abgeschlossen = True
        self.g.save()
        r = self.client.post(self.url(self.e1), {"aktion": "antworten", "text": "Noch etwas"})
        self.assertEqual(r.status_code, 404)

    def test_sprache_der_eltern(self):
        self.e1.person.sprache = "en"
        self.e1.person.save()
        r = self.client.get(self.url(self.e1))
        self.assertContains(r, 'lang="en"')
        self.assertContains(r, "Confirm receipt")
        self.assertContains(self.client.get(self.url(self.e1) + "?sprache=de"), "Erhalt bestätigen")

    def test_schule_vermerkt_empfang(self):
        self.anmelden("lehrkraft")
        self.client.post(reverse("elterngespraech", args=[self.g.pk]),
                         {"aktion": "vermerken", "empfaenger": self.e2.pk, "notiz": "Rücklaufzettel"})
        self.e2.refresh_from_db()
        self.assertEqual(self.e2.bestaetigt_ueber, "schule")
        self.assertEqual(self.e2.bestaetigung_vermerkt_von, self.lehrkraft)
        self.assertIsNone(self.e2.gelesen_am)

    def test_vorschau_vermerkt_nichts(self):
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("elterngespraech_vorschau", args=[self.g.pk, self.e1.pk]))
        self.assertContains(r, "Vorschau")
        self.e1.refresh_from_db()
        self.assertIsNone(self.e1.gelesen_am)


class RechteTest(Grundlage):
    def test_fremde_lehrkraft_darf_nicht_schreiben_und_nicht_lesen(self):
        g = gespraech_anlegen(self.s, [standard_empfaenger(self.s)[0].person], betreff="x", text="y", von=self.lehrkraft)
        self.anmelden("fremd")
        self.assertEqual(self.client.get(reverse("elternnachricht_neu") + f"?schueler={self.s.pk}").status_code, 403)
        self.assertEqual(self.client.get(reverse("elterngespraech", args=[g.pk])).status_code, 403)
        self.assertNotContains(self.client.get(reverse("elternkontakt")), "?schueler=")

    def test_sekretariat_sieht_zeugnis_und_fehlzeiten_aber_keine_persoenlichen_gespraeche(self):
        persoenlich = gespraech_anlegen(self.s, [standard_empfaenger(self.s)[0].person], betreff="Persönlich", text="y", von=self.lehrkraft)
        auto = gespraech_anlegen(self.s, [standard_empfaenger(self.s)[0].person], art=Gespraech.FEHLZEITEN, vorlage="fehlzeiten",
                                 daten={"merkmal": "verspaetungen", "wert": 3, "schwelle": 3, "vorname": "X"})
        self.anmelden("verwaltung")
        self.assertEqual(self.client.get(reverse("elterngespraech", args=[persoenlich.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("elterngespraech", args=[auto.pk])).status_code, 200)
        self.anmelden("schulleitung")
        self.assertEqual(self.client.get(reverse("elterngespraech", args=[persoenlich.pk])).status_code, 200)

    def test_klassenleitung_und_stufe_sehen_gespraech_einer_fachlehrkraft(self):
        mue = User.objects.get(username="mittelstufe")   # unterrichtet Mathematik in der 9a, koordiniert 5–10
        g = gespraech_anlegen(self.s, [standard_empfaenger(self.s)[0].person], betreff="Mathe", text="y", von=mue)
        self.anmelden("lehrkraft")
        self.assertEqual(self.client.get(reverse("elterngespraech", args=[g.pk])).status_code, 200)

    def test_startseite_und_akte(self):
        g = gespraech_anlegen(self.s, [standard_empfaenger(self.s)[0].person], betreff="Hinweis", text="y", von=self.lehrkraft)
        from .versand import antwort_der_eltern

        antwort_der_eltern(g.empfaenger.first(), "Danke")
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("start"))
        self.assertContains(r, 'id="elternnachrichten"')
        self.assertContains(r, "Hinweis")
        r = self.client.get(reverse("schuelerakte", args=[self.s.pk]))
        self.assertContains(r, f"?schueler={self.s.pk}")
        self.assertContains(r, "Hinweis")

    def test_menueband(self):
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("start"))
        self.assertContains(r, reverse("elternkontakt"))
        self.assertNotContains(r, reverse("elternkontakt_regeln"))
        self.anmelden("mittelstufe")
        self.assertContains(self.client.get(reverse("start")), reverse("elternkontakt_regeln"))


class KaputtBackend:
    def __init__(self, *a, **k):
        pass

    def send_messages(self, nachrichten):
        raise OSError("SMTP nicht erreichbar")


class RegelTest(Grundlage):
    def setUp(self):
        self.stichtag = timezone.localdate()
        self.hj = self.sj.abschnitte.filter(beginn__lte=self.stichtag, ende__gte=self.stichtag).first()
        if self.hj is None:
            self.skipTest("Heute liegt in keinem Halbjahr der Demodaten.")
        self.kind = self.schueler[0]
        self.kind.fehlzeiten.all().delete()

    def verspaetung(self, tage_zurueck, quelle="lehrkraft", status="offen"):
        tag = max(self.hj.beginn, self.stichtag - timedelta(days=tage_zurueck))
        return Fehlzeit.objects.create(schueler=self.kind, art=Fehlzeit.VERSPAETUNG, datum_von=tag, minuten=10, quelle=quelle, status=status)

    def regel(self, **mehr):
        werte = dict(name="Test", merkmal="verspaetungen", zaehlung="alle", schwelle=2, zeitraum="halbjahr")
        werte.update(mehr)
        return Benachrichtigungsregel.objects.create(**werte)

    def test_signal_loest_bei_schwelle_einmal_aus(self):
        self.regel()
        with self.captureOnCommitCallbacks(execute=True):
            self.verspaetung(3)
        self.assertFalse(Ausloesung.objects.exists())
        with self.captureOnCommitCallbacks(execute=True):
            self.verspaetung(2)
        a = Ausloesung.objects.get()
        g = a.gespraech
        self.assertEqual(g.art, Gespraech.FEHLZEITEN)
        self.assertEqual({e.person_id for e in g.empfaenger.all()}, {b.person_id for b in standard_empfaenger(self.kind)})
        with translation.override("de"):
            self.assertIn("2 Verspätungen", g.beitraege.get().anzeigetext())
        with translation.override("en"):
            self.assertIn("2 late arrivals", g.beitraege.get().anzeigetext())
        with self.captureOnCommitCallbacks(execute=True):
            self.verspaetung(1)
        self.assertEqual(Ausloesung.objects.count(), 1)

    def test_wiederholen_bei_vielfachen(self):
        self.regel(wiederholen=True)
        for t in (5, 4, 3, 2):
            self.verspaetung(t)
        schueler_pruefen(self.kind, self.stichtag)
        self.assertEqual(Ausloesung.objects.get().stufe, 2)

    def test_schulische_veranstaltung_und_entschuldigt(self):
        self.regel(zaehlung="nicht_entschuldigt")
        self.verspaetung(3, quelle="schulisch")
        self.verspaetung(2, status="entschuldigt")
        self.verspaetung(1)
        self.assertEqual(kennzahl(self.kind, "verspaetungen", "alle", self.hj.beginn, self.hj.ende), 2)
        self.assertEqual(kennzahl(self.kind, "verspaetungen", "nicht_entschuldigt", self.hj.beginn, self.hj.ende), 1)
        self.assertEqual(schueler_pruefen(self.kind, self.stichtag), [])

    def test_jahrgang_ausserhalb(self):
        self.regel(jahrgang_von=5, jahrgang_bis=8)
        self.verspaetung(2)
        self.verspaetung(1)
        self.assertEqual(schueler_pruefen(self.kind, self.stichtag), [])

    def test_fehltage_ueber_wochenende_und_halbjahresgrenze(self):
        # Freitag bis Dienstag = 3 Werktage
        fr = self.hj.beginn + timedelta(days=(4 - self.hj.beginn.weekday()) % 7 + 7)
        Fehlzeit.objects.create(schueler=self.kind, art=Fehlzeit.GANZTAEGIG, datum_von=fr, datum_bis=fr + timedelta(days=4))
        self.assertEqual(kennzahl(self.kind, "fehltage", "alle", self.hj.beginn, self.hj.ende), 3)
        # nur der Teil im Zeitraum zählt
        self.assertEqual(kennzahl(self.kind, "fehltage", "alle", fr + timedelta(days=3), self.hj.ende), 2)
        stunden = self.sj.zeitraster.count()
        Fehlzeit.objects.create(schueler=self.kind, art=Fehlzeit.STUNDEN, datum_von=fr + timedelta(days=7), stunde_von=2, stunde_bis=3)
        self.assertEqual(kennzahl(self.kind, "fehlstunden", "alle", self.hj.beginn, self.hj.ende), 3 * stunden + 2)

    def test_neue_regel_still_vormerken_oder_benachrichtigen(self):
        self.verspaetung(2)
        self.verspaetung(1)
        r = self.regel()
        self.assertGreaterEqual(regel_anwenden(r, benachrichtigen=False), 1)
        a = Ausloesung.objects.get(regel=r, schueler=self.kind)
        self.assertTrue(a.still)
        self.assertIsNone(a.gespraech)
        self.assertFalse(Gespraech.objects.filter(art=Gespraech.FEHLZEITEN).exists())
        r2 = self.regel(name="Zweite")
        regel_anwenden(r2, benachrichtigen=True)
        self.assertTrue(Ausloesung.objects.get(regel=r2, schueler=self.kind).gespraech_id)

    def test_regelrechte(self):
        self.anmelden("lehrkraft")
        self.assertEqual(self.client.get(reverse("elternkontakt_regeln")).status_code, 403)
        self.anmelden("mittelstufe")
        daten = {"name": "Mittelstufe", "merkmal": "verspaetungen", "zaehlung": "alle", "schwelle": 5, "zeitraum": "halbjahr",
                 "jahrgang_von": 5, "jahrgang_bis": 10, "aktiv": "on", "bestaetigung_erbeten": "on"}
        r = self.client.post(reverse("elternkontakt_regel_neu"), daten)
        self.assertRedirects(r, reverse("elternkontakt_regeln"))
        daten.update(name="Oberstufe", jahrgang_von=11, jahrgang_bis=12)
        r = self.client.post(reverse("elternkontakt_regel_neu"), daten)
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Benachrichtigungsregel.objects.filter(name="Oberstufe").exists())
        alle = self.regel(name="Alle Jahrgänge")
        self.assertEqual(self.client.get(reverse("elternkontakt_regel", args=[alle.pk])).status_code, 403)
        self.anmelden("schulleitung")
        self.assertEqual(self.client.get(reverse("elternkontakt_regel", args=[alle.pk])).status_code, 200)
        self.anmelden("verwaltungsleitung")
        self.assertEqual(self.client.get(reverse("elternkontakt_regel", args=[alle.pk])).status_code, 200)

    def test_vorschau_speichert_nicht(self):
        self.verspaetung(2)
        self.verspaetung(1)
        self.anmelden("schulleitung")
        r = self.client.post(reverse("elternkontakt_regel_neu"), {
            "name": "V", "merkmal": "verspaetungen", "zaehlung": "alle", "schwelle": 2, "zeitraum": "halbjahr", "vorschau": "1"})
        self.assertContains(r, self.kind.person.nachname)
        self.assertFalse(Benachrichtigungsregel.objects.exists())


class ZeugnisempfangTest(Grundlage):
    def test_anfordern_und_bestaetigen(self):
        from zeugnisse.models import Zeugnis

        hj1 = self.sj.abschnitte.get(nummer=1)
        Zeugnis.objects.filter(klasse=self.kl9a, abschnitt=hj1).update(status=Zeugnis.FREIGEGEBEN)
        n = Zeugnis.objects.filter(klasse=self.kl9a, abschnitt=hj1).count()
        self.anmelden("lehrkraft")
        url = reverse("zeugnis_klasse", kwargs={"gruppe": self.kl9a.pk, "abschnitt": hj1.pk})
        self.assertContains(self.client.get(url), reverse("zeugnisempfang_anfordern", args=[self.kl9a.pk, hj1.pk]))
        self.client.post(reverse("zeugnisempfang_anfordern", args=[self.kl9a.pk, hj1.pk]), {"zurueck": url})
        anfragen = Gespraech.objects.filter(art=Gespraech.ZEUGNIS)
        self.assertEqual(anfragen.count(), sum(1 for z in Zeugnis.objects.filter(klasse=self.kl9a, abschnitt=hj1)
                                               if standard_empfaenger(z.schueler)))
        self.assertLessEqual(anfragen.count(), n)
        # zweites Anfordern legt nichts doppelt an
        self.client.post(reverse("zeugnisempfang_anfordern", args=[self.kl9a.pk, hj1.pk]))
        self.assertEqual(Gespraech.objects.filter(art=Gespraech.ZEUGNIS).count(), anfragen.count())
        g = anfragen.first()
        e = g.empfaenger.first()
        r = self.client.get(reverse("eltern_nachricht", args=[link_token(e)]) + "?sprache=de")
        self.assertContains(r, "Erhalt des Zeugnisses bestätigen")
        self.client.post(reverse("eltern_nachricht", args=[link_token(e)]), {"aktion": "bestaetigen"})
        self.assertContains(self.client.get(url), "1/")

    def test_fremde_lehrkraft_darf_nicht_anfordern(self):
        hj1 = self.sj.abschnitte.get(nummer=1)
        self.anmelden("fremd")
        r = self.client.post(reverse("zeugnisempfang_anfordern", args=[self.kl9a.pk, hj1.pk]))
        self.assertEqual(r.status_code, 403)


class ElternportalTest(Grundlage):
    def setUp(self):
        self.eltern = User.objects.get(username="eltern")
        self.person = self.eltern.person
        kind = self.person.kinder_beziehungen.first().schueler
        self.g = gespraech_anlegen(kind, [self.person], betreff="Portalnachricht", text="Hallo", von=self.lehrkraft)
        anderes = next(s for s in self.schueler if s != kind and standard_empfaenger(s))
        self.fremd_g = gespraech_anlegen(anderes, [standard_empfaenger(anderes)[0].person], betreff="Fremd", text="x", von=self.lehrkraft)

    def test_aus_keine_anmeldung(self):
        r = self.client.post(reverse("login"), {"username": "eltern", "password": PW})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "nur für Beschäftigte")

    @override_settings(ELTERNPORTAL_AKTIV=True)
    def test_an_eigene_nachrichten(self):
        r = self.client.post(reverse("login"), {"username": "eltern", "password": PW})
        self.assertEqual(r.status_code, 302)
        r = self.client.get(reverse("start"))
        self.assertRedirects(r, reverse("elternportal"))
        r = self.client.get(reverse("elternportal"))
        self.assertContains(r, "Portalnachricht")
        self.assertContains(r, "melden Sie sich nach der Nutzung ab")
        self.assertNotContains(r, "Link nicht weiter")
        self.assertNotContains(r, "Fremd")
        self.assertEqual(self.client.get(reverse("elternportal_gespraech", args=[self.g.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("elternportal_gespraech", args=[self.fremd_g.pk])).status_code, 404)
        self.assertRedirects(self.client.get(reverse("elternkontakt")), reverse("elternportal"))
        self.client.post(reverse("elternportal_gespraech", args=[self.g.pk]), {"aktion": "antworten", "text": "Antwort im Portal"})
        self.assertEqual(self.g.beitraege.filter(ueber="portal").count(), 1)

    @override_settings(ELTERNPORTAL_AKTIV=True)
    def test_systemhinweis(self):
        self.assertIn("elternkontakt.W001", [m.id for m in run_checks()])


class AdminUndKatalogTest(Grundlage):
    def test_rollenmatrix_vollstaendig(self):
        for rolle, werte in R.MATRIX.items():
            self.assertEqual({k for k, _n in R.BEREICHE} - set(werte), set(), rolle)

    def test_admin_seiten(self):
        User.objects.create_superuser("chef", "", PW)
        self.anmelden("chef")
        for name in ("gespraech", "benachrichtigungsregel", "ausloesung"):
            for art in ("changelist", "add"):
                self.assertEqual(self.client.get(reverse(f"admin:elternkontakt_{name}_{art}")).status_code, 200)

    def test_englische_texte_der_oberflaeche(self):
        self.anmelden("lehrkraft")
        self.client.post(reverse("sprache_wechseln"), {"sprache": "en", "next": "/"})
        r = self.client.get(reverse("elternkontakt"))
        self.assertContains(r, "Parent messages")
        self.assertFalse(re.search(r"Elternnachrichten", r.content.decode()))
