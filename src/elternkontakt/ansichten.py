"""Portalansichten der Elternkommunikation für Beschäftigte."""
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Exists, F, OuterRef, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy as _, ngettext
from django.views.decorators.http import require_POST

from portal.rechte import ist_verwaltung, koordinierte_jahrgaenge, personal_von
from stammdaten.models import Abschnitt, Gruppe, Mitgliedschaft, Schuelerprofil, Schuljahr

from . import rechte
from .models import Benachrichtigungsregel, Empfaenger, Gespraech
from .pruefung import betroffene, regel_anwenden
from .versand import (antwort_der_schule, beitraege_fuer_eltern, gespraech_anlegen, kontakte_fuer, standard_empfaenger,
                      zustellen)

UNGELESEN = Q(eltern_antwort_am__isnull=False) & (Q(schule_gelesen_am__isnull=True) | Q(eltern_antwort_am__gt=F("schule_gelesen_am")))


def offen_filter():
    return Q(bestaetigung_erbeten=True) & Exists(Empfaenger.objects.filter(gespraech=OuterRef("pk"), bestaetigt_am__isnull=True))


# ---------------------------------------------------------------- Formulare

class NachrichtForm(forms.Form):
    betreff = forms.CharField(label=_("Betreff"), max_length=200)
    text = forms.CharField(label=_("Nachricht"), widget=forms.Textarea(attrs={"rows": 9}), max_length=8000)
    bestaetigung = forms.BooleanField(label=_("Lesebestätigung erbitten"), required=False)
    antworten = forms.BooleanField(label=_("Eltern dürfen antworten"), required=False, initial=True)


class AntwortForm(forms.Form):
    text = forms.CharField(label=_("Antwort"), widget=forms.Textarea(attrs={"rows": 4}), max_length=8000)


