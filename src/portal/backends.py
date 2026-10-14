"""
Anmeldung und Rechteprüfung: wie Djangos ModelBackend, zusätzlich können einzelnen Konten Rechte ihrer Rollen
entzogen werden (Benutzereinstellung.entzogene_rechte, gepflegt unter „Benutzer und Rechte“).
Für Konten mit Vollzugriff (Superuser, Rolle IT-Administration) gilt ein Entzug nicht.
"""
from django.contrib.auth.backends import ModelBackend


class RechteBackend(ModelBackend):
    def _entzogen(self, user_obj):
        if not hasattr(user_obj, "_entzogen_cache"):
            from .models import Benutzereinstellung

            user_obj._entzogen_cache = {
                f"{app}.{code}" for app, code in Benutzereinstellung.entzogene_rechte.through.objects.filter(
                    benutzereinstellung__benutzer_id=user_obj.pk).values_list("permission__content_type__app_label", "permission__codename")
            }
        return user_obj._entzogen_cache

    def get_all_permissions(self, user_obj, obj=None):
        rechte = super().get_all_permissions(user_obj, obj)
        if not rechte or user_obj.is_anonymous or not user_obj.is_active:
            return rechte
        entzogen = self._entzogen(user_obj)
        return rechte - entzogen if entzogen else rechte

    def get_group_permissions(self, user_obj, obj=None):
        rechte = super().get_group_permissions(user_obj, obj)
        if not rechte or user_obj.is_anonymous or not user_obj.is_active:
            return rechte
        return rechte - self._entzogen(user_obj)
