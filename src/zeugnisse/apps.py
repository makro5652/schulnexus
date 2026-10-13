from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ZeugnisseConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "zeugnisse"
    verbose_name = _("Zeugnisse und Konferenzen")
