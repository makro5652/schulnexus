from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AufnahmeConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "aufnahme"
    verbose_name = _("Neuanmeldungen")

    def ready(self):
        from django.db.models.signals import post_delete

        from .models import AnmeldeDatei

        def datei_entfernen(sender, instance, **kwargs):
            """Gelöschte Bewerbungsunterlagen werden auch vom Datenträger entfernt (Datensparsamkeit)."""
            if instance.datei and not AnmeldeDatei.objects.filter(datei=instance.datei.name).exists():
                instance.datei.delete(save=False)

        post_delete.connect(datei_entfernen, sender=AnmeldeDatei, weak=False, dispatch_uid="anmeldedatei_entfernen")
