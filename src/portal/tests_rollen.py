"""Tests für das Rollenmodell (seit Version 0.4.2.3)."""
from django.contrib.auth.models import Group, Permission, User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from foerderung.models import Foerderplan, Nachteilsausgleich
from noten.models import Unterricht
from stammdaten.models import Gesundheitsangaben, Gruppe, Zusatzfeld

from . import rollen as R

PW = "Test-Passwort-123"


class RollenTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))
        cls.s9a = Gruppe.objects.get(name="9a").aktuelle_mitglieder().order_by("person__nachname").first()
        Gesundheitsangaben.objects.update_or_create(schueler=cls.s9a, defaults={"allergien": "Testallergie Haselnuss"})

    def anmelden(self, name):
        self.client.logout()
        self.assertTrue(self.client.login(username=name, password=PW), name)

    def status(self, url):
        return self.client.get(url).status_code

    # ------------------------------------------------------------ Grundlagen
    def test_alle_rollen_angelegt(self):
        self.assertEqual(set(Group.objects.values_list("name", flat=True)) >= set(R.REIHENFOLGE), True)
        self.assertFalse(Group.objects.filter(name__in=["Lehrkraft", "Verwaltung", "Personalverwaltung"]).exists())

    def test_rechte_zuruecksetzen(self):
        g = Group.objects.get(name=R.SEKRETARIAT)
        extra = Permission.objects.get(codename="change_notenskala")
        g.permissions.add(extra)
        call_command("grundeinrichtung", stdout=open("/dev/null", "w"))
        self.assertTrue(g.permissions.filter(pk=extra.pk).exists())  # normal: nur ergänzen
        call_command("grundeinrichtung", "--rechte-zuruecksetzen", stdout=open("/dev/null", "w"))
        self.assertFalse(g.permissions.filter(pk=extra.pk).exists())

    def test_schueler_und_eltern_ohne_portalzugang(self):
        for name in ("schueler", "eltern"):
            self.client.logout()
            r = self.client.post(reverse("login"), {"username": name, "password": PW})
            self.assertContains(r, "nur für Beschäftigte")
            self.assertTrue(User.objects.get(username=name).groups.exists())

    # ------------------------------------------------------------ Stufenkoordination
    def test_mittelstufe_sieht_ganze_stufe(self):
        self.anmelden("mittelstufe")  # Sabine Müller: Klassenleitung 8a, keine Klassenleitung in 9a
        r = self.client.get(reverse("schuelerakte", args=[self.s9a.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Testallergie Haselnuss")  # Gesundheitshinweise der Stufe
        u = Unterricht.objects.get(fach__kuerzel="CH", gruppe__name="9a")  # fremder Unterricht in der Stufe
        self.assertEqual(self.status(reverse("notenuebersicht", args=[u.pk])), 200)
        self.assertEqual(self.status(reverse("klassenliste", args=[Gruppe.objects.get(name="9b").pk])), 200)
        self.assertEqual(self.status(reverse("stufe", args=["mittelstufe"])), 200)
        self.assertEqual(self.status(reverse("stufe", args=["oberstufe"])), 403)
        plan = Foerderplan.objects.filter(schueler=self.s9a).first() or Foerderplan.objects.filter(
            schueler__in=Gruppe.objects.get(name="9a").aktuelle_mitglieder()).first()
        self.assertEqual(self.status(reverse("foerderplan", args=[plan.pk])), 200)
        r = self.client.get(reverse("admin:foerderung_foerderplan_change", args=[plan.pk]))
        self.assertContains(r, 'name="_save"')  # darf in der eigenen Stufe bearbeiten
        r = self.client.get(reverse("admin:foerderung_nachteilsausgleich_add"))
        self.assertNotContains(r, 'name="status"')  # Genehmigung bleibt Förderkoordination/Schulleitung

    def test_oberstufe_sieht_mittelstufe_nicht(self):
        self.anmelden("oberstufe")
        self.assertEqual(self.status(reverse("schuelerakte", args=[self.s9a.pk])), 403)
        self.assertEqual(self.status(reverse("stufe", args=["oberstufe"])), 200)
        self.assertEqual(self.status(reverse("stufe", args=["mittelstufe"])), 403)

    def test_stufenseite_inhalt(self):
        self.anmelden("mittelstufe")
        r = self.client.get(reverse("stufe", args=["mittelstufe"]))
        self.assertEqual({z["klasse"].name for z in r.context["zeilen"]}, {"8a", "9a", "9b"})
        self.assertGreaterEqual(r.context["gesamt"]["nta"], 1)

    # ------------------------------------------------------------ Verwaltung
    def test_sekretariat(self):
        self.anmelden("verwaltung")
        u = User.objects.get(username="verwaltung")
        self.assertTrue(u.has_perm("stammdaten.change_schuelerprofil"))
        self.assertTrue(u.has_perm("noten.view_notenskala"))
        self.assertFalse(u.has_perm("noten.change_notenskala"))
        self.assertFalse(u.has_perm("noten.change_note"))
        self.assertFalse(u.has_perm("stammdaten.view_hr_daten"))
        self.assertFalse(u.has_perm("auth.change_user"))
        self.assertEqual(self.status(reverse("rollen")), 403)
        self.assertEqual(self.status(reverse("schuelerakte", args=[self.s9a.pk])), 200)

    def test_verwaltungsleitung(self):
        self.anmelden("verwaltungsleitung")
        u = User.objects.get(username="verwaltungsleitung")
        for perm in ("noten.change_notenskala", "stammdaten.change_schuljahr", "noten.change_unterricht", "auth.change_user",
                     "stammdaten.view_hr_daten", "stammdaten.change_dienstleister"):
            self.assertTrue(u.has_perm(perm), perm)
        self.assertFalse(u.has_perm("noten.change_note"))
        self.assertFalse(u.has_perm("foerderung.view_foerderplan"))
        r = self.client.get(reverse("rollen"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context["zeilen"]), len(R.REIHENFOLGE))
        mb = r.context["MENUEBAND"]
        self.assertIn("finanzen", [k["schluessel"] for k in mb["karten"]])

    def test_finanzen(self):
        self.anmelden("finanzen")
        self.assertEqual(self.status(reverse("start")), 200)
        self.assertEqual(self.status(reverse("schuelerakte", args=[self.s9a.pk])), 403)
        u = Unterricht.objects.get(fach__kuerzel="CH", gruppe__name="9a")
        self.assertEqual(self.status(reverse("notenuebersicht", args=[u.pk])), 403)
        self.assertEqual(self.status(reverse("admin:stammdaten_beziehung_changelist") + "?rechnungsempfaenger__exact=1"), 200)
        self.assertEqual(self.status(reverse("admin:foerderung_foerderplan_changelist")), 403)
        mb = self.client.get("/").context["MENUEBAND"]
        self.assertIn("finanzen", [k["schluessel"] for k in mb["karten"]])
        self.assertNotIn("unterricht", [k["schluessel"] for k in mb["karten"]])
        from stammdaten.zusatzfelder import darf_sehen

        feld = Zusatzfeld.objects.filter(sichtbarkeit="verwaltung").first()
        self.assertTrue(darf_sehen(User.objects.get(username="finanzen"), feld))

    def test_hr_ohne_schuelerdaten(self):
        self.anmelden("personal")
        u = User.objects.get(username="personal")
        self.assertTrue(u.has_perm("stammdaten.view_hr_daten"))
        self.assertFalse(u.has_perm("noten.view_note"))
        self.assertEqual(self.status(reverse("schuelerakte", args=[self.s9a.pk])), 403)

    def test_schulleitung(self):
        self.anmelden("schulleitung")
        self.assertEqual(self.status(reverse("rollen")), 200)
        self.assertEqual(self.status(reverse("schuelerakte", args=[self.s9a.pk])), 200)
        self.assertEqual(self.status(reverse("stufe", args=["oberstufe"])), 200)
        nta = Nachteilsausgleich.objects.first()
        self.assertContains(self.client.get(reverse("admin:foerderung_nachteilsausgleich_change", args=[nta.pk])), 'name="status"')

    def test_rollenseite_englisch(self):
        self.anmelden("schulleitung")
        self.client.post(reverse("sprache_wechseln"), {"sprache": "en", "next": "/"})
        r = self.client.get(reverse("rollen"))
        self.assertContains(r, "Roles and permissions")
        self.assertContains(r, "Middle school coordination")
