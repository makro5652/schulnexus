"""Noten im Portal (ab 0.4.7.0): Schnelleingabe, Bewertungsstruktur, Leistungsvorgaben."""
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import get_language, gettext, gettext_lazy as _, ngettext
from django.views.decorators.http import require_POST

from portal.rechte import ist_schulleitung, ist_verwaltung, personal_von
from stammdaten.models import Abschnitt, Fach, Schuljahr

from . import eingabe as E
from . import rechte
from . import vorgaben as V
from .berechnung import Baum, nominale_anteile
from .models import (
    GEWICHTSARTEN, PROZENT, Bewertungsordner, Leistungsnachweis, Leistungsvorgabe, Note, Notenschluessel, Unterricht,
)

HUNDERT = Decimal(100)


def _unterricht(request, pk):
    u = get_object_or_404(Unterricht.objects.select_related("fach", "gruppe", "abschnitt", "skala", "lehrkraft__person"), pk=pk)
    if not rechte.darf_noten_eintragen(request.user, u):
        raise PermissionDenied
    return u


def _zahl(wert):
    if wert is None:
        return ""
    return format(Decimal(wert).normalize(), "f").replace(".", ",")


def _dezimal(text):
    try:
        return Decimal((text or "").strip().replace(",", "."))
    except InvalidOperation:
        return None


def summen(baum, ohne_ln=None):
    """Summe der Gewichte je Ebene: {ordner_id oder None: Summe} (Unterordner und Leistungsnachweise)."""
    erg = {}
    for eltern_id, kinder in baum.kinder.items():
        erg[eltern_id] = erg.get(eltern_id, Decimal(0)) + sum((k.gewicht for k in kinder), Decimal(0))
    for ordner_id, nachweise in baum.nachweise_in.items():
        erg[ordner_id] = erg.get(ordner_id, Decimal(0)) + sum((ln.gewicht for ln in nachweise if ln.pk != ohne_ln), Decimal(0))
    return erg


def gewicht_text(gewicht, art):
    return f"{_zahl(gewicht)} %" if art == PROZENT else f"×{_zahl(gewicht)}"


# ---------------------------------------------------------------- Schnelleingabe

class NachweisForm(forms.ModelForm):
    ordner = forms.TypedChoiceField(label=_("Ordner"), coerce=int)

    class Meta:
        model = Leistungsnachweis
        fields = ["titel", "datum", "gewicht", "schluessel", "max_be"]
        widgets = {
            "datum": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "gewicht": forms.TextInput(attrs={"inputmode": "decimal", "size": 6}),
            "max_be": forms.TextInput(attrs={"inputmode": "decimal", "size": 6}),
            "titel": forms.TextInput(attrs={"list": "ne-titel", "autocomplete": "off"}),
        }

    def __init__(self, *args, unterricht, baum, **kwargs):
        super().__init__(*args, **kwargs)
        self.unterricht = unterricht
        self.fields["ordner"].choices = [(o.pk, pfad) for o, _ebene, pfad in baum.in_reihenfolge()]
        self.fields["schluessel"].queryset = Notenschluessel.objects.filter(skala=unterricht.skala)
        self.fields["schluessel"].required = False
        self.fields["gewicht"].localize = True
        self.fields["max_be"].localize = True
        if self.instance.pk:
            self.fields["ordner"].initial = self.instance.ordner_id

    def clean_ordner(self):
        o = Bewertungsordner.objects.filter(pk=self.cleaned_data["ordner"], unterricht=self.unterricht).first()
        if o is None:
            raise ValidationError(gettext("Bitte einen Ordner wählen."))
        return o

    def clean(self):
        daten = super().clean()
        o, g = daten.get("ordner"), daten.get("gewicht")
        if o is not None and g is not None and o.gewichtsart == PROZENT and g > HUNDERT:
            self.add_error("gewicht", gettext("In einem Prozent-Ordner höchstens 100."))
        return daten

    def _post_clean(self):
        if self.cleaned_data.get("ordner") is not None:
            self.instance.ordner = self.cleaned_data["ordner"]
            self.instance.unterricht_id = self.cleaned_data["ordner"].unterricht_id
        super()._post_clean()


