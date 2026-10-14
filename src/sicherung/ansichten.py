"""Portalseiten: Sicherung und Wiederherstellung, PDF-Export, Benutzer und Rechte, Protokoll."""
import io
import zipfile
from datetime import timedelta
from functools import wraps

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone, translation
from django.utils.translation import gettext, gettext_lazy as _, ngettext
from django.views.decorators.http import require_POST

from portal import rollen as R
from portal.rechte import darf_sichern, ist_it
from stammdaten.models import Abschnitt, Schuljahr

from . import archiv, konten, pdf
from .models import Exportauftrag, Protokoll, Sicherung
from .module import MODULE, NAMEN, SCHLUESSEL

BESTAETIGUNG = _("WIEDERHERSTELLEN")
BESTAETIGUNG_WOERTER = {"WIEDERHERSTELLEN", "RESTORE"}
DATUM = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


def nur_sicherung(ansicht):
    @wraps(ansicht)
    @login_required
    def innen(request, *args, **kwargs):
        if not darf_sichern(request.user):
            raise PermissionDenied
        return ansicht(request, *args, **kwargs)
    return innen


def nur_it(ansicht):
    @wraps(ansicht)
    @login_required
    def innen(request, *args, **kwargs):
        if not ist_it(request.user):
            raise PermissionDenied
        return ansicht(request, *args, **kwargs)
    return innen


def _reiter(request, aktiv):
    reiter = []
    if darf_sichern(request.user):
        reiter += [("sicherung", _("Sicherung und Wiederherstellung"), "sicherungen"), ("pdf", _("PDF-Export"), "pdf_export")]
    if ist_it(request.user):
        reiter.append(("benutzer", _("Benutzer und Rechte"), "benutzerverwaltung"))
    reiter.append(("protokoll", _("Protokoll"), "systemprotokoll"))
    return [{"schluessel": s, "name": n, "url": u, "aktiv": s == aktiv} for s, n, u in reiter]


# ---------------------------------------------------------------- Sicherungen

class SicherungForm(forms.Form):
    module = forms.MultipleChoiceField(label=_("Module"), choices=[(k, n) for k, n, _a in MODULE], initial=SCHLUESSEL,
                                       widget=forms.CheckboxSelectMultiple)
    mit_dateien = forms.BooleanField(label=_("Hochgeladene Dateien einschließen (Anhänge, Bewerbungsunterlagen)"), required=False)
    bemerkung = forms.CharField(label=_("Bemerkung"), max_length=200, required=False)


class HochladenForm(forms.Form):
    datei = forms.FileField(label=_("Sicherungsdatei (ZIP)"))

    def clean_datei(self):
        d = self.cleaned_data["datei"]
        if d.size > settings.SICHERUNG_UPLOAD_MAX_MB * 1024 * 1024:
            raise forms.ValidationError(_("Die Datei ist größer als %(mb)s MB.") % {"mb": settings.SICHERUNG_UPLOAD_MAX_MB})
        return d


@nur_sicherung
def sicherungen(request):
    form = SicherungForm()
    hochladen = HochladenForm()
    if request.method == "POST":
        if request.POST.get("aktion") == "hochladen":
            hochladen = HochladenForm(request.POST, request.FILES)
            if hochladen.is_valid():
                try:
                    s = archiv.sicherung_hochladen(hochladen.cleaned_data["datei"], request.user)
                except archiv.SicherungFehler as fehler:
                    hochladen.add_error("datei", str(fehler))
                else:
                    messages.success(request, gettext("Sicherung hochgeladen und geprüft: %(datei)s") % {"datei": s.datei})
                    return redirect("sicherungen")
        else:
            form = SicherungForm(request.POST)
            if form.is_valid():
                d = form.cleaned_data
                s = archiv.sicherung_erstellen(d["module"], request.user, mit_dateien=d["mit_dateien"], bemerkung=d["bemerkung"])
                messages.success(request, gettext("Sicherung erstellt: %(datei)s (%(n)s Einträge)") % {"datei": s.datei, "n": s.gesamt})
                return redirect("sicherungen")
    liste = list(Sicherung.objects.select_related("erstellt_von__person"))
    for s in liste:
        s.modulnamen = [NAMEN.get(m, m) for m in s.module]
        s.vorhanden = s.pfad.exists()
    return render(request, "sicherung/sicherungen.html", {
        "reiter": _reiter(request, "sicherung"), "form": form, "hochladen": hochladen, "sicherungen": liste,
        "ordner": settings.MODUL_SICHERUNGEN, "alle_module": len(SCHLUESSEL),
    })


