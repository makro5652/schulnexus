"""Tests 0.6.0: Kontenliste mit Filtern und Sammelaktionen, Klassenfilter und Klassensuche, Befehlssuche, Menüband."""
from django.contrib.auth.models import User
from django.urls import reverse

from portal import rollen as R
from sicherung.models import Protokoll
from stammdaten.filter import suche_mit_klasse
from stammdaten.models import Gruppe, Mitgliedschaft, Schuelerprofil, Schuljahr

from . import konten
from .tests import Grundlage


class KontenlisteTest(Grundlage):
    def test_filter_nach_rolle_status_und_merkmal(self):
        self.anmelden("it")
        url = reverse("benutzerverwaltung")
        alle = self.client.get(url)
        self.assertContains(alle, 'id="sy-sammel"')
        self.assertContains(alle, 'name="konten"')
        nur_it = self.client.get(url, {"rolle": R.IT})
        namen = {z["u"].username for z in nur_it.context["zeilen"]}
        self.assertEqual(namen, set(User.objects.filter(groups__name=R.IT).values_list("username", flat=True)))
        lk = User.objects.get(username="lehrkraft")
        lk.is_active = False
        lk.save()
        gesperrt = self.client.get(url, {"status": "gesperrt"})
        self.assertEqual({z["u"].username for z in gesperrt.context["zeilen"]}, {"lehrkraft"})
        voll = self.client.get(url, {"merkmal": "vollzugriff"})
        self.assertTrue(all(z["u"].is_superuser for z in voll.context["zeilen"]))
        self.assertTrue(voll.context["zeilen"])

    def test_sammelaktion_rolle_fuer_mehrere_konten(self):
        self.anmelden("it")
        ziele = list(User.objects.filter(username__in=["lehrkraft", "verwaltung"]))
        r = self.client.post(reverse("benutzerverwaltung") + "?status=aktiv",
                             {"konten": [u.pk for u in ziele], "aktion": "rolle_plus", "sammelrolle": R.FOERDERKOORDINATION})
        self.assertRedirects(r, reverse("benutzerverwaltung") + "?status=aktiv")
        for u in ziele:
            self.assertTrue(u.groups.filter(name=R.FOERDERKOORDINATION).exists(), u.username)
        self.assertTrue(Protokoll.objects.filter(aktion="konto", text__startswith="lehrkraft").exists())
        self.client.post(reverse("benutzerverwaltung"),
                         {"konten": [u.pk for u in ziele], "aktion": "rolle_minus", "sammelrolle": R.FOERDERKOORDINATION})
        for u in ziele:
            self.assertFalse(u.groups.filter(name=R.FOERDERKOORDINATION).exists(), u.username)

    def test_sammelaktion_behaelt_andere_rollen_und_schuetzt_das_eigene_konto(self):
        it = User.objects.get(username="it")
        lk = User.objects.get(username="lehrkraft")
        vorher = set(lk.groups.values_list("name", flat=True))
        n, hinweise = konten.sammelaktion([it, lk], "sperren", "", it)
        self.assertEqual(n, 1)
        self.assertEqual(len(hinweise), 1)                      # das eigene Konto bleibt aktiv
        it.refresh_from_db()
        lk.refresh_from_db()
        self.assertTrue(it.is_active)
        self.assertFalse(lk.is_active)
        self.assertEqual(set(lk.groups.values_list("name", flat=True)), vorher)
        n, _h = konten.sammelaktion([lk], "entsperren", "", it)
        self.assertEqual(n, 1)
        n, _h = konten.sammelaktion([lk], "zweifaktor_an", "", it)
        self.assertEqual(n, 1)
        lk.refresh_from_db()
        self.assertTrue(lk.zweifaktor.pflicht)
        with self.assertRaises(konten.KontoFehler):
            konten.sammelaktion([lk], "rolle_plus", "gibt-es-nicht", it)
        with self.assertRaises(konten.KontoFehler):
            konten.sammelaktion([lk], "loeschen", "", it)

    def test_sammelaktion_nur_fuer_it_und_nur_mit_auswahl(self):
        self.anmelden("schulleitung")
        lk = User.objects.get(username="lehrkraft")
        r = self.client.post(reverse("benutzerverwaltung"), {"konten": [lk.pk], "aktion": "sperren"})
        self.assertEqual(r.status_code, 403)
        lk.refresh_from_db()
        self.assertTrue(lk.is_active)
        self.anmelden("it")
        r = self.client.post(reverse("benutzerverwaltung"), {"aktion": "sperren"}, follow=True)
        self.assertContains(r, "Bitte zuerst Konten ankreuzen.")

    def test_einzelrechte_mit_suche(self):
        self.anmelden("it")
        lk = User.objects.get(username="lehrkraft")
        r = self.client.get(reverse("benutzer_bearbeiten", args=[lk.pk]))
        for teil in ('id="sy-rechtesuche"', 'id="sy-nur-abweichungen"', 'id="sy-rechteform"', "rechte.js"):
            self.assertContains(r, teil)

    def test_rollenuebersicht_fuehrt_zu_den_konten(self):
        self.anmelden("it")
        r = self.client.get(reverse("rollen"))
        self.assertContains(r, reverse("benutzerverwaltung") + "?rolle=")


