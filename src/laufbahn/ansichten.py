from datetime import date, timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy as _, ngettext

from portal.rechte import ist_schulleitung
from sicherung.models import Protokoll
from stammdaten.models import Gruppe, Personalprofil, Schuelerprofil, Schuljahr

from . import ereignisse, loeschung, rechte, wechsel as W
from .models import ENTSCHEIDUNGEN, Klassenplan, Laufbahnereignis, Loeschfrist, Loeschvorgang, Schuljahreswechsel, Wechselposten

DATUM = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


def _reiter(aktiv, user):
    reiter = []
    if rechte.darf_schuljahre(user):
        reiter.append({"url": "schuljahre", "name": _("Schuljahre und Wechsel"), "aktiv": aktiv == "schuljahre"})
    if rechte.darf_archiv(user):
        reiter.append({"url": "archiv", "name": _("Archiv"), "aktiv": aktiv == "archiv"})
    if rechte.darf_fristen_sehen(user):
        reiter.append({"url": "loeschfristen", "name": _("Löschfristen"), "aktiv": aktiv == "loeschfristen"})
    return reiter


# ---------------------------------------------------------------- Schuljahre

class SchuljahrForm(forms.Form):
    name = forms.CharField(label=_("Bezeichnung"), max_length=20)
    beginn = forms.DateField(label=_("Erster Schultag"), widget=DATUM)
    ende = forms.DateField(label=_("Letzter Schultag"), widget=DATUM)
    vorlage = forms.ModelChoiceField(label=_("Halbjahre übernehmen von"), queryset=Schuljahr.objects.all(), required=False)

    def clean(self):
        d = super().clean()
        if d.get("beginn") and d.get("ende") and d["ende"] <= d["beginn"]:
            raise ValidationError(_("Das Ende muss nach dem Beginn liegen."))
        if d.get("name") and Schuljahr.objects.filter(name=d["name"]).exists():
            self.add_error("name", _("Dieses Schuljahr gibt es schon."))
        if d.get("beginn") and d.get("ende") and Schuljahr.objects.filter(beginn__lte=d["ende"], ende__gte=d["beginn"]).exists():
            raise ValidationError(_("Der Zeitraum überschneidet sich mit einem vorhandenen Schuljahr."))
        return d


@login_required
def schuljahre(request):
    user = request.user
    if not rechte.darf_schuljahre(user):
        raise PermissionDenied
    aktuell = Schuljahr.aktuelles()
    letztes = Schuljahr.objects.order_by("-beginn").first()
    vorschlag = W.vorschlag_neues_schuljahr(letztes) if letztes else {}
    form = SchuljahrForm(initial={**vorschlag, "vorlage": letztes})
    if request.method == "POST":
        aktion = request.POST.get("aktion")
        if aktion == "anlegen":
            form = SchuljahrForm(request.POST)
            if form.is_valid():
                d = form.cleaned_data
                sj = W.schuljahr_anlegen(d["name"], d["beginn"], d["ende"], d["vorlage"])
                Protokoll.schreiben(user, "schuljahr", gettext("Schuljahr %(sj)s angelegt") % {"sj": sj})
                messages.success(request, gettext("Schuljahr %(sj)s angelegt.") % {"sj": sj})
                return redirect("schuljahre")
        elif aktion == "aktivieren":
            sj = get_object_or_404(Schuljahr, pk=request.POST.get("schuljahr"))
            W.aktivieren(sj)
            Protokoll.schreiben(user, "schuljahr", gettext("Schuljahr %(sj)s als aktuelles Schuljahr gesetzt") % {"sj": sj})
            messages.success(request, gettext("%(sj)s ist jetzt das aktuelle Schuljahr.") % {"sj": sj})
            return redirect("schuljahre")
        elif aktion == "wechsel":
            von = get_object_or_404(Schuljahr, pk=request.POST.get("von"))
            nach = get_object_or_404(Schuljahr, pk=request.POST.get("nach"))
            try:
                w = W.wechsel_anlegen(von, nach, user)
            except ValidationError as e:
                messages.error(request, " ".join(e.messages))
                return redirect("schuljahre")
            return redirect("schuljahreswechsel", pk=w.pk)
        else:
            raise PermissionDenied
    jahre = list(Schuljahr.objects.annotate(
        n_klassen=Count("gruppen", filter=Q(gruppen__typ=Gruppe.STAMMKLASSE), distinct=True),
        n_schueler=Count("laufbahnabschnitte__schueler", distinct=True)).prefetch_related("abschnitte").order_by("-beginn"))
    wechsel = {w.von_id: w for w in Schuljahreswechsel.objects.select_related("nach")}
    for j in jahre:
        j.wechsel = wechsel.get(j.pk)
        j.folgejahr = W.naechstes_schuljahr(j) if (aktuell is None or j.beginn >= aktuell.beginn) else None
    heute = timezone.localdate()
    return render(request, "laufbahn/schuljahre.html", {
        "titel": _("Schuljahre und Schuljahreswechsel"), "reiter": _reiter("schuljahre", user),
        "jahre": jahre, "aktuell": aktuell, "form": form, "heute": heute,
        "aktuell_vorbei": bool(aktuell and heute > aktuell.ende),
    })


