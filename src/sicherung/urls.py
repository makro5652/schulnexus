from django.urls import path

from . import ansichten

urlpatterns = [
    path("sicherung/", ansichten.sicherungen, name="sicherungen"),
    path("sicherung/<int:pk>/herunterladen/", ansichten.sicherung_herunterladen, name="sicherung_herunterladen"),
    path("sicherung/<int:pk>/loeschen/", ansichten.sicherung_loeschen, name="sicherung_loeschen"),
    path("sicherung/<int:pk>/wiederherstellen/", ansichten.wiederherstellen, name="wiederherstellen"),
    path("pdf/", ansichten.pdf_export, name="pdf_export"),
    path("pdf/<int:pk>/zip/", ansichten.pdf_zip, name="pdf_zip"),
    path("pdf/<int:pk>/loeschen/", ansichten.pdf_loeschen, name="pdf_loeschen"),
    path("pdf/<int:pk>/<str:name>", ansichten.pdf_datei, name="pdf_datei"),
    path("benutzer/", ansichten.benutzerverwaltung, name="benutzerverwaltung"),
    path("benutzer/<int:pk>/", ansichten.benutzer_bearbeiten, name="benutzer_bearbeiten"),
    path("protokoll/", ansichten.systemprotokoll, name="systemprotokoll"),
]
