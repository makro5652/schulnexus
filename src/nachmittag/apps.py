from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class NachmittagConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nachmittag"
    verbose_name = _("Nachmittagsprogramm")
