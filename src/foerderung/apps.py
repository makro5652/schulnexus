from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FoerderungConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "foerderung"
    verbose_name = _("Förderung")
