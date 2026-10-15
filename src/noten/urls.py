from django.urls import path

from . import ansichten as A
from . import klausurregeln as KR
from . import export as X
from . import kurswahl as K
from . import sperrseite as SP

urlpatterns = [
    path("kurs/", K.kurs_oeffnen, name="kurs_oeffnen"),
    path("klausurregeln/", KR.klausurregeln, name="klausurregeln"),
    path("sperre/", SP.notensperre, name="notensperre"),
    path("unterricht/<int:pk>/excel/", X.excel, name="noten_excel"),
    path("unterricht/<int:pk>/notenbogen/", X.notenbogen, name="notenbogen"),
    path("klausurregeln/<int:pk>/", KR.klausurregeln, name="klausurregel_bearbeiten"),
    path("klausurregeln/<int:pk>/loeschen/", KR.klausurregel_loeschen, name="klausurregel_loeschen"),
    path("klausurregeln/freigabe/<int:pk>/loeschen/", KR.freigabe_loeschen, name="zeugnisfreigabe_loeschen"),
    path("unterricht/<int:pk>/eintragen/", A.noten_eintragen, name="noten_eintragen"),
    path("unterricht/<int:pk>/eintragen/<int:ln_pk>/", A.noten_eintragen, name="noten_bearbeiten"),
    path("unterricht/<int:pk>/struktur/", A.struktur, name="bewertungsstruktur"),
    path("vorgaben/", A.vorgaben, name="leistungsvorgaben"),
    path("vorgaben/neu/", A.vorgabe_bearbeiten, name="vorgabe_neu"),
    path("vorgaben/<int:pk>/", A.vorgabe_bearbeiten, name="vorgabe_bearbeiten"),
    path("vorgaben/<int:pk>/loeschen/", A.vorgabe_loeschen, name="vorgabe_loeschen"),
]
