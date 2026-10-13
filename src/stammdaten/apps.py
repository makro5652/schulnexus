from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class StammdatenConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "stammdaten"
    verbose_name = _("Stammdaten")

    def ready(self):
        from django.db.models.signals import post_delete

        from .models import Dokument

        def datei_entfernen(sender, instance, **kwargs):
            """Gelöschte Anhänge werden auch vom Datenträger entfernt (Datensparsamkeit)."""
            if instance.datei and not Dokument.objects.filter(datei=instance.datei.name).exists():
                instance.datei.delete(save=False)

        post_delete.connect(datei_entfernen, sender=Dokument, weak=False, dispatch_uid="dokument_datei_entfernen")
