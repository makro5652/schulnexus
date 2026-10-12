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

Noten mit Sonderstatus (entschuldigt, befreit, nicht bewertbar) zählen nicht.
"Unentschuldigt" zählt nur, wenn die Lehrkraft eine Note eingetragen hat.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal


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


def vorschlagsnote(unterricht, schueler, noten=None, baum=None) -> Vorschlag:
    """
    Berechnet die Vorschlagsnote einer Schülerin / eines Schülers in einem Unterricht.
    `noten` und `baum` können vorab geladen übergeben werden (vermeidet viele Datenbankabfragen).
    """
    from .models import Note

    skala = unterricht.skala
    baum = baum or Baum(unterricht)
    if noten is None:
        noten = Note.objects.filter(leistungsnachweis__unterricht=unterricht, schueler=schueler).select_related("stufe")
    wert_je_ln = {n.leistungsnachweis_id: n.stufe.wert for n in noten if n.stufe is not None}

    ergebnisse: dict[int, OrdnerErgebnis] = {}

    def wert(o, ebene, pfad):
        p = f"{pfad} › {o.name}" if pfad else o.name
        paare = [(wert_je_ln[ln.pk], ln.gewicht) for ln in baum.nachweise_in[o.pk] if ln.pk in wert_je_ln]
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
                warnungen.append(f"Keine Note im Ordner „{w.name}“ – der Schnitt beruht nur auf den übrigen Ordnern.")
        else:
            gesamt_paare.append((schnitt, w.gewicht))

    alle = [ergebnisse[o.pk] for o, _, _ in baum.in_reihenfolge()]
    haupt = [ergebnisse[w.pk] for w in baum.wurzeln()]

    gesamt = gewichteter_schnitt(gesamt_paare)
    if gesamt is None:
        return Vorschlag(None, None, haupt, alle, warnungen or ["Noch keine Noten vorhanden."])

    gesamt = skala.runden(gesamt)
    return Vorschlag(
        schnitt=gesamt,
        stufe=skala.naechste_stufe(gesamt),
        hauptordner=haupt,
        alle_ordner=alle,
        warnungen=warnungen,
        gefaehrdet=skala.ist_gefaehrdet(gesamt),
    )
