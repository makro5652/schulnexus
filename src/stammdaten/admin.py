from django.contrib import admin
from django.utils import timezone
from simple_history.admin import SimpleHistoryAdmin

from .models import (
    Abschnitt,
    Beziehung,
    Dokument,
    Einwilligung,
    Fach,
    Gruppe,
    Mitgliedschaft,
    Person,
    Personalprofil,
    Schuelerprofil,
    Schuljahr,
)

admin.site.site_header = "Schulverwaltung"
admin.site.site_title = "Schulverwaltung"
admin.site.index_title = "Verwaltung"


class AbschnittInline(admin.TabularInline):
    model = Abschnitt
    extra = 0


@admin.register(Schuljahr)
class SchuljahrAdmin(admin.ModelAdmin):
    list_display = ["name", "beginn", "ende", "aktiv"]
    inlines = [AbschnittInline]


class SchuelerprofilInline(admin.StackedInline):
    model = Schuelerprofil
    extra = 0
    max_num = 1


class PersonalprofilInline(admin.StackedInline):
    model = Personalprofil
    extra = 0
    max_num = 1


class KinderInline(admin.TabularInline):
    model = Beziehung
    fk_name = "person"
    extra = 0
    verbose_name = "Kind (Schüler:in)"
    verbose_name_plural = "Ist Kontaktperson von"
    autocomplete_fields = ["schueler"]


class DokumentInline(admin.TabularInline):
    model = Dokument
    extra = 0
    fields = ["kategorie", "titel", "datei", "zugriffsstufe", "aufbewahren_bis"]


@admin.register(Person)
class PersonAdmin(SimpleHistoryAdmin):
    list_display = ["nachname", "vorname", "rolle", "email", "telefon"]
    search_fields = ["nachname", "vorname", "rufname", "email"]
    list_filter = ["sprache"]
    inlines = [SchuelerprofilInline, PersonalprofilInline, KinderInline, DokumentInline]
    fieldsets = [
        ("Name", {"fields": [("vorname", "rufname", "nachname"), "geburtsdatum"]}),
        ("Kontakt", {"fields": [("email", "telefon"), ("strasse", "ort", "land"), "sprache"]}),
        ("System", {"fields": ["benutzer", "notizen"], "classes": ["collapse"]}),
    ]

    @admin.display(description="Rolle")
    def rolle(self, obj):
        rollen = []
        if hasattr(obj, "schueler"):
            rollen.append("Schüler:in")
        if hasattr(obj, "personal"):
            rollen.append(obj.personal.get_funktion_display())
        if obj.kinder_beziehungen.exists():
            rollen.append("Kontaktperson")
        return ", ".join(rollen) or "—"

    def save_formset(self, request, form, formset, change):
        for obj in formset.save(commit=False):
            if isinstance(obj, Dokument) and not obj.hochgeladen_von_id:
                obj.hochgeladen_von = request.user
            obj.save()
        formset.save_m2m()
        for obj in formset.deleted_objects:
            obj.delete()


class BeziehungInline(admin.TabularInline):
    model = Beziehung
    fk_name = "schueler"
    extra = 0
    autocomplete_fields = ["person"]


class MitgliedschaftInline(admin.TabularInline):
    model = Mitgliedschaft
    extra = 0
    autocomplete_fields = ["gruppe"]
    fields = ["gruppe", "von", "bis", "rolle"]


class EinwilligungInline(admin.TabularInline):
    model = Einwilligung
    extra = 0
    autocomplete_fields = ["erteilt_durch"]


class StammklasseFilter(admin.SimpleListFilter):
    title = "Stammklasse (aktuell)"
    parameter_name = "klasse"

    def lookups(self, request, model_admin):
        sj = Schuljahr.aktuelles()
        if not sj:
            return []
        return [(g.pk, g.name) for g in Gruppe.objects.filter(schuljahr=sj, typ=Gruppe.STAMMKLASSE)]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(
                mitgliedschaften__in=Mitgliedschaft.objects.aktiv().filter(gruppe_id=self.value())
            ).distinct()
        return queryset


@admin.register(Schuelerprofil)
class SchuelerprofilAdmin(SimpleHistoryAdmin):
    list_display = ["person", "schuelernummer", "klasse", "status"]
    list_filter = ["status", StammklasseFilter]
    search_fields = ["person__nachname", "person__vorname", "schuelernummer"]
    autocomplete_fields = ["person"]
    inlines = [MitgliedschaftInline, BeziehungInline, EinwilligungInline]

    @admin.display(description="Stammklasse")
    def klasse(self, obj):
        g = obj.stammklasse()
        return g.name if g else "—"


