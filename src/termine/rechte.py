"""Zeilenweise Rechte für Kalender, Räume und Sprechtage."""
from portal.rechte import (
    _in_gruppen, ist_it, ist_schulleitung, ist_stellvertretung, ist_verwaltung, koordinierte_stufen, personal_von,
)
from portal import rollen as R


def ist_beschaeftigt(user):
    return user.is_authenticated and (personal_von(user) is not None or user.is_staff)


def darf_kalender_sehen(user):
    return ist_beschaeftigt(user) and user.has_perm("termine.view_termin")


def darf_kalender_bearbeiten(user):
    """Termine eintragen: Verwaltung, Schulleitung, Stellvertretung, Stufenkoordination."""
    return user.has_perm("termine.add_termin") and (
        ist_verwaltung(user) or ist_stellvertretung(user) or ist_it(user) or bool(koordinierte_stufen(user)))


def darf_termin_aendern(user, termin):
    if not user.has_perm("termine.change_termin"):
        return False
    return ist_verwaltung(user) or ist_stellvertretung(user) or ist_it(user) or termin.erstellt_von_id == user.pk


def darf_raeume_verwalten(user):
    return user.has_perm("termine.change_raum") and (ist_verwaltung(user) or ist_stellvertretung(user) or ist_it(user))


def darf_raum_buchen(user):
    return ist_beschaeftigt(user) and user.has_perm("termine.add_raumbuchung")


def darf_buchung_loeschen(user, buchung):
    if buchung.sprechtag_id or buchung.termin_id:
        return darf_raeume_verwalten(user)
    return buchung.gebucht_von_id == user.pk or darf_raeume_verwalten(user)


def darf_sprechtage_planen(user):
    """Zeitraster, Teilnehmende und Buchungszeitraum festlegen: Stellvertretende Schulleitung und Schulleitung."""
    return user.has_perm("termine.change_sprechtag") and (ist_stellvertretung(user) or ist_schulleitung(user) or ist_it(user))


def darf_fuer_alle_buchen(user):
    """Termine für beliebige Lehrkräfte eintragen oder absagen: Planung und Sekretariat."""
    return user.has_perm("termine.add_gespraechstermin") and (darf_sprechtage_planen(user) or ist_verwaltung(user))


def eigene_teilnahme(user, sprechtag):
    p = personal_von(user)
    return sprechtag.teilnahmen.filter(lehrkraft=p).first() if p else None


def darf_teilnahme_bearbeiten(user, teilnahme):
    p = personal_von(user)
    return darf_sprechtage_planen(user) or (p is not None and teilnahme.lehrkraft_id == p.pk and user.has_perm("termine.change_teilnahme"))


def ist_eltern(user):
    return user.is_authenticated and _in_gruppen(user, {R.ELTERN}) and not user.is_superuser
