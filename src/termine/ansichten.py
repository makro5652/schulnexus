import calendar
import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import formats, timezone
from django.utils.translation import gettext, gettext_lazy as _, ngettext

from portal.rechte import personal_von
from stammdaten.models import Person, Schuelerprofil, Schuljahr

from . import rechte, sprechtag as S
from .models import Gespraechstermin, Raum, Raumbuchung, Sprechtag, Teilnahme, Termin, Zeitfenster

DATUM = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
ZEIT = forms.TimeInput(attrs={"type": "time"}, format="%H:%M")
DATUMZEIT = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")


def _reiter(aktiv, user):
    r = [{"url": "kalender", "name": _("Schulkalender"), "aktiv": aktiv == "kalender"}]
    if rechte.darf_raum_buchen(user) or rechte.darf_raeume_verwalten(user):
        r.append({"url": "raumplan", "name": _("Räume"), "aktiv": aktiv == "raeume"})
    r.append({"url": "sprechtage", "name": _("Sprechtage"), "aktiv": aktiv == "sprechtage"})
    return r


def _beschaeftigt(user):
    if not rechte.ist_beschaeftigt(user):
        raise PermissionDenied


def _zeit_aus_schluessel(k):
    try:
        return timezone.make_aware(datetime.strptime(k, "%Y-%m-%dT%H:%M"), timezone.get_current_timezone())
    except (TypeError, ValueError):
        return None


# ================================================================= Schulkalender

