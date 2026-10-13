from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class NotenConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "noten"
    verbose_name = _("Noten")
