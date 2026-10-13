from datetime import date, timedelta
from decimal import Decimal

from django.contrib.admin.sites import site
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    Dienstleister,
    Nachweis,
    Nachweisart,
    Person,
    Personalbereich,
    Personalprofil,
    Schuelerprofil,
    Zusatzfeld,
)
from .zusatzfelder import darf_sehen


class Grundlage(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("grundeinrichtung", stdout=open("/dev/null", "w"))
        cls.lk = Personalbereich.objects.get(kuerzel="LK")
        cls.sich = Personalbereich.objects.get(kuerzel="SICH")
        cls.firma = Dienstleister.objects.create(name="Wache GmbH")

    def benutzer(self, name, rolle=None, superuser=False):
        if superuser:
            return User.objects.create_superuser(name, password="Test-Passwort-123")
        u = User.objects.create_user(name, password="Test-Passwort-123", is_staff=True)
        if rolle:
            u.groups.add(Group.objects.get(name=rolle))
        return u


class PersonalTest(Grundlage):
    def test_bereiche_eingerichtet(self):
        kuerzel = set(Personalbereich.objects.values_list("kuerzel", flat=True))
        self.assertTrue({"HR", "REIN", "SICH", "FAC", "NACHM", "KUE", "TRANS"} <= kuerzel)

    def test_kuerzel_pflicht_nur_fuer_unterrichtende(self):
        p = Person.objects.create(vorname="A", nachname="B")
        with self.assertRaises(ValidationError):
            Personalprofil(person=p, bereich=self.lk).full_clean()
        Personalprofil(person=p, bereich=self.sich, anstellungsart="ortskraft").full_clean()

    def test_mehrere_ohne_kuerzel_moeglich(self):
        for i in range(3):
            Personalprofil.objects.create(person=Person.objects.create(vorname=str(i), nachname="X"), bereich=self.sich, kuerzel="")
        self.assertEqual(Personalprofil.objects.filter(kuerzel__isnull=True).count(), 3)

    def test_dienstleister_pflicht_bei_fremdfirma(self):
        p = Person.objects.create(vorname="A", nachname="B")
        with self.assertRaises(ValidationError):
            Personalprofil(person=p, bereich=self.sich, anstellungsart="dienstleister").full_clean()
        Personalprofil(person=p, bereich=self.sich, anstellungsart="dienstleister", dienstleister=self.firma).full_clean()

    def test_gueltig_bis_wird_berechnet(self):
        pp = Personalprofil.objects.create(person=Person.objects.create(vorname="A", nachname="B"), bereich=self.sich)
        art = Nachweisart.objects.get(name__startswith="Erste")
        n = Nachweis.objects.create(personal=pp, art=art, ausgestellt_am=date(2024, 2, 29))
        self.assertEqual(n.gueltig_bis, date(2026, 2, 28))  # 24 Monate, Schaltjahr korrekt behandelt

    def test_nachweisstatus(self):
        pp = Personalprofil.objects.create(person=Person.objects.create(vorname="A", nachname="B"), bereich=self.sich)
        heute = timezone.localdate()
        Nachweis.objects.create(personal=pp, art=Nachweisart.objects.get(name__startswith="Erste"), ausgestellt_am=heute - timedelta(days=800))
        Nachweis.objects.create(personal=pp, art=Nachweisart.objects.get(name__startswith="Kinderschutz"), ausgestellt_am=heute - timedelta(days=700))
        status = {a.name.split(" ")[0]: st for a, st, _ in pp.nachweisstatus()}
        self.assertEqual(status["Erste-Hilfe-Kurs"], "abgelaufen")
        self.assertEqual(status["Kinderschutz-Schulung"], "laeuft_ab")
        self.assertEqual(status["Polizeiliches"], "fehlt")


class RechteTest(Grundlage):
    def test_verwaltung_hat_keine_hr_rechte(self):
        u = self.benutzer("sek", "Verwaltung")
        self.assertTrue(u.has_perm("stammdaten.view_personalprofil"))
        self.assertFalse(u.has_perm("stammdaten.view_hr_daten"))
        self.assertFalse(u.has_perm("stammdaten.view_nachweis"))

    def test_hr_hat_hr_rechte_aber_keine_noten(self):
        u = self.benutzer("hr", "Personalverwaltung")
        self.assertTrue(u.has_perm("stammdaten.view_hr_daten"))
        self.assertTrue(u.has_perm("stammdaten.change_nachweis"))
        self.assertFalse(u.has_perm("noten.view_note"))
        self.assertFalse(u.has_perm("stammdaten.view_gesundheitsangaben"))

    def test_grundeinrichtung_entfernt_keine_angepassten_rechte(self):
        from django.contrib.auth.models import Permission

        g = Group.objects.get(name="Lehrkraft")
        extra = Permission.objects.get(codename="view_gesundheit_klasse")
        g.permissions.add(extra)
        call_command("grundeinrichtung", stdout=open("/dev/null", "w"))
        self.assertTrue(g.permissions.filter(pk=extra.pk).exists())

    def test_hr_abschnitt_nur_fuer_hr(self):
        pp = Personalprofil.objects.create(person=Person.objects.create(vorname="A", nachname="B"), bereich=self.sich)
        url = reverse("admin:stammdaten_personalprofil_change", args=[pp.pk])
        self.client.force_login(self.benutzer("sek", "Verwaltung"))
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Dienstverhältnis (HR)")
        self.client.force_login(self.benutzer("hr", "Personalverwaltung"))
        r = self.client.get(url)
        self.assertContains(r, "Dienstverhältnis (HR)")
        self.assertContains(r, "Nachweise")


class ZusatzfeldTest(Grundlage):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.haus = Zusatzfeld.objects.create(zielgruppe="schueler", name="Schulhaus (House)", typ="auswahl",
                                             optionen="Kenya\nElgon", sichtbarkeit="alle", pflicht=True)
        cls.datum = Zusatzfeld.objects.create(zielgruppe="schueler", name="Ermäßigung bis", typ="datum", sichtbarkeit="verwaltung")
        cls.zahl = Zusatzfeld.objects.create(zielgruppe="schueler", name="Spind-Nr.", typ="zahl", sichtbarkeit="alle")
        cls.jn = Zusatzfeld.objects.create(zielgruppe="schueler", name="Darf allein gehen", typ="janein", sichtbarkeit="alle")
        cls.multi = Zusatzfeld.objects.create(zielgruppe="schueler", name="Sport", typ="mehrfach", optionen="Fußball\nSchwimmen")
        cls.hr = Zusatzfeld.objects.create(zielgruppe="personal", name="Visum", typ="text", sichtbarkeit="hr")
        cls.s = Schuelerprofil.objects.create(person=Person.objects.create(vorname="A", nachname="B"), schuelernummer="1")

    def test_schluessel_automatisch_und_eindeutig(self):
        self.assertEqual(self.haus.schluessel, "schulhaus_house")
        self.assertEqual(self.datum.schluessel, "ermaessigung_bis")
        zweites = Zusatzfeld.objects.create(zielgruppe="schueler", name="Schulhaus House", typ="text")
        self.assertEqual(zweites.schluessel, "schulhaus_house_2")
        anderes = Zusatzfeld.objects.create(zielgruppe="personal", name="Schulhaus House", typ="text")
        self.assertEqual(anderes.schluessel, "schulhaus_house")  # eindeutig nur je Zielgruppe

    def test_auswahl_braucht_optionen(self):
        with self.assertRaises(ValidationError):
            Zusatzfeld(zielgruppe="schueler", name="X", typ="auswahl").full_clean()

    def test_anzeige(self):
        self.assertEqual(self.datum.anzeigewert("2027-01-31"), "31.01.2027")
        self.assertEqual(self.zahl.anzeigewert("12.50"), "12,5")
        self.assertEqual(self.jn.anzeigewert(False), "nein")
        self.assertEqual(self.multi.anzeigewert(["Fußball", "Schwimmen"]), "Fußball, Schwimmen")
        self.assertEqual(self.haus.anzeigewert(None), "—")

    def test_sichtbarkeit(self):
        lk, sek, hr = self.benutzer("lk", "Lehrkraft"), self.benutzer("sek", "Verwaltung"), self.benutzer("hr", "Personalverwaltung")
        self.assertTrue(darf_sehen(lk, self.haus))
        self.assertFalse(darf_sehen(lk, self.datum))
        self.assertTrue(darf_sehen(sek, self.datum))
        self.assertFalse(darf_sehen(sek, self.hr))
        self.assertTrue(darf_sehen(hr, self.hr))

    def _formular(self, user, daten):
        rf = RequestFactory()
        req = rf.get("/")
        req.user = user
        ma = site._registry[Schuelerprofil]
        Form = ma.get_form(req, self.s, change=True)
        basis = {"person": self.s.person_id, "schuelernummer": self.s.schuelernummer, "status": "aktiv"}
        return Form(data={**basis, **daten}, instance=self.s)

    def test_formular_speichert_typgerecht(self):
        admin = self.benutzer("chef", superuser=True)
        form = self._formular(admin, {
            "zusatz__schulhaus_house": "Elgon", "zusatz__ermaessigung_bis": "31.01.2027", "zusatz__spind_nr": "17",
            "zusatz__darf_allein_gehen": "true", "zusatz__sport": ["Fußball", "Schwimmen"],
        })
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.s.refresh_from_db()
        self.assertEqual(self.s.zusatzfelder, {
            "schulhaus_house": "Elgon", "ermaessigung_bis": "2027-01-31", "spind_nr": "17",
            "darf_allein_gehen": True, "sport": ["Fußball", "Schwimmen"],
        })

    def test_pflichtfeld(self):
        form = self._formular(self.benutzer("chef", superuser=True), {})
        self.assertFalse(form.is_valid())
        self.assertIn("zusatz__schulhaus_house", form.errors)

    def test_unsichtbare_werte_bleiben_erhalten(self):
        self.s.zusatzfelder = {"ermaessigung_bis": "2027-01-31", "altes_feld": "bleibt"}
        self.s.save()
        from django.contrib.auth.models import Permission

        lk = self.benutzer("lk", "Lehrkraft")  # darf hier ausnahmsweise bearbeiten, sieht aber kein Verwaltungsfeld
        lk.user_permissions.add(Permission.objects.get(codename="change_schuelerprofil"))
        lk = User.objects.get(pk=lk.pk)
        form = self._formular(lk, {"zusatz__schulhaus_house": "Kenya"})
        self.assertNotIn("zusatz__ermaessigung_bis", form.fields)  # Lehrkraft sieht das Feld nicht
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.s.refresh_from_db()
        self.assertEqual(self.s.zusatzfelder["ermaessigung_bis"], "2027-01-31")
        self.assertEqual(self.s.zusatzfelder["altes_feld"], "bleibt")
        self.assertEqual(self.s.zusatzfelder["schulhaus_house"], "Kenya")

    def test_inaktive_felder_ausgeblendet(self):
        self.multi.aktiv = False
        self.multi.save()
        form = self._formular(self.benutzer("chef", superuser=True), {"zusatz__schulhaus_house": "Kenya"})
        self.assertNotIn("zusatz__sport", form.fields)