@login_required
def noten_eintragen(request, pk, ln_pk=None):
    u = _unterricht(request, pk)
    ln = get_object_or_404(Leistungsnachweis.objects.select_related("ordner", "schluessel"), pk=ln_pk, unterricht=u) if ln_pk else None
    baum = Baum(u)
    if not baum.ordner:
        messages.info(request, gettext("Bitte zuerst einen Ordner anlegen, z. B. „Schriftlich“ oder „Sonstige Mitarbeit“."))
        return redirect("bewertungsstruktur", pk=u.pk)
    schueler = list(u.schueler())
    instanz = ln or Leistungsnachweis(unterricht=u, datum=timezone.localdate())
    fehler, werte = {}, {}

    if request.method == "POST":
        form = NachweisForm(request.POST, instance=instanz, unterricht=u, baum=baum)
        eingaben = {s.pk: {"note": request.POST.get(f"n_{s.pk}", ""), "kommentar": request.POST.get(f"k_{s.pk}", ""),
                           "gewicht": request.POST.get(f"g_{s.pk}", ""), "begruendung": request.POST.get(f"b_{s.pk}", "")}
                    for s in schueler}
        werte = eingaben
        if form.is_valid():
            vorlaeufig = form.save(commit=False)
            ergebnisse, fehler = E.pruefen(vorlaeufig, eingaben, schueler)
            if not fehler:
                with transaction.atomic():
                    vorlaeufig.save()
                    vorlaeufig.notenzeilen_anlegen()
                    n = E.speichern(vorlaeufig, ergebnisse)
                messages.success(request, ngettext("„%(titel)s“ gespeichert, %(n)s Note geändert.",
                                                   "„%(titel)s“ gespeichert, %(n)s Noten geändert.", n) % {"titel": vorlaeufig.titel, "n": n})
                if request.POST.get("weiter") == "neu":
                    return redirect(reverse("noten_eintragen", args=[u.pk]) + f"?ordner={vorlaeufig.ordner_id}")
                return redirect("notenuebersicht", pk=u.pk)
            messages.error(request, ngettext("%(n)s Eingabe ist nicht gültig – es wurde nichts gespeichert.",
                                             "%(n)s Eingaben sind nicht gültig – es wurde nichts gespeichert.", len(fehler)) % {"n": len(fehler)})
    else:
        initial = {}
        if not ln:
            ordner = request.GET.get("ordner")
            if ordner and any(str(o.pk) == ordner for o in baum.ordner):
                initial["ordner"] = int(ordner)
            initial.update({"datum": timezone.localdate(), "gewicht": Decimal(1), "titel": request.GET.get("titel", "")})
        form = NachweisForm(instance=instanz, unterricht=u, baum=baum, initial=initial)
        if ln:
            for n in Note.objects.filter(leistungsnachweis=ln).select_related("stufe", "leistungsnachweis"):
                werte[n.schueler_id] = {"note": E.anzeige(n), "kommentar": n.kommentar,
                                        "gewicht": _zahl(n.gewicht_individuell), "begruendung": n.gewicht_begruendung}

    summe = summen(baum, ohne_ln=ln.pk if ln else None)
    ordner_optionen = [{"pk": o.pk, "name": o.name, "pfad": pfad, "ebene": ebene, "art": o.gewichtsart,
                        "einzug": "\u00a0\u00a0\u00a0" * ebene + ("└ " if ebene else ""),
                        "summe": _zahl(summe.get(o.pk, Decimal(0)))} for o, ebene, pfad in baum.in_reihenfolge()]
    zeilen = [{"s": s, "w": werte.get(s.pk, {}), "fehler": fehler.get(s.pk)} for s in schueler]
    schluessel = {str(k.pk): [[float(sw.min_prozent), sw.stufe.bezeichnung] for sw in k.schwellen.select_related("stufe").order_by("-min_prozent")]
                  for k in Notenschluessel.objects.filter(skala=u.skala).prefetch_related("schwellen")}
    return render(request, "noten/eingabe.html", {
        "u": u, "ln": ln, "form": form, "zeilen": zeilen, "ordner_optionen": ordner_optionen,
        "gewaehlt": str(form["ordner"].value() or ""),
        "erlaubt_liste": [s.bezeichnung for s in u.skala.stufen.all()],
        "schluessel": schluessel,
        "texte": {
            "entschuldigt": gettext("entschuldigt"), "unentschuldigt": gettext("unentschuldigt"), "befreit": gettext("befreit"),
            "nicht_bewertbar": gettext("nicht bewertbar"), "ungueltig": gettext("keine gültige Note"),
            "be_ungueltig": gettext("BE ungültig"), "summe": gettext("In diesem Ordner bisher vergeben: {a} %, mit diesem Eintrag: {b} %"),
            "komma": "," if (get_language() or "de").startswith("de") else ".",
            "verlassen": gettext("Es gibt ungespeicherte Eingaben."),
        },
        "titel_vorschlaege": sorted({t for t in Leistungsnachweis.objects.filter(unterricht=u).values_list("titel", flat=True)}),
        "einzelgewichte": any(z["w"].get("gewicht") for z in zeilen),
    })


