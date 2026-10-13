from django.conf import settings

from config.version import VERSION
from stammdaten.models import Schuljahr


def schulinfo(request):
    return {
        "SCHULNAME": settings.SCHULNAME,
        "AKTUELLES_SCHULJAHR": Schuljahr.aktuelles(),
        "VERSION": VERSION,
        "SPRACHEN": settings.LANGUAGES,
        "DOKUMENT_MAX_MB": settings.DOKUMENT_MAX_MB,
    }
