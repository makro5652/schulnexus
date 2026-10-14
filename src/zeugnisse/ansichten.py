"""Portalansichten: Zeugnisnoten und Kommentare je Unterricht, Zeugnisse je Klasse, Zeugnis, Druck, Konferenzen."""
from collections import Counter
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import formats, timezone, translation
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext, ngettext
from django.views.decorators.http import require_POST

from noten.berechnung import Baum, vorschlagsnote
from noten.models import Note, Unterricht, Zeugnisnote
from portal.rechte import ist_schulleitung, ist_verwaltung, personal_von
from stammdaten.models import Abschnitt, Gruppe, Personalprofil

from . import rechte
from .models import Abzeichnung, Anmerkung, Beschluss, Konferenz, Zeugnis, ZeugnisFachnote
from .noten import (
    BILDUNGSGANG_TEXT, WORTE, fach_sortierung, fachnoten, ganze_note, kernfach_ids, klassen_mitglieder, laufbahn, note_text, stammklasse_im_abschnitt,
    versetzungsvorschlag,
)

DATUM = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


# ---------------------------------------------------------------- Hilfen

def aktueller_abschnitt():
    heute = timezone.localdate()
    a = Abschnitt.objects.filter(beginn__lte=heute, ende__gte=heute).select_related("schuljahr").first()
    return a or Abschnitt.objects.filter(beginn__lte=heute).select_related("schuljahr").order_by("-beginn").first() \
        or Abschnitt.objects.select_related("schuljahr").order_by("beginn").first()


def art_fuer(abschnitt):
    letzte = abschnitt.schuljahr.abschnitte.order_by("-nummer").values_list("nummer", flat=True).first()
    return Zeugnis.JAHR if abschnitt.nummer == letzte and abschnitt.nummer > 1 else Zeugnis.HALBJAHR


def zeugnis_fuer(schueler, abschnitt, klasse=None):
    """Zeugnis anlegen bzw. holen; Klasse, Jahrgang und Bildungsgang werden ergänzt, solange es ein Entwurf ist."""
    z, neu = Zeugnis.objects.get_or_create(schueler=schueler, abschnitt=abschnitt, defaults={
        "art": art_fuer(abschnitt), "zeugnisdatum": abschnitt.ende, "ort": settings.SCHULORT})
    if not z.freigegeben:
        felder = []
        klasse = klasse or stammklasse_im_abschnitt(schueler, abschnitt)
        if klasse and z.klasse_id != klasse.pk:
            z.klasse, felder = klasse, felder + ["klasse"]
        bg, jg = laufbahn(schueler, abschnitt)
        jg = jg or getattr(klasse, "jahrgang", None)
        if bg and z.bildungsgang_id != bg.pk:
            z.bildungsgang, felder = bg, felder + ["bildungsgang"]
        if jg and z.jahrgang != jg:
            z.jahrgang, felder = jg, felder + ["jahrgang"]
        if felder:
            z.save(update_fields=felder)
    return z


def kommentar_status(z, lehrkraft_ids=None):
    """Wer muss abzeichnen, wer hat (aktuell) abgezeichnet."""
    pflicht = set(lehrkraft_ids if lehrkraft_ids is not None else rechte.lehrkraefte_ids(z.schueler, z.abschnitt))
    if z.klasse and z.klasse.leitung_id:
        pflicht.add(z.klasse.leitung_id)
    abz = {a.lehrkraft_id: a for a in z.abzeichnungen.all()}
    aktuell = {pk for pk, a in abz.items() if a.aktuell}
    return {"pflicht": pflicht, "aktuell": aktuell & pflicht, "veraltet": {pk for pk, a in abz.items() if not a.aktuell},
            "offen": pflicht - aktuell, "vollstaendig": bool(pflicht) and pflicht <= aktuell}


def _weiter(request, standard):
    ziel = request.POST.get("weiter") or request.GET.get("weiter")
    if ziel and url_has_allowed_host_and_scheme(ziel, allowed_hosts={request.get_host()}):
        return redirect(ziel)
    return redirect(standard)


def schnitt(zeilen):
    werte = [e["note"] for e in zeilen if e["note"] and not e["punkte"] and not e["vermerk"]]
    if not werte:
        return None
    return (Decimal(sum(werte)) / len(werte)).quantize(Decimal("0.1"), rounding=ROUND_DOWN)


# ---------------------------------------------------------------- Übersicht