class TerminForm(forms.ModelForm):
    class Meta:
        model = Termin
        fields = ["titel", "titel_en", "art", "beginn", "ende", "uhrzeit_von", "uhrzeit_bis", "raum", "ort", "zielgruppe",
                  "beschreibung", "unterrichtsfrei", "fuer_eltern"]
        widgets = {"beginn": DATUM, "ende": DATUM, "uhrzeit_von": ZEIT, "uhrzeit_bis": ZEIT,
                   "beschreibung": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["raum"].queryset = Raum.objects.filter(aktiv=True)

    def clean(self):
        d = super().clean()
        raum, von, bis = d.get("raum"), d.get("uhrzeit_von"), d.get("uhrzeit_bis")
        if raum and not (von and bis):
            self.add_error("raum", gettext("Für eine Raumbelegung bitte Uhrzeit von und bis angeben."))
        elif raum and d.get("ende") and d.get("ende") != d.get("beginn"):
            self.add_error("raum", gettext("Räume lassen sich nur für eintägige Termine belegen; mehrtägig bitte unter Räume buchen."))
        elif raum and d.get("beginn"):
            b = Raumbuchung(raum=raum, datum=d["beginn"], von=von, bis=bis)
            andere = b.ueberschneidungen().exclude(termin_id=self.instance.pk or 0).first()
            if andere:
                self.add_error("raum", gettext("Der Raum ist zu dieser Zeit bereits gebucht: %(b)s") % {
                    "b": f"{andere.von:%H:%M}–{andere.bis:%H:%M} {andere.zweck}"})
        return d


def _eintraege(von, bis, user):
    """Kalendereinträge (Termine und Sprechtage) im Zeitraum als {datum: [eintrag]}."""
    tage = defaultdict(list)
    for t in Termin.objects.filter(beginn__lte=bis).filter(Q(ende__gte=von) | Q(ende__isnull=True, beginn__gte=von)).select_related("raum"):
        d = max(t.beginn, von)
        while d <= min(t.bis, bis):
            tage[d].append({"art": t.art, "titel": t.lokal_titel, "zeit": t.uhrzeit_von, "bis": t.uhrzeit_bis,
                            "ort": t.raum.name if t.raum else t.ort, "url": reverse("termin", args=[t.pk]), "termin": t,
                            "mehrtaegig": t.ende and t.ende != t.beginn, "frei": t.unterrichtsfrei})
            d += timedelta(days=1)
    planer = rechte.darf_sprechtage_planen(user)
    fenster = Zeitfenster.objects.filter(datum__gte=von, datum__lte=bis).select_related("sprechtag")
    if not planer:
        fenster = fenster.exclude(sprechtag__status=Sprechtag.ENTWURF)
    zusammen = {}
    for z in fenster:
        k = (z.sprechtag_id, z.datum)
        if k not in zusammen:
            zusammen[k] = {"art": "sprechtag", "titel": z.sprechtag.titel, "zeit": z.von, "bis": z.bis, "ort": "",
                           "url": reverse("sprechtag", args=[z.sprechtag_id]), "termin": None}
            tage[z.datum].append(zusammen[k])
        else:
            zusammen[k]["zeit"] = min(zusammen[k]["zeit"], z.von)
            zusammen[k]["bis"] = max(zusammen[k]["bis"], z.bis)
    for liste in tage.values():
        liste.sort(key=lambda e: (e["zeit"] is not None, e["zeit"] or time(0)))
    return tage


@login_required
def kalender(request):
    user = request.user
    if not rechte.darf_kalender_sehen(user):
        raise PermissionDenied
    heute = timezone.localdate()
    try:
        jahr, monat = (int(x) for x in (request.GET.get("monat") or "").split("-"))
        erster = date(jahr, monat, 1)
    except ValueError:
        erster = heute.replace(day=1)
    wochen = calendar.Calendar(firstweekday=0).monthdatescalendar(erster.year, erster.month)
    tage = _eintraege(wochen[0][0], wochen[-1][-1], user)
    art = request.GET.get("art") or ""
    if art:
        tage = {d: [e for e in l if e["art"] == art] for d, l in tage.items()}
    vor = (erster - timedelta(days=1)).replace(day=1)
    nach = (erster + timedelta(days=32)).replace(day=1)
    kommend = _eintraege(heute, heute + timedelta(days=30), user)
    liste, gesehen = [], set()
    for d in sorted(kommend):
        for e in kommend[d]:
            schluessel = (e["url"], e["titel"])
            if e.get("mehrtaegig") and schluessel in gesehen:
                continue
            gesehen.add(schluessel)
            liste.append({"datum": d, **e})
    return render(request, "termine/kalender.html", {
        "titel": _("Schulkalender"), "reiter": _reiter("kalender", user), "erster": erster, "heute": heute,
        "wochen": [[{"datum": d, "eintraege": tage.get(d, []), "fremd": d.month != erster.month} for d in w] for w in wochen],
        "vor": vor, "nach": nach, "arten": Termin.ARTEN + [("sprechtag", _("Sprechtag"))], "art": art, "kommend": liste[:20],
        "darf_bearbeiten": rechte.darf_kalender_bearbeiten(user),
    })


@login_required
def termin(request, pk=None):
    user = request.user
    if not rechte.darf_kalender_sehen(user):
        raise PermissionDenied
    t = get_object_or_404(Termin, pk=pk) if pk else None
    darf = rechte.darf_termin_aendern(user, t) if t else rechte.darf_kalender_bearbeiten(user)
    initial = {}
    if not t and request.GET.get("datum"):
        initial["beginn"] = request.GET["datum"]
    form = TerminForm(instance=t, initial=initial)
    if request.method == "POST":
        if not darf:
            raise PermissionDenied
        if request.POST.get("aktion") == "loeschen" and t:
            t.delete()
            messages.success(request, gettext("Termin gelöscht."))
            return redirect("kalender")
        form = TerminForm(request.POST, instance=t)
        if form.is_valid():
            with transaction.atomic():
                neu = form.save(commit=False)
                if not neu.pk:
                    neu.erstellt_von = user
                neu.save()
                neu.raumbuchungen.all().delete()
                if neu.raum and neu.uhrzeit_von and neu.uhrzeit_bis:
                    Raumbuchung.objects.create(raum=neu.raum, datum=neu.beginn, von=neu.uhrzeit_von, bis=neu.uhrzeit_bis,
                                               zweck=neu.titel[:150], gebucht_von=user, termin=neu)
            messages.success(request, gettext("Termin gespeichert."))
            return redirect(reverse("kalender") + f"?monat={neu.beginn:%Y-%m}")
    return render(request, "termine/termin.html", {
        "titel": t.lokal_titel if t else _("Neuer Termin"), "reiter": _reiter("kalender", user), "t": t, "form": form, "darf": darf,
    })


def _ics_text(s):
    return str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


@login_required
def kalender_ics(request):
    """Termine der aktuellen und kommenden Schuljahre als iCalendar-Datei (z. B. für Outlook)."""
    if not rechte.darf_kalender_sehen(request.user):
        raise PermissionDenied
    sj = Schuljahr.aktuelles()
    ab = sj.beginn if sj else timezone.localdate() - timedelta(days=180)
    zeilen = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//edunex//Schulkalender//DE", "CALSCALE:GREGORIAN",
              "X-WR-CALNAME:" + _ics_text(gettext("Schulkalender"))]
    stempel = timezone.now().strftime("%Y%m%dT%H%M%SZ")
    for t in Termin.objects.filter(Q(beginn__gte=ab) | Q(ende__gte=ab)).select_related("raum"):
        zeilen += ["BEGIN:VEVENT", f"UID:termin-{t.pk}@edunex", f"DTSTAMP:{stempel}", "SUMMARY:" + _ics_text(t.lokal_titel)]
        if t.ganztaegig:
            zeilen += [f"DTSTART;VALUE=DATE:{t.beginn:%Y%m%d}", f"DTEND;VALUE=DATE:{t.bis + timedelta(days=1):%Y%m%d}"]
        else:
            ende = t.uhrzeit_bis or (datetime.combine(t.beginn, t.uhrzeit_von) + timedelta(hours=1)).time()
            zeilen += [f"DTSTART:{t.beginn:%Y%m%d}T{t.uhrzeit_von:%H%M}00", f"DTEND:{t.bis:%Y%m%d}T{ende:%H%M}00"]
        ort = t.raum.name if t.raum else t.ort
        if ort:
            zeilen.append("LOCATION:" + _ics_text(ort))
        if t.beschreibung:
            zeilen.append("DESCRIPTION:" + _ics_text(t.beschreibung))
        zeilen.append("END:VEVENT")
    for z in Zeitfenster.objects.filter(datum__gte=ab).exclude(sprechtag__status=Sprechtag.ENTWURF).select_related("sprechtag"):
        zeilen += ["BEGIN:VEVENT", f"UID:sprechtag-{z.pk}@edunex", f"DTSTAMP:{stempel}", "SUMMARY:" + _ics_text(z.sprechtag.titel),
                   f"DTSTART:{z.datum:%Y%m%d}T{z.von:%H%M}00", f"DTEND:{z.datum:%Y%m%d}T{z.bis:%H%M}00", "END:VEVENT"]
    zeilen.append("END:VCALENDAR")
    antwort = HttpResponse("\r\n".join(zeilen) + "\r\n", content_type="text/calendar; charset=utf-8")
    antwort["Content-Disposition"] = 'attachment; filename="schulkalender.ics"'
    return antwort


