"""
Zuordnen von Schüler:innen zu Klassen, Lerngruppen und AGs – schnelle Arbeitsseite.

Grundsatz wie im Datenmodell: Mitgliedschaften werden nicht gelöscht, sondern zum Stichtag beendet;
so bleibt die Historie erhalten. Nur Einträge, die am Stichtag noch gar nicht begonnen haben
(Tippfehler, gleich wieder entfernt), werden tatsächlich gelöscht.
"""
from datetime import timedelta
from urllib.parse import urlencode

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import formats, timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext, gettext_lazy as _
from django.views.decorators.http import require_POST

from stammdaten.models import Gruppe, Laufbahnabschnitt, Mitgliedschaft, Person, Personalprofil, Schuelerprofil, Schuljahr

from .rechte import ist_it, ist_verwaltung, koordinierte_jahrgaenge


# ---------------------------------------------------------------- Rechte

def alle_jahrgaenge(user):
    """Verwaltung (Sekretariat, Verwaltungsleitung, Schulleitung) und IT-Administration arbeiten in allen Jahrgängen."""
    return ist_verwaltung(user) or ist_it(user)


def darf_zuordnen(user):
    """Verwaltung, IT-Administration oder Stufenkoordination mit Mitgliedschaftsrechten."""
    if not user.has_perm("stammdaten.change_mitgliedschaft"):
        return False
    return alle_jahrgaenge(user) or bool(koordinierte_jahrgaenge(user))


def gruppen_fuer(user, sj):
    qs = Gruppe.objects.filter(schuljahr=sj)
    if alle_jahrgaenge(user):
        return qs
    return qs.filter(jahrgang__in=koordinierte_jahrgaenge(user))


def darf_gruppe_bearbeiten(user, gruppe):
    return darf_zuordnen(user) and (alle_jahrgaenge(user) or gruppe.jahrgang in koordinierte_jahrgaenge(user))


def darf_schueler_anlegen(user):
    """Neue Schüler:innen direkt anlegen: wer Personen und Schülerprofile anlegen darf (Sekretariat, Leitung, IT)."""
    return user.has_perms(("stammdaten.add_person", "stammdaten.add_schuelerprofil"))


def schueler_fuer(user, sj):
    """Schülerpool: Verwaltung alle aktiven; Stufenkoordination die Schüler:innen ihrer Stufe und solche ohne Klasse."""
    qs = Schuelerprofil.objects.filter(status__in=["aktiv", "bewerber"])
    if alle_jahrgaenge(user):
        return qs
    jahrgaenge = koordinierte_jahrgaenge(user)
    in_stufe = Mitgliedschaft.objects.aktiv().filter(gruppe__schuljahr=sj, gruppe__typ=Gruppe.STAMMKLASSE,
                                                     gruppe__jahrgang__in=jahrgaenge).values("schueler")
    mit_klasse = Mitgliedschaft.objects.aktiv().filter(gruppe__schuljahr=sj, gruppe__typ=Gruppe.STAMMKLASSE).values("schueler")
    return qs.filter(Q(pk__in=in_stufe) | ~Q(pk__in=mit_klasse))


# ---------------------------------------------------------------- Kernfunktionen (auch für Tests)

def stichtag_fuer(gruppe, datum=None):
    """Beginn einer neuen Mitgliedschaft: gewünschtes Datum, aber nicht vor Schuljahresbeginn bzw. nach dessen Ende."""
    datum = datum or timezone.localdate()
    return min(max(datum, gruppe.schuljahr.beginn), gruppe.schuljahr.ende)


def beenden(mitgliedschaft, datum):
    """Mitgliedschaft zum Ende des Vortags von `datum` beenden; noch nicht begonnene werden gelöscht."""
    if mitgliedschaft.von >= datum:
        mitgliedschaft.delete()
        return "geloescht"
    mitgliedschaft.bis = datum - timedelta(days=1)
    mitgliedschaft.save()
    return "beendet"


