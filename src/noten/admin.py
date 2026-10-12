from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin

from portal.rechte import ist_verwaltung

from .models import (
    Gewichtungsvorlage,
    Leistungskategorie,
    Leistungsnachweis,
    Note,
    Notenschluessel,
    Notenskala,
    Notenstufe,
    Schluesselschwelle,
    Unterricht,
    Zeugnisnote,
)


class NotenstufeInline(admin.TabularInline):
    model = Notenstufe
    extra = 0


@admin.register(Notenskala)
class NotenskalaAdmin(admin.ModelAdmin):
    list_display = ["name", "hoeher_ist_besser", "nachkommastellen", "gefaehrdung_ab"]
    inlines = [NotenstufeInline]


class SchwelleInline(admin.TabularInline):
    model = Schluesselschwelle
    extra = 0


@admin.register(Notenschluessel)
class NotenschluesselAdmin(admin.ModelAdmin):
    list_display = ["name", "skala"]
    inlines = [SchwelleInline]


class KategorieInline(admin.TabularInline):
    model = Leistungskategorie
    extra = 0


@admin.register(Gewichtungsvorlage)
class GewichtungsvorlageAdmin(admin.ModelAdmin):
    list_display = ["name", "kategorien_text"]
    inlines = [KategorieInline]

    @admin.display(description="Kategorien")
    def kategorien_text(self, obj):
        return ", ".join(str(k) for k in obj.kategorien.all())


class EigeneDatenMixin:
    """Lehrkräfte sehen nur ihre eigenen Unterrichte; Verwaltung und Leitung sehen alles."""

    unterricht_pfad = "unterricht"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if ist_verwaltung(request.user):
            return qs
        return qs.filter(**{f"{self.unterricht_pfad}__lehrkraft__person__benutzer": request.user})


@admin.register(Unterricht)
class UnterrichtAdmin(admin.ModelAdmin):
    list_display = ["__str__", "gruppe", "fach", "lehrkraft", "gewichtung", "uebersicht"]
    list_filter = ["abschnitt", "fach", "gruppe__jahrgang"]
    search_fields = ["gruppe__name", "fach__name", "lehrkraft__kuerzel"]
    autocomplete_fields = ["gruppe", "lehrkraft"]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if ist_verwaltung(request.user):
            return qs
        return qs.filter(lehrkraft__person__benutzer=request.user)

    @admin.display(description="Noten")
    def uebersicht(self, obj):
        return format_html('<a href="{}">Notenübersicht</a>', reverse("notenuebersicht", args=[obj.pk]))


class NoteInline(admin.TabularInline):
    model = Note
    extra = 0
    fields = ["schueler", "erreichte_be", "stufe", "sonderstatus", "kommentar"]
    autocomplete_fields = ["schueler"]

    def get_readonly_fields(self, request, obj=None):
        # Bestehende Leistungsnachweise: Notenzeilen werden automatisch je Schüler:in angelegt.
        return ["schueler"] if obj else []

    def has_add_permission(self, request, obj=None):
        return obj is None and super().has_add_permission(request, obj)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "stufe":
            ln_id = request.resolver_match.kwargs.get("object_id")
            if ln_id:
                ln = Leistungsnachweis.objects.filter(pk=ln_id).select_related("unterricht").first()
                if ln:
                    kwargs["queryset"] = Notenstufe.objects.filter(skala=ln.unterricht.skala)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Leistungsnachweis)
class LeistungsnachweisAdmin(EigeneDatenMixin, admin.ModelAdmin):
    list_display = ["titel", "unterricht", "kategorie", "datum", "gewicht", "anzahl_noten"]
    list_filter = ["unterricht__abschnitt", "unterricht__fach", "kategorie__name"]
    search_fields = ["titel", "unterricht__gruppe__name"]
    autocomplete_fields = ["unterricht"]
    inlines = [NoteInline]

    @admin.display(description="Noten erfasst")
    def anzahl_noten(self, obj):
        return obj.noten.exclude(stufe__isnull=True, sonderstatus="").count()

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "unterricht" and not ist_verwaltung(request.user):
            kwargs["queryset"] = Unterricht.objects.filter(lehrkraft__person__benutzer=request.user)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        # Für jede Schülerin / jeden Schüler der Gruppe eine (leere) Notenzeile anlegen,
        # damit die Lehrkraft die Noten direkt in der Liste eintragen kann.
        ln = form.instance
        vorhanden = set(ln.noten.values_list("schueler_id", flat=True))
        neue = [Note(leistungsnachweis=ln, schueler=s) for s in ln.unterricht.schueler() if s.pk not in vorhanden]
        Note.objects.bulk_create(neue)
        if neue:
            self.message_user(request, f"{len(neue)} Notenzeilen angelegt – bitte jetzt die Noten eintragen.")


@admin.register(Note)
class NoteAdmin(EigeneDatenMixin, SimpleHistoryAdmin):
    unterricht_pfad = "leistungsnachweis__unterricht"
    list_display = ["schueler", "leistungsnachweis", "erreichte_be", "stufe", "sonderstatus"]
    list_filter = ["leistungsnachweis__unterricht__abschnitt", "leistungsnachweis__unterricht__fach"]
    search_fields = ["schueler__person__nachname", "leistungsnachweis__titel"]
    autocomplete_fields = ["schueler", "leistungsnachweis"]


@admin.register(Zeugnisnote)
class ZeugnisnoteAdmin(EigeneDatenMixin, SimpleHistoryAdmin):
    list_display = ["schueler", "unterricht", "vorschlag", "stufe"]
    list_filter = ["unterricht__abschnitt", "unterricht__fach", "unterricht__gruppe"]
    search_fields = ["schueler__person__nachname"]
    autocomplete_fields = ["schueler", "unterricht"]