# ---------------------------------------------------------------- Schuljahreswechsel (Assistent)

SCHRITTE = [("klassen", _("1. Klassen planen")), ("schueler", _("2. Entscheidungen")), ("durchfuehren", _("3. Durchführen"))]


@login_required
def schuljahreswechsel(request, pk):
    user = request.user
    if not rechte.darf_schuljahre(user):
        raise PermissionDenied
    w = get_object_or_404(Schuljahreswechsel.objects.select_related("von", "nach"), pk=pk)
    schritt = request.GET.get("schritt") or ("durchfuehren" if w.durchgefuehrt else "klassen")
    if schritt not in dict(SCHRITTE):
        schritt = "klassen"
    if request.method == "POST":
        return _wechsel_post(request, w)

    klassen_nach = list(Gruppe.objects.filter(schuljahr=w.nach, typ=Gruppe.STAMMKLASSE).select_related("leitung__person")
                        .order_by("jahrgang", "name"))
    posten = list(w.posten.select_related("schueler__person", "alte_klasse", "neue_klasse").order_by(
        "alte_klasse__jahrgang", "alte_klasse__name", "schueler__person__nachname", "schueler__person__vorname"))
    for p in posten:
        p.hindernis = W.hindernis(p) if p.status == Wechselposten.OFFEN else ""
    zaehler = {"gesamt": len(posten), "offen": sum(1 for p in posten if p.status == Wechselposten.OFFEN),
               "durchgefuehrt": sum(1 for p in posten if p.status == Wechselposten.DURCHGEFUEHRT),
               "hindernisse": sum(1 for p in posten if p.hindernis)}
    je_entscheidung = []
    for k, name, _d in ENTSCHEIDUNGEN:
        n = sum(1 for p in posten if p.entscheidung == k)
        if n:
            je_entscheidung.append({"name": name, "n": n})
    gruppen = []
    for p in posten:
        schluessel = p.alte_klasse.name if p.alte_klasse else gettext("ohne Klasse")
        if not gruppen or gruppen[-1]["name"] != schluessel:
            gruppen.append({"name": schluessel, "posten": []})
        gruppen[-1]["posten"].append(p)
    filter_klasse = request.GET.get("klasse") or ""
    alle_klassen = [g["name"] for g in gruppen]
    if filter_klasse:
        gruppen = [g for g in gruppen if g["name"] == filter_klasse] or gruppen
    return render(request, "laufbahn/wechsel.html", {
        "titel": _("Schuljahreswechsel %(von)s → %(nach)s") % {"von": w.von, "nach": w.nach}, "reiter": _reiter("schuljahre", user),
        "w": w, "schritt": schritt, "schritte": SCHRITTE, "plan": W.klassenplan_zeilen(w), "klassen_nach": klassen_nach,
        "lehrkraefte": Personalprofil.objects.filter(aktiv=True).select_related("person").order_by("person__nachname"),
        "gruppen": gruppen, "alle_klassen": alle_klassen,
        "filter_klasse": filter_klasse, "entscheidungen": [(k, n) for k, n, _d in ENTSCHEIDUNGEN], "zaehler": zaehler,
        "je_entscheidung": je_entscheidung, "heute": timezone.localdate(),
        "zu_frueh": timezone.localdate() < w.von.ende, "aktiv_vorher": w.von.aktiv,
    })