# ---------------------------------------------------------------- Bewertungsstruktur

@login_required
def struktur(request, pk):
    u = _unterricht(request, pk)
    if request.method == "POST":
        aktion, _sep, ziel = (request.POST.get("aktion") or "").partition(":")
        try:
            with transaction.atomic():
                if aktion == "speichern":
                    _struktur_speichern(request, u)
                    messages.success(request, gettext("Bewertungsstruktur gespeichert."))
                elif aktion == "ordner_neu":
                    eltern = Bewertungsordner.objects.filter(pk=request.POST.get("eltern") or 0, unterricht=u).first()
                    art = eltern.gewichtsart if eltern else u.gewichtsart
                    gewicht = _dezimal(request.POST.get("gewicht")) if request.POST.get("gewicht", "").strip() else Decimal(1)
                    _gewicht_pruefen(gewicht, art, request.POST.get("name", ""))
                    o = Bewertungsordner(unterricht=u, eltern=eltern, name=request.POST.get("name", "").strip(), gewicht=gewicht,
                                         reihenfolge=(Bewertungsordner.objects.filter(unterricht=u, eltern=eltern).count() + 1) * 10)
                    o.full_clean()
                    o.save()
                    messages.success(request, gettext("Ordner „%(name)s“ angelegt.") % {"name": o.name})
                elif aktion == "ordner_loeschen":
                    o = get_object_or_404(Bewertungsordner, pk=ziel or request.POST.get("ordner"), unterricht=u)
                    if o.unterordner.exists() or o.leistungsnachweise.exists():
                        raise ValidationError(gettext("Nur leere Ordner lassen sich löschen."))
                    o.delete()
                    messages.success(request, gettext("Ordner „%(name)s“ gelöscht.") % {"name": o.name})
                elif aktion == "ln_loeschen":
                    ln = get_object_or_404(Leistungsnachweis, pk=ziel or request.POST.get("ln"), unterricht=u)
                    n = ln.noten.exclude(stufe__isnull=True, sonderstatus="").count()
                    ln.delete()
                    messages.success(request, ngettext("„%(titel)s“ mit %(n)s Note gelöscht.", "„%(titel)s“ mit %(n)s Noten gelöscht.", n)
                                     % {"titel": ln.titel, "n": n})
        except ValidationError as f:
            messages.error(request, " ".join(f.messages))
        return redirect("bewertungsstruktur", pk=u.pk)

    baum = Baum(u)
    anteil_o, anteil_ln = nominale_anteile(baum.ordner, baum.nachweise)
    summe = summen(baum)
    noten_je_ln = {}
    for ln_id in Note.objects.filter(leistungsnachweis__unterricht=u).exclude(stufe__isnull=True, sonderstatus="").values_list(
            "leistungsnachweis_id", flat=True):
        noten_je_ln[ln_id] = noten_je_ln.get(ln_id, 0) + 1
    art_von = {o.pk: o.gewichtsart for o in baum.ordner}

    def ebene_info(eltern_id, art):
        s = summe.get(eltern_id, Decimal(0))
        return {"art": art, "summe": _zahl(s), "abweichung": art == PROZENT and s != HUNDERT and s > 0,
                "fehlt": _zahl(HUNDERT - s) if s < HUNDERT else "", "zuviel": _zahl(s - HUNDERT) if s > HUNDERT else ""}

    zeilen = []
    for o, ebene, pfad in baum.in_reihenfolge():
        eltern_art = art_von.get(o.eltern_id) if o.eltern_id else u.gewichtsart
        zeilen.append({"typ": "ordner", "o": o, "ebene": ebene, "einzug": ebene * 1.4, "eltern_art": eltern_art,
                       "anteil": anteil_o.get(o.pk), "info": ebene_info(o.pk, o.gewichtsart),
                       "leer": not baum.kinder[o.pk] and not baum.nachweise_in[o.pk]})
        for ln in baum.nachweise_in[o.pk]:
            zeilen.append({"typ": "ln", "ln": ln, "ebene": ebene + 1, "einzug": (ebene + 1) * 1.4, "eltern_art": o.gewichtsart,
                           "anteil": anteil_ln.get(ln.pk), "noten": noten_je_ln.get(ln.pk, 0)})
    return render(request, "noten/struktur.html", {
        "u": u, "zeilen": zeilen, "wurzel": ebene_info(None, u.gewichtsart), "gewichtsarten": GEWICHTSARTEN,
        "ordner_liste": [(o, "\u00a0\u00a0\u00a0" * ebene + o.name) for o, ebene, _p in baum.in_reihenfolge() if ebene < Bewertungsordner.MAX_TIEFE - 1],
    })


