"""Anlegen von Nachrichten, persönliche Links und E-Mail-Zustellung an Eltern."""
import logging
from datetime import timedelta
from hmac import compare_digest

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMessage
from django.db import transaction
from django.urls import reverse
from django.utils import formats, timezone, translation
from django.utils.translation import gettext as _

from .models import Beitrag, Empfaenger, Gespraech

log = logging.getLogger(__name__)
SALZ = "elternkontakt.link"


# ---------------------------------------------------------------- Links

def link_token(empfaenger):
    return signing.dumps([empfaenger.pk, empfaenger.schluessel], salt=SALZ, compress=True)


def link_fuer(empfaenger):
    return settings.ELTERN_LINK_BASIS + reverse("eltern_nachricht", args=[link_token(empfaenger)])


class LinkUngueltig(Exception):
    pass


def empfaenger_aus_token(token):
    """Prüft Signatur, Ablauf und Schlüssel; wirft LinkUngueltig (ohne Grund – keine Hinweise für Ratende)."""
    try:
        pk, schluessel = signing.loads(token, salt=SALZ, max_age=timedelta(days=settings.ELTERN_LINK_TAGE))
        e = Empfaenger.objects.select_related("gespraech", "gespraech__schueler__person", "person").get(pk=pk)
    except (signing.BadSignature, ValueError, TypeError, Empfaenger.DoesNotExist):
        raise LinkUngueltig from None
    if not compare_digest(str(schluessel), e.schluessel):
        raise LinkUngueltig
    return e


# ---------------------------------------------------------------- Empfänger:innen

def kontakte_fuer(schueler):
    """Mögliche Empfänger:innen: Kontaktpersonen mit Auskunftsrecht; vorausgewählt sind Sorgeberechtigte."""
    return (schueler.beziehungen.filter(auskunftsrecht=True).select_related("person")
            .order_by("-sorgerecht", "art", "person__nachname"))


def standard_empfaenger(schueler):
    return [b for b in kontakte_fuer(schueler) if b.sorgerecht]


# ---------------------------------------------------------------- Zustellung

def _sprache(person):
    return person.sprache if person.sprache in dict(settings.LANGUAGES) else settings.LANGUAGE_CODE


def mail_inhalt(empfaenger, beitrag=None):
    """Betreff und Text der E-Mail in der bevorzugten Sprache der Empfängerin / des Empfängers."""
    g = empfaenger.gespraech
    with translation.override(_sprache(empfaenger.person)):
        kind = g.schueler.person.rufname or g.schueler.person.vorname
        gueltig = formats.date_format(timezone.localdate() + timedelta(days=settings.ELTERN_LINK_TAGE), "SHORT_DATE_FORMAT")
        betreff = _("%(schule)s: Neue Nachricht zu %(kind)s") % {"schule": settings.SCHULNAME, "kind": kind}
        zeilen = [
            _("Guten Tag %(name)s,") % {"name": empfaenger.person.anzeigename},
            _("die Schule hat Ihnen eine Nachricht zu %(kind)s geschickt. Bitte öffnen Sie sie über Ihren persönlichen Link:")
            % {"kind": kind},
            link_fuer(empfaenger),
            _("Der Link ist bis %(datum)s gültig und nur für Sie bestimmt. Bitte leiten Sie ihn nicht weiter.") % {"datum": gueltig},
        ]
        if g.bestaetigung_erbeten and not empfaenger.bestaetigt_am:
            zeilen.insert(3, _("Die Schule bittet um eine Bestätigung über diesen Link."))
        if settings.ELTERN_EMAIL_INHALT:
            b = beitrag or g.beitraege.order_by("-erstellt_am").first()
            if b:
                zeilen += ["—", g.titel(), b.anzeigetext()]
        zeilen += ["", settings.SCHULNAME, _("Diese E-Mail wurde automatisch versendet.")]
    return betreff, "\n\n".join(z for z in zeilen if z is not None)