@login_required
def uebersicht(request):
    user = request.user
    if not user.has_perm("zeugnisse.view_zeugnis"):
        raise PermissionDenied
    abschnitte = list(Abschnitt.objects.select_related("schuljahr").order_by("-beginn")[:6])
    wahl = request.GET.get("abschnitt", "")
    abschnitt = next((a for a in abschnitte if str(a.pk) == wahl), None) or aktueller_abschnitt()
    if abschnitt is None:
        return render(request, "zeugnisse/uebersicht.html", {"abschnitt": None})
    klassen = [g for g in Gruppe.objects.filter(schuljahr=abschnitt.schuljahr, typ=Gruppe.STAMMKLASSE)
               .select_related("leitung__person").order_by("jahrgang", "name") if rechte.darf_klasse_sehen(user, g)]
    for g in klassen:
        zs = Zeugnis.objects.filter(abschnitt=abschnitt, klasse=g)
        g.zahl = len(klassen_mitglieder(g, abschnitt))
        g.freigegeben = zs.filter(status=Zeugnis.FREIGEGEBEN).count()
        g.konferenz = Konferenz.objects.filter(klasse=g, abschnitt=abschnitt).first()

    personal = personal_von(user)
    unterrichte, abzuzeichnen = [], []
    if personal:
        for u in (Unterricht.objects.filter(abschnitt=abschnitt, lehrkraft=personal)
                  .select_related("fach", "gruppe").order_by("gruppe__name", "fach__reihenfolge")):
            schueler = list(u.schueler())
            noten = Zeugnisnote.objects.filter(unterricht=u, schueler__in=schueler).count()
            unterrichte.append({"u": u, "gesamt": len(schueler), "noten": noten})
        meine_schueler = set()
        for u in Unterricht.objects.filter(abschnitt=abschnitt, lehrkraft=personal):
            meine_schueler |= {s.pk for s in u.schueler()}
        for z in (Zeugnis.objects.filter(abschnitt=abschnitt, schueler_id__in=meine_schueler).exclude(kommentar="")
                  .exclude(status=Zeugnis.FREIGEGEBEN).select_related("schueler__person", "klasse")
                  .prefetch_related("abzeichnungen")):
            eigene = next((a for a in z.abzeichnungen.all() if a.lehrkraft_id == personal.pk), None)
            if eigene is None or not eigene.aktuell:
                z.eigene_veraltet = eigene is not None
                abzuzeichnen.append(z)
        for e in unterrichte:
            e["abzeichnen"] = sum(1 for z in abzuzeichnen if z.schueler_id in {s.pk for s in e["u"].schueler()})
    konferenzen = [k for k in Konferenz.objects.filter(abschnitt=abschnitt).select_related("klasse")
                   if rechte.darf_konferenz_sehen(user, k)]
    return render(request, "zeugnisse/uebersicht.html", {
        "abschnitt": abschnitt, "abschnitte": abschnitte, "klassen": klassen, "unterrichte": unterrichte,
        "abzuzeichnen": abzuzeichnen, "konferenzen": konferenzen,
    })


# ---------------------------------------------------------------- Zeugnisnoten und Kommentare je Unterricht

def _noten_auswahl(skala):
    """Für Zeugnisse nur ganze Noten (Rili 3.5) – bei der Punkteskala alle Stufen."""
    stufen = list(skala.stufen.order_by("reihenfolge"))
    if skala.hoeher_ist_besser:
        return stufen
    return [s for s in stufen if s.wert == s.wert.to_integral_value()]


@login_required
def unterricht(request, pk):
    u = get_object_or_404(Unterricht.objects.select_related("fach", "gruppe", "abschnitt__schuljahr", "skala", "lehrkraft__person"), pk=pk)
    from portal.rechte import darf_unterricht_sehen

    if not darf_unterricht_sehen(request.user, u):
        raise PermissionDenied
    darf_noten = rechte.darf_zeugnisnote_setzen(request.user, u)
    schueler = list(u.schueler())
    bestehend = {z.schueler_id: z for z in Zeugnisnote.objects.filter(unterricht=u).select_related("stufe")}
    zeugnisse = {}
    for s in schueler:
        zeugnisse[s.pk] = zeugnis_fuer(s, u.abschnitt)
    gesperrt = {sid for sid, z in zeugnisse.items() if z.freigegeben}
    baum = Baum(u)
    alle = Note.objects.filter(leistungsnachweis__unterricht=u).select_related("stufe")
    noten_je = {}
    for n in alle:
        noten_je.setdefault(n.schueler_id, []).append(n)
    auswahl = _noten_auswahl(u.skala)

    fehler = {}
    if request.method == "POST" and request.POST.get("aktion") == "noten":
        if not darf_noten:
            raise PermissionDenied
        gespeichert = 0
        with transaction.atomic():
            for s in schueler:
                if s.pk in gesperrt:
                    continue
                wert = request.POST.get(f"note-{s.pk}", "")
                begruendung = request.POST.get(f"begruendung-{s.pk}", "").strip()
                if wert == "":
                    if s.pk in bestehend:
                        bestehend.pop(s.pk).delete()
                    continue
                z = bestehend.get(s.pk) or Zeugnisnote(unterricht=u, schueler=s)
                v = vorschlagsnote(u, s, noten_je.get(s.pk, []), baum)
                z.vorschlag = v.schnitt
                z.begruendung = begruendung
                if wert in ("nb", "befreit"):
                    z.vermerk, z.stufe = wert, None
                else:
                    stufe = next((st for st in auswahl if str(st.pk) == wert), None)
                    if stufe is None:
                        continue
                    z.vermerk, z.stufe = "", stufe
                try:
                    z.full_clean()
                except ValidationError as e:
                    fehler[s.pk] = " ".join(e.messages)
                    continue
                z.save()
                bestehend[s.pk] = z
                gespeichert += 1
        if fehler:
            messages.error(request, ngettext("%(n)s Note nicht gespeichert – bitte die markierte Zeile prüfen.",
                                             "%(n)s Noten nicht gespeichert – bitte die markierten Zeilen prüfen.", len(fehler))
                           % {"n": len(fehler)})
        else:
            messages.success(request, gettext("Zeugnisnoten gespeichert."))
            return redirect("zeugnis_unterricht", pk=u.pk)

    personal = personal_von(request.user)
    lehrkraefte = {}
    zeilen = []
    for s in schueler:
        z = zeugnisse[s.pk]
        v = vorschlagsnote(u, s, noten_je.get(s.pk, []), baum)
        zn = bestehend.get(s.pk)
        if s.pk not in lehrkraefte:
            lehrkraefte[s.pk] = rechte.lehrkraefte_ids(s, u.abschnitt)
        status = kommentar_status(z, lehrkraefte[s.pk])
        eigene = next((a for a in z.abzeichnungen.all() if personal and a.lehrkraft_id == personal.pk), None)
        gewaehlt, vorgeschlagen = "", False
        if request.method == "POST" and s.pk in fehler:
            gewaehlt = request.POST.get(f"note-{s.pk}", "")
        elif zn:
            gewaehlt = zn.vermerk or str(zn.stufe_id)
        elif v.schnitt is not None and auswahl:
            ziel = v.schnitt if u.skala.hoeher_ist_besser else v.schnitt.quantize(Decimal(1), rounding=ROUND_HALF_UP)
            naechste = min(auswahl, key=lambda st: abs(st.wert - ziel))
            gewaehlt, vorgeschlagen = str(naechste.pk), True
        zeilen.append({
            "s": s, "z": z, "zn": zn, "vorschlag": v, "gewaehlt": gewaehlt, "vorgeschlagen": vorgeschlagen, "fehler": fehler.get(s.pk),
            "begruendung": request.POST.get(f"begruendung-{s.pk}", zn.begruendung if zn else "") if request.method == "POST" else (zn.begruendung if zn else ""),
            "gesperrt": s.pk in gesperrt, "status": status, "eigene": eigene,
            "darf_abzeichnen": rechte.darf_abzeichnen(request.user, z),
            "darf_anmerken": rechte.darf_anmerken(request.user, z),
            "darf_erledigen": rechte.darf_kommentar_schreiben(request.user, z),
            "anmerkungen": list(z.anmerkungen.select_related("autor__person")),
        })
    optionen = []
    for st in auswahl:
        note, punkte = ganze_note(st)
        optionen.append((str(st.pk), st.bezeichnung if punkte else f"{st.bezeichnung} – {WORTE[note]}"))
    return render(request, "zeugnisse/unterricht.html", {
        "u": u, "zeilen": zeilen, "optionen": optionen, "darf_noten": darf_noten,
        "gesetzt": sum(1 for z in zeilen if z["zn"]), "personal": personal,
    })


