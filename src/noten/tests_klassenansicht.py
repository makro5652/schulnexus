"""Tests: Noten nach Klasse – Klassenauswahl, Klassenübersicht, bearbeitbare Notentabelle (ab 0.4.12.0)."""
from django.contrib.auth.models import User
from django.urls import reverse

from portal.rechte import personal_von
from sicherung.tests import Grundlage
from stammdaten.models import Gruppe, Mitgliedschaft

from . import eingabe as E
from .models import Leistungsnachweis, Note, Unterricht
from .sperre import gesperrte_schueler


class NotenNachKlasseTest(Grundlage):
    def setUp(self):
        super().setUp()
        self.lk = personal_von(User.objects.get(username="lehrkraft"))
        self.u = (Unterricht.objects.filter(lehrkraft=self.lk, gruppe__name="9a", fach__kuerzel="CH")
                  .select_related("gruppe", "abschnitt").order_by("abschnitt__nummer").first())
        self.klasse = self.u.gruppe
        self.anmelden("lehrkraft")

    def url(self, **k):
        teile = {"abschnitt": self.u.abschnitt_id, "klasse": self.klasse.pk, **k}
        return reverse("noten_klassen") + "?" + "&".join(f"{a}={b}" for a, b in teile.items())

    def ln_ohne_schluessel(self):
        return Leistungsnachweis.objects.filter(unterricht=self.u, schluessel__isnull=True).first()

    def freie_zeile(self, ln):
        gesperrt = gesperrte_schueler(self.u, [s.pk for s in self.u.schueler()])
        return next(s for s in self.u.schueler() if s.pk not in gesperrt)

    # ------------------------------------------------------------
    def test_klassen_und_uebersicht(self):
        r = self.client.get(reverse("noten_klassen") + f"?abschnitt={self.u.abschnitt_id}")
        self.assertEqual(r.status_code, 200)
        self.assertIn(self.klasse, r.context["klassen"])
        r = self.client.get(self.url())
        kurse = [x["u"] for x in r.context["kurse"]]
        self.assertIn(self.u, kurse)
        self.assertContains(r, self.u.lehrkraft.person.anzeigename)
        ue = r.context["uebersicht"]
        self.assertIsNotNone(ue)
        self.assertIn(self.u.fach, [f["fach"] for f in ue["spalten"]])
        self.assertEqual(len(ue["zeilen"]), len([z for z in ue["zeilen"]]))
        # eine Zeile je Schüler:in, eine Spalte je Fach – nicht jede Einzelnote
        self.assertEqual(len(ue["zeilen"][0]["zellen"]), len(ue["spalten"]))

    def test_kurs_bearbeiten_speichern(self):
        ln = self.ln_ohne_schluessel()
        s = self.freie_zeile(ln)
        n = Note.objects.filter(leistungsnachweis=ln, schueler=s).first()
        alt = E.anzeige(n) if n else ""
        neu = "5" if alt != "5" else "4"
        r = self.client.get(self.url(kurs=self.u.pk))
        self.assertContains(r, f'name="n_{ln.pk}_{s.pk}"')
        self.assertContains(r, "Excel-Tabelle hochladen")
        r = self.client.post(self.url(kurs=self.u.pk), {"aktion": "speichern", f"n_{ln.pk}_{s.pk}": neu, f"o_{ln.pk}_{s.pk}": alt})
        self.assertEqual(r.status_code, 302)
        n = Note.objects.select_related("stufe").get(leistungsnachweis=ln, schueler=s)
        self.assertEqual(n.stufe.bezeichnung, neu)

    def test_ungueltig_speichert_nichts(self):
        ln = self.ln_ohne_schluessel()
        schueler = [s for s in self.u.schueler() if s.pk not in gesperrte_schueler(self.u, [x.pk for x in self.u.schueler()])][:2]
        vorher = {s.pk: E.anzeige(Note.objects.filter(leistungsnachweis=ln, schueler=s).first()) for s in schueler}
        daten = {"aktion": "speichern"}
        daten[f"n_{ln.pk}_{schueler[0].pk}"], daten[f"o_{ln.pk}_{schueler[0].pk}"] = "1", vorher[schueler[0].pk] or ""
        daten[f"n_{ln.pk}_{schueler[1].pk}"], daten[f"o_{ln.pk}_{schueler[1].pk}"] = "xyz", vorher[schueler[1].pk] or ""
        if vorher[schueler[0].pk] == "1":
            daten[f"n_{ln.pk}_{schueler[0].pk}"] = "2"
        r = self.client.post(self.url(kurs=self.u.pk), daten)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "nicht gültig")
        self.assertContains(r, 'value="xyz"')
        for s in schueler:
            self.assertEqual(E.anzeige(Note.objects.filter(leistungsnachweis=ln, schueler=s).first()), vorher[s.pk])

    def test_konflikt_wird_nicht_ueberschrieben(self):
        ln = self.ln_ohne_schluessel()
        s = self.freie_zeile(ln)
        vorher = E.anzeige(Note.objects.filter(leistungsnachweis=ln, schueler=s).select_related("stufe", "leistungsnachweis").first())
        neu = "1" if vorher != "1" else "2"
        r = self.client.post(self.url(kurs=self.u.pk), {"aktion": "speichern", f"n_{ln.pk}_{s.pk}": neu,
                                                        f"o_{ln.pk}_{s.pk}": "3-" if vorher != "3-" else "4"}, follow=True)
        self.assertContains(r, "nicht überschrieben")
        nachher = E.anzeige(Note.objects.filter(leistungsnachweis=ln, schueler=s).select_related("stufe", "leistungsnachweis").first())
        self.assertEqual(nachher, vorher)

    def test_notenschluessel_und_sperre_nur_lesen(self):
        r = self.client.get(self.url(kurs=self.u.pk))
        tabelle = r.context["tabelle"]
        for z in tabelle["zeilen"]:
            for sp, c in zip(tabelle["spalten"], z["zellen"]):
                if sp["nur_lesen"] or z["gesperrt"]:
                    self.assertFalse(c["bearbeitbar"])
        ln = Leistungsnachweis.objects.filter(unterricht=self.u, schluessel__isnull=False).first()
        if ln:
            s = next(iter(self.u.schueler()))
            r = self.client.post(self.url(kurs=self.u.pk), {"aktion": "speichern", f"n_{ln.pk}_{s.pk}": "1", f"o_{ln.pk}_{s.pk}": ""})
            self.assertEqual(r.status_code, 302)
            self.assertFalse(Note.objects.filter(leistungsnachweis=ln, schueler=s, stufe__bezeichnung="1", erreichte_be__isnull=True).exists())

    def test_nur_lesen_ohne_recht(self):
        self.anmelden("verwaltung")
        r = self.client.get(self.url(kurs=self.u.pk))
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.context["tabelle"]["darf_eintragen"])
        self.assertNotContains(r, 'type="text" name="n_')
        ln = self.ln_ohne_schluessel()
        s = next(iter(self.u.schueler()))
        r = self.client.post(self.url(kurs=self.u.pk), {"aktion": "speichern", f"n_{ln.pk}_{s.pk}": "1", f"o_{ln.pk}_{s.pk}": ""})
        self.assertEqual(r.status_code, 403)

    def test_lerngruppe_erscheint_bei_der_klasse(self):
        kurs = Gruppe.objects.create(schuljahr=self.klasse.schuljahr, name="9 Spanisch", typ=Gruppe.LERNGRUPPE)
        s = Mitgliedschaft.objects.filter(gruppe=self.klasse).first().schueler
        Mitgliedschaft.objects.create(gruppe=kurs, schueler=s, von=self.u.abschnitt.beginn)
        from stammdaten.models import Fach

        fach = Fach.objects.exclude(pk=self.u.fach_id).first()
        lg = Unterricht.objects.create(abschnitt=self.u.abschnitt, gruppe=kurs, fach=fach, lehrkraft=self.lk, skala=self.u.skala)
        r = self.client.get(self.url())
        eintrag = next(x for x in r.context["kurse"] if x["u"] == lg)
        self.assertTrue(eintrag["lerngruppe"])
        self.assertContains(r, "Lerngruppe")

    def test_excel_hochladen_kehrt_zurueck(self):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from openpyxl import load_workbook

        from . import notentabelle as T

        wb = load_workbook(io.BytesIO(self.client.get(reverse("notentabelle_vorlage", args=[self.u.pk])).content))
        ws = wb[T.BLATT_HJ[self.u.abschnitt.nummer]]
        sp = next(k for k in range(T.SP_S, T.SP_ENDE + 1) if not any(ws.cell(row=T.ERSTE + i, column=k).value for i in range(T.ANZAHL)))
        ws.cell(row=6, column=sp, value="Aus Excel")
        gesperrt = gesperrte_schueler(self.u, [x.pk for x in self.u.schueler()])
        zeile = next(i for i, x in enumerate(self.u.schueler()) if x.pk not in gesperrt)
        ws.cell(row=T.ERSTE + zeile, column=sp, value="2")
        puffer = io.BytesIO()
        wb.save(puffer)
        zurueck = self.url(kurs=self.u.pk)
        self.client.post(reverse("notentabelle", args=[self.u.pk]), {
            "aktion": "hochladen", "weiter": zurueck, "datei": SimpleUploadedFile("t.xlsx", puffer.getvalue())})
        r = self.client.post(reverse("notentabelle", args=[self.u.pk]), {"aktion": "uebernehmen"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], zurueck)
        self.assertTrue(Leistungsnachweis.objects.filter(unterricht=self.u, titel="Aus Excel").exists())

    def test_fremde_weiterleitung_wird_ignoriert(self):
        import io

        from django.core.files.uploadedfile import SimpleUploadedFile
        from openpyxl import load_workbook

        from . import notentabelle as T

        wb = load_workbook(io.BytesIO(self.client.get(reverse("notentabelle_vorlage", args=[self.u.pk])).content))
        puffer = io.BytesIO()
        wb.save(puffer)
        self.client.post(reverse("notentabelle", args=[self.u.pk]), {
            "aktion": "hochladen", "weiter": "https://boese.example/", "datei": SimpleUploadedFile("t.xlsx", puffer.getvalue())})
        self.assertNotIn("weiter", self.client.session.get(f"notenimport_{self.u.pk}", {}))
        self.assertTrue(T.ANZAHL)
