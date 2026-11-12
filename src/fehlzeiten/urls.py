from django.urls import path

from . import ansichten

urlpatterns = [
    path("", ansichten.fehlzeiten, name="fehlzeiten"),
]
