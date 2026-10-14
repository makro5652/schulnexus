from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class TermineConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "termine"
    verbose_name = _("Kalender, Räume und Sprechtage")