@login_required
@require_POST
def kommentar_aktion(request, pk):
    z = get_object_or_404(Zeugnis.objects.select_related("schueler__person", "klasse", "abschnitt"), pk=pk)
    user = request.user
    aktion = request.POST.get("aktion")
    standard = reverse("zeugnis", args=[z.pk]) + "#kommentar"
    if aktion in ("abzeichnen", "zuruecknehmen"):
        if not rechte.darf_abzeichnen(user, z):
            raise PermissionDenied
        p = personal_von(user)
        if aktion == "abzeichnen":
            Abzeichnung.objects.update_or_create(zeugnis=z, lehrkraft=p, defaults={"am": timezone.now(), "stand": z.kommentar_geaendert})
            messages.success(request, gettext("Kommentar für %(name)s abgezeichnet.") % {"name": z.schueler.person.anzeigename})
        else:
            Abzeichnung.objects.filter(zeugnis=z, lehrkraft=p).delete()
    elif aktion == "anmerkung":
        if not rechte.darf_anmerken(user, z):
            raise PermissionDenied
        text = request.POST.get("text", "").strip()
        if text:
            Anmerkung.objects.create(zeugnis=z, autor=user, text=text[:2000])
            messages.success(request, gettext("Anmerkung gespeichert."))
    elif aktion == "erledigt":
        a = get_object_or_404(Anmerkung, pk=request.POST.get("anmerkung"), zeugnis=z)
        if not (rechte.darf_kommentar_schreiben(user, z) or a.autor_id == user.pk):
            raise PermissionDenied
        a.erledigt = not a.erledigt
        a.save(update_fields=["erledigt"])
    else:
        raise Http404
    return _weiter(request, standard)


# ---------------------------------------------------------------- Zeugnisse einer Klasse

def _klassen_zeilen(klasse, abschnitt):
    zeilen = []
    for s in klassen_mitglieder(klasse, abschnitt):
        z = zeugnis_fuer(s, abschnitt, klasse)
        fn = fachnoten(s, abschnitt, z.art)
        bg, jg = (z.bildungsgang, z.jahrgang)
        ergebnis, hinweis = versetzungsvorschlag(s, bg, jg, fn)
        zeilen.append({"s": s, "z": z, "fachnoten": fn, "fehlen": sum(1 for e in fn if e["fehlt"]),
                       "schnitt": schnitt(fn), "ergebnis": ergebnis, "hinweis": hinweis,
                       "kommentar": kommentar_status(z) if z.kommentar else None,
                       "anmerkungen_offen": z.anmerkungen.filter(erledigt=False).count()})
    return zeilen