@transaction.atomic
def hinzufuegen(gruppe, schueler_liste, datum=None):
    """
    Fügt Schüler:innen zum Stichtag hinzu. Bei Stammklassen wird eine laufende Mitgliedschaft in einer anderen
    Stammklasse desselben Schuljahres zum Vortag beendet (Klassenwechsel).
    Rückgabe: dict mit Zählern und den Namen der Wechsel.
    """
    start = stichtag_fuer(gruppe, datum)
    ergebnis = {"neu": 0, "schon": 0, "wechsel": [], "fehler": []}
    for s in schueler_liste:
        laufend = Mitgliedschaft.objects.filter(gruppe=gruppe, schueler=s).filter(Q(bis__isnull=True) | Q(bis__gte=start))
        if laufend.exists():
            ergebnis["schon"] += 1
            continue
        if gruppe.typ == Gruppe.STAMMKLASSE:
            andere = (Mitgliedschaft.objects.filter(schueler=s, gruppe__typ=Gruppe.STAMMKLASSE, gruppe__schuljahr=gruppe.schuljahr)
                      .exclude(gruppe=gruppe).filter(Q(bis__isnull=True) | Q(bis__gte=start)).select_related("gruppe"))
            for m in andere:
                ergebnis["wechsel"].append(f"{s.person.anzeigename} ({m.gruppe.name} → {gruppe.name})")
                beenden(m, start)
        try:
            Mitgliedschaft.objects.create(gruppe=gruppe, schueler=s, von=start)
            ergebnis["neu"] += 1
            if gruppe.typ == Gruppe.STAMMKLASSE:       # Schullaufbahn des Schuljahres nachführen (gleicher Jahrgang)
                lb = Laufbahnabschnitt.objects.filter(schueler=s, schuljahr=gruppe.schuljahr).filter(
                    Q(bis__isnull=True) | Q(bis__gte=start)).order_by("-von", "-pk").first()
                if lb and (gruppe.jahrgang is None or lb.jahrgang == gruppe.jahrgang) and lb.stammklasse_id != gruppe.pk:
                    lb.stammklasse = gruppe
                    lb.save(update_fields=["stammklasse"])
        except ValidationError as e:
            ergebnis["fehler"].append(f"{s.person.anzeigename}: {' '.join(e.messages)}")
    return ergebnis


@transaction.atomic
def entfernen(gruppe, schueler_ids, datum=None):
    datum = datum or timezone.localdate()
    n = 0
    for m in Mitgliedschaft.objects.filter(gruppe=gruppe, schueler_id__in=schueler_ids).filter(Q(bis__isnull=True) | Q(bis__gte=datum)):
        beenden(m, datum)
        n += 1
    return n


# ---------------------------------------------------------------- Formulare

