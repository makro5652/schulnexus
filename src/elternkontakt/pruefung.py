"""
Automatische Benachrichtigung bei Fehlzeiten und Verspätungen.

Nach jedem Speichern einer Fehlzeit werden die aktiven Regeln für die betroffene Schülerin / den Schüler geprüft.
Jede Regel löst je Zeitraum (Halbjahr bzw. Schuljahr) höchstens einmal aus – mit „wiederholen“ erneut bei jedem
weiteren Vielfachen der Schwelle. Schulische Veranstaltungen (Quelle „schulisch“) zählen nicht.
"""
from datetime import date, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from stammdaten.models import Abschnitt, Gruppe, Mitgliedschaft, Schuljahr

from .models import Ausloesung, Benachrichtigungsregel, Gespraech


def _wochentage(von: date, bis: date) -> int:
    if bis < von:
        return 0
    tage, tag = 0, von
    while tag <= bis:
        tage += tag.weekday() < 5
        tag += timedelta(days=1)
    return tage


def zeitraum(regel, stichtag):
    """(Schlüssel, Beginn, Ende, Typ, ID) des Zeitraums, in dem der Stichtag liegt – oder None."""
    if regel.zeitraum == "halbjahr":
        a = Abschnitt.objects.filter(beginn__lte=stichtag, ende__gte=stichtag).first()
        return (f"abschnitt:{a.pk}", a.beginn, a.ende, "halbjahr", a.pk) if a else None
    s = Schuljahr.objects.filter(beginn__lte=stichtag, ende__gte=stichtag).first()
    return (f"schuljahr:{s.pk}", s.beginn, s.ende, "schuljahr", s.pk) if s else None


def kennzahl(schueler, merkmal, zaehlung, von, bis):
    """Wert eines Merkmals im Zeitraum [von, bis]."""
    from fehlzeiten.models import Fehlzeit

    qs = schueler.fehlzeiten.exclude(quelle="schulisch").filter(datum_von__lte=bis)
    if zaehlung == "unentschuldigt":
        qs = qs.filter(status="unentschuldigt")
    elif zaehlung == "nicht_entschuldigt":
        qs = qs.exclude(status="entschuldigt")
    if merkmal in ("verspaetungen", "verspaetungsminuten"):
        qs = qs.filter(art=Fehlzeit.VERSPAETUNG, datum_von__gte=von)
        return qs.count() if merkmal == "verspaetungen" else sum(f.minuten or 0 for f in qs)
    wert = 0
    stunden_pro_tag = None
    for f in qs.exclude(art=Fehlzeit.VERSPAETUNG):
        ende = f.datum_bis or f.datum_von
        if ende < von:
            continue
        if f.art == Fehlzeit.GANZTAEGIG:
            tage = _wochentage(max(f.datum_von, von), min(ende, bis))
            if merkmal == "fehltage":
                wert += tage
            else:
                if stunden_pro_tag is None:
                    sj = Schuljahr.objects.filter(beginn__lte=bis, ende__gte=bis).first()
                    stunden_pro_tag = sj.zeitraster.count() if sj else 0
                wert += tage * stunden_pro_tag
        elif merkmal == "fehlstunden" and f.datum_von >= von:
            wert += f.fehlstunden()
    return wert


def jahrgang_von(schueler, stichtag):
    m = (Mitgliedschaft.objects.aktiv(stichtag).filter(schueler=schueler, gruppe__typ=Gruppe.STAMMKLASSE)
         .select_related("gruppe").first())
    return m.gruppe.jahrgang if m else None


def _stufe(regel, wert):
    if wert < regel.schwelle:
        return 0
    return wert // regel.schwelle if regel.wiederholen else 1


def regel_pruefen(regel, schueler, stichtag, still=False, jahrgang=None):
    """Prüft eine Regel; legt bei Erreichen der Schwelle eine Auslösung (und ggf. eine Nachricht) an."""
    zr = zeitraum(regel, stichtag)
    if zr is None:
        return None
    schluessel, von, bis, typ, zid = zr
    wert = kennzahl(schueler, regel.merkmal, regel.zaehlung, von, bis)
    stufe = _stufe(regel, wert)
    if not stufe or Ausloesung.objects.filter(regel=regel, schueler=schueler, zeitraum=schluessel, stufe__gte=stufe).exists():
        return None
    try:
        with transaction.atomic():
            a = Ausloesung.objects.create(regel=regel, schueler=schueler, zeitraum=schluessel, stufe=stufe, wert=wert, still=still)
    except IntegrityError:  # gleichzeitig bereits ausgelöst
        return None
    if not still:
        from .versand import gespraech_anlegen, standard_empfaenger

        daten = {"merkmal": regel.merkmal, "zaehlung": regel.zaehlung, "wert": wert, "schwelle": regel.schwelle * stufe,
                 "zeitraum": typ, "zeitraum_id": zid, "vorname": schueler.person.rufname or schueler.person.vorname,
                 "regel": regel.pk, "zusatztext": regel.zusatztext}
        a.gespraech = gespraech_anlegen(
            schueler, [b.person for b in standard_empfaenger(schueler)], art=Gespraech.FEHLZEITEN, vorlage="fehlzeiten",
            daten=daten, bestaetigung=regel.bestaetigung_erbeten, antworten=True)
        a.save(update_fields=["gespraech"])
    return a


def schueler_pruefen(schueler, stichtag=None):
    """Alle aktiven Regeln für eine Schülerin / einen Schüler (nach dem Speichern einer Fehlzeit)."""
    stichtag = stichtag or timezone.localdate()
    jahrgang = jahrgang_von(schueler, stichtag)
    ergebnis = []
    for regel in Benachrichtigungsregel.objects.filter(aktiv=True):
        if regel.gilt_fuer(jahrgang):
            a = regel_pruefen(regel, schueler, stichtag)
            if a:
                ergebnis.append(a)
    return ergebnis


def betroffene(regel, stichtag=None):
    """Vorschau: Schüler:innen, die die Schwelle aktuell erreichen und noch nicht benachrichtigt wurden."""
    stichtag = stichtag or timezone.localdate()
    zr = zeitraum(regel, stichtag)
    if zr is None:
        return []
    schluessel, von, bis, _typ, _zid = zr
    mitglieder = (Mitgliedschaft.objects.aktiv(stichtag).filter(gruppe__typ=Gruppe.STAMMKLASSE)
                  .select_related("schueler__person", "gruppe"))
    ergebnis = []
    for m in mitglieder:
        if not regel.gilt_fuer(m.gruppe.jahrgang):
            continue
        wert = kennzahl(m.schueler, regel.merkmal, regel.zaehlung, von, bis)
        stufe = _stufe(regel, wert)
        if stufe and not (regel.pk and Ausloesung.objects.filter(regel=regel, schueler=m.schueler, zeitraum=schluessel,
                                                                 stufe__gte=stufe).exists()):
            ergebnis.append({"schueler": m.schueler, "klasse": m.gruppe, "wert": wert})
    return sorted(ergebnis, key=lambda e: (e["klasse"].name, e["schueler"].person.nachname))


def regel_anwenden(regel, benachrichtigen=False, stichtag=None):
    """Nach dem Anlegen/Ändern: bereits überschrittene Fälle benachrichtigen oder still vormerken."""
    stichtag = stichtag or timezone.localdate()
    n = 0
    if not regel.aktiv:
        return 0
    for e in betroffene(regel, stichtag):
        if regel_pruefen(regel, e["schueler"], stichtag, still=not benachrichtigen):
            n += 1
    return n
