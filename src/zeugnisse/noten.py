"""Zusammenstellung der Zeugnisnoten einer Schülerin / eines Schülers und Vorbereitung der Versetzungsprüfung."""
from decimal import ROUND_HALF_UP, Decimal

from django.db.models import Q
from django.utils.translation import gettext as _, gettext_lazy

from noten.models import Unterricht, Zeugnisnote
from stammdaten.models import Gruppe, Mitgliedschaft

from . import versetzung

# Notenstufen nach § 3 Sek I-PO
WORTE = {
    1: gettext_lazy("sehr gut"), 2: gettext_lazy("gut"), 3: gettext_lazy("befriedigend"),
    4: gettext_lazy("ausreichend"), 5: gettext_lazy("mangelhaft"), 6: gettext_lazy("ungenügend"),
}
VERMERK_KURZ = {"nb": gettext_lazy("n.b."), "befreit": gettext_lazy("befreit")}

# Kernfächer für die Versetzungsentscheidung (Rili 5.3) je Bildungsgang (Kürzel aus der Grundeinrichtung)
KERNFAECHER = {"GYM": ("deutsch", "mathematik", "fs1", "fs2"), "RS": ("deutsch", "mathematik", "fs1"), "HS": ("deutsch", "mathematik")}
BILDUNGSGANG_TEXT = {"GYM": gettext_lazy("Gymnasialer Bildungsgang"),
                     "RS": gettext_lazy("Bildungsgang zum Mittleren Schulabschluss (MSA)"),
                     "HS": gettext_lazy("Bildungsgang zum Ersten Schulabschluss (ESA)")}


# Reihenfolge innerhalb einer Zeugnisspalte wie im Muster (Anlage 11): links Deutsch, Fremdsprachen,
# Gesellschaftswissenschaften, Religion/Ethik; rechts Mathematik, Naturwissenschaften, Kunst/Musik/Sport.
ROLLENRANG = {"deutsch": 0, "mathematik": 0, "fremdsprache": 1, "sonstiges": 2, "religion": 3, "musisch": 3}


def fach_sortierung(fach):
    return (fach.zeugnisspalte, ROLLENRANG.get(fach.zeugnisrolle, 2), fach.reihenfolge, fach.name)


def ganze_note(stufe):
    """(Note, Punkte?) – Sek I: ganze Note 1–6 (Tendenzen werden gerundet), Sek II: Punkte 0–15."""
    if stufe is None:
        return None, False
    if stufe.skala.hoeher_ist_besser:
        return int(stufe.wert.to_integral_value(rounding=ROUND_HALF_UP)), True
    wert = int(Decimal(stufe.wert).to_integral_value(rounding=ROUND_HALF_UP))
    return min(max(wert, 1), 6), False


def note_text(note, punkte=False, vermerk=""):
    if vermerk:
        return str(VERMERK_KURZ.get(vermerk, vermerk))
    if note is None:
        return ""
    if punkte:
        return _("%(n)s Punkte") % {"n": note}
    return str(WORTE.get(note, note))


def stichtag_fuer(abschnitt, heute=None):
    from django.utils import timezone

    heute = heute or timezone.localdate()
    return min(max(heute, abschnitt.beginn), abschnitt.ende)


def klassen_mitglieder(klasse, abschnitt):
    """Schüler:innen der Klasse zum Stichtag im Halbjahr (heute bzw. Beginn/Ende des Halbjahres)."""
    return list(klasse.aktuelle_mitglieder(stichtag_fuer(abschnitt)).select_related("person").order_by("person__nachname", "person__vorname"))


def stammklasse_im_abschnitt(schueler, abschnitt):
    m = (Mitgliedschaft.objects.aktiv(stichtag_fuer(abschnitt))
         .filter(schueler=schueler, gruppe__typ=Gruppe.STAMMKLASSE, gruppe__schuljahr=abschnitt.schuljahr)
         .select_related("gruppe", "gruppe__leitung__person").first())
    return m.gruppe if m else None


def unterrichte_fuer(schueler, abschnitt):
    """Unterricht des Halbjahres, an dem die Schülerin / der Schüler teilgenommen hat."""
    gruppen = (Mitgliedschaft.objects.filter(schueler=schueler, von__lte=abschnitt.ende)
               .filter(Q(bis__isnull=True) | Q(bis__gte=abschnitt.beginn)).values("gruppe"))
    return (Unterricht.objects.filter(abschnitt=abschnitt, gruppe__in=gruppen)
            .select_related("fach", "skala", "lehrkraft__person", "gruppe", "abschnitt"))


