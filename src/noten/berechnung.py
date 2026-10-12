"""
Berechnung der Vorschlagsnote.

1. Innerhalb jeder Kategorie k:   n̄_k = Σ(w_i · n_i) / Σ w_i
2. Über die Kategorien:           N   = Σ(g_k · n̄_k) / Σ g_k
   (nur Kategorien, in denen mindestens eine Note vorliegt)

Fehlt eine Kategorie ganz, wird NICHT stillschweigend umgewichtet,
ohne dass es auffällt: Das Ergebnis trägt dann einen Warnhinweis.

Noten mit Sonderstatus (entschuldigt, befreit, nicht bewertbar) zählen nicht.
"Unentschuldigt" zählt nur, wenn die Lehrkraft eine Note eingetragen hat
(z. B. 6 gemäß Schulordnung).
"""
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class KategorieErgebnis:
    name: str
    anteil: Decimal
    schnitt: Decimal | None
    anzahl: int


@dataclass
class Vorschlag:
    schnitt: Decimal | None
    stufe: object | None
    kategorien: list[KategorieErgebnis] = field(default_factory=list)
    warnungen: list[str] = field(default_factory=list)
    gefaehrdet: bool = False


def gewichteter_schnitt(paare):
    """paare: Liste von (wert, gewicht). Gibt None zurück, wenn leer."""
    summe_gewichte = sum((g for _, g in paare), Decimal(0))
    if not paare or summe_gewichte == 0:
        return None
    return sum((w * g for w, g in paare), Decimal(0)) / summe_gewichte


def vorschlagsnote(unterricht, schueler, noten=None) -> Vorschlag:
    """
    Berechnet die Vorschlagsnote einer Schülerin / eines Schülers in einem Unterricht.
    `noten` kann vorab geladen übergeben werden (vermeidet viele Datenbankabfragen).
    """
    from .models import Note

    skala = unterricht.skala
    if noten is None:
        noten = list(
            Note.objects.filter(leistungsnachweis__unterricht=unterricht, schueler=schueler)
            .select_related("stufe", "leistungsnachweis__kategorie")
        )

    kategorien = list(unterricht.gewichtung.kategorien.all())
    ergebnisse: list[KategorieErgebnis] = []
    warnungen: list[str] = []
    gesamt_paare = []

    for kat in kategorien:
        paare = [
            (n.stufe.wert, n.leistungsnachweis.gewicht)
            for n in noten
            if n.leistungsnachweis.kategorie_id == kat.pk and n.stufe is not None
        ]
        schnitt = gewichteter_schnitt(paare)
        ergebnisse.append(KategorieErgebnis(kat.name, kat.anteil, skala.runden(schnitt) if schnitt is not None else None, len(paare)))
        if schnitt is None:
            if kat.anteil > 0:
                warnungen.append(f"Keine Note in der Kategorie „{kat.name}“ – der Schnitt beruht nur auf den übrigen Kategorien.")
        else:
            gesamt_paare.append((schnitt, kat.anteil))

    gesamt = gewichteter_schnitt(gesamt_paare)
    if gesamt is None:
        return Vorschlag(None, None, ergebnisse, warnungen or ["Noch keine Noten vorhanden."])

    gesamt = skala.runden(gesamt)
    return Vorschlag(
        schnitt=gesamt,
        stufe=skala.naechste_stufe(gesamt),
        kategorien=ergebnisse,
        warnungen=warnungen,
        gefaehrdet=skala.ist_gefaehrdet(gesamt),
    )
