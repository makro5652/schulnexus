"""Sprechtage im Elternportal (Anmeldung mit Elternkonto, nur mit ELTERNPORTAL_AKTIV)."""
from django.urls import path

from . import eltern

urlpatterns = [
    path("", eltern.uebersicht, name="eltern_sprechtage"),
    path("<int:pk>/", eltern.buchen, name="eltern_sprechtag"),
]
