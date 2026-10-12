"""
Zuteilung der AG-Plätze per Losverfahren.

Ablauf je Halbjahr:
1. Alle Schüler:innen mit Wünschen, die noch keine AG haben, werden ausgelost (zufällige Reihenfolge).
2. Runde 1 vergibt Erstwünsche, solange Plätze frei sind; Runde 2 Zweitwünsche; Runde 3 Drittwünsche.
3. Pro Zuteilung entsteht eine Mitgliedschaft in der AG-Gruppe.

Annahme für Version 1: jede Schülerin / jeder Schüler erhält höchstens eine AG pro Halbjahr.
Bereits vorhandene Zuteilungen bleiben unangetastet.
"""
import random
from dataclasses import dataclass

from django.db import transaction

from stammdaten.models import Mitgliedschaft

from .models import AGAngebot, AGWahl, AGZuteilung


@dataclass
class Ergebnis:
    zugeteilt: dict
    ohne_platz: list


@transaction.atomic
def lose_zuteilen(abschnitt, seed=None) -> Ergebnis:
    rng = random.Random(seed)
    angebote = {a.pk: a for a in AGAngebot.objects.select_for_update().filter(abschnitt=abschnitt)}
    belegt = {pk: a.zuteilungen.count() for pk, a in angebote.items()}

    bereits = set(AGZuteilung.objects.filter(angebot__abschnitt=abschnitt).values_list("schueler_id", flat=True))
    wahlen = AGWahl.objects.filter(angebot__abschnitt=abschnitt).select_related("schueler", "angebot")
    wuensche: dict[int, dict[int, int]] = {}
    schueler_objekte = {}
    for w in wahlen:
        if w.schueler_id in bereits:
            continue
        wuensche.setdefault(w.schueler_id, {})[w.prioritaet] = w.angebot_id
        schueler_objekte[w.schueler_id] = w.schueler

    reihenfolge = list(wuensche)
    rng.shuffle(reihenfolge)
    zugeteilt = {1: 0, 2: 0, 3: 0}
    offen = list(reihenfolge)

    for prioritaet in (1, 2, 3):
        noch_offen = []
        for sid in offen:
            angebot_id = wuensche[sid].get(prioritaet)
            angebot = angebote.get(angebot_id)
            if angebot and belegt[angebot.pk] < angebot.kapazitaet:
                schueler = schueler_objekte[sid]
                AGZuteilung.objects.create(schueler=schueler, angebot=angebot, erfuellter_wunsch=prioritaet)
                Mitgliedschaft.objects.get_or_create(
                    gruppe=angebot.gruppe, schueler=schueler,
                    defaults={"von": abschnitt.beginn, "bis": abschnitt.ende},
                )
                belegt[angebot.pk] += 1
                zugeteilt[prioritaet] += 1
            else:
                noch_offen.append(sid)
        offen = noch_offen

    return Ergebnis(zugeteilt=zugeteilt, ohne_platz=[schueler_objekte[s] for s in offen])
