"""Portalansichten für Neuanmeldungen: Liste, Erfassen, Bewerbungsakte, Checkliste, Unterlagen, Übernahme."""
import os
from urllib.parse import urlencode

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.forms import inlineformset_factory
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy as _, ngettext
from django.views.decorators.http import require_POST

from portal.anhaenge import datei_ausliefern
from stammdaten.dokumente import INLINE_TYPEN, groesse_pruefen
from stammdaten.models import Bildungsgang, Dokument, Gruppe, Mitgliedschaft, Schuljahr

from . import rechte
from .models import ZUSTAENDIG, AnmeldeDatei, AnmeldeKontakt, AnmeldePunkt, Anmeldung, ChecklistenVorlage
from .uebernahme import hindernisse, hinweise, kontakt_kandidaten, moegliche_dubletten, uebernehmen

DATUM = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


# ---------------------------------------------------------------- Formulare

class AnmeldungForm(forms.ModelForm):
    class Meta:
        model = Anmeldung
        fields = [
            "eingang", "schuljahr", "jahrgang", "bildungsgang", "eintrittsdatum",
            "vorname", "nachname", "rufname", "geschlecht", "geburtsdatum", "geburtsort", "geburtsland", "staatsangehoerigkeiten",
            "muttersprache", "familiensprache", "deutschkenntnisse", "daz", "religionsunterricht",
            "strasse", "postfach", "plz", "ort", "land",
            "vorherige_schule", "vorherige_schule_ort", "vorherige_schule_land", "vorherige_schulform", "letzter_jahrgang",
            "geschwister", "bemerkungen",
        ]
        widgets = {"eingang": DATUM, "eintrittsdatum": DATUM, "geburtsdatum": DATUM,
                   "bemerkungen": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        heute = timezone.localdate()
        sj = Schuljahr.objects.filter(ende__gte=heute)
        if self.instance.pk:
            sj = sj | Schuljahr.objects.filter(pk=self.instance.schuljahr_id)
        self.fields["schuljahr"].queryset = sj.order_by("beginn")
        if not self.instance.pk and not self.initial.get("schuljahr"):
            self.initial["schuljahr"] = Schuljahr.aktuelles()
        self.fields["bildungsgang"].queryset = Bildungsgang.objects.order_by("reihenfolge")
        self.fields["bildungsgang"].label_from_instance = lambda b: b.lokal_name
        self.fields["bildungsgang"].empty_label = "—"
        erlaubt = rechte.erlaubte_jahrgaenge(user) if user is not None else None
        jahrgaenge = erlaubt if erlaubt is not None else list(range(1, 14))
        leer = [] if erlaubt is not None else [("", "—")]
        self.fields["jahrgang"].widget = forms.Select(choices=leer + [(j, j) for j in jahrgaenge])
        self.fields["jahrgang"].required = erlaubt is not None
        self.erlaubt = erlaubt
        self.fields["staatsangehoerigkeiten"].help_text = _("mehrere durch Komma trennen")

    def clean_jahrgang(self):
        jg = self.cleaned_data.get("jahrgang")
        if self.erlaubt is not None and jg not in self.erlaubt:
            raise ValidationError(_("Bitte einen Jahrgang Ihrer Stufe wählen."))
        return jg


class KontaktForm(forms.ModelForm):
    class Meta:
        model = AnmeldeKontakt
        fields = ["art", "anrede", "vorname", "nachname", "email", "mobil", "telefon", "sprache", "korrespondenzweg",
                  "beruf", "arbeitgeber", "sorgerecht", "abholberechtigt", "notfallkontakt", "rechnungsempfaenger",
                  "adresse_wie_kind", "strasse", "postfach", "plz", "ort", "land"]


def kontakt_formset(user, a=None, data=None):
    neu = a is None or user.has_perm("aufnahme.add_anmeldekontakt")
    loeschen = a is not None and user.has_perm("aufnahme.delete_anmeldekontakt")
    extra = (2 if a is None else (1 if not a.kontakte.exists() else 0)) if neu else 0
    fs = inlineformset_factory(Anmeldung, AnmeldeKontakt, form=KontaktForm, extra=extra, can_delete=loeschen,
                               max_num=6 if neu else 0, validate_max=True)
    initial = [{"art": "mutter"}, {"art": "vater"}] if a is None else None
    return fs(data, instance=a or Anmeldung(), prefix="kontakt", initial=initial)


class MehrfachDateiWidget(forms.ClearableFileInput):
    allow_multiple_selected = True


class MehrfachDateiFeld(forms.FileField):
    widget = MehrfachDateiWidget

    def clean(self, data, initial=None):
        einzeln = super().clean
        if isinstance(data, (list, tuple)):
            ergebnis = [einzeln(d, initial) for d in data if d]
        else:
            ergebnis = [einzeln(data, initial)] if data else []
        for d in ergebnis:
            groesse_pruefen(d)
        if self.required and not ergebnis:
            raise ValidationError(self.error_messages["required"], code="required")
        return ergebnis


class DateiForm(forms.Form):
    dateien = MehrfachDateiFeld(label=_("Dateien"), required=True)
    kategorie = forms.ChoiceField(label=_("Kategorie"), choices=Dokument.KATEGORIEN, initial="zeugnis")
    titel = forms.CharField(label=_("Titel"), max_length=120, required=False,
                            help_text=_("leer = Dateiname"))
    notiz = forms.CharField(label=_("Notiz"), max_length=200, required=False)


class ZeugnisseForm(forms.Form):
    zeugnisse = MehrfachDateiFeld(label=_("Zeugnisse und weitere Unterlagen"), required=False)


class PunktForm(forms.ModelForm):
    class Meta:
        model = AnmeldePunkt
        fields = ["text", "zustaendig", "pflicht"]
        labels = {"text": _("Neuer Punkt")}


def dateien_speichern(a, dateien, user, kategorie="zeugnis", titel="", notiz=""):
    stufe = AnmeldeDatei.STUFE_NACH_KATEGORIE.get(kategorie, "akte")
    for d in dateien:
        stamm = os.path.splitext(os.path.basename(d.name))[0][:100]
        t = (f"{titel} – {stamm}" if len(dateien) > 1 else titel) if titel else stamm
        AnmeldeDatei.objects.create(anmeldung=a, datei=d, kategorie=kategorie, titel=t[:120], notiz=notiz,
                                    zugriffsstufe=stufe, hochgeladen_von=user)
    return len(dateien)


def _fehlertext(form):
    teile = []
    for feld, fehler in form.errors.items():
        label = form.fields[feld].label if feld in form.fields else ""
        teile.append(f"{label}: {' '.join(fehler)}" if label else " ".join(fehler))
    return "; ".join(teile)


def _anmeldung(request, pk):
    a = get_object_or_404(Anmeldung.objects.select_related("schuljahr", "bildungsgang", "vorlaeufige_klasse", "schueler__person"), pk=pk)
    if not rechte.darf_sehen(request.user, a):
        raise PermissionDenied
    return a


def _zur_akte(a, anker=""):
    return redirect(reverse("anmeldung", args=[a.pk]) + (f"#{anker}" if anker else ""))


# ---------------------------------------------------------------- Liste

STATUS_FILTER = [("offen", _("Offen")), *Anmeldung.STATUS, ("alle", _("Alle"))]


@login_required
def anmeldungen(request):
    if not rechte.darf_aufnahme(request.user):
        raise PermissionDenied
    user = request.user
    basis = rechte.anmeldungen_fuer(user)
    schuljahre = Schuljahr.objects.filter(pk__in=basis.values("schuljahr")).order_by("-beginn")
    sj = request.GET.get("sj", "")
    if sj.isdigit():
        basis = basis.filter(schuljahr_id=int(sj))
    zaehler = dict(basis.values_list("status").annotate(n=Count("pk")))
    status = request.GET.get("status", "offen")
    qs = basis
    if status == "offen":
        qs = qs.filter(status__in=Anmeldung.OFFEN)
    elif status in dict(Anmeldung.STATUS):
        qs = qs.filter(status=status)
    jahrgang = request.GET.get("jahrgang", "")
    if jahrgang.isdigit():
        qs = qs.filter(jahrgang=int(jahrgang))
    q = request.GET.get("q", "").strip()
    if q:
        for wort in q.split():
            qs = qs.filter(Q(vorname__icontains=wort) | Q(nachname__icontains=wort) | Q(rufname__icontains=wort)
                           | Q(nummer__icontains=wort) | Q(kontakte__nachname__icontains=wort)).distinct()
    eigene = rechte.eigene_zustaendigkeiten(user)
    qs = qs.select_related("schuljahr", "vorlaeufige_klasse", "bildungsgang").annotate(
        punkte_gesamt=Count("punkte", distinct=True),
        punkte_erledigt=Count("punkte", filter=Q(punkte__erledigt=True), distinct=True),
        pflicht_offen=Count("punkte", filter=Q(punkte__erledigt=False, punkte__pflicht=True), distinct=True),
        meine_offen=Count("punkte", filter=Q(punkte__erledigt=False, punkte__zustaendig__in=eigene), distinct=True),
        anzahl_dateien=Count("dateien", distinct=True),
    )
    nur_meine = request.GET.get("meine") == "1"
    if nur_meine:
        qs = qs.filter(meine_offen__gt=0)
    zeilen = list(qs.order_by("status", "-eingang", "-pk") if status == "alle" else qs.order_by("-eingang", "-pk"))
    for a in zeilen:
        a.prozent = round(100 * a.punkte_erledigt / a.punkte_gesamt) if a.punkte_gesamt else 0
    tabs = []
    for wert, name in STATUS_FILTER:
        if wert == "offen":
            n = sum(zaehler.get(s, 0) for s in Anmeldung.OFFEN)
        elif wert == "alle":
            n = sum(zaehler.values())
        else:
            n = zaehler.get(wert, 0)
        param = {k: v for k, v in (("sj", sj), ("jahrgang", jahrgang), ("q", q)) if v}
        param["status"] = wert
        tabs.append({"wert": wert, "name": name, "anzahl": n, "aktiv": wert == status, "url": "?" + urlencode(param)})
    return render(request, "aufnahme/liste.html", {
        "zeilen": zeilen, "tabs": tabs, "status": status, "schuljahre": schuljahre, "sj": sj, "jahrgang": jahrgang, "q": q,
        "nur_meine": nur_meine, "eigene": eigene,
        "jahrgaenge": sorted(j for j in basis.values_list("jahrgang", flat=True).distinct() if j is not None),
        "darf_anlegen": user.has_perm("aufnahme.add_anmeldung"),
        "zugesagt": zaehler.get(Anmeldung.ZUGESAGT, 0),
    })


# ---------------------------------------------------------------- Erfassen und bearbeiten

def _vorlagen_auswahl(jahrgang=None):
    vorlagen = list(ChecklistenVorlage.objects.filter(aktiv=True).annotate(anzahl=Count("punkte")).order_by("reihenfolge", "name"))
    for v in vorlagen:
        v.vorgewaehlt = v.passt_zu(jahrgang)
    return vorlagen


@login_required
def anmeldung_neu(request):
    user = request.user
    if not (rechte.darf_aufnahme(user) and user.has_perm("aufnahme.add_anmeldung")):
        raise PermissionDenied
    form = AnmeldungForm(request.POST or None, user=user)
    kontakte = kontakt_formset(user, None, request.POST or None)
    dateien = ZeugnisseForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid() and kontakte.is_valid() and dateien.is_valid():
        with transaction.atomic():
            a = form.save(commit=False)
            a.erstellt_von = user
            a.save()
            kontakte.instance = a
            for i, k in enumerate(kontakte.save(commit=False), start=1):
                k.anmeldung, k.reihenfolge = a, i
                k.save()
            gewaehlt = ChecklistenVorlage.objects.filter(pk__in=[v for v in request.POST.getlist("vorlagen") if v.isdigit()])
            for v in gewaehlt.order_by("reihenfolge"):
                a.punkte_aus_vorlage(v)
            n = dateien_speichern(a, dateien.cleaned_data["zeugnisse"], user)
        messages.success(request, gettext("Anmeldung %(nr)s für %(name)s angelegt.") % {"nr": a.nummer, "name": a.anzeigename}
                         + (" " + ngettext("%(n)s Datei gespeichert.", "%(n)s Dateien gespeichert.", n) % {"n": n} if n else ""))
        return redirect("anmeldung", pk=a.pk)
    gewaehlt = set(request.POST.getlist("vorlagen")) if request.method == "POST" else None
    vorlagen = _vorlagen_auswahl()
    if gewaehlt is not None:
        for v in vorlagen:
            v.vorgewaehlt = str(v.pk) in gewaehlt
    return render(request, "aufnahme/formular.html", {
        "form": form, "kontakte": kontakte, "dateien_form": dateien, "vorlagen": vorlagen, "neu": True,
        "darf_kind": True, "darf_kontakte": True,
    })


@login_required
def anmeldung_bearbeiten(request, pk):
    a = _anmeldung(request, pk)
    user = request.user
    darf_kind = rechte.darf_bearbeiten(user, a)
    darf_kontakte = rechte.darf_kontakte_bearbeiten(user, a)
    if not (darf_kind or darf_kontakte):
        raise PermissionDenied
    daten = request.POST if request.method == "POST" else None
    form = AnmeldungForm(daten if darf_kind else None, instance=a, user=user)
    if not darf_kind:
        for f in form.fields.values():
            f.disabled = True
    kontakte = kontakt_formset(user, a, daten if darf_kontakte else None)
    if request.method == "POST":
        ok = (not darf_kind or form.is_valid()) and (not darf_kontakte or kontakte.is_valid())
        if ok:
            with transaction.atomic():
                if darf_kind:
                    form.save()
                if darf_kontakte:
                    rf = (a.kontakte.order_by("-reihenfolge").values_list("reihenfolge", flat=True).first() or 0)
                    for k in kontakte.save(commit=False):
                        if not k.pk:
                            rf += 1
                            k.reihenfolge = rf
                        k.anmeldung = a
                        k.save()
                    for k in kontakte.deleted_objects:
                        k.delete()
            messages.success(request, gettext("Änderungen an der Anmeldung %(nr)s gespeichert.") % {"nr": a.nummer})
            return redirect("anmeldung", pk=a.pk)
    return render(request, "aufnahme/formular.html", {
        "a": a, "form": form, "kontakte": kontakte, "neu": False, "darf_kind": darf_kind, "darf_kontakte": darf_kontakte,
    })


# ---------------------------------------------------------------- Bewerbungsakte

def klassen_auswahl(user, a):
    """Stammklassen des Ziel-Schuljahres mit aktueller Größe und vorläufigen Zuordnungen."""
    qs = Gruppe.objects.filter(schuljahr=a.schuljahr, typ=Gruppe.STAMMKLASSE)
    erlaubt = rechte.erlaubte_jahrgaenge(user)
    if erlaubt is not None:
        qs = qs.filter(Q(jahrgang__in=erlaubt) | Q(pk=a.vorlaeufige_klasse_id))
    stichtag = max(a.eintritt, timezone.localdate()) if a.eintritt else None
    belegung = dict(Mitgliedschaft.objects.aktiv(stichtag).filter(gruppe__in=qs).values_list("gruppe").annotate(n=Count("pk")))
    vorlaeufig = dict(Anmeldung.objects.filter(vorlaeufige_klasse__in=qs, status__in=Anmeldung.OFFEN).exclude(pk=a.pk)
                      .values_list("vorlaeufige_klasse").annotate(n=Count("pk")))
    klassen = list(qs.select_related("leitung__person"))
    klassen.sort(key=lambda g: (g.jahrgang != a.jahrgang, g.jahrgang or 99, g.name))
    for g in klassen:
        g.belegung = belegung.get(g.pk, 0)
        g.vorlaeufig = vorlaeufig.get(g.pk, 0)
        g.passend = a.jahrgang is None or g.jahrgang == a.jahrgang
    return klassen


@login_required
def anmeldung(request, pk):
    a = _anmeldung(request, pk)
    user = request.user
    darf = {
        "bearbeiten": rechte.darf_bearbeiten(user, a),
        "kontakte": rechte.darf_kontakte_bearbeiten(user, a),
        "hochladen": rechte.darf_dateien_hochladen(user, a),
        "abhaken": rechte.darf_abhaken(user, a),
        "zusammenstellen": rechte.darf_checkliste_zusammenstellen(user, a),
        "uebernehmen": rechte.darf_uebernehmen(user, a),
        "loeschen": rechte.darf_loeschen(user, a),
    }
    aelteste = request.GET.get("sortierung") == "alt"
    dateien = list(a.dateien.select_related("hochgeladen_von__person").order_by(
        *(("hochgeladen_am", "pk") if aelteste else ("-hochgeladen_am", "-pk"))))
    for d in dateien:
        d.inline_moeglich = d.inhaltstyp in INLINE_TYPEN
        d.darf_loeschen = rechte.darf_datei_loeschen(user, d)
    punkte = list(a.punkte.select_related("erledigt_von__person"))
    eigene = rechte.eigene_zustaendigkeiten(user)
    for p in punkte:
        p.meins = p.zustaendig in eigene and not p.erledigt
    fortschritt = a.fortschritt()
    vorhandene_texte = {p.text.strip().lower() for p in punkte}
    vorlagen = []
    if darf["zusammenstellen"]:
        for v in ChecklistenVorlage.objects.filter(aktiv=True).prefetch_related("punkte"):
            fehlend = [vp for vp in v.punkte.all() if vp.text.strip().lower() not in vorhandene_texte]
            if fehlend:
                v.fehlend = len(fehlend)
                vorlagen.append(v)
    return render(request, "aufnahme/anmeldung.html", {
        "a": a, "darf": darf, "kontakte": list(a.kontakte.all()), "dateien": dateien, "aelteste": aelteste,
        "punkte": punkte, "fortschritt": fortschritt, "vorlagen": vorlagen,
        "punkt_form": PunktForm(prefix="punkt") if darf["zusammenstellen"] else None,
        "datei_form": DateiForm(prefix="datei") if darf["hochladen"] else None,
        "klassen": klassen_auswahl(user, a) if darf["bearbeiten"] else [],
        "status_auswahl": [(w, n) for w, n in Anmeldung.STATUS if w != Anmeldung.UEBERNOMMEN],
        "hindernisse": hindernisse(a) if not a.abgeschlossen else [],
        "stufen": Dokument.STUFEN, "zustaendig": ZUSTAENDIG,
        "historie": verlauf(a),
    })


def verlauf(a, anzahl=8):
    """Letzte Änderungen der Anmeldung in Worten: angelegt, Statuswechsel, geänderte Felder."""
    eintraege = []
    for h in a.history.select_related("history_user__person").order_by("-history_date")[:anzahl]:
        if h.history_type == "+":
            text = gettext("angelegt")
        else:
            vorher = h.prev_record
            if vorher is None:
                continue
            delta = h.diff_against(vorher, excluded_fields=["geaendert", "status_seit"])
            felder = [c.field for c in delta.changes]
            if not felder:
                continue
            if "status" in felder:
                text = gettext("Status: %(status)s") % {"status": h.get_status_display()}
                felder.remove("status")
            else:
                text = ""
            if felder:
                namen = ", ".join(str(Anmeldung._meta.get_field(f).verbose_name) for f in felder)
                text = (text + " · " if text else "") + gettext("geändert: %(felder)s") % {"felder": namen}
        wer = ""
        if h.history_user:
            person = getattr(h.history_user, "person", None)
            wer = person.anzeigename if person else h.history_user.get_username()
        eintraege.append({"datum": h.history_date, "text": text, "wer": wer})
    return eintraege


@login_required
@require_POST
def anmeldung_aktion(request, pk):
    a = _anmeldung(request, pk)
    user = request.user
    aktion = request.POST.get("aktion", "")

    if aktion == "status":
        if not rechte.darf_bearbeiten(user, a):
            raise PermissionDenied
        neu = request.POST.get("status", "")
        if neu not in dict(Anmeldung.STATUS) or neu == Anmeldung.UEBERNOMMEN:
            raise Http404
        if neu != a.status:
            a.status, a.status_seit = neu, timezone.localdate()
            a.save(update_fields=["status", "status_seit", "geaendert"])
            messages.success(request, gettext("Status: %(status)s.") % {"status": a.get_status_display()})
        return _zur_akte(a)

    if aktion == "klasse":
        if not rechte.darf_bearbeiten(user, a):
            raise PermissionDenied
        wert = request.POST.get("klasse", "")
        if not wert:
            a.vorlaeufige_klasse = None
            a.save(update_fields=["vorlaeufige_klasse", "geaendert"])
            messages.success(request, gettext("Vorläufige Klasse entfernt."))
            return _zur_akte(a, "klasse")
        klasse = next((g for g in klassen_auswahl(user, a) if str(g.pk) == wert), None)
        if klasse is None:
            raise PermissionDenied
        a.vorlaeufige_klasse = klasse
        felder = ["vorlaeufige_klasse", "geaendert"]
        if a.jahrgang is None and klasse.jahrgang:
            a.jahrgang = klasse.jahrgang
            felder.append("jahrgang")
        a.save(update_fields=felder)
        messages.success(request, gettext("Vorläufige Klasse: %(klasse)s.") % {"klasse": klasse.name})
        return _zur_akte(a, "klasse")

    if aktion in ("abhaken", "zuruecknehmen", "bemerkung"):
        if not rechte.darf_abhaken(user, a):
            raise PermissionDenied
        p = get_object_or_404(AnmeldePunkt, pk=request.POST.get("punkt"), anmeldung=a)
        if aktion == "bemerkung":
            p.bemerkung = request.POST.get("bemerkung", "").strip()[:200]
            p.save(update_fields=["bemerkung"])
        else:
            p.abhaken(user, aktion == "abhaken")
        return _zur_akte(a, f"punkt-{p.pk}")

    if aktion in ("punkt_neu", "punkt_loeschen", "pflicht", "vorlage"):
        if not rechte.darf_checkliste_zusammenstellen(user, a):
            raise PermissionDenied
        if aktion == "punkt_neu":
            form = PunktForm(request.POST, prefix="punkt")
            if form.is_valid():
                p = form.save(commit=False)
                p.anmeldung = a
                p.reihenfolge = (a.punkte.order_by("-reihenfolge").values_list("reihenfolge", flat=True).first() or 0) + 10
                p.save()
                messages.success(request, gettext("Punkt „%(text)s“ ergänzt.") % {"text": p.text})
            else:
                messages.error(request, _fehlertext(form))
        elif aktion == "punkt_loeschen":
            p = get_object_or_404(AnmeldePunkt, pk=request.POST.get("punkt"), anmeldung=a)
            p.delete()
            messages.success(request, gettext("Punkt „%(text)s“ entfernt.") % {"text": p.lokal_text})
        elif aktion == "pflicht":
            p = get_object_or_404(AnmeldePunkt, pk=request.POST.get("punkt"), anmeldung=a)
            p.pflicht = not p.pflicht
            p.save(update_fields=["pflicht"])
        else:
            v = get_object_or_404(ChecklistenVorlage, pk=request.POST.get("vorlage"))
            n = a.punkte_aus_vorlage(v)
            messages.success(request, ngettext("%(n)s Punkt aus „%(vorlage)s“ ergänzt.", "%(n)s Punkte aus „%(vorlage)s“ ergänzt.", n)
                             % {"n": n, "vorlage": v.lokal_name})
        return _zur_akte(a, "checkliste")

    if aktion == "datei":
        d = get_object_or_404(AnmeldeDatei, pk=request.POST.get("datei"), anmeldung=a)
        if not rechte.darf_bearbeiten(user, a):
            raise PermissionDenied
        stufe = request.POST.get("zugriffsstufe")
        if stufe in dict(Dokument.STUFEN):
            d.zugriffsstufe = stufe
        d.uebernehmen = request.POST.get("uebernehmen") == "1"
        d.save(update_fields=["zugriffsstufe", "uebernehmen"])
        return _zur_akte(a, "dateien")

    raise Http404


@login_required
@require_POST
def datei_hochladen(request, pk):
    a = _anmeldung(request, pk)
    if not rechte.darf_dateien_hochladen(request.user, a):
        raise PermissionDenied
    form = DateiForm(request.POST, request.FILES, prefix="datei")
    if form.is_valid():
        c = form.cleaned_data
        n = dateien_speichern(a, c["dateien"], request.user, c["kategorie"], c["titel"].strip(), c["notiz"].strip())
        messages.success(request, ngettext("%(n)s Datei gespeichert.", "%(n)s Dateien gespeichert.", n) % {"n": n})
    else:
        messages.error(request, gettext("Nicht gespeichert – %(fehler)s") % {"fehler": _fehlertext(form)})
    return _zur_akte(a, "dateien")


def _datei(request, d):
    if not rechte.darf_sehen(request.user, d.anmeldung):
        raise PermissionDenied
    return datei_ausliefern(request, d.datei, d.inhaltstyp, d.originalname)


@login_required
def datei(request, pk):
    return _datei(request, get_object_or_404(AnmeldeDatei.objects.select_related("anmeldung"), pk=pk))


@login_required
def datei_pfad(request, name):
    d = AnmeldeDatei.objects.select_related("anmeldung").filter(datei=name).first()
    if d is None:
        raise Http404
    return _datei(request, d)


@login_required
@require_POST
def datei_loeschen(request, pk):
    d = get_object_or_404(AnmeldeDatei.objects.select_related("anmeldung"), pk=pk)
    if not rechte.darf_datei_loeschen(request.user, d):
        raise PermissionDenied
    a, titel = d.anmeldung, d.titel
    d.delete()
    messages.success(request, gettext("Datei „%(titel)s“ gelöscht.") % {"titel": titel})
    return _zur_akte(a, "dateien")


@login_required
@require_POST
def anmeldung_loeschen(request, pk):
    a = _anmeldung(request, pk)
    if not rechte.darf_loeschen(request.user, a):
        raise PermissionDenied
    text = str(a)
    a.delete()
    messages.success(request, gettext("Anmeldung %(text)s mit allen Unterlagen gelöscht.") % {"text": text})
    return redirect("anmeldungen")


# ---------------------------------------------------------------- Übernahme

@login_required
def anmeldung_uebernahme(request, pk):
    a = _anmeldung(request, pk)
    user = request.user
    if a.abgeschlossen and a.schueler_id:
        return redirect("schuelerakte", pk=a.schueler_id)
    if not rechte.darf_uebernehmen(user, a):
        raise PermissionDenied
    kontakte = list(a.kontakte.all())
    for k in kontakte:
        k.kandidaten = kontakt_kandidaten(k)
    dubletten = moegliche_dubletten(a)
    gruende = hindernisse(a)
    fehler = []
    if request.method == "POST" and not gruende:
        zuordnung = {}
        for k in kontakte:
            wahl = request.POST.get(f"kontakt-{k.pk}", "neu")
            if wahl != "neu":
                person = next((p for p in k.kandidaten if str(p.pk) == wahl), None)
                if person is None:
                    raise PermissionDenied
                zuordnung[k.pk] = person
        if dubletten and request.POST.get("dubletten_geprueft") != "1":
            fehler.append(gettext("Bitte bestätigen, dass die gefundenen Personen nicht identisch mit dem Kind sind."))
        if not fehler:
            try:
                schueler = uebernehmen(a, user, zuordnung, dateien_uebernehmen=request.POST.get("dateien", "1") == "1")
            except ValidationError as e:
                fehler.extend(e.messages)
            else:
                messages.success(request, gettext(
                    "%(name)s wurde als Schüler:in übernommen (Schülernummer %(nr)s).") % {
                    "name": schueler.person.anzeigename, "nr": schueler.schuelernummer})
                return redirect("schuelerakte", pk=schueler.pk)
    return render(request, "aufnahme/uebernahme.html", {
        "a": a, "kontakte": kontakte, "dubletten": dubletten, "hindernisse": gruende, "hinweise": hinweise(a),
        "fehler": fehler, "dateien": list(a.dateien.filter(uebernehmen=True).order_by("hochgeladen_am")),
        "nicht_uebernommen": a.dateien.filter(uebernehmen=False).count(), "fortschritt": a.fortschritt(),
    })


# ---------------------------------------------------------------- Startseite

def start_hinweise(user):
    """Kurzüberblick für die Startseite – oder None ohne Zugriff."""
    if not rechte.darf_aufnahme(user):
        return None
    qs = rechte.anmeldungen_fuer(user).filter(status__in=Anmeldung.OFFEN)
    eigene = rechte.eigene_zustaendigkeiten(user)
    meine = list(qs.annotate(n=Count("punkte", filter=Q(punkte__erledigt=False, punkte__zustaendig__in=eigene)))
                 .filter(n__gt=0).select_related("vorlaeufige_klasse").order_by("eingang")[:6]) if eigene else []
    zaehler = dict(qs.values_list("status").annotate(n=Count("pk")))
    return {
        "offen": sum(zaehler.values()),
        "eingegangen": zaehler.get(Anmeldung.EINGEGANGEN, 0) + zaehler.get(Anmeldung.PRUEFUNG, 0),
        "warteliste": zaehler.get(Anmeldung.WARTELISTE, 0),
        "zugesagt": zaehler.get(Anmeldung.ZUGESAGT, 0),
        "meine": meine,
        "darf_anlegen": user.has_perm("aufnahme.add_anmeldung"),
    }

