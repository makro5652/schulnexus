"""Bausteine der Startseite: Schnellzugriff, Geburtstage, Notizen und Personensuche."""
import calendar
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy as _
from django.views.decorators.http import require_POST

from stammdaten.models import Gruppe, Mitgliedschaft, Person, Personalprofil, Schuelerprofil, Schuljahr

from .models import Notiz
from .rechte import (
    darf_akte_sehen, ist_foerderkoordination, ist_personalverwaltung, ist_verwaltung, klassenleitung_schueler_ids,
    personal_von, unterrichtete_schueler_ids,
)

TAGE_VORAUS = 7


# ---------------------------------------------------------------- Begrüßung

def begruessung(jetzt=None):
    stunde = timezone.localtime(jetzt).hour
    if stunde < 11:
        return gettext("Guten Morgen")
    if stunde < 17:
        return gettext("Guten Tag")
    return gettext("Guten Abend")


# ---------------------------------------------------------------- Schnellzugriff

def schnellzugriff(user, sj):
    """Direkte Wege zu den eigenen Klassen, Kursen und den Bereichen der jeweiligen Rolle."""
    from noten.models import Unterricht

    personal = personal_von(user)
    klassen, kurse = [], []
    if personal and sj:
        for g in Gruppe.objects.filter(leitung=personal, schuljahr=sj).order_by("typ", "name"):
            klassen.append({"titel": g.name, "unter": g.get_typ_display(), "url": reverse("klassenliste", args=[g.pk]),
                            "anzahl": Mitgliedschaft.objects.aktiv().filter(gruppe=g).count()})
        for u in (Unterricht.objects.filter(lehrkraft=personal, abschnitt__schuljahr=sj)
                  .select_related("fach", "gruppe", "abschnitt").order_by("abschnitt__nummer", "gruppe__name", "fach__reihenfolge")):
            kurse.append({"titel": f"{u.fach.lokal_name} {u.gruppe.name}", "unter": u.abschnitt.lokal_name,
                          "url": reverse("notenuebersicht", args=[u.pk])})

    bereiche = []
    if user.is_staff:
        if ist_verwaltung(user):
            bereiche += [
                {"titel": gettext("Schüler:innen"), "url": reverse("admin:stammdaten_schuelerprofil_changelist"), "symbol": "personen"},
                {"titel": gettext("Klassen und Gruppen"), "url": reverse("admin:stammdaten_gruppe_changelist"), "symbol": "gruppen"},
                {"titel": gettext("Fehlzeiten"), "url": reverse("admin:fehlzeiten_fehlzeit_changelist"), "symbol": "uhr"},
                {"titel": gettext("Nachmittag / AGs"), "url": reverse("admin:nachmittag_agangebot_changelist"), "symbol": "ball"},
            ]
        if ist_foerderkoordination(user) or (klassenleitung_schueler_ids(user) and user.has_perm("foerderung.view_foerderplan")):
            bereiche.append({"titel": gettext("Förderpläne"), "url": reverse("admin:foerderung_foerderplan_changelist"), "symbol": "pflanze"})
        if user.has_perm("foerderung.view_nachteilsausgleich"):
            bereiche.append({"titel": gettext("Nachteilsausgleiche"),
                             "url": reverse("admin:foerderung_nachteilsausgleich_changelist") + "?gueltig=aktiv", "symbol": "waage"})
        if ist_personalverwaltung(user) or ist_verwaltung(user):
            bereiche.append({"titel": gettext("Personal"), "url": reverse("admin:stammdaten_personalprofil_changelist"), "symbol": "ausweis"})
        if user.has_perm("stammdaten.view_dokument"):
            bereiche.append({"titel": gettext("Anhänge"), "url": reverse("admin:stammdaten_dokument_changelist"), "symbol": "klammer"})
        bereiche.append({"titel": gettext("Verwaltung"), "url": reverse("admin:index"), "symbol": "zahnrad"})
    return {"klassen": klassen, "kurse": kurse, "bereiche": bereiche}


# ---------------------------------------------------------------- Geburtstage

def _naechster_geburtstag(geburtsdatum, heute):
    """Datum des nächsten Geburtstags (heute eingeschlossen); 29. Februar in Nicht-Schaltjahren am 28. Februar."""
    for jahr in (heute.year, heute.year + 1):
        tag = geburtsdatum.day
        if geburtsdatum.month == 2 and tag == 29 and not calendar.isleap(jahr):
            tag = 28
        kandidat = geburtsdatum.replace(year=jahr, day=tag)
        if kandidat >= heute:
            return kandidat
    return None


