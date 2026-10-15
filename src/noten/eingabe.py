"""
Schnelleingabe von Noten (ab 0.4.7.0).

Eine Eingabe je Schüler:in als Text:
    2+  2  2-  …        Note der Skala des Unterrichts (Sek II: 15 … 0)
    34  34,5            erreichte BE, wenn der Leistungsnachweis einen Notenschlüssel hat
    =2+                 Note direkt, auch bei Leistungsnachweisen mit Notenschlüssel
    e  u  b  nb         entschuldigt, unentschuldigt, befreit, nicht bewertbar
    u 6                 unentschuldigt mit Note
    (leer)              keine Note
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils.translation import gettext

from .models import Note

STATUS = {
    "e": "entschuldigt", "en": "entschuldigt", "ent": "entschuldigt", "entsch": "entschuldigt", "entsch.": "entschuldigt",
    "u": "unentschuldigt", "un": "unentschuldigt", "unent": "unentschuldigt", "unentsch": "unentschuldigt", "unentsch.": "unentschuldigt",
    "b": "befreit", "bef": "befreit", "befreit": "befreit",
    "nb": "nicht_bewertbar", "n.b.": "nicht_bewertbar", "n.b": "nicht_bewertbar", "nichtbewertbar": "nicht_bewertbar",
}
KUERZEL = {"entschuldigt": "e", "unentschuldigt": "u", "befreit": "b", "nicht_bewertbar": "nb"}


class EingabeFehler(ValueError):
    pass


@dataclass
class Gedeutet:
    stufe: object = None
    be: Decimal | None = None
    status: str = ""

    @property
    def leer(self):
        return self.stufe is None and self.be is None and not self.status


def normalisieren(text):
    t = (text or "").strip().lower()
    for zeichen in ("−", "–", "—"):
        t = t.replace(zeichen, "-")
    return t.replace(" ", "")


def stufen_verzeichnis(skala):
    """Normalisierte Bezeichnung → Notenstufe (Sek II zusätzlich mit führender Null, z. B. „05“)."""
    verzeichnis = {}
    for s in skala.stufen.all():
        b = normalisieren(s.bezeichnung)
        verzeichnis[b] = s
        if b.isdigit() and len(b) == 1:
            verzeichnis["0" + b] = s
    return verzeichnis


def _stufe(t, verzeichnis):
    return verzeichnis.get(t)


def deuten(text, ln, verzeichnis):
    """Deutet eine Eingabe für den Leistungsnachweis `ln`. Wirft EingabeFehler mit verständlicher Meldung."""
    t = normalisieren(text)
    if not t:
        return Gedeutet()
    if t in STATUS:
        return Gedeutet(status=STATUS[t])
    if t.startswith("u") and t[1:].lstrip(":") and _stufe(t[1:].lstrip(":"), verzeichnis):
        return Gedeutet(stufe=_stufe(t[1:].lstrip(":"), verzeichnis), status="unentschuldigt")
    if t.startswith("="):
        s = _stufe(t[1:], verzeichnis)
        if s is None:
            raise EingabeFehler(gettext("„%(text)s“ ist keine Note dieser Skala.") % {"text": text.strip()})
        return Gedeutet(stufe=s)
    if ln.schluessel_id and ln.max_be:
        try:
            be = Decimal(t.replace(",", "."))
        except InvalidOperation:
            raise EingabeFehler(gettext("„%(text)s“: Bitte erreichte BE als Zahl eingeben (oder =Note).") % {"text": text.strip()}) from None
        if be < 0 or be > ln.max_be:
            raise EingabeFehler(gettext("%(be)s BE liegt nicht zwischen 0 und %(max)s.") % {
                "be": text.strip(), "max": _zahl(ln.max_be)})
        if be != be.quantize(Decimal("0.01")):
            raise EingabeFehler(gettext("Bitte höchstens zwei Nachkommastellen."))
        return Gedeutet(be=be)
    s = _stufe(t, verzeichnis)
    if s is None:
        raise EingabeFehler(gettext("„%(text)s“ ist keine Note dieser Skala.") % {"text": text.strip()})
    return Gedeutet(stufe=s)


def _zahl(wert):
    if wert is None:
        return ""
    text = format(wert.normalize(), "f") if isinstance(wert, Decimal) else str(wert)
    return text.replace(".", ",")


def anzeige(note):
    """Text, der eine gespeicherte Note in der Schnelleingabe wiedergibt."""
    if note is None:
        return ""
    ln = note.leistungsnachweis
    if note.sonderstatus:
        k = KUERZEL.get(note.sonderstatus, "")
        return f"{k} {note.stufe.bezeichnung}" if note.sonderstatus == "unentschuldigt" and note.stufe_id else k
    if note.erreichte_be is not None and ln.schluessel_id:
        return _zahl(note.erreichte_be)
    if note.stufe_id:
        return f"={note.stufe.bezeichnung}" if ln.schluessel_id and ln.max_be else note.stufe.bezeichnung
    return ""


def gewicht_deuten(text):
    t = (text or "").strip().replace(",", ".")
    if not t:
        return None
    try:
        wert = Decimal(t)
    except InvalidOperation:
        raise EingabeFehler(gettext("Das Gewicht muss eine Zahl sein.")) from None
    if wert < 0:
        raise EingabeFehler(gettext("Das Gewicht darf nicht negativ sein."))
    return wert


def pruefen(ln, eingaben, schueler):
    """
    eingaben: {schueler_pk: {"note": str, "kommentar": str, "gewicht": str, "begruendung": str}}
    Gibt (ergebnisse, fehler) zurück; ergebnisse: {pk: (Gedeutet, kommentar, gewicht, begruendung)}.
    """
    verzeichnis = stufen_verzeichnis(ln.unterricht.skala)
    ergebnisse, fehler = {}, {}
    for s in schueler:
        e = eingaben.get(s.pk)
        if e is None:
            continue
        try:
            g = deuten(e.get("note", ""), ln, verzeichnis)
            gewicht = gewicht_deuten(e.get("gewicht", ""))
            begruendung = (e.get("begruendung") or "").strip()[:200]
            if gewicht is not None and gewicht != ln.gewicht and not begruendung:
                raise EingabeFehler(gettext("Abweichendes Gewicht bitte begründen."))
            if gewicht is not None and g.leer:
                raise EingabeFehler(gettext("Ein Einzelgewicht ohne Note ist nicht möglich."))
        except EingabeFehler as f:
            fehler[s.pk] = str(f)
            continue
        ergebnisse[s.pk] = (g, (e.get("kommentar") or "").strip()[:200], gewicht, begruendung)
    return ergebnisse, fehler


@transaction.atomic
def speichern(ln, ergebnisse):
    """Schreibt die geprüften Eingaben. Gibt die Zahl der geänderten Noten zurück."""
    vorhanden = {n.schueler_id: n for n in Note.objects.filter(leistungsnachweis=ln).select_related("stufe")}
    geaendert = 0
    for pk, (g, kommentar, gewicht, begruendung) in ergebnisse.items():
        n = vorhanden.get(pk) or Note(leistungsnachweis=ln, schueler_id=pk)
        neu = {
            "stufe_id": g.stufe.pk if g.stufe is not None else None,
            "erreichte_be": g.be,
            "sonderstatus": g.status,
            "kommentar": kommentar,
            "gewicht_individuell": gewicht,
            "gewicht_begruendung": begruendung if gewicht is not None else "",
        }
        # Bei BE ergibt sich die Note beim Speichern aus dem Notenschlüssel; sie wird daher nicht verglichen.
        vergleich = [k for k in neu if not (k == "stufe_id" and g.be is not None)]
        if n.pk and all(getattr(n, k) == neu[k] for k in vergleich):
            continue
        for k, v in neu.items():
            setattr(n, k, v)
        n.leistungsnachweis = ln
        n.save()
        geaendert += 1
    return geaendert