@nur_sicherung
def sicherung_herunterladen(request, pk):
    s = get_object_or_404(Sicherung, pk=pk)
    if not s.pfad.exists():
        raise Http404
    Protokoll.schreiben(request.user, "heruntergeladen", s.datei)
    return FileResponse(open(s.pfad, "rb"), as_attachment=True, filename=s.datei, content_type="application/zip")


@nur_sicherung
@require_POST
def sicherung_loeschen(request, pk):
    s = get_object_or_404(Sicherung, pk=pk)
    archiv.sicherung_loeschen(s, request.user)
    messages.success(request, gettext("Sicherung gelöscht."))
    return redirect("sicherungen")


@nur_sicherung
def wiederherstellen(request, pk):
    s = get_object_or_404(Sicherung, pk=pk)
    if not s.pfad.exists():
        messages.error(request, gettext("Die Datei dieser Sicherung fehlt im Sicherungsordner."))
        return redirect("sicherungen")
    angeboten = [(k, NAMEN[k]) for k in SCHLUESSEL if k in s.module]
    gewaehlt = [k for k in request.POST.getlist("module") if k in s.module] if request.method == "POST" else []
    plan = fehler = None
    if request.method == "POST":
        if not gewaehlt:
            fehler = gettext("Bitte mindestens ein Modul wählen.")
        elif request.POST.get("aktion") == "ausfuehren":
            if request.POST.get("bestaetigung", "").strip().upper() not in BESTAETIGUNG_WOERTER or not request.POST.get("verstanden"):
                fehler = gettext("Bitte die Sicherheitsabfrage ausfüllen.")
            else:
                try:
                    plan, vorher = archiv.wiederherstellen(s, gewaehlt, request.user)
                except archiv.SicherungFehler as f:
                    fehler = str(f)
                else:
                    return render(request, "sicherung/wiederhergestellt.html", {
                        "reiter": _reiter(request, "sicherung"), "s": s, "plan": plan, "vorher": vorher})
        if not fehler or plan is None:
            try:
                plan = archiv.planen(s.pfad, gewaehlt, request.user) if gewaehlt else None
            except archiv.SicherungFehler as f:
                fehler = str(f)
    return render(request, "sicherung/wiederherstellen.html", {
        "reiter": _reiter(request, "sicherung"), "s": s, "angeboten": angeboten, "gewaehlt": gewaehlt, "plan": plan,
        "fehler": fehler, "bestaetigung": BESTAETIGUNG,
    })


# ---------------------------------------------------------------- PDF-Export

ZEITRAEUME = [("halbjahr", _("aktuelles Halbjahr")), ("schuljahr", _("aktuelles Schuljahr")), ("30", _("letzte 30 Tage")),
              ("eigen", _("eigener Zeitraum")), ("alles", _("ohne Begrenzung"))]


