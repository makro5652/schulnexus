"""
Versetzungsprüfung nach der Richtlinie zur Gestaltung von Bildungsgängen und Abschlüssen in der Sekundarstufe I
an Deutschen Schulen im Ausland (Beschluss vom 18.03.2026), Ziffer 5.3 bis 5.5.

Reine Rechenlogik ohne Datenbank – die Entscheidung trifft immer die Klassenkonferenz als Versetzungskonferenz;
das Ergebnis hier ist ein Vorschlag.

Regeln (5.3):
- Versetzt, wenn alle Noten mindestens ausreichend sind.
- Versetzt auch, wenn
  a) höchstens ein Kernfach mangelhaft ist und durch mindestens befriedigend in einem anderen Kernfach
     ausgeglichen wird, oder
  b) höchstens eines der übrigen Fächer mangelhaft ist (kein Ausgleich nötig), oder
  c) ein Kernfach und ein weiteres Fach mangelhaft sind und durch mindestens befriedigend in drei anderen
     Fächern ausgeglichen werden (davon mindestens ein Kernfach, höchstens eines aus Kunst/Musik/Sport), oder
  d) zwei Fächer außerhalb der Kernfächer mangelhaft sind und durch mindestens befriedigend in zwei anderen
     Fächern ausgeglichen werden (höchstens eines aus Kunst/Musik/Sport), oder
  e) ein Fach außerhalb der Kernfächer ungenügend ist und durch mindestens befriedigend in drei Fächern
     ausgeglichen wird (davon eines ein Kernfach, höchstens eines aus Kunst/Musik/Sport).
- Ungenügend in einem Kernfach schließt die Versetzung aus (kein Ausgleich, keine Nachprüfung).
- Ausgeschlossen bei mehr als zwei mangelhaften Fächern, bei mangelhaft und ungenügend zugleich oder bei
  zwei oder mehr ungenügenden Fächern.
- Nachprüfung ab Jahrgangsstufe 7, wenn die Verbesserung um eine Notenstufe in einem Fach zur Versetzung führt.
- Fächer mit „n.b.“ bleiben außer Betracht (5.5).
"""
from dataclasses import dataclass, field

from django.utils.translation import gettext as _

VERSETZT, AUSGLEICH, NICHT = "versetzt", "versetzt_ausgleich", "nicht_versetzt"


@dataclass(frozen=True)
class Fachnote:
    schluessel: object          # z. B. Fach-ID
    name: str
    note: int | None            # 1–6; None = n.b. / befreit / fehlt
    kern: bool = False
    musisch: bool = False       # Fächergruppe Kunst, Musik, Sport


@dataclass
class Ergebnis:
    ergebnis: str
    gruende: list = field(default_factory=list)
    ausgleich: list = field(default_factory=list)        # Fächer, die zum Ausgleich herangezogen werden
    defizite: list = field(default_factory=list)         # (Name, Note) der mangelhaften/ungenügenden Fächer
    nachpruefung: list = field(default_factory=list)     # Fächer, in denen eine Nachprüfung zur Versetzung führen kann

    @property
    def versetzt(self):
        return self.ergebnis in (VERSETZT, AUSGLEICH)

    @property
    def gefaehrdet(self):
        return bool(self.defizite)

    def kurztext(self):
        teile = []
        if self.ergebnis == VERSETZT:
            teile.append(_("versetzt"))
        elif self.ergebnis == AUSGLEICH:
            teile.append(_("versetzt mit Ausgleich durch %(faecher)s") % {"faecher": ", ".join(self.ausgleich)})
        else:
            teile.append(_("nicht versetzt"))
        if self.nachpruefung:
            teile.append(_("Nachprüfung möglich in %(faecher)s") % {"faecher": ", ".join(self.nachpruefung)})
        return "; ".join(teile)


def _auswahl(kandidaten, anzahl, kern_mindestens):
    """Wählt Ausgleichsfächer: zuerst Kernfächer, höchstens ein Fach aus Kunst/Musik/Sport."""
    kern = sorted((f for f in kandidaten if f.kern), key=lambda f: f.note)
    if len(kern) < kern_mindestens:
        return None
    gewaehlt = kern[:kern_mindestens]
    rest = sorted((f for f in kandidaten if f not in gewaehlt), key=lambda f: (f.musisch, f.note, not f.kern))
    musisch = sum(1 for f in gewaehlt if f.musisch)
    for f in rest:
        if len(gewaehlt) >= anzahl:
            break
        if f.musisch and musisch >= 1:
            continue
        gewaehlt.append(f)
        musisch += f.musisch
    return gewaehlt if len(gewaehlt) >= anzahl else None


