from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from simple_history.admin import SimpleHistoryAdmin

from portal.suchauswahl import SuchauswahlAdminMixin
from stammdaten.models import Schuelerprofil

from .models import Abzeichnung, Anmerkung, Beschluss, Konferenz, Zeugnis, ZeugnisFachnote
from .rechte import darf_konferenz_sehen, darf_zeugnis_sehen, konferenz_kandidaten


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


def _konferenz_aus_anfrage(request):
    pk = request.resolver_match.kwargs.get("object_id") if request.resolver_match else None
    return Konferenz.objects.filter(pk=pk).select_related("klasse", "abschnitt").first() if pk else None


class BeschlussInline(admin.TabularInline):
    model = Beschluss
    extra = 0
    fields = ["schueler", "entscheidung", "ausgleich", "gefaehrdung", "stimmen_ja", "stimmen_nein", "begruendung"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        # Nur Schüler:innen der Klasse zur Auswahl (ab 0.4.10.0), dazu bereits erfasste (z. B. nach einem Klassenwechsel)
        if db_field.name == "schueler":
            from .noten import klassen_mitglieder

            k = _konferenz_aus_anfrage(request)
            if k:
                ids = {s.pk for s in klassen_mitglieder(k.klasse, k.abschnitt)}
                ids |= set(k.beschluesse.values_list("schueler_id", flat=True))
                kwargs["queryset"] = (Schuelerprofil.objects.filter(pk__in=ids).select_related("person")
                                      .order_by("person__nachname", "person__vorname"))
            else:
                kwargs["queryset"] = Schuelerprofil.objects.none()
                kwargs["help_text"] = _("Erst die Konferenz speichern; dann stehen die Schüler:innen der Klasse zur Auswahl.")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Konferenz)
class KonferenzAdmin(SuchauswahlAdminMixin, SimpleHistoryAdmin):
    list_display = ["klasse", "abschnitt", "art", "datum", "status", "portal"]
    list_filter = ["abschnitt", "art", "status"]
    inlines = [BeschlussInline]
    suchauswahl_texte = {"teilnehmende": (_("Lehrkräfte der Klasse"), _("Alle Lehrkräfte der Klasse übernehmen"))}

    def suchauswahl_vorschlaege(self, request, db_field):
        k = _konferenz_aus_anfrage(request)
        return konferenz_kandidaten(k) if k and db_field.name == "teilnehmende" else set()

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj) and (obj is None or darf_konferenz_sehen(request.user, obj))

    @admin.display(description=_("Portal"))
    def portal(self, obj):
        return format_html('<a href="{}">{}</a>', reverse("konferenz", args=[obj.pk]), _("öffnen"))