@login_required
def klasse(request, gruppe, abschnitt):
    klasse = get_object_or_404(Gruppe.objects.select_related("leitung__person", "schuljahr"), pk=gruppe)
    abschnitt = get_object_or_404(Abschnitt.objects.select_related("schuljahr"), pk=abschnitt, schuljahr=klasse.schuljahr)
    user = request.user
    if not rechte.darf_klasse_sehen(user, klasse):
        raise PermissionDenied
    if request.method == "POST":
        aktion = request.POST.get("aktion")
        if aktion == "konferenz":
            if not rechte.darf_konferenz_leiten(user, klasse):
                raise PermissionDenied
            k = konferenz_anlegen(klasse, abschnitt, user)
            return redirect("konferenz", pk=k.pk)
        if aktion == "freigeben":
            n = 0
            for zeile in _klassen_zeilen(klasse, abschnitt):
                z = zeile["z"]
                if not z.freigegeben and rechte.darf_freigeben(user, z) and not freigabe_hindernisse(z, zeile["fachnoten"]):
                    freigeben(z, user, zeile["fachnoten"])
                    n += 1
            messages.success(request, ngettext("%(n)s Zeugnis freigegeben.", "%(n)s Zeugnisse freigegeben.", n) % {"n": n})
            return redirect("zeugnis_klasse", gruppe=klasse.pk, abschnitt=abschnitt.pk)
        raise Http404
    zeilen = _klassen_zeilen(klasse, abschnitt)
    from elternkontakt.ansichten import zeugnisempfang_status
    from elternkontakt.rechte import darf_zeugnisempfang

    empfang = zeugnisempfang_status(klasse, abschnitt)
    for zeile in zeilen:
        zeile["empfang"] = empfang.get(zeile["z"].pk)
    return render(request, "zeugnisse/klasse.html", {
        "empfang_offen": sum(1 for z in zeilen if z["z"].freigegeben and not z["empfang"]),
        "darf_empfang": darf_zeugnisempfang(user, klasse),
        "klasse": klasse, "abschnitt": abschnitt, "zeilen": zeilen,
        "abschnitte": klasse.schuljahr.abschnitte.order_by("nummer"),
        "konferenz": Konferenz.objects.filter(klasse=klasse, abschnitt=abschnitt).first(),
        "darf_konferenz": rechte.darf_konferenz_leiten(user, klasse),
        "darf_freigeben": any(rechte.darf_freigeben(user, z["z"]) for z in zeilen),
        "freigegeben": sum(1 for z in zeilen if z["z"].freigegeben),
    })


# ---------------------------------------------------------------- Einzelnes Zeugnis

class ZeugnisForm(forms.ModelForm):
    class Meta:
        model = Zeugnis
        fields = ["bemerkungen", "versetzung", "zeugnisdatum", "ort", "fehltage_entschuldigt", "fehltage_unentschuldigt",
                  "kommentar_drucken", "abgangsvermerk"]
        widgets = {"bemerkungen": forms.Textarea(attrs={"rows": 3}), "zeugnisdatum": DATUM,
                   "abgangsvermerk": forms.Textarea(attrs={"rows": 2})}


def freigabe_hindernisse(z, zeilen=None):
    zeilen = zeilen if zeilen is not None else fachnoten(z.schueler, z.abschnitt, z.art)
    gruende = []
    fehlen = [e["fachname"] for e in zeilen if e["fehlt"]]
    if fehlen:
        gruende.append(gettext("Zeugnisnoten fehlen: %(faecher)s") % {"faecher": ", ".join(fehlen)})
    if not zeilen:
        gruende.append(gettext("Keine Fächer gefunden."))
    if not z.zeugnisdatum:
        gruende.append(gettext("Das Datum des Zeugnisses fehlt."))
    return gruende


def freigabe_hinweise(z):
    h = []
    if z.kommentar:
        st = kommentar_status(z)
        if st["offen"]:
            h.append(ngettext("Der Kommentar ist von %(n)s Lehrkraft noch nicht abgezeichnet.",
                              "Der Kommentar ist von %(n)s Lehrkräften noch nicht abgezeichnet.", len(st["offen"])) % {"n": len(st["offen"])})
        if z.anmerkungen.filter(erledigt=False).exists():
            h.append(gettext("Es gibt offene Anmerkungen zum Kommentar."))
    if z.art == Zeugnis.JAHR and not z.versetzung and (z.jahrgang or 0) <= 10:
        h.append(gettext("Kein Versetzungsvermerk eingetragen."))
    return h


@transaction.atomic
def freigeben(z, user, zeilen=None):
    zeilen = zeilen if zeilen is not None else fachnoten(z.schueler, z.abschnitt, z.art)
    z.fachnoten.all().delete()
    ZeugnisFachnote.objects.bulk_create([
        ZeugnisFachnote(zeugnis=z, fach=e["fach"], fachname=e["fach"].name, note=e["note"], punkte=e["punkte"],
                        vermerk=e["vermerk"], hinweis=e["abschnitt"].name if e["hinweis"] else "",
                        spalte=e["fach"].zeugnisspalte, reihenfolge=i) for i, e in enumerate(zeilen)])
    z.status, z.freigegeben_am, z.freigegeben_von = Zeugnis.FREIGEGEBEN, timezone.now(), user
    z.save()