class RegelForm(forms.ModelForm):
    jetzt_benachrichtigen = forms.BooleanField(
        label=_("Bereits erreichte Schwellen jetzt benachrichtigen"), required=False,
        help_text=_("Sonst werden Schüler:innen, die die Schwelle schon erreicht haben, still vorgemerkt und erst "
                    "bei der nächsten Stufe benachrichtigt."))

    class Meta:
        model = Benachrichtigungsregel
        fields = ["name", "merkmal", "zaehlung", "schwelle", "zeitraum", "jahrgang_von", "jahrgang_bis", "wiederholen",
                  "bestaetigung_erbeten", "zusatztext", "aktiv"]
        widgets = {"zusatztext": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, erlaubt=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.erlaubt = erlaubt
        jahrgaenge = sorted(erlaubt) if erlaubt is not None else list(range(1, 14))
        leer = [] if erlaubt is not None else [("", _("alle"))]
        for feld in ("jahrgang_von", "jahrgang_bis"):
            self.fields[feld].widget = forms.Select(choices=leer + [(j, j) for j in jahrgaenge])
            self.fields[feld].required = erlaubt is not None
        if erlaubt is not None and not self.instance.pk:
            self.initial.setdefault("jahrgang_von", min(jahrgaenge) if jahrgaenge else None)
            self.initial.setdefault("jahrgang_bis", max(jahrgaenge) if jahrgaenge else None)

    def clean(self):
        daten = super().clean()
        von, bis = daten.get("jahrgang_von"), daten.get("jahrgang_bis")
        if von and bis and bis < von:
            raise forms.ValidationError(_("„Jahrgang bis“ darf nicht vor „Jahrgang von“ liegen."))
        if self.erlaubt is not None:
            if not (von and bis) or not set(range(von, bis + 1)) <= set(self.erlaubt):
                raise forms.ValidationError(_("Sie können Regeln nur für die Jahrgänge Ihrer Stufe anlegen."))
        return daten


# ---------------------------------------------------------------- Hilfen

def _gruppen_fuer(user):
    """Gruppen des aktuellen Schuljahres, deren Eltern die Person anschreiben darf (für „An eine Klasse schreiben“)."""
    sj = Schuljahr.aktuelles()
    if sj is None:
        return Gruppe.objects.none()
    qs = Gruppe.objects.filter(schuljahr=sj).exclude(typ=Gruppe.AG)
    if ist_verwaltung(user):
        return qs.filter(typ=Gruppe.STAMMKLASSE).order_by("jahrgang", "name")
    personal = personal_von(user)
    q = Q(pk__in=[])
    if personal:
        from noten.models import Unterricht

        q |= Q(leitung=personal, typ=Gruppe.STAMMKLASSE) | Q(leitung2=personal, typ=Gruppe.STAMMKLASSE)
        q |= Q(pk__in=Unterricht.objects.filter(lehrkraft=personal, abschnitt__schuljahr=sj).values("gruppe"))
    jahrgaenge = koordinierte_jahrgaenge(user)
    if jahrgaenge:
        q |= Q(typ=Gruppe.STAMMKLASSE, jahrgang__in=jahrgaenge)
    return qs.filter(q).distinct().order_by("typ", "jahrgang", "name")


def gruppe_erlaubt(user, gruppe):
    return user.has_perm("elternkontakt.add_gespraech") and _gruppen_fuer(user).filter(pk=gruppe.pk).exists()


def _empfaengerstatus(g):
    e = list(g.empfaenger.all())
    return {
        "gesamt": len(e), "gelesen": sum(1 for x in e if x.gelesen_am), "bestaetigt": sum(1 for x in e if x.bestaetigt_am),
        "ohne_email": sum(1 for x in e if x.versand_status == Empfaenger.OHNE_EMAIL),
        "fehler": sum(1 for x in e if x.versand_status == Empfaenger.FEHLER),
        "wartet": sum(1 for x in e if x.versand_status == Empfaenger.WARTET),
    }


# ---------------------------------------------------------------- Übersicht

@login_required
def uebersicht(request):
    alle = rechte.sichtbare_gespraeche(request.user)
    tab = request.GET.get("tab") or "alle"
    q = (request.GET.get("q") or "").strip()
    art = request.GET.get("art") or ""
    klasse_id = request.GET.get("klasse") or ""

    tabs_def = [("alle", _("Alle"), Q()), ("antworten", _("Neue Antworten"), UNGELESEN),
                ("offen", _("Bestätigung offen"), offen_filter()), ("meine", _("Von mir begonnen"), Q(erstellt_von=request.user))]
    tabs = []
    for schluessel, name, filt in tabs_def:
        tabs.append({"schluessel": schluessel, "name": name, "anzahl": alle.filter(filt).count(), "aktiv": schluessel == tab,
                     "url": f"?tab={schluessel}"})
    qs = alle.filter(dict((t[0], t[2]) for t in tabs_def).get(tab, Q()))
    if art in dict(Gespraech.ARTEN):
        qs = qs.filter(art=art)
    if q:
        for teil in q.split():
            qs = qs.filter(Q(schueler__person__nachname__icontains=teil) | Q(schueler__person__vorname__icontains=teil)
                           | Q(betreff__icontains=teil))
    klassen = Gruppe.objects.filter(schuljahr=Schuljahr.aktuelles(), typ=Gruppe.STAMMKLASSE).order_by("jahrgang", "name")
    if klasse_id.isdigit():
        qs = qs.filter(schueler__in=Mitgliedschaft.objects.aktiv().filter(gruppe_id=klasse_id).values("schueler"))
    qs = (qs.select_related("schueler__person", "erstellt_von__person")
          .annotate(n_empf=Count("empfaenger", distinct=True),
                    n_best=Count("empfaenger", filter=Q(empfaenger__bestaetigt_am__isnull=False), distinct=True),
                    n_gel=Count("empfaenger", filter=Q(empfaenger__gelesen_am__isnull=False), distinct=True),
                    n_beitr=Count("beitraege", distinct=True))
          .order_by("-letzte_aktivitaet"))[:300]
    return render(request, "elternkontakt/uebersicht.html", {
        "zeilen": qs, "tabs": tabs, "tab": tab, "q": q, "art": art, "arten": Gespraech.ARTEN, "klassen": klassen,
        "klasse_id": klasse_id, "darf_schreiben": rechte.anschreibbare_schueler_ids(request.user) != set(),
        "darf_regeln": rechte.darf_regeln(request.user),
    })


# ---------------------------------------------------------------- Neue Nachricht

@login_required
def neu(request):
    user = request.user
    schueler = gruppe = None
    if request.GET.get("schueler", "").isdigit():
        schueler = get_object_or_404(Schuelerprofil.objects.select_related("person"), pk=request.GET["schueler"])
        if not rechte.darf_schreiben(user, schueler):
            raise PermissionDenied
    elif request.GET.get("gruppe", "").isdigit():
        gruppe = get_object_or_404(_gruppen_fuer(user), pk=request.GET["gruppe"])
    else:
        gruppen = list(_gruppen_fuer(user))
        if not gruppen and rechte.anschreibbare_schueler_ids(user) == set():
            raise PermissionDenied
        return render(request, "elternkontakt/neu_auswahl.html", {"gruppen": gruppen})

    form = NachrichtForm(request.POST or None)
    if schueler:
        kontakte = list(kontakte_fuer(schueler))
        gewaehlt = ({int(x) for x in request.POST.getlist("empfaenger") if x.isdigit()} if request.method == "POST"
                    else {b.person_id for b in kontakte if b.sorgerecht})
        zeilen = [{"b": b, "gewaehlt": b.person_id in gewaehlt} for b in kontakte]
    else:
        erlaubt = rechte.anschreibbare_schueler_ids(user)
        mitglieder = [s for s in gruppe.aktuelle_mitglieder().order_by("person__nachname", "person__vorname")
                      if erlaubt is None or s.pk in erlaubt]
        gewaehlt = ({int(x) for x in request.POST.getlist("schueler") if x.isdigit()} if request.method == "POST"
                    else {s.pk for s in mitglieder})
        zeilen = [{"s": s, "empf": standard_empfaenger(s), "gewaehlt": s.pk in gewaehlt} for s in mitglieder]

    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        kwargs = dict(betreff=d["betreff"], text=d["text"], von=user, bestaetigung=d["bestaetigung"], antworten=d["antworten"])
        if schueler:
            personen = [z["b"].person for z in zeilen if z["gewaehlt"]]
            if not personen:
                form.add_error(None, gettext("Bitte mindestens eine Empfängerin oder einen Empfänger wählen."))
            else:
                g = gespraech_anlegen(schueler, personen, **kwargs)
                messages.success(request, _meldung_versand(len(personen)))
                return redirect("elterngespraech", g.pk)
        else:
            ausgewaehlt = [z for z in zeilen if z["gewaehlt"] and z["empf"]]
            if not ausgewaehlt:
                form.add_error(None, gettext("Bitte mindestens eine Schülerin oder einen Schüler mit Kontaktperson wählen."))
            else:
                n = 0
                for z in ausgewaehlt:
                    gespraech_anlegen(z["s"], [b.person for b in z["empf"]], **kwargs)
                    n += len(z["empf"])
                messages.success(request, ngettext(
                    "Nachricht an die Eltern von %(s)d Schüler:in angelegt (%(n)d Empfänger:innen).",
                    "Nachricht an die Eltern von %(s)d Schüler:innen angelegt (%(n)d Empfänger:innen).",
                    len(ausgewaehlt)) % {"s": len(ausgewaehlt), "n": n})
                return redirect(reverse("elternkontakt") + "?tab=meine")
    return render(request, "elternkontakt/neu.html", {"form": form, "schueler": schueler, "gruppe": gruppe, "zeilen": zeilen})


def _meldung_versand(n):
    from django.conf import settings

    if settings.ELTERN_EMAIL_VERSAND:
        return ngettext("Nachricht an %(n)d Empfänger:in versendet.", "Nachricht an %(n)d Empfänger:innen versendet.", n) % {"n": n}
    return ngettext("Nachricht für %(n)d Empfänger:in gespeichert (E-Mail-Versand ist ausgeschaltet – Postausgang).",
                    "Nachricht für %(n)d Empfänger:innen gespeichert (E-Mail-Versand ist ausgeschaltet – Postausgang).", n) % {"n": n}


# ---------------------------------------------------------------- Gesprächsverlauf

@login_required
def gespraech(request, pk):
    g = get_object_or_404(Gespraech.objects.select_related("schueler__person", "erstellt_von__person", "zeugnis"), pk=pk)
    if not rechte.darf_sehen(request.user, g):
        raise PermissionDenied
    darf_antworten = rechte.darf_antworten(request.user, g)
    darf_verwalten = rechte.darf_verwalten(request.user, g)
    form = AntwortForm()

    if request.method == "POST":
        aktion = request.POST.get("aktion")
        if aktion == "antworten":
            if not darf_antworten:
                raise PermissionDenied
            form = AntwortForm(request.POST)
            if form.is_valid():
                antwort_der_schule(g, form.cleaned_data["text"], request.user)
                if g.abgeschlossen:
                    g.abgeschlossen = False
                    g.save(update_fields=["abgeschlossen"])
                messages.success(request, gettext("Antwort gespeichert; die Eltern werden benachrichtigt."))
                return redirect("elterngespraech", g.pk)
        elif aktion in ("vermerken", "erneut", "abschliessen", "oeffnen"):
            if not darf_verwalten:
                raise PermissionDenied
            if aktion == "vermerken":
                e = get_object_or_404(g.empfaenger, pk=request.POST.get("empfaenger"))
                if e.bestaetigen("schule", request.user, request.POST.get("notiz", "").strip()):
                    messages.success(request, gettext("Bestätigung für %(name)s vermerkt.") % {"name": e.person.anzeigename})
            elif aktion == "erneut":
                e = get_object_or_404(g.empfaenger, pk=request.POST.get("empfaenger"))
                zustellen(e)
                messages.info(request, gettext("Zustellung: %(status)s") % {"status": e.get_versand_status_display()})
            else:
                g.abgeschlossen = aktion == "abschliessen"
                g.save(update_fields=["abgeschlossen"])
            return redirect("elterngespraech", g.pk)
        else:
            raise Http404

    if g.ungelesen:
        g.schule_gelesen_am = timezone.now()
        g.save(update_fields=["schule_gelesen_am"])
    return render(request, "elternkontakt/gespraech.html", {
        "g": g, "beitraege": g.beitraege.select_related("von_benutzer__person", "von_person"),
        "empfaenger": g.empfaenger.select_related("person", "bestaetigung_vermerkt_von__person"),
        "status": _empfaengerstatus(g), "form": form, "darf_antworten": darf_antworten, "darf_verwalten": darf_verwalten,
        "klasse": g.schueler.stammklasse(),
    })


@login_required
def elternansicht(request, pk, epk):
    """Vorschau: so sieht die Empfängerin / der Empfänger den Verlauf (ohne Knöpfe, ohne Lesevermerk)."""
    g = get_object_or_404(Gespraech, pk=pk)
    if not rechte.darf_sehen(request.user, g):
        raise PermissionDenied
    e = get_object_or_404(g.empfaenger.select_related("person"), pk=epk)
    return render(request, "elternkontakt/eltern_nachricht.html", {
        "e": e, "g": g, "beitraege": beitraege_fuer_eltern(g, e.person), "vorschau": True,
    })


# ---------------------------------------------------------------- Benachrichtigungsregeln

def _regeln_erlaubt(request):
    if not rechte.darf_regeln(request.user):
        raise PermissionDenied
    return rechte.regel_jahrgaenge(request.user)


@login_required
def regeln(request):
    erlaubt = _regeln_erlaubt(request)
    liste = []
    for r in Benachrichtigungsregel.objects.annotate(
            n_ausl=Count("ausloesungen", filter=Q(ausloesungen__still=False))):
        liste.append({"r": r, "darf": rechte.darf_regel_bearbeiten(request.user, r)})
    erlaubt_text = ", ".join(str(j) for j in sorted(erlaubt)) if erlaubt is not None else ""
    return render(request, "elternkontakt/regeln.html", {"regeln": liste, "erlaubt": erlaubt, "erlaubt_text": erlaubt_text})


@login_required
def regel_bearbeiten(request, pk=None):
    erlaubt = _regeln_erlaubt(request)
    regel = None
    if pk is not None:
        regel = get_object_or_404(Benachrichtigungsregel, pk=pk)
        if not rechte.darf_regel_bearbeiten(request.user, regel):
            raise PermissionDenied
    form = RegelForm(request.POST or None, instance=regel, erlaubt=erlaubt)
    vorschau = None
    if request.method == "POST" and form.is_valid():
        if "vorschau" in request.POST:
            vorschau = betroffene(form.save(commit=False))
        else:
            neu_angelegt = regel is None
            regel = form.save(commit=False)
            if neu_angelegt:
                regel.erstellt_von = request.user
            regel.save()
            n = regel_anwenden(regel, benachrichtigen=form.cleaned_data["jetzt_benachrichtigen"])
            if n and form.cleaned_data["jetzt_benachrichtigen"]:
                messages.success(request, ngettext("Regel gespeichert; %(n)d Benachrichtigung ausgelöst.",
                                                   "Regel gespeichert; %(n)d Benachrichtigungen ausgelöst.", n) % {"n": n})
            elif n:
                messages.success(request, ngettext(
                    "Regel gespeichert; %(n)d Schüler:in hat die Schwelle bereits erreicht und wurde still vorgemerkt.",
                    "Regel gespeichert; %(n)d Schüler:innen haben die Schwelle bereits erreicht und wurden still vorgemerkt.",
                    n) % {"n": n})
            else:
                messages.success(request, gettext("Regel gespeichert."))
            return redirect("elternkontakt_regeln")
    elif regel is not None and request.method == "GET":
        vorschau = betroffene(regel)
    return render(request, "elternkontakt/regel.html", {"form": form, "regel": regel, "vorschau": vorschau, "erlaubt": erlaubt})


@login_required
@require_POST
def regel_loeschen(request, pk):
    _regeln_erlaubt(request)
    regel = get_object_or_404(Benachrichtigungsregel, pk=pk)
    if not rechte.darf_regel_bearbeiten(request.user, regel):
        raise PermissionDenied
    regel.delete()
    messages.success(request, gettext("Regel gelöscht. Bereits versendete Nachrichten bleiben erhalten."))
    return redirect("elternkontakt_regeln")


# ---------------------------------------------------------------- Zeugnisempfang

def zeugnisempfang_status(klasse, abschnitt):
    """Je Zeugnis-ID: {'angefordert', 'bestaetigt', 'gesamt', 'gespraech'} für die Zeugnisliste einer Klasse."""
    status = {}
    for g in (Gespraech.objects.filter(art=Gespraech.ZEUGNIS, zeugnis__klasse=klasse, zeugnis__abschnitt=abschnitt)
              .annotate(n=Count("empfaenger"), b=Count("empfaenger", filter=Q(empfaenger__bestaetigt_am__isnull=False)))):
        status[g.zeugnis_id] = {"gespraech": g.pk, "gesamt": g.n, "bestaetigt": g.b}
    return status


@login_required
@require_POST
def zeugnisempfang(request, klasse_pk, abschnitt_pk):
    from zeugnisse.models import Zeugnis

    klasse = get_object_or_404(Gruppe, pk=klasse_pk)
    abschnitt = get_object_or_404(Abschnitt, pk=abschnitt_pk)
    if not rechte.darf_zeugnisempfang(request.user, klasse):
        raise PermissionDenied
    vorhanden = set(Gespraech.objects.filter(art=Gespraech.ZEUGNIS, zeugnis__klasse=klasse, zeugnis__abschnitt=abschnitt)
                    .values_list("zeugnis_id", flat=True))
    n = ohne = 0
    for z in (Zeugnis.objects.filter(klasse=klasse, abschnitt=abschnitt, status=Zeugnis.FREIGEGEBEN)
              .exclude(pk__in=vorhanden).select_related("schueler__person")):
        personen = [b.person for b in standard_empfaenger(z.schueler)]
        if not personen:
            ohne += 1
            continue
        gespraech_anlegen(
            z.schueler, personen, von=request.user, art=Gespraech.ZEUGNIS, vorlage="zeugnis", bestaetigung=True, zeugnis=z,
            daten={"zeugnis_art": z.art, "zeitraum": "halbjahr", "zeitraum_id": abschnitt.pk,
                   "vorname": z.schueler.person.rufname or z.schueler.person.vorname})
        n += 1
    if n:
        messages.success(request, ngettext("Empfangsbestätigung für %(n)d Zeugnis angefordert.",
                                           "Empfangsbestätigung für %(n)d Zeugnisse angefordert.", n) % {"n": n})
    else:
        messages.info(request, gettext("Keine freigegebenen Zeugnisse ohne Anfrage."))
    if ohne:
        messages.warning(request, ngettext("%(n)d Schüler:in ohne sorgeberechtigte Kontaktperson – bitte direkt klären.",
                                           "%(n)d Schüler:innen ohne sorgeberechtigte Kontaktperson – bitte direkt klären.",
                                           ohne) % {"n": ohne})
    return redirect(request.POST.get("zurueck") or reverse("elternkontakt"))


# ---------------------------------------------------------------- Startseite und Schülerakte

def start_hinweise(user):
    if not user.has_perm("elternkontakt.view_gespraech"):
        return None
    sichtbar = rechte.sichtbare_gespraeche(user)
    ungelesen = list(sichtbar.filter(UNGELESEN).select_related("schueler__person").order_by("-eltern_antwort_am")[:6])
    offen = sichtbar.filter(offen_filter()).filter(Q(erstellt_von=user) | Q(art=Gespraech.ZEUGNIS)).count()
    seit = timezone.now() - timedelta(days=14)
    automatisch = list(sichtbar.filter(art=Gespraech.FEHLZEITEN, erstellt_am__gte=seit).exclude(
        pk__in=[g.pk for g in ungelesen]).select_related("schueler__person")[:5])
    if not (ungelesen or offen or automatisch) and rechte.anschreibbare_schueler_ids(user) == set():
        return None
    return {"ungelesen": ungelesen, "n_ungelesen": sichtbar.filter(UNGELESEN).count(), "offen": offen,
            "automatisch": automatisch}


def akte_kontext(user, schueler):
    if not user.has_perm("elternkontakt.view_gespraech"):
        return None
    return {
        "gespraeche": rechte.sichtbare_gespraeche(user).filter(schueler=schueler).annotate(
            n_empf=Count("empfaenger", distinct=True),
            n_best=Count("empfaenger", filter=Q(empfaenger__bestaetigt_am__isnull=False), distinct=True))[:12],
        "darf_schreiben": rechte.darf_schreiben(user, schueler),
    }
