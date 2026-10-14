from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LaufbahnConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "laufbahn"
    verbose_name = _("Schuljahre, Abgänge und Archiv")