# ================================================================= Räume

class BuchungForm(forms.Form):
    raum = forms.ModelChoiceField(label=_("Raum"), queryset=Raum.objects.none())
    datum = forms.DateField(label=_("Datum"), widget=DATUM)
    von = forms.TimeField(label=_("Von"), widget=ZEIT)
    bis = forms.TimeField(label=_("Bis"), widget=ZEIT)
    zweck = forms.CharField(label=_("Zweck"), max_length=150)
    woechentlich_bis = forms.DateField(label=_("Wöchentlich wiederholen bis"), widget=DATUM, required=False,
                                       help_text=_("leer = einmalig"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["raum"].queryset = Raum.objects.filter(aktiv=True, buchbar=True)

    def clean(self):
        d = super().clean()
        if d.get("von") and d.get("bis") and d["bis"] <= d["von"]:
            self.add_error("bis", gettext("Das Ende muss nach dem Beginn liegen."))
        wb = d.get("woechentlich_bis")
        if wb and d.get("datum") and (wb < d["datum"] or wb > d["datum"] + timedelta(days=366)):
            self.add_error("woechentlich_bis", gettext("Bitte ein Enddatum innerhalb eines Jahres nach dem ersten Termin angeben."))
        return d


def serie_buchen(d, user):
    """Bucht einmalig oder wöchentlich; bei einer Überschneidung wird nichts gebucht. Rückgabe: (Buchungen, Konflikte)."""
    tage, tag = [], d["datum"]
    while tag <= (d.get("woechentlich_bis") or d["datum"]):
        tage.append(tag)
        tag += timedelta(days=7)
    serie = str(uuid.uuid4()) if len(tage) > 1 else ""
    buchungen = [Raumbuchung(raum=d["raum"], datum=t, von=d["von"], bis=d["bis"], zweck=d["zweck"], gebucht_von=user, serie=serie)
                 for t in tage]
    konflikte = []
    for b in buchungen:
        andere = b.ueberschneidungen().first()
        if andere:
            konflikte.append(f"{formats.date_format(b.datum, 'SHORT_DATE_FORMAT')}: {andere.von:%H:%M}–{andere.bis:%H:%M} {andere.zweck}")
    if not konflikte:
        with transaction.atomic():
            for b in buchungen:
                b.save()
    return buchungen, konflikte


BEGINN_STUNDE, ENDE_STUNDE = 7, 19


@login_required
def raumplan(request):
    user = request.user
    if not (rechte.darf_raum_buchen(user) or rechte.darf_raeume_verwalten(user)):
        raise PermissionDenied
    try:
        tag = date.fromisoformat(request.GET.get("datum") or "")
    except ValueError:
        tag = timezone.localdate()
    form = BuchungForm(initial={"datum": tag, "raum": request.GET.get("raum")})
    if request.method == "POST":
        aktion = request.POST.get("aktion")
        if aktion == "loeschen":
            b = get_object_or_404(Raumbuchung, pk=request.POST.get("buchung"))
            if not rechte.darf_buchung_loeschen(user, b):
                raise PermissionDenied
            if request.POST.get("serie") and b.serie:
                n = Raumbuchung.objects.filter(serie=b.serie, datum__gte=b.datum).delete()[0]
                messages.success(request, ngettext("%(n)s Buchung gelöscht.", "%(n)s Buchungen gelöscht.", n) % {"n": n})
            else:
                b.delete()
                messages.success(request, gettext("Buchung gelöscht."))
            return redirect(reverse("raumplan") + f"?datum={b.datum:%Y-%m-%d}")
        if not rechte.darf_raum_buchen(user):
            raise PermissionDenied
        form = BuchungForm(request.POST)
        if form.is_valid():
            buchungen, konflikte = serie_buchen(form.cleaned_data, user)
            if konflikte:
                form.add_error(None, gettext("Der Raum ist bereits belegt: %(k)s") % {"k": "; ".join(konflikte[:5])})
            else:
                messages.success(request, ngettext("%(n)s Buchung angelegt.", "%(n)s Buchungen angelegt.", len(buchungen))
                                 % {"n": len(buchungen)})
                return redirect(reverse("raumplan") + f"?datum={form.cleaned_data['datum']:%Y-%m-%d}")
    raeume = list(Raum.objects.filter(aktiv=True))
    buchungen = defaultdict(list)
    spanne = (ENDE_STUNDE - BEGINN_STUNDE) * 60
    for b in Raumbuchung.objects.filter(datum=tag).select_related("gebucht_von", "raum"):
        anfang = max(0, (b.von.hour - BEGINN_STUNDE) * 60 + b.von.minute)
        ende = min(spanne, (b.bis.hour - BEGINN_STUNDE) * 60 + b.bis.minute)
        b.links = round(100 * anfang / spanne, 2)
        b.breite = round(100 * max(ende - anfang, 10) / spanne, 2)
        b.darf_loeschen = rechte.darf_buchung_loeschen(user, b)
        buchungen[b.raum_id].append(b)
    zeilen = [{"raum": r, "buchungen": buchungen.get(r.pk, [])} for r in raeume]
    return render(request, "termine/raumplan.html", {
        "titel": _("Räume"), "reiter": _reiter("raeume", user), "tag": tag, "zeilen": zeilen, "form": form,
        "vortag": tag - timedelta(days=1), "folgetag": tag + timedelta(days=1), "heute": timezone.localdate(),
        "stunden": list(range(BEGINN_STUNDE, ENDE_STUNDE)), "darf_buchen": rechte.darf_raum_buchen(user),
        "darf_verwalten": rechte.darf_raeume_verwalten(user),
        "meine": Raumbuchung.objects.filter(gebucht_von=user, datum__gte=timezone.localdate(), sprechtag__isnull=True,
                                            termin__isnull=True).select_related("raum")[:15],
    })


# ================================================================= Sprechtage

class SprechtagForm(forms.ModelForm):
    class Meta:
        model = Sprechtag
        fields = ["art", "titel", "schuljahr", "jahrgang_von", "jahrgang_bis", "slot_minuten", "puffer_minuten", "max_je_kind",
                  "eltern_buchen", "buchung_ab", "buchung_bis", "hinweis"]
        widgets = {"buchung_ab": DATUMZEIT, "buchung_bis": DATUMZEIT, "hinweis": forms.Textarea(attrs={"rows": 3})}


class ZeitfensterForm(forms.ModelForm):
    class Meta:
        model = Zeitfenster
        fields = ["datum", "von", "bis"]
        widgets = {"datum": DATUM, "von": ZEIT, "bis": ZEIT}


@login_required
def sprechtage(request):
    user = request.user
    _beschaeftigt(user)
    planer = rechte.darf_sprechtage_planen(user)
    form = SprechtagForm(initial={"schuljahr": Schuljahr.aktuelles()})
    if request.method == "POST":
        if not planer:
            raise PermissionDenied
        form = SprechtagForm(request.POST)
        if form.is_valid():
            st = form.save(commit=False)
            st.erstellt_von = user
            st.save()
            messages.success(request, gettext("Sprechtag angelegt. Bitte jetzt die Zeitfenster festlegen."))
            return redirect("sprechtag", pk=st.pk)
    qs = Sprechtag.objects.select_related("schuljahr").prefetch_related("zeitfenster").annotate(
        n_termine=Count("termine", distinct=True), n_lehrkraefte=Count("teilnahmen", filter=Q(teilnahmen__nimmt_teil=True), distinct=True))
    if not planer:
        qs = qs.exclude(status=Sprechtag.ENTWURF)
    p = personal_von(user)
    eigene = {t.sprechtag_id: t for t in Teilnahme.objects.filter(lehrkraft=p)} if p else {}
    liste = list(qs)
    for st in liste:
        st.eigene = eigene.get(st.pk)
    return render(request, "termine/sprechtage.html", {
        "titel": _("Elternsprechtage und LEG"), "reiter": _reiter("sprechtage", user), "liste": liste, "planer": planer,
        "form": form, "fuer_alle": rechte.darf_fuer_alle_buchen(user),
    })


@login_required
def sprechtag(request, pk):
    """Planung: Zeitraster, Teilnehmende, Status. Andere landen in der Übersicht."""
    user = request.user
    st = get_object_or_404(Sprechtag.objects.select_related("schuljahr"), pk=pk)
    if not rechte.darf_sprechtage_planen(user):
        if st.status == Sprechtag.ENTWURF:
            raise Http404
        return redirect("sprechtag_uebersicht", pk=st.pk)
    form = SprechtagForm(instance=st)
    fenster_form = ZeitfensterForm(initial={"datum": st.tage[-1] if st.tage else None})
    if request.method == "POST":
        aktion = request.POST.get("aktion")
        ziel = reverse("sprechtag", args=[st.pk])
        if aktion == "einstellungen":
            form = SprechtagForm(request.POST, instance=st)
            if form.is_valid():
                form.save()
                messages.success(request, gettext("Einstellungen gespeichert."))
                return redirect(ziel)
        elif aktion == "fenster":
            fenster_form = ZeitfensterForm(request.POST)
            if fenster_form.is_valid():
                z = fenster_form.save(commit=False)
                ueber = st.zeitfenster.filter(datum=z.datum, von__lt=z.bis, bis__gt=z.von).exists()
                if ueber:
                    fenster_form.add_error(None, gettext("Das Zeitfenster überschneidet sich mit einem vorhandenen."))
                else:
                    z.sprechtag = st
                    z.save()
                    messages.success(request, gettext("Zeitfenster hinzugefügt."))
                    return redirect(ziel + "#raster")
        elif aktion == "fenster_loeschen":
            z = get_object_or_404(Zeitfenster, pk=request.POST.get("fenster"), sprechtag=st)
            betroffen = st.termine.filter(beginn__date=z.datum).count()
            if betroffen and not request.POST.get("bestaetigt"):
                messages.error(request, gettext("In diesem Zeitfenster gibt es gebuchte Gespräche. Bitte zuerst absagen."))
            else:
                z.delete()
                messages.success(request, gettext("Zeitfenster entfernt."))
            return redirect(ziel + "#raster")
        elif aktion == "lehrkraefte":
            n = S.teilnahmen_ergaenzen(st)
            messages.success(request, ngettext("%(n)s Lehrkraft ergänzt.", "%(n)s Lehrkräfte ergänzt.", n) % {"n": n})
            return redirect(ziel + "#lehrkraefte")
        elif aktion == "lehrkraft_dazu":
            from stammdaten.models import Personalprofil
            lk = get_object_or_404(Personalprofil, pk=request.POST.get("lehrkraft"))
            Teilnahme.objects.get_or_create(sprechtag=st, lehrkraft=lk)
            return redirect(ziel + "#lehrkraefte")
        elif aktion == "teilnahmen":
            raeume = {str(r.pk): r for r in Raum.objects.filter(aktiv=True)}
            for t in st.teilnahmen.all():
                t.raum = raeume.get(request.POST.get(f"raum-{t.pk}") or "")
                t.nimmt_teil = bool(request.POST.get(f"teil-{t.pk}"))
                t.save(update_fields=["raum", "nimmt_teil"])
            messages.success(request, gettext("Teilnahme und Räume gespeichert."))
            return redirect(ziel + "#lehrkraefte")
        elif aktion == "raeume_belegen":
            n, konflikte = S.raeume_buchen(st, user)
            messages.success(request, ngettext("%(n)s Raumbuchung angelegt.", "%(n)s Raumbuchungen angelegt.", n) % {"n": n})
            if konflikte:
                messages.warning(request, gettext("Bereits belegt: %(k)s") % {"k": "; ".join(konflikte[:5])})
            return redirect(ziel + "#lehrkraefte")
        elif aktion == "status":
            neu = request.POST.get("status")
            if neu not in dict(Sprechtag.STATUS):
                raise PermissionDenied
            if neu != Sprechtag.ENTWURF and not st.zeitfenster.exists():
                messages.error(request, gettext("Bitte zuerst mindestens ein Zeitfenster festlegen."))
            else:
                if neu in (Sprechtag.VERFUEGBARKEIT, Sprechtag.BUCHUNG) and not st.teilnahmen.exists():
                    S.teilnahmen_ergaenzen(st)
                st.status = neu
                st.save(update_fields=["status"])
                messages.success(request, gettext("Status: %(s)s") % {"s": st.get_status_display()})
            return redirect(ziel)
        elif aktion == "loeschen":
            if st.termine.exists() and not request.POST.get("bestaetigt"):
                messages.error(request, gettext("Es gibt bereits gebuchte Gespräche."))
                return redirect(ziel)
            st.delete()
            messages.success(request, gettext("Sprechtag gelöscht."))
            return redirect("sprechtage")
        else:
            raise PermissionDenied
    teilnahmen = list(st.teilnahmen.select_related("lehrkraft__person", "raum").annotate(n_termine=Count("termine")))
    slots = len(st.slots())
    for t in teilnahmen:
        t.n_gesperrt = len(t.gesperrt or [])
        t.n_frei = max(slots - t.n_gesperrt - t.n_termine, 0) if t.nimmt_teil else 0
    from stammdaten.models import Personalprofil
    vorhanden = {t.lehrkraft_id for t in teilnahmen}
    fenster = list(st.zeitfenster.all())
    for z in fenster:
        z.anzahl = len(z.slots(st.slot_minuten, st.puffer_minuten))
    return render(request, "termine/sprechtag.html", {
        "titel": st.titel, "reiter": _reiter("sprechtage", user), "st": st, "form": form, "fenster_form": fenster_form,
        "fenster": fenster, "teilnahmen": teilnahmen, "slots": slots, "raeume": Raum.objects.filter(aktiv=True),
        "weitere": Personalprofil.objects.filter(aktiv=True).exclude(pk__in=vorhanden).select_related("person").order_by("person__nachname"),
        "status_folge": Sprechtag.STATUS,
        "n_termine": st.termine.count(),
    })


def _darf_uebersicht(user, st):
    if st.status == Sprechtag.ENTWURF and not rechte.darf_sprechtage_planen(user):
        return False
    return rechte.darf_fuer_alle_buchen(user) or rechte.eigene_teilnahme(user, st) is not None or rechte.darf_sprechtage_planen(user)


@login_required
def uebersicht(request, pk):
    """Alle Gespräche des Sprechtags; Sekretariat und Planung buchen hier für beliebige Lehrkräfte."""
    user = request.user
    st = get_object_or_404(Sprechtag.objects.select_related("schuljahr"), pk=pk)
    if not _darf_uebersicht(user, st):
        raise PermissionDenied
    fuer_alle = rechte.darf_fuer_alle_buchen(user)
    if not fuer_alle:
        t = rechte.eigene_teilnahme(user, st)
        return redirect("sprechzeiten", pk=st.pk, teilnahme=t.pk)
    if request.method == "POST":
        aktion = request.POST.get("aktion")
        if aktion == "absagen":
            g = get_object_or_404(Gespraechstermin, pk=request.POST.get("termin"), sprechtag=st)
            g.delete()
            messages.success(request, gettext("Gespräch abgesagt."))
        return redirect(reverse("sprechtag_uebersicht", args=[st.pk]) + (f"?lk={request.GET.get('lk')}" if request.GET.get("lk") else ""))
    teilnahmen = list(st.teilnahmen.filter(nimmt_teil=True).select_related("lehrkraft__person", "raum"))
    termine = defaultdict(list)
    for g in st.termine.select_related("schueler__person", "eltern", "teilnahme").order_by("beginn"):
        termine[g.teilnahme_id].append(g)
    for t in teilnahmen:
        t.liste = termine.get(t.pk, [])
    ohne = []
    if st.ist_leg:
        mit = set(st.termine.values_list("schueler_id", flat=True))
        ohne = [s for s in Schuelerprofil.objects.filter(pk__in=S.schueler_ids(st) - mit, status="aktiv").select_related("person")
                .order_by("person__nachname")]
        for s in ohne:
            s.klasse = s.stammklasse(st.schuljahr, S.stichtag(st))
    return render(request, "termine/uebersicht.html", {
        "titel": st.titel, "reiter": _reiter("sprechtage", user), "st": st, "teilnahmen": teilnahmen, "ohne": ohne,
        "planer": rechte.darf_sprechtage_planen(user), "n_termine": sum(len(l) for l in termine.values()),
    })


@login_required
def sprechzeiten(request, pk, teilnahme):
    """Verfügbarkeit einer Lehrkraft (Sperren, Einschränken), ihre Gespräche und Buchung für eigene Schüler:innen."""
    user = request.user
    st = get_object_or_404(Sprechtag.objects.select_related("schuljahr"), pk=pk)
    t = get_object_or_404(Teilnahme.objects.select_related("lehrkraft__person", "raum"), pk=teilnahme, sprechtag=st)
    eigen = rechte.darf_teilnahme_bearbeiten(user, t)
    fuer_alle = rechte.darf_fuer_alle_buchen(user)
    if not (eigen or fuer_alle) or (st.status == Sprechtag.ENTWURF and not rechte.darf_sprechtage_planen(user)):
        raise PermissionDenied
    ziel = reverse("sprechzeiten", args=[st.pk, t.pk])
    if request.method == "POST":
        aktion = request.POST.get("aktion")
        if aktion in ("sperren", "einschraenken", "alle_frei", "angaben", "bestaetigen") and not eigen:
            raise PermissionDenied
        if aktion == "sperren":
            gesperrt = set(request.POST.getlist("gesperrt"))
            sichtbar = set(request.POST.getlist("zeit"))
            behalten = set(t.gesperrt or []) - sichtbar           # Zeiten anderer Tage bleiben unverändert
            n = S.sperren_setzen(t, behalten | gesperrt)
            messages.success(request, ngettext("Verfügbarkeit gespeichert: %(n)s Zeit gesperrt.",
                                               "Verfügbarkeit gespeichert: %(n)s Zeiten gesperrt.", n) % {"n": n})
        elif aktion == "einschraenken":
            try:
                tag = date.fromisoformat(request.POST.get("datum"))
                von = time.fromisoformat(request.POST.get("von"))
                bis = time.fromisoformat(request.POST.get("bis"))
            except (TypeError, ValueError):
                messages.error(request, gettext("Bitte Tag, Beginn und Ende angeben."))
                return redirect(ziel)
            S.nur_verfuegbar(t, tag, von, bis)
            messages.success(request, gettext("Verfügbar am %(d)s nur von %(von)s bis %(bis)s.") % {
                "d": formats.date_format(tag, "SHORT_DATE_FORMAT"), "von": von.strftime("%H:%M"), "bis": bis.strftime("%H:%M")})
        elif aktion == "alle_frei":
            S.sperren_setzen(t, [])
            messages.success(request, gettext("Alle Zeiten freigegeben."))
        elif aktion == "angaben":
            t.bemerkung = (request.POST.get("bemerkung") or "")[:200]
            raum = Raum.objects.filter(pk=request.POST.get("raum") or 0, aktiv=True).first()
            if raum is not None or not request.POST.get("raum"):
                t.raum = raum
            t.save(update_fields=["bemerkung", "raum"])
            messages.success(request, gettext("Angaben gespeichert."))
        elif aktion == "bestaetigen":
            t.bestaetigt_am = timezone.now()
            t.save(update_fields=["bestaetigt_am"])
            messages.success(request, gettext("Verfügbarkeit bestätigt."))
        elif aktion == "buchen":
            if not (eigen or fuer_alle) or not user.has_perm("termine.add_gespraechstermin"):
                raise PermissionDenied
            beginn = _zeit_aus_schluessel(request.POST.get("zeit"))
            s = Schuelerprofil.objects.filter(pk=request.POST.get("schueler") or 0).first()
            eltern = Person.objects.filter(pk=request.POST.get("eltern") or 0).first()
            if not (beginn and s):
                messages.error(request, gettext("Bitte Zeit und Schüler:in wählen."))
            else:
                if eltern and not s.beziehungen.filter(person=eltern).exists():
                    eltern = None
                try:
                    S.buchen(t, beginn, s, eltern=eltern, user=user, anliegen=request.POST.get("anliegen", ""))
                except ValidationError as e:
                    messages.error(request, " ".join(e.messages))
                else:
                    messages.success(request, gettext("Gespräch mit %(name)s eingetragen.") % {"name": s.person.anzeigename})
        elif aktion == "absagen":
            if not user.has_perm("termine.delete_gespraechstermin"):
                raise PermissionDenied
            g = get_object_or_404(Gespraechstermin, pk=request.POST.get("termin"), teilnahme=t)
            g.delete()
            messages.success(request, gettext("Gespräch abgesagt."))
        else:
            raise PermissionDenied
        return redirect(ziel)
    zeilen = S.raster(t)
    tage = []
    for z in zeilen:
        if not tage or tage[-1]["datum"] != z["datum"]:
            tage.append({"datum": z["datum"], "zeilen": []})
        tage[-1]["zeilen"].append(z)
    schueler = list(S.schueler_fuer_teilnahme(t))
    for s in schueler:
        s.kontakte = [b.person for b in s.beziehungen.filter(Q(sorgerecht=True) | Q(auskunftsrecht=True)).select_related("person")]
    return render(request, "termine/sprechzeiten.html", {
        "titel": t.lehrkraft.person.anzeigename, "reiter": _reiter("sprechtage", user), "st": st, "t": t, "tage": tage,
        "eigen": eigen, "fuer_alle": fuer_alle, "schueler": schueler, "frei": [z for z in zeilen if z["status"] == "frei"],
        "raeume": Raum.objects.filter(aktiv=True), "n_gebucht": sum(1 for z in zeilen if z["status"] == "gebucht"),
        "n_gesperrt": sum(1 for z in zeilen if z["status"] == "gesperrt"), "n_frei": sum(1 for z in zeilen if z["status"] == "frei"),
        "planer": rechte.darf_sprechtage_planen(user),
    })


# ================================================================= Startseite

def start_hinweise(user):
    if not rechte.darf_kalender_sehen(user):
        return None
    heute = timezone.localdate()
    tage = _eintraege(heute, heute + timedelta(days=14), user)
    kommend, gesehen = [], set()
    for d in sorted(tage):
        for e in tage[d]:
            k = (e["url"], e["titel"])
            if k in gesehen:
                continue
            gesehen.add(k)
            kommend.append({"datum": d, **e})
    aufgaben = []
    p = personal_von(user)
    if p:
        for t in Teilnahme.objects.filter(lehrkraft=p, nimmt_teil=True).select_related("sprechtag").exclude(
                sprechtag__status=Sprechtag.ENTWURF):
            st = t.sprechtag
            tage_st = st.tage
            if tage_st and tage_st[-1] < heute:
                continue
            n = t.termine.count()
            aufgaben.append({"st": st, "t": t, "offen": st.status == Sprechtag.VERFUEGBARKEIT and not t.bestaetigt_am,
                             "termine": n, "datum": tage_st[0] if tage_st else None})
    if not kommend and not aufgaben:
        return None
    return {"kommend": kommend[:8], "aufgaben": aufgaben}
