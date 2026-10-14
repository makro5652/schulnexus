from django.urls import path

from . import ansichten

urlpatterns = [
    path("", ansichten.schuljahre, name="schuljahre"),
    path("wechsel/<int:pk>/", ansichten.schuljahreswechsel, name="schuljahreswechsel"),
    path("schueler/<int:pk>/", ansichten.schueler, name="laufbahn_schueler"),
    path("archiv/", ansichten.archiv, name="archiv"),
    path("loeschfristen/", ansichten.loeschfristen, name="loeschfristen"),
]
