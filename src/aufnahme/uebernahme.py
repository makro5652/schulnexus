"""
Übernahme einer Anmeldung in die regulären Stammdaten.

Aus der Anmeldung entstehen in einem Schritt (eine Transaktion):
  • Person + Schülerprofil (mit neuer Schülernummer), bisherige Schule, Schullaufbahn
  • für jeden Kontakt eine Person + Elternprofil + Beziehung – oder die Verknüpfung mit einer
    bereits vorhandenen Person (z. B. Eltern von Geschwisterkindern)
  • die Mitgliedschaft in der vorläufigen Klasse ab dem Eintrittsdatum
  • Kopien der ausgewählten Unterlagen als Anhänge der Schülerakte (mit ursprünglichem Upload-Datum)
  • ein Protokoll der Checkliste als Anhang (nur Verwaltung)
Die Anmeldung bleibt als abgeschlossene Akte erhalten und verweist auf die neue Schülerin / den neuen Schüler.
"""
from django.core.exceptions import ValidationError
from django.core.files import File
from django.db import transaction
from django.db.models import Q
from django.utils import formats, timezone
from django.utils.translation import gettext, gettext_lazy as _

from portal.zuordnung import hinzufuegen
from stammdaten.models import (
    Beziehung, Dokument, Elternprofil, Laufbahnabschnitt, Person, Schuelerprofil, VorherigeSchule,
)

from .models import Anmeldung


def naechste_schuelernummer():
    """Höchste rein numerische Schülernummer + 1; sonst Jahr + 001 (z. B. 2026001)."""
    zahlen = [int(n) for n in Schuelerprofil.objects.values_list("schuelernummer", flat=True) if n.isdigit()]
    if zahlen:
        kandidat = max(zahlen) + 1
    else:
        kandidat = int(f"{timezone.localdate().year}001")
    while Schuelerprofil.objects.filter(schuelernummer=str(kandidat)).exists():
        kandidat += 1
    return str(kandidat)


# ---------------------------------------------------------------- Prüfungen vor der Übernahme

def moegliche_dubletten(a):
    """Vorhandene Personen mit gleichem Namen und Geburtsdatum (oder gleichem vollständigem Namen)."""
    q = Q(vorname__iexact=a.vorname.strip(), nachname__iexact=a.nachname.strip())
    if a.geburtsdatum:
        q |= Q(nachname__iexact=a.nachname.strip(), geburtsdatum=a.geburtsdatum)
    return list(Person.objects.filter(q).select_related("schueler")[:5])


def kontakt_kandidaten(k):
    """Vorhandene Personen, die derselbe Elternteil sein könnten (E-Mail oder Name)."""
    q = Q(vorname__iexact=k.vorname.strip(), nachname__iexact=k.nachname.strip())
    if k.email:
        q |= Q(email__iexact=k.email.strip())
    return list(Person.objects.filter(q).filter(Q(elternprofil__isnull=False) | Q(kinder_beziehungen__isnull=False))
                .distinct().order_by("nachname", "vorname")[:5])


def hindernisse(a):
    """Gründe, warum die Übernahme (noch) nicht möglich ist."""
    gruende = []
    if a.status != Anmeldung.ZUGESAGT:
        gruende.append(gettext("Die Übernahme ist erst nach einer Zusage möglich (Status „Zugesagt“)."))
    offen = a.fortschritt()["offen_pflicht"]
    if offen:
        gruende.append(gettext("Offene Pflichtpunkte der Checkliste: %(punkte)s")
                       % {"punkte": ", ".join(p.lokal_text for p in offen)})
    if not a.geburtsdatum:
        gruende.append(gettext("Das Geburtsdatum fehlt."))
    return gruende


