from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from simple_history.admin import SimpleHistoryAdmin

from .models import Abzeichnung, Anmerkung, Beschluss, Konferenz, Zeugnis, ZeugnisFachnote
from .rechte import darf_konferenz_sehen, darf_zeugnis_sehen


class FachnoteInline(admin.TabularInline):
    model = ZeugnisFachnote
    extra = 0
    can_delete = False
    readonly_fields = ["fach", "fachname", "note", "punkte", "vermerk", "hinweis"]
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


class AbzeichnungInline(admin.TabularInline):
    model = Abzeichnung
    extra = 0
    readonly_fields = ["lehrkraft", "am", "stand"]


@admin.register(Zeugnis)
class ZeugnisAdmin(SimpleHistoryAdmin):
    list_display = ["schueler", "abschnitt", "art", "klasse", "versetzung", "status", "portal"]
    list_filter = ["abschnitt", "art", "status", "klasse"]
    search_fields = ["schueler__person__nachname", "schueler__person__vorname"]
    readonly_fields = ["schueler", "abschnitt", "status", "freigegeben_am", "freigegeben_von", "kommentar_geaendert", "kommentar_von"]
    inlines = [FachnoteInline, AbzeichnungInline]

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj) and (obj is None or darf_zeugnis_sehen(request.user, obj))

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and (obj is None or not obj.freigegeben)

    @admin.display(description=_("Portal"))
    def portal(self, obj):
        return format_html('<a href="{}">{}</a>', reverse("zeugnis", args=[obj.pk]), _("öffnen"))


@admin.register(Anmerkung)
class AnmerkungAdmin(admin.ModelAdmin):
    list_display = ["zeugnis", "autor", "erstellt", "erledigt"]
    list_filter = ["erledigt"]


class BeschlussInline(admin.TabularInline):
    model = Beschluss
    extra = 0
    fields = ["schueler", "entscheidung", "ausgleich", "gefaehrdung", "stimmen_ja", "stimmen_nein", "begruendung"]


@admin.register(Konferenz)
class KonferenzAdmin(SimpleHistoryAdmin):
    list_display = ["klasse", "abschnitt", "art", "datum", "status", "portal"]
    list_filter = ["abschnitt", "art", "status"]
    filter_horizontal = ["teilnehmende"]
    inlines = [BeschlussInline]

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj) and (obj is None or darf_konferenz_sehen(request.user, obj))

    @admin.display(description=_("Portal"))
    def portal(self, obj):
        return format_html('<a href="{}">{}</a>', reverse("konferenz", args=[obj.pk]), _("öffnen"))
