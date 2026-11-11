"""Tests: Suchauswahl statt Hin-und-her-Listen und Schülerauswahl nur aus der Klasse (ab 0.4.10.0)."""
from django import forms
from django.contrib import admin
from django.test import SimpleTestCase
from django.urls import reverse

from foerderung.models import Foerderplan
from portal.suchauswahl import Suchauswahl, SuchauswahlAdminMixin
from sicherung.tests import Grundlage
from stammdaten.models import Personalprofil
from zeugnisse.models import Konferenz
from zeugnisse.noten import klassen_mitglieder
from zeugnisse.rechte import konferenz_kandidaten


class WidgetTest(SimpleTestCase):
    def test_darstellung(self):
        w = Suchauswahl(choices=[("1", "Anna Abel (ABE)"), ("2", "Bert Brandt")], vorschlaege=[2],
                        vorschlag_titel="Lehrkräfte der Klasse", alle_text="Alle übernehmen")
        html = w.render("teilnehmende", ["1"], attrs={"id": "id_teilnehmende"})
        self.assertIn('class="suchauswahl" data-suchauswahl', html)
        self.assertIn('<select name="teilnehmende" id="id_teilnehmende" multiple', html)
        self.assertIn('<option value="1" selected>Anna Abel (ABE)</option>', html)
        self.assertIn('<option value="2" data-vorschlag="1">Bert Brandt</option>', html)
        self.assertIn('data-t-vorschlaege="Lehrkräfte der Klasse"', html)
        self.assertIn('data-t-alle="Alle übernehmen"', html)
        self.assertIn('data-t-eingabe="Name oder Kürzel eingeben …"', html)
        self.assertIn("suchauswahl.js", str(w.media))
        self.assertIn("suchauswahl.css", str(w.media))

    def test_ohne_vorschlaege_und_ohne_javascript_nutzbar(self):
        html = Suchauswahl(choices=[("1", "A")]).render("x", None)
        self.assertNotIn("data-vorschlag", html)
        self.assertIn("<select", html)   # ohne JavaScript bleibt die normale Mehrfachauswahl

    def test_einstellung_im_formular(self):
        class F(forms.Form):
            wahl = forms.MultipleChoiceField(choices=[("a", "A"), ("b", "B")], widget=Suchauswahl)

        f = F({"wahl": ["a", "b"]})
        self.assertTrue(f.is_valid())
        self.assertEqual(f.cleaned_data["wahl"], ["a", "b"])


