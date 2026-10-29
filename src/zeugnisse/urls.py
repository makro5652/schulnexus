from django.urls import path

from . import ansichten, notenliste

urlpatterns = [
    path("", ansichten.uebersicht, name="zeugnisse"),
    path("notenliste/", notenliste.notenliste, name="notenliste"),
    path("unterricht/<int:pk>/", ansichten.unterricht, name="zeugnis_unterricht"),
    path("klasse/<int:gruppe>/<int:abschnitt>/", ansichten.klasse, name="zeugnis_klasse"),
    path("klasse/<int:gruppe>/<int:abschnitt>/druck/", ansichten.klasse_druck, name="zeugnis_klasse_druck"),
    path("<int:pk>/", ansichten.zeugnis, name="zeugnis"),
    path("<int:pk>/druck/", ansichten.druck, name="zeugnis_druck"),
    path("<int:pk>/kommentar/", ansichten.kommentar_aktion, name="zeugnis_kommentar"),
    path("konferenz/<int:pk>/", ansichten.konferenz, name="konferenz"),
    path("konferenz/<int:pk>/protokoll/", ansichten.konferenz_protokoll, name="konferenz_protokoll"),
    path("konferenz/<int:pk>/gefaehrdung/", ansichten.gefaehrdung_druck, name="konferenz_gefaehrdung"),
]
