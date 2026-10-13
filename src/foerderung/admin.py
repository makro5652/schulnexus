from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext, gettext_lazy as _
from simple_history.admin import SimpleHistoryAdmin

from portal.rechte import (
    darf_foerderung_bearbeiten, darf_foerderung_sehen, darf_nachteilsausgleich_sehen, foerder_schueler_filter,
    ist_foerderkoordination, ist_verwaltung, klassenleitung_schueler_ids,
)
from stammdaten.models import Person, Schuelerprofil

from .models import (
    Aushaendigung, Ausgleichsmassnahme, Foerdereintrag, Foerderplan, Foerderschwerpunkt, Foerderziel, Nachteilsausgleich,
)


@admin.register(Foerderschwerpunkt)
class FoerderschwerpunktAdmin(admin.ModelAdmin):
    list_display = ["name", "name_en", "reihenfolge", "aktiv"]
    list_editable = ["reihenfolge", "aktiv"]
    search_fields = ["name", "name_en"]


@admin.register(Ausgleichsmassnahme)
class AusgleichsmassnahmeAdmin(admin.ModelAdmin):
    list_display = ["name", "name_en", "notenschutz", "reihenfolge", "aktiv"]
    list_editable = ["reihenfolge", "aktiv"]
    search_fields = ["name", "name_en"]


class FoerderRechteMixin:
    """
    Zeilenweise Rechte: Förderkoordination/Leitung alles; Klassenleitung bearbeitet die eigene Klasse;
    Fachlehrkräfte sehen (lesend) die Unterlagen ihrer Schüler:innen.
    """

    schueler_pfad = "schueler"
    sehen_pruefung = staticmethod(darf_foerderung_sehen)

    def schueler_von(self, obj):
        for teil in self.schueler_pfad.split("__"):
            obj = getattr(obj, teil)
        return obj

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if self.sehen_pruefung is darf_nachteilsausgleich_sehen and ist_verwaltung(request.user):
            return qs
        return qs.filter(foerder_schueler_filter(request.user, self.schueler_pfad))

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj) and (obj is None or self.sehen_pruefung(request.user, self.schueler_von(obj)))

    def has_change_permission(self, request, obj=None):
        return super().has_change_permission(request, obj) and (
            obj is None or darf_foerderung_bearbeiten(request.user, self.schueler_von(obj)))

    def has_delete_permission(self, request, obj=None):
        return super().has_delete_permission(request, obj) and (obj is None or ist_foerderkoordination(request.user))

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "schueler" and not ist_foerderkoordination(request.user):
            kwargs["queryset"] = Schuelerprofil.objects.filter(pk__in=klassenleitung_schueler_ids(request.user)).select_related("person")
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def get_autocomplete_fields(self, request):
        felder = list(super().get_autocomplete_fields(request))
        if not ist_foerderkoordination(request.user) and "schueler" in felder:
            felder.remove("schueler")  # Klassenleitung wählt aus der eigenen Klasse
        return felder

    def save_model(self, request, obj, form, change):
        if not darf_foerderung_bearbeiten(request.user, self.schueler_von(obj)):
            raise PermissionDenied
        if not change and hasattr(obj, "erstellt_von_id") and not obj.erstellt_von_id:
            obj.erstellt_von = request.user
        if change and hasattr(obj, "geaendert_am") and form.has_changed():
            obj.geaendert_am = timezone.now()  # nur echte Inhaltsänderungen zählen
        super().save_model(request, obj, form, change)


class ZielInline(admin.StackedInline):
    model = Foerderziel
    extra = 0
    fields = [("fach", "bereich", "reihenfolge"), "ziel", "massnahmen", ("zustaendig", "bis"), ("ergebnis", "bewertung")]
    autocomplete_fields = ["fach"]
    classes = ["ziele"]

    def has_add_permission(self, request, obj=None):
        return obj is None or darf_foerderung_bearbeiten(request.user, obj.schueler)

    def has_change_permission(self, request, obj=None):
        return obj is None or darf_foerderung_bearbeiten(request.user, obj.schueler)

    has_delete_permission = has_change_permission

    def has_view_permission(self, request, obj=None):
        return True