@login_required
def zeugnis(request, pk):
    z = get_object_or_404(Zeugnis.objects.select_related("schueler__person", "abschnitt__schuljahr", "klasse__leitung__person",
                                                         "bildungsgang", "kommentar_von__person", "freigegeben_von"), pk=pk)
    user = request.user
    if not rechte.darf_zeugnis_sehen(user, z):
        raise PermissionDenied
    if not z.freigegeben:
        z = zeugnis_fuer(z.schueler, z.abschnitt, z.klasse)
    darf = {"bearbeiten": rechte.darf_zeugnis_bearbeiten(user, z), "kommentar": rechte.darf_kommentar_schreiben(user, z),
            "abzeichnen": rechte.darf_abzeichnen(user, z), "anmerken": rechte.darf_anmerken(user, z),
            "freigeben": rechte.darf_freigeben(user, z)}
    form = ZeugnisForm(instance=z)
    if request.method == "POST":
        aktion = request.POST.get("aktion")
        if aktion == "speichern":
            if not darf["bearbeiten"]:
                raise PermissionDenied
            form = ZeugnisForm(request.POST, instance=z)
            if form.is_valid():
                z = form.save(commit=False)
                ger = {}
                for schluessel, _name in Zeugnis.GER_ZEILEN:
                    werte = {f: request.POST.get(f"ger-{schluessel}-{f}", "").strip()[:30] for f in ("sprache", "von", "bis", "niveau")}
                    if any(werte.values()):
                        ger[schluessel] = werte
                z.ger = ger
                z.save()
                messages.success(request, gettext("Zeugnis gespeichert."))
                return redirect("zeugnis", pk=z.pk)
        elif aktion == "kommentar":
            if not darf["kommentar"]:
                raise PermissionDenied
            if z.kommentar_setzen(request.POST.get("kommentar", ""), user):
                z.save()
                messages.success(request, gettext("Kommentar gespeichert. Bisherige Abzeichnungen müssen erneuert werden."))
            return redirect(reverse("zeugnis", args=[z.pk]) + "#kommentar")
        elif aktion == "freigeben":
            if not darf["freigeben"]:
                raise PermissionDenied
            gruende = freigabe_hindernisse(z)
            if gruende:
                messages.error(request, " ".join(gruende))
            else:
                freigeben(z, user)
                messages.success(request, gettext("Zeugnis freigegeben."))
            return redirect("zeugnis", pk=z.pk)
        elif aktion == "aufheben":
            if not (z.freigegeben and user.has_perm("zeugnisse.freigeben_zeugnis")
                    and (ist_schulleitung(user) or rechte.ist_stufe(user, z.jahrgang))):
                raise PermissionDenied
            z.status, z.freigegeben_am, z.freigegeben_von = Zeugnis.ENTWURF, None, None
            z.save()
            messages.success(request, gettext("Freigabe aufgehoben – das Zeugnis ist wieder ein Entwurf."))
            return redirect("zeugnis", pk=z.pk)
        else:
            raise Http404
    zeilen = fachnoten(z.schueler, z.abschnitt, z.art)
    ergebnis, hinweis = versetzungsvorschlag(z.schueler, z.bildungsgang, z.jahrgang, zeilen)
    kern = kernfach_ids(z.schueler, z.bildungsgang, zeilen) or set()
    lk_ids = rechte.lehrkraefte_ids(z.schueler, z.abschnitt)
    st = kommentar_status(z, lk_ids)
    abz = {a.lehrkraft_id: a for a in z.abzeichnungen.select_related("lehrkraft__person")}
    unterzeichner = [{"p": p, "a": abz.get(p.pk), "kl": z.klasse and z.klasse.leitung_id == p.pk}
                     for p in Personalprofil.objects.filter(pk__in=st["pflicht"]).select_related("person").order_by("person__nachname")]
    geschwister = []
    if z.klasse:
        mitglieder = [s.pk for s in klassen_mitglieder(z.klasse, z.abschnitt)]
        if z.schueler_id in mitglieder:
            i = mitglieder.index(z.schueler_id)
            ids = {"zurueck": mitglieder[i - 1] if i > 0 else None, "weiter": mitglieder[i + 1] if i + 1 < len(mitglieder) else None}
            for k, sid in ids.items():
                if sid:
                    andere = Zeugnis.objects.filter(schueler_id=sid, abschnitt=z.abschnitt).first()
                    if andere:
                        geschwister.append((k, andere))
    personal = personal_von(user)
    return render(request, "zeugnisse/zeugnis.html", {
        "z": z, "form": form, "darf": darf, "zeilen": zeilen, "kern": kern, "ergebnis": ergebnis, "vhinweis": hinweis,
        "schnitt": schnitt(zeilen), "status": st, "unterzeichner": unterzeichner,
        "eigene": abz.get(personal.pk) if personal else None, "anmerkungen": z.anmerkungen.select_related("autor__person"),
        "hindernisse": freigabe_hindernisse(z, zeilen) if not z.freigegeben else [],
        "hinweise": freigabe_hinweise(z) if not z.freigegeben else [],
        "konferenz": Konferenz.objects.filter(klasse=z.klasse, abschnitt=z.abschnitt).first() if z.klasse else None,
        "nachbarn": dict(geschwister), "zeichen": len(z.kommentar),
    })


# ---------------------------------------------------------------- Druck

def _geschlecht_text(person):
    return {"w": gettext("sie"), "m": gettext("er")}.get(person.geschlecht, gettext("sie/er"))