def _tagesfilter(heute, tage):
    q = Q()
    for i in range(tage + 1):
        t = heute + timedelta(days=i)
        q |= Q(geburtsdatum__month=t.month, geburtsdatum__day=t.day)
        if t.month == 2 and t.day == 28 and not calendar.isleap(t.year):
            q |= Q(geburtsdatum__month=2, geburtsdatum__day=29)
    return q


def sichtbare_schueler_fuer_geburtstage(user):
    """Verwaltung, Leitung und Förderkoordination: alle aktiven; Lehrkräfte: eigene Klassen, Gruppen und Kurse."""
    qs = Schuelerprofil.objects.filter(status="aktiv")
    if ist_verwaltung(user) or ist_foerderkoordination(user):
        return qs
    personal = personal_von(user)
    if not personal:
        return qs.none()
    sj = Schuljahr.aktuelles()
    geleitet = Mitgliedschaft.objects.aktiv().filter(gruppe__leitung=personal, gruppe__schuljahr=sj).values("schueler")
    ids = unterrichtete_schueler_ids(user) | klassenleitung_schueler_ids(user)
    return qs.filter(Q(pk__in=ids) | Q(pk__in=geleitet))


def geburtstage(user, heute=None, tage=TAGE_VORAUS):
    """Geburtstage von heute bis in `tage` Tagen, nach Datum gruppiert."""
    heute = heute or timezone.localdate()
    if not user.is_authenticated:
        return []
    filter_tage = _tagesfilter(heute, tage)
    eintraege = []

    schueler = (sichtbare_schueler_fuer_geburtstage(user)
                .filter(person__geburtstag_anzeigen=True, person__in=Person.objects.filter(filter_tage))
                .select_related("person"))
    sj = Schuljahr.aktuelles()
    klassen = {}
    if sj:
        for m in Mitgliedschaft.objects.aktiv().filter(schueler__in=schueler, gruppe__typ=Gruppe.STAMMKLASSE,
                                                       gruppe__schuljahr=sj).select_related("gruppe"):
            klassen[m.schueler_id] = m.gruppe.name
    for s in schueler:
        tag = _naechster_geburtstag(s.person.geburtsdatum, heute)
        if tag is None:
            continue
        eintraege.append({
            "tag": tag, "name": s.person.anzeigename, "art": "schueler",
            "zusatz": gettext("Klasse %(klasse)s") % {"klasse": klassen[s.pk]} if s.pk in klassen else "",
            "alter": tag.year - s.person.geburtsdatum.year,
            "url": reverse("schuelerakte", args=[s.pk]) if darf_akte_sehen(user, s) else "",
        })

    if personal_von(user) or user.is_staff:
        kollegium = (Personalprofil.objects.filter(aktiv=True, person__geburtstag_anzeigen=True,
                                                   person__geburtsdatum__isnull=False)
                     .filter(person__in=Person.objects.filter(filter_tage)).select_related("person", "bereich"))
        for pp in kollegium:
            tag = _naechster_geburtstag(pp.person.geburtsdatum, heute)
            if tag is None:
                continue
            eintraege.append({
                "tag": tag, "name": pp.person.anzeigename, "art": "personal",
                "zusatz": pp.stellenbezeichnung or (pp.bereich.lokal_name if pp.bereich else ""),
                "alter": None, "url": "", "ich": pp.person.benutzer_id == user.pk,
            })

    eintraege.sort(key=lambda e: (e["tag"], e["art"] != "personal", e["name"]))
    gruppen = []
    for e in eintraege:
        if not gruppen or gruppen[-1]["tag"] != e["tag"]:
            abstand = (e["tag"] - heute).days
            gruppen.append({"tag": e["tag"], "abstand": abstand, "eintraege": []})
        gruppen[-1]["eintraege"].append(e)
    return gruppen


# ---------------------------------------------------------------- Notizen