class EintragInline(admin.TabularInline):
    model = Foerdereintrag
    extra = 0
    fields = ["datum", "art", "text", "verfasst_von"]
    readonly_fields = ["verfasst_von"]
    verbose_name_plural = _("Verlaufsdokumentation (neueste zuerst)")

    def has_add_permission(self, request, obj=None):
        return obj is None or darf_foerderung_sehen(request.user, obj.schueler)

    def has_change_permission(self, request, obj=None):
        return obj is None or darf_foerderung_bearbeiten(request.user, obj.schueler)

    has_delete_permission = has_change_permission

    def has_view_permission(self, request, obj=None):
        return True


class AushaendigungInline(admin.TabularInline):
    model = Aushaendigung
    extra = 0
    fields = ["empfaenger", "ausgehaendigt_am", "weg", "bestaetigt_am", "bestaetigung", "bemerkung", "aktuell"]
    readonly_fields = ["aktuell"]
    verbose_name_plural = _("Aushändigung an Eltern und Bestätigung des Erhalts")

    @admin.display(description=_("Stand"))
    def aktuell(self, obj):
        if obj.pk and obj.veraltet:
            return format_html('<strong style="color:#b45309">{}</strong>', gettext("seither geändert"))
        return "✓" if obj.pk else ""

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "empfaenger":
            schueler_id = getattr(request, "_foerder_schueler_id", None)
            qs = Person.objects.filter(kinder_beziehungen__isnull=False).distinct()
            if schueler_id:
                qs = Person.objects.filter(kinder_beziehungen__schueler_id=schueler_id).distinct()
            kwargs["queryset"] = qs
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def has_add_permission(self, request, obj=None):
        return obj is None or darf_foerderung_bearbeiten(request.user, obj.schueler)

    def has_change_permission(self, request, obj=None):
        return obj is None or darf_foerderung_bearbeiten(request.user, obj.schueler)

    has_delete_permission = has_change_permission

    def has_view_permission(self, request, obj=None):
        return True


class ElternbestaetigungFilter(admin.SimpleListFilter):
    title = _("Elternbestätigung")
    parameter_name = "bestaetigung"

    def lookups(self, request, model_admin):
        return [("fehlt", _("noch nicht ausgehändigt")), ("offen", _("ausgehändigt, Erhalt offen")), ("ok", _("bestätigt"))]

    def queryset(self, request, qs):
        if self.value() == "fehlt":
            return qs.filter(aushaendigungen__isnull=True)
        if self.value() == "offen":
            return qs.filter(aushaendigungen__isnull=False, aushaendigungen__bestaetigt_am__isnull=True).distinct()
        if self.value() == "ok":
            return qs.filter(aushaendigungen__bestaetigt_am__isnull=False).distinct()
        return qs


class SchuelerVorauswahlMixin:
    """Merkt sich die Person des Dokuments, damit bei der Aushändigung nur deren Eltern zur Auswahl stehen."""

    def get_form(self, request, obj=None, **kwargs):
        request._foerder_schueler_id = obj.schueler_id if obj else request.GET.get("schueler")
        return super().get_form(request, obj, **kwargs)


