"""Wer darf was: Schuljahreswechsel und Abgänge (Verwaltung), Löschfristen (Schulleitung und IT)."""
from portal.rechte import _in_gruppen, ist_it, ist_schulleitung, ist_verwaltung
from portal import rollen as R


def darf_schuljahre(user) -> bool:
    """Schuljahre anlegen, Schuljahreswechsel vorbereiten und durchführen, Abgänge erfassen."""
    return ist_verwaltung(user) and user.has_perm("laufbahn.change_schuljahreswechsel")


def darf_abgang(user) -> bool:
    return ist_verwaltung(user) and user.has_perm("laufbahn.add_laufbahnereignis")


def darf_archiv(user) -> bool:
    return (ist_verwaltung(user) or ist_it(user)) and user.has_perm("stammdaten.view_schuelerprofil")


def darf_fristen_sehen(user) -> bool:
    return _in_gruppen(user, {R.SCHULLEITUNG, R.IT, R.VERWALTUNGSLEITUNG}) and user.has_perm("laufbahn.view_loeschfrist")


def darf_fristen_aendern(user) -> bool:
    return (ist_schulleitung(user) or ist_it(user)) and user.has_perm("laufbahn.change_loeschfrist")


def darf_loeschen(user) -> bool:
    return (ist_schulleitung(user) or ist_it(user)) and user.has_perm("laufbahn.loeschen_archiv")
