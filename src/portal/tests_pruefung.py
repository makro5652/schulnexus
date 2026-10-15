"""Tests zur Code-Prüfung (0.4.9.2): Abstürze bei fehlenden Verknüpfungen, Zahleneingaben, Anmeldesperre, tote Links."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from noten import eingabe as E
from noten.models import Unterricht
from portal import anmeldeschutz as A
from portal import zweifaktor as Z
from portal.models import Anmeldeversuch
from sicherung.tests import PW, Grundlage
from stammdaten.models import Gruppe, Mitgliedschaft, Personalprofil, Schuljahr
from zeugnisse import rechte as ZR
from zeugnisse.ansichten import zeugnis_fuer
from zeugnisse.models import Zeugnis


class FehlendeVerknuepfungTest(Grundlage):
    def test_zeugnis_ohne_freigebendes_konto(self):
        """Wurde das Konto gelöscht, das ein Zeugnis freigegeben hat, darf die Seite nicht abstürzen."""
        u = Unterricht.objects.filter(gruppe__name="9a", abschnitt__nummer=1).first()
        s = u.schueler().first()
        z = zeugnis_fuer(s, u.abschnitt)
        Zeugnis.objects.filter(pk=z.pk).update(status=Zeugnis.FREIGEGEBEN, freigegeben_am=timezone.now(), freigegeben_von=None)
        self.anmelden("schulleitung")
        r = self.client.get(reverse("zeugnis", args=[z.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Freigegeben")

    def test_suche_personal_ohne_bereich(self):
        pp = Personalprofil.objects.filter(aktiv=True).select_related("person").first()
        Personalprofil.objects.filter(pk=pp.pk).update(bereich=None, stellenbezeichnung="")
        self.anmelden("verwaltung")
        r = self.client.get(reverse("suche"), {"q": pp.person.nachname})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, pp.person.nachname)


class ZahleneingabeTest(Grundlage):
    def test_zahl_lesen(self):
        self.assertEqual(str(E.zahl_lesen("2,5")), "2.5")
        for unsinn in ("NaN", "nan", "Infinity", "-inf", "sNaN", "1e10", "abc", "", None):
            self.assertIsNone(E.zahl_lesen(unsinn), unsinn)

    def test_gewicht_nan_in_schnelleingabe(self):
        with self.assertRaises(E.EingabeFehler):
            E.gewicht_deuten("NaN")
        with self.assertRaises(E.EingabeFehler):
            E.gewicht_deuten("1e9")

    def test_struktur_mit_nan_kein_serverfehler(self):
        u = Unterricht.objects.filter(gruppe__name="9a", fach__kuerzel="CH", abschnitt__nummer=2).first()
        self.anmelden("lehrkraft")
        ordner = list(u.bewertungsordner.all())
        daten = {"aktion": "speichern"}
        for o in ordner:
            daten[f"name_{o.pk}"] = o.name
            daten[f"gewicht_{o.pk}"] = "NaN"
        daten["anteil_vorhalbjahr"] = "NaN"
        r = self.client.post(reverse("bewertungsstruktur", args=[u.pk]), daten)
        self.assertLess(r.status_code, 500)
        u.refresh_from_db()
        self.assertTrue(u.anteil_vorhalbjahr.is_finite())


@override_settings(ANMELDUNG_MAX_FEHLVERSUCHE=3, ANMELDUNG_MAX_JE_IP=5, ANMELDUNG_SPERRE_MINUTEN=15)
class AnmeldesperreTest(Grundlage):
    def anmeldung(self, name, passwort, **kopf):
        return self.client.post(reverse("login"), {"username": name, "password": passwort}, **kopf)

    def test_sperre_nach_fehlversuchen_und_ablauf(self):
        for _ in range(3):
            r = self.anmeldung("lehrkraft", "falsch-falsch")
            self.assertEqual(r.status_code, 200)
        # jetzt gesperrt – auch das richtige Passwort wird abgelehnt
        r = self.anmeldung("lehrkraft", PW)
        self.assertContains(r, "Zu viele fehlgeschlagene Anmeldeversuche")
        self.assertNotIn("_auth_user_id", self.client.session)
        # Groß-/Kleinschreibung umgeht die Sperre nicht
        r = self.anmeldung("LehrKraft", PW)
        self.assertContains(r, "Zu viele fehlgeschlagene Anmeldeversuche")
        # nach Ablauf des Zeitfensters wieder möglich
        Anmeldeversuch.objects.update(zeit=timezone.now() - timedelta(minutes=16))
        r = self.anmeldung("lehrkraft", PW)
        self.assertEqual(r.status_code, 302)
        self.assertFalse(Anmeldeversuch.objects.filter(benutzername="lehrkraft").exists())

    def test_erfolg_setzt_zurueck(self):
        self.anmeldung("lehrkraft", "falsch-falsch")
        self.anmeldung("lehrkraft", "falsch-falsch")
        self.assertEqual(self.anmeldung("lehrkraft", PW).status_code, 302)
        self.assertEqual(Anmeldeversuch.objects.filter(benutzername="lehrkraft").count(), 0)

    def test_sperre_je_ip(self):
        for name in ("a1", "a2", "a3", "a4", "a5"):
            self.anmeldung(name, "falsch-falsch", REMOTE_ADDR="10.0.0.7")
        r = self.anmeldung("verwaltung", PW, REMOTE_ADDR="10.0.0.7")
        self.assertContains(r, "Zu viele fehlgeschlagene Anmeldeversuche")
        self.assertEqual(self.anmeldung("verwaltung", PW, REMOTE_ADDR="10.0.0.8").status_code, 302)

    @override_settings(HINTER_PROXY=True)
    def test_ip_hinter_proxy(self):
        anfrage = type("A", (), {"META": {"REMOTE_ADDR": "172.18.0.2", "HTTP_X_FORWARDED_FOR": "1.2.3.4, 203.0.113.9"}})()
        self.assertEqual(A.client_ip(anfrage), "203.0.113.9")   # die vom eigenen Proxy angehängte Adresse
        anfrage.META["HTTP_X_FORWARDED_FOR"] = "kein-ip"
        self.assertIsNone(A.client_ip(anfrage))

    def test_ip_ohne_proxy_ignoriert_kopf(self):
        anfrage = type("A", (), {"META": {"REMOTE_ADDR": "192.0.2.5", "HTTP_X_FORWARDED_FOR": "1.2.3.4"}})()
        self.assertEqual(A.client_ip(anfrage), "192.0.2.5")

    def test_zweiter_faktor_zaehlt_mit(self):
        user = User.objects.get(username="lehrkraft")
        z = Z.eintrag(user)
        Z.einrichten_beginnen(z)
        z.refresh_from_db()
        z.aktiv = True
        z.save()
        for _ in range(3):
            r = self.anmeldung("lehrkraft", PW)
            self.assertRedirects(r, reverse("anmelden_code"), fetch_redirect_response=False)
            self.client.post(reverse("anmelden_code"), {"code": "000000"})
        self.assertGreaterEqual(Anmeldeversuch.objects.filter(benutzername="lehrkraft").count(), 3)
        r = self.anmeldung("lehrkraft", PW)
        self.assertContains(r, "Zu viele fehlgeschlagene Anmeldeversuche")


class LinksNurMitRechtTest(Grundlage):
    def test_klassenliste_ohne_aktenrecht_ohne_link(self):
        """Oberstufenkoordination sieht einen Kurs ihres Jahrgangs, aber nicht die Akten von Mittelstufen-Schüler:innen."""
        sj = Schuljahr.aktuelles()
        s = Unterricht.objects.filter(gruppe__name="9a").first().schueler().first()
        kurs = Gruppe.objects.create(schuljahr=sj, name="Kurs Q1 test", jahrgang=11, typ=Gruppe.LERNGRUPPE)
        Mitgliedschaft.objects.create(gruppe=kurs, schueler=s, von=sj.beginn)
        self.anmelden("oberstufe")
        r = self.client.get(reverse("klassenliste", args=[kurs.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, str(s.person))
        self.assertNotContains(r, reverse("schuelerakte", args=[s.pk]))
        self.assertEqual(self.client.get(reverse("schuelerakte", args=[s.pk])).status_code, 403)

    def test_zeugnis_druckknopf_nur_mit_recht(self):
        user = User.objects.get(username="oberstufe")
        for z in Zeugnis.objects.select_related("klasse", "schueler"):
            if ZR.darf_zeugnis_sehen(user, z) and not ZR.darf_drucken(user, z):
                break
        else:
            z = None
        if z is None:
            u = Unterricht.objects.filter(lehrkraft=user.person.personal).first()
            if u is None:
                self.skipTest("Oberstufenkoordination unterrichtet in den Demodaten nicht")
            z = zeugnis_fuer(u.schueler().first(), u.abschnitt)
            if not ZR.darf_zeugnis_sehen(user, z) or ZR.darf_drucken(user, z):
                self.skipTest("kein passendes Zeugnis in den Demodaten")
        self.anmelden("oberstufe")
        r = self.client.get(reverse("zeugnis", args=[z.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, reverse("zeugnis_druck", args=[z.pk]))
        self.assertEqual(self.client.get(reverse("zeugnis_druck", args=[z.pk])).status_code, 403)

    def test_schuelerakte_kurslinks_nur_mit_recht(self):
        s = Unterricht.objects.filter(gruppe__name="9a").first().schueler().first()
        self.anmelden("foerderung")
        r = self.client.get(reverse("schuelerakte", args=[s.pk]))
        self.assertEqual(r.status_code, 200)
        for n in r.context["noten"]:
            link = reverse("notenuebersicht", args=[n["unterricht"].pk])
            if n["darf_oeffnen"]:
                self.assertContains(r, link)
            else:
                self.assertNotContains(r, f'href="{link}"')
                self.assertEqual(self.client.get(link).status_code, 403)


class BefehleTest(Grundlage):
    def test_regelmaessige_befehle_laufen(self):
        import io

        from django.core.management import call_command

        for befehl in ("fehlzeiten_pruefen", "elternpost_senden", "schluessel_erzeugen"):
            aus = io.StringIO()
            call_command(befehl, stdout=aus)
            self.assertTrue(aus.getvalue().strip(), befehl)
