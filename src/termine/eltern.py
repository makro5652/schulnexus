"""
Sprechtage im Elternportal (nur mit ELTERNPORTAL_AKTIV und Elternkonto).

Eltern sehen die Sprechtage, deren Buchung offen ist, je Kind die vorgesehenen Lehrkräfte mit freien Zeiten,
und buchen bzw. sagen ab, solange der Buchungszeitraum läuft.
"""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext

from elternkontakt.eltern import _absichern, _portal_person, _sprache

from . import sprechtag as S
from .ansichten import _zeit_aus_schluessel
from .models import Gespraechstermin, Sprechtag, Teilnahme, Termin


def offene_sprechtage(person):
    kinder = list(S.kinder_von(person))
    ergebnis = []
    for st in Sprechtag.objects.filter(status__in=[Sprechtag.BUCHUNG, Sprechtag.GESCHLOSSEN]).prefetch_related("zeitfenster"):
        tage = st.tage
        if tage and tage[-1] < timezone.localdate():
            continue
        passend = [k for k in kinder if S.teilnahmen_fuer_schueler(st, k).exists()]
        if passend:
            ergebnis.append({"st": st, "kinder": passend, "offen": st.buchung_offen(),
                             "termine": Gespraechstermin.objects.filter(sprechtag=st, schueler__in=passend).count()})
    return ergebnis


@login_required
def uebersicht(request):
    person = _portal_person(request)
    with translation.override(_sprache(request, person)):
        heute = timezone.localdate()
        termine = Termin.objects.filter(fuer_eltern=True).filter(Q(beginn__gte=heute) | Q(ende__gte=heute))[:20]
        return _absichern(render(request, "termine/eltern_uebersicht.html", {
            "person": person, "sprechtage": offene_sprechtage(person), "termine": termine, "portal": True,
            "meine": Gespraechstermin.objects.filter(schueler__in=S.kinder_von(person), beginn__gte=timezone.now())
            .select_related("teilnahme__lehrkraft__person", "teilnahme__raum", "schueler__person", "sprechtag").order_by("beginn"),
        }))


@login_required
def buchen(request, pk):
    person = _portal_person(request)
    st = get_object_or_404(Sprechtag.objects.exclude(status__in=[Sprechtag.ENTWURF, Sprechtag.VERFUEGBARKEIT]), pk=pk)
    kinder = [k for k in S.kinder_von(person) if S.teilnahmen_fuer_schueler(st, k).exists()]
    if not kinder:
        raise Http404
    ziel = reverse("eltern_sprechtag", args=[st.pk])
    with translation.override(_sprache(request, person)):
        if request.method == "POST":
            aktion = request.POST.get("aktion")
            if aktion == "buchen":
                t = get_object_or_404(Teilnahme, pk=request.POST.get("teilnahme"), sprechtag=st)
                kind = next((k for k in kinder if str(k.pk) == request.POST.get("schueler")), None)
                beginn = _zeit_aus_schluessel(request.POST.get("zeit"))
                if kind is None or beginn is None:
                    return _absichern(redirect(ziel + "?fehler=auswahl"))
                try:
                    S.buchen(t, beginn, kind, eltern=person, user=request.user, ueber=Gespraechstermin.PORTAL,
                             anliegen=request.POST.get("anliegen", ""))
                except ValidationError as e:
                    request.session["eltern_fehler"] = " ".join(e.messages)
                    return _absichern(redirect(ziel + "?fehler=1"))
                return _absichern(redirect(ziel + "?gebucht=1"))
            if aktion == "absagen":
                g = get_object_or_404(Gespraechstermin, pk=request.POST.get("termin"), sprechtag=st)
                if not S.darf_absagen_eltern(g, person):
                    raise Http404
                g.delete()
                return _absichern(redirect(ziel + "?abgesagt=1"))
            raise Http404
        offen = st.buchung_offen()
        bereiche = []
        for k in kinder:
            gebucht = list(Gespraechstermin.objects.filter(sprechtag=st, schueler=k)
                           .select_related("teilnahme__lehrkraft__person", "teilnahme__raum").order_by("beginn"))
            mit = {g.teilnahme_id for g in gebucht}
            lehrkraefte = []
            for t in S.teilnahmen_fuer_schueler(st, k):
                lehrkraefte.append({"t": t, "gebucht": t.pk in mit, "frei": S.freie_zeiten(t) if offen and t.pk not in mit else []})
            voll = bool(st.max_je_kind and len(gebucht) >= st.max_je_kind)
            bereiche.append({"kind": k, "gebucht": gebucht, "lehrkraefte": lehrkraefte, "voll": voll,
                             "alle_gebucht": bool(lehrkraefte) and all(l["gebucht"] for l in lehrkraefte)})
        fehler = request.session.pop("eltern_fehler", "") if request.GET.get("fehler") else ""
        if request.GET.get("fehler") == "auswahl":
            fehler = gettext("Bitte Kind und Uhrzeit wählen.")
        return _absichern(render(request, "termine/eltern_sprechtag.html", {
            "person": person, "st": st, "bereiche": bereiche, "offen": offen, "portal": True, "fehler": fehler,
            "gebucht": request.GET.get("gebucht"), "abgesagt": request.GET.get("abgesagt"),
        }))