class ExportForm(forms.Form):
    module = forms.MultipleChoiceField(label=_("Module"), choices=[(k, n) for k, n, _a in MODULE if k != "konten"],
                                       widget=forms.CheckboxSelectMultiple)
    zeitraum = forms.ChoiceField(label=_("Zeitraum"), choices=ZEITRAEUME, initial="halbjahr")
    von = forms.DateField(label=_("Von"), required=False, widget=DATUM)
    bis = forms.DateField(label=_("Bis"), required=False, widget=DATUM)
    aufteilung = forms.ChoiceField(label=_("Aufteilung in mehrere PDFs"), choices=Exportauftrag.AUFTEILUNG, initial="auto")
    mit_bestand = forms.BooleanField(label=_("Bestandsdaten ohne Datum einbeziehen (z. B. Personen, Klassen, Kataloge)"),
                                     required=False, initial=True)
    mit_protokoll = forms.BooleanField(label=_("Änderungsprotokoll im Zeitraum einbeziehen"), required=False)

    def clean(self):
        d = super().clean()
        heute = timezone.localdate()
        art = d.get("zeitraum")
        if art == "halbjahr":
            a = Abschnitt.objects.filter(beginn__lte=heute, ende__gte=heute).first()
            if a is None:
                raise forms.ValidationError(_("Heute liegt in keinem Halbjahr – bitte einen eigenen Zeitraum wählen."))
            d["von"], d["bis"] = a.beginn, a.ende
        elif art == "schuljahr":
            sj = Schuljahr.aktuelles()
            if sj is None:
                raise forms.ValidationError(_("Kein aktuelles Schuljahr – bitte einen eigenen Zeitraum wählen."))
            d["von"], d["bis"] = sj.beginn, sj.ende
        elif art == "30":
            d["von"], d["bis"] = heute - timedelta(days=30), heute
        elif art == "alles":
            d["von"] = d["bis"] = None
        else:
            if not (d.get("von") and d.get("bis")):
                raise forms.ValidationError(_("Bitte Beginn und Ende des Zeitraums angeben."))
            if d["bis"] < d["von"]:
                raise forms.ValidationError(_("Das Ende darf nicht vor dem Beginn liegen."))
        return d


@nur_sicherung
def pdf_export(request):
    form = ExportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        auftrag = Exportauftrag.objects.create(
            module=[k for k in SCHLUESSEL if k in d["module"]], von=d["von"], bis=d["bis"], aufteilung=d["aufteilung"],
            mit_bestand=d["mit_bestand"], mit_protokoll=d["mit_protokoll"], sprache=translation.get_language() or "de",
            erstellt_von=request.user)
        pdf.export_starten(auftrag)
        messages.success(request, gettext("PDF-Export gestartet. Die Dateien erscheinen unten, sobald sie fertig sind."))
        return redirect("pdf_export")
    auftraege = list(Exportauftrag.objects.select_related("erstellt_von")[:30])
    for a in auftraege:
        a.modulnamen = [NAMEN.get(m, m) for m in a.module]
        a.zeitraum = pdf.zeitraum_text(a.von, a.bis)
        a.seiten = sum(d.get("seiten", 0) for d in a.dateien)
    laeuft = any(a.status in (Exportauftrag.WARTET, Exportauftrag.LAEUFT) for a in auftraege)
    return render(request, "sicherung/pdf.html", {
        "reiter": _reiter(request, "pdf"), "form": form, "auftraege": auftraege, "laeuft": laeuft,
        "grenze": settings.PDF_EINTRAEGE_JE_DATEI,
    })


def _export_datei(auftrag, name):
    if name not in {d["name"] for d in auftrag.dateien}:
        raise Http404
    pfad = auftrag.ordner / name
    if not pfad.exists():
        raise Http404
    return pfad


@nur_sicherung
def pdf_datei(request, pk, name):
    auftrag = get_object_or_404(Exportauftrag, pk=pk)
    pfad = _export_datei(auftrag, name)
    return FileResponse(open(pfad, "rb"), as_attachment=request.GET.get("ansehen") != "1", filename=name, content_type="application/pdf")


@nur_sicherung
def pdf_zip(request, pk):
    auftrag = get_object_or_404(Exportauftrag, pk=pk, status=Exportauftrag.FERTIG)
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in auftrag.dateien:
            pfad = auftrag.ordner / d["name"]
            if pfad.exists():
                zf.write(pfad, d["name"])
    puffer.seek(0)
    name = f"pdf-export-{auftrag.pk}-{timezone.localtime(auftrag.erstellt_am):%Y%m%d}.zip"
    return FileResponse(puffer, as_attachment=True, filename=name, content_type="application/zip")


@nur_sicherung
@require_POST
def pdf_loeschen(request, pk):
    auftrag = get_object_or_404(Exportauftrag, pk=pk)
    import shutil

    shutil.rmtree(auftrag.ordner, ignore_errors=True)
    auftrag.delete()
    messages.success(request, gettext("PDF-Export gelöscht."))
    return redirect("pdf_export")


