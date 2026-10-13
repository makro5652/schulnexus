from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from simple_history.admin import SimpleHistoryAdmin

from .models import AnmeldeDatei, AnmeldeKontakt, AnmeldePunkt, Anmeldung, ChecklistenVorlage, VorlagenPunkt
from .rechte import anmeldungen_fuer, darf_sehen


class VorlagenPunktInline(admin.TabularInline):
    model = VorlagenPunkt
    extra = 3
    fields = ["reihenfolge", "text", "text_en", "zustaendig", "pflicht"]


@admin.register(ChecklistenVorlage)
class ChecklistenVorlageAdmin(admin.ModelAdmin):
    list_display = ["name", "name_en", "jahrgaenge", "standard", "anzahl_punkte", "aktiv", "reihenfolge"]
    list_editable = ["standard", "aktiv", "reihenfolge"]
    search_fields = ["name", "name_en"]
    inlines = [VorlagenPunktInline]
    fields = ["name", "name_en", "beschreibung", ("jahrgang_von", "jahrgang_bis"), ("standard", "aktiv", "reihenfolge")]

    @admin.display(description=_("Jahrgänge"))
    def jahrgaenge(self, obj):
        if obj.jahrgang_von is None and obj.jahrgang_bis is None:
            return "—"
        return f"{obj.jahrgang_von or '…'}–{obj.jahrgang_bis or '…'}"

    @admin.display(description=_("Punkte"))
    def anzahl_punkte(self, obj):
        return obj.punkte.count()


class KontaktInline(admin.StackedInline):
    model = AnmeldeKontakt
    extra = 0


class DateiInline(admin.TabularInline):
    model = AnmeldeDatei
    extra = 0
    fields = ["hochgeladen_am", "kategorie", "titel", "datei", "zugriffsstufe", "uebernehmen"]
    readonly_fields = ["hochgeladen_am"]


class PunktInline(admin.TabularInline):
    model = AnmeldePunkt
    extra = 0
    fields = ["reihenfolge", "text", "zustaendig", "pflicht", "erledigt", "erledigt_am", "erledigt_von", "bemerkung"]
    readonly_fields = ["erledigt_am", "erledigt_von"]


@admin.register(Anmeldung)
class AnmeldungAdmin(SimpleHistoryAdmin):
    """Vollständige Liste für die Verwaltung; die Arbeit geschieht im Portal (Neuanmeldungen)."""

    list_display = ["nummer", "__str__", "geburtsdatum", "schuljahr", "jahrgang", "vorlaeufige_klasse", "status", "eingang", "portal"]
    list_filter = ["status", "schuljahr", "jahrgang"]
    search_fields = ["nummer", "nachname", "vorname", "kontakte__nachname", "kontakte__email"]
    date_hierarchy = "eingang"
    inlines = [KontaktInline, DateiInline, PunktInline]
    readonly_fields = ["nummer", "schueler", "uebernommen_am", "uebernommen_von"]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(pk__in=anmeldungen_fuer(request.user).values("pk")).select_related(
            "schuljahr", "vorlaeufige_klasse")

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj) and (obj is None or darf_sehen(request.user, obj))

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and (obj is None or (darf_sehen(request.user, obj) and not obj.abgeschlossen))

    @admin.display(description=_("Portal"))
    def portal(self, obj):
        return format_html('<a href="{}">{}</a>', reverse("anmeldung", args=[obj.pk]), _("öffnen"))
