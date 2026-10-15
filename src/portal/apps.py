from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PortalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "portal"
    verbose_name = _("Portal")

    def ready(self):
        from django.contrib import admin

        from . import anmeldeschutz, checks, signals  # noqa: F401 – Anmeldesperre; Systemprüfungen; Sprachübernahme beim Anmelden
        from .sicherheit import admin_anmeldung

        # Die Verwaltungsoberfläche hat keine eigene Anmeldung (sonst ließe sich der zweite Faktor umgehen).
        admin.site.login = admin_anmeldung
