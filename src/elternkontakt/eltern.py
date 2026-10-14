"""
Elternseite: Öffnen über den persönlichen Link (ohne Konto) sowie das vorbereitete Elternportal.

Sicherheit: Links sind signiert, befristet (ELTERN_LINK_TAGE) und widerrufbar (Schlüssel je Empfänger:in).
Seiten mit Link werden nicht zwischengespeichert, nicht indexiert und geben keinen Referrer weiter.
"""
from django import forms
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _

from portal import rollen as R

from .models import Empfaenger
from .versand import LinkUngueltig, antwort_der_eltern, beitraege_fuer_eltern, empfaenger_aus_token


class ElternAntwortForm(forms.Form):
    text = forms.CharField(label=_("Ihre Antwort an die Schule"), widget=forms.Textarea(attrs={"rows": 5}), max_length=4000)


def _sprache(request, person):
    wahl = request.GET.get("sprache")
    if wahl in dict(settings.LANGUAGES):
        return wahl
    return person.sprache if person.sprache in dict(settings.LANGUAGES) else settings.LANGUAGE_CODE


def _absichern(antwort):
    antwort["Cache-Control"] = "no-store"
    antwort["Referrer-Policy"] = "no-referrer"
    antwort["X-Robots-Tag"] = "noindex, nofollow"
    return antwort


def _verlauf(request, e, ueber, ziel):
    """Gemeinsamer Ablauf für Link und Portal: lesen, bestätigen, antworten."""
    g = e.gespraech
    sprache = _sprache(request, e.person)
    with translation.override(sprache):
        form = ElternAntwortForm()
        if request.method == "POST":
            aktion = request.POST.get("aktion")
            if aktion == "bestaetigen" and g.bestaetigung_erbeten:
                e.bestaetigen(ueber)
                return _absichern(redirect(f"{ziel}?sprache={sprache}&bestaetigt=1"))
            if aktion == "antworten":
                if not g.nimmt_antworten_an:
                    raise Http404
                form = ElternAntwortForm(request.POST)
                if form.is_valid():
                    antwort_der_eltern(e, form.cleaned_data["text"], ueber)
                    return _absichern(redirect(f"{ziel}?sprache={sprache}&gesendet=1"))
        elif not e.gelesen_am:
            e.gelesen_am = timezone.now()
            e.save(update_fields=["gelesen_am"])
        antwort = render(request, "elternkontakt/eltern_nachricht.html", {
            "e": e, "g": g, "beitraege": beitraege_fuer_eltern(g, e.person), "form": form, "sprache": sprache,
            "bestaetigt": request.GET.get("bestaetigt"), "gesendet": request.GET.get("gesendet"),
            "portal": ueber == "portal",
        })
        antwort["Content-Language"] = sprache
    return _absichern(antwort)


def nachricht(request, token):
    try:
        e = empfaenger_aus_token(token)
    except LinkUngueltig:
        with translation.override(request.GET.get("sprache") if request.GET.get("sprache") in dict(settings.LANGUAGES)
                                  else translation.get_language()):
            return _absichern(render(request, "elternkontakt/eltern_ungueltig.html", status=404))
    return _verlauf(request, e, "link", request.path)


# ---------------------------------------------------------------- Elternportal (vorbereitet, abschaltbar)

def _portal_person(request):
    if not settings.ELTERNPORTAL_AKTIV:
        raise Http404
    if not request.user.groups.filter(name=R.ELTERN).exists():
        raise Http404
    person = getattr(request.user, "person", None)
    if person is None:
        raise Http404
    return person


@login_required
def portal_start(request):
    person = _portal_person(request)
    eintraege = (Empfaenger.objects.filter(person=person).select_related("gespraech__schueler__person")
                 .order_by("-gespraech__letzte_aktivitaet"))
    with translation.override(_sprache(request, person)):
        return _absichern(render(request, "elternkontakt/eltern_portal.html", {"eintraege": eintraege, "person": person,
                                                                                       "portal": True}))


@login_required
def portal_gespraech(request, pk):
    person = _portal_person(request)
    e = get_object_or_404(Empfaenger.objects.select_related("gespraech__schueler__person", "person"), gespraech_id=pk, person=person)
    return _verlauf(request, e, "portal", request.path)