def fachnoten(schueler, abschnitt, art):
    """
    Zeilen für das Zeugnis: je Fach die Zeugnisnote des Halbjahres; beim Jahreszeugnis zusätzlich Fächer, die nur
    im 1. Halbjahr unterrichtet wurden (epochal), mit Halbjahresangabe (Rili 5.1).
    """
    from .models import Zeugnis

    abschnitte = [abschnitt]
    if art in (Zeugnis.JAHR, Zeugnis.ABGANG):
        abschnitte = list(abschnitt.schuljahr.abschnitte.filter(nummer__lt=abschnitt.nummer).order_by("-nummer")) + abschnitte
    je_fach = {}
    for a in abschnitte:                               # spätere Halbjahre überschreiben frühere
        unterrichte = list(unterrichte_fuer(schueler, a))
        noten = {z.unterricht_id: z for z in Zeugnisnote.objects.filter(unterricht__in=unterrichte, schueler=schueler)
                 .select_related("stufe__skala")}
        for u in unterrichte:
            if not u.fach.auf_zeugnis:
                continue
            z = noten.get(u.pk)
            bisher = je_fach.get(u.fach_id)
            if bisher and bisher["abschnitt"] == a and bisher["zn"] is not None and z is None:
                continue                               # mehrere Kurse desselben Fachs: den mit Note nehmen
            note, punkte = ganze_note(z.stufe if z else None)
            je_fach[u.fach_id] = {
                "fach": u.fach, "unterricht": u, "abschnitt": a, "zn": z, "note": note, "punkte": punkte,
                "vermerk": z.vermerk if z else "", "fehlt": z is None, "lehrkraft": u.lehrkraft,
                "tendenz": bool(z and z.stufe and not punkte and z.stufe.wert != Decimal(note or 0)),
            }
    zeilen = sorted(je_fach.values(), key=lambda e: fach_sortierung(e["fach"]))
    for e in zeilen:
        e["hinweis"] = e["abschnitt"].lokal_name if e["abschnitt"] != abschnitt else ""
        e["text"] = note_text(e["note"], e["punkte"], e["vermerk"])
        e["fachname"] = e["fach"].lokal_name
    return zeilen


def laufbahn(schueler, abschnitt):
    """(Bildungsgang, Jahrgang) laut Schullaufbahn im Schuljahr des Halbjahres."""
    lb = (schueler.laufbahn.filter(schuljahr=abschnitt.schuljahr)
          .filter(Q(von__isnull=True) | Q(von__lte=abschnitt.ende)).select_related("bildungsgang").order_by("-von").first())
    return (lb.bildungsgang, lb.jahrgang) if lb else (None, None)


def fremdsprachen_reihenfolge(schueler, zeilen):
    """Fach-IDs der Fremdsprachen in Reihenfolge (1., 2. …) – aus der Sprachenfolge, sonst Englisch zuerst."""
    folge = list(schueler.sprachenfolge.order_by("position").values_list("fach_id", flat=True))
    vorhanden = [e["fach"] for e in zeilen if e["fach"].zeugnisrolle == "fremdsprache"]
    rest = sorted((f for f in vorhanden if f.pk not in folge),
                  key=lambda f: (f.kuerzel.upper() not in ("E", "EN"), f.reihenfolge))
    return folge + [f.pk for f in rest]


def kernfach_ids(schueler, bildungsgang, zeilen):
    rollen = KERNFAECHER.get(getattr(bildungsgang, "kuerzel", ""), None)
    if rollen is None:
        return None
    ids = {e["fach"].pk for e in zeilen if e["fach"].zeugnisrolle in rollen}
    fs = fremdsprachen_reihenfolge(schueler, zeilen)
    if "fs1" in rollen and fs:
        ids.add(fs[0])
    if "fs2" in rollen and len(fs) > 1:
        ids.add(fs[1])
    return ids


def versetzungsvorschlag(schueler, bildungsgang, jahrgang, zeilen):
    """
    Ergebnis der Prüfung nach Rili 5.3 oder ein Hinweistext, wenn die Regel nicht anwendbar ist
    (Abschlussjahrgänge, Oberstufe, fehlender Bildungsgang).
    """
    kern = kernfach_ids(schueler, bildungsgang, zeilen)
    if kern is None:
        return None, _("Kein Bildungsgang der Sekundarstufe I in der Schullaufbahn – keine automatische Prüfung.")
    if jahrgang is None or not 5 <= jahrgang <= 10:
        return None, _("Versetzungsregeln der Sekundarstufe I gelten für die Jahrgänge 5 bis 10.")
    noten = [versetzung.Fachnote(e["fach"].pk, e["fachname"], None if e["vermerk"] or e["punkte"] else e["note"],
                                 e["fach"].pk in kern, e["fach"].zeugnisrolle == "musisch") for e in zeilen]
    ergebnis = versetzung.pruefen(noten, jahrgang)
    hinweis = ""
    if jahrgang == 10:
        hinweis = _("Jahrgangsstufe 10: Übergang in die Qualifikationsphase bzw. Abschluss nach Sek I-PO – Vorschlag nur zur Orientierung.")
    elif jahrgang == 9 and getattr(bildungsgang, "kuerzel", "") == "HS":
        hinweis = _("Jahrgangsstufe 9 im Bildungsgang ESA: Abschlussverfahren nach Sek I-PO – Vorschlag nur zur Orientierung.")
    if any(e["fehlt"] for e in zeilen):
        hinweis = (hinweis + " " if hinweis else "") + _("Es fehlen noch Zeugnisnoten.")
    return ergebnis, hinweis
