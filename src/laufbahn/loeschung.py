"""
Löschfristen für das Archiv (abgegangene Schüler:innen).

Je Datenkategorie gilt eine Aufbewahrungsfrist ab dem Austritt (bzw. ab dem Ende des Kalenderjahres des Austritts).
Ist sie abgelaufen, erinnert die Startseite die Schulleitung; gelöscht wird erst nach Bestätigung. Gelöscht werden
die Einträge selbst, ihr Änderungsprotokoll und zugehörige Dateien. Der Nachweis (Löschvorgang) enthält nur
Schülernummer, Kategorie, Anzahl, Datum und Person.

Hinweis: Bereits erstellte Modulsicherungen enthalten gelöschte Daten weiterhin, bis sie selbst gelöscht werden.
"""
from datetime import date, timedelta

from django.core.files.storage import default_storage
from django.db import models, transaction
from django.db.models.deletion import Collector
from django.utils import timezone
from django.utils.translation import gettext

from stammdaten.models import Person, Schuelerprofil

from .models import Loeschfrist, Loeschvorgang

KATEGORIEN = [k for k, _n in Loeschfrist.KATEGORIEN]


def fristen_sicherstellen():
    """Legt fehlende Kategorien mit den Vorschlagswerten an (aktiv)."""
    vorhanden = set(Loeschfrist.objects.values_list("kategorie", flat=True))
    for k in KATEGORIEN:
        if k not in vorhanden:
            Loeschfrist.objects.create(kategorie=k, jahre=Loeschfrist.VORSCHLAG[k],
                                       hinweis=gettext("Vorschlagswert – bitte durch die Schulleitung festlegen."))
    return sorted(Loeschfrist.objects.all(), key=lambda f: f.reihenfolge)


def _plus_jahre(d, jahre):
    try:
        return d.replace(year=d.year + jahre)
    except ValueError:                       # 29. Februar
        return d.replace(year=d.year + jahre, day=28)


def faellig_am(frist, austritt):
    if not austritt:
        return None
    start = date(austritt.year, 12, 31) if frist.bezug == "jahresende" else austritt
    return _plus_jahre(start, frist.jahre)


# ---------------------------------------------------------------- Was gehört zu welcher Kategorie

def querysets(kategorie, s):
    from aufnahme.models import Anmeldung
    from elternkontakt.models import Ausloesung, Gespraech
    from fehlzeiten.models import Fehlzeit
    from foerderung.models import Foerdereintrag, Foerderplan, Nachteilsausgleich
    from nachmittag.models import AGWahl, AGZuteilung
    from noten.models import Note, Zeugnisnote
    from stammdaten.models import Beziehung, Dokument, Einwilligung, Gesundheitsangaben
    from zeugnisse.models import Beschluss, Zeugnis

    p = s.person
    return {
        "fehlzeiten": [Fehlzeit.objects.filter(schueler=s), AGWahl.objects.filter(schueler=s), AGZuteilung.objects.filter(schueler=s)],
        "elternkontakt": [Gespraech.objects.filter(schueler=s), Ausloesung.objects.filter(schueler=s)],
        "gesundheit": [Gesundheitsangaben.objects.filter(schueler=s)],
        "foerderung": [Foerderplan.objects.filter(schueler=s), Foerdereintrag.objects.filter(schueler=s),
                       Nachteilsausgleich.objects.filter(schueler=s)],
        "noten": [Note.objects.filter(schueler=s), Zeugnisnote.objects.filter(schueler=s)],
        "dokumente": [Dokument.objects.filter(person=p)],
        "aufnahme": [Anmeldung.objects.filter(schueler=s)],
        "zeugnisse": [Zeugnis.objects.filter(schueler=s).exclude(art=Zeugnis.ABGANG), Beschluss.objects.filter(schueler=s)],
        "kontakte": [Beziehung.objects.filter(schueler=s), Einwilligung.objects.filter(schueler=s)],
        "akte": [Person.objects.filter(pk=p.pk)],
    }[kategorie]