def hinweise(a):
    """Keine Hindernisse, aber vor der Übernahme zu beachten."""
    h = []
    if not a.vorlaeufige_klasse_id:
        h.append(gettext("Keine vorläufige Klasse – die Klassenzuordnung kann später unter „Klassen und Gruppen“ erfolgen."))
    if not a.kontakte.exists():
        h.append(gettext("Es sind keine Erziehungsberechtigten erfasst."))
    if a.bildungsgang_id and a.jahrgang:
        bg = a.bildungsgang
        if (bg.jahrgang_von and a.jahrgang < bg.jahrgang_von) or (bg.jahrgang_bis and a.jahrgang > bg.jahrgang_bis):
            h.append(gettext("Jahrgang %(jg)s passt nicht zum Bildungsgang %(bg)s – die Schullaufbahn wird nicht angelegt.")
                     % {"jg": a.jahrgang, "bg": bg})
    elif not a.bildungsgang_id:
        h.append(gettext("Kein Bildungsgang angegeben – die Schullaufbahn wird nicht angelegt."))
    return h


# ---------------------------------------------------------------- Übernahme

def _datei_kopieren(quelle, person, user, gespeichert):
    dok = Dokument(person=person, kategorie=quelle.kategorie, titel=quelle.titel, notiz=quelle.notiz,
                   zugriffsstufe=quelle.zugriffsstufe, hochgeladen_von=quelle.hochgeladen_von or user)
    with quelle.datei.open("rb") as f:
        dok.datei.save(quelle.originalname or quelle.datei.name.rsplit("/", 1)[-1], File(f), save=False)
    gespeichert.append(dok.datei)
    dok.originalname, dok.groesse, dok.inhaltstyp = quelle.originalname, quelle.groesse, quelle.inhaltstyp
    dok.save()
    Dokument.objects.filter(pk=dok.pk).update(hochgeladen_am=quelle.hochgeladen_am)
    return dok


def _checklistenprotokoll(a):
    zeilen = [gettext("Aufnahmecheckliste der Anmeldung %(nr)s (Eingang %(datum)s)")
              % {"nr": a.nummer, "datum": formats.date_format(a.eingang, "SHORT_DATE_FORMAT")}, ""]
    for p in a.punkte.select_related("erledigt_von"):
        if p.erledigt:
            wer = p.erledigt_von.get_full_name() or p.erledigt_von.get_username() if p.erledigt_von else ""
            status = gettext("erledigt am %(datum)s von %(wer)s") % {
                "datum": formats.date_format(timezone.localtime(p.erledigt_am), "SHORT_DATE_FORMAT") if p.erledigt_am else "",
                "wer": wer or "—"}
        else:
            status = gettext("nicht erledigt")
        zeilen.append(f"[{'x' if p.erledigt else ' '}] {p.text} – {status}" + (f" ({p.bemerkung})" if p.bemerkung else ""))
    return "\n".join(zeilen)


