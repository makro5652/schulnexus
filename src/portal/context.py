from django.conf import settings

from stammdaten.models import Schuljahr


def schulinfo(request):
    return {"SCHULNAME": settings.SCHULNAME, "AKTUELLES_SCHULJAHR": Schuljahr.aktuelles()}