class KlassenfilterTest(Grundlage):
    def klasse(self):
        sj = Schuljahr.aktuelles()
        return (Gruppe.objects.filter(schuljahr=sj, typ=Gruppe.STAMMKLASSE, mitgliedschaften__isnull=False)
                .distinct().order_by("name").first())

    def test_suche_mit_klassenname(self):
        g = self.klasse()
        mitglieder = set(Mitgliedschaft.objects.aktiv().filter(gruppe=g).values_list("schueler_id", flat=True))
        qs, rest, eingeschraenkt = suche_mit_klasse(Schuelerprofil.objects.all(), g.name.upper())
        self.assertTrue(eingeschraenkt)
        self.assertEqual(rest, "")
        self.assertEqual(set(qs.values_list("pk", flat=True)), mitglieder)
        eine = Schuelerprofil.objects.filter(pk__in=mitglieder).select_related("person").first()
        qs, rest, _e = suche_mit_klasse(Schuelerprofil.objects.all(), f"{g.name} {eine.person.nachname}")
        self.assertEqual(rest, eine.person.nachname)
        qs, rest, eingeschraenkt = suche_mit_klasse(Schuelerprofil.objects.all(), "Meier")
        self.assertFalse(eingeschraenkt)
        self.assertEqual(rest, "Meier")

    def test_auswahlfeld_findet_ganze_klasse(self):
        self.anmelden("it")
        g = self.klasse()
        mitglieder = Mitgliedschaft.objects.aktiv().filter(gruppe=g).count()
        r = self.client.get(reverse("admin:autocomplete"), {"term": g.name, "app_label": "fehlzeiten", "model_name": "fehlzeit",
                                                            "field_name": "schueler"})
        self.assertEqual(r.status_code, 200)
        daten = r.json()
        self.assertEqual(len(daten["results"]), min(mitglieder, 20))

    def test_listen_lassen_sich_nach_klasse_und_jahrgang_filtern(self):
        self.anmelden("it")
        g = self.klasse()
        for name in ("admin:fehlzeiten_fehlzeit_changelist", "admin:stammdaten_beziehung_changelist",
                     "admin:foerderung_foerderplan_changelist", "admin:nachmittag_agwahl_changelist",
                     "admin:noten_note_changelist", "admin:stammdaten_schuelerprofil_changelist"):
            r = self.client.get(reverse(name), {"klasse": g.pk})
            self.assertEqual(r.status_code, 200, name)
            r = self.client.get(reverse(name), {"jahrgang_aktuell": g.jahrgang})
            self.assertEqual(r.status_code, 200, name)
        r = self.client.get(reverse("admin:stammdaten_beziehung_changelist"), {"klasse": g.pk})
        mitglieder = set(Mitgliedschaft.objects.aktiv().filter(gruppe=g).values_list("schueler_id", flat=True))
        self.assertTrue(all(b.schueler_id in mitglieder for b in r.context["cl"].result_list))


class SteuerungTest(Grundlage):
    def test_befehlssuche_und_favoritenleiste_auf_jeder_seite(self):
        self.anmelden("lehrkraft")
        for url in (reverse("start"), reverse("admin:index")):
            r = self.client.get(url)
            for teil in ('id="mb-befehle-oeffnen"', 'id="bs"', 'id="mb-schnell"', "befehle.js"):
                self.assertContains(r, teil, msg_prefix=url)
        self.client.logout()
        r = self.client.get(reverse("login"))
        self.assertNotContains(r, 'id="bs"')

    def test_menueband_behaelt_alle_befehle(self):
        from portal.navigation import menueband

        self.anmelden("it")
        r = self.client.get(reverse("start"))
        mb = menueband(r.wsgi_request)
        karten = {k["schluessel"]: {g.titel: [b["titel"] for b in g.befehle] for g in k["gruppen"]} for k in mb["karten"]}
        self.assertEqual(karten["system"]["Benutzer und Rechte"], ["Konten und Rechte", "Benutzerkonten", "Rollen und Rechte", "Rollen"])
        self.assertEqual(karten["unterricht"]["Noten"], ["Noten nach Klasse", "Leistungsvorgaben"])
        self.assertEqual(karten["unterricht"]["Listen"], ["Leistungsnachweise", "Neuer Leistungsnachweis", "Bewertungsordner", "Einzelnoten"])
        self.assertEqual(karten["unterricht"]["Zeugnis"], ["Zeugnisse", "Notenliste", "Notensperre"])
        self.assertEqual(karten["unterricht"]["Konferenz und Vorlagen"], ["Konferenzen", "Textbausteine", "Unterzeichnung"])
        reihenfolge = [t for t in karten["schueler"] if t in ("Schülerakten", "Klassen und Gruppen", "Fehlzeiten", "Eltern", "Neuanmeldung")]
        self.assertEqual(reihenfolge, ["Schülerakten", "Klassen und Gruppen", "Fehlzeiten", "Eltern", "Neuanmeldung"])