class NotizForm(forms.ModelForm):
    class Meta:
        model = Notiz
        fields = ["text", "farbe", "datum", "sichtbarkeit", "angeheftet"]
        widgets = {
            "text": forms.Textarea(attrs={"rows": 3, "placeholder": _("Notiz schreiben …")}),
            "datum": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "farbe": forms.RadioSelect,
        }

    def __init__(self, *args, darf_mitteilen=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["datum"].help_text = ""
        if not darf_mitteilen:
            del self.fields["sichtbarkeit"]


def darf_mitteilen(user):
    """Mitteilungen an alle: Verwaltung und Schulleitung."""
    return ist_verwaltung(user)


def notizen_fuer(user, heute=None):
    heute = heute or timezone.localdate()
    eigene = list(Notiz.objects.filter(besitzer=user, sichtbarkeit=Notiz.PRIVAT))
    mitteilungen = list(
        Notiz.objects.filter(sichtbarkeit=Notiz.ALLE, erledigt=False)
        .filter(Q(datum__isnull=True) | Q(datum__gte=heute))
        .select_related("besitzer", "besitzer__person").order_by("-angeheftet", "-erstellt_am")
    )
    for n in mitteilungen:
        n.darf_bearbeiten = n.besitzer_id == user.pk or darf_mitteilen(user)
    for n in eigene + mitteilungen:
        n.form = NotizForm(instance=n, prefix=f"n{n.pk}", darf_mitteilen=darf_mitteilen(user))
    return {
        "offen": [n for n in eigene if not n.erledigt],
        "erledigt": [n for n in eigene if n.erledigt][:20],
        "mitteilungen": mitteilungen,
        "form": NotizForm(prefix="notiz", darf_mitteilen=darf_mitteilen(user)),
        "darf_mitteilen": darf_mitteilen(user),
    }


def _eigene_notiz(request, pk):
    notiz = get_object_or_404(Notiz, pk=pk)
    erlaubt = notiz.besitzer_id == request.user.pk or (notiz.sichtbarkeit == Notiz.ALLE and darf_mitteilen(request.user))
    if not erlaubt:
        raise PermissionDenied
    return notiz


def _zur_startseite():
    return redirect(reverse("start") + "#notizen")


@login_required
@require_POST
def notiz_anlegen(request):
    form = NotizForm(request.POST, prefix="notiz", darf_mitteilen=darf_mitteilen(request.user))
    if form.is_valid():
        n = form.save(commit=False)
        n.besitzer = request.user
        n.save()
    else:
        messages.error(request, gettext("Notiz nicht gespeichert – bitte einen Text eingeben."))
    return _zur_startseite()


@login_required
@require_POST
def notiz_aendern(request, pk):
    notiz = _eigene_notiz(request, pk)
    form = NotizForm(request.POST, instance=notiz, prefix=f"n{pk}", darf_mitteilen=darf_mitteilen(request.user))
    if form.is_valid():
        form.save()
    else:
        messages.error(request, gettext("Notiz nicht gespeichert – bitte einen Text eingeben."))
    return _zur_startseite()


@login_required
@require_POST
def notiz_aktion(request, pk):
    notiz = _eigene_notiz(request, pk)
    aktion = request.POST.get("aktion")
    if aktion == "erledigt":
        notiz.erledigt = not notiz.erledigt
        notiz.angeheftet = False if notiz.erledigt else notiz.angeheftet
        notiz.save(update_fields=["erledigt", "angeheftet", "geaendert_am"])
    elif aktion == "anheften":
        notiz.angeheftet = not notiz.angeheftet
        notiz.save(update_fields=["angeheftet", "geaendert_am"])
    elif aktion == "loeschen":
        notiz.delete()
    return _zur_startseite()


@login_required
@require_POST
def erledigte_loeschen(request):
    Notiz.objects.filter(besitzer=request.user, sichtbarkeit=Notiz.PRIVAT, erledigt=True).delete()
    return _zur_startseite()


# ---------------------------------------------------------------- Personensuche

@login_required
def suche(request):
    q = (request.GET.get("q") or "").strip()
    schueler, personal, eltern = [], [], []
    if len(q) >= 2:
        teile = q.split()
        namensfilter = Q()
        for t in teile:
            namensfilter &= Q(vorname__icontains=t) | Q(nachname__icontains=t) | Q(rufname__icontains=t)
        personen = Person.objects.filter(namensfilter)

        sichtbar = sichtbare_schueler_fuer_geburtstage(request.user)  # gleiche Regel: eigene bzw. alle
        sj = Schuljahr.aktuelles()
        for s in sichtbar.filter(person__in=personen).select_related("person")[:50]:
            klasse = s.stammklasse(sj)
            schueler.append({"s": s, "klasse": klasse, "akte": darf_akte_sehen(request.user, s)})

        if request.user.is_staff:
            for pp in Personalprofil.objects.filter(aktiv=True, person__in=personen).select_related("person", "bereich")[:50]:
                personal.append({"pp": pp, "link": ist_personalverwaltung(request.user) or ist_verwaltung(request.user)})
        if ist_verwaltung(request.user):
            eltern = list(personen.filter(kinder_beziehungen__isnull=False).distinct()
                          .prefetch_related("kinder_beziehungen__schueler__person")[:50])
    return render(request, "portal/suche.html", {
        "q": q, "schueler": schueler, "personal": personal, "eltern": eltern, "zu_kurz": 0 < len(q) < 2,
    })
