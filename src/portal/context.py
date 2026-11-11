from django.conf import settings
from django.utils.functional import SimpleLazyObject

from config.version import VERSION
from stammdaten.models import Schuljahr

from .models import DESIGNS, design_gruppen


def darf_portal_nutzen(user):
    """Das Portal ist nur für Beschäftigte: Verwaltung und Lehrkräfte (Konto mit Personalakte oder Verwaltungszugang)."""
    if not user.is_authenticated or not user.is_active:
        return False
    if user.is_staff or user.is_superuser:
        return True
    person = getattr(user, "person", None)
    return person is not None and hasattr(person, "personal")


def aktuelles_design(request):
    """Design der angemeldeten Person, sonst aus dem Cookie (Anmeldeseite), sonst Standard."""
    from .models import DESIGN_COOKIE

    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        einstellung = getattr(user, "einstellung", None)
        if einstellung is not None:
            return einstellung.design
    design = request.COOKIES.get(DESIGN_COOKIE)
    return design if design in dict(DESIGNS) else "standard"


def schulinfo(request):
    daten = {
        "SCHULNAME": settings.SCHULNAME,
        "AKTUELLES_SCHULJAHR": Schuljahr.aktuelles(),
        "VERSION": VERSION,
        "SPRACHEN": settings.LANGUAGES,
        "DOKUMENT_MAX_MB": settings.DOKUMENT_MAX_MB,
        "DESIGN": aktuelles_design(request),
        "DESIGNS": DESIGNS,
        "DESIGN_GRUPPEN": design_gruppen(),
    }
    user = getattr(request, "user", None)
    if user is not None and darf_portal_nutzen(user):
        from .navigation import menueband

        daten["MENUEBAND"] = SimpleLazyObject(lambda: menueband(request))
    return daten
