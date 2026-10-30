"""
Fächer und Lehrkräfte einer Klasse oder Lerngruppe (ab 0.4.14.0) – Teil der Seite „Klassen und Gruppen“.

Je Fach und Halbjahr wird eine Lehrkraft gewählt; daraus entsteht der Unterricht (noten.Unterricht).
Ein Unterricht mit Leistungsnachweisen oder Zeugnisnoten wird nie gelöscht – dort lässt sich nur die
Lehrkraft wechseln. Übernommen werden nur Zellen, die auf der Seite geändert wurden; was inzwischen von
anderer Seite geändert wurde, bleibt unangetastet.
"""
from collections import Counter
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext
from django.views.decorators.http import require_POST

from noten.models import Leistungsnachweis, Notenskala, Unterricht, Zeugnisnote
from stammdaten.models import Abschnitt, Fach, Gruppe, Personalprofil, Stundentafel

from .zuordnung import _zurueck, darf_gruppe_bearbeiten

UNTERRICHT_RECHTE = ("noten.add_unterricht", "noten.change_unterricht", "noten.delete_unterricht")


def darf_unterricht_verteilen(user, gruppe):
    """Wer die Gruppe bearbeiten darf und die Rechte für Unterricht hat (Sekretariat, Koordination, Leitung, IT)."""
    return darf_gruppe_bearbeiten(user, gruppe) and user.has_perms(UNTERRICHT_RECHTE)


def _feld(fach_id, abschnitt_id):
    return f"l_{fach_id}_{abschnitt_id}"


def standardskala(gruppe):
    """Notenskala wie bei anderen Gruppen desselben Jahrgangs; sonst Sek II für die Oberstufe, Sek I für alle anderen."""
    vorhanden = Counter(Unterricht.objects.filter(gruppe__jahrgang=gruppe.jahrgang).values_list("skala_id", flat=True)) \
        if gruppe.jahrgang else Counter()
    if vorhanden:
        return Notenskala.objects.get(pk=vorhanden.most_common(1)[0][0])
    oberstufe = gruppe.jahrgang in settings.STUFEN.get("oberstufe", ())
    return (Notenskala.objects.filter(name__startswith="Sek II" if oberstufe else "Sek I ").first()
            or Notenskala.objects.order_by("pk").first())


def _gewichtung(gruppe, fach):
    """Startvorlage wie beim zuletzt angelegten Unterricht desselben Fachs im selben Jahrgang."""
    u = (Unterricht.objects.filter(fach=fach, gruppe__jahrgang=gruppe.jahrgang, gewichtung__isnull=False)
         .order_by("-pk").first()) if gruppe.jahrgang else None
    return u.gewichtung if u else None


def unterrichte(gruppe):
    """{(fach_id, abschnitt_id): Unterricht} mit Markierung `hat_daten` (Leistungsnachweise oder Zeugnisnoten)."""
    qs = (Unterricht.objects.filter(gruppe=gruppe).select_related("lehrkraft__person")
          .annotate(hat_nachweise=Exists(Leistungsnachweis.objects.filter(unterricht=OuterRef("pk"))),
                    hat_zeugnisnoten=Exists(Zeugnisnote.objects.filter(unterricht=OuterRef("pk")))))
    ergebnis = {}
    for u in qs:
        u.hat_daten = u.hat_nachweise or u.hat_zeugnisnoten
        ergebnis[(u.fach_id, u.abschnitt_id)] = u
    return ergebnis


def lehrkraefte(gruppe):
    """Aktive Lehrkräfte (unterrichtender Bereich) und alle, die in der Gruppe schon unterrichten."""
    return (Personalprofil.objects.filter(Q(aktiv=True, bereich__unterrichtet=True) | Q(unterrichte__gruppe=gruppe))
            .select_related("person").prefetch_related("lehrbefaehigungen").distinct()
            .order_by("person__nachname", "person__vorname"))


def tabelle(gruppe):
    """Zeilen je Fach mit einer Zelle je Halbjahr für die Seite."""
    abschnitte = list(Abschnitt.objects.filter(schuljahr=gruppe.schuljahr).order_by("nummer"))
    vorhanden = unterrichte(gruppe)
    personal = list(lehrkraefte(gruppe))
    befaehigt = {}
    for p in personal:
        for f in p.lehrbefaehigungen.all():
            befaehigt.setdefault(f.pk, []).append(p)
    tafel = dict(Stundentafel.objects.filter(jahrgang=gruppe.jahrgang).values_list("fach_id", "wochenstunden")) if gruppe.jahrgang else {}
    zeilen = []
    for fach in Fach.objects.select_related("fachbereich"):
        zellen = [{"abschnitt": a, "feld": _feld(fach.pk, a.pk), "u": vorhanden.get((fach.pk, a.pk))} for a in abschnitte]
        mit = befaehigt.get(fach.pk, [])
        zeilen.append({"fach": fach, "zellen": zellen, "belegt": any(z["u"] for z in zellen), "stunden": tafel.get(fach.pk),
                       "befaehigt": mit, "weitere": [p for p in personal if p not in mit]})
    return {"abschnitte": abschnitte, "zeilen": zeilen, "belegt": any(z["belegt"] for z in zeilen),
            "deputate": deputate(gruppe, abschnitte, vorhanden.values())}


def stunden_von(u, tafel):
    return u.wochenstunden if u.wochenstunden is not None else tafel.get((u.fach_id, u.gruppe.jahrgang))


