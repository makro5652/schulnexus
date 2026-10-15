"""
Berechnung der Vorschlagsnote über verschachtelte Bewertungsordner.

Jeder Ordner bildet den gewichteten Mittelwert seiner Einträge – das sind
Leistungsnachweise UND Unterordner, jeweils mit ihrem eigenen Gewicht:

    Wert(Ordner) = Σ(g_i · w_i) / Σ g_i      (nur Einträge mit Wert)

Die Gesamtnote ist derselbe Mittelwert über die obersten Ordner.

Beispiel:  Schriftlich (50)  ─ 1. Klassenarbeit (1), Test (0,5)
           Sonstige Mitarbeit (50) ─ Quartal 1 (1) ─ Mitarbeit (1), Protokoll (0,5)
                                    └ Quartal 2 (1) ─ (noch leer)

Leere Ordner werden übersprungen, die übrigen Einträge ihrer Ebene tragen dann
mehr Gewicht. Fehlt einem obersten Ordner jede Note, gibt es einen Warnhinweis.

Jede einzelne Note kann ein individuelles Gewicht haben (z. B. Nachschreibarbeit);
sonst gilt das Gewicht des Leistungsnachweises.

Noten mit Sonderstatus (entschuldigt, befreit, nicht bewertbar) zählen nicht.
"Unentschuldigt" zählt mit der eingetragenen Note, sonst mit der Note der Skala für unentschuldigtes Versäumnis
(Voreinstellung 6 bzw. 0 Punkte; ab 0.4.8.0).

Jahresnote (ab 0.4.8.0): Im 2. Halbjahr kann das 1. Halbjahr mit einem Anteil (Voreinstellung 40 % in Jg. 5–10)
einfließen:  Jahr = a · Wert(1. Hj.) + (1 − a) · Schnitt(2. Hj.).  Wert(1. Hj.) ist der rechnerische Schnitt oder
– je nach Einstellung des Unterrichts – die festgesetzte Halbjahreszeugnisnote.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from django.utils.translation import gettext


@dataclass
class OrdnerErgebnis:
    ordner_id: int
    name: str
    pfad: str
    ebene: int
    gewicht: Decimal
    schnitt: Decimal | None
    anzahl: int


@dataclass
class Vorschlag:
    schnitt: Decimal | None
    stufe: object | None
    hauptordner: list[OrdnerErgebnis] = field(default_factory=list)
    alle_ordner: list[OrdnerErgebnis] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)
    gefaehrdet: bool = False
    halbjahr_schnitt: Decimal | None = None      # nur 2. Halbjahr (ohne Anteil des 1. Halbjahres)
    vorhalbjahr: Decimal | None = None           # Wert des 1. Halbjahres, falls eingerechnet
    anteil_vorhalbjahr: Decimal | None = None    # in Prozent


def gewichteter_schnitt(paare):
    """paare: Liste von (wert, gewicht). Gibt None zurück, wenn leer oder alle Gewichte 0."""
    summe_gewichte = sum((g for _, g in paare), Decimal(0))
    if not paare or summe_gewichte == 0:
        return None
    return sum((w * g for w, g in paare), Decimal(0)) / summe_gewichte


class Baum:
    """Ordner und Leistungsnachweise eines Unterrichts, einmal geladen und mehrfach nutzbar."""

    def __init__(self, unterricht, ordner=None, nachweise=None):
        from .models import Bewertungsordner, Leistungsnachweis

        self.ordner = list(ordner if ordner is not None else Bewertungsordner.objects.filter(unterricht=unterricht))
        self.nachweise = list(nachweise if nachweise is not None else Leistungsnachweis.objects.filter(unterricht=unterricht))
        self.kinder = defaultdict(list)
        self.nachweise_in = defaultdict(list)
        for o in self.ordner:
            self.kinder[o.eltern_id].append(o)
        for liste in self.kinder.values():
            liste.sort(key=lambda o: (o.reihenfolge, o.name))
        for ln in self.nachweise:
            self.nachweise_in[ln.ordner_id].append(ln)
        for liste in self.nachweise_in.values():
            liste.sort(key=lambda ln: (ln.datum, ln.titel))

    def wurzeln(self):
        return self.kinder[None]

    def in_reihenfolge(self):
        """(ordner, ebene, pfad) in Baumreihenfolge."""
        def gehe(o, ebene, pfad):
            p = f"{pfad} › {o.name}" if pfad else o.name
            yield o, ebene, p
            for k in self.kinder[o.pk]:
                yield from gehe(k, ebene + 1, p)

        for w in self.wurzeln():
            yield from gehe(w, 0, "")

    def nachweise_in_reihenfolge(self):
        """(leistungsnachweis, pfad des Ordners) in Baumreihenfolge."""
        for o, _, pfad in self.in_reihenfolge():
            for ln in self.nachweise_in[o.pk]:
                yield ln, pfad


def nominale_anteile(ordner, nachweise):
    """
    Planmäßiger Anteil jedes Ordners und Leistungsnachweises an der Gesamtnote in Prozent,
    wenn alle Einträge bewertet sind. Gibt ({ordner_id: %}, {nachweis_id: %}) zurück.
    """
    baum = Baum(None, ordner, nachweise)
    anteil_o, anteil_ln = {}, {}

    def verteile(eltern_id, faktor):
        eintraege = [("o", o, o.gewicht) for o in baum.kinder[eltern_id]]
        if eltern_id is not None:
            eintraege += [("n", ln, ln.gewicht) for ln in baum.nachweise_in[eltern_id]]
        summe = sum((g for _, _, g in eintraege), Decimal(0))
        for art, obj, g in eintraege:
            anteil = faktor * g / summe if summe else Decimal(0)
            if art == "o":
                anteil_o[obj.pk] = anteil * 100
                verteile(obj.pk, anteil)
            else:
                anteil_ln[obj.pk] = anteil * 100

    verteile(None, Decimal(1))
    return anteil_o, anteil_ln


class Vorhalbjahr:
    """Werte des 1. Halbjahres für die Jahresnote eines Unterrichts im 2. Halbjahr (einmal geladen, je Schüler:in abrufbar)."""

    def __init__(self, unterricht):
        from .models import Note, Unterricht, Zeugnisnote

        self.unterricht = unterricht
        self.anteil = (unterricht.anteil_vorhalbjahr or Decimal(0)) / 100
        self.kurse, self.mitglieder, self._baum, self._noten, self._zeugnis = [], {}, {}, {}, {}
        hj1 = unterricht.vorhalbjahr() if unterricht.mit_jahresnote else None
        if hj1 is None:
            return
        kurse = list(Unterricht.objects.filter(abschnitt=hj1, fach=unterricht.fach, skala=unterricht.skala)
                     .select_related("skala", "abschnitt", "gruppe"))
        # derselbe Kurs (gleiche Gruppe) zuerst, dann andere Kurse desselben Fachs (z. B. nach Klassenwechsel)
        kurse.sort(key=lambda k: k.gruppe_id != unterricht.gruppe_id)
        self.kurse = kurse
        for k in kurse:
            self.mitglieder[k.pk] = set(k.schueler().values_list("pk", flat=True))
        ids = [k.pk for k in kurse]
        for n in Note.objects.filter(leistungsnachweis__unterricht__in=ids).select_related("stufe", "leistungsnachweis"):
            self._noten.setdefault((n.leistungsnachweis.unterricht_id, n.schueler_id), []).append(n)
        for z in Zeugnisnote.objects.filter(unterricht__in=ids).select_related("stufe"):
            self._zeugnis[(z.unterricht_id, z.schueler_id)] = z

    def kurs_fuer(self, schueler):
        return next((k for k in self.kurse if schueler.pk in self.mitglieder.get(k.pk, ())), None)

    def wert(self, schueler):
        k = self.kurs_fuer(schueler)
        if k is None:
            return None
        if self.unterricht.vorhalbjahr_basis == "zeugnis":
            z = self._zeugnis.get((k.pk, schueler.pk))
            if z is not None and z.stufe_id:
                return z.stufe.wert
        if k.pk not in self._baum:
            self._baum[k.pk] = Baum(k)
        return vorschlagsnote(k, schueler, self._noten.get((k.pk, schueler.pk), []), self._baum[k.pk], jahr=False).schnitt


def vorschlagsnote(unterricht, schueler, noten=None, baum=None, jahr=None) -> Vorschlag:
    """
    Berechnet die Vorschlagsnote einer Schülerin / eines Schülers in einem Unterricht.
    `noten` und `baum` können vorab geladen übergeben werden (vermeidet viele Datenbankabfragen),
    ebenso `jahr` (Vorhalbjahr) für die Jahresnote; `jahr=False` rechnet nur das eigene Halbjahr.
    """
    from .models import Note

    skala = unterricht.skala
    baum = baum or Baum(unterricht)
    if noten is None:
        noten = Note.objects.filter(leistungsnachweis__unterricht=unterricht, schueler=schueler).select_related("stufe")
    ersatz = skala.unentschuldigt_stufe
    # Wert und ggf. individuelles Gewicht je Leistungsnachweis
    wert_je_ln = {}
    for n in noten:
        if n.stufe is not None:
            wert_je_ln[n.leistungsnachweis_id] = (n.stufe.wert, n.gewicht_individuell)
        elif n.sonderstatus == "unentschuldigt" and ersatz is not None:
            wert_je_ln[n.leistungsnachweis_id] = (ersatz.wert, n.gewicht_individuell)

    ergebnisse: dict[int, OrdnerErgebnis] = {}

    def wert(o, ebene, pfad):
        p = f"{pfad} › {o.name}" if pfad else o.name
        paare = []
        for ln in baum.nachweise_in[o.pk]:
            if ln.pk in wert_je_ln:
                wert_n, gewicht_individuell = wert_je_ln[ln.pk]
                paare.append((wert_n, gewicht_individuell if gewicht_individuell is not None else ln.gewicht))
        anzahl = len(paare)
        for k in baum.kinder[o.pk]:
            w, n = wert(k, ebene + 1, p)
            anzahl += n
            if w is not None:
                paare.append((w, k.gewicht))
        schnitt = gewichteter_schnitt(paare)
        ergebnisse[o.pk] = OrdnerErgebnis(o.pk, o.name, p, ebene, o.gewicht, skala.runden(schnitt) if schnitt is not None else None, anzahl)
        return schnitt, anzahl

    gesamt_paare, warnungen = [], []
    for w in baum.wurzeln():
        schnitt, _ = wert(w, 0, "")
        if schnitt is None:
            if w.gewicht > 0:
                warnungen.append(gettext("Keine Note im Ordner „%(ordner)s“ – der Schnitt beruht nur auf den übrigen Ordnern.")
                                 % {"ordner": w.name})
        else:
            gesamt_paare.append((schnitt, w.gewicht))

    alle = [ergebnisse[o.pk] for o, _, _ in baum.in_reihenfolge()]
    haupt = [ergebnisse[w.pk] for w in baum.wurzeln()]

    gesamt = gewichteter_schnitt(gesamt_paare)
    halbjahr = skala.runden(gesamt) if gesamt is not None else None
    vorher = anteil = None
    if jahr is not False and unterricht.mit_jahresnote:
        jahr = jahr or Vorhalbjahr(unterricht)
        vorher = jahr.wert(schueler)
        if vorher is not None:
            anteil = unterricht.anteil_vorhalbjahr
            a = anteil / 100
            if gesamt is None:
                gesamt = vorher
                warnungen = [gettext("Noch keine Note im 2. Halbjahr – der Vorschlag beruht nur auf dem 1. Halbjahr.")]
            else:
                gesamt = a * vorher + (1 - a) * gesamt
    if gesamt is None:
        return Vorschlag(None, None, haupt, alle, warnungen or [gettext("Noch keine Noten vorhanden.")])

    gesamt = skala.runden(gesamt)
    return Vorschlag(
        schnitt=gesamt,
        stufe=skala.naechste_stufe(gesamt),
        hauptordner=haupt,
        alle_ordner=alle,
        warnungen=warnungen,
        gefaehrdet=skala.ist_gefaehrdet(gesamt),
        halbjahr_schnitt=halbjahr,
        vorhalbjahr=skala.runden(vorher) if vorher is not None else None,
        anteil_vorhalbjahr=anteil,
    )
