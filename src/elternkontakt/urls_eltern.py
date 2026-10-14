"""Öffentliche Elternseiten (ohne Anmeldung über den persönlichen Link; Portal nur mit ELTERNPORTAL_AKTIV)."""
from django.urls import path

from . import eltern

urlpatterns = [
    path("", eltern.portal_start, name="elternportal"),
    path("gespraech/<int:pk>/", eltern.portal_gespraech, name="elternportal_gespraech"),
    path("n/<str:token>/", eltern.nachricht, name="eltern_nachricht"),
]