def uebernehmen(a, user, kontakt_personen=None, dateien_uebernehmen=True):
    """
    Führt die Übernahme aus und gibt das neue Schülerprofil zurück.
    `kontakt_personen`: {kontakt_pk: Person} für Kontakte, die mit vorhandenen Personen verknüpft werden sollen.
    Wirft ValidationError, wenn Hindernisse bestehen.
    """
    gruende = hindernisse(a)
    if gruende:
        raise ValidationError(gruende)
    kontakt_personen = kontakt_personen or {}
    gespeichert = []
    try:
        with transaction.atomic():
            a = Anmeldung.objects.select_for_update().get(pk=a.pk)
            if a.status != Anmeldung.ZUGESAGT:
                raise ValidationError(gettext("Diese Anmeldung wurde bereits übernommen."))
            eintritt = a.eintritt
            person = Person.objects.create(
                vorname=a.vorname, nachname=a.nachname, rufname=a.rufname, geschlecht=a.geschlecht,
                geburtsdatum=a.geburtsdatum, geburtsort=a.geburtsort, geburtsland=a.geburtsland,
                staatsangehoerigkeiten=a.staatsangehoerigkeiten, strasse=a.strasse, postfach=a.postfach, plz=a.plz,
                ort=a.ort, land=a.land,
            )
            bemerkung = gettext("Aufgenommen über Anmeldung %(nr)s.") % {"nr": a.nummer}
            if a.deutschkenntnisse:
                bemerkung += " " + gettext("Deutschkenntnisse bei Anmeldung: %(dk)s.") % {"dk": a.deutschkenntnisse}
            schueler = Schuelerprofil.objects.create(
                person=person, schuelernummer=naechste_schuelernummer(), eintrittsdatum=eintritt,
                eintritt_jahrgang=a.jahrgang, status="aktiv", muttersprache=a.muttersprache,
                familiensprache=a.familiensprache, daz=a.daz, religionsunterricht=a.religionsunterricht,
                bemerkungen=bemerkung,
            )
            if a.vorherige_schule:
                VorherigeSchule.objects.create(
                    schueler=schueler, name=a.vorherige_schule, ort=a.vorherige_schule_ort, land=a.vorherige_schule_land,
                    schulform=a.vorherige_schulform, letzter_jahrgang=a.letzter_jahrgang,
                )
            if a.bildungsgang_id and a.jahrgang:
                lb = Laufbahnabschnitt(schueler=schueler, schuljahr=a.schuljahr, jahrgang=a.jahrgang, bildungsgang=a.bildungsgang,
                                       stammklasse=a.vorlaeufige_klasse,
                                       von=eintritt if eintritt > a.schuljahr.beginn else None)
                try:
                    lb.full_clean()
                    lb.save()
                except ValidationError:
                    pass  # wird vorher als Hinweis angezeigt

            for k in a.kontakte.all():
                p = kontakt_personen.get(k.pk)
                if p is None:
                    adresse = {f: getattr(a if k.adresse_wie_kind else k, f) for f in ("strasse", "postfach", "plz", "ort", "land")}
                    p = Person.objects.create(
                        anrede=k.anrede, titel=k.titel, vorname=k.vorname, nachname=k.nachname, email=k.email,
                        telefon=k.telefon, mobil=k.mobil, sprache=k.sprache, **adresse,
                    )
                Elternprofil.objects.get_or_create(person=p, defaults={
                    "beruf": k.beruf, "arbeitgeber": k.arbeitgeber, "korrespondenzweg": k.korrespondenzweg})
                Beziehung.objects.get_or_create(schueler=schueler, person=p, defaults={
                    "art": k.art, "sorgerecht": k.sorgerecht, "auskunftsrecht": k.sorgerecht,
                    "abholberechtigt": k.abholberechtigt, "notfallkontakt": k.notfallkontakt,
                    "rechnungsempfaenger": k.rechnungsempfaenger})
                k.person = p
                k.save(update_fields=["person"])

            if a.vorlaeufige_klasse_id:
                hinzufuegen(a.vorlaeufige_klasse, [schueler], eintritt)

            if dateien_uebernehmen:
                for d in a.dateien.filter(uebernehmen=True).order_by("hochgeladen_am", "pk"):
                    try:
                        _datei_kopieren(d, person, user, gespeichert)
                    except FileNotFoundError:
                        continue
            if a.punkte.exists():
                Dokument.objects.create(
                    person=person, kategorie="vertrag", zugriffsstufe="verwaltung", hochgeladen_von=user,
                    titel=gettext("Aufnahmecheckliste %(nr)s") % {"nr": a.nummer}, notiz=_checklistenprotokoll(a),
                )

            a.status = Anmeldung.UEBERNOMMEN
            a.status_seit = timezone.localdate()
            a.schueler = schueler
            a.uebernommen_am = timezone.now()
            a.uebernommen_von = user
            a.save()
            return schueler
    except Exception:
        # Bereits kopierte Dateien wieder entfernen, wenn die Transaktion zurückgerollt wurde.
        for f in gespeichert:
            try:
                f.storage.delete(f.name)
            except OSError:
                pass
        raise


UEBERNAHME_TEXT = _("Schüler:in, Erziehungsberechtigte, Klassenzuordnung und Unterlagen werden in die Stammdaten übernommen.")
