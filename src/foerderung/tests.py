"""Tests für Anhänge zur Schülerakte und das Modul Förderung (seit Version 0.4.2.0)."""
from datetime import timedelta

from django.contrib.auth.models import Group, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from portal.rechte import darf_foerderung_sehen
from stammdaten.models import Dokument, Gruppe, Schuelerprofil

from .models import Aushaendigung, Foerdereintrag, Foerderplan, Nachteilsausgleich

PW = "Test-Passwort-123"


class Grundlage(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("demodaten", passwort=PW, stdout=open("/dev/null", "w"))
        cls.kl9a = Gruppe.objects.get(name="9a")
        cls.kl9b = Gruppe.objects.get(name="9b")
        cls.s9a = cls.kl9a.aktuelle_mitglieder().order_by("person__nachname")[1]   # Lesen/Rechtschreiben
        cls.s9b = cls.kl9b.aktuelle_mitglieder().order_by("person__nachname")[2]   # DaZ
        cls.plan_9a = Foerderplan.objects.get(schueler=cls.s9a)
        cls.plan_9b = Foerderplan.objects.get(schueler=cls.s9b)
        # zusätzliche Lehrkraft ohne Bezug zu 9a/9b
        cls.fremd = User.objects.create_user("fremd", password=PW, is_staff=True)
        cls.fremd.groups.add(Group.objects.get(name="Lehrkraft"))

    def anmelden(self, name):
        self.client.logout()
        self.assertTrue(self.client.login(username=name, password=PW))


class AnhangTest(Grundlage):
    def test_anhaenge_in_akte_nach_uploaddatum_sortiert(self):
        self.anmelden("verwaltung")
        r = self.client.get(reverse("schuelerakte", args=[self.s9a.pk]))
        anhaenge = r.context["anhaenge"]
        self.assertTrue(len(anhaenge) >= 2)
        daten = [d.hochgeladen_am for d in anhaenge]
        self.assertEqual(daten, sorted(daten, reverse=True))
        r = self.client.get(reverse("schuelerakte", args=[self.s9a.pk]) + "?sortierung=alt")
        daten = [d.hochgeladen_am for d in r.context["anhaenge"]]
        self.assertEqual(daten, sorted(daten))

    def test_kategorie_filter(self):
        self.anmelden("verwaltung")
        r = self.client.get(reverse("schuelerakte", args=[self.s9a.pk]) + "?kategorie=zeugnis")
        self.assertTrue(all(d.kategorie == "zeugnis" for d in r.context["anhaenge"]))

    def test_sichtbarkeit_nach_stufe(self):
        gutachten = Dokument.objects.get(person=self.s9a.person, kategorie="diagnostik")  # Stufe Förderteam
        anmeldung = Dokument.objects.get(person__schueler__isnull=False, kategorie="vertrag")  # Stufe Verwaltung
        # Sekretariat: Verwaltungsunterlagen ja, Gutachten nein
        self.anmelden("verwaltung")
        self.assertEqual(self.client.get(reverse("anhang", args=[anmeldung.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("anhang", args=[gutachten.pk])).status_code, 403)
        # Klassenleitung 9a: Gutachten ja (Förderteam), Anmeldeformular nein
        self.anmelden("lehrkraft")
        self.assertEqual(self.client.get(reverse("anhang", args=[gutachten.pk])).status_code, 200)
        anmeldung_9a = Dokument.objects.filter(kategorie="vertrag", person__schueler__in=self.kl9a.aktuelle_mitglieder())
        for d in anmeldung_9a:
            self.assertEqual(self.client.get(reverse("anhang", args=[d.pk])).status_code, 403)
        # fremde Lehrkraft: nichts
        self.anmelden("fremd")
        self.assertEqual(self.client.get(reverse("anhang", args=[gutachten.pk])).status_code, 403)

    def test_download_kopfzeilen(self):
        self.anmelden("lehrkraft")
        d = Dokument.objects.filter(person=self.s9a.person).exclude(datei="").first()
        r = self.client.get(reverse("anhang", args=[d.pk]))
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertIn("sandbox", r["Content-Security-Policy"])
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        r = self.client.get(reverse("anhang", args=[d.pk]) + "?ansehen=1")
        self.assertIn("inline", r["Content-Disposition"])
        self.assertTrue(b"".join(r.streaming_content).startswith(b"%PDF"))

    def test_admin_dateilink_rechtegeprueft(self):
        d = Dokument.objects.filter(person=self.s9a.person, zugriffsstufe="foerderung").exclude(datei="").first()
        self.assertTrue(d.datei.url.startswith("/anhang/datei/"))
        self.anmelden("verwaltung")
        self.assertEqual(self.client.get(d.datei.url).status_code, 403)
        self.anmelden("foerderung")
        self.assertEqual(self.client.get(d.datei.url).status_code, 200)

    def test_hochladen_beliebiger_datei(self):
        self.anmelden("lehrkraft")
        datei = SimpleUploadedFile("Messprotokoll Gruppe 3.xlsx", b"PK\x03\x04beliebiger inhalt",
                                   content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        r = self.client.post(reverse("anhang_hochladen", args=[self.s9a.pk]), {
            "anhang-titel": "Messprotokoll", "anhang-kategorie": "sonstiges", "anhang-zugriffsstufe": "akte",
            "anhang-datei": datei, "anhang-notiz": ""})
        self.assertEqual(r.status_code, 302)
        d = Dokument.objects.get(titel="Messprotokoll")
        self.assertEqual(d.originalname, "Messprotokoll Gruppe 3.xlsx")
        self.assertEqual(d.groesse, len(b"PK\x03\x04beliebiger inhalt"))
        self.assertNotIn("Messprotokoll", d.datei.name)  # zufälliger Dateiname auf dem Datenträger
        self.assertEqual(d.hochgeladen_von.username, "lehrkraft")
        # erscheint ganz oben (neuester Anhang)
        r = self.client.get(reverse("schuelerakte", args=[self.s9a.pk]))
        self.assertEqual(r.context["anhaenge"][0].pk, d.pk)
        # Download liefert den Originalnamen
        r = self.client.get(reverse("anhang", args=[d.pk]))
        self.assertIn("Messprotokoll%20Gruppe%203.xlsx", r["Content-Disposition"])

    def test_nur_notiz_ohne_datei(self):
        self.anmelden("lehrkraft")
        self.client.post(reverse("anhang_hochladen", args=[self.s9a.pk]), {
            "anhang-titel": "Telefonat", "anhang-kategorie": "korrespondenz", "anhang-zugriffsstufe": "akte",
            "anhang-notiz": "Vater ruft wegen Ausflug an."})
        self.assertTrue(Dokument.objects.filter(titel="Telefonat", datei="").exists())
        r = self.client.post(reverse("anhang_hochladen", args=[self.s9a.pk]), {
            "anhang-titel": "Leer", "anhang-kategorie": "sonstiges", "anhang-zugriffsstufe": "akte", "anhang-notiz": ""})
        self.assertFalse(Dokument.objects.filter(titel="Leer").exists())

    def test_lehrkraft_kann_keine_hoehere_stufe_vergeben(self):
        self.anmelden("lehrkraft")
        self.client.post(reverse("anhang_hochladen", args=[self.s9a.pk]), {
            "anhang-titel": "Geheim", "anhang-kategorie": "sonstiges", "anhang-zugriffsstufe": "leitung", "anhang-notiz": "x"})
        self.assertFalse(Dokument.objects.filter(titel="Geheim").exists())

    @override_settings(DOKUMENT_MAX_MB=1)
    def test_groessenbegrenzung(self):
        self.anmelden("lehrkraft")
        gross = SimpleUploadedFile("gross.bin", b"0" * (1024 * 1024 + 1))
        self.client.post(reverse("anhang_hochladen", args=[self.s9a.pk]), {
            "anhang-titel": "Zu gross", "anhang-kategorie": "sonstiges", "anhang-zugriffsstufe": "akte", "anhang-datei": gross})
        self.assertFalse(Dokument.objects.filter(titel="Zu gross").exists())

    def test_fremde_lehrkraft_kann_nicht_hochladen(self):
        self.anmelden("fremd")
        r = self.client.post(reverse("anhang_hochladen", args=[self.s9a.pk]), {
            "anhang-titel": "x", "anhang-kategorie": "sonstiges", "anhang-zugriffsstufe": "akte", "anhang-notiz": "x"})
        self.assertEqual(r.status_code, 403)

    def test_loeschen_entfernt_datei(self):
        self.anmelden("lehrkraft")
        self.client.post(reverse("anhang_hochladen", args=[self.s9a.pk]), {
            "anhang-titel": "Wegwerf", "anhang-kategorie": "sonstiges", "anhang-zugriffsstufe": "akte",
            "anhang-datei": SimpleUploadedFile("a.txt", b"hallo")})
        d = Dokument.objects.get(titel="Wegwerf")
        speicher, name = d.datei.storage, d.datei.name
        self.assertTrue(speicher.exists(name))
        self.anmelden("fremd")
        self.assertEqual(self.client.post(reverse("anhang_loeschen", args=[d.pk])).status_code, 403)
        self.anmelden("lehrkraft")
        self.client.post(reverse("anhang_loeschen", args=[d.pk]))
        self.assertFalse(Dokument.objects.filter(pk=d.pk).exists())
        self.assertFalse(speicher.exists(name))

    def test_personalunterlagen_nur_hr(self):
        from stammdaten.models import Personalprofil

        pp = Personalprofil.objects.get(kuerzel="KRA")
        d = Dokument.objects.create(person=pp.person, titel="Arbeitsvertrag", kategorie="vertrag", notiz="liegt in Papierform vor")
        self.anmelden("verwaltung")
        self.assertEqual(self.client.get(reverse("admin:stammdaten_dokument_change", args=[d.pk])).status_code, 302)
        self.anmelden("personal")
        self.assertEqual(self.client.get(reverse("admin:stammdaten_dokument_change", args=[d.pk])).status_code, 200)


class FoerderRechteTest(Grundlage):
    def test_klassenleitung_sieht_und_bearbeitet_eigene_klasse(self):
        self.anmelden("lehrkraft")
        self.assertEqual(self.client.get(reverse("foerderplan", args=[self.plan_9a.pk])).status_code, 200)
        r = self.client.get(reverse("admin:foerderung_foerderplan_change", args=[self.plan_9a.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'name="_save"')

    def test_fachlehrkraft_sieht_nur_lesend(self):
        # Martin Krause unterrichtet Chemie in 9b, ist dort aber nicht Klassenleitung
        self.anmelden("lehrkraft")
        self.assertEqual(self.client.get(reverse("foerderplan", args=[self.plan_9b.pk])).status_code, 200)
        r = self.client.get(reverse("admin:foerderung_foerderplan_change", args=[self.plan_9b.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'name="_save"')
        # Erhalt bestätigen darf nur, wer bearbeiten darf
        a = Aushaendigung.objects.filter(foerderplan=self.plan_9b, bestaetigt_am__isnull=True).first()
        self.assertEqual(self.client.post(reverse("erhalt_bestaetigen", args=[a.pk])).status_code, 403)

    def test_fachlehrkraft_darf_verlauf_ergaenzen(self):
        self.anmelden("lehrkraft")
        self.client.post(reverse("foerdereintrag_anlegen", args=[self.plan_9b.pk]), {
            "eintrag-datum": timezone.localdate().isoformat(), "eintrag-art": "beobachtung",
            "eintrag-text": "Arbeitet im Labor konzentriert."})
        e = Foerdereintrag.objects.get(text="Arbeitet im Labor konzentriert.")
        self.assertEqual(e.schueler, self.s9b)
        self.assertEqual(e.verfasst_von.username, "lehrkraft")

    def test_fremde_lehrkraft_sieht_nichts(self):
        self.anmelden("fremd")
        self.assertEqual(self.client.get(reverse("foerderplan", args=[self.plan_9a.pk])).status_code, 403)
        r = self.client.get(reverse("admin:foerderung_foerderplan_changelist"))
        self.assertEqual(r.context["cl"].result_count, 0)

    def test_sekretariat_sieht_nachteilsausgleich_aber_keinen_foerderplan(self):
        self.anmelden("verwaltung")
        self.assertEqual(self.client.get(reverse("foerderplan", args=[self.plan_9a.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin:foerderung_foerderplan_changelist")).status_code, 403)
        nta = Nachteilsausgleich.objects.filter(schueler=self.s9a).first()
        r = self.client.get(reverse("nachteilsausgleich", args=[nta.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Gutachten vom")  # Begründung bleibt dem Förderteam vorbehalten
        self.assertEqual(self.client.get(reverse("admin:foerderung_nachteilsausgleich_changelist")).status_code, 200)

    def test_foerderkoordination_sieht_alles(self):
        self.anmelden("foerderung")
        for plan in Foerderplan.objects.all():
            self.assertEqual(self.client.get(reverse("foerderplan", args=[plan.pk])).status_code, 200)
        r = self.client.get(reverse("schuelerakte", args=[self.s9a.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'id="foerderung"')
        self.assertIsNone(r.context["gesundheit"])  # keine Gesundheitsdaten über die Förderrolle

    def test_klassenleitung_kann_nta_nicht_selbst_genehmigen(self):
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("admin:foerderung_nachteilsausgleich_add") + f"?schueler={self.s9a.pk}")
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'name="status"')
        self.anmelden("foerderung")
        r = self.client.get(reverse("admin:foerderung_nachteilsausgleich_add"))
        self.assertContains(r, 'name="status"')

    def test_rolle_verwaltung_ohne_foerderplanrechte(self):
        verwaltung = Group.objects.get(name="Verwaltung")
        codes = set(verwaltung.permissions.filter(content_type__app_label="foerderung").values_list("codename", flat=True))
        self.assertEqual(codes, {"view_nachteilsausgleich", "view_foerderschwerpunkt", "view_ausgleichsmassnahme"})

    def test_rechtefunktion(self):
        self.assertTrue(darf_foerderung_sehen(User.objects.get(username="lehrkraft"), self.s9b))
        self.assertFalse(darf_foerderung_sehen(User.objects.get(username="verwaltung"), self.s9b))


class ElternbestaetigungTest(Grundlage):
    def test_aushaendigen_und_bestaetigen(self):
        plan = Foerderplan.objects.get(schueler__in=self.kl9a.aktuelle_mitglieder(), titel="Arbeitsorganisation")
        self.assertEqual(plan.eltern_status, "fehlt")
        elternteil = plan.schueler.beziehungen.first().person
        self.anmelden("lehrkraft")
        heute = timezone.localdate()
        self.client.post(reverse("aushaendigung_anlegen"), {
            "dokument": "plan", "dokument_id": plan.pk, "aush-empfaenger": elternteil.pk,
            "aush-ausgehaendigt_am": heute.isoformat(), "aush-weg": "persoenlich", "aush-bemerkung": ""})
        a = Aushaendigung.objects.get(foerderplan=plan)
        self.assertIsNotNone(a.stand)
        self.assertEqual(Foerderplan.objects.get(pk=plan.pk).eltern_status, "offen")
        self.client.post(reverse("erhalt_bestaetigen", args=[a.pk]), {
            "best-bestaetigt_am": heute.isoformat(), "best-bestaetigung": "unterschrift"})
        a.refresh_from_db()
        self.assertEqual(a.bestaetigt_am, heute)
        self.assertEqual(a.bestaetigt_durch_konto.username, "lehrkraft")
        self.assertEqual(Foerderplan.objects.get(pk=plan.pk).eltern_status, "ok")

    def test_bestaetigung_nicht_vor_aushaendigung(self):
        a = Aushaendigung.objects.filter(foerderplan=self.plan_9b, bestaetigt_am__isnull=True).first()
        self.anmelden("foerderung")
        self.client.post(reverse("erhalt_bestaetigen", args=[a.pk]), {
            "best-bestaetigt_am": (a.ausgehaendigt_am - timedelta(days=1)).isoformat(), "best-bestaetigung": "unterschrift"})
        a.refresh_from_db()
        self.assertIsNone(a.bestaetigt_am)

    def test_empfaenger_muss_elternteil_sein(self):
        fremde_person = self.s9b.beziehungen.first().person
        self.anmelden("lehrkraft")
        self.client.post(reverse("aushaendigung_anlegen"), {
            "dokument": "plan", "dokument_id": self.plan_9a.pk, "aush-empfaenger": fremde_person.pk,
            "aush-ausgehaendigt_am": timezone.localdate().isoformat(), "aush-weg": "email"})
        self.assertFalse(Aushaendigung.objects.filter(foerderplan=self.plan_9a, empfaenger=fremde_person).exists())

    def test_inhaltliche_aenderung_macht_aushaendigung_veraltet(self):
        self.assertEqual(self.plan_9a.eltern_status, "ok")
        self.anmelden("lehrkraft")
        url = reverse("admin:foerderung_foerderplan_change", args=[self.plan_9a.pk])
        formular = self.client.get(url).context["adminform"].form
        daten = admin_postdaten(self.client.get(url))
        # 1) unverändert speichern -> bleibt bestätigt
        self.client.post(url, daten)
        self.assertEqual(Foerderplan.objects.get(pk=self.plan_9a.pk).eltern_status, "ok")
        # 2) Inhalt ändern -> Hinweis „seit Aushändigung geändert“
        daten["ausgangslage"] = formular.initial["ausgangslage"] + " Ergänzung nach Elterngespräch."
        r = self.client.post(url, daten)
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["adminform"].form.errors)
        plan = Foerderplan.objects.get(pk=self.plan_9a.pk)
        plan.geaendert_am = plan.geaendert_am + timedelta(minutes=5)  # Toleranz von 1 Minute im Modell
        plan.save(update_fields=["geaendert_am"])
        self.assertEqual(Foerderplan.objects.get(pk=self.plan_9a.pk).eltern_status, "veraltet")

    def test_admin_aktion_erhalt_bestaetigen(self):
        a = Aushaendigung.objects.filter(nachteilsausgleich__schueler=self.s9a, bestaetigt_am__isnull=True).first()
        self.anmelden("lehrkraft")
        self.client.post(reverse("admin:foerderung_aushaendigung_changelist"),
                         {"action": "erhalt_heute_bestaetigen", "_selected_action": [a.pk]})
        a.refresh_from_db()
        self.assertIsNotNone(a.bestaetigt_am)


class PortalFoerderTest(Grundlage):
    def test_startseite_klassenleitung(self):
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("start"))
        f = r.context["foerderung"]
        self.assertFalse(f["koordination"])
        self.assertTrue(any(p.titel == "Arbeitsorganisation" for p in f["plan_ohne"]))
        self.assertTrue(any(p.titel == "Arbeitsorganisation" for p in f["evaluation"]))
        self.assertTrue(f["offen"])  # Nachteilsausgleich per E-Mail, Erhalt offen
        self.assertFalse(any(n.schueler_id == self.s9b.pk for n in f["ablauf"]))  # andere Klasse

    def test_startseite_koordination(self):
        self.anmelden("foerderung")
        f = self.client.get(reverse("start")).context["foerderung"]
        self.assertTrue(f["koordination"])
        self.assertTrue(any(n.schueler_id == self.s9b.pk for n in f["ablauf"]))
        self.assertTrue(f["beantragt"])

    def test_keine_foerderhinweise_ohne_rolle(self):
        self.anmelden("verwaltung")
        self.assertIsNone(self.client.get(reverse("start")).context["foerderung"])

    def test_nta_markierung_in_notenuebersicht(self):
        from noten.models import Unterricht

        self.anmelden("lehrkraft")
        # Chemie 9a: Nachteilsausgleich gilt nur für Deutsch und Englisch -> keine Markierung
        u = Unterricht.objects.get(fach__kuerzel="CH", gruppe__name="9a")
        zeilen = self.client.get(reverse("notenuebersicht", args=[u.pk])).context["zeilen"]
        self.assertFalse([z for z in zeilen if z["nta"]])
        # Chemie 9b: DaZ-Nachteilsausgleich gilt für alle Fächer -> Markierung
        u = Unterricht.objects.get(fach__kuerzel="CH", gruppe__name="9b")
        r = self.client.get(reverse("notenuebersicht", args=[u.pk]))
        markiert = [z for z in r.context["zeilen"] if z["nta"]]
        self.assertEqual([z["schueler"].pk for z in markiert], [self.s9b.pk])
        self.assertContains(r, "nta-marke")

    def test_druckansicht(self):
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("foerderplan", args=[self.plan_9a.pk]))
        self.assertContains(r, "window.print()")
        self.assertContains(r, "unterschriften")
        nta = Nachteilsausgleich.objects.filter(schueler=self.s9a).first()
        r = self.client.get(reverse("nachteilsausgleich", args=[nta.pk]))
        self.assertContains(r, "Notenschutz")

    def test_alle_foerderseiten_englisch(self):
        self.anmelden("foerderung")
        self.client.post(reverse("sprache_wechseln"), {"sprache": "en", "next": "/"})
        r = self.client.get(reverse("foerderplan", args=[self.plan_9a.pk]))
        self.assertContains(r, "Support plan")
        self.assertContains(r, "Reading and spelling")
        r = self.client.get(reverse("schuelerakte", args=[self.s9a.pk]))
        self.assertContains(r, "Attachments")
        self.assertContains(r, "Access arrangements")
        self.assertContains(self.client.get(reverse("start")), "Parent confirmation pending")

    def test_admin_seiten_laden(self):
        from django.contrib import admin

        chef = User.objects.create_superuser("chef", "", PW)
        self.anmelden("chef")
        for model in admin.site._registry:
            if model._meta.app_label not in {"foerderung", "stammdaten"}:
                continue
            info = (model._meta.app_label, model._meta.model_name)
            for name in ("changelist", "add"):
                self.assertEqual(self.client.get(reverse(f"admin:{info[0]}_{info[1]}_{name}")).status_code, 200, info)
        for plan in Foerderplan.objects.all():
            self.assertEqual(self.client.get(reverse("admin:foerderung_foerderplan_change", args=[plan.pk])).status_code, 200)
        self.assertIsNotNone(chef)

    def test_neuer_plan_mit_aushaendigung_in_einem_schritt(self):
        """Plan samt Ziel und Aushändigung im selben Formular anlegen (übergeordneter Plan noch ungespeichert)."""
        s = Schuelerprofil.objects.filter(pk__in=self.kl9a.aktuelle_mitglieder()).exclude(foerderplaene__isnull=False).first()
        elternteil = s.beziehungen.first().person
        self.anmelden("lehrkraft")
        url = reverse("admin:foerderung_foerderplan_add")
        daten = admin_postdaten(self.client.get(url + f"?schueler={s.pk}"))
        daten.update({
            "schueler": s.pk, "titel": "Neu", "status": "aktiv", "gueltig_von": timezone.localdate().isoformat(),
            "ziele-TOTAL_FORMS": "1", "ziele-0-ziel": "Testziel", "ziele-0-reihenfolge": "1", "ziele-0-ergebnis": "offen",
            "aushaendigungen-TOTAL_FORMS": "1", "aushaendigungen-0-empfaenger": elternteil.pk,
            "aushaendigungen-0-ausgehaendigt_am": timezone.localdate().isoformat(), "aushaendigungen-0-weg": "persoenlich",
        })
        r = self.client.post(url, daten)
        self.assertEqual(r.status_code, 302, r.context and [r.context["adminform"].form.errors,
                                                             [fs.errors for fs in r.context["inline_admin_formsets"]]])
        plan = Foerderplan.objects.get(schueler=s, titel="Neu")
        self.assertEqual(plan.erstellt_von.username, "lehrkraft")
        self.assertEqual(plan.ziele.count(), 1)
        self.assertEqual(plan.aushaendigungen.get().stand is not None, True)


def admin_postdaten(antwort):
    """Liest alle Formularwerte einer Admin-Änderungsseite aus (wie ein Browser sie senden würde)."""
    from django.forms.models import BaseModelFormSet

    ctx = antwort.context
    daten = {}
    form = ctx["adminform"].form
    for name, feld in form.fields.items():
        wert = form[name].value()
        if wert is None:
            continue
        if isinstance(wert, (list, tuple)):
            daten[name] = [str(v) for v in wert]
        elif hasattr(wert, "isoformat"):
            daten[name] = wert.isoformat()
        elif isinstance(wert, bool):
            if wert:
                daten[name] = "on"
        else:
            daten[name] = str(wert)
    for inline in ctx["inline_admin_formsets"]:
        fs = inline.formset
        for k, v in fs.management_form.initial.items():
            daten[f"{fs.prefix}-{k}"] = str(v)
        for f in fs.initial_forms:
            for name in f.fields:
                wert = f[name].value()
                schluessel = f"{f.prefix}-{name}"
                if wert is None:
                    continue
                if hasattr(wert, "isoformat"):
                    daten[schluessel] = wert.isoformat()
                elif isinstance(wert, bool):
                    if wert:
                        daten[schluessel] = "on"
                elif hasattr(wert, "pk"):
                    daten[schluessel] = str(wert.pk)
                else:
                    daten[schluessel] = str(wert)
        assert isinstance(fs, BaseModelFormSet)
    return daten