def druckdaten(z):
    if z.freigegeben:
        zeilen = []
        for f in z.fachnoten.select_related("fach"):
            zeilen.append({"fachname": f.fach.lokal_name, "text": note_text(f.note, f.punkte, f.vermerk),
                           "hinweis": next((a.lokal_name for a in z.abschnitt.schuljahr.abschnitte.all() if a.name == f.hinweis), f.hinweis),
                           "spalte": f.spalte})
    else:
        zeilen = [{"fachname": e["fachname"], "text": e["text"] or "", "hinweis": e["hinweis"], "spalte": e["fach"].zeugnisspalte}
                  for e in fachnoten(z.schueler, z.abschnitt, z.art)]
    links = [e for e in zeilen if e["spalte"] == 1]
    rechts = [e for e in zeilen if e["spalte"] != 1]
    paare = [(links[i] if i < len(links) else None, rechts[i] if i < len(rechts) else None) for i in range(max(len(links), len(rechts)))]
    p = z.schueler.person
    vermerk = ""
    if z.art in (Zeugnis.JAHR, Zeugnis.ABGANG) and z.versetzung:
        pron = _geschlecht_text(p)
        vermerk = {
            "versetzt": gettext("Versetzt in die Jahrgangsstufe %(jg)s.") % {"jg": (z.jahrgang or 0) + 1} if z.jahrgang else gettext("Versetzt."),
            "nicht_versetzt": gettext("Nicht versetzt."),
            "qp_ja": gettext("Die Berechtigung zum Übergang in die Qualifikationsphase hat %(pron)s erhalten. Die Berechtigung zum "
                             "Übergang in die Qualifikationsphase schließt den Mittleren Schulabschluss ein.") % {"pron": pron},
            "qp_nein": gettext("Die Berechtigung zum Übergang in die Qualifikationsphase hat %(pron)s nicht erhalten.") % {"pron": pron},
            "wiederholung": gettext("Die Jahrgangsstufe wird freiwillig wiederholt."),
        }.get(z.versetzung, "")
    abgang = ""
    if z.art == Zeugnis.ABGANG:
        s = z.schueler
        if s.austrittsdatum:
            abgang = gettext("%(name)s verlässt die Schule am %(datum)s.") % {
                "name": f"{p.rufname or p.vorname} {p.nachname}", "datum": formats.date_format(s.austrittsdatum, "SHORT_DATE_FORMAT")}
        else:
            abgang = gettext("%(name)s verlässt die Schule.") % {"name": f"{p.rufname or p.vorname} {p.nachname}"}
        if z.abgangsvermerk:
            abgang += " " + z.abgangsvermerk
    bg = z.bildungsgang
    return {
        "z": z, "p": p, "paare": paare, "vermerk": vermerk, "abgang": abgang,
        "bildungsgang": BILDUNGSGANG_TEXT.get(getattr(bg, "kuerzel", ""), getattr(bg, "lokal_name", "")) if bg else "",
        "kommentar": z.kommentar if z.kommentar and z.kommentar_drucken else "",
        "entwurf": not z.freigegeben, "fehlzeiten": settings.ZEUGNIS_FEHLZEITEN,
    }


def _druck(request, zeugnisse, titel):
    sprache = "en" if request.GET.get("sprache") == "en" else "de"
    with translation.override(sprache):
        seiten = [druckdaten(z) for z in zeugnisse]
        return render(request, "zeugnisse/druck.html", {
            "seiten": seiten, "titel": titel, "sprache": sprache, "SCHULNAME": settings.SCHULNAME,
            "notenstufen": [WORTE[i] for i in range(1, 7)],
        })


@login_required
def druck(request, pk):
    z = get_object_or_404(Zeugnis.objects.select_related("schueler__person", "abschnitt__schuljahr", "klasse", "bildungsgang"), pk=pk)
    if not rechte.darf_zeugnis_sehen(request.user, z) or not (ist_verwaltung(request.user) or rechte.darf_zeugnis_bearbeiten(request.user, z)
                                                              or rechte.ist_klassenleitung(request.user, z.klasse) or rechte.ist_stufe(request.user, z.jahrgang)):
        raise PermissionDenied
    return _druck(request, [z], z.schueler.person.anzeigename)


@login_required
def klasse_druck(request, gruppe, abschnitt):
    klasse = get_object_or_404(Gruppe, pk=gruppe)
    abschnitt = get_object_or_404(Abschnitt.objects.select_related("schuljahr"), pk=abschnitt)
    if not rechte.darf_klasse_sehen(request.user, klasse):
        raise PermissionDenied
    zeugnisse = [zeugnis_fuer(s, abschnitt, klasse) for s in klassen_mitglieder(klasse, abschnitt)]
    if request.GET.get("nur") == "freigegeben":
        zeugnisse = [z for z in zeugnisse if z.freigegeben]
    return _druck(request, zeugnisse, gettext("Klasse %(k)s") % {"k": klasse.name})


# ---------------------------------------------------------------- Konferenzen

def konferenz_anlegen(klasse, abschnitt, user):
    art = Konferenz.VERSETZUNG if art_fuer(abschnitt) == Zeugnis.JAHR else Konferenz.HALBJAHR
    k, neu = Konferenz.objects.get_or_create(klasse=klasse, abschnitt=abschnitt, defaults={"art": art, "erstellt_von": user})
    if neu:
        ids = set()
        for s in klassen_mitglieder(klasse, abschnitt):
            ids |= rechte.lehrkraefte_ids(s, abschnitt)
        if klasse.leitung_id:
            ids.add(klasse.leitung_id)
        k.teilnehmende.set(ids)
        if klasse.leitung_id:
            k.protokoll = klasse.leitung
            k.save(update_fields=["protokoll"])
    return k


