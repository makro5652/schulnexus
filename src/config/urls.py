from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from portal import anhaenge, startseite, views, zuordnung
from portal.formulare import AnmeldeFormular

urlpatterns = [
    path("", views.start, name="start"),
    path("anmelden/", auth_views.LoginView.as_view(template_name="portal/login.html", authentication_form=AnmeldeFormular), name="login"),
    path("abmelden/", auth_views.LogoutView.as_view(), name="logout"),
    path("noten/unterricht/<int:pk>/", views.notenuebersicht, name="notenuebersicht"),
    path("klassen/<int:pk>/", views.klassenliste, name="klassenliste"),
    path("schueler/<int:pk>/", views.schuelerakte, name="schuelerakte"),
    path("schueler/<int:pk>/anhang/", anhaenge.anhang_hochladen, name="anhang_hochladen"),
    path("anhang/<int:pk>/", anhaenge.anhang_herunterladen, name="anhang"),
    path("anhang/<int:pk>/loeschen/", anhaenge.anhang_loeschen, name="anhang_loeschen"),
    path("anhang/datei/<path:name>", anhaenge.anhang_pfad, name="anhang_pfad"),
    path("foerderung/", include("foerderung.urls")),
    path("aufnahme/", include("aufnahme.urls")),
    path("zeugnisse/", include("zeugnisse.urls")),
    path("suche/", startseite.suche, name="suche"),
    path("stufe/<slug:schluessel>/", startseite.stufe, name="stufe"),
    path("rollen/", startseite.rollenuebersicht, name="rollen"),
    path("zuordnung/", zuordnung.zuordnung, name="zuordnung"),
    path("zuordnung/gruppe/<int:pk>/", zuordnung.zuordnung_aktion, name="zuordnung_aktion"),
    path("zuordnung/neue-gruppe/", zuordnung.gruppe_anlegen, name="gruppe_anlegen"),
    path("notizen/neu/", startseite.notiz_anlegen, name="notiz_anlegen"),
    path("notizen/<int:pk>/", startseite.notiz_aendern, name="notiz_aendern"),
    path("notizen/<int:pk>/aktion/", startseite.notiz_aktion, name="notiz_aktion"),
    path("notizen/erledigte-loeschen/", startseite.erledigte_loeschen, name="notizen_erledigte_loeschen"),
    path("gesundheit/", views.gesundheit, name="gesundheit"),
    path("sprache/", views.sprache_wechseln, name="sprache_wechseln"),
    path("design/", views.design_wechseln, name="design_wechseln"),
    path("verwaltung/", admin.site.urls),
]