class GruppeForm(forms.ModelForm):
    class Meta:
        model = Gruppe
        fields = ["name", "typ", "jahrgang", "leitung", "kuerzel", "vorgaenger"]

    def __init__(self, *args, schuljahr=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.schuljahr = schuljahr
        self.fields["leitung"].queryset = Personalprofil.objects.filter(aktiv=True).select_related("person").order_by("person__nachname")
        self.fields["leitung"].label_from_instance = lambda p: f"{p.person.anzeigename}{f' ({p.kuerzel})' if p.kuerzel else ''}"
        vorjahr = Schuljahr.objects.filter(beginn__lt=schuljahr.beginn).order_by("-beginn").first() if schuljahr else None
        self.fields["vorgaenger"].queryset = Gruppe.objects.filter(schuljahr=vorjahr) if vorjahr else Gruppe.objects.none()
        for f in ("kuerzel", "name"):
            self.fields[f].help_text = ""
        if user is not None and not alle_jahrgaenge(user):
            jg = sorted(koordinierte_jahrgaenge(user))
            self.fields["jahrgang"].required = True
            self.fields["jahrgang"].widget = forms.Select(choices=[(j, j) for j in jg])
            self.user_jahrgaenge = set(jg)
        else:
            self.user_jahrgaenge = None

    def clean_jahrgang(self):
        jg = self.cleaned_data.get("jahrgang")
        if self.user_jahrgaenge is not None and jg not in self.user_jahrgaenge:
            raise ValidationError(_("Nur Jahrgänge der eigenen Stufe."))
        return jg

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if self.schuljahr and Gruppe.objects.filter(schuljahr=self.schuljahr, name__iexact=name).exclude(pk=self.instance.pk).exists():
            raise ValidationError(_("Eine Gruppe mit diesem Namen gibt es in diesem Schuljahr schon."))
        return name


class GruppeBearbeitenForm(GruppeForm):
    """Wie „Neue Gruppe“, aber ohne Typ – ein Typwechsel würde die Regeln für Stammklassen umgehen."""

    class Meta(GruppeForm.Meta):
        fields = ["name", "jahrgang", "leitung", "kuerzel", "vorgaenger"]


class SchuelerNeuForm(forms.Form):
    vorname = forms.CharField(label=_("Vorname(n)"), max_length=80)
    nachname = forms.CharField(label=_("Nachname"), max_length=80)
    geschlecht = forms.ChoiceField(label=_("Geschlecht"), choices=Person.GESCHLECHT, required=False)
    geburtsdatum = forms.DateField(label=_("Geburtsdatum"), required=False, widget=forms.DateInput(attrs={"type": "date"}))
    religionsunterricht = forms.ChoiceField(label=_("Religion / Ethik"), choices=Schuelerprofil.RELIGIONSUNTERRICHT, required=False)
    trotzdem = forms.BooleanField(label=_("Trotzdem anlegen (gleichnamige Person vorhanden)"), required=False)

    def clean(self):
        daten = super().clean()
        if daten.get("vorname") and daten.get("nachname") and not daten.get("trotzdem"):
            gleich = Person.objects.filter(vorname__iexact=daten["vorname"].strip(), nachname__iexact=daten["nachname"].strip())
            if daten.get("geburtsdatum"):
                gleich = gleich.filter(Q(geburtsdatum=daten["geburtsdatum"]) | Q(geburtsdatum__isnull=True))
            if gleich.exists():
                raise ValidationError(_("Eine Person mit diesem Namen gibt es schon – bitte rechts in der Liste suchen. "
                                        "Wirklich eine weitere Person anlegen: „Trotzdem anlegen“ ankreuzen."))
        return daten


# ---------------------------------------------------------------- Ansichten

def _zurueck(sj, gruppe=None, **extra):
    q = {"sj": sj.pk}
    if gruppe:
        q["gruppe"] = gruppe.pk
    q.update({k: v for k, v in extra.items() if v})
    return redirect(reverse("zuordnung") + "?" + urlencode(q))


def _datum(request):
    return parse_date(request.POST.get("datum") or "") or timezone.localdate()


@login_required
def zuordnung(request):
    if not darf_zuordnen(request.user):
        raise PermissionDenied
    sj = Schuljahr.objects.filter(pk=request.GET.get("sj")).first() or Schuljahr.aktuelles() or Schuljahr.objects.first()
    if sj is None:
        messages.error(request, gettext("Bitte zuerst ein Schuljahr anlegen."))
        return redirect("start")
    heute = timezone.localdate()
    stichtag = min(max(heute, sj.beginn), sj.ende)

    gruppen = list(gruppen_fuer(request.user, sj).select_related("leitung__person")
                   .annotate(anzahl=Count("mitgliedschaften", filter=Q(mitgliedschaften__von__lte=stichtag)
                                          & (Q(mitgliedschaften__bis__isnull=True) | Q(mitgliedschaften__bis__gte=stichtag)), distinct=True),
                             rang=Case(When(typ=Gruppe.STAMMKLASSE, then=Value(0)), When(typ=Gruppe.LERNGRUPPE, then=Value(1)),
                                       default=Value(2), output_field=IntegerField()))
                   .order_by("rang", "jahrgang", "name"))
    gruppe = next((g for g in gruppen if str(g.pk) == request.GET.get("gruppe")), None) or (gruppen[0] if gruppen else None)

    # Stammklasse jeder Person im gewählten Schuljahr (für Anzeige und Filter)
    klasse_von = {}
    for m in Mitgliedschaft.objects.aktiv(stichtag).filter(gruppe__schuljahr=sj, gruppe__typ=Gruppe.STAMMKLASSE).select_related("gruppe"):
        klasse_von[m.schueler_id] = m.gruppe

    mitglieder, mitglieder_ids, vorgaenger_neu = [], set(), 0
    if gruppe:
        for m in (Mitgliedschaft.objects.aktiv(stichtag).filter(gruppe=gruppe).select_related("schueler__person")
                  .order_by("schueler__person__nachname", "schueler__person__vorname")):
            m.stammklasse = klasse_von.get(m.schueler_id)
            mitglieder.append(m)
            mitglieder_ids.add(m.schueler_id)
        if gruppe.vorgaenger_id:
            vorgaenger_neu = gruppe.vorgaenger.aktuelle_mitglieder(gruppe.vorgaenger.schuljahr.ende).exclude(pk__in=mitglieder_ids).count()

    pool = []
    for s in schueler_fuer(request.user, sj).select_related("person").order_by("person__nachname", "person__vorname"):
        k = klasse_von.get(s.pk)
        pool.append({"s": s, "klasse": k, "drin": s.pk in mitglieder_ids})

    # Voreinstellung des Filters: Lerngruppe aus Stammklassen gebildet → diese Klassen; Ethik/Religion → passende Wahl
    vorfilter = {"klassen": [], "religion": ""}
    if gruppe and gruppe.typ != Gruppe.STAMMKLASSE:
        vorfilter["klassen"] = [str(k.pk) for k in gruppe.gebildet_aus.all()]
        name = gruppe.name.lower()
        for schluessel, wort in (("ethik", "ethik"), ("ev", "evang"), ("kath", "kathol")):
            if wort in name:
                vorfilter["religion"] = schluessel
    elif gruppe and gruppe.typ == Gruppe.STAMMKLASSE:
        # Klassenbildung: zuerst die Schüler:innen zeigen, die im Schuljahr noch keine Klasse haben
        vorfilter["ohne_klasse"] = any(e["klasse"] is None for e in pool)

    klassen = [g for g in gruppen if g.typ == Gruppe.STAMMKLASSE]
    darf_bearbeiten = gruppe is not None and darf_gruppe_bearbeiten(request.user, gruppe)
    from .klassenunterricht import darf_unterricht_verteilen, tabelle

    mit_faechern = gruppe is not None and gruppe.typ != Gruppe.AG      # AGs haben keinen Unterricht mit Noten
    ansicht = "faecher" if mit_faechern and request.GET.get("ansicht") == "faecher" else "schueler"
    return render(request, "portal/zuordnung.html", {
        "ansicht": ansicht, "mit_faechern": mit_faechern, "unterricht": tabelle(gruppe) if ansicht == "faecher" else None,
        "darf_unterricht": gruppe is not None and darf_unterricht_verteilen(request.user, gruppe),
        "bearbeiten_form": GruppeBearbeitenForm(prefix="bearb", instance=gruppe, schuljahr=sj, user=request.user)
        if darf_bearbeiten and request.user.has_perm("stammdaten.change_gruppe") else None,
        "schueler_form": SchuelerNeuForm(prefix="sn") if darf_bearbeiten and darf_schueler_anlegen(request.user) else None,
        "sj": sj, "schuljahre": Schuljahr.objects.all(), "gruppen": gruppen, "gruppe": gruppe, "mitglieder": mitglieder,
        "pool": pool, "klassen": klassen, "jahrgaenge": sorted({g.jahrgang for g in klassen if g.jahrgang}),
        "religionen": Schuelerprofil.RELIGIONSUNTERRICHT[1:], "stichtag": stichtag, "vorgaenger_neu": vorgaenger_neu,
        "vorfilter": vorfilter, "darf_bearbeiten": darf_bearbeiten,
        "neu_form": GruppeForm(prefix="neu", schuljahr=sj, user=request.user,
                               initial={"typ": Gruppe.LERNGRUPPE}) if request.user.has_perm("stammdaten.add_gruppe") else None,
        "typen": Gruppe.TYPEN,
    })


@login_required
@require_POST
def zuordnung_aktion(request, pk):
    gruppe = get_object_or_404(Gruppe.objects.select_related("schuljahr"), pk=pk)
    if not darf_gruppe_bearbeiten(request.user, gruppe):
        raise PermissionDenied
    aktion = request.POST.get("aktion")
    datum = _datum(request)
    ids = [int(i) for i in request.POST.getlist("schueler") if i.isdigit()]

    if aktion == "hinzufuegen":
        erlaubt = schueler_fuer(request.user, gruppe.schuljahr).filter(pk__in=ids).select_related("person")
        e = hinzufuegen(gruppe, list(erlaubt), datum)
        teile = [gettext("%(n)s hinzugefügt") % {"n": e["neu"]}]
        if e["schon"]:
            teile.append(gettext("%(n)s waren schon Mitglied") % {"n": e["schon"]})
        if e["wechsel"]:
            teile.append(gettext("Klassenwechsel: %(liste)s") % {"liste": "; ".join(e["wechsel"])})
        messages.success(request, " · ".join(teile))
        for f in e["fehler"]:
            messages.error(request, f)
    elif aktion == "entfernen":
        n = entfernen(gruppe, ids, datum)
        messages.success(request, gettext("%(n)s Mitgliedschaft(en) zum %(datum)s beendet.") % {
            "n": n, "datum": formats.date_format(datum, "SHORT_DATE_FORMAT")})
    elif aktion == "vorgaenger":
        if gruppe.vorgaenger_id:
            vorher = gruppe.vorgaenger.aktuelle_mitglieder(gruppe.vorgaenger.schuljahr.ende)
            erlaubt = schueler_fuer(request.user, gruppe.schuljahr).filter(pk__in=vorher.values("pk")).select_related("person")
            e = hinzufuegen(gruppe, list(erlaubt), gruppe.schuljahr.beginn if datum <= gruppe.schuljahr.beginn else datum)
            messages.success(request, gettext("%(n)s aus %(gruppe)s übernommen.") % {"n": e["neu"], "gruppe": gruppe.vorgaenger.name})
            for f in e["fehler"]:
                messages.error(request, f)
    elif aktion == "rolle":
        m = get_object_or_404(Mitgliedschaft, pk=request.POST.get("mitgliedschaft"), gruppe=gruppe)
        m.rolle = (request.POST.get("rolle") or "").strip()[:40]
        m.save()
        messages.success(request, gettext("Rolle gespeichert."))
    return _zurueck(gruppe.schuljahr, gruppe)


@login_required
@require_POST
def gruppe_anlegen(request):
    sj = get_object_or_404(Schuljahr, pk=request.POST.get("sj"))
    if not (darf_zuordnen(request.user) and request.user.has_perm("stammdaten.add_gruppe")):
        raise PermissionDenied
    form = GruppeForm(request.POST, prefix="neu", schuljahr=sj, user=request.user)
    if form.is_valid():
        g = form.save(commit=False)
        g.schuljahr = sj
        g.save()
        messages.success(request, gettext("Gruppe „%(name)s“ angelegt.") % {"name": g.name})
        return _zurueck(sj, g)
    messages.error(request, gettext("Gruppe nicht angelegt: %(fehler)s") % {
        "fehler": " ".join(f"{form.fields[f].label}: {' '.join(e)}" if f in form.fields else " ".join(e) for f, e in form.errors.items())})
    return _zurueck(sj)


def _fehlertext(form):
    return " ".join(f"{form.fields[f].label}: {' '.join(e)}" if f in form.fields else " ".join(e) for f, e in form.errors.items())


@login_required
@require_POST
def gruppe_bearbeiten(request, pk):
    gruppe = get_object_or_404(Gruppe.objects.select_related("schuljahr"), pk=pk)
    if not (darf_gruppe_bearbeiten(request.user, gruppe) and request.user.has_perm("stammdaten.change_gruppe")):
        raise PermissionDenied
    form = GruppeBearbeitenForm(request.POST, prefix="bearb", instance=gruppe, schuljahr=gruppe.schuljahr, user=request.user)
    if form.is_valid():
        form.save()
        messages.success(request, gettext("Gruppe „%(name)s“ gespeichert.") % {"name": gruppe.name})
    else:
        messages.error(request, gettext("Nicht gespeichert: %(fehler)s") % {"fehler": _fehlertext(form)})
    return _zurueck(gruppe.schuljahr, gruppe)


@login_required
@require_POST
def schueler_anlegen(request, pk):
    """Neue:n Schüler:in mit den wichtigsten Angaben anlegen und gleich der Gruppe zuordnen."""
    from aufnahme.uebernahme import naechste_schuelernummer

    gruppe = get_object_or_404(Gruppe.objects.select_related("schuljahr"), pk=pk)
    if not (darf_gruppe_bearbeiten(request.user, gruppe) and darf_schueler_anlegen(request.user)):
        raise PermissionDenied
    form = SchuelerNeuForm(request.POST, prefix="sn")
    if not form.is_valid():
        messages.error(request, gettext("Nicht angelegt: %(fehler)s") % {"fehler": _fehlertext(form)})
        return _zurueck(gruppe.schuljahr, gruppe, neu="1")
    d = form.cleaned_data
    start = stichtag_fuer(gruppe, _datum(request))
    with transaction.atomic():
        person = Person.objects.create(vorname=d["vorname"].strip(), nachname=d["nachname"].strip(),
                                       geschlecht=d["geschlecht"], geburtsdatum=d["geburtsdatum"])
        s = Schuelerprofil.objects.create(person=person, schuelernummer=naechste_schuelernummer(), eintrittsdatum=start,
                                          eintritt_jahrgang=gruppe.jahrgang, status="aktiv",
                                          religionsunterricht=d["religionsunterricht"])
        e = hinzufuegen(gruppe, [s], start)
    for f in e["fehler"]:
        messages.error(request, f)
    messages.success(request, gettext("%(name)s angelegt (Schülernummer %(nr)s) und %(gruppe)s zugeordnet. "
                                      "Weitere Angaben in der Schülerakte.") % {
        "name": person.anzeigename, "nr": s.schuelernummer, "gruppe": gruppe.name})
    return _zurueck(gruppe.schuljahr, gruppe)
