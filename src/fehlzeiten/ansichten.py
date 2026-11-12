"""
Fehlzeiten nach Klasse (ab 0.7.1) – die Arbeitsseite für Klassenleitungen, Lehrkräfte und Sekretariat.

1. Klasse wählen (Kacheln nach Jahrgang, mit Zahl der offenen Entschuldigungen) und ein Datum.
2. Die Klasse alphabetisch: je Schüler:in ganztägig, Stunden oder Verspätung mit wenigen Klicks erfassen; was an dem
   Tag schon eingetragen ist, steht in der Zeile.
3. Offene Entschuldigungen der Klasse ankreuzen und als entschuldigt bzw. unentschuldigt markieren.
4. Übersicht des Halbjahres je Schüler:in und alle Einträge der Klasse.

Ohne Klasse zeigt `?offen=1` alle offenen Entschuldigungen, die man sehen darf, nach Klasse und Name geordnet.
Die bisherige Liste der Verwaltungsoberfläche bleibt daneben bestehen.
"""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.translation import gettext, ngettext

from noten.models import Unterricht
from portal.rechte import ist_it, ist_verwaltung, koordinierte_jahrgaenge, personal_von
from stammdaten.models import Abschnitt, Gruppe, Mitgliedschaft, Schuljahr

from .models import Fehlzeit, Stunde

SORTIERUNG = ("schueler__person__nachname", "schueler__person__vorname")


# ---------------------------------------------------------------- Rechte und Auswahl

def darf_sehen(user):
    return user.has_perm("fehlzeiten.view_fehlzeit")


def alle_klassen(user):
    return ist_verwaltung(user) or ist_it(user)


def klassen_fuer(user, sj):
    """Stammklassen des Schuljahres, mit denen die Person arbeitet – sortiert nach Jahrgang und Name.

    Verwaltung, Leitung und IT: alle; Stufenkoordination: die Klassen ihrer Jahrgänge; Lehrkräfte: Klassen, die sie
    leiten oder (als ganze Klasse) unterrichten.
    """
    qs = Gruppe.objects.filter(schuljahr=sj, typ=Gruppe.STAMMKLASSE)
    if not alle_klassen(user):
        personal = personal_von(user)
        bedingung = Q(jahrgang__in=koordinierte_jahrgaenge(user))
        if personal:
            unterrichtet = Unterricht.objects.filter(lehrkraft=personal, abschnitt__schuljahr=sj).values("gruppe")
            bedingung |= Q(leitung=personal) | Q(leitung2=personal) | Q(pk__in=unterrichtet)
        qs = qs.filter(bedingung)
    return qs.select_related("leitung__person").order_by("jahrgang", "name")


def schueler_ids_der_klassen(klassen, stichtag=None):
    return set(Mitgliedschaft.objects.aktiv(stichtag).filter(gruppe__in=klassen).values_list("schueler_id", flat=True))


def abschnitt_zu(datum):
    return Abschnitt.objects.filter(beginn__lte=datum, ende__gte=datum).select_related("schuljahr").first()


def stunden_je_tag(sj):
    return Stunde.objects.filter(schuljahr=sj).count() if sj else 0


# ---------------------------------------------------------------- Erfassen

def _zahl(text):
    text = (text or "").strip()
    return int(text) if text.isdigit() else None


def eintrag_aus_formular(post, s_pk, datum):
    """Liest die Eingaben einer Zeile. None, wenn nichts eingetragen wurde; sonst eine ungespeicherte Fehlzeit."""
    art = post.get(f"art_{s_pk}", "")
    if art not in dict(Fehlzeit.ARTEN):
        return None
    f = Fehlzeit(schueler_id=s_pk, art=art, datum_von=datum, status=post.get(f"status_{s_pk}") or "offen",
                 grund=(post.get(f"grund_{s_pk}") or "").strip()[:200])
    if f.status not in dict(Fehlzeit.STATUS):
        f.status = "offen"
    if art == Fehlzeit.GANZTAEGIG:
        bis = parse_date(post.get(f"bis_{s_pk}") or "")
        f.datum_bis = bis if bis and bis != datum else None
    elif art == Fehlzeit.STUNDEN:
        f.stunde_von, f.stunde_bis = _zahl(post.get(f"von_{s_pk}")), _zahl(post.get(f"bisstd_{s_pk}"))
        if f.stunde_von and not f.stunde_bis:
            f.stunde_bis = f.stunde_von
    else:
        f.minuten = _zahl(post.get(f"min_{s_pk}"))
    return f


