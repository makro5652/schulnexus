"""Rechte rund um Noteneingabe, Bewertungsstruktur und Leistungsvorgaben (ab 0.4.7.0)."""
from portal.rechte import ist_schulleitung, ist_stellvertretung, koordinierte_jahrgaenge, personal_von

ALLE_JAHRGAENGE = set(range(1, 14))


def ist_eigener_unterricht(user, unterricht) -> bool:
    p = personal_von(user)
    return p is not None and unterricht.lehrkraft_id == p.pk


def darf_noten_eintragen(user, unterricht) -> bool:
    """Noten und Bewertungsstruktur: die unterrichtende Lehrkraft, außerdem Schulleitung und IT."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or ist_schulleitung(user):
        return True
    return ist_eigener_unterricht(user, unterricht) and user.has_perm("noten.change_note") \
        and user.has_perm("noten.add_leistungsnachweis")


def vorgaben_jahrgaenge(user) -> set:
    """Jahrgänge, für die die Person Leistungsvorgaben anlegen darf."""
    if not user.is_authenticated or not user.has_perm("noten.add_leistungsvorgabe"):
        return set()
    if user.is_superuser or ist_schulleitung(user) or ist_stellvertretung(user):
        return set(ALLE_JAHRGAENGE)
    return set(koordinierte_jahrgaenge(user))


def darf_vorgaben_verwalten(user) -> bool:
    return bool(vorgaben_jahrgaenge(user))


def darf_vorgabe_aendern(user, vorgabe) -> bool:
    return user.has_perm("noten.change_leistungsvorgabe") and set(vorgabe.jahrgaenge) <= vorgaben_jahrgaenge(user)


def darf_vorgaben_sehen(user) -> bool:
    return user.is_authenticated and user.has_perm("noten.view_leistungsvorgabe")


def darf_klausurregeln(user) -> bool:
    """Klausurregeln je Fach (ab 0.4.8.0): Schulleitung und Stellvertretung (nach Beschluss der Fachkonferenz)."""
    return user.is_authenticated and (user.is_superuser or ist_schulleitung(user) or ist_stellvertretung(user))


def darf_noten_sperren(user, jahrgang) -> bool:
    """Notensperre setzen oder aufheben: Schulleitung, Stellvertretung, Stufenkoordination für ihre Jahrgänge."""
    if not user.is_authenticated:
        return False
    if user.is_superuser or ist_schulleitung(user) or ist_stellvertretung(user):
        return True
    return jahrgang is not None and jahrgang in koordinierte_jahrgaenge(user)


def ist_koordination(user) -> bool:
    return bool(koordinierte_jahrgaenge(user)) if user.is_authenticated else False
