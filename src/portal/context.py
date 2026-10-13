from django.conf import settings
from django.utils.functional import SimpleLazyObject

from config.version import VERSION
from stammdaten.models import Schuljahr


def darf_portal_nutzen(user):
    """Das Portal ist nur für Beschäftigte: Verwaltung und Lehrkräfte (Konto mit Personalakte oder Verwaltungszugang)."""
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_staff or user.is_superuser:
        return True
    person = getattr(user, "person", None)
    return person is not None and hasattr(person, "personal")


def schulinfo(request):
    daten = {
        "SCHULNAME": settings.SCHULNAME,
        "AKTUELLES_SCHULJAHR": Schuljahr.aktuelles(),
        "VERSION": VERSION,
        "SPRACHEN": settings.LANGUAGES,
        "DOKUMENT_MAX_MB": settings.DOKUMENT_MAX_MB,
    }
    user = getattr(request, "user", None)
    if user is not None and darf_portal_nutzen(user):
        from .navigation import menueband

        daten["MENUEBAND"] = SimpleLazyObject(lambda: menueband(request))
    return daten