def _entscheiden(noten):
    bewertet = [f for f in noten if f.note in (1, 2, 3, 4, 5, 6)]
    mangelhaft = [f for f in bewertet if f.note == 5]
    ungenuegend = [f for f in bewertet if f.note == 6]
    defizite = mangelhaft + ungenuegend
    erg = Ergebnis(VERSETZT, defizite=[(f.name, f.note) for f in defizite])
    if not defizite:
        erg.gruende.append(_("Alle Fächer mindestens ausreichend."))
        return erg

    m_kern = [f for f in mangelhaft if f.kern]
    u_kern = [f for f in ungenuegend if f.kern]
    gut = [f for f in bewertet if f.note <= 3 and f not in defizite]

    def nicht(grund):
        erg.ergebnis = NICHT
        erg.gruende.append(grund)
        return erg

    if u_kern:
        return nicht(_("Ungenügend im Kernfach %(fach)s – ein Ausgleich oder eine Nachprüfung ist nicht möglich.")
                     % {"fach": u_kern[0].name})
    if len(ungenuegend) >= 2:
        return nicht(_("Ungenügend in zwei oder mehr Fächern."))
    if ungenuegend and mangelhaft:
        return nicht(_("Mangelhaft und ungenügend in je einem Fach."))
    if len(mangelhaft) > 2:
        return nicht(_("Mangelhaft in mehr als zwei Fächern."))

    def mit_ausgleich(anzahl, kern_mindestens, beschreibung):
        wahl = _auswahl(gut, anzahl, kern_mindestens)
        if wahl is None:
            return nicht(_("Kein ausreichender Ausgleich: %(regel)s") % {"regel": beschreibung})
        erg.ergebnis = AUSGLEICH
        erg.ausgleich = [f.name for f in wahl]
        erg.gruende.append(beschreibung)
        return erg

    if ungenuegend:                                   # genau ein ungenügendes Fach außerhalb der Kernfächer
        return mit_ausgleich(3, 1, _("Ungenügend in einem Fach außerhalb der Kernfächer erfordert mindestens befriedigend "
                                     "in drei Fächern, davon eines ein Kernfach, höchstens eines aus Kunst, Musik, Sport."))
    if len(mangelhaft) == 1:
        if m_kern:
            return mit_ausgleich(1, 1, _("Mangelhaft in einem Kernfach erfordert mindestens befriedigend in einem anderen Kernfach."))
        erg.gruende.append(_("Mangelhaft in höchstens einem Fach außerhalb der Kernfächer – ohne Ausgleich zulässig."))
        return erg
    # zwei mangelhafte Fächer
    if len(m_kern) == 2:
        return nicht(_("Mangelhaft in zwei Kernfächern."))
    if len(m_kern) == 1:
        return mit_ausgleich(3, 1, _("Mangelhaft in einem Kernfach und einem weiteren Fach erfordert mindestens befriedigend in "
                                     "drei anderen Fächern, davon mindestens ein Kernfach, höchstens eines aus Kunst, Musik, Sport."))
    return mit_ausgleich(2, 0, _("Mangelhaft in zwei Fächern außerhalb der Kernfächer erfordert mindestens befriedigend in "
                                 "zwei anderen Fächern, höchstens eines aus Kunst, Musik, Sport."))


def pruefen(noten, jahrgang=None):
    """Versetzungsvorschlag für eine Liste von Fachnoten (siehe Modulbeschreibung)."""
    noten = list(noten)
    erg = _entscheiden(noten)
    if erg.ergebnis == NICHT and (jahrgang or 0) >= 7 and not any(f.kern and f.note == 6 for f in noten):
        for f in noten:
            if f.note in (5, 6):
                besser = [Fachnote(g.schluessel, g.name, g.note - 1 if g is f else g.note, g.kern, g.musisch) for g in noten]
                if _entscheiden(besser).versetzt:
                    erg.nachpruefung.append(f.name)
    return erg