@admin.register(Foerderplan)
class FoerderplanAdmin(SchuelerVorauswahlMixin, FoerderRechteMixin, SimpleHistoryAdmin):
    list_display = ["schueler", "klasse", "titel", "status", "gueltig_von", "evaluation_am", "eltern", "ansicht"]
    list_filter = ["status", "schuljahr", "schwerpunkte", ElternbestaetigungFilter]
    search_fields = ["schueler__person__nachname", "schueler__person__vorname", "titel"]
    autocomplete_fields = ["schueler", "verantwortlich", "vorgaenger"]
    filter_horizontal = ["schwerpunkte", "beteiligte"]
    readonly_fields = ["erstellt_von", "erstellt_am", "geaendert_am"]
    inlines = [ZielInline, EintragInline, AushaendigungInline]
    fieldsets = [
        (None, {"fields": ["schueler", ("schuljahr", "status"), "titel", "schwerpunkte"]}),
        (_("Zeitraum und Zuständigkeit"), {"fields": [("gueltig_von", "gueltig_bis", "evaluation_am"), "verantwortlich", "beteiligte"]}),
        (_("Ausgangslage"), {"fields": ["ausgangslage", "staerken", "grundlagen"]}),
        (_("Vereinbarungen und Evaluation"), {"fields": ["vereinbarungen", "evaluation", "vorgaenger"]}),
        (_("System"), {"fields": [("erstellt_von", "erstellt_am", "geaendert_am")], "classes": ["collapse"]}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("schueler__person", "schuljahr").prefetch_related("aushaendigungen")

    def get_changeform_initial_data(self, request):
        from stammdaten.models import Schuljahr

        daten = super().get_changeform_initial_data(request)
        daten.setdefault("schuljahr", getattr(Schuljahr.aktuelles(), "pk", None))
        daten.setdefault("gueltig_von", timezone.localdate())
        return daten

    @admin.display(description=_("Klasse"))
    def klasse(self, obj):
        k = obj.schueler.stammklasse(obj.schuljahr)
        return k.name if k else "—"

    @admin.display(description=_("Eltern"))
    def eltern(self, obj):
        return elternstatus(obj)

    @admin.display(description="")
    def ansicht(self, obj):
        return format_html('<a href="{}">{}</a>', reverse("foerderplan", args=[obj.pk]), gettext("Ansicht / Druck"))

    def save_formset(self, request, form, formset, change):
        for obj in formset.save(commit=False):
            if isinstance(obj, Foerdereintrag):
                obj.schueler_id = form.instance.schueler_id
                if not obj.verfasst_von_id:
                    obj.verfasst_von = request.user
            if isinstance(obj, Aushaendigung) and not obj.erfasst_von_id:
                obj.erfasst_von = request.user
                if obj.bestaetigt_am and not obj.bestaetigt_durch_konto_id:
                    obj.bestaetigt_durch_konto = request.user
            obj.save()
        formset.save_m2m()
        for obj in formset.deleted_objects:
            obj.delete()

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        if change and any(fs.model is Foerderziel and fs.has_changed() for fs in formsets):
            Foerderplan.objects.filter(pk=form.instance.pk).update(geaendert_am=timezone.now())
        # Aushändigungen speichern den Stand des Dokuments; neu angelegte Pläne erst jetzt vollständig.
        for a in form.instance.aushaendigungen.filter(stand__isnull=True):
            a.save()


def elternstatus(obj):
    farbe = "#166534" if obj.eltern_status == "ok" else "#b45309"
    zeichen = "✓ " if obj.eltern_status == "ok" else ""
    return format_html('<span style="color:{}">{}{}</span>', farbe, zeichen, obj.eltern_status_text)


class AktivFilter(admin.SimpleListFilter):
    title = _("Gültigkeit")
    parameter_name = "gueltig"

    def lookups(self, request, model_admin):
        return [("aktiv", _("aktuell gültig")), ("bald", _("läuft in 30 Tagen ab")), ("abgelaufen", _("abgelaufen"))]

    def queryset(self, request, qs):
        heute = timezone.localdate()
        if self.value() == "aktiv":
            return qs.filter(pk__in=Nachteilsausgleich.aktive().values("pk"))
        if self.value() == "bald":
            from datetime import timedelta

            return qs.filter(pk__in=Nachteilsausgleich.aktive().values("pk"), gueltig_bis__lte=heute + timedelta(days=30))
        if self.value() == "abgelaufen":
            return qs.filter(gueltig_bis__lt=heute)
        return qs


@admin.register(Nachteilsausgleich)
class NachteilsausgleichAdmin(SchuelerVorauswahlMixin, FoerderRechteMixin, SimpleHistoryAdmin):
    sehen_pruefung = staticmethod(darf_nachteilsausgleich_sehen)
    list_display = ["schueler", "klasse", "massnahmen_kurz", "faecher_kurz", "status", "gueltig_von", "gueltig_bis", "eltern", "ansicht"]
    list_filter = [AktivFilter, "status", "massnahmen", "schwerpunkte", ElternbestaetigungFilter]
    search_fields = ["schueler__person__nachname", "schueler__person__vorname"]
    autocomplete_fields = ["schueler", "foerderplan"]
    filter_horizontal = ["massnahmen", "faecher", "schwerpunkte"]
    readonly_fields = ["erstellt_von", "erstellt_am", "geaendert_am"]
    inlines = [AushaendigungInline]
    fieldsets = [
        (None, {"fields": ["schueler", "status", "schwerpunkte", "begruendung"]}),
        (_("Maßnahmen"), {"fields": ["massnahmen", "zeitverlaengerung", "weitere_massnahmen", "faecher"]}),
        (_("Geltung und Beschluss"), {"fields": [("gueltig_von", "gueltig_bis"), ("beschlossen_am", "beschlossen_durch"), "foerderplan"]}),
        (_("System"), {"fields": [("erstellt_von", "erstellt_am", "geaendert_am")], "classes": ["collapse"]}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("schueler__person").prefetch_related(
            "massnahmen", "faecher", "aushaendigungen")

    def get_changeform_initial_data(self, request):
        daten = super().get_changeform_initial_data(request)
        daten.setdefault("gueltig_von", timezone.localdate())
        return daten

    def get_readonly_fields(self, request, obj=None):
        felder = list(super().get_readonly_fields(request, obj))
        if not ist_foerderkoordination(request.user):
            # Klassenleitungen beantragen; genehmigt wird durch Förderkoordination bzw. Schulleitung.
            felder += ["status", "beschlossen_am", "beschlossen_durch"]
        return felder

    @admin.display(description=_("Klasse"))
    def klasse(self, obj):
        k = obj.schueler.stammklasse()
        return k.name if k else "—"

    @admin.display(description=_("Maßnahmen"))
    def massnahmen_kurz(self, obj):
        return "; ".join(obj.massnahmen_liste()) or "—"

    @admin.display(description=_("Fächer"))
    def faecher_kurz(self, obj):
        return obj.faecher_text

    @admin.display(description=_("Eltern"))
    def eltern(self, obj):
        return elternstatus(obj)

    @admin.display(description="")
    def ansicht(self, obj):
        return format_html('<a href="{}">{}</a>', reverse("nachteilsausgleich", args=[obj.pk]), gettext("Ansicht / Druck"))

    def save_formset(self, request, form, formset, change):
        for obj in formset.save(commit=False):
            if isinstance(obj, Aushaendigung) and not obj.erfasst_von_id:
                obj.erfasst_von = request.user
                if obj.bestaetigt_am and not obj.bestaetigt_durch_konto_id:
                    obj.bestaetigt_durch_konto = request.user
            obj.save()
        formset.save_m2m()
        for obj in formset.deleted_objects:
            obj.delete()


@admin.register(Foerdereintrag)
class FoerdereintragAdmin(FoerderRechteMixin, SimpleHistoryAdmin):
    list_display = ["datum", "schueler", "art", "kurztext", "plan", "verfasst_von"]
    list_filter = ["art", ("datum", admin.DateFieldListFilter)]
    search_fields = ["schueler__person__nachname", "text"]
    autocomplete_fields = ["schueler", "plan"]
    readonly_fields = ["verfasst_von", "erstellt_am"]
    date_hierarchy = "datum"

    def has_change_permission(self, request, obj=None):
        # Eigene Einträge dürfen Verfasser:innen korrigieren.
        if obj is not None and obj.verfasst_von_id == request.user.pk and darf_foerderung_sehen(request.user, obj.schueler):
            return admin.ModelAdmin.has_change_permission(self, request, obj)
        return super().has_change_permission(request, obj)

    @admin.display(description=_("Eintrag"))
    def kurztext(self, obj):
        return obj.text[:80] + ("…" if len(obj.text) > 80 else "")

    def save_model(self, request, obj, form, change):
        if not darf_foerderung_sehen(request.user, obj.schueler):
            raise PermissionDenied
        if not obj.verfasst_von_id:
            obj.verfasst_von = request.user
        admin.ModelAdmin.save_model(self, request, obj, form, change)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "schueler" and not ist_foerderkoordination(request.user):
            from portal.rechte import unterrichtete_schueler_ids

            ids = klassenleitung_schueler_ids(request.user) | unterrichtete_schueler_ids(request.user)
            kwargs["queryset"] = Schuelerprofil.objects.filter(pk__in=ids).select_related("person")
            return admin.ModelAdmin.formfield_for_foreignkey(self, db_field, request, **kwargs)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Aushaendigung)
class AushaendigungAdmin(FoerderRechteMixin, SimpleHistoryAdmin):
    schueler_pfad = "foerderplan__schueler"
    list_display = ["ausgehaendigt_am", "schueler_anzeige", "dokument_art", "empfaenger", "weg", "bestaetigt_am", "bestaetigung"]
    list_filter = [("bestaetigt_am", admin.EmptyFieldListFilter), "weg"]
    search_fields = ["empfaenger__nachname", "foerderplan__schueler__person__nachname",
                     "nachteilsausgleich__schueler__person__nachname"]
    autocomplete_fields = ["foerderplan", "nachteilsausgleich", "empfaenger"]
    readonly_fields = ["stand", "erfasst_von", "bestaetigt_durch_konto"]
    actions = ["erhalt_heute_bestaetigen"]

    def schueler_von(self, obj):
        return obj.schueler

    def get_queryset(self, request):
        qs = admin.ModelAdmin.get_queryset(self, request).select_related(
            "foerderplan__schueler__person", "nachteilsausgleich__schueler__person", "empfaenger")
        if ist_foerderkoordination(request.user):
            return qs
        return qs.filter(foerder_schueler_filter(request.user, "foerderplan__schueler")
                         | foerder_schueler_filter(request.user, "nachteilsausgleich__schueler"))

    @admin.display(description=_("Schüler:in"))
    def schueler_anzeige(self, obj):
        return obj.schueler

    @admin.display(description=_("Dokument"))
    def dokument_art(self, obj):
        return obj.dokument_art

    @admin.action(description=_("Erhalt heute bestätigt (Unterschrift liegt vor)"))
    def erhalt_heute_bestaetigen(self, request, queryset):
        n = 0
        for a in queryset.filter(bestaetigt_am__isnull=True):
            if darf_foerderung_bearbeiten(request.user, a.schueler):
                a.bestaetigt_am = max(timezone.localdate(), a.ausgehaendigt_am)
                a.bestaetigung = "unterschrift"
                a.bestaetigt_durch_konto = request.user
                a.save()
                n += 1
        self.message_user(request, gettext("%(n)s Bestätigung(en) erfasst.") % {"n": n}, messages.SUCCESS)

    def save_model(self, request, obj, form, change):
        if not darf_foerderung_bearbeiten(request.user, obj.schueler):
            raise PermissionDenied
        if not obj.erfasst_von_id:
            obj.erfasst_von = request.user
        if obj.bestaetigt_am and not obj.bestaetigt_durch_konto_id:
            obj.bestaetigt_durch_konto = request.user
        admin.ModelAdmin.save_model(self, request, obj, form, change)