def deputate(gruppe, abschnitte, unterrichte_der_gruppe):
    """Je Lehrkraft der Gruppe und Halbjahr: Stunden in dieser Gruppe, insgesamt im Halbjahr und Soll (ab 0.4.16.0)."""
    lehrkraefte = {u.lehrkraft_id for u in unterrichte_der_gruppe}
    if not lehrkraefte:
        return []
    tafel = {(f, j): w for f, j, w in Stundentafel.objects.values_list("fach_id", "jahrgang", "wochenstunden")}
    alle = Unterricht.objects.filter(abschnitt__in=abschnitte, lehrkraft_id__in=lehrkraefte).select_related("gruppe")
    summe = {}
    for u in alle:
        schluessel = (u.lehrkraft_id, u.abschnitt_id)
        hier, gesamt = summe.get(schluessel, (Decimal(0), Decimal(0)))
        h = stunden_von(u, tafel) or Decimal(0)
        summe[schluessel] = (hier + (h if u.gruppe_id == gruppe.pk else 0), gesamt + h)
    zeilen = []
    for p in Personalprofil.objects.filter(pk__in=lehrkraefte).select_related("person").order_by("person__nachname"):
        soll = (p.wochenstunden - (p.ermaessigung or 0)) if p.wochenstunden is not None else None
        zeilen.append({"p": p, "soll": soll, "halbjahre": [summe.get((p.pk, a.pk), (Decimal(0), Decimal(0))) for a in abschnitte]})
    return zeilen


@transaction.atomic
def speichern(gruppe, aenderungen):
    """
    aenderungen: {(fach_id, abschnitt_id): (vorher_lehrkraft_id | None, neu_lehrkraft_id | None)}.
    Rückgabe: dict mit Zählern und Meldungen.
    """
    ergebnis = {"neu": 0, "geaendert": 0, "entfernt": 0, "fehler": []}
    if not aenderungen:
        return ergebnis
    vorhanden = unterrichte(gruppe)
    faecher = Fach.objects.in_bulk({f for f, _a in aenderungen})
    abschnitte = Abschnitt.objects.filter(schuljahr=gruppe.schuljahr).in_bulk({a for _f, a in aenderungen})
    personal = Personalprofil.objects.in_bulk({n for _v, n in aenderungen.values() if n})
    skala = None
    for (fach_id, abschnitt_id), (vorher, neu) in aenderungen.items():
        fach, abschnitt = faecher.get(fach_id), abschnitte.get(abschnitt_id)
        if fach is None or abschnitt is None or (neu and neu not in personal):
            continue
        u = vorhanden.get((fach_id, abschnitt_id))
        if (u.lehrkraft_id if u else None) != vorher:
            ergebnis["fehler"].append(gettext("%(fach)s, %(hj)s: inzwischen von anderer Seite geändert – nicht überschrieben.")
                                      % {"fach": fach.lokal_name, "hj": abschnitt.lokal_name})
            continue
        if u is None and neu:
            skala = skala or standardskala(gruppe)
            if skala is None:
                ergebnis["fehler"].append(gettext("Es gibt noch keine Notenskala – bitte zuerst eine anlegen."))
                break
            Unterricht.objects.create(abschnitt=abschnitt, gruppe=gruppe, fach=fach, lehrkraft=personal[neu], skala=skala,
                                      gewichtung=_gewichtung(gruppe, fach),
                                      wochenstunden=Stundentafel.stunden(fach.pk, gruppe.jahrgang))
            ergebnis["neu"] += 1
        elif u is not None and neu:
            u.lehrkraft = personal[neu]
            u.save(update_fields=["lehrkraft"])
            ergebnis["geaendert"] += 1
        elif u is not None:
            if u.hat_daten:
                ergebnis["fehler"].append(gettext("%(fach)s, %(hj)s: Es gibt schon Noten – der Unterricht bleibt bestehen. "
                                                  "Bitte stattdessen die Lehrkraft wechseln.")
                                          % {"fach": fach.lokal_name, "hj": abschnitt.lokal_name})
                continue
            u.delete()
            ergebnis["entfernt"] += 1
    return ergebnis


def _id(wert):
    return int(wert) if wert and wert.isdigit() else None


@login_required
@require_POST
def unterricht_speichern(request, pk):
    gruppe = get_object_or_404(Gruppe.objects.select_related("schuljahr"), pk=pk)
    if not darf_unterricht_verteilen(request.user, gruppe):
        raise PermissionDenied
    aenderungen = {}
    for a in Abschnitt.objects.filter(schuljahr=gruppe.schuljahr):
        for fach_id in Fach.objects.values_list("pk", flat=True):
            feld = _feld(fach_id, a.pk)
            if feld not in request.POST:
                continue
            vorher, neu = _id(request.POST.get("vorher_" + feld)), _id(request.POST.get(feld))
            if vorher != neu:
                aenderungen[(fach_id, a.pk)] = (vorher, neu)
    e = speichern(gruppe, aenderungen)
    if e["neu"] or e["geaendert"] or e["entfernt"]:
        messages.success(request, gettext("Fächer und Lehrkräfte gespeichert: %(neu)s neu, %(geaendert)s geändert, "
                                          "%(entfernt)s entfernt.") % e)
    elif not e["fehler"]:
        messages.info(request, gettext("Keine Änderungen."))
    for f in e["fehler"]:
        messages.error(request, f)
    return _zurueck(gruppe.schuljahr, gruppe, ansicht="faecher")
