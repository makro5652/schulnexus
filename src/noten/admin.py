from django.contrib import admin
from django.urls import reverse
from django.utils import formats
from django.utils.html import format_html
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from simple_history.admin import SimpleHistoryAdmin
from stammdaten.filter import jahrgangsfilter, klassenfilter

from portal.suchauswahl import SuchauswahlAdminMixin

from portal.rechte import ist_verwaltung

from .berechnung import nominale_anteile
from .models import (
    Notenschluss,
    Bewertungsordner,
    Klausurregel,
    Notensperre,
    Zeugnisnotenfreigabe,
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

    @admin.display(description=_("Kategorien"))
    def kategorien_text(self, obj):
        return ", ".join(str(k) for k in obj.kategorien.all())


class EigeneDatenMixin:
    """Lehrkräfte sehen nur ihren eigenen Unterricht; Verwaltung und Leitung sehen alles."""

    unterricht_pfad = "unterricht"

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if ist_verwaltung(request.user):
            return qs
        return qs.filter(**{f"{self.unterricht_pfad}__lehrkraft__person__benutzer": request.user})


def eigene_unterrichte(request):
    qs = Unterricht.objects.select_related("fach", "gruppe", "abschnitt", "lehrkraft")
    return qs if ist_verwaltung(request.user) else qs.filter(lehrkraft__person__benutzer=request.user)


def eigene_ordner(request):
    return Bewertungsordner.objects.filter(unterricht__in=eigene_unterrichte(request)).select_related(
        "unterricht__fach", "unterricht__gruppe", "eltern__eltern__eltern__eltern"
    )


class EigenerUnterrichtFilter(admin.SimpleListFilter):
    title = _("Unterricht")
    parameter_name = "unterricht"

    def lookups(self, request, model_admin):
        return [(u.pk, str(u)) for u in eigene_unterrichte(request)]

    def queryset(self, request, queryset):
        return queryset.filter(unterricht_id=self.value()) if self.value() else queryset


class OberordnerInline(admin.TabularInline):
    model = Bewertungsordner
    extra = 0
    fields = ["name", "eltern", "gewicht", "reihenfolge"]
    verbose_name_plural = _("Bewertungsordner")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "eltern":
            uid = request.resolver_match.kwargs.get("object_id")
            kwargs["queryset"] = Bewertungsordner.objects.filter(unterricht_id=uid) if uid else Bewertungsordner.objects.none()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Klausurregel)
class KlausurregelAdmin(SuchauswahlAdminMixin, SimpleHistoryAdmin):
    list_display = ["__str__", "anteil_klausur", "bemerkung"]


@admin.register(Zeugnisnotenfreigabe)
class ZeugnisnotenfreigabeAdmin(SuchauswahlAdminMixin, SimpleHistoryAdmin):
    list_display = ["__str__", "bemerkung", "geaendert_am"]


@admin.register(Notensperre)
class NotensperreAdmin(SimpleHistoryAdmin):
    list_display = ["klasse", "abschnitt", "gesperrt", "geaendert_von", "geaendert_am"]
    list_filter = ["abschnitt", "gesperrt"]


@admin.register(Unterricht)
class UnterrichtAdmin(admin.ModelAdmin):
    list_display = ["__str__", "gruppe", "fach", "lehrkraft", "links"]
    list_filter = ["abschnitt", "fach", "gruppe__jahrgang"]
    search_fields = ["gruppe__name", "fach__name", "lehrkraft__kuerzel"]
    autocomplete_fields = ["gruppe", "lehrkraft"]
    inlines = [OberordnerInline]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if ist_verwaltung(request.user):
            return qs
        return qs.filter(lehrkraft__person__benutzer=request.user)

    @admin.display(description=_("Noten"))
    def links(self, obj):
        return format_html(
            '<a href="{}">{}</a> · <a href="{}?unterricht={}">{}</a>',
            reverse("notenuebersicht", args=[obj.pk]), gettext("Notenübersicht"),
            reverse("admin:noten_bewertungsordner_changelist"), obj.pk, gettext("Bewertungsordner"),
        )


