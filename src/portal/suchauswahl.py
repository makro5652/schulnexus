"""
Suchauswahl (ab 0.4.10.0): Mehrfachauswahl mit Suchfeld, Vorschlägen und aufklappbarer Liste.

Ersetzt die Auswahl mit zwei Listen zum Hin- und Herschieben (filter_horizontal) und lange Ankreuzlisten:
  - Namen oder Kürzel tippen, mit Pfeiltasten wählen, Tab oder Enter übernimmt; die Auswahl erscheint als Marken
    mit Entfernen-Knopf.
  - „Liste öffnen“ zeigt alle Einträge in einem Overlay zum Anklicken, mit Suchfeld.
  - Optional „Vorschläge“ (z. B. die Lehrkräfte der Klasse) stehen oben und lassen sich gesammelt übernehmen.

Ohne JavaScript bleibt die gewöhnliche Mehrfachauswahl sichtbar; gespeichert wird immer über das <select>.
"""
from django import forms
from django.forms.utils import flatatt
from django.utils.html import format_html
from django.utils.translation import gettext as _


class Suchauswahl(forms.SelectMultiple):
    class Media:
        js = ["suchauswahl.js"]
        css = {"all": ["suchauswahl.css"]}

    def __init__(self, attrs=None, choices=(), vorschlaege=(), vorschlag_titel=None, alle_text=None):
        super().__init__(attrs, choices)
        self.vorschlaege = {str(v) for v in vorschlaege}
        self.vorschlag_titel = vorschlag_titel
        self.alle_text = alle_text

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        if str(value) in self.vorschlaege:
            option["attrs"]["data-vorschlag"] = "1"
        return option

    def texte(self):
        return {
            "eingabe": _("Name oder Kürzel eingeben …"),
            "hinweis": _("Pfeiltasten wählen aus, Tab oder Enter übernimmt."),
            "liste": _("Liste öffnen"),
            "fertig": _("Fertig"),
            "entfernen": _("entfernen"),
            "keine": _("Keine Treffer"),
            "suche": _("In der Liste suchen"),
            "zahl": _("Ausgewählt: %n"),
            "leer": _("Noch niemand ausgewählt."),
            "vorschlaege": str(self.vorschlag_titel or _("Vorschläge")),
            "weitere": _("Weitere"),
            "alle": str(self.alle_text or _("Alle Vorschläge übernehmen")),
        }

    def render(self, name, value, attrs=None, renderer=None):
        html = super().render(name, value, attrs, renderer)
        daten = {f"data-t-{k}": v for k, v in self.texte().items()}
        return format_html('<div class="suchauswahl" data-suchauswahl{}>{}</div>', flatatt(daten), html)


class SuchauswahlAdminMixin:
    """Verwaltungsoberfläche: Mehrfachauswahl-Felder als Suchauswahl statt Hin-und-her-Listen (ab 0.4.10.0).

    Vorschläge je Feld liefert optional `suchauswahl_vorschlaege(request, db_field)` (Menge von Primärschlüsseln),
    Überschriften `suchauswahl_texte` = {Feldname: (Vorschlagstitel, Text für „alle übernehmen“)}.
    """

    suchauswahl_texte = {}

    def suchauswahl_vorschlaege(self, request, db_field):
        return set()

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if ("widget" not in kwargs and db_field.name not in self.get_autocomplete_fields(request)
                and db_field.name not in self.raw_id_fields):
            titel, alle = self.suchauswahl_texte.get(db_field.name, (None, None))
            kwargs["widget"] = Suchauswahl(vorschlaege=self.suchauswahl_vorschlaege(request, db_field),
                                           vorschlag_titel=titel, alle_text=alle)
        feld = super().formfield_for_manytomany(db_field, request, **kwargs)
        if feld is not None and isinstance(feld.widget, Suchauswahl):
            feld.help_text = db_field.help_text   # ohne „Strg gedrückt halten …“
        return feld
