from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Fehlzeit, Stunde


@admin.register(Stunde)
class StundeAdmin(admin.ModelAdmin):
    list_display = ["schuljahr", "nummer", "beginn", "ende"]
    list_filter = ["schuljahr"]


@admin.register(Fehlzeit)
class FehlzeitAdmin(SimpleHistoryAdmin):
    list_display = ["schueler", "art", "zeitraum", "status", "quelle", "fehlstunden_anzeige"]
    list_filter = ["status", "art", "quelle", "datum_von"]
    search_fields = ["schueler__person__nachname", "schueler__person__vorname", "grund"]
    autocomplete_fields = ["schueler"]
    date_hierarchy = "datum_von"
    readonly_fields = ["erfasst_von", "erfasst_am"]
    actions = ["als_entschuldigt", "als_unentschuldigt"]
    fieldsets = [
        (None, {"fields": ["schueler", "art", "status"]}),
        ("Zeitraum", {"fields": [("datum_von", "datum_bis"), ("stunde_von", "stunde_bis"), "minuten"]}),
        ("Details", {"fields": ["grund", "quelle", "erfasst_von", "erfasst_am"]}),
    ]

    @admin.display(description="Zeitraum")
    def zeitraum(self, obj):
        text = f"{obj.datum_von:%d.%m.%Y}"
        if obj.datum_bis and obj.datum_bis != obj.datum_von:
            text += f" – {obj.datum_bis:%d.%m.%Y}"
        if obj.art == Fehlzeit.STUNDEN:
            text += f", {obj.stunde_von}.–{obj.stunde_bis}. Std."
        if obj.art == Fehlzeit.VERSPAETUNG:
            text += f", {obj.minuten} Min."
        return text

    @admin.display(description="Fehlstunden")
    def fehlstunden_anzeige(self, obj):
        return obj.fehlstunden()

    def save_model(self, request, obj, form, change):
        if not obj.erfasst_von_id:
            obj.erfasst_von = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description="Als entschuldigt markieren")
    def als_entschuldigt(self, request, queryset):
        n = queryset.update(status="entschuldigt")
        self.message_user(request, f"{n} Fehlzeiten als entschuldigt markiert.")

    @admin.action(description="Als unentschuldigt markieren")
    def als_unentschuldigt(self, request, queryset):
        n = queryset.update(status="unentschuldigt")
        self.message_user(request, f"{n} Fehlzeiten als unentschuldigt markiert.")
