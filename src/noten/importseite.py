"""Seite „Excel-Notentabelle“ eines Unterrichts: Vorlage herunterladen, Datei hochladen, Vorschau, Übernahme (ab 0.4.11.0)."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _, gettext_lazy, ngettext

from . import notenimport as I
from .ansichten import _unterricht
from .berechnung import Baum

SITZUNG = "notenimport_{pk}"


class DateiForm(forms.Form):
    datei = forms.FileField(label=gettext_lazy("Ausgefüllte Notentabelle (.xlsx)"),
                            widget=forms.ClearableFileInput(attrs={"accept": ".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}))


def _protokoll(request, u, text):
    from sicherung.models import Protokoll

    Protokoll.schreiben(request.user, "notenimport", f"{text}: {u.fach.kuerzel} {u.gruppe.name}, {u.abschnitt}")


@login_required
def vorlage(request, pk):
    u = _unterricht(request, pk)
    if not I.nur_sek1(u):
        messages.error(request, _("Die Notentabelle ist für Noten 1–6 (Sek I) gedacht; dieser Unterricht verwendet Punkte."))
        return redirect("notenuebersicht", pk=u.pk)
    inhalt = I.vorlage(u)
    _protokoll(request, u, _("Notentabelle heruntergeladen"))
    antwort = HttpResponse(inhalt, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    antwort["Content-Disposition"] = f'attachment; filename="{I.dateiname(u)}"'
    return antwort


@login_required
def notentabelle(request, pk):
    u = _unterricht(request, pk)
    schluessel = SITZUNG.format(pk=u.pk)
    tabelle = request.session.get(schluessel)
    wahl = {b: request.POST.get(f"ordner_{b}") or request.GET.get(f"ordner_{b}") for b in I.BEREICHE}
    form = DateiForm()
    if request.method == "POST":
        aktion = request.POST.get("aktion")
        if aktion == "hochladen":
            form = DateiForm(request.POST, request.FILES)
            if form.is_valid():
                try:
                    tabelle = I.lesen(form.cleaned_data["datei"])
                except I.ImportFehler as f:
                    form.add_error("datei", str(f))
                else:
                    tabelle["dateiname"] = form.cleaned_data["datei"].name[:120]
                    weiter = request.POST.get("weiter", "")
                    if weiter and url_has_allowed_host_and_scheme(weiter, allowed_hosts={request.get_host()}):
                        tabelle["weiter"] = weiter[:500]
                    request.session[schluessel] = tabelle
                    return redirect("notentabelle", pk=u.pk)
        elif aktion == "verwerfen":
            weiter = (tabelle or {}).get("weiter")
            request.session.pop(schluessel, None)
            messages.info(request, _("Die hochgeladene Tabelle wurde verworfen."))
            return redirect(weiter or reverse("notentabelle", args=[u.pk]))
        elif aktion == "uebernehmen" and tabelle:
            try:
                ergebnis = I.uebernehmen(u, tabelle, wahl, gewichte_uebernehmen=bool(request.POST.get("gewichte")))
            except I.ImportFehler as f:
                messages.error(request, _("Es wurde nichts gespeichert: %(fehler)s") % {"fehler": f})
            else:
                request.session.pop(schluessel, None)
                s = ergebnis["summe"]
                anzahl = sum(1 for sp in ergebnis["spalten"] if sp["aktion"] != "uebersprungen" and sp["zellen"])
                text = ngettext("%(n)s Leistungsnachweis übernommen", "%(n)s Leistungsnachweise übernommen", anzahl) % {"n": anzahl}
                text += " – " + _("%(neu)s Noten neu, %(geaendert)s geändert, %(gleich)s unverändert.") % s
                _protokoll(request, u, _("Noten aus Excel übernommen") + f" ({text})")
                messages.success(request, text)
                return redirect(tabelle.get("weiter") or reverse("notenuebersicht", args=[u.pk]))
        elif aktion == "pruefen" and tabelle:
            url = reverse("notentabelle", args=[u.pk]) + "?" + "&".join(f"ordner_{b}={wahl[b]}" for b in I.BEREICHE if wahl[b])
            return redirect(url)
    vorschau = I.pruefen(u, tabelle, wahl) if tabelle else None
    return render(request, "noten/notentabelle.html", {
        "u": u, "form": form, "tabelle": tabelle, "vorschau": vorschau, "sek1": I.nur_sek1(u),
        "ordner": I.ordner_auswahl(u, Baum(u)),
        "bereiche": [{"b": b, "titel": titel, "ziel": (vorschau or {}).get("ziel", {}).get(b), "neu": I.NEU[b]}
                     for b, titel in (("ka", _("Klassenarbeiten")), ("somi", _("Sonstige Mitarbeit (SoMi)")))],
        "blatt": I.T.BLATT_HJ[u.abschnitt.nummer],
    })
