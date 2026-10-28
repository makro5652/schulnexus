"""Tests: Excel-Notentabelle herunterladen und hochladen (ab 0.4.11.0)."""
import io
from datetime import date

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import load_workbook

from portal.rechte import personal_von
from sicherung.models import Protokoll
from sicherung.tests import Grundlage

from . import notenimport as I
from . import notentabelle as T
from .models import Bewertungsordner, Leistungsnachweis, Note, Unterricht
from .sperre import gesperrte_schueler


class NotentabelleTest(Grundlage):
    def setUp(self):
        super().setUp()
        p = personal_von(User.objects.get(username="lehrkraft"))
        kandidaten = Unterricht.objects.filter(lehrkraft=p, skala__hoeher_ist_besser=False).select_related(
            "gruppe", "abschnitt", "fach", "skala").order_by("abschnitt__nummer")
        self.u = next(u for u in kandidaten if not gesperrte_schueler(u, list(u.schueler().values_list("pk", flat=True))))
        self.schueler = list(self.u.schueler())
        self.anmelden("lehrkraft")

    # ------------------------------------------------------------ Hilfen
    def vorlage(self):
        r = self.client.get(reverse("notentabelle_vorlage", args=[self.u.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertIn("spreadsheetml", r["Content-Type"])
        return load_workbook(io.BytesIO(r.content))

    def hochladen(self, wb, name="noten.xlsx"):
        puffer = io.BytesIO()
        wb.save(puffer)
        datei = SimpleUploadedFile(name, puffer.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        r = self.client.post(reverse("notentabelle", args=[self.u.pk]), {"aktion": "hochladen", "datei": datei})
        self.assertEqual(r.status_code, 302, getattr(r, "context", None) and r.context["form"].errors)
        return self.client.get(reverse("notentabelle", args=[self.u.pk]))

    def blatt(self, wb):
        return wb[T.BLATT_HJ[self.u.abschnitt.nummer]]

    def freie_spalte(self, ws, bereich="somi"):
        start, ende = (T.SP_S, T.SP_ENDE) if bereich == "somi" else (T.SP_K, T.SP_S - 1)
        for sp in range(start, ende + 1):
            if not any(ws.cell(row=T.ERSTE + i, column=sp).value for i in range(T.ANZAHL)):
                return sp
        self.fail("keine freie Spalte")

    def datum_im_halbjahr(self):
        a = self.u.abschnitt
        return min(max(date.today(), a.beginn), a.ende)

    # ------------------------------------------------------------ Tests
    def test_seite_und_vorlage(self):
        r = self.client.get(reverse("notenuebersicht", args=[self.u.pk]))
        self.assertContains(r, reverse("notentabelle", args=[self.u.pk]))
        r = self.client.get(reverse("notentabelle", args=[self.u.pk]))
        self.assertContains(r, "Notentabelle herunterladen")
        wb = self.vorlage()
        self.assertEqual(wb.sheetnames, ["Anleitung", "Master", "1. Halbjahr", "2. Halbjahr", "Jahresnote", "Erklärung"])
        self.assertEqual(wb["Master"]["B5"].value, self.u.gruppe.name)
        hj1 = wb["1. Halbjahr"]
        namen = [(hj1.cell(row=T.ERSTE + i, column=2).value, hj1.cell(row=T.ERSTE + i, column=3).value) for i in range(len(self.schueler))]
        self.assertEqual(namen, [(s.person.nachname, s.person.rufname or s.person.vorname) for s in self.schueler])
        titel = {self.blatt(wb).cell(row=6, column=sp).value for sp in range(T.SP_K, T.SP_ENDE + 1)}
        for ln in Leistungsnachweis.objects.filter(unterricht=self.u)[:3]:
            self.assertIn(ln.titel, titel)
        self.assertTrue(Protokoll.objects.filter(aktion="notenimport").exists())

    def test_rundreise_neue_spalte_und_aenderung(self):
        wb = self.vorlage()
        ws = self.blatt(wb)
        sp = self.freie_spalte(ws)
        ws.cell(row=6, column=sp, value="Referat Säuren")
        ws.cell(row=7, column=sp, value=self.datum_im_halbjahr())
        ws.cell(row=8, column=sp, value=0.5)
        ws.cell(row=T.ERSTE, column=sp, value="2-")
        ws.cell(row=T.ERSTE + 1, column=sp, value="2,3")       # Dezimalnote → Stufe 2-
        ws.cell(row=T.ERSTE + 2, column=sp, value="e")
        # eine vorhandene Note ändern, Kommentar muss erhalten bleiben
        vorhanden = (Note.objects.filter(leistungsnachweis__unterricht=self.u, stufe__isnull=False, schueler=self.schueler[3],
                                         leistungsnachweis__schluessel__isnull=True)
                     .select_related("leistungsnachweis").first())
        if vorhanden:
            Note.objects.filter(pk=vorhanden.pk).update(kommentar="bleibt")
            for s in range(T.SP_K, T.SP_ENDE + 1):
                if ws.cell(row=6, column=s).value == vorhanden.leistungsnachweis.titel:
                    neu = "6" if vorhanden.stufe.bezeichnung != "6" else "1"
                    ws.cell(row=T.ERSTE + 3, column=s, value=neu)
        r = self.hochladen(wb)
        v = r.context["vorschau"]
        self.assertEqual(v["fehler"], [])
        neu = next(s for s in v["spalten"] if s["titel"] == "Referat Säuren")
        self.assertEqual((neu["aktion"], neu["neu"]), ("neu", 3))
        self.assertContains(r, "Noten übernehmen")
        self.assertEqual(self.client.post(reverse("notentabelle", args=[self.u.pk]), {"aktion": "uebernehmen"}).status_code, 302)
        ln = Leistungsnachweis.objects.get(unterricht=self.u, titel="Referat Säuren")
        self.assertEqual(ln.gewicht, 0.5)
        self.assertEqual(ln.datum, self.datum_im_halbjahr())
        noten = {n.schueler_id: n for n in ln.noten.select_related("stufe")}
        self.assertEqual(noten[self.schueler[0].pk].stufe.bezeichnung, "2-")
        self.assertEqual(noten[self.schueler[1].pk].stufe.bezeichnung, "2-")
        self.assertEqual(noten[self.schueler[2].pk].sonderstatus, "entschuldigt")
        self.assertEqual(len(noten), len(self.schueler))          # Notenzeilen für alle angelegt
        if vorhanden:
            vorhanden.refresh_from_db()
            self.assertIn(vorhanden.stufe.bezeichnung, ("6", "1"))
            self.assertEqual(vorhanden.kommentar, "bleibt")
        self.assertIsNone(self.client.session.get(f"notenimport_{self.u.pk}"))

    def test_erneutes_hochladen_aendert_nichts_und_leere_zellen_loeschen_nicht(self):
        anzahl_ln = Leistungsnachweis.objects.filter(unterricht=self.u).count()
        vorher = {(n.leistungsnachweis_id, n.schueler_id): (n.stufe_id, n.sonderstatus) for n in Note.objects.filter(leistungsnachweis__unterricht=self.u)}
        wb = self.vorlage()
        ws = self.blatt(wb)
        for sp in range(T.SP_K, T.SP_ENDE + 1):          # erste Zeile leeren
            ws.cell(row=T.ERSTE, column=sp, value=None)
        r = self.hochladen(wb)
        v = r.context["vorschau"]
        self.assertEqual(v["fehler"], [])
        self.assertEqual((v["summe"]["neu"], v["summe"]["geaendert"]), (0, 0))
        self.client.post(reverse("notentabelle", args=[self.u.pk]), {"aktion": "uebernehmen"})
        self.assertEqual(Leistungsnachweis.objects.filter(unterricht=self.u).count(), anzahl_ln)
        nachher = {(n.leistungsnachweis_id, n.schueler_id): (n.stufe_id, n.sonderstatus) for n in Note.objects.filter(leistungsnachweis__unterricht=self.u)}
        for k, w in vorher.items():
            self.assertEqual(nachher[k], w)

    def test_falsche_klasse_wird_abgelehnt(self):
        wb = self.vorlage()
        wb["Master"]["B5"] = "5z"
        ws = self.blatt(wb)
        ws.cell(row=T.ERSTE, column=self.freie_spalte(ws), value="1")
        r = self.hochladen(wb)
        self.assertTrue(any("Klasse" in f for f in r.context["vorschau"]["fehler"]))
        self.assertNotContains(r, 'value="uebernehmen"')
        anzahl = Leistungsnachweis.objects.count()
        self.client.post(reverse("notentabelle", args=[self.u.pk]), {"aktion": "uebernehmen"})
        self.assertEqual(Leistungsnachweis.objects.count(), anzahl)

    def test_klasse_ohne_leerzeichen_und_gross_klein(self):
        wb = self.vorlage()
        wb["Master"]["B5"] = " " + self.u.gruppe.name.upper().replace("", " ").strip() + " "
        ws = self.blatt(wb)
        ws.cell(row=T.ERSTE, column=self.freie_spalte(ws), value="1")
        self.assertEqual(self.hochladen(wb).context["vorschau"]["fehler"], [])

    def test_unbekannter_name_wird_ausgelassen(self):
        wb = self.vorlage()
        hj1 = wb["1. Halbjahr"]
        hj1.cell(row=T.ERSTE + 1, column=2, value="Unbekannt")
        ws = self.blatt(wb)
        sp = self.freie_spalte(ws)
        ws.cell(row=6, column=sp, value="Test X")
        ws.cell(row=T.ERSTE, column=sp, value="3")
        ws.cell(row=T.ERSTE + 1, column=sp, value="4")
        r = self.hochladen(wb)
        v = r.context["vorschau"]
        self.assertEqual(v["fehler"], [])
        self.assertTrue(any(z["status"] == "fehlt" for z in v["zeilen"]))
        self.assertIn(str(self.schueler[1].person), v["ohne"])
        self.client.post(reverse("notentabelle", args=[self.u.pk]), {"aktion": "uebernehmen"})
        ln = Leistungsnachweis.objects.get(unterricht=self.u, titel="Test X")
        self.assertEqual(ln.noten.exclude(stufe__isnull=True).count(), 1)

    def test_ungueltige_note_und_datum_blockieren(self):
        wb = self.vorlage()
        ws = self.blatt(wb)
        sp = self.freie_spalte(ws)
        ws.cell(row=T.ERSTE, column=sp, value="x")
        sp2 = self.freie_spalte(ws, "ka")
        ws.cell(row=7, column=sp2, value=date(1999, 1, 1))
        ws.cell(row=T.ERSTE, column=sp2, value="2")
        r = self.hochladen(wb)
        fehler = " ".join(r.context["vorschau"]["fehler"])
        self.assertIn("keine Note dieser Skala", fehler)
        self.assertIn("nicht im Halbjahr", fehler)
        self.assertNotContains(r, 'value="uebernehmen"')

    def test_neuer_ordner_und_gewichte(self):
        wb = self.vorlage()
        nr = self.u.abschnitt.nummer
        wb["Master"]["B17" if nr == 1 else "C17"] = 70
        wb["Master"]["B18" if nr == 1 else "C18"] = 30
        ws = self.blatt(wb)
        sp = self.freie_spalte(ws, "ka")
        ws.cell(row=6, column=sp, value="Klassenarbeit neu")
        ws.cell(row=T.ERSTE, column=sp, value="2")
        self.hochladen(wb)
        r = self.client.post(reverse("notentabelle", args=[self.u.pk]),
                             {"aktion": "uebernehmen", "ordner_ka": "neu", "ordner_somi": "neu", "gewichte": "1"})
        self.assertEqual(r.status_code, 302)
        o = Bewertungsordner.objects.get(unterricht=self.u, eltern=None, name="Klassenarbeiten")
        self.assertEqual(o.gewicht, 70)
        self.assertTrue(Leistungsnachweis.objects.filter(ordner=o, titel="Klassenarbeit neu").exists())

    def test_verwerfen(self):
        wb = self.vorlage()
        ws = self.blatt(wb)
        ws.cell(row=T.ERSTE, column=self.freie_spalte(ws), value="1")
        self.hochladen(wb)
        self.client.post(reverse("notentabelle", args=[self.u.pk]), {"aktion": "verwerfen"})
        self.assertIsNone(self.client.session.get(f"notenimport_{self.u.pk}"))

    def test_keine_excel_datei(self):
        datei = SimpleUploadedFile("x.xlsx", b"kein zip", "application/octet-stream")
        r = self.client.post(reverse("notentabelle", args=[self.u.pk]), {"aktion": "hochladen", "datei": datei})
        self.assertContains(r, "nicht als Excel-Datei")

    def test_nur_mit_recht(self):
        self.anmelden("verwaltung")
        self.assertEqual(self.client.get(reverse("notentabelle", args=[self.u.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse("notentabelle_vorlage", args=[self.u.pk])).status_code, 403)

    def test_allgemeine_vorlage_ohne_kurs(self):
        wb = load_workbook(io.BytesIO(T.erstellen()))
        self.assertEqual(wb["1. Halbjahr"]["B10"].value, "Beispiel")
        self.assertEqual(I.norm(" 9 A "), "9a")

    def test_notenschluessel_wird_nicht_ueberschrieben(self):
        ln = Leistungsnachweis.objects.filter(unterricht=self.u, schluessel__isnull=False).first()
        if ln is None:
            self.skipTest("kein Leistungsnachweis mit Notenschlüssel in den Demodaten")
        n = ln.noten.filter(stufe__isnull=False, schueler=self.schueler[0]).select_related("stufe").first()
        wb = self.vorlage()
        ws = self.blatt(wb)
        sp = next(s for s in range(T.SP_K, T.SP_ENDE + 1) if ws.cell(row=6, column=s).value == ln.titel)
        ws.cell(row=T.ERSTE, column=sp, value="6" if not n or n.stufe.bezeichnung != "6" else "1")
        r = self.hochladen(wb)
        v = r.context["vorschau"]
        self.assertEqual(v["fehler"], [])
        self.assertTrue(any("Notenschlüssel" in w for w in v["warnungen"]))
        self.client.post(reverse("notentabelle", args=[self.u.pk]), {"aktion": "uebernehmen"})
        if n:
            stufe = n.stufe_id
            n.refresh_from_db()
            self.assertEqual(n.stufe_id, stufe)