def _gewicht_pruefen(gewicht, art, wo):
    if gewicht is None or gewicht < 0:
        raise ValidationError(gettext("%(wo)s: Das Gewicht muss eine Zahl ab 0 sein.") % {"wo": wo})
    if art == PROZENT and gewicht > HUNDERT:
        raise ValidationError(gettext("%(wo)s: In einem Prozent-Ordner höchstens 100.") % {"wo": wo})


def _struktur_speichern(request, u):
    P = request.POST
    arten = dict(GEWICHTSARTEN)
    if P.get("art_wurzel") in arten:
        u.gewichtsart = P["art_wurzel"]
        u.save(update_fields=["gewichtsart"])
    ordner = list(Bewertungsordner.objects.filter(unterricht=u))
    for o in ordner:
        if P.get(f"art_{o.pk}") in arten:
            o.gewichtsart = P[f"art_{o.pk}"]
    art_von = {o.pk: o.gewichtsart for o in ordner}
    for o in ordner:
        name = (P.get(f"name_{o.pk}") or o.name).strip()
        if not name:
            raise ValidationError(gettext("Ein Ordner braucht einen Namen."))
        o.name = name
        if f"gewicht_{o.pk}" in P:
            o.gewicht = _dezimal(P[f"gewicht_{o.pk}"])
            _gewicht_pruefen(o.gewicht, art_von.get(o.eltern_id) if o.eltern_id else u.gewichtsart, name)
        if (P.get(f"reihenfolge_{o.pk}") or "").strip().isdigit():
            o.reihenfolge = int(P[f"reihenfolge_{o.pk}"])
        o.full_clean()
        o.save()
    for ln in Leistungsnachweis.objects.filter(unterricht=u).select_related("ordner"):
        if f"lgewicht_{ln.pk}" in P:
            g = _dezimal(P[f"lgewicht_{ln.pk}"])
            _gewicht_pruefen(g, art_von.get(ln.ordner_id), ln.titel)
            if g == 0:
                raise ValidationError(gettext("%(wo)s: Das Gewicht eines Leistungsnachweises muss größer als 0 sein.") % {"wo": ln.titel})
            if g != ln.gewicht:
                ln.gewicht = g
                ln.save(update_fields=["gewicht"])


# ---------------------------------------------------------------- Leistungsvorgaben