class LeistungsnachweisInline(admin.TabularInline):
    model = Leistungsnachweis
    extra = 1
    fields = ["titel", "datum", "gewicht", "schluessel", "max_be"]
    show_change_link = True
    verbose_name = _("Leistungsnachweis in diesem Ordner")
    verbose_name_plural = _("Leistungsnachweise in diesem Ordner (Noten über „Ändern“ eintragen)")


@admin.register(Bewertungsordner)
class BewertungsordnerAdmin(SimpleHistoryAdmin):
    list_display = ["pfad_anzeige", "unterricht", "gewicht", "anteil", "anzahl_nachweise"]

    def get_readonly_fields(self, request, obj=None):
        # Vorgaben der Schulleitung (Klausurregel) und Kurse mit gesperrten Noten (ab 0.4.8.0)
        if obj is not None and (obj.vorgegeben or _kurs_gesperrt(obj.unterricht)):
            return ["unterricht", "eltern", "name", "gewicht"] + (["gewichtsart", "reihenfolge"] if _kurs_gesperrt(obj.unterricht) else [])
        return []

    def has_delete_permission(self, request, obj=None):
        if obj is not None and (obj.vorgegeben or _kurs_gesperrt(obj.unterricht)):
            return False
        return super().has_delete_permission(request, obj)
    list_filter = [EigenerUnterrichtFilter]
    search_fields = ["name", "unterricht__gruppe__name", "unterricht__fach__name"]
    fields = ["unterricht", "eltern", "name", "gewicht", "gewichtsart", "reihenfolge", "beschreibung"]
    inlines = [LeistungsnachweisInline]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(pk__in=eigene_ordner(request).values("pk")).select_related(
            "unterricht__fach", "unterricht__gruppe", "unterricht__lehrkraft", "unterricht__abschnitt", "eltern__eltern__eltern"
        )

    def get_changeform_initial_data(self, request):
        daten = super().get_changeform_initial_data(request)
        for feld in ("unterricht", "eltern"):
            if request.GET.get(feld):
                daten[feld] = request.GET[feld]
        return daten

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "unterricht":
            kwargs["queryset"] = eigene_unterrichte(request)
        if db_field.name == "eltern":
            qs = eigene_ordner(request)
            oid = request.resolver_match.kwargs.get("object_id")
            if oid:
                eigener = Bewertungsordner.objects.filter(pk=oid).first()
                qs = qs.filter(unterricht_id=eigener.unterricht_id).exclude(pk=oid) if eigener else qs
            elif request.GET.get("unterricht"):
                qs = qs.filter(unterricht_id=request.GET["unterricht"])
            kwargs["queryset"] = qs
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description=_("Ordner"), ordering="name")
    def pfad_anzeige(self, obj):
        return obj.pfad

    @admin.display(description=_("Anteil an der Gesamtnote"))
    def anteil(self, obj):
        ordner = list(Bewertungsordner.objects.filter(unterricht_id=obj.unterricht_id))
        nachweise = list(Leistungsnachweis.objects.filter(unterricht_id=obj.unterricht_id))
        wert = nominale_anteile(ordner, nachweise)[0].get(obj.pk)
        return f"{formats.number_format(wert, 1)} %" if wert is not None else "—"

    @admin.display(description=_("Leistungsnachweise"))
    def anzahl_nachweise(self, obj):
        return obj.leistungsnachweise.count()

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        if formset.model is Leistungsnachweis:
            neu = sum(ln.notenzeilen_anlegen() for ln in form.instance.leistungsnachweise.all())
            if neu:
                self.message_user(request, gettext("%(n)s Notenzeilen angelegt – Noten über „Ändern“ beim Leistungsnachweis eintragen.") % {"n": neu})


class NoteInline(admin.TabularInline):
    model = Note
    extra = 0
    fields = ["schueler", "erreichte_be", "stufe", "sonderstatus", "gewicht_individuell", "gewicht_begruendung", "kommentar"]
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


