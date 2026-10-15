"""Anhänge zur Schülerakte: hochladen, rechtegeprüft herunterladen, löschen."""
from urllib.parse import quote

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.translation import gettext, gettext_lazy as _
from django.views.decorators.http import require_POST

from stammdaten.dokumente import INLINE_TYPEN
from stammdaten.models import Dokument, Schuelerprofil

from .rechte import darf_dokument_loeschen, darf_dokument_sehen, dokument_stufen_fuer


class AnhangForm(forms.ModelForm):
    class Meta:
        model = Dokument
        fields = ["titel", "kategorie", "zugriffsstufe", "datei", "notiz"]
        widgets = {"notiz": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, stufen=None, **kwargs):
        super().__init__(*args, **kwargs)
        if stufen is not None:
            self.fields["zugriffsstufe"].choices = [c for c in Dokument.STUFEN if c[0] in stufen]
        self.fields["zugriffsstufe"].help_text = ""
        self.fields["datei"].required = False


def anhang_form(user, schueler, data=None, files=None):
    stufen = dokument_stufen_fuer(user, schueler.person)
    if not stufen:
        return None
    return AnhangForm(data, files, stufen=stufen, prefix="anhang")


def anhaenge_fuer(user, person, kategorie=None, aelteste_zuerst=False):
    qs = person.dokumente.select_related("hochgeladen_von", "hochgeladen_von__person")
    if kategorie:
        qs = qs.filter(kategorie=kategorie)
    qs = qs.order_by("hochgeladen_am", "pk") if aelteste_zuerst else qs.order_by("-hochgeladen_am", "-pk")
    sichtbar = [d for d in qs if darf_dokument_sehen(user, d)]
    for d in sichtbar:
        d.darf_loeschen = darf_dokument_loeschen(user, d)
        d.inline_moeglich = bool(d.datei) and d.inhaltstyp in INLINE_TYPEN
    return sichtbar


@login_required
@require_POST
def anhang_hochladen(request, pk):
    schueler = get_object_or_404(Schuelerprofil.objects.select_related("person"), pk=pk)
    form = anhang_form(request.user, schueler, request.POST, request.FILES)
    if form is None:
        raise PermissionDenied
    ziel = reverse("schuelerakte", args=[pk]) + "#anhaenge"
    if form.is_valid():
        dok = form.save(commit=False)
        dok.person = schueler.person
        dok.hochgeladen_von = request.user
        dok.save()
        messages.success(request, gettext("Anhang „%(titel)s“ gespeichert.") % {"titel": dok.titel})
    else:
        fehler = "; ".join(f"{form.fields[f].label if f in form.fields else ''}: {' '.join(e)}".lstrip(": ")
                           for f, e in form.errors.items())
        messages.error(request, gettext("Anhang nicht gespeichert – %(fehler)s") % {"fehler": fehler})
    return redirect(ziel)


def _ausliefern(request, dok):
    if not darf_dokument_sehen(request.user, dok):
        raise PermissionDenied
    return datei_ausliefern(request, dok.datei, dok.inhaltstyp, dok.originalname)


def datei_ausliefern(request, feld, inhaltstyp, originalname):
    """Gemeinsame, sichere Auslieferung hochgeladener Dateien (Anhänge, Bewerbungsunterlagen) – Rechte prüft der Aufrufer."""
    if not feld:
        raise Http404
    try:
        datei = feld.open("rb")
    except FileNotFoundError:
        raise Http404
    ansehen = request.GET.get("ansehen") == "1" and inhaltstyp in INLINE_TYPEN
    name = originalname or feld.name.rsplit("/", 1)[-1]
    antwort = FileResponse(datei, content_type=inhaltstyp or "application/octet-stream")
    art = "inline" if ansehen else "attachment"
    antwort["Content-Disposition"] = f"{art}; filename*=UTF-8''{quote(name)}"
    # Hochgeladene Inhalte dürfen keine Skripte im Kontext von edunex ausführen.
    antwort["Content-Security-Policy"] = "sandbox; default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"
    antwort["X-Content-Type-Options"] = "nosniff"
    antwort["Cache-Control"] = "private, no-store"
    return antwort


@login_required
def anhang_herunterladen(request, pk):
    return _ausliefern(request, get_object_or_404(Dokument.objects.select_related("person"), pk=pk))


@login_required
def anhang_pfad(request, name):
    """Links aus der Verwaltungsoberfläche (Dateifeld) – gleiche Rechteprüfung wie oben."""
    dok = Dokument.objects.select_related("person").filter(datei=name).first()
    if dok is None:
        raise Http404
    return _ausliefern(request, dok)


@login_required
@require_POST
def anhang_loeschen(request, pk):
    dok = get_object_or_404(Dokument.objects.select_related("person"), pk=pk)
    if not darf_dokument_loeschen(request.user, dok):
        raise PermissionDenied
    schueler = getattr(dok.person, "schueler", None)
    titel = dok.titel
    dok.delete()
    messages.success(request, gettext("Anhang „%(titel)s“ gelöscht.") % {"titel": titel})
    if schueler:
        return redirect(reverse("schuelerakte", args=[schueler.pk]) + "#anhaenge")
    return redirect("start")


KATEGORIE_FILTER = [("", _("Alle Kategorien"))] + Dokument.KATEGORIEN