class VorgabeForm(forms.ModelForm):
    class Meta:
        model = Leistungsvorgabe
        fields = ["titel", "titel_en", "abschnitt", "jahrgang_von", "jahrgang_bis", "faecher", "ordner_enthaelt", "titel_enthaelt",
                  "mindestanzahl", "frist", "hinweis"]
        widgets = {
            "frist": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "faecher": forms.CheckboxSelectMultiple,
            "jahrgang_von": forms.NumberInput(attrs={"min": 1, "max": 13}),
            "jahrgang_bis": forms.NumberInput(attrs={"min": 1, "max": 13}),
            "mindestanzahl": forms.NumberInput(attrs={"min": 1, "max": 20}),
        }

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        heute = timezone.localdate()
        self.fields["abschnitt"].queryset = Abschnitt.objects.filter(ende__gte=heute - timedelta(days=200)).select_related("schuljahr").order_by("beginn")
        self.fields["abschnitt"].label_from_instance = lambda a: f"{a.schuljahr} – {a.lokal_name}"
        self.fields["faecher"].queryset = Fach.objects.order_by("reihenfolge", "name")
        self.fields["faecher"].label_from_instance = lambda f: f.lokal_name

    def clean(self):
        daten = super().clean()
        von, bis = daten.get("jahrgang_von"), daten.get("jahrgang_bis")
        erlaubt = rechte.vorgaben_jahrgaenge(self.user)
        if von and bis and not set(range(von, bis + 1)) <= erlaubt:
            raise ValidationError(gettext("Sie können Vorgaben nur für die Jahrgänge %(j)s anlegen.") % {
                "j": ", ".join(str(j) for j in sorted(erlaubt))})
        return daten


def _abschnitt_waehlen(request):
    alle = list(Abschnitt.objects.select_related("schuljahr").order_by("beginn"))
    gewaehlt = next((a for a in alle if str(a.pk) == request.GET.get("abschnitt")), None)
    if gewaehlt is None:
        heute = timezone.localdate()
        sj = Schuljahr.aktuelles()
        gewaehlt = next((a for a in alle if a.beginn <= heute <= a.ende), None) \
            or next((a for a in alle if sj and a.schuljahr_id == sj.pk), None) or (alle[-1] if alle else None)
    return alle, gewaehlt


def _sichtbarkeit(user):
    """(alle_sehen, jahrgaenge, eigene_unterricht_ids) – wer welche Zeilen der Übersicht sieht."""
    if ist_verwaltung(user) or ist_schulleitung(user) or user.is_superuser:
        return True, None, None
    jahrgaenge = rechte.vorgaben_jahrgaenge(user)
    p = personal_von(user)
    eigene = set(Unterricht.objects.filter(lehrkraft=p).values_list("pk", flat=True)) if p else set()
    return False, jahrgaenge, eigene


@login_required
def vorgaben(request):
    if not rechte.darf_vorgaben_sehen(request.user):
        raise PermissionDenied
    abschnitte, a = _abschnitt_waehlen(request)
    alle_sehen, jahrgaenge, eigene = _sichtbarkeit(request.user)
    nur_offen = request.GET.get("offen") == "1"
    vorrat = V.Vorrat()
    karten = []
    qs = Leistungsvorgabe.objects.filter(abschnitt=a).prefetch_related("faecher") if a else Leistungsvorgabe.objects.none()
    for v in qs:
        zeilen = []
        for u in v.unterrichte():
            if not (alle_sehen or (u.gruppe.jahrgang in (jahrgaenge or set())) or u.pk in (eigene or set())):
                continue
            zeilen.append(vorrat.stand(v, u))
        if not zeilen and not (alle_sehen or set(v.jahrgaenge) & (jahrgaenge or set())):
            continue
        zaehler = {k: sum(1 for z in zeilen if z.stand == k) for k in V.STAND_TEXT}
        if nur_offen:
            zeilen = [z for z in zeilen if not z.erfuellt]
        reihenfolge = {V.UEBERFAELLIG: 0, V.OFFEN: 1, V.IN_ARBEIT: 2, V.ERFUELLT: 3}
        zeilen.sort(key=lambda z: (reihenfolge[z.stand], z.unterricht.gruppe.name, z.unterricht.fach.reihenfolge))
        karten.append({"v": v, "zeilen": zeilen, "zaehler": zaehler, "gesamt": sum(zaehler.values()),
                       "darf_aendern": rechte.darf_vorgabe_aendern(request.user, v),
                       "faecher": ", ".join(f.lokal_name for f in v.faecher.all()) or gettext("alle Fächer")})
    return render(request, "noten/vorgaben.html", {
        "abschnitte": abschnitte, "a": a, "karten": karten, "nur_offen": nur_offen,
        "darf_verwalten": rechte.darf_vorgaben_verwalten(request.user), "heute": timezone.localdate(),
        "stand_text": V.STAND_TEXT,
    })