class KonferenzForm(forms.ModelForm):
    class Meta:
        model = Konferenz
        fields = ["art", "datum", "beginn", "ende", "ort", "vorsitz", "protokoll", "teilnehmende", "notizen"]
        widgets = {"datum": DATUM, "beginn": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
                   "ende": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
                   "notizen": forms.Textarea(attrs={"rows": 4}), "teilnehmende": forms.CheckboxSelectMultiple}

    def __init__(self, *args, kandidaten=None, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Personalprofil.objects.filter(aktiv=True).select_related("person").order_by("person__nachname")
        for f in ("vorsitz", "protokoll"):
            self.fields[f].queryset = qs
            self.fields[f].label_from_instance = lambda p: f"{p.person.anzeigename}{f' ({p.kuerzel})' if p.kuerzel else ''}"
        ids = set(kandidaten or []) | set(self.instance.teilnehmende.values_list("pk", flat=True) if self.instance.pk else [])
        self.fields["teilnehmende"].queryset = qs.filter(pk__in=ids)
        self.fields["teilnehmende"].label_from_instance = lambda p: f"{p.person.anzeigename}{f' ({p.kuerzel})' if p.kuerzel else ''}"


def _konferenz_zeilen(k):
    art = Zeugnis.JAHR if k.art == Konferenz.VERSETZUNG else art_fuer(k.abschnitt)
    zeilen, faecher = [], {}
    beschluesse = {b.schueler_id: b for b in k.beschluesse.all()}
    for s in klassen_mitglieder(k.klasse, k.abschnitt):
        z = zeugnis_fuer(s, k.abschnitt, k.klasse)
        fn = fachnoten(s, k.abschnitt, art)
        ergebnis, hinweis = versetzungsvorschlag(s, z.bildungsgang, z.jahrgang, fn)
        kern = kernfach_ids(s, z.bildungsgang, fn) or set()
        for e in fn:
            faecher[e["fach"].pk] = e["fach"]
        b = beschluesse.get(s.pk) or Beschluss(konferenz=k, schueler=s)
        if k.art == Konferenz.HALBJAHR:
            vorschlag_entscheidung = "keine"
        elif ergebnis is None:
            vorschlag_entscheidung = ""
        elif (z.jahrgang or 0) >= 10:
            vorschlag_entscheidung = ""
        elif ergebnis.ergebnis == "nicht_versetzt" and ergebnis.nachpruefung:
            vorschlag_entscheidung = "nachpruefung"
        else:
            vorschlag_entscheidung = ergebnis.ergebnis
        defizite = ", ".join(f"{name} ({WORTE[note]})" for name, note in (ergebnis.defizite if ergebnis else []))
        zeilen.append({"s": s, "z": z, "fn": {e["fach"].pk: e for e in fn}, "kern": kern, "ergebnis": ergebnis, "hinweis": hinweis,
                       "schnitt": schnitt(fn), "b": b, "vorschlag_entscheidung": vorschlag_entscheidung, "defizite": defizite,
                       "stimmberechtigt": len(rechte.lehrkraefte_ids(s, k.abschnitt)),
                       "anzahl5": sum(1 for e in fn if e["note"] == 5 and not e["punkte"]),
                       "anzahl6": sum(1 for e in fn if e["note"] == 6 and not e["punkte"])})
    spalten = sorted(faecher.values(), key=fach_sortierung)
    for zl in zeilen:
        zl["zellen"] = [{"e": zl["fn"].get(f.pk), "kern": f.pk in zl["kern"]} for f in spalten]
    return zeilen, spalten


def _beschluesse_speichern(request, k, zeilen):
    with transaction.atomic():
        for zl in zeilen:
            s, b = zl["s"], zl["b"]
            p = f"b-{s.pk}-"
            entscheidung = request.POST.get(p + "entscheidung", "")
            if entscheidung not in dict(Beschluss.ENTSCHEIDUNGEN):
                entscheidung = ""
            b.entscheidung = entscheidung
            b.ausgleich = request.POST.get(p + "ausgleich", "").strip()[:200]
            b.gefaehrdung = request.POST.get(p + "gefaehrdung", "").strip()[:200]
            b.begruendung = request.POST.get(p + "begruendung", "").strip()
            b.nicht_mitwirkend = request.POST.get(p + "nicht_mitwirkend", "").strip()[:200]
            for f in ("stimmen_ja", "stimmen_nein"):
                wert = request.POST.get(p + f, "").strip()
                setattr(b, f, int(wert) if wert.isdigit() else None)
            datum = request.POST.get(p + "gefaehrdung_mitgeteilt", "").strip()
            from django.utils.dateparse import parse_date

            b.gefaehrdung_mitgeteilt = parse_date(datum) if datum else None
            b.vorschlag = (zl["ergebnis"].kurztext() if zl["ergebnis"] else zl["hinweis"])[:250]
            b.save()


def abschluss_hindernisse(k, zeilen):
    gruende = []
    for zl in zeilen:
        b, name = zl["b"], zl["s"].person.anzeigename
        if k.art == Konferenz.VERSETZUNG and not b.entscheidung:
            gruende.append(gettext("%(name)s: keine Entscheidung.") % {"name": name})
        if b.entscheidung in ("nicht_versetzt", "nachpruefung", "qp_nein") and not b.begruendung.strip():
            gruende.append(gettext("%(name)s: Die Nichtversetzung bedarf einer Begründung im Protokoll.") % {"name": name})
        if b.entscheidung == "versetzt_ausgleich" and not b.ausgleich.strip():
            gruende.append(gettext("%(name)s: Bitte den Notenausgleich im Protokoll vermerken.") % {"name": name})
    if not k.datum:
        gruende.append(gettext("Das Datum der Konferenz fehlt."))
    return gruende


@login_required
def konferenz(request, pk):
    k = get_object_or_404(Konferenz.objects.select_related("klasse__leitung__person", "abschnitt__schuljahr", "vorsitz__person",
                                                           "protokoll__person"), pk=pk)
    user = request.user
    if not rechte.darf_konferenz_sehen(user, k):
        raise PermissionDenied
    darf_leiten = rechte.darf_konferenz_leiten(user, k.klasse) and not k.abgeschlossen
    zeilen, spalten = _konferenz_zeilen(k)
    kandidaten = set()
    for zl in zeilen:
        kandidaten |= rechte.lehrkraefte_ids(zl["s"], k.abschnitt)
    form = KonferenzForm(instance=k, kandidaten=kandidaten | ({k.klasse.leitung_id} if k.klasse.leitung_id else set()))
    hindernisse = []
    if request.method == "POST":
        aktion = request.POST.get("aktion")
        if aktion == "wiedereroeffnen":
            if not (rechte.darf_konferenz_leiten(user, k.klasse) and k.abgeschlossen):
                raise PermissionDenied
            k.status = Konferenz.DURCHGEFUEHRT
            k.save(update_fields=["status"])
            return redirect("konferenz", pk=k.pk)
        if not darf_leiten:
            raise PermissionDenied
        form = KonferenzForm(request.POST, instance=k, kandidaten=form.fields["teilnehmende"].queryset.values_list("pk", flat=True))
        if form.is_valid():
            k = form.save(commit=False)
            if k.status == Konferenz.GEPLANT and aktion in ("speichern", "abschliessen") and k.datum and k.datum <= timezone.localdate():
                k.status = Konferenz.DURCHGEFUEHRT
            k.save()
            form.save_m2m()
            _beschluesse_speichern(request, k, zeilen)
            if aktion == "abschliessen":
                zeilen, spalten = _konferenz_zeilen(k)
                hindernisse = abschluss_hindernisse(k, zeilen)
                if not hindernisse:
                    with transaction.atomic():
                        k.status = Konferenz.ABGESCHLOSSEN
                        k.save(update_fields=["status"])
                        if k.art == Konferenz.VERSETZUNG:
                            for zl in zeilen:
                                z = zl["z"]
                                vermerk = Beschluss.ZEUGNISVERMERK.get(zl["b"].entscheidung, "")
                                if not z.freigegeben and vermerk:
                                    z.versetzung = vermerk
                                    z.save(update_fields=["versetzung"])
                    messages.success(request, gettext("Konferenz abgeschlossen. Die Beschlüsse sind in die Zeugnisse übernommen."))
                    return redirect("konferenz", pk=k.pk)
            else:
                messages.success(request, gettext("Konferenz gespeichert."))
                return redirect("konferenz", pk=k.pk)
    return render(request, "zeugnisse/konferenz.html", {
        "k": k, "form": form, "zeilen": zeilen, "spalten": spalten, "darf_leiten": darf_leiten,
        "entscheidungen": Beschluss.ENTSCHEIDUNGEN, "hindernisse": hindernisse,
        "darf_wiedereroeffnen": k.abgeschlossen and rechte.darf_konferenz_leiten(user, k.klasse),
        "gefaehrdet": sum(1 for zl in zeilen if zl["ergebnis"] and zl["ergebnis"].gefaehrdet),
        "statistik": Counter(zl["b"].entscheidung or zl["vorschlag_entscheidung"] for zl in zeilen),
    })


@login_required
def konferenz_protokoll(request, pk):
    k = get_object_or_404(Konferenz.objects.select_related("klasse__leitung__person", "abschnitt__schuljahr", "vorsitz__person",
                                                           "protokoll__person"), pk=pk)
    if not rechte.darf_konferenz_sehen(request.user, k):
        raise PermissionDenied
    zeilen, spalten = _konferenz_zeilen(k)
    return render(request, "zeugnisse/protokoll.html", {
        "k": k, "zeilen": zeilen, "spalten": spalten, "SCHULNAME": settings.SCHULNAME,
        "teilnehmende": k.teilnehmende.select_related("person").order_by("person__nachname"),
    })


@login_required
def gefaehrdung_druck(request, pk):
    k = get_object_or_404(Konferenz.objects.select_related("klasse__leitung__person", "abschnitt__schuljahr"), pk=pk)
    if not rechte.darf_konferenz_sehen(request.user, k):
        raise PermissionDenied
    zeilen, _sp = _konferenz_zeilen(k)
    briefe = [zl for zl in zeilen if (zl["b"].gefaehrdung or zl["defizite"])]
    sprache = "en" if request.GET.get("sprache") == "en" else "de"
    with translation.override(sprache):
        return render(request, "zeugnisse/gefaehrdung.html", {
            "k": k, "briefe": briefe, "SCHULNAME": settings.SCHULNAME, "SCHULORT": settings.SCHULORT,
            "heute": timezone.localdate(), "sprache": sprache,
        })


# ---------------------------------------------------------------- Startseite

def start_hinweise(user):
    """Offene Zeugnisaufgaben der angemeldeten Person – oder None."""
    if not user.has_perm("zeugnisse.view_zeugnis"):
        return None
    personal = personal_von(user)
    abschnitt = aktueller_abschnitt()
    if not personal or abschnitt is None:
        return None
    meine_schueler = set()
    for u in Unterricht.objects.filter(abschnitt=abschnitt, lehrkraft=personal).select_related("gruppe", "abschnitt"):
        meine_schueler |= {s.pk for s in u.schueler()}
    abzeichnen = 0
    for z in (Zeugnis.objects.filter(abschnitt=abschnitt, schueler_id__in=meine_schueler).exclude(kommentar="")
              .exclude(status=Zeugnis.FREIGEGEBEN).prefetch_related("abzeichnungen")):
        eigene = next((a for a in z.abzeichnungen.all() if a.lehrkraft_id == personal.pk), None)
        if eigene is None or not eigene.aktuell:
            abzeichnen += 1
    klassen = list(Gruppe.objects.filter(leitung=personal, schuljahr=abschnitt.schuljahr, typ=Gruppe.STAMMKLASSE))
    ohne_kommentar = 0
    for g in klassen:
        mitglieder = [s.pk for s in klassen_mitglieder(g, abschnitt)]
        mit = Zeugnis.objects.filter(abschnitt=abschnitt, schueler_id__in=mitglieder).exclude(kommentar="").count()
        ohne_kommentar += len(mitglieder) - mit
    if not (abzeichnen or ohne_kommentar):
        return None
    return {"abschnitt": abschnitt, "abzeichnen": abzeichnen, "ohne_kommentar": ohne_kommentar, "klassen": klassen}