KONTAKTFELDER_PERSON = ["strasse", "postfach", "plz", "ort", "email", "telefon", "mobil", "telefon_dienstlich", "notizen"]
KONTAKTFELDER_SCHUELER = ["lebt_bei", "schulweg", "buslinie", "abholhinweise", "bemerkungen"]


def anzahl(kategorie, s):
    n = sum(qs.count() for qs in querysets(kategorie, s))
    if kategorie == "kontakte":
        p = s.person
        n += sum(1 for f in KONTAKTFELDER_PERSON if getattr(p, f)) + sum(1 for f in KONTAKTFELDER_SCHUELER if getattr(s, f))
        n += 1 if p.benutzer_id else 0
    return n


# ---------------------------------------------------------------- Löschen

def _endgueltig(querysets_):
    """Löscht mit allen abhängigen Einträgen, deren Änderungsprotokoll und Dateien. Rückgabe: Anzahl Einträge."""
    collector = Collector(using="default")
    for qs in querysets_:
        collector.collect(qs)                      # ProtectedError, falls etwas geschützt ist
    dateien, historie, n = [], [], 0

    def merken(model, objekte):
        nonlocal n
        pks = []
        for o in objekte:
            pks.append(o.pk)
            for f in model._meta.concrete_fields:
                if isinstance(f, models.FileField):
                    name = getattr(o, f.attname)
                    name = getattr(name, "name", name)
                    if name:
                        dateien.append((f.storage if hasattr(f, "storage") else default_storage, name))
        n += len(pks)
        verlauf = getattr(model, "history", None)
        if verlauf is not None and hasattr(verlauf, "model") and pks:
            historie.append((verlauf.model, pks))

    for model, objekte in collector.data.items():
        merken(model, objekte)
    for qs in collector.fast_deletes:
        merken(qs.model, list(qs))
    collector.delete()
    for hm, pks in historie:
        hm.objects.filter(id__in=pks).delete()
    for speicher, name in dateien:
        try:
            speicher.delete(name)
        except Exception:                          # Datei fehlt bereits – unkritisch
            pass
    return n


def _kontakte_anonymisieren(s):
    """Kontaktdaten leeren, Elternverknüpfungen lösen, verwaiste Elternpersonen und das Schülerkonto löschen."""
    from stammdaten.models import Beziehung, Einwilligung

    eltern = list(Person.objects.filter(kinder_beziehungen__schueler=s).distinct())
    n = _endgueltig([Einwilligung.objects.filter(schueler=s), Beziehung.objects.filter(schueler=s)])
    from portal.rollen import ELTERN

    for e in eltern:
        konto = e.benutzer
        nur_eltern = konto is None or (not konto.is_staff and not konto.groups.exclude(name=ELTERN).exists())
        if e.kinder_beziehungen.exists() or hasattr(e, "personal") or hasattr(e, "schueler") or not nur_eltern:
            continue
        try:
            n += _endgueltig([Person.objects.filter(pk=e.pk)])
        except models.ProtectedError:
            continue
        if konto:
            konto.delete()
    p = s.person
    for f in KONTAKTFELDER_PERSON:
        if getattr(p, f):
            setattr(p, f, "")
            n += 1
    for f in KONTAKTFELDER_SCHUELER:
        if getattr(s, f):
            setattr(s, f, "")
            n += 1
    konto = p.benutzer
    if konto:
        p.benutzer = None
        p.save()
        konto.delete()
        n += 1
    p.save()
    s.save()
    # Frühere Fassungen (mit Adressen) aus dem Änderungsprotokoll entfernen
    Person.history.filter(id=p.pk).delete()
    Schuelerprofil.history.filter(id=s.pk).delete()
    return n