def _wechsel_post(request, w):
    user = request.user
    aktion = request.POST.get("aktion")
    weiter = reverse("schuljahreswechsel", args=[w.pk])
    if aktion == "klassen_anlegen":
        n = 0
        for plan in w.klassenplan.select_related("alt"):
            if plan.neu_id or not request.POST.get(f"anlegen-{plan.pk}"):
                continue
            leitung = Personalprofil.objects.filter(pk=request.POST.get(f"leitung-{plan.pk}") or 0).first()
            try:
                g, neu = W.klasse_anlegen(w, request.POST.get(f"name-{plan.pk}"), (plan.alt.jahrgang or 0) + 1 if plan.alt.jahrgang else None,
                                          leitung, plan.alt)
            except ValidationError as e:
                messages.error(request, f"{plan.alt.name}: {' '.join(e.messages)}")
                continue
            plan.neu, plan.neu_angelegt = g, neu
            plan.save()
            n += neu
        W.posten_aktualisieren(w)
        messages.success(request, ngettext("%(n)s Klasse angelegt.", "%(n)s Klassen angelegt.", n) % {"n": n})
        return redirect(weiter + "?schritt=klassen")
    if aktion == "zuordnen":
        plan = get_object_or_404(Klassenplan, pk=request.POST.get("plan"), wechsel=w)
        plan.neu = Gruppe.objects.filter(pk=request.POST.get("neu") or 0, schuljahr=w.nach).first()
        plan.save(update_fields=["neu"])
        W.posten_aktualisieren(w)
        return redirect(weiter + "?schritt=klassen")
    if aktion == "zusatzklasse":
        leitung = Personalprofil.objects.filter(pk=request.POST.get("leitung") or 0).first()
        try:
            jg = int(request.POST.get("jahrgang") or 0) or None
            g, neu = W.klasse_anlegen(w, request.POST.get("name"), jg, leitung)
        except (ValidationError, ValueError) as e:
            messages.error(request, " ".join(getattr(e, "messages", [str(e)])))
        else:
            messages.success(request, gettext("Klasse %(k)s angelegt.") % {"k": g.name} if neu else
                             gettext("Klasse %(k)s gibt es bereits.") % {"k": g.name})
            W.posten_aktualisieren(w)
        return redirect(weiter + "?schritt=klassen")
    if aktion == "aktualisieren":
        n = W.posten_aktualisieren(w)
        messages.success(request, ngettext("Liste aktualisiert: %(n)s Schüler:in neu aufgenommen.", "Liste aktualisiert: %(n)s Schüler:innen neu aufgenommen.", n) % {"n": n})
        return redirect(weiter + "?schritt=schueler")
    if aktion == "entscheidungen":
        gueltig = dict((k, n) for k, n, _d in ENTSCHEIDUNGEN)
        klassen = {str(g.pk): g for g in Gruppe.objects.filter(schuljahr=w.nach, typ=Gruppe.STAMMKLASSE)}
        plan_neu = {pl.alt_id: pl.neu for pl in w.klassenplan.select_related("neu")}
        n = 0
        for p in w.posten.filter(status=Wechselposten.OFFEN).select_related("alte_klasse"):
            e = request.POST.get(f"e-{p.pk}")
            if e not in gueltig:
                continue
            k = klassen.get(request.POST.get(f"k-{p.pk}") or "")
            geaendert = e != p.entscheidung
            p.entscheidung = e
            if geaendert and (k is None or k.jahrgang != p.neuer_jahrgang):
                k = W.zielklasse_vorschlagen(p, plan_neu, list(klassen.values()))
            p.neue_klasse = None if p.verlaesst_schule else k
            if geaendert:
                p.grundlage = gettext("Geändert von %(wer)s") % {"wer": user.get_full_name() or user.get_username()}
            p.save()
            n += 1
        messages.success(request, gettext("Entscheidungen gespeichert."))
        ziel = weiter + "?schritt=schueler"
        if request.POST.get("klasse"):
            ziel += "&klasse=" + request.POST["klasse"]
        return redirect(ziel)
    if aktion == "durchfuehren":
        if not request.POST.get("bestaetigt"):
            messages.error(request, gettext("Bitte bestätigen, dass der Wechsel durchgeführt werden soll."))
            return redirect(weiter + "?schritt=durchfuehren")
        ok, offen = W.wechsel_durchfuehren(w, user, schuljahr_aktivieren=bool(request.POST.get("aktivieren")))
        Protokoll.schreiben(user, "schuljahreswechsel", gettext("Schuljahreswechsel %(w)s: %(ok)s durchgeführt, %(offen)s offen")
                            % {"w": w, "ok": ok, "offen": offen})
        messages.success(request, ngettext("Schuljahreswechsel durchgeführt: %(ok)s Schüler:in übertragen.", "Schuljahreswechsel durchgeführt: %(ok)s Schüler:innen übertragen.", ok) % {"ok": ok})
        if offen:
            messages.warning(request, ngettext("%(n)s Schüler:in ist noch offen (fehlende Zielklasse o. Ä.).",
                                               "%(n)s Schüler:innen sind noch offen (fehlende Zielklasse o. Ä.).", offen) % {"n": offen})
        return redirect(weiter + "?schritt=durchfuehren")
    if aktion == "posten_zuruecknehmen":
        p = get_object_or_404(Wechselposten, pk=request.POST.get("posten"), wechsel=w)
        if W.posten_zuruecknehmen(p):
            Protokoll.schreiben(user, "schuljahreswechsel", gettext("Wechsel %(w)s für Schülernummer %(nr)s zurückgenommen")
                                % {"w": w, "nr": p.schueler.schuelernummer})
            messages.success(request, gettext("Für %(name)s zurückgenommen – die Entscheidung kann jetzt geändert und erneut "
                                              "durchgeführt werden.") % {"name": p.schueler.person.anzeigename})
        return redirect(weiter + "?schritt=schueler")
    if aktion == "zuruecknehmen":
        if not request.POST.get("bestaetigt"):
            messages.error(request, gettext("Bitte bestätigen, dass der gesamte Wechsel zurückgenommen werden soll."))
            return redirect(weiter + "?schritt=durchfuehren")
        n, k = W.wechsel_zuruecknehmen(w, klassen_loeschen=bool(request.POST.get("klassen_loeschen")))
        Protokoll.schreiben(user, "schuljahreswechsel", gettext("Schuljahreswechsel %(w)s vollständig zurückgenommen") % {"w": w})
        messages.success(request, gettext("Wechsel zurückgenommen: %(n)s Schüler:innen zurückgesetzt, %(k)s leere Klassen entfernt.")
                         % {"n": n, "k": k})
        return redirect(weiter + "?schritt=durchfuehren")
    raise PermissionDenied


