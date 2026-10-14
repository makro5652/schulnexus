from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SicherungConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "sicherung"
    verbose_name = _("Sicherung und Wiederherstellung")