@admin.register(Personalprofil)
class PersonalprofilAdmin(SimpleHistoryAdmin):
    list_display = ["kuerzel", "person", "funktion", "aktiv"]
    list_filter = ["funktion", "aktiv"]
    search_fields = ["kuerzel", "person__nachname", "person__vorname"]
    autocomplete_fields = ["person"]


class GruppenMitgliederInline(admin.TabularInline):
    model = Mitgliedschaft
    extra = 0
    autocomplete_fields = ["schueler"]
    fields = ["schueler", "von", "bis", "rolle"]


@admin.register(Gruppe)
class GruppeAdmin(SimpleHistoryAdmin):
    list_display = ["name", "typ", "jahrgang", "schuljahr", "leitung", "anzahl_mitglieder"]
    list_filter = ["schuljahr", "typ", "jahrgang"]
    search_fields = ["name", "kuerzel"]
    autocomplete_fields = ["leitung"]
    filter_horizontal = ["gebildet_aus"]
    inlines = [GruppenMitgliederInline]
    actions = ["aus_stammklassen_fuellen"]

    @admin.display(description="Mitglieder (aktuell)")
    def anzahl_mitglieder(self, obj):
        return Mitgliedschaft.objects.aktiv().filter(gruppe=obj).count()

    @admin.action(description="Alle Schüler:innen der Ursprungs-Stammklassen hinzufügen")
    def aus_stammklassen_fuellen(self, request, queryset):
        heute = timezone.localdate()
        neu = 0
        for gruppe in queryset.prefetch_related("gebildet_aus"):
            for klasse in gruppe.gebildet_aus.all():
                for schueler in klasse.aktuelle_mitglieder():
                    _, erstellt = Mitgliedschaft.objects.get_or_create(
                        gruppe=gruppe, schueler=schueler, defaults={"von": max(heute, gruppe.schuljahr.beginn)}
                    )
                    neu += int(erstellt)
        self.message_user(request, f"{neu} Mitgliedschaften angelegt. Danach bitte Abwählende wieder entfernen.")


@admin.register(Mitgliedschaft)
class MitgliedschaftAdmin(SimpleHistoryAdmin):
    list_display = ["schueler", "gruppe", "von", "bis", "rolle"]
    list_filter = ["gruppe__schuljahr", "gruppe__typ", "gruppe"]
    search_fields = ["schueler__person__nachname", "gruppe__name"]
    autocomplete_fields = ["schueler", "gruppe"]


@admin.register(Fach)
class FachAdmin(admin.ModelAdmin):
    list_display = ["kuerzel", "name", "reihenfolge"]
    list_editable = ["reihenfolge"]
    search_fields = ["kuerzel", "name"]


@admin.register(Beziehung)
class BeziehungAdmin(SimpleHistoryAdmin):
    list_display = ["schueler", "person", "art", "sorgerecht", "notfallkontakt"]
    list_filter = ["art", "sorgerecht", "notfallkontakt"]
    search_fields = ["schueler__person__nachname", "person__nachname"]
    autocomplete_fields = ["schueler", "person"]


@admin.register(Einwilligung)
class EinwilligungAdmin(SimpleHistoryAdmin):
    list_display = ["schueler", "zweck", "erteilt_am", "widerrufen_am", "gueltig"]
    list_filter = ["zweck"]
    search_fields = ["schueler__person__nachname"]
    autocomplete_fields = ["schueler", "erteilt_durch"]

    @admin.display(boolean=True, description="Gültig")
    def gueltig(self, obj):
        return obj.gueltig


@admin.register(Dokument)
class DokumentAdmin(admin.ModelAdmin):
    list_display = ["titel", "person", "kategorie", "zugriffsstufe", "hochgeladen_am"]
    list_filter = ["kategorie", "zugriffsstufe"]
    search_fields = ["titel", "person__nachname"]
    autocomplete_fields = ["person"]
    readonly_fields = ["hochgeladen_von"]

    def save_model(self, request, obj, form, change):
        if not obj.hochgeladen_von_id:
            obj.hochgeladen_von = request.user
        super().save_model(request, obj, form, change)
