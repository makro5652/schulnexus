from django.urls import path

from . import ansichten

urlpatterns = [
    path("", ansichten.uebersicht, name="elternkontakt"),
    path("neu/", ansichten.neu, name="elternnachricht_neu"),
    path("<int:pk>/", ansichten.gespraech, name="elterngespraech"),
    path("<int:pk>/elternansicht/<int:epk>/", ansichten.elternansicht, name="elterngespraech_vorschau"),
    path("regeln/", ansichten.regeln, name="elternkontakt_regeln"),
    path("regeln/neu/", ansichten.regel_bearbeiten, name="elternkontakt_regel_neu"),
    path("regeln/<int:pk>/", ansichten.regel_bearbeiten, name="elternkontakt_regel"),
    path("regeln/<int:pk>/loeschen/", ansichten.regel_loeschen, name="elternkontakt_regel_loeschen"),
    path("zeugnisse/<int:klasse_pk>/<int:abschnitt_pk>/", ansichten.zeugnisempfang, name="zeugnisempfang_anfordern"),
]
