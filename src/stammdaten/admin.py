from django.contrib import admin
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from simple_history.admin import SimpleHistoryAdmin

from portal.rechte import ist_verwaltung

from .models import (
    Abschluss,
    Abschlussart,
    Abschnitt,
    Beziehung,
    Bildungsgang,
    Dokument,
    Einwilligung,
    Elternprofil,
    Fach,
    Fortbildung,
    Gesundheitsangaben,
    Gruppe,
    Laufbahnabschnitt,
    Mitgliedschaft,
    Notfallkontakt,
    Person,
    Personalprofil,
    Schuelerprofil,
    Schuljahr,
    Sprachenfolge,
    VorherigeSchule,
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


# ---------------------------------------------------------------- Person

class SchuelerprofilKurzInline(admin.StackedInline):
    model = Schuelerprofil
    extra = 0
    max_num = 1
    fields = ["schuelernummer", "status", "eintrittsdatum"]
    show_change_link = True
    verbose_name_plural = "Schülerprofil (vollständige Akte über „Ändern“)"


class PersonalprofilKurzInline(admin.StackedInline):
    model = Personalprofil
    extra = 0
    max_num = 1
    fields = ["kuerzel", "funktion", "aktiv"]
    show_change_link = True
    verbose_name_plural = "Personalprofil (vollständige Personalakte über „Ändern“)"


class ElternprofilInline(admin.StackedInline):
    model = Elternprofil
    extra = 0
    max_num = 1
    verbose_name_plural = "Elternprofil (für Erziehungsberechtigte)"
    fieldsets = [(None, {"fields": [("beruf", "arbeitgeber"), "korrespondenzweg",
                                    ("schulverein_mitglied", "mitgliedsnummer"), "elternvertretung", "kontaktdaten_weitergabe"]})]


class KinderInline(admin.TabularInline):
    model = Beziehung
    fk_name = "person"
    extra = 0
    verbose_name = "Kind (Schüler:in)"
    verbose_name_plural = "Ist Erziehungsberechtigte:r / Kontaktperson von"
    autocomplete_fields = ["schueler"]
    fields = ["schueler", "art", "sorgerecht", "auskunftsrecht", "abholberechtigt", "notfallkontakt", "rechnungsempfaenger"]


class DokumentInline(admin.TabularInline):
    model = Dokument
    extra = 0
    fields = ["kategorie", "titel", "datei", "zugriffsstufe", "aufbewahren_bis"]


PERSON_FIELDSETS = [
    ("Name", {"fields": [("anrede", "titel"), ("vorname", "rufname", "nachname"), "geschlecht"]}),
    ("Geburt und Herkunft", {"fields": [("geburtsdatum", "geburtsort", "geburtsland"), "staatsangehoerigkeiten"]}),
    ("Kontakt", {"fields": [("email", "sprache"), ("telefon", "mobil", "telefon_dienstlich")]}),
    ("Anschrift", {"fields": ["strasse", ("postfach", "plz"), ("ort", "land")]}),
    ("System", {"fields": ["benutzer", "notizen"], "classes": ["collapse"]}),
]


class RolleFilter(admin.SimpleListFilter):
    title = "Rolle"
    parameter_name = "rolle"

    def lookups(self, request, model_admin):
        return [("schueler", "Schüler:innen"), ("eltern", "Eltern / Kontaktpersonen"), ("personal", "Personal")]

    def queryset(self, request, qs):
        if self.value() == "schueler":
            return qs.filter(schueler__isnull=False)
        if self.value() == "eltern":
            return qs.filter(kinder_beziehungen__isnull=False).distinct()
        if self.value() == "personal":
            return qs.filter(personal__isnull=False)
        return qs


@admin.register(Person)
class PersonAdmin(SimpleHistoryAdmin):
    list_display = ["nachname", "vorname", "rolle", "email", "mobil_oder_telefon"]
    search_fields = ["nachname", "vorname", "rufname", "email", "mobil", "telefon"]
    list_filter = [RolleFilter, "sprache"]
    inlines = [SchuelerprofilKurzInline, PersonalprofilKurzInline, ElternprofilInline, KinderInline, DokumentInline]
    fieldsets = PERSON_FIELDSETS

    @admin.display(description="Rolle")
    def rolle(self, obj):
        rollen = []
        if hasattr(obj, "schueler"):
            rollen.append("Schüler:in")
        if hasattr(obj, "personal"):
            rollen.append(obj.personal.get_funktion_display())
        if obj.kinder_beziehungen.exists():
            rollen.append("Eltern / Kontakt")
        return ", ".join(rollen) or "—"

    @admin.display(description="Telefon")
    def mobil_oder_telefon(self, obj):
        return obj.mobil or obj.telefon or "—"

    def save_formset(self, request, form, formset, change):
        for obj in formset.save(commit=False):
            if isinstance(obj, Dokument) and not obj.hochgeladen_von_id:
                obj.hochgeladen_von = request.user
            obj.save()
        formset.save_m2m()
        for obj in formset.deleted_objects:
            obj.delete()


# ---------------------------------------------------------------- Schüler:innen

class BeziehungInline(admin.TabularInline):
    model = Beziehung
    fk_name = "schueler"
    extra = 0
    autocomplete_fields = ["person"]
    verbose_name_plural = "Eltern / Erziehungsberechtigte / Kontaktpersonen"


class MitgliedschaftInline(admin.TabularInline):
    model = Mitgliedschaft
    extra = 0
    autocomplete_fields = ["gruppe"]
    fields = ["gruppe", "von", "bis", "rolle"]
    verbose_name_plural = "Klassen und Gruppen"


class EinwilligungInline(admin.TabularInline):
    model = Einwilligung
    extra = 0
    autocomplete_fields = ["erteilt_durch"]


class LaufbahnInline(admin.TabularInline):
    model = Laufbahnabschnitt
    extra = 0
    fields = ["schuljahr", "jahrgang", "bildungsgang", "stammklasse", "von", "bis", "ergebnis", "bemerkung"]
    verbose_name_plural = "Schullaufbahn"


class AbschlussInline(admin.TabularInline):
    model = Abschluss
    extra = 0
    fields = ["art", "datum", "durchschnitt", "niveau", "an_dieser_schule", "bemerkung"]


class VorherigeSchuleInline(admin.TabularInline):
    model = VorherigeSchule
    extra = 0


class SprachenfolgeInline(admin.TabularInline):
    model = Sprachenfolge
    extra = 0


class GesundheitInline(admin.StackedInline):
    """Wird nur angezeigt, wer das Recht zum Ansehen von Gesundheitsangaben hat."""

    model = Gesundheitsangaben
    extra = 0
    max_num = 1
    verbose_name_plural = "Gesundheitsangaben (vertraulich)"
    fieldsets = [(None, {"fields": [("allergien", "erkrankungen"), "medikamente", "notfallhinweise",
                                    ("arzt", "krankenversicherung"), "schwimmen_erlaubt"]})]


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


class BildungsgangFilter(admin.SimpleListFilter):
    title = "Bildungsgang (aktuelles Schuljahr)"
    parameter_name = "bildungsgang"

    def lookups(self, request, model_admin):
        return [(b.pk, b.name) for b in Bildungsgang.objects.all()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(laufbahn__bildungsgang_id=self.value(), laufbahn__schuljahr__aktiv=True).distinct()
        return queryset


@admin.register(Schuelerprofil)
class SchuelerprofilAdmin(SimpleHistoryAdmin):
    list_display = ["person", "schuelernummer", "klasse", "bildungsgang", "status", "akte"]
    list_filter = ["status", StammklasseFilter, BildungsgangFilter, "daz", "nachteilsausgleich"]
    search_fields = ["person__nachname", "person__vorname", "schuelernummer"]
    autocomplete_fields = ["person"]
    fieldsets = [
        ("Schüler:in", {"fields": ["person", ("schuelernummer", "status")]}),
        ("Eintritt und Austritt", {"fields": [("eintrittsdatum", "eintritt_jahrgang"), ("austrittsdatum", "austrittsgrund")]}),
        ("Sprache und Förderung", {"fields": [("muttersprache", "familiensprache"), ("daz", "nachteilsausgleich"),
                                              "foerderbedarf", "religionsunterricht"]}),
        ("Organisatorisches", {"fields": ["lebt_bei", ("schulweg", "buslinie"), "abholhinweise", "bemerkungen"]}),
    ]

    def get_inlines(self, request, obj):
        inlines = [LaufbahnInline, MitgliedschaftInline, BeziehungInline, AbschlussInline,
                   SprachenfolgeInline, VorherigeSchuleInline, EinwilligungInline]
        if request.user.has_perm("stammdaten.view_gesundheitsangaben"):
            inlines.append(GesundheitInline)
        return inlines

    @admin.display(description="Stammklasse")
    def klasse(self, obj):
        g = obj.stammklasse()
        return g.name if g else "—"

    @admin.display(description="Bildungsgang")
    def bildungsgang(self, obj):
        abschnitt = obj.aktueller_laufbahnabschnitt()
        return abschnitt.bildungsgang.kuerzel if abschnitt else "—"

    @admin.display(description="Akte")
    def akte(self, obj):
        return format_html('<a href="{}">Schülerakte</a>', reverse("schuelerakte", args=[obj.pk]))


# ---------------------------------------------------------------- Personal

class FortbildungInline(admin.TabularInline):
    model = Fortbildung
    extra = 0


class NotfallkontaktInline(admin.TabularInline):
    model = Notfallkontakt
    extra = 0


@admin.register(Personalprofil)
class PersonalprofilAdmin(SimpleHistoryAdmin):
    list_display = ["kuerzel", "person", "funktion", "anstellungsart", "wochenstunden", "vertragsende", "aktiv"]
    list_filter = ["funktion", "anstellungsart", "aktiv", "lehrbefaehigungen"]
    search_fields = ["kuerzel", "person__nachname", "person__vorname", "personalnummer"]
    autocomplete_fields = ["person"]
    filter_horizontal = ["lehrbefaehigungen"]
    inlines = [FortbildungInline, NotfallkontaktInline]
    fieldsets = [
        ("Person", {"fields": ["person", ("kuerzel", "funktion", "aktiv")]}),
        ("Dienstverhältnis", {"fields": [("personalnummer", "anstellungsart"), ("dienstbeginn", "vertragsende"),
                                         ("wochenstunden", "ermaessigung"), "arbeitserlaubnis_bis"]}),
        ("Tätigkeit", {"fields": ["lehrbefaehigungen", "weitere_funktionen", ("dienst_email", "raum")]}),
        ("Intern", {"fields": ["bemerkungen"], "classes": ["collapse"]}),
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if ist_verwaltung(request.user) else qs.filter(person__benutzer=request.user)


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


@admin.register(Bildungsgang)
class BildungsgangAdmin(admin.ModelAdmin):
    list_display = ["kuerzel", "name", "angestrebter_abschluss", "jahrgang_von", "jahrgang_bis", "reihenfolge"]
    list_editable = ["reihenfolge"]


@admin.register(Abschlussart)
class AbschlussartAdmin(admin.ModelAdmin):
    list_display = ["kuerzel", "name", "reihenfolge"]
    list_editable = ["reihenfolge"]


@admin.register(Laufbahnabschnitt)
class LaufbahnabschnittAdmin(SimpleHistoryAdmin):
    list_display = ["schueler", "schuljahr", "jahrgang", "bildungsgang", "stammklasse", "ergebnis"]
    list_filter = ["schuljahr", "jahrgang", "bildungsgang", "ergebnis"]
    search_fields = ["schueler__person__nachname", "schueler__person__vorname"]
    autocomplete_fields = ["schueler", "stammklasse"]


@admin.register(Abschluss)
class AbschlussAdmin(SimpleHistoryAdmin):
    list_display = ["schueler", "art", "datum", "durchschnitt", "niveau"]
    list_filter = ["art", "an_dieser_schule"]
    search_fields = ["schueler__person__nachname"]
    autocomplete_fields = ["schueler"]


@admin.register(Elternprofil)
class ElternprofilAdmin(SimpleHistoryAdmin):
    list_display = ["person", "beruf", "korrespondenzweg", "schulverein_mitglied", "elternvertretung"]
    list_filter = ["schulverein_mitglied", "korrespondenzweg"]
    search_fields = ["person__nachname", "person__vorname", "beruf"]
    autocomplete_fields = ["person"]


@admin.register(Gesundheitsangaben)
class GesundheitsangabenAdmin(SimpleHistoryAdmin):
    list_display = ["schueler", "allergien", "medikamente", "schwimmen_erlaubt"]
    search_fields = ["schueler__person__nachname"]
    autocomplete_fields = ["schueler"]