def zustellen(empfaenger, beitrag=None):
    """Versendet die Benachrichtigung (falls aktiviert) und vermerkt den Status."""
    email = (empfaenger.person.email or "").strip()
    empfaenger.email = email
    if not email:
        empfaenger.versand_status = Empfaenger.OHNE_EMAIL
    elif not settings.ELTERN_EMAIL_VERSAND:
        empfaenger.versand_status = Empfaenger.WARTET
    else:
        betreff, text = mail_inhalt(empfaenger, beitrag)
        try:
            EmailMessage(betreff, text, settings.DEFAULT_FROM_EMAIL, [email], headers={"Auto-Submitted": "auto-generated"}).send()
        except Exception as fehler:  # SMTP- und Netzwerkfehler sollen das Speichern nicht verhindern
            log.warning("Elternnachricht an %s nicht versendet: %s", empfaenger.pk, fehler)
            empfaenger.versand_status = Empfaenger.FEHLER
            empfaenger.versand_fehler = str(fehler)[:300]
        else:
            empfaenger.versand_status = Empfaenger.VERSENDET
            empfaenger.versendet_am = timezone.now()
            empfaenger.versand_fehler = ""
    empfaenger.save(update_fields=["email", "versand_status", "versendet_am", "versand_fehler"])


def alle_benachrichtigen(gespraech, beitrag=None):
    for e in gespraech.empfaenger.select_related("person"):
        transaction.on_commit(lambda e=e: zustellen(e, beitrag))


def postausgang_senden():
    """Wartende und fehlgeschlagene Zustellungen erneut versuchen (nach dem Einschalten des Versands)."""
    n = 0
    for e in Empfaenger.objects.filter(versand_status__in=[Empfaenger.WARTET, Empfaenger.FEHLER]).select_related("person", "gespraech"):
        zustellen(e)
        n += e.versand_status == Empfaenger.VERSENDET
    return n


# ---------------------------------------------------------------- Anlegen

@transaction.atomic
def gespraech_anlegen(schueler, personen, *, betreff="", text="", von=None, art=Gespraech.NACHRICHT,
                      bestaetigung=False, antworten=True, vorlage="", daten=None, zeugnis=None):
    """Legt Gespräch, ersten Beitrag und Empfänger:innen an; die Zustellung erfolgt nach dem Speichern."""
    jetzt = timezone.now()
    g = Gespraech.objects.create(
        schueler=schueler, art=art, betreff=betreff[:200], vorlage=vorlage, daten=daten or {}, bestaetigung_erbeten=bestaetigung,
        antworten_erlaubt=antworten, erstellt_von=von, zeugnis=zeugnis, letzte_aktivitaet=jetzt, schule_gelesen_am=jetzt)
    beitrag = Beitrag.objects.create(gespraech=g, text=text, vorlage=vorlage, daten=daten or {}, von_benutzer=von,
                                     ueber="schule" if von else "system", erstellt_am=jetzt)
    arten = {b.person_id: b.art for b in schueler.beziehungen.all()}
    for person in personen:
        Empfaenger.objects.create(gespraech=g, person=person, beziehung=arten.get(person.pk, ""))
    alle_benachrichtigen(g, beitrag)
    return g


@transaction.atomic
def antwort_der_schule(gespraech, text, von):
    jetzt = timezone.now()
    b = Beitrag.objects.create(gespraech=gespraech, text=text, von_benutzer=von, ueber="schule", erstellt_am=jetzt)
    gespraech.letzte_aktivitaet = jetzt
    gespraech.schule_gelesen_am = jetzt
    gespraech.save(update_fields=["letzte_aktivitaet", "schule_gelesen_am"])
    alle_benachrichtigen(gespraech, b)
    return b


@transaction.atomic
def antwort_der_eltern(empfaenger, text, ueber="link"):
    jetzt = timezone.now()
    g = empfaenger.gespraech
    b = Beitrag.objects.create(gespraech=g, text=text, von_person=empfaenger.person, ueber=ueber, erstellt_am=jetzt)
    g.letzte_aktivitaet = jetzt
    g.eltern_antwort_am = jetzt
    g.save(update_fields=["letzte_aktivitaet", "eltern_antwort_am"])
    if not empfaenger.gelesen_am:
        empfaenger.gelesen_am = jetzt
        empfaenger.save(update_fields=["gelesen_am"])
    return b


def beitraege_fuer_eltern(gespraech, person):
    """Eltern sehen die Beiträge der Schule und ihre eigenen – nicht die Antworten anderer Kontaktpersonen."""
    from django.db.models import Q

    return gespraech.beitraege.filter(Q(von_person__isnull=True) | Q(von_person=person)).select_related("von_benutzer__person", "von_person")