def _kurs_gesperrt(unterricht):
    from .sperre import gesperrte_schueler

    return bool(gesperrte_schueler(unterricht))


def _ln_gesperrt(ln):
    """Hängen an diesem Leistungsnachweis Noten gesperrter Schüler:innen?"""
    from .sperre import gesperrte_schueler

    ids = list(ln.noten.exclude(stufe__isnull=True, sonderstatus="").values_list("schueler_id", flat=True))
    return bool(ids and gesperrte_schueler(ln.unterricht, ids))


@admin.register(Leistungsnachweis)
class LeistungsnachweisAdmin(EigeneDatenMixin, SimpleHistoryAdmin):
    list_display = ["titel", "ordner_pfad", "unterricht", "datum", "gewicht", "anzahl_noten"]
    list_filter = [EigenerUnterrichtFilter, "unterricht__abschnitt"]
    search_fields = ["titel", "ordner__name", "unterricht__gruppe__name"]
    fields = ["ordner", "titel", "datum", "gewicht", "schluessel", "max_be"]
    inlines = [NoteInline]

    @admin.display(description=_("Ordner"), ordering="ordner__name")
    def ordner_pfad(self, obj):
        return obj.ordner.pfad

    @admin.display(description=_("Noten erfasst"))
    def anzahl_noten(self, obj):
        return obj.noten.exclude(stufe__isnull=True, sonderstatus="").count()

    def get_changeform_initial_data(self, request):
        daten = super().get_changeform_initial_data(request)
        if request.GET.get("ordner"):
            daten["ordner"] = request.GET["ordner"]
        return daten

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "ordner":
            kwargs["queryset"] = eigene_ordner(request)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def has_change_permission(self, request, obj=None):
        if obj is not None and _ln_gesperrt(obj):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None and _ln_gesperrt(obj):
            return False
        return super().has_delete_permission(request, obj)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        neu = form.instance.notenzeilen_anlegen()
        if neu:
            self.message_user(request, gettext("%(n)s Notenzeilen angelegt – bitte jetzt die Noten eintragen.") % {"n": neu})


@admin.register(Note)
class NoteAdmin(EigeneDatenMixin, SimpleHistoryAdmin):
    unterricht_pfad = "leistungsnachweis__unterricht"
    list_display = ["schueler", "leistungsnachweis", "erreichte_be", "stufe", "sonderstatus", "gewicht_individuell"]
    list_filter = [klassenfilter("schueler"), jahrgangsfilter("schueler"), "leistungsnachweis__unterricht__abschnitt", "leistungsnachweis__unterricht__fach"]
    search_fields = ["schueler__person__nachname", "leistungsnachweis__titel"]
    autocomplete_fields = ["schueler", "leistungsnachweis"]

    def has_change_permission(self, request, obj=None):
        from .sperre import ist_gesperrt

        if obj is not None and ist_gesperrt(obj, obj.leistungsnachweis.unterricht):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        from .sperre import ist_gesperrt

        if obj is not None and ist_gesperrt(obj, obj.leistungsnachweis.unterricht):
            return False
        return super().has_delete_permission(request, obj)


@admin.register(Zeugnisnote)
class ZeugnisnoteAdmin(EigeneDatenMixin, SimpleHistoryAdmin):
    list_display = ["schueler", "unterricht", "vorschlag", "stufe", "vermerk"]
    list_filter = [klassenfilter("schueler"), jahrgangsfilter("schueler"), "unterricht__abschnitt", "unterricht__fach", "unterricht__gruppe"]
    search_fields = ["schueler__person__nachname"]
    autocomplete_fields = ["schueler", "unterricht"]

    def has_change_permission(self, request, obj=None):
        from .sperre import ist_gesperrt

        if obj is not None and ist_gesperrt(obj, obj.unterricht):
            return False
        return super().has_change_permission(request, obj)


@admin.register(Notenschluss)
class NotenschlussAdmin(SimpleHistoryAdmin):
    list_display = ["abschnitt", "jahrgang_von", "jahrgang_bis", "datum", "angelegt_von"]
    list_filter = ["abschnitt"]