@transaction.atomic
def erfassen(eintraege, quelle, user):
    for f in eintraege:
        f.quelle = quelle
        f.erfasst_von = user
        f.save()                       # löst die automatische Elternbenachrichtigung aus (elternkontakt)
    return len(eintraege)


# ---------------------------------------------------------------- Seite

@login_required
def fehlzeiten(request):
    user = request.user
    if not darf_sehen(user):
        raise PermissionDenied
    sj = Schuljahr.aktuelles()
    heute = timezone.localdate()
    datum = parse_date(request.GET.get("datum") or request.POST.get("datum") or "") or heute
    klassen = list(klassen_fuer(user, sj)) if sj else []
    darf_erfassen, darf_aendern = user.has_perm("fehlzeiten.add_fehlzeit"), user.has_perm("fehlzeiten.change_fehlzeit")
    darf_loeschen = user.has_perm("fehlzeiten.delete_fehlzeit")

    gruppe = None
    if (request.GET.get("gruppe") or request.POST.get("gruppe") or "").isdigit():
        gruppe = get_object_or_404(Gruppe, pk=request.GET.get("gruppe") or request.POST.get("gruppe"))
        if gruppe not in klassen:
            raise PermissionDenied

    # Offene Entschuldigungen je Klasse für die Kacheln
    klasse_je_schueler = dict(Mitgliedschaft.objects.aktiv().filter(gruppe__in=klassen).values_list("schueler_id", "gruppe_id"))
    offen_je_klasse = {}
    for s_pk, n in (Fehlzeit.objects.filter(status="offen", schueler_id__in=klasse_je_schueler)
                    .values_list("schueler_id").annotate(n=Count("pk"))):
        g = klasse_je_schueler[s_pk]
        offen_je_klasse[g] = offen_je_klasse.get(g, 0) + n

    def zurueck(**extra):
        ziel = {"gruppe": gruppe.pk if gruppe else "", "datum": datum.isoformat()} if gruppe else {"offen": "1"}
        ziel.update(extra)
        return redirect(reverse("fehlzeiten") + "?" + "&".join(f"{k}={v}" for k, v in ziel.items() if v != ""))

    sichtbare_ids = schueler_ids_der_klassen([gruppe] if gruppe else klassen)

    if request.method == "POST":
        aktion = request.POST.get("aktion")
        if aktion == "erfassen":
            if not (darf_erfassen and gruppe):
                raise PermissionDenied
            mitglieder = {s.pk for s in gruppe.aktuelle_mitglieder(datum)}
            eintraege, fehler = [], []
            for s_pk in mitglieder:
                f = eintrag_aus_formular(request.POST, s_pk, datum)
                if f is None:
                    continue
                try:
                    f.clean()
                except ValidationError as e:
                    fehler.append(f"{f.schueler.person}: {' '.join(e.messages)}")
                    continue
                eintraege.append(f)
            if fehler:
                for meldung in fehler:
                    messages.error(request, meldung)
                messages.error(request, gettext("Es wurde nichts gespeichert. Bitte die markierten Angaben prüfen."))
            elif not eintraege:
                messages.info(request, gettext("Es war nichts eingetragen."))
            else:
                quelle = request.POST.get("quelle")
                n = erfassen(eintraege, quelle if quelle in dict(Fehlzeit.QUELLEN) else "lehrkraft", user)
                messages.success(request, ngettext("%(n)d Fehlzeit gespeichert.", "%(n)d Fehlzeiten gespeichert.", n) % {"n": n})
            return zurueck()
        if aktion in ("entschuldigt", "unentschuldigt", "offen"):
            if not darf_aendern:
                raise PermissionDenied
            ids = [int(x) for x in request.POST.getlist("fehlzeit") if x.isdigit()]
            qs = Fehlzeit.objects.filter(pk__in=ids, schueler_id__in=sichtbare_ids)
            n = 0
            for f in qs:                   # einzeln speichern, damit Änderungsprotokoll und Benachrichtigung greifen
                if f.status != aktion:
                    f.status = aktion
                    f.save(update_fields=["status"])
                    n += 1
            if n:
                messages.success(request, ngettext("%(n)d Fehlzeit geändert.", "%(n)d Fehlzeiten geändert.", n) % {"n": n})
            else:
                messages.info(request, gettext("Bitte zuerst Einträge ankreuzen."))
            return zurueck(offen="1" if request.POST.get("offen") else "")
        if aktion == "loeschen":
            if not darf_loeschen:
                raise PermissionDenied
            f = get_object_or_404(Fehlzeit, pk=request.POST.get("fehlzeit"), schueler_id__in=sichtbare_ids)
            f.delete()
            messages.success(request, gettext("Fehlzeit gelöscht."))
            return zurueck()
        raise PermissionDenied

    kontext = {
        "sj": sj, "klassen": klassen, "gruppe": gruppe, "datum": datum, "heute": heute,
        "vortag": datum - timedelta(days=3 if datum.weekday() == 0 else 1),
        "folgetag": datum + timedelta(days=3 if datum.weekday() == 4 else 1),
        "offen_je_klasse": offen_je_klasse, "offen_gesamt": sum(offen_je_klasse.values()),
        "nur_offen": request.GET.get("offen") == "1",
        "darf_erfassen": darf_erfassen, "darf_aendern": darf_aendern, "darf_loeschen": darf_loeschen,
        "arten": Fehlzeit.ARTEN, "status_werte": Fehlzeit.STATUS, "quellen": Fehlzeit.QUELLEN,
        "quelle_vorwahl": "sekretariat" if ist_verwaltung(user) else "lehrkraft",
        "jahrgaenge": sorted({k.jahrgang for k in klassen if k.jahrgang is not None}),
    }

    if gruppe is None:
        if kontext["nur_offen"]:
            offene = (Fehlzeit.objects.filter(status="offen", schueler_id__in=sichtbare_ids)
                      .select_related("schueler__person").order_by(*SORTIERUNG, "datum_von"))
            klasse_von = dict(Mitgliedschaft.objects.aktiv().filter(gruppe__in=klassen).values_list("schueler_id", "gruppe__name"))
            kontext["offene"] = sorted(offene, key=lambda f: (klasse_von.get(f.schueler_id, ""), f.schueler.person.nachname,
                                                               f.schueler.person.vorname, f.datum_von))
            kontext["klasse_von"] = klasse_von
        return render(request, "fehlzeiten/klassen.html", kontext)

    # Klasse geöffnet
    mitglieder = sorted(gruppe.aktuelle_mitglieder(datum),
                        key=lambda s: (s.person.nachname.lower(), (s.person.rufname or s.person.vorname).lower()))
    ids = [s.pk for s in mitglieder]
    abschnitt = abschnitt_zu(datum)
    std_tag = stunden_je_tag(sj)
    am_tag = {}
    for f in (Fehlzeit.objects.filter(schueler_id__in=ids, datum_von__lte=datum)
              .filter(Q(datum_bis__gte=datum) | Q(datum_bis__isnull=True, datum_von=datum))):
        am_tag.setdefault(f.schueler_id, []).append(f)
    summen = {pk: {"fehltage": 0, "stunden": 0, "unentsch": 0, "verspaetung": 0, "minuten": 0, "offen": 0} for pk in ids}
    eintraege = []
    if abschnitt:
        eintraege = list(Fehlzeit.objects.filter(schueler_id__in=ids, datum_von__gte=abschnitt.beginn, datum_von__lte=abschnitt.ende)
                         .select_related("schueler__person").order_by("-datum_von", *SORTIERUNG))
        for f in eintraege:
            z = summen[f.schueler_id]
            if f.art == Fehlzeit.VERSPAETUNG:
                z["verspaetung"] += 1
                z["minuten"] += f.minuten or 0
            else:
                h = f.fehlstunden(std_tag)
                z["stunden"] += h
                if f.art == Fehlzeit.GANZTAEGIG:
                    z["fehltage"] += f.schultage()
                if f.status == "unentschuldigt":
                    z["unentsch"] += h
            if f.status == "offen":
                z["offen"] += 1
    kontext.update({
        "zeilen": [{"s": s, "heute": am_tag.get(s.pk, []), "summe": summen[s.pk]} for s in mitglieder],
        "abschnitt": abschnitt, "eintraege": eintraege,
        "offene": list(Fehlzeit.objects.filter(schueler_id__in=ids, status="offen").select_related("schueler__person")
                       .order_by(*SORTIERUNG, "datum_von")),
        "stunden": list(Stunde.objects.filter(schuljahr=sj).order_by("nummer")) if sj else [],
        "wochenende": datum.weekday() >= 5, "datum_im_schuljahr": bool(sj and sj.beginn <= datum <= sj.ende),
        "anzahl_am_tag": sum(len(v) for v in am_tag.values()),
    })
    return render(request, "fehlzeiten/klasse.html", kontext)

