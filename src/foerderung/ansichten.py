"""Portalansichten für Förderpläne und Nachteilsausgleiche (lesen, drucken, Verlauf ergänzen, Erhalt bestätigen)."""
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy as _
from django.views.decorators.http import require_POST

from portal.rechte import (
    darf_akte_sehen,
    darf_foerderung_bearbeiten, darf_foerderung_sehen, darf_nachteilsausgleich_sehen, ist_foerderkoordination,
    klassenleitung_schueler_ids,
)
from stammdaten.models import Person

from .models import Aushaendigung, Foerdereintrag, Foerderplan, Nachteilsausgleich

DATUM = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class EintragForm(forms.ModelForm):
    class Meta:
        model = Foerdereintrag
        fields = ["datum", "art", "text"]
        widgets = {"datum": DATUM, "text": forms.Textarea(attrs={"rows": 3})}


class AushaendigungForm(forms.ModelForm):
    class Meta:
        model = Aushaendigung
        fields = ["empfaenger", "ausgehaendigt_am", "weg", "bemerkung"]
        widgets = {"ausgehaendigt_am": DATUM}

    def __init__(self, *args, dokument=None, **kwargs):
        super().__init__(*args, **kwargs)
        schueler = dokument.schueler if dokument is not None else None
        if isinstance(dokument, Foerderplan):
            self.instance.foerderplan = dokument
        elif dokument is not None:
            self.instance.nachteilsausgleich = dokument
        if schueler is not None:
            self.fields["empfaenger"].queryset = Person.objects.filter(
                pk__in=schueler.beziehungen.values("person")).order_by("nachname", "vorname")
        self.fields["empfaenger"].label_from_instance = lambda p: f"{p.anzeigename}"


class BestaetigungForm(forms.Form):
    bestaetigt_am = forms.DateField(label=_("Erhalt bestätigt am"), widget=DATUM, initial=timezone.localdate)
    bestaetigung = forms.ChoiceField(label=_("Bestätigt durch"), choices=Aushaendigung.BESTAETIGUNG[:3], initial="unterschrift")


# ---------------------------------------------------------------- Kontext für die Schülerakte

def foerder_kontext(user, schueler):
    """Was in der Schülerakte zur Förderung erscheint – oder None, wenn nichts sichtbar ist."""
    sehen = darf_foerderung_sehen(user, schueler)
    nta_sehen = darf_nachteilsausgleich_sehen(user, schueler)
    if not (sehen or nta_sehen):
        return None
    aush = Prefetch("aushaendigungen", queryset=Aushaendigung.objects.select_related("empfaenger"))
    nta = list(schueler.nachteilsausgleiche.prefetch_related("massnahmen", "faecher", aush))
    return {
        "nta_aktiv": any(n.aktiv for n in nta),
        "sehen": sehen,
        "bearbeiten": darf_foerderung_bearbeiten(user, schueler),
        "plaene": list(schueler.foerderplaene.select_related("schuljahr", "verantwortlich__person")
                       .prefetch_related("schwerpunkte", aush)) if sehen else [],
        "nta": nta,
    }


def aktive_nta_je_schueler(schueler_ids):
    """{schueler_id: [Nachteilsausgleich, …]} für Markierungen in Noten- und Klassenlisten."""
    ergebnis = {}
    for n in Nachteilsausgleich.aktive().filter(schueler_id__in=schueler_ids).prefetch_related("massnahmen", "faecher"):
        ergebnis.setdefault(n.schueler_id, []).append(n)
    return ergebnis


def nta_kurztext(liste):
    teile = []
    for n in liste:
        teile.append(f"{'; '.join(n.massnahmen_liste())} ({n.faecher_text})")
    return " | ".join(teile)


def foerder_hinweise(user):
    """Offene Punkte für die Startseite: Förderkoordination sieht alle, Klassenleitungen ihre Klasse."""
    if ist_foerderkoordination(user):
        plaene = Foerderplan.objects.all()
        nta = Nachteilsausgleich.objects.all()
        koordination = True
    else:
        ids = klassenleitung_schueler_ids(user)
        if not ids:
            return None
        plaene = Foerderplan.objects.filter(schueler_id__in=ids)
        nta = Nachteilsausgleich.objects.filter(schueler_id__in=ids)
        koordination = False
    heute = timezone.localdate()
    plaene = plaene.select_related("schueler__person")
    nta = nta.select_related("schueler__person")
    offene = Aushaendigung.objects.filter(bestaetigt_am__isnull=True).filter(
        foerderplan__in=plaene) | Aushaendigung.objects.filter(bestaetigt_am__isnull=True, nachteilsausgleich__in=nta)
    hinweise = {
        "heute": heute,
        "koordination": koordination,
        "plan_ohne": list(plaene.filter(status=Foerderplan.AKTIV, aushaendigungen__isnull=True)),
        "nta_ohne": list(nta.filter(pk__in=Nachteilsausgleich.aktive().values("pk"), aushaendigungen__isnull=True)),
        "offen": list(offene.select_related("empfaenger", "foerderplan__schueler__person",
                                            "nachteilsausgleich__schueler__person").order_by("ausgehaendigt_am")),
        "evaluation": list(plaene.filter(status=Foerderplan.AKTIV, evaluation_am__lte=heute + timedelta(days=14))
                           .order_by("evaluation_am")),
        "ablauf": list(nta.filter(pk__in=Nachteilsausgleich.aktive().values("pk"),
                                  gueltig_bis__lte=heute + timedelta(days=30)).order_by("gueltig_bis")),
        "beantragt": list(nta.filter(status=Nachteilsausgleich.BEANTRAGT)) if koordination else [],
        "aktive_plaene": plaene.filter(status=Foerderplan.AKTIV).count(),
        "aktive_nta": Nachteilsausgleich.aktive().filter(pk__in=nta.values("pk")).count(),
    }
    hinweise["anzahl"] = sum(len(hinweise[k]) for k in ("plan_ohne", "nta_ohne", "offen", "evaluation", "ablauf", "beantragt"))
    return hinweise