@login_required
def vorgabe_bearbeiten(request, pk=None):
    v = get_object_or_404(Leistungsvorgabe, pk=pk) if pk else None
    if v is not None and not rechte.darf_vorgabe_aendern(request.user, v):
        raise PermissionDenied
    if v is None and not rechte.darf_vorgaben_verwalten(request.user):
        raise PermissionDenied
    initial = {}
    if v is None:
        _alle, a = _abschnitt_waehlen(request)
        j = sorted(rechte.vorgaben_jahrgaenge(request.user) & set(range(5, 13))) or sorted(rechte.vorgaben_jahrgaenge(request.user))
        initial = {"abschnitt": a, "jahrgang_von": j[0] if j else None, "jahrgang_bis": j[-1] if j else None, "mindestanzahl": 1}
    form = VorgabeForm(request.POST or None, instance=v, user=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        neu = form.save(commit=False)
        if v is None:
            neu.angelegt_von = request.user
        neu.save()
        form.save_m2m()
        n = neu.unterrichte().count()
        messages.success(request, ngettext("Vorgabe „%(titel)s“ gespeichert – sie gilt für %(n)s Unterricht.",
                                           "Vorgabe „%(titel)s“ gespeichert – sie gilt für %(n)s Unterrichte.", n) % {"titel": neu.titel, "n": n})
        return redirect(reverse("leistungsvorgaben") + f"?abschnitt={neu.abschnitt_id}")
    return render(request, "noten/vorgabe_form.html", {"form": form, "v": v})


@login_required
@require_POST
def vorgabe_loeschen(request, pk):
    v = get_object_or_404(Leistungsvorgabe, pk=pk)
    if not (rechte.darf_vorgabe_aendern(request.user, v) and request.user.has_perm("noten.delete_leistungsvorgabe")):
        raise PermissionDenied
    a = v.abschnitt_id
    v.delete()
    messages.success(request, gettext("Vorgabe „%(titel)s“ gelöscht.") % {"titel": v.titel})
    return redirect(reverse("leistungsvorgaben") + f"?abschnitt={a}")


# ---------------------------------------------------------------- Startseite

def start_hinweise(user):
    """Lehrkräfte: Vorgaben mit Frist in den nächsten 14 Tagen bzw. überfällige. Leitung: Zahl überfälliger Vorgaben."""
    if not rechte.darf_vorgaben_sehen(user):
        return None
    sj = Schuljahr.aktuelles()
    if sj is None or not Leistungsvorgabe.objects.filter(abschnitt__schuljahr=sj).exists():
        return None
    heute = timezone.localdate()
    ergebnis = {}
    vorrat = V.Vorrat()
    p = personal_von(user)
    if p:
        meine = []
        for u in Unterricht.objects.filter(lehrkraft=p, abschnitt__schuljahr=sj).select_related("fach", "gruppe", "abschnitt"):
            for v in V.vorgaben_fuer(u).filter(frist__lte=heute + timedelta(days=V.BALD_TAGE)):
                st = vorrat.stand(v, u, heute)
                if not st.erfuellt:
                    meine.append(st)
        meine.sort(key=lambda st: (st.vorgabe.frist, st.unterricht.gruppe.name))
        if meine:
            ergebnis["meine"] = meine
    if rechte.darf_vorgaben_verwalten(user):
        jahrgaenge = rechte.vorgaben_jahrgaenge(user)
        ueberfaellig = 0
        for v in Leistungsvorgabe.objects.filter(abschnitt__schuljahr=sj, frist__lt=heute).prefetch_related("faecher"):
            for u in v.unterrichte():
                if u.gruppe.jahrgang in jahrgaenge and vorrat.stand(v, u, heute).stand == V.UEBERFAELLIG:
                    ueberfaellig += 1
        if ueberfaellig:
            ergebnis["ueberfaellig"] = ueberfaellig
    return ergebnis or None