# ---------------------------------------------------------------- Benutzer und Rechte (IT)

@nur_it
def benutzerverwaltung(request):
    User = get_user_model()
    q = (request.GET.get("q") or "").strip()
    rolle = request.GET.get("rolle") or ""
    qs = User.objects.prefetch_related("groups").select_related("person", "einstellung").order_by("-is_active", "username")
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(person__nachname__icontains=q) | Q(person__vorname__icontains=q))
    if rolle:
        qs = qs.filter(groups__name=rolle)
    zeilen = []
    for u in qs[:500]:
        namen = {g.name for g in u.groups.all()}
        zeilen.append({"u": u, "rollen": [R.ANZEIGE.get(n, n) for n in R.REIHENFOLGE if n in namen] + sorted(n for n in namen if n not in R.ANZEIGE),
                       "plus": u.user_permissions.count(),
                       "minus": u.einstellung.entzogene_rechte.count() if hasattr(u, "einstellung") else 0})
    return render(request, "sicherung/benutzer.html", {
        "reiter": _reiter(request, "benutzer"), "zeilen": zeilen, "q": q, "rolle": rolle,
        "rollen": [(r, R.ANZEIGE[r]) for r in R.REIHENFOLGE],
    })


@nur_it
def benutzer_bearbeiten(request, pk):
    User = get_user_model()
    u = get_object_or_404(User.objects.select_related("person"), pk=pk)
    neues_passwort = None
    if request.method == "POST":
        aktion = request.POST.get("aktion")
        try:
            if aktion == "konto":
                konten.konto_speichern(u, request.POST.getlist("rollen"), bool(request.POST.get("aktiv")), request.user)
                messages.success(request, gettext("Rollen und Konto gespeichert."))
            elif aktion == "rechte":
                zustaende = {int(k[2:]): v for k, v in request.POST.items() if k.startswith("r_") and k[2:].isdigit()}
                n = konten.einzelrechte_speichern(u, zustaende, request.user)
                messages.success(request, ngettext("%(n)d Einzelrecht geändert.", "%(n)d Einzelrechte geändert.", n) % {"n": n})
            elif aktion == "passwort":
                if u == request.user:
                    raise konten.KontoFehler(gettext("Ihr eigenes Passwort ändern Sie über „Passwort ändern“ im Kontomenü."))
                neues_passwort = konten.passwort_zuruecksetzen(u, request.user)
            else:
                raise Http404
        except konten.KontoFehler as f:
            messages.error(request, str(f))
        if neues_passwort is None:
            return redirect("benutzer_bearbeiten", pk=u.pk)
    rollen = set(u.groups.values_list("name", flat=True))
    return render(request, "sicherung/benutzer_bearbeiten.html", {
        "reiter": _reiter(request, "benutzer"), "u": u, "neues_passwort": neues_passwort,
        "rollen": [{"name": r, "anzeige": R.ANZEIGE[r], "beschreibung": R.BESCHREIBUNG[r], "aktiv": r in rollen} for r in R.REIHENFOLGE],
        "tabelle": konten.rechte_tabelle(u), "aktionen": [_("ansehen"), _("anlegen"), _("ändern"), _("löschen")],
        "vollzugriff": u.is_superuser,
        "email": u.email or getattr(getattr(u, "person", None), "email", ""),
    })


# ---------------------------------------------------------------- Protokoll

@login_required
def systemprotokoll(request):
    if not (darf_sichern(request.user) or ist_it(request.user)):
        raise PermissionDenied
    qs = Protokoll.objects.select_related("benutzer")
    if not ist_it(request.user):
        qs = qs.exclude(aktion__in=["rechte", "passwort", "konto"])
    aktion = request.GET.get("aktion") or ""
    if aktion in dict(Protokoll.AKTIONEN):
        qs = qs.filter(aktion=aktion)
    return render(request, "sicherung/protokoll.html", {
        "reiter": _reiter(request, "protokoll"), "eintraege": qs[:500], "aktion": aktion, "aktionen": Protokoll.AKTIONEN,
    })