@transaction.atomic
def loeschen(s, kategorie, user=None):
    """Löscht eine Kategorie für eine Schülerin / einen Schüler im Archiv und schreibt den Nachweis."""
    if not s.archiviert:
        raise ValueError("nur Archiv")
    nummer = s.schuelernummer
    if kategorie == "kontakte":
        n = _kontakte_anonymisieren(s)
    elif kategorie == "akte":
        n = 0
        for k in KATEGORIEN[:-1]:
            if k == "kontakte":
                n += _kontakte_anonymisieren(s)
            else:
                n += _endgueltig(querysets(k, s))
            s.refresh_from_db()
        n += _endgueltig(querysets("akte", s))
        Loeschvorgang.objects.filter(schuelernummer=nummer).exclude(kategorie="akte").update(status=Loeschvorgang.ERLEDIGT)
    else:
        n = _endgueltig(querysets(kategorie, s))
    Loeschvorgang.objects.update_or_create(schuelernummer=nummer, kategorie=kategorie, defaults={
        "status": Loeschvorgang.ERLEDIGT if n else Loeschvorgang.LEER, "anzahl": n, "bis": None, "grund": "", "von": user})
    from sicherung.models import Protokoll
    Protokoll.schreiben(user, "loeschung", gettext("Löschfrist: %(k)s für Schülernummer %(nr)s gelöscht (%(n)s Einträge)")
                        % {"k": dict(Loeschfrist.KATEGORIEN)[kategorie], "nr": nummer, "n": n})
    return n


def aufschieben(s, kategorie, bis, grund, user=None):
    Loeschvorgang.objects.update_or_create(schuelernummer=s.schuelernummer, kategorie=kategorie, defaults={
        "status": Loeschvorgang.AUFGESCHOBEN, "bis": bis, "grund": grund[:250], "von": user, "anzahl": 0})


# ---------------------------------------------------------------- Fälligkeiten

def faellige(heute=None, vorlauf_tage=0, mit_anzahl=False, schueler=None):
    """
    Liste der fälligen (bzw. in `vorlauf_tage` fällig werdenden) Löschungen:
    [{"schueler", "frist", "faellig", "anzahl", "vorgang"}]. Erledigte und laufende Aufschübe fehlen.
    """
    heute = heute or timezone.localdate()
    grenze = heute + timedelta(days=vorlauf_tage)
    fristen = [f for f in Loeschfrist.objects.filter(aktiv=True)]
    if not fristen:
        return []
    archiv = Schuelerprofil.objects.filter(status="abgang", austrittsdatum__isnull=False).select_related("person")
    if schueler is not None:
        archiv = archiv.filter(pk=schueler.pk)
    kuerzeste = min(f.jahre for f in fristen)
    archiv = archiv.filter(austrittsdatum__lte=date(grenze.year - kuerzeste, 12, 31))
    vorgaenge = {(v.schuelernummer, v.kategorie): v for v in Loeschvorgang.objects.filter(
        schuelernummer__in=archiv.values("schuelernummer"))}
    liste = []
    for s in archiv:
        for f in fristen:
            am = faellig_am(f, s.austrittsdatum)
            if am is None or am > grenze:
                continue
            v = vorgaenge.get((s.schuelernummer, f.kategorie))
            if v and (v.status in (Loeschvorgang.ERLEDIGT, Loeschvorgang.LEER) or (v.bis and v.bis >= heute)):
                continue
            eintrag = {"schueler": s, "frist": f, "faellig": am, "vorgang": v, "ueberfaellig": am <= heute}
            if mit_anzahl:
                eintrag["anzahl"] = anzahl(f.kategorie, s)
                if eintrag["anzahl"] == 0 and f.kategorie != "akte":
                    Loeschvorgang.objects.update_or_create(schuelernummer=s.schuelernummer, kategorie=f.kategorie,
                                                           defaults={"status": Loeschvorgang.LEER, "anzahl": 0})
                    continue
            liste.append(eintrag)
    liste.sort(key=lambda e: (e["faellig"], e["schueler"].person.nachname, e["frist"].reihenfolge))
    return liste
