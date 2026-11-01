"""Notenregeln für Schulleitung und Stellvertretung: Klausuren je Fach (ab 0.4.8.0), Zeugnisnote ohne Einzelnoten (ab 0.4.8.1)."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext, ngettext
from django.views.decorators.http import require_POST

from sicherung.models import Protokoll
from stammdaten.models import Fach

from . import rechte
from .models import Klausurregel, Zeugnisnotenfreigabe


class RegelForm(forms.ModelForm):
    class Meta:
        model = Klausurregel
        fields = ["faecher", "jahrgang_von", "jahrgang_bis", "anteil_klausur", "name_klausur", "name_mitarbeit",
                  "max_klausuren", "max_mitarbeit", "bemerkung"]
        widgets = {
            "faecher": forms.CheckboxSelectMultiple,
            "jahrgang_von": forms.NumberInput(attrs={"min": 1, "max": 13}),
            "jahrgang_bis": forms.NumberInput(attrs={"min": 1, "max": 13}),
            "anteil_klausur": forms.TextInput(attrs={"inputmode": "decimal", "size": 5}),
            "max_klausuren": forms.NumberInput(attrs={"min": 0, "max": 20}),
            "max_mitarbeit": forms.NumberInput(attrs={"min": 0, "max": 99}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["faecher"].queryset = Fach.objects.order_by("reihenfolge", "name")
        self.fields["faecher"].label_from_instance = lambda f: f.lokal_name
        self.fields["anteil_klausur"].localize = True

    def clean(self):
        daten = super().clean()
        von, bis, faecher = daten.get("jahrgang_von"), daten.get("jahrgang_bis"), daten.get("faecher")
        if von and bis and faecher:
            andere = Klausurregel.objects.exclude(pk=self.instance.pk).filter(
                faecher__in=faecher, jahrgang_von__lte=bis, jahrgang_bis__gte=von).distinct()
            for r in andere:
                doppelt = ", ".join(f.lokal_name for f in r.faecher.all() if f in faecher)
                raise ValidationError(gettext("Für %(f)s gibt es in diesen Jahrgängen schon eine Regel (%(r)s).") % {"f": doppelt, "r": r})
        return daten


class FreigabeForm(forms.ModelForm):
    class Meta:
        model = Zeugnisnotenfreigabe
        fields = ["faecher", "jahrgang_von", "jahrgang_bis", "bemerkung"]
        widgets = {
            "faecher": forms.CheckboxSelectMultiple,
            "jahrgang_von": forms.NumberInput(attrs={"min": 1, "max": 13}),
            "jahrgang_bis": forms.NumberInput(attrs={"min": 1, "max": 13}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, prefix="fg", **kwargs)
        self.fields["faecher"].queryset = Fach.objects.order_by("reihenfolge", "name")
        self.fields["faecher"].label_from_instance = lambda f: f.lokal_name


def _betroffen(regel):
    heute = timezone.localdate()
    return {u.pk: u for u in regel.unterrichte().filter(abschnitt__ende__gte=heute)}


def neu_anwenden(unterrichte):
    """Wendet auf jeden Unterricht die jetzt gültige Regel an bzw. hebt die Vorgabe auf. Gibt (Kurse, verschobene Ordner) zurück."""
    n = verschoben = 0
    for u in unterrichte:
        regel = Klausurregel.fuer(u)
        if regel is None:
            Klausurregel.freigeben(u)
        else:
            verschoben += regel.anwenden(u)
        n += 1
    return n, verschoben


@login_required
def klausurregeln(request, pk=None):
    if not rechte.darf_klausurregeln(request.user):
        raise PermissionDenied
    regel = get_object_or_404(Klausurregel, pk=pk) if pk else None
    freigabe_form = FreigabeForm(request.POST if request.POST.get("aktion") == "freigabe" else None)
    if freigabe_form.is_bound:
        if freigabe_form.is_valid():
            f = freigabe_form.save(commit=False)
            f.angelegt_von = request.user
            f.save()
            freigabe_form.save_m2m()
            Protokoll.schreiben(request.user, "rechte", gettext("Zeugnisnote ohne Einzelnoten freigegeben: %(f)s, %(fa)s") % {
                "f": f, "fa": ", ".join(x.kuerzel for x in f.faecher.all()) or gettext("alle Fächer")})
            messages.success(request, gettext("Freigabe gespeichert."))
            return redirect("klausurregeln")
        form = RegelForm(instance=regel)
    else:
        form = RegelForm(request.POST or None, instance=regel)
    if request.method == "POST" and not freigabe_form.is_bound and form.is_valid():
        with transaction.atomic():
            vorher = _betroffen(regel) if regel else {}
            neu = form.save(commit=False)
            if regel is None:
                neu.angelegt_von = request.user
            neu.save()
            form.save_m2m()
            nachher = _betroffen(neu)
            n, verschoben = neu_anwenden({**vorher, **nachher}.values())
            Protokoll.schreiben(request.user, "rechte", gettext("Klausurregel gespeichert: %(r)s, %(f)s") % {
                "r": neu, "f": ", ".join(f.kuerzel for f in neu.faecher.all())})
        text = ngettext("Regel gespeichert und auf %(n)s Kurs angewendet.", "Regel gespeichert und auf %(n)s Kurse angewendet.", n) % {"n": n}
        if verschoben:
            text += " " + ngettext("%(v)s weiterer Ordner der obersten Ebene wurde in „%(m)s“ verschoben.",
                                   "%(v)s weitere Ordner der obersten Ebene wurden in „%(m)s“ verschoben.", verschoben) % {
                "v": verschoben, "m": neu.name_mitarbeit}
        messages.success(request, text)
        return redirect("klausurregeln")
    regeln = list(Klausurregel.objects.prefetch_related("faecher"))
    for r in regeln:
        r.kurse = len(_betroffen(r))
    return render(request, "noten/klausurregeln.html", {
        "form": form, "regel": regel, "regeln": regeln, "freigabe_form": freigabe_form,
        "freigaben": Zeugnisnotenfreigabe.objects.prefetch_related("faecher"),
    })


@login_required
@require_POST
def freigabe_loeschen(request, pk):
    if not rechte.darf_klausurregeln(request.user):
        raise PermissionDenied
    f = get_object_or_404(Zeugnisnotenfreigabe, pk=pk)
    Protokoll.schreiben(request.user, "rechte", gettext("Freigabe „Zeugnisnote ohne Einzelnoten“ aufgehoben: %(f)s") % {"f": f})
    f.delete()
    messages.success(request, gettext("Freigabe aufgehoben."))
    return redirect("klausurregeln")


@login_required
@require_POST
def klausurregel_loeschen(request, pk):
    if not rechte.darf_klausurregeln(request.user):
        raise PermissionDenied
    regel = get_object_or_404(Klausurregel, pk=pk)
    with transaction.atomic():
        betroffen = _betroffen(regel)
        name = str(regel)
        regel.delete()
        n, _v = neu_anwenden(betroffen.values())
        Protokoll.schreiben(request.user, "rechte", gettext("Klausurregel gelöscht: %(r)s") % {"r": name})
    messages.success(request, ngettext("Regel gelöscht; in %(n)s Kurs sind die Ordner wieder frei.",
                                       "Regel gelöscht; in %(n)s Kursen sind die Ordner wieder frei.", n) % {"n": n})
    return redirect("klausurregeln")
