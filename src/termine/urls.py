from django.urls import path

from . import ansichten

urlpatterns = [
    path("", ansichten.kalender, name="kalender"),
    path("kalender.ics", ansichten.kalender_ics, name="kalender_ics"),
    path("neu/", ansichten.termin, name="termin_neu"),
    path("<int:pk>/", ansichten.termin, name="termin"),
    path("raeume/", ansichten.raumplan, name="raumplan"),
    path("sprechtage/", ansichten.sprechtage, name="sprechtage"),
    path("sprechtage/<int:pk>/", ansichten.sprechtag, name="sprechtag"),
    path("sprechtage/<int:pk>/uebersicht/", ansichten.uebersicht, name="sprechtag_uebersicht"),
    path("sprechtage/<int:pk>/zeiten/<int:teilnahme>/", ansichten.sprechzeiten, name="sprechzeiten"),
]
