from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PortalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "portal"
    verbose_name = _("Portal")

    def ready(self):
        from . import signals  # noqa: F401 – registriert die Sprachübernahme beim Anmelden