# ---------------------------------------------------------------- Laufbahn einer Schülerin / eines Schülers

class UmstufungForm(forms.Form):
    klasse = forms.ModelChoiceField(label=_("Neue Klasse"), queryset=Gruppe.objects.none())
    datum = forms.DateField(label=_("Wirksam ab"), widget=DATUM)
    bemerkung = forms.CharField(label=_("Bemerkung"), max_length=200, required=False,
                                help_text=_("z. B. Beschluss der Klassenkonferenz vom …"))

    def __init__(self, *args, schueler=None, **kwargs):
        super().__init__(*args, **kwargs)
        jahre = Schuljahr.objects.filter(ende__gte=timezone.localdate() - timedelta(days=60))
        self.fields["klasse"].queryset = Gruppe.objects.filter(typ=Gruppe.STAMMKLASSE, schuljahr__in=jahre).select_related(
            "schuljahr").order_by("schuljahr__beginn", "jahrgang", "name")
        self.fields["klasse"].label_from_instance = lambda g: f"{g.name} · {g.schuljahr}"


class AbgangForm(forms.Form):
    datum = forms.DateField(label=_("Letzter Schultag"), widget=DATUM)
    art = forms.ChoiceField(label=_("Art des Abgangs"))
    grund = forms.CharField(label=_("Grund / Zielschule"), max_length=200, required=False)
    zeugnis = forms.BooleanField(label=_("Abgangszeugnis anlegen"), required=False, initial=True)
    vermerk = forms.CharField(label=_("Abgangsvermerk auf dem Zeugnis"), required=False, max_length=500,
                              widget=forms.Textarea(attrs={"rows": 2}),
                              help_text=_("z. B. „Grund: Umzug der Familie nach Mombasa.“"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["art"].choices = ereignisse.abgangsarten()


@login_required
def schueler(request, pk):
    user = request.user
    s = get_object_or_404(Schuelerprofil.objects.select_related("person"), pk=pk)
    if not (rechte.darf_abgang(user) or rechte.darf_archiv(user)):
        raise PermissionDenied
    darf = rechte.darf_abgang(user) and not s.archiviert
    umstufung = UmstufungForm(schueler=s, initial={"datum": timezone.localdate()})
    sj = Schuljahr.aktuelles()
    abgang = AbgangForm(initial={"datum": sj.ende if sj else timezone.localdate()})
    if request.method == "POST":
        aktion = request.POST.get("aktion")
        if aktion == "zuruecknehmen":
            if not rechte.darf_abgang(user):
                raise PermissionDenied
            e = get_object_or_404(Laufbahnereignis, pk=request.POST.get("ereignis"), schueler=s)
            try:
                ereignisse.zuruecknehmen(e)
            except ValidationError as fehler:
                messages.error(request, " ".join(fehler.messages))
            else:
                Protokoll.schreiben(user, "laufbahn", gettext("Laufbahnänderung zurückgenommen (Schülernummer %(nr)s): %(t)s")
                                    % {"nr": s.schuelernummer, "t": e.text})
                messages.success(request, gettext("Zurückgenommen: %(t)s") % {"t": e.text})
            return redirect("laufbahn_schueler", pk=s.pk)
        if not darf:
            raise PermissionDenied
        if aktion == "umstufen":
            umstufung = UmstufungForm(request.POST, schueler=s)
            if umstufung.is_valid():
                d = umstufung.cleaned_data
                try:
                    e = ereignisse.umstufen(s, d["klasse"], d["datum"], user, d["bemerkung"])
                except ValidationError as fehler:
                    umstufung.add_error(None, fehler)
                else:
                    messages.success(request, e.text)
                    return redirect("laufbahn_schueler", pk=s.pk)
        elif aktion == "abgang":
            abgang = AbgangForm(request.POST)
            if abgang.is_valid():
                d = abgang.cleaned_data
                try:
                    e, z, hinweis = ereignisse.abgang_erfassen(s, d["datum"], d["art"], d["grund"], user, d["zeugnis"], d["vermerk"])
                except ValidationError as fehler:
                    abgang.add_error(None, fehler)
                else:
                    Protokoll.schreiben(user, "laufbahn", gettext("Abgang erfasst (Schülernummer %(nr)s)") % {"nr": s.schuelernummer})
                    messages.success(request, e.text)
                    if hinweis:
                        messages.warning(request, hinweis)
                    return redirect("laufbahn_schueler", pk=s.pk)
        else:
            raise PermissionDenied
    from zeugnisse.models import Zeugnis

    letztes = ereignisse.letztes_ereignis(s)
    return render(request, "laufbahn/schueler.html", {
        "titel": s.person.anzeigename, "s": s, "p": s.person, "darf": darf, "darf_zuruecknehmen": rechte.darf_abgang(user),
        "stationen": ereignisse.stationen(s), "umstufung": umstufung, "abgang": abgang,
        "ereignisse": s.laufbahnereignisse.select_related("erstellt_von").order_by("-erstellt_am", "-pk"), "letztes": letztes,
        "posten": s.wechselposten.select_related("wechsel__von", "wechsel__nach", "neue_klasse").order_by("-wechsel__von__beginn"),
        "abgangszeugnisse": Zeugnis.objects.filter(schueler=s, art=Zeugnis.ABGANG).select_related("abschnitt__schuljahr"),
        "faellig": loeschung.faellige(schueler=s, vorlauf_tage=365 * 60) if s.archiviert else [],
        "klasse": s.stammklasse(), "darf_schuljahre": rechte.darf_schuljahre(user),
    })


# ---------------------------------------------------------------- Archiv

@login_required
def archiv(request):
    user = request.user
    if not rechte.darf_archiv(user):
        raise PermissionDenied
    from zeugnisse.models import Zeugnis

    qs = Schuelerprofil.objects.filter(status="abgang").select_related("person").order_by("-austrittsdatum", "person__nachname")
    q = (request.GET.get("q") or "").strip()
    if q:
        for t in q.split():
            qs = qs.filter(Q(person__nachname__icontains=t) | Q(person__vorname__icontains=t) | Q(schuelernummer__icontains=t))
    jahre = sorted({d.year for d in Schuelerprofil.objects.filter(status="abgang", austrittsdatum__isnull=False)
                    .values_list("austrittsdatum", flat=True)}, reverse=True)
    jahr = request.GET.get("jahr") or ""
    if jahr.isdigit():
        qs = qs.filter(austrittsdatum__year=int(jahr))
    eintraege = list(qs[:300])
    zeugnisse = {z.schueler_id: z for z in Zeugnis.objects.filter(schueler__in=eintraege, art=Zeugnis.ABGANG)}
    fristen = [f for f in Loeschfrist.objects.filter(aktiv=True)]
    erledigt = {(v.schuelernummer, v.kategorie) for v in Loeschvorgang.objects.filter(
        schuelernummer__in=[s.schuelernummer for s in eintraege]).exclude(status=Loeschvorgang.AUFGESCHOBEN)}
    heute = timezone.localdate()
    for s in eintraege:
        s.abgangszeugnis = zeugnisse.get(s.pk)
        s.letzte = s.aktueller_laufbahnabschnitt()
        naechste = sorted(((loeschung.faellig_am(f, s.austrittsdatum), f) for f in fristen
                           if (s.schuelernummer, f.kategorie) not in erledigt and s.austrittsdatum), key=lambda x: x[0])
        s.naechste_loeschung = naechste[0] if naechste else None
        s.loeschung_faellig = bool(naechste and naechste[0][0] <= heute)
    return render(request, "laufbahn/archiv.html", {
        "titel": _("Archiv"), "reiter": _reiter("archiv", user), "bereich": "schulleitung" if ist_schulleitung(user) else "verwaltung", "eintraege": eintraege, "q": q, "jahre": jahre, "jahr": jahr,
        "gesamt": qs.count(), "darf_fristen": rechte.darf_fristen_sehen(user),
    })


# ---------------------------------------------------------------- Löschfristen

@login_required
def loeschfristen(request):
    user = request.user
    if not rechte.darf_fristen_sehen(user):
        raise PermissionDenied
    fristen = loeschung.fristen_sicherstellen()
    if request.method == "POST":
        aktion = request.POST.get("aktion")
        if aktion == "fristen":
            if not rechte.darf_fristen_aendern(user):
                raise PermissionDenied
            bezug, aktionen = dict(Loeschfrist.BEZUG), dict(Loeschfrist.AKTIONEN)
            fehler = []
            for f in fristen:
                try:
                    jahre = int(request.POST.get(f"jahre-{f.pk}", f.jahre))
                    if not 0 <= jahre <= 100:
                        raise ValueError
                except ValueError:
                    fehler.append(f.get_kategorie_display())
                    continue
                neu = {"jahre": jahre, "bezug": request.POST.get(f"bezug-{f.pk}", f.bezug),
                       "aktion": request.POST.get(f"aktion-{f.pk}", f.aktion), "aktiv": bool(request.POST.get(f"aktiv-{f.pk}")),
                       "hinweis": (request.POST.get(f"hinweis-{f.pk}", f.hinweis) or "")[:250]}
                if neu["bezug"] not in bezug or neu["aktion"] not in aktionen:
                    continue
                if any(getattr(f, k) != v for k, v in neu.items()):
                    for k, v in neu.items():
                        setattr(f, k, v)
                    f.geaendert_von = user
                    f.save()
                    Protokoll.schreiben(user, "loeschfrist", gettext("Löschfrist geändert: %(f)s Jahre, %(k)s")
                                        % {"f": f.jahre, "k": f.get_kategorie_display()})
            if fehler:
                messages.error(request, gettext("Ungültige Jahresangabe (0 bis 100) bei: %(k)s") % {"k": ", ".join(fehler)})
            else:
                messages.success(request, gettext("Löschfristen gespeichert."))
            return redirect("loeschfristen")
        if aktion in ("loeschen", "aufschieben"):
            if not rechte.darf_loeschen(user):
                raise PermissionDenied
            s = get_object_or_404(Schuelerprofil, pk=request.POST.get("schueler"), status="abgang")
            kategorie = request.POST.get("kategorie")
            if kategorie not in loeschung.KATEGORIEN:
                raise PermissionDenied
            name = dict(Loeschfrist.KATEGORIEN)[kategorie]
            if aktion == "loeschen":
                if not request.POST.get("bestaetigt"):
                    messages.error(request, gettext("Bitte die Löschung bestätigen."))
                    return redirect("loeschfristen")
                person = s.person.anzeigename
                try:
                    n = loeschung.loeschen(s, kategorie, user)
                except ProtectedError:
                    messages.error(request, gettext("%(k)s für %(p)s konnte nicht gelöscht werden: andere Daten verweisen darauf.")
                                   % {"k": name, "p": person})
                else:
                    messages.success(request, gettext("%(k)s für %(p)s gelöscht (%(n)s Einträge).") % {"k": name, "p": person, "n": n})
            else:
                try:
                    bis = date.fromisoformat(request.POST.get("bis") or "")
                except ValueError:
                    messages.error(request, gettext("Bitte ein Datum für den Aufschub angeben."))
                    return redirect("loeschfristen")
                grund = (request.POST.get("grund") or "").strip()
                if not grund:
                    messages.error(request, gettext("Bitte einen Grund für den Aufschub angeben."))
                    return redirect("loeschfristen")
                loeschung.aufschieben(s, kategorie, bis, grund, user)
                Protokoll.schreiben(user, "loeschfrist", gettext("Löschung aufgeschoben bis %(bis)s: %(k)s, Schülernummer %(nr)s")
                                    % {"bis": bis, "k": name, "nr": s.schuelernummer})
                messages.success(request, gettext("Löschung aufgeschoben."))
            return redirect("loeschfristen")
        raise PermissionDenied
    heute = timezone.localdate()
    faellig = loeschung.faellige(heute, vorlauf_tage=30, mit_anzahl=True)
    return render(request, "laufbahn/loeschfristen.html", {
        "titel": _("Löschfristen"), "reiter": _reiter("loeschfristen", user), "fristen": fristen,
        "darf_aendern": rechte.darf_fristen_aendern(user), "darf_loeschen": rechte.darf_loeschen(user),
        "faellig": faellig, "heute": heute, "aufschub_bis": heute + timedelta(days=365),
        "vorgaenge": Loeschvorgang.objects.select_related("von")[:50],
        "bezuege": Loeschfrist.BEZUG, "aktionen": Loeschfrist.AKTIONEN,
    })


# ---------------------------------------------------------------- Startseite

def start_hinweise(user):
    """Erinnerungen: Schuljahreswechsel (Verwaltung) und fällige Löschungen (Schulleitung, IT)."""
    ergebnis = {}
    heute = timezone.localdate()
    if rechte.darf_schuljahre(user):
        sj = Schuljahr.aktuelles()
        if sj and heute >= sj.ende - timedelta(days=42):
            w = Schuljahreswechsel.objects.filter(von=sj).first()
            if not (w and w.durchgefuehrt):
                ergebnis["wechsel"] = {"sj": sj, "w": w, "naechstes": W.naechstes_schuljahr(sj), "vorbei": heute > sj.ende}
    if rechte.darf_fristen_sehen(user) and Loeschfrist.objects.filter(aktiv=True).exists():
        faellig = loeschung.faellige(heute, mit_anzahl=True)
        if faellig:
            ergebnis["loeschungen"] = len(faellig)
            ergebnis["loeschung_personen"] = len({e["schueler"].pk for e in faellig})
    return ergebnis or None
