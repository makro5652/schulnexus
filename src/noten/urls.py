from django.urls import path

from . import ansichten as A
from . import kurswahl as K

urlpatterns = [
    path("kurs/", K.kurs_oeffnen, name="kurs_oeffnen"),
    path("unterricht/<int:pk>/eintragen/", A.noten_eintragen, name="noten_eintragen"),
    path("unterricht/<int:pk>/eintragen/<int:ln_pk>/", A.noten_eintragen, name="noten_bearbeiten"),
    path("unterricht/<int:pk>/struktur/", A.struktur, name="bewertungsstruktur"),
    path("vorgaben/", A.vorgaben, name="leistungsvorgaben"),
    path("vorgaben/neu/", A.vorgabe_bearbeiten, name="vorgabe_neu"),
    path("vorgaben/<int:pk>/", A.vorgabe_bearbeiten, name="vorgabe_bearbeiten"),
    path("vorgaben/<int:pk>/loeschen/", A.vorgabe_loeschen, name="vorgabe_loeschen"),
]
