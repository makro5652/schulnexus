from django.urls import path

from . import ansichten

urlpatterns = [
    path("", ansichten.anmeldungen, name="anmeldungen"),
    path("neu/", ansichten.anmeldung_neu, name="anmeldung_neu"),
    path("<int:pk>/", ansichten.anmeldung, name="anmeldung"),
    path("<int:pk>/bearbeiten/", ansichten.anmeldung_bearbeiten, name="anmeldung_bearbeiten"),
    path("<int:pk>/aktion/", ansichten.anmeldung_aktion, name="anmeldung_aktion"),
    path("<int:pk>/dateien/", ansichten.datei_hochladen, name="anmeldung_datei_hochladen"),
    path("<int:pk>/uebernahme/", ansichten.anmeldung_uebernahme, name="anmeldung_uebernahme"),
    path("<int:pk>/loeschen/", ansichten.anmeldung_loeschen, name="anmeldung_loeschen"),
    path("datei/<int:pk>/", ansichten.datei, name="aufnahme_datei"),
    path("datei/<int:pk>/loeschen/", ansichten.datei_loeschen, name="aufnahme_datei_loeschen"),
    path("datei/pfad/<path:name>", ansichten.datei_pfad, name="aufnahme_datei_pfad"),
]
