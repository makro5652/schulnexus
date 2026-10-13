"""Zentrale Rechteprüfung. Rollen werden als Django-Benutzergruppen abgebildet."""

VERWALTUNGSGRUPPEN = {"Verwaltung", "Schulleitung"}
PERSONALGRUPPEN = {"Personalverwaltung", "Schulleitung"}


def ist_verwaltung(user) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=VERWALTUNGSGRUPPEN).exists()


def ist_personalverwaltung(user) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=PERSONALGRUPPEN).exists()


def darf_unterricht_sehen(user, unterricht) -> bool:
    if ist_verwaltung(user):
        return True
    person = getattr(user, "person", None)
    if person is None:
        return False
    if unterricht.lehrkraft.person_id == person.pk:
        return True
    # Klassenleitung darf die Noten der eigenen Stammklasse einsehen.
    return unterricht.gruppe.leitung_id is not None and unterricht.gruppe.leitung.person_id == person.pk
