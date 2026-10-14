from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ElternkontaktConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "elternkontakt"
    verbose_name = _("Elternkommunikation")

    def ready(self):
        from django.db import transaction
        from django.db.models.signals import post_save

        from fehlzeiten.models import Fehlzeit

        from . import checks  # noqa: F401  (Systemprüfung Elternportal)

        def fehlzeit_gespeichert(sender, instance, raw=False, **kwargs):
            """Nach jeder erfassten oder geänderten Fehlzeit die Benachrichtigungsregeln prüfen."""
            if raw:
                return
            from .pruefung import schueler_pruefen

            schueler, stichtag = instance.schueler, instance.datum_von
            transaction.on_commit(lambda: schueler_pruefen(schueler, stichtag))

        post_save.connect(fehlzeit_gespeichert, sender=Fehlzeit, weak=False, dispatch_uid="elternkontakt_fehlzeit")
