"""
Dynamische Formularfelder für frei definierbare Zusatzfelder.

Verwendung im Admin über ZusatzfelderAdminMixin bzw. ZusatzfelderInlineMixin.
"""
from collections import OrderedDict

from django import forms
from django.contrib.admin.widgets import AdminDateWidget

from portal.rechte import ist_personalverwaltung, ist_verwaltung

from .models import Zusatzfeld


def darf_sehen(user, feld) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser or feld.sichtbarkeit == "alle":
        return True
    if feld.sichtbarkeit == "verwaltung":
        return ist_verwaltung(user) or ist_personalverwaltung(user)
    return ist_personalverwaltung(user)  # "hr"


def sichtbare_felder(user, zielgruppe):
    return [f for f in Zusatzfeld.objects.filter(zielgruppe=zielgruppe, aktiv=True) if darf_sehen(user, f)]


def formfeld(feld: Zusatzfeld):
    gemeinsam = {"label": feld.name, "required": feld.pflicht, "help_text": feld.hilfetext}
    if feld.typ == "langtext":
        return forms.CharField(widget=forms.Textarea(attrs={"rows": 3, "cols": 60}), **gemeinsam)
    if feld.typ == "zahl":
        return forms.DecimalField(max_digits=14, decimal_places=4, **gemeinsam)
    if feld.typ == "datum":
        return forms.DateField(widget=AdminDateWidget, **gemeinsam)
    if feld.typ == "janein":
        gemeinsam["required"] = False  # Pflicht wird in clean() geprüft (Ja/Nein muss gewählt sein)
        return forms.NullBooleanField(widget=forms.NullBooleanSelect, **gemeinsam)
    if feld.typ == "auswahl":
        return forms.ChoiceField(choices=[("", "—")] + [(o, o) for o in feld.optionsliste], **gemeinsam)
    if feld.typ == "mehrfach":
        return forms.MultipleChoiceField(
            choices=[(o, o) for o in feld.optionsliste], widget=forms.CheckboxSelectMultiple, **gemeinsam
        )
    return forms.CharField(max_length=255, widget=forms.TextInput(attrs={"size": 40}), **gemeinsam)


class ZusatzfelderFormMixin:
    """Liest beim Öffnen die gespeicherten Werte ein und schreibt sie beim Prüfen zurück ins JSON-Feld."""

    zusatzfeld_definitionen: list = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        daten = getattr(self.instance, "zusatzfelder", None) or {}
        for f in self.zusatzfeld_definitionen:
            if f.formularname in self.fields:
                self.initial[f.formularname] = f.aus_speicher(daten.get(f.schluessel))

    def clean(self):
        cleaned = super().clean()
        daten = dict(getattr(self.instance, "zusatzfelder", None) or {})  # unsichtbare / inaktive Felder bleiben erhalten
        for f in self.zusatzfeld_definitionen:
            if f.formularname not in self.fields:
                continue
            wert = cleaned.get(f.formularname)
            if f.typ == "janein" and f.pflicht and wert is None:
                self.add_error(f.formularname, "Bitte Ja oder Nein wählen.")
            gespeichert = f.in_speicher(wert)
            if gespeichert is None:
                daten.pop(f.schluessel, None)
            else:
                daten[f.schluessel] = gespeichert
        self.instance.zusatzfelder = daten
        return cleaned


def zusatzform(basis, definitionen):
    attrs = {f.formularname: formfeld(f) for f in definitionen}
    attrs["zusatzfeld_definitionen"] = definitionen
    return type(f"{basis.__name__}MitZusatzfeldern", (ZusatzfelderFormMixin, basis), attrs)


def zusatz_fieldsets(definitionen):
    abschnitte = OrderedDict()
    for f in sorted(definitionen, key=lambda f: (f.abschnitt or "", f.reihenfolge, f.name)):
        abschnitte.setdefault(f.abschnitt or "Weitere Angaben", []).append(f.formularname)
    return [(f"Zusatzfelder – {titel}", {"fields": felder}) for titel, felder in abschnitte.items()]


class ZusatzfelderAdminMixin:
    """Für ModelAdmin-Klassen von Schülerprofil, Personalprofil, Elternprofil."""

    zusatz_zielgruppe = None

    def _zusatz_definitionen(self, request):
        if not hasattr(request, "_zusatzfeld_cache"):
            request._zusatzfeld_cache = {}
        if self.zusatz_zielgruppe not in request._zusatzfeld_cache:
            request._zusatzfeld_cache[self.zusatz_zielgruppe] = sichtbare_felder(request.user, self.zusatz_zielgruppe)
        return request._zusatzfeld_cache[self.zusatz_zielgruppe]

    def get_fieldsets(self, request, obj=None):
        return list(super().get_fieldsets(request, obj)) + zusatz_fieldsets(self._zusatz_definitionen(request))

    def get_form(self, request, obj=None, change=False, **kwargs):
        kwargs["form"] = zusatzform(kwargs.get("form", self.form), self._zusatz_definitionen(request))
        return super().get_form(request, obj, change, **kwargs)

    def get_list_display(self, request):
        spalten = list(super().get_list_display(request))
        for f in self._zusatz_definitionen(request):
            if f.in_liste:
                def spalte(obj, f=f):
                    return f.anzeigewert((obj.zusatzfelder or {}).get(f.schluessel))
                spalte.short_description = f.name
                spalte.__name__ = f.formularname
                spalten.append(spalte)
        return spalten


class ZusatzfelderInlineMixin(ZusatzfelderAdminMixin):
    def get_formset(self, request, obj=None, **kwargs):
        kwargs["form"] = zusatzform(kwargs.get("form", self.form), self._zusatz_definitionen(request))
        return super().get_formset(request, obj, **kwargs)

    def get_form(self, *args, **kwargs):  # Inlines haben kein get_form
        raise NotImplementedError


def anzeige(user, obj, zielgruppe):
    """[(abschnitt, [(name, wert), ...]), ...] für die Lese-Ansicht."""
    daten = getattr(obj, "zusatzfelder", None) or {}
    abschnitte = OrderedDict()
    for f in sorted(sichtbare_felder(user, zielgruppe), key=lambda f: (f.abschnitt or "", f.reihenfolge, f.name)):
        abschnitte.setdefault(f.abschnitt or "Weitere Angaben", []).append((f.name, f.anzeigewert(daten.get(f.schluessel))))
    return list(abschnitte.items())
