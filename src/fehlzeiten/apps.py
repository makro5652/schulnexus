from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FehlzeitenConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "fehlzeiten"
    verbose_name = _("Fehlzeiten")