class KonferenzAnwesenheitTest(Grundlage):
    def setUp(self):
        super().setUp()
        self.k = Konferenz.objects.select_related("klasse", "abschnitt").first()
        self.kandidaten = konferenz_kandidaten(self.k)
        self.fremd = Personalprofil.objects.filter(aktiv=True).exclude(pk__in=self.kandidaten).first()

    def test_portal_zeigt_suchauswahl_mit_vorschlaegen(self):
        self.assertTrue(self.kandidaten)
        self.anmelden("mittelstufe")
        r = self.client.get(reverse("konferenz", args=[self.k.pk]))
        self.assertContains(r, "data-suchauswahl")
        self.assertContains(r, "suchauswahl.js")
        self.assertContains(r, 'data-t-alle="Alle Lehrkräfte der Klasse übernehmen"')
        self.assertNotContains(r, 'type="checkbox" name="teilnehmende"')
        feld = r.context["form"].fields["teilnehmende"]
        ids = set(feld.queryset.values_list("pk", flat=True))
        self.assertTrue(self.kandidaten <= ids)
        self.assertIn(self.fremd.pk, ids)                     # auch Gäste (z. B. Schulleitung) eintragbar
        self.assertEqual(feld.widget.vorschlaege, {str(i) for i in self.kandidaten})

    def test_gast_eintragen_und_speichern(self):
        self.anmelden("mittelstufe")
        r = self.client.get(reverse("konferenz", args=[self.k.pk]))
        daten = {"aktion": "speichern", "art": self.k.art, "datum": "2027-01-22",
                 "teilnehmende": sorted(self.kandidaten) + [self.fremd.pk]}
        for zl in r.context["zeilen"]:
            daten[f"b-{zl['s'].pk}-entscheidung"] = ""
        r = self.client.post(reverse("konferenz", args=[self.k.pk]), daten)
        self.assertEqual(r.status_code, 302)
        self.assertEqual(set(self.k.teilnehmende.values_list("pk", flat=True)), self.kandidaten | {self.fremd.pk})

    def test_ausgeschiedene_bleiben_eingetragen(self):
        p = Personalprofil.objects.filter(pk__in=self.kandidaten).first()
        self.k.teilnehmende.add(p)
        Personalprofil.objects.filter(pk=p.pk).update(aktiv=False)
        self.anmelden("mittelstufe")
        r = self.client.get(reverse("konferenz", args=[self.k.pk]))
        self.assertIn(p.pk, set(r.context["form"].fields["teilnehmende"].queryset.values_list("pk", flat=True)))

    def test_verwaltung_suchauswahl_und_nur_klasse(self):
        self.anmelden("it")
        r = self.client.get(reverse("admin:zeugnisse_konferenz_change", args=[self.k.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "data-suchauswahl")
        self.assertNotContains(r, "SelectFilter2.js")
        self.assertNotContains(r, 'class="selectfilter')
        self.assertNotContains(r, "gedrückt")  # kein Hinweis „Strg gedrückt halten …“ (ab 0.6.0 steht „Strg+K“ im Menüband)
        formset = r.context["inline_admin_formsets"][0].formset
        auswahl = set(formset.empty_form.fields["schueler"].queryset.values_list("pk", flat=True))
        klasse = {s.pk for s in klassen_mitglieder(self.k.klasse, self.k.abschnitt)}
        self.assertEqual(auswahl, klasse)
        widget = r.context["adminform"].form.fields["teilnehmende"].widget
        self.assertEqual(widget.widget.vorschlaege, {str(i) for i in self.kandidaten})

    def test_verwaltung_neue_konferenz_ohne_schuelerliste(self):
        self.anmelden("it")
        r = self.client.get(reverse("admin:zeugnisse_konferenz_add"))
        self.assertEqual(r.status_code, 200)
        formset = r.context["inline_admin_formsets"][0].formset
        self.assertFalse(formset.empty_form.fields["schueler"].queryset.exists())
        self.assertContains(r, "Erst die Konferenz speichern")


class VerwaltungMehrfachauswahlTest(Grundlage):
    def test_keine_hin_und_her_listen_mehr(self):
        """Alle früheren filter_horizontal-Felder der Schulverwaltung nutzen die Suchauswahl."""
        offen = []
        for model, ma in admin.site._registry.items():
            if model._meta.app_label in ("auth",):
                continue
            if ma.filter_horizontal or ma.filter_vertical:
                offen.append(type(ma).__name__)
            m2m = [f for f in model._meta.many_to_many if f.name not in (ma.autocomplete_fields or [])]
            if m2m and not isinstance(ma, SuchauswahlAdminMixin):
                offen.append(f"{type(ma).__name__}: {[f.name for f in m2m]}")
        self.assertEqual(offen, [])

    def test_seiten_laden(self):
        self.anmelden("it")
        for model, ma in admin.site._registry.items():
            if not isinstance(ma, SuchauswahlAdminMixin):
                continue
            obj = model.objects.first()
            name = f"admin:{model._meta.app_label}_{model._meta.model_name}"
            r = self.client.get(reverse(name + "_add"))
            self.assertEqual(r.status_code, 200, name)
            self.assertContains(r, "data-suchauswahl", msg_prefix=name)
            if obj:
                r = self.client.get(reverse(name + "_change", args=[obj.pk]))
                self.assertEqual(r.status_code, 200, name)   # Felder können je nach Datensatz ausgeblendet sein

    def test_foerderplan_schlaegt_unterrichtende_vor(self):
        plan = Foerderplan.objects.select_related("schueler").first()
        if plan is None:
            self.skipTest("kein Förderplan in den Demodaten")
        self.anmelden("it")
        r = self.client.get(reverse("admin:foerderung_foerderplan_change", args=[plan.pk]))
        self.assertEqual(r.status_code, 200)
        widget = r.context["adminform"].form.fields["beteiligte"].widget.widget
        self.assertTrue(widget.vorschlaege)
        self.assertContains(r, "Alle unterrichtenden Lehrkräfte übernehmen")
