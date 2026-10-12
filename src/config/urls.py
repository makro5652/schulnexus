from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path

from portal import views

urlpatterns = [
    path("", views.start, name="start"),
    path("anmelden/", auth_views.LoginView.as_view(template_name="portal/login.html"), name="login"),
    path("abmelden/", auth_views.LogoutView.as_view(), name="logout"),
    path("noten/unterricht/<int:pk>/", views.notenuebersicht, name="notenuebersicht"),
    path("klassen/<int:pk>/", views.klassenliste, name="klassenliste"),
    path("gesundheit/", views.gesundheit, name="gesundheit"),
    path("verwaltung/", admin.site.urls),
]
