from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from simple_history.admin import SimpleHistoryAdmin

from .models import Ausloesung, Beitrag, Benachrichtigungsregel, Empfaenger, Gespraech
from .rechte import sichtbare_gespraeche


class EmpfaengerInline(admin.TabularInline):
    model = Empfaenger
    extra = 0
    fields = ["person", "email", "versand_status", "versendet_am", "gelesen_am", "bestaetigt_am", "bestaetigt_ueber"]
    readonly_fields = ["email", "versand_status", "versendet_am", "gelesen_am", "bestaetigt_am", "bestaetigt_ueber"]
    raw_id_fields = ["person"]


class BeitragInline(admin.StackedInline):
    model = Beitrag
    extra = 0
    fields = ["erstellt_am", "ueber", "von_benutzer", "von_person", "text"]
    readonly_fields = ["erstellt_am", "ueber", "von_benutzer", "von_person"]


@admin.register(Gespraech)
class GespraechAdmin(SimpleHistoryAdmin):
    """Übersicht für die Verwaltung; geschrieben wird im Portal (Elternkommunikation)."""

    list_display = ["titel", "schueler", "art", "letzte_aktivitaet", "bestaetigung_erbeten", "abgeschlossen", "portal"]
    list_filter = ["art", "bestaetigung_erbeten", "abgeschlossen"]
    search_fields = ["betreff", "schueler__person__nachname", "schueler__person__vorname"]
    raw_id_fields = ["schueler", "zeugnis"]
    readonly_fields = ["erstellt_von", "erstellt_am", "eltern_antwort_am", "schule_gelesen_am"]
    inlines = [EmpfaengerInline, BeitragInline]

    def get_queryset(self, request):
        return sichtbare_gespraeche(request.user).select_related("schueler__person")

    @admin.display(description=_("Betreff"))
    def titel(self, obj):
        return obj.titel()

    @admin.display(description=_("Portal"))
    def portal(self, obj):
        return format_html('<a href="{}">{}</a>', reverse("elterngespraech", args=[obj.pk]), _("öffnen"))


@admin.register(Benachrichtigungsregel)
class BenachrichtigungsregelAdmin(SimpleHistoryAdmin):
    list_display = ["name", "merkmal", "zaehlung", "schwelle", "zeitraum", "jahrgang_von", "jahrgang_bis", "wiederholen", "aktiv"]
    list_filter = ["aktiv", "merkmal", "zeitraum"]
    readonly_fields = ["erstellt_von", "geaendert_am"]


@admin.register(Ausloesung)
class AusloesungAdmin(admin.ModelAdmin):
    list_display = ["ausgeloest_am", "regel", "schueler", "zeitraum", "stufe", "wert", "still", "gespraech"]
    list_filter = ["regel", "still"]
    search_fields = ["schueler__person__nachname"]
    raw_id_fields = ["schueler", "gespraech"]
