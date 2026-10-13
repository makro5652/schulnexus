from django.urls import path

from . import ansichten

urlpatterns = [
    path("plan/<int:pk>/", ansichten.foerderplan, name="foerderplan"),
    path("plan/<int:pk>/eintrag/", ansichten.eintrag_anlegen, name="foerdereintrag_anlegen"),
    path("nachteilsausgleich/<int:pk>/", ansichten.nachteilsausgleich, name="nachteilsausgleich"),
    path("aushaendigung/", ansichten.aushaendigung_anlegen, name="aushaendigung_anlegen"),
    path("aushaendigung/<int:pk>/bestaetigen/", ansichten.erhalt_bestaetigen, name="erhalt_bestaetigen"),
]