# ---------------------------------------------------------------- Seiten

def _darf_klasse(user, schueler):
    from portal.rechte import darf_klassenliste_sehen

    klasse = schueler.stammklasse()
    return klasse is not None and darf_klassenliste_sehen(user, klasse)


def _gemeinsam(request, dokument, schueler):
    bearbeiten = darf_foerderung_bearbeiten(request.user, schueler)
    return {
        "s": schueler,
        "p": schueler.person,
        "klasse": schueler.stammklasse(),
        "darf_klasse": _darf_klasse(request.user, schueler),
        "bearbeiten": bearbeiten,
        "darf_akte": darf_akte_sehen(request.user, schueler),
        "aushaendigungen": dokument.aushaendigungen.select_related("empfaenger", "erfasst_von"),
        "aush_form": AushaendigungForm(dokument=dokument, prefix="aush",
                                       initial={"ausgehaendigt_am": timezone.localdate()}) if bearbeiten else None,
        "best_form": BestaetigungForm(prefix="best") if bearbeiten else None,
        "sorgeberechtigte": schueler.beziehungen.filter(sorgerecht=True).select_related("person"),
        "heute": timezone.localdate(),
    }


@login_required
def foerderplan(request, pk):
    plan = get_object_or_404(Foerderplan.objects.select_related("schueler__person", "schuljahr", "verantwortlich__person",
                                                                "vorgaenger"), pk=pk)
    if not darf_foerderung_sehen(request.user, plan.schueler):
        raise PermissionDenied
    kontext = _gemeinsam(request, plan, plan.schueler)
    kontext.update({
        "plan": plan,
        "ziele": plan.ziele.select_related("fach"),
        "eintraege": plan.eintraege.select_related("verfasst_von__person"),
        "nta": plan.nachteilsausgleiche.prefetch_related("massnahmen", "faecher"),
        "eintrag_form": EintragForm(prefix="eintrag", initial={"datum": timezone.localdate()}),
        "beteiligte": plan.beteiligte.select_related("person"),
    })
    return render(request, "foerderung/plan.html", kontext)


@login_required
def nachteilsausgleich(request, pk):
    nta = get_object_or_404(Nachteilsausgleich.objects.select_related("schueler__person", "foerderplan"), pk=pk)
    if not darf_nachteilsausgleich_sehen(request.user, nta.schueler):
        raise PermissionDenied
    kontext = _gemeinsam(request, nta, nta.schueler)
    kontext["nta"] = nta
    return render(request, "foerderung/nachteilsausgleich.html", kontext)


def _dokument_aus_post(request):
    art, pk = request.POST.get("dokument"), request.POST.get("dokument_id")
    if art == "plan":
        return get_object_or_404(Foerderplan, pk=pk)
    if art == "nta":
        return get_object_or_404(Nachteilsausgleich, pk=pk)
    raise PermissionDenied


def _zurueck(dokument):
    if isinstance(dokument, Foerderplan):
        return redirect("foerderplan", dokument.pk)
    return redirect("nachteilsausgleich", dokument.pk)


@login_required
@require_POST
def eintrag_anlegen(request, pk):
    plan = get_object_or_404(Foerderplan.objects.select_related("schueler"), pk=pk)
    if not darf_foerderung_sehen(request.user, plan.schueler):
        raise PermissionDenied
    form = EintragForm(request.POST, prefix="eintrag")
    if form.is_valid():
        e = form.save(commit=False)
        e.plan, e.schueler, e.verfasst_von = plan, plan.schueler, request.user
        e.save()
        messages.success(request, gettext("Verlaufseintrag gespeichert."))
    else:
        messages.error(request, gettext("Eintrag nicht gespeichert – bitte Datum und Text angeben."))
    return redirect("foerderplan", plan.pk)


@login_required
@require_POST
def aushaendigung_anlegen(request):
    dokument = _dokument_aus_post(request)
    if not darf_foerderung_bearbeiten(request.user, dokument.schueler):
        raise PermissionDenied
    form = AushaendigungForm(request.POST, prefix="aush", dokument=dokument)
    if form.is_valid():
        a = form.save(commit=False)
        a.erfasst_von = request.user
        a.save()
        messages.success(request, gettext("Aushändigung an %(person)s vermerkt.") % {"person": a.empfaenger.anzeigename})
    else:
        messages.error(request, gettext("Aushändigung nicht gespeichert – bitte Empfänger:in und Datum angeben."))
    return _zurueck(dokument)


@login_required
@require_POST
def erhalt_bestaetigen(request, pk):
    a = get_object_or_404(Aushaendigung.objects.select_related("foerderplan__schueler", "nachteilsausgleich__schueler"), pk=pk)
    if not darf_foerderung_bearbeiten(request.user, a.schueler):
        raise PermissionDenied
    form = BestaetigungForm(request.POST, prefix="best")
    if form.is_valid() and form.cleaned_data["bestaetigt_am"] >= a.ausgehaendigt_am:
        a.bestaetigt_am = form.cleaned_data["bestaetigt_am"]
        a.bestaetigung = form.cleaned_data["bestaetigung"]
        a.bestaetigt_durch_konto = request.user
        a.save()
        messages.success(request, gettext("Erhalt durch %(person)s bestätigt.") % {"person": a.empfaenger.anzeigename})
    else:
        messages.error(request, gettext("Bitte ein gültiges Datum angeben (nicht vor der Aushändigung)."))
    return _zurueck(a.dokument)
