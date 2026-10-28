"""Tests: Zeugnisnoten aus der Excel-Notentabelle und der Klassenübersicht festsetzen (ab 0.4.13.0)."""
import io

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import load_workbook

from portal.rechte import personal_von
from sicherung.tests import Grundlage

from . import notentabelle as T
from . import zeugnisnoten as Z
from .models import Note, Unterricht, Zeugnisnote
from .sperre import gesperrte_schueler


class ZeugnisnoteUebernahmeTest(Grundlage):
    def setUp(self):
        super().setUp()
        p = personal_von(User.objects.get(username="lehrkraft"))
        kandidaten = Unterricht.objects.filter(lehrkraft=p, skala__hoeher_ist_besser=False).select_related(
            "gruppe", "abschnitt", "fach", "skala").order_by("abschnitt__nummer")
        self.u = next(u for u in kandidaten if not gesperrte_schueler(u, list(u.schueler().values_list("pk", flat=True)))
                      and not u.mit_jahresnote
                      and Note.objects.filter(leistungsnachweis__unterricht=u).exists())
        self.schueler = list(self.u.schueler())
        Zeugnisnote.objects.filter(unterricht=self.u).delete()
        self.stufen = Z.ganze_stufen(self.u.skala)
        self.anmelden("lehrkraft")

    def mit_einzelnoten(self):
        return [s for s in self.schueler if Note.objects.filter(leistungsnachweis__unterricht=self.u, schueler=s).exists()]

    def hochladen(self, wb):
        puffer = io.BytesIO()
        wb.save(puffer)
        datei = SimpleUploadedFile("n.xlsx", puffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        r = self.client.post(reverse("notentabelle", args=[self.u.pk]), {"aktion": "hochladen", "datei": datei})
        self.assertEqual(r.status_code, 302)
        return self.client.get(reverse("notentabelle", args=[self.u.pk]))

    def vorlage(self):
        r = self.client.get(reverse("notentabelle_vorlage", args=[self.u.pk]))
        return load_workbook(io.BytesIO(r.content))

    def zn(self, s):
        return Zeugnisnote.objects.filter(unterricht=self.u, schueler=s).select_related("stufe").first()

    # ------------------------------------------------------------ Excel
    def test_excel_uebernimmt_festgesetzte_zeugnisnoten(self):
        a, b, c = self.mit_einzelnoten()[:3]
        wb = self.vorlage()
        ws = wb[T.BLATT_HJ[self.u.abschnitt.nummer]]
        zeile = {s.pk: T.ERSTE + i for i, s in enumerate(self.schueler)}
        ws.cell(row=zeile[a.pk], column=T.ERG + 5, value=2)
        ws.cell(row=zeile[b.pk], column=T.ERG + 5, value="4")
        ws.cell(row=zeile[c.pk], column=T.ERG + 5, value="nb")
        r = self.hochladen(wb)
        v = r.context["vorschau"]
        self.assertEqual(v["fehler"], [])
        self.assertEqual(v["zeugnis"]["summe"]["neu"], 3)
        self.assertContains(r, "Zeugnisnoten (festgesetzt)")
        r = self.client.post(reverse("notentabelle", args=[self.u.pk]), {"aktion": "uebernehmen"}, follow=True)
        self.assertContains(r, "3 Zeugnisnoten festgesetzt")
        self.assertEqual(self.zn(a).stufe.bezeichnung, "2")
        self.assertEqual(self.zn(b).stufe.bezeichnung, "4")
        self.assertEqual(self.zn(c).vermerk, "nb")
        self.assertEqual({self.zn(x).quelle for x in (a, b, c)}, {"excel"})
        self.assertIsNotNone(self.zn(a).vorschlag)

    def test_excel_leere_zelle_und_gleiche_note_aendern_nichts(self):
        a = self.mit_einzelnoten()[0]
        Zeugnisnote.objects.create(unterricht=self.u, schueler=a, stufe=self.stufen[3], quelle="")
        wb = self.vorlage()
        ws = wb[T.BLATT_HJ[self.u.abschnitt.nummer]]
        ws.cell(row=T.ERSTE + self.schueler.index(a), column=T.ERG + 5, value=3)       # gleich
        r = self.hochladen(wb)
        self.assertEqual(r.context["vorschau"]["zeugnis"]["summe"]["gleich"], 1)
        self.client.post(reverse("notentabelle", args=[self.u.pk]), {"aktion": "uebernehmen"})
        self.assertEqual(self.zn(a).quelle, "")                                       # nicht neu gesetzt
        wb = self.vorlage()
        r = self.hochladen(wb)                                                        # keine Zeugnisnote in der Datei
        self.assertEqual(r.context["vorschau"]["zeugnis"]["zeilen"], [])
        self.client.post(reverse("notentabelle", args=[self.u.pk]), {"aktion": "uebernehmen"})
        self.assertEqual(self.zn(a).stufe.bezeichnung, "3")

    def test_excel_ungueltige_zeugnisnote_blockiert(self):
        wb = self.vorlage()
        ws = wb[T.BLATT_HJ[self.u.abschnitt.nummer]]
        ws.cell(row=T.ERSTE, column=T.ERG + 5, value=7)
        r = self.hochladen(wb)
        self.assertTrue(any("Zeugnisnote" in f for f in r.context["vorschau"]["fehler"]))
        self.assertNotContains(r, 'value="uebernehmen"')

    def test_excel_ohne_einzelnoten_wird_nicht_gesetzt(self):
        leer = next((s for s in self.schueler if s not in self.mit_einzelnoten()), None)
        if leer is None:
            Note.objects.filter(leistungsnachweis__unterricht=self.u, schueler=self.schueler[-1]).delete()
            leer = self.schueler[-1]
        wb = self.vorlage()
        ws = wb[T.BLATT_HJ[self.u.abschnitt.nummer]]
        ws.cell(row=T.ERSTE + self.schueler.index(leer), column=T.ERG + 5, value=3)
        r = self.hochladen(wb)
        self.assertEqual(r.context["vorschau"]["zeugnis"]["summe"]["fehler"], 1)
        self.client.post(reverse("notentabelle", args=[self.u.pk]), {"aktion": "uebernehmen"})
        self.assertIsNone(self.zn(leer))

    def test_excel_zeugnisnote_ohne_recht_nicht_uebernommen(self):
        from . import notenimport as I

        a = self.mit_einzelnoten()[0]
        wb = self.vorlage()
        ws = wb[T.BLATT_HJ[self.u.abschnitt.nummer]]
        ws.cell(row=T.ERSTE + self.schueler.index(a), column=T.ERG + 5, value=2)
        puffer = io.BytesIO()
        wb.save(puffer)
        tabelle = I.lesen(SimpleUploadedFile("n.xlsx", puffer.getvalue()))
        v = I.pruefen(self.u, tabelle, zeugnis_darf=False)
        self.assertEqual(v["zeugnis"]["zeilen"], [])
        self.assertTrue(any("nicht übernommen" in w for w in v["warnungen"]))
        I.uebernehmen(self.u, tabelle, {}, zeugnis_darf=False)
        self.assertIsNone(self.zn(a))

    # ------------------------------------------------------------ Klassenübersicht
    def uebersicht_post(self, felder):
        url = reverse("noten_klassen") + f"?abschnitt={self.u.abschnitt_id}&klasse={self.u.gruppe_id}"
        return self.client.post(url, {"aktion": "zeugnis", **felder}, follow=True)

    def test_klassenuebersicht_zeigt_auswahl_und_speichert(self):
        a = self.mit_einzelnoten()[0]
        url = reverse("noten_klassen") + f"?abschnitt={self.u.abschnitt_id}&klasse={self.u.gruppe_id}"
        r = self.client.get(url)
        self.assertContains(r, f'name="zn_{self.u.pk}_{a.pk}"')
        r = self.uebersicht_post({f"zn_{self.u.pk}_{a.pk}": "3", f"zo_{self.u.pk}_{a.pk}": ""})
        self.assertContains(r, "1 Zeugnisnote festgesetzt")
        z = self.zn(a)
        self.assertEqual((z.stufe.bezeichnung, z.quelle), ("3", "klasse"))
        # Auswahl zeigt jetzt den Wert und die Herkunft
        r = self.client.get(url)
        self.assertContains(r, "in der Klassenübersicht festgesetzt")
        # unverändert → nichts passiert
        r = self.uebersicht_post({f"zn_{self.u.pk}_{a.pk}": "3", f"zo_{self.u.pk}_{a.pk}": "3"})
        self.assertContains(r, "Keine Änderungen")
        # leeren löscht
        r = self.uebersicht_post({f"zn_{self.u.pk}_{a.pk}": "", f"zo_{self.u.pk}_{a.pk}": "3"})
        self.assertIsNone(self.zn(a))

    def test_klassenuebersicht_konflikt_wird_nicht_ueberschrieben(self):
        a = self.mit_einzelnoten()[0]
        Zeugnisnote.objects.create(unterricht=self.u, schueler=a, stufe=self.stufen[2])
        r = self.uebersicht_post({f"zn_{self.u.pk}_{a.pk}": "5", f"zo_{self.u.pk}_{a.pk}": ""})
        self.assertContains(r, "inzwischen von anderer Seite geändert")
        self.assertEqual(self.zn(a).stufe.bezeichnung, "2")

    def test_klassenuebersicht_ungueltig_und_ohne_einzelnoten(self):
        a = self.mit_einzelnoten()[0]
        r = self.uebersicht_post({f"zn_{self.u.pk}_{a.pk}": "9", f"zo_{self.u.pk}_{a.pk}": ""})
        self.assertContains(r, "keine Zeugnisnote")
        self.assertIsNone(self.zn(a))

    # ------------------------------------------------------------ Einzelnoten: Hinweis
    def test_einzelnoten_zeigen_hinweis_auf_herkunft(self):
        a = self.mit_einzelnoten()[0]
        Zeugnisnote.objects.create(unterricht=self.u, schueler=a, stufe=self.stufen[2], quelle="excel")
        url = reverse("noten_klassen") + f"?abschnitt={self.u.abschnitt_id}&klasse={self.u.gruppe_id}&kurs={self.u.pk}"
        r = self.client.get(url)
        self.assertContains(r, "aus der Excel-Notentabelle übernommen")
        self.assertContains(r, "Sie gelten für das Zeugnis")
        self.assertEqual(r.context["tabelle"]["zeilen"][self.schueler.index(a)]["zeugnisnote"], "2")

    def test_zeugnisnoten_seite_setzt_herkunft_zurueck(self):
        a = self.mit_einzelnoten()[0]
        Zeugnisnote.objects.create(unterricht=self.u, schueler=a, stufe=self.stufen[2], quelle="excel")
        url = reverse("zeugnis_unterricht", args=[self.u.pk])
        felder = {"aktion": "noten"}
        for s in self.schueler:
            z = self.zn(s)
            felder[f"note-{s.pk}"] = str(z.stufe_id) if z else ""
        felder[f"note-{a.pk}"] = str(self.stufen[4].pk)
        self.client.post(url, felder)
        self.assertEqual((self.zn(a).stufe.bezeichnung, self.zn(a).quelle), ("4", ""))
