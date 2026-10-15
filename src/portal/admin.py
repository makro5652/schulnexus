from django.contrib import admin

from .models import Anmeldeversuch, OfficeKachel


@admin.register(OfficeKachel)
class OfficeKachelAdmin(admin.ModelAdmin):
    list_display = ("titel", "url", "symbol", "reihenfolge", "aktiv")
    list_editable = ("reihenfolge", "aktiv")
    search_fields = ("titel", "titel_en", "url")


@admin.register(Anmeldeversuch)
class AnmeldeversuchAdmin(admin.ModelAdmin):
    """Fehlgeschlagene Anmeldungen ansehen; Löschen hebt eine vorübergehende Sperre vorzeitig auf (nur IT)."""

    list_display = ("zeit", "benutzername", "ip")
    list_filter = ("zeit",)
    search_fields = ("benutzername", "ip")
    readonly_fields = ("zeit", "benutzername", "ip")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
