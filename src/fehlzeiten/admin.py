from django.contrib import admin
from django.utils import formats
from django.utils.translation import gettext, gettext_lazy as _
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
        (_("Zeitraum"), {"fields": [("datum_von", "datum_bis"), ("stunde_von", "stunde_bis"), "minuten"]}),
        (_("Details"), {"fields": ["grund", "quelle", "erfasst_von", "erfasst_am"]}),
    ]

    @admin.display(description=_("Zeitraum"))
    def zeitraum(self, obj):
        text = formats.date_format(obj.datum_von, "SHORT_DATE_FORMAT")
        if obj.datum_bis and obj.datum_bis != obj.datum_von:
            text += " – " + formats.date_format(obj.datum_bis, "SHORT_DATE_FORMAT")
        if obj.art == Fehlzeit.STUNDEN:
            text += ", " + gettext("%(von)s.–%(bis)s. Std.") % {"von": obj.stunde_von, "bis": obj.stunde_bis}
        if obj.art == Fehlzeit.VERSPAETUNG:
            text += ", " + gettext("%(n)s Min.") % {"n": obj.minuten}
        return text

    @admin.display(description=_("Fehlstunden"))
    def fehlstunden_anzeige(self, obj):
        return obj.fehlstunden()

    def save_model(self, request, obj, form, change):
        if not obj.erfasst_von_id:
            obj.erfasst_von = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description=_("Als entschuldigt markieren"))
    def als_entschuldigt(self, request, queryset):
        n = queryset.update(status="entschuldigt")
        self.message_user(request, gettext("%(n)s Fehlzeiten als entschuldigt markiert.") % {"n": n})

    @admin.action(description=_("Als unentschuldigt markieren"))
    def als_unentschuldigt(self, request, queryset):
        n = queryset.update(status="unentschuldigt")
        self.message_user(request, gettext("%(n)s Fehlzeiten als unentschuldigt markiert.") % {"n": n})
