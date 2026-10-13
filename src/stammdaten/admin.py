from django.contrib import admin
from django.urls import reverse
from django.utils import timezone
from django.utils import formats
from django.utils.html import format_html
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from simple_history.admin import SimpleHistoryAdmin

from portal.rechte import ist_personalverwaltung, ist_verwaltung

from .models import (
    Abschluss,
    Abschlussart,
    Abschnitt,
    Beziehung,
    Bildungsgang,
    Dienstleister,
    Dokument,
    Einwilligung,
    Elternprofil,
    Fach,
    Fortbildung,
    Gesundheitsangaben,
    Gruppe,
    Laufbahnabschnitt,
    Mitgliedschaft,
    Nachweis,
    Nachweisart,
    Notfallkontakt,
    Person,
    Personalabwesenheit,
    Personalbereich,
    Personalprofil,
    Schuelerprofil,
    Schuljahr,
    Sprachenfolge,
    VorherigeSchule,
    Zusatzfeld,
)
from .zusatzfelder import ZusatzfelderAdminMixin, ZusatzfelderInlineMixin, zusatz_fieldsets

admin.site.site_header = _("Schulverwaltung")
admin.site.site_title = _("Schulverwaltung")
admin.site.index_title = _("Verwaltung")
admin.site.enable_nav_sidebar = False  # volle Breite für Tabellen; Navigation über Startseite und Brotkrumen


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
    verbose_name_plural = _("Schülerprofil (vollständige Akte über „Ändern“)")


class PersonalprofilKurzInline(admin.StackedInline):
    model = Personalprofil
    extra = 0
    max_num = 1
    fields = ["bereich", "stellenbezeichnung", "kuerzel", "aktiv"]
    show_change_link = True
    verbose_name_plural = _("Personalprofil (vollständige Personalakte über „Ändern“)")


class ElternprofilInline(ZusatzfelderInlineMixin, admin.StackedInline):
    zusatz_zielgruppe = "eltern"
    model = Elternprofil
    extra = 0
    max_num = 1
    verbose_name_plural = _("Elternprofil (für Erziehungsberechtigte)")
    fieldsets = [(None, {"fields": [("beruf", "arbeitgeber"), "korrespondenzweg",
                                    ("schulverein_mitglied", "mitgliedsnummer"), "elternvertretung", "kontaktdaten_weitergabe"]})]


class KinderInline(admin.TabularInline):
    model = Beziehung
    fk_name = "person"
    extra = 0
    verbose_name = _("Kind (Schüler:in)")
    verbose_name_plural = _("Ist Erziehungsberechtigte:r / Kontaktperson von")
    autocomplete_fields = ["schueler"]
    fields = ["schueler", "art", "sorgerecht", "auskunftsrecht", "abholberechtigt", "notfallkontakt", "rechnungsempfaenger"]


class DokumentInline(admin.TabularInline):
    model = Dokument
    extra = 0
    fields = ["hochgeladen_am", "kategorie", "titel", "datei", "zugriffsstufe", "aufbewahren_bis"]
    readonly_fields = ["hochgeladen_am"]
    verbose_name_plural = _("Anhänge (neueste zuerst)")

    def get_queryset(self, request):
        from portal.rechte import sichtbare_dokumente

        return sichtbare_dokumente(request.user, super().get_queryset(request))


PERSON_FIELDSETS = [
    (_("Name"), {"fields": [("anrede", "titel"), ("vorname", "rufname", "nachname"), "geschlecht"]}),
    (_("Geburt und Herkunft"), {"fields": [("geburtsdatum", "geburtsort", "geburtsland"), "geburtstag_anzeigen", "staatsangehoerigkeiten"]}),
    (_("Kontakt"), {"fields": [("email", "sprache"), ("telefon", "mobil", "telefon_dienstlich")]}),
    (_("Anschrift"), {"fields": ["strasse", ("postfach", "plz"), ("ort", "land")]}),
    (_("System"), {"fields": ["benutzer", "notizen"], "classes": ["collapse"]}),
]


class RolleFilter(admin.SimpleListFilter):
    title = _("Rolle")
    parameter_name = "rolle"

    def lookups(self, request, model_admin):
        return [("schueler", _("Schüler:innen")), ("eltern", _("Eltern / Kontaktpersonen")), ("personal", _("Personal"))]

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

    @admin.display(description=_("Rolle"))
    def rolle(self, obj):
        rollen = []
        if hasattr(obj, "schueler"):
            rollen.append(gettext("Schüler:in"))
        if hasattr(obj, "personal"):
            rollen.append(obj.personal.stellenbezeichnung or (obj.personal.bereich.lokal_name if obj.personal.bereich else gettext("Personal")))
        if obj.kinder_beziehungen.exists():
            rollen.append(gettext("Eltern / Kontakt"))
        return ", ".join(rollen) or "—"

    @admin.display(description=_("Telefon"))
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
    verbose_name_plural = _("Eltern / Erziehungsberechtigte / Kontaktpersonen")


class MitgliedschaftInline(admin.TabularInline):
    model = Mitgliedschaft
    extra = 0
    autocomplete_fields = ["gruppe"]
    fields = ["gruppe", "von", "bis", "rolle"]
    verbose_name_plural = _("Klassen und Gruppen")


class EinwilligungInline(admin.TabularInline):
    model = Einwilligung
    extra = 0
    autocomplete_fields = ["erteilt_durch"]


class LaufbahnInline(admin.TabularInline):
    model = Laufbahnabschnitt
    extra = 0
    fields = ["schuljahr", "jahrgang", "bildungsgang", "stammklasse", "von", "bis", "ergebnis", "bemerkung"]
    verbose_name_plural = _("Schullaufbahn")


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
    verbose_name_plural = _("Gesundheitsangaben (vertraulich)")
    fieldsets = [(None, {"fields": [("allergien", "erkrankungen"), "medikamente", "notfallhinweise",
                                    ("arzt", "krankenversicherung"), "schwimmen_erlaubt"]})]


class StammklasseFilter(admin.SimpleListFilter):
    title = _("Stammklasse (aktuell)")
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
    title = _("Bildungsgang (aktuelles Schuljahr)")
    parameter_name = "bildungsgang"

    def lookups(self, request, model_admin):
        return [(b.pk, b.name) for b in Bildungsgang.objects.all()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(laufbahn__bildungsgang_id=self.value(), laufbahn__schuljahr__aktiv=True).distinct()
        return queryset


@admin.register(Schuelerprofil)
class SchuelerprofilAdmin(ZusatzfelderAdminMixin, SimpleHistoryAdmin):
    zusatz_zielgruppe = "schueler"
    list_display = ["person", "schuelernummer", "klasse", "bildungsgang", "status", "akte"]
    list_filter = ["status", StammklasseFilter, BildungsgangFilter, "daz", "nachteilsausgleich"]
    search_fields = ["person__nachname", "person__vorname", "schuelernummer"]
    autocomplete_fields = ["person"]
    fieldsets = [
        (_("Schüler:in"), {"fields": ["person", ("schuelernummer", "status")]}),
        (_("Eintritt und Austritt"), {"fields": [("eintrittsdatum", "eintritt_jahrgang"), ("austrittsdatum", "austrittsgrund")]}),
        (_("Sprache und Förderung"), {"fields": [("muttersprache", "familiensprache"), ("daz", "nachteilsausgleich"),
                                              "foerderbedarf", "religionsunterricht"]}),
        (_("Organisatorisches"), {"fields": ["lebt_bei", ("schulweg", "buslinie"), "abholhinweise", "bemerkungen"]}),
    ]

    def get_inlines(self, request, obj):
        inlines = [LaufbahnInline, MitgliedschaftInline, BeziehungInline, AbschlussInline,
                   SprachenfolgeInline, VorherigeSchuleInline, EinwilligungInline]
        if request.user.has_perm("stammdaten.view_gesundheitsangaben"):
            inlines.append(GesundheitInline)
        return inlines

    @admin.display(description=_("Stammklasse"))
    def klasse(self, obj):
        g = obj.stammklasse()
        return g.name if g else "—"

    @admin.display(description=_("Bildungsgang"))
    def bildungsgang(self, obj):
        abschnitt = obj.aktueller_laufbahnabschnitt()
        return abschnitt.bildungsgang.kuerzel if abschnitt else "—"

    @admin.display(description=_("Akte"))
    def akte(self, obj):
        return format_html('<a href="{}">{}</a>', reverse("schuelerakte", args=[obj.pk]), gettext("Schülerakte"))


# ---------------------------------------------------------------- Personal

class FortbildungInline(admin.TabularInline):
    model = Fortbildung
    extra = 0


class NotfallkontaktInline(admin.TabularInline):
    model = Notfallkontakt
    extra = 0


class NachweisInline(admin.TabularInline):
    model = Nachweis
    extra = 0
    fields = ["art", "ausgestellt_am", "gueltig_bis", "datei", "bemerkung", "status_anzeige"]
    readonly_fields = ["status_anzeige"]

    @admin.display(description=_("Status"))
    def status_anzeige(self, obj):
        if not obj.pk:
            return "—"
        return status_etikett(next((st for a, st, n in obj.personal.nachweisstatus() if n and n.pk == obj.pk), "gueltig"))


class AbwesenheitInline(admin.TabularInline):
    model = Personalabwesenheit
    extra = 0
    fields = ["art", "von", "bis", "halbtags", "status", "bemerkung"]


STATUS_TEXT = {"fehlt": _("fehlt"), "abgelaufen": _("abgelaufen"), "laeuft_ab": _("läuft bald ab"), "gueltig": _("gültig")}
STATUS_FARBE = {"fehlt": "#b4532a", "abgelaufen": "#b4532a", "laeuft_ab": "#9a6b00", "gueltig": "#1f5f5b"}


def status_etikett(status):
    return format_html('<strong style="color:{}">{}</strong>', STATUS_FARBE[status], STATUS_TEXT[status])


class NachweisFilter(admin.SimpleListFilter):
    title = _("Nachweise")
    parameter_name = "nachweise"

    def lookups(self, request, model_admin):
        return [("offen", _("fehlend, abgelaufen oder bald ablaufend")), ("ok", _("vollständig und gültig"))]

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        offen = [p.pk for p in queryset.select_related("bereich") if p.offene_nachweise()]
        return queryset.filter(pk__in=offen) if self.value() == "offen" else queryset.exclude(pk__in=offen)


@admin.register(Personalprofil)
class PersonalprofilAdmin(ZusatzfelderAdminMixin, SimpleHistoryAdmin):
    zusatz_zielgruppe = "personal"
    list_display = ["person", "bereich", "stellenbezeichnung", "kuerzel"]
    list_filter = ["bereich", "anstellungsart", "dienstleister", "aktiv", "lehrbefaehigungen"]
    search_fields = ["kuerzel", "person__nachname", "person__vorname", "personalnummer", "stellenbezeichnung", "ausweisnummer"]
    autocomplete_fields = ["person", "vorgesetzt"]
    filter_horizontal = ["lehrbefaehigungen"]
    list_select_related = ["person", "bereich"]

    def _hr(self, request):
        return ist_personalverwaltung(request.user) or request.user.has_perm("stammdaten.view_hr_daten")

    def get_list_display(self, request):
        spalten = list(super().get_list_display(request))
        if self._hr(request):
            spalten.insert(4, "nachweise_anzeige")
        return spalten

    def get_list_filter(self, request):
        filter_ = list(super().get_list_filter(request))
        return filter_ + [NachweisFilter] if self._hr(request) else filter_

    def get_fieldsets(self, request, obj=None):
        basis = [
            (_("Person und Einsatz"), {"fields": ["person", ("bereich", "stellenbezeichnung"), ("kuerzel", "aktiv"), "vorgesetzt"]}),
            (_("Tätigkeit"), {"fields": ["lehrbefaehigungen", "weitere_funktionen", ("dienst_email", "raum"), "ausweisnummer"]}),
        ]
        if obj is not None and obj.bereich_id and not obj.bereich.unterrichtet:
            basis[1][1]["fields"] = basis[1][1]["fields"][1:]  # Lehrbefähigungen nur bei unterrichtendem Personal
        if self._hr(request):
            basis.insert(1, (_("Dienstverhältnis (HR)"), {"fields": [
                ("personalnummer", "anstellungsart"), "dienstleister", ("dienstbeginn", "vertragsende"),
                ("wochenstunden", "ermaessigung"), "arbeitszeit", "arbeitserlaubnis_bis"]}))
            basis.append((_("Intern (HR)"), {"fields": ["bemerkungen"], "classes": ["collapse"]}))
        return basis + zusatz_fieldsets(self._zusatz_definitionen(request))

    def get_inlines(self, request, obj):
        inlines = [NotfallkontaktInline, FortbildungInline]
        if self._hr(request):
            inlines = [NachweisInline, AbwesenheitInline] + inlines
        return inlines

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if ist_verwaltung(request.user) or ist_personalverwaltung(request.user):
            return qs
        return qs.filter(person__benutzer=request.user)

    @admin.display(description=_("Nachweise"))
    def nachweise_anzeige(self, obj):
        offen = obj.offene_nachweise()
        if not offen:
            return status_etikett("gueltig")
        schlimmster = min(offen, key=lambda t: ["fehlt", "abgelaufen", "laeuft_ab"].index(t[1]))
        return format_html('<span title="{}">{} ({})</span>', "; ".join(f"{a.lokal_name}: {STATUS_TEXT[st]}" for a, st, n in offen),
                           status_etikett(schlimmster[1]), len(offen))


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

    @admin.display(description=_("Mitglieder (aktuell)"))
    def anzahl_mitglieder(self, obj):
        return Mitgliedschaft.objects.aktiv().filter(gruppe=obj).count()

    @admin.action(description=_("Alle Schüler:innen der Ursprungs-Stammklassen hinzufügen"))
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
        self.message_user(request, gettext("%(n)s Mitgliedschaften angelegt. Danach bitte Abwählende wieder entfernen.") % {"n": neu})


@admin.register(Mitgliedschaft)
class MitgliedschaftAdmin(SimpleHistoryAdmin):
    list_display = ["schueler", "gruppe", "von", "bis", "rolle"]
    list_filter = ["gruppe__schuljahr", "gruppe__typ", "gruppe"]
    search_fields = ["schueler__person__nachname", "gruppe__name"]
    autocomplete_fields = ["schueler", "gruppe"]


@admin.register(Fach)
class FachAdmin(admin.ModelAdmin):
    list_display = ["kuerzel", "name", "name_en", "reihenfolge"]
    list_editable = ["reihenfolge"]
    search_fields = ["kuerzel", "name", "name_en"]


@admin.register(Beziehung)
class BeziehungAdmin(SimpleHistoryAdmin):
    list_display = ["schueler", "person", "art", "sorgerecht", "notfallkontakt", "rechnungsempfaenger"]
    list_filter = ["art", "sorgerecht", "notfallkontakt", "rechnungsempfaenger"]
    search_fields = ["schueler__person__nachname", "person__nachname"]
    autocomplete_fields = ["schueler", "person"]


@admin.register(Einwilligung)
class EinwilligungAdmin(SimpleHistoryAdmin):
    list_display = ["schueler", "zweck", "erteilt_am", "widerrufen_am", "gueltig"]
    list_filter = ["zweck"]
    search_fields = ["schueler__person__nachname"]
    autocomplete_fields = ["schueler", "erteilt_durch"]

    @admin.display(boolean=True, description=_("Gültig"))
    def gueltig(self, obj):
        return obj.gueltig


@admin.register(Dokument)
class DokumentAdmin(SimpleHistoryAdmin):
    list_display = ["hochgeladen_am", "titel", "person", "kategorie", "zugriffsstufe", "datei_info", "hochgeladen_von"]
    list_display_links = ["hochgeladen_am", "titel"]
    list_filter = ["kategorie", "zugriffsstufe", ("hochgeladen_am", admin.DateFieldListFilter)]
    search_fields = ["titel", "notiz", "originalname", "person__nachname", "person__vorname"]
    autocomplete_fields = ["person"]
    readonly_fields = ["hochgeladen_am", "hochgeladen_von", "originalname", "groesse_anzeige", "inhaltstyp"]
    fields = ["person", ("titel", "kategorie"), "datei", "notiz", ("zugriffsstufe", "aufbewahren_bis"),
              ("hochgeladen_am", "hochgeladen_von"), ("originalname", "groesse_anzeige", "inhaltstyp")]
    date_hierarchy = "hochgeladen_am"
    ordering = ["-hochgeladen_am", "-pk"]

    def get_queryset(self, request):
        from portal.rechte import sichtbare_dokumente

        return sichtbare_dokumente(request.user, super().get_queryset(request).select_related("person", "hochgeladen_von"))

    @admin.display(description=_("Datei"))
    def datei_info(self, obj):
        if not obj.datei:
            return gettext("Notiz")
        return format_html('<a href="{}">{}</a> <span class="quiet">{}</span>',
                           reverse("anhang", args=[obj.pk]), obj.dateiendung or "?", obj.groesse_lesbar)

    @admin.display(description=_("Größe"))
    def groesse_anzeige(self, obj):
        return obj.groesse_lesbar or "—"

    def save_model(self, request, obj, form, change):
        if not obj.hochgeladen_von_id:
            obj.hochgeladen_von = request.user
        super().save_model(request, obj, form, change)


@admin.register(Bildungsgang)
class BildungsgangAdmin(admin.ModelAdmin):
    list_display = ["kuerzel", "name", "name_en", "angestrebter_abschluss", "jahrgang_von", "jahrgang_bis", "reihenfolge"]
    list_editable = ["reihenfolge"]


@admin.register(Abschlussart)
class AbschlussartAdmin(admin.ModelAdmin):
    list_display = ["kuerzel", "name", "name_en", "reihenfolge"]
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
class ElternprofilAdmin(ZusatzfelderAdminMixin, SimpleHistoryAdmin):
    zusatz_zielgruppe = "eltern"
    fieldsets = [(None, {"fields": ["person", ("beruf", "arbeitgeber"), "korrespondenzweg",
                                    ("schulverein_mitglied", "mitgliedsnummer"), "elternvertretung", "kontaktdaten_weitergabe"]})]
    list_display = ["person", "beruf", "korrespondenzweg", "schulverein_mitglied", "elternvertretung"]
    list_filter = ["schulverein_mitglied", "korrespondenzweg"]
    search_fields = ["person__nachname", "person__vorname", "beruf"]
    autocomplete_fields = ["person"]


@admin.register(Gesundheitsangaben)
class GesundheitsangabenAdmin(SimpleHistoryAdmin):
    list_display = ["schueler", "allergien", "medikamente", "schwimmen_erlaubt"]
    search_fields = ["schueler__person__nachname"]
    autocomplete_fields = ["schueler"]


@admin.register(Personalbereich)
class PersonalbereichAdmin(admin.ModelAdmin):
    list_display = ["name", "name_en", "kuerzel", "unterrichtet", "anzahl", "reihenfolge"]
    list_editable = ["reihenfolge"]

    @admin.display(description=_("Personen (aktiv)"))
    def anzahl(self, obj):
        return obj.personal.filter(aktiv=True).count()


@admin.register(Dienstleister)
class DienstleisterAdmin(admin.ModelAdmin):
    list_display = ["name", "leistung", "ansprechperson", "telefon", "vertrag_bis", "anzahl"]
    search_fields = ["name", "leistung"]

    @admin.display(description=_("Eingesetzte Personen"))
    def anzahl(self, obj):
        return obj.personal.filter(aktiv=True).count()


@admin.register(Nachweisart)
class NachweisartAdmin(admin.ModelAdmin):
    list_display = ["name", "name_en", "gueltigkeit_monate", "pflicht_text", "reihenfolge"]
    list_editable = ["reihenfolge"]
    filter_horizontal = ["pflicht_fuer"]

    @admin.display(description=_("Pflicht für"))
    def pflicht_text(self, obj):
        return ", ".join(b.lokal_name for b in obj.pflicht_fuer.all()) or "—"


@admin.register(Nachweis)
class NachweisAdmin(SimpleHistoryAdmin):
    list_display = ["personal", "art", "ausgestellt_am", "gueltig_bis"]
    list_filter = ["art", "personal__bereich"]
    search_fields = ["personal__person__nachname", "personal__person__vorname"]
    autocomplete_fields = ["personal"]
    date_hierarchy = "gueltig_bis"


@admin.register(Personalabwesenheit)
class PersonalabwesenheitAdmin(SimpleHistoryAdmin):
    list_display = ["personal", "art", "von", "bis", "arbeitstage_anzeige", "status"]
    list_filter = ["art", "status", "personal__bereich"]
    search_fields = ["personal__person__nachname", "personal__person__vorname"]
    autocomplete_fields = ["personal"]
    date_hierarchy = "von"

    @admin.display(description=_("Arbeitstage"))
    def arbeitstage_anzeige(self, obj):
        return formats.number_format(obj.arbeitstage)


@admin.register(Zusatzfeld)
class ZusatzfeldAdmin(admin.ModelAdmin):
    list_display = ["name", "zielgruppe", "typ", "abschnitt", "pflicht", "sichtbarkeit", "in_liste", "reihenfolge", "aktiv"]
    list_editable = ["reihenfolge", "aktiv", "in_liste"]
    list_filter = ["zielgruppe", "typ", "sichtbarkeit", "aktiv"]
    search_fields = ["name", "abschnitt"]
    fieldsets = [
        (None, {"fields": [("zielgruppe", "name"), "schluessel", ("typ", "pflicht"), "optionen", "abschnitt", "hilfetext"]}),
        (_("Englische Bezeichnungen"), {"fields": ["name_en", "optionen_en", "abschnitt_en", "hilfetext_en"], "classes": ["collapse"]}),
        (_("Sichtbarkeit und Anzeige"), {"fields": ["sichtbarkeit", ("in_liste", "reihenfolge", "aktiv")]}),
    ]

    def get_readonly_fields(self, request, obj=None):
        return ["zielgruppe", "schluessel"] if obj else []

    def _nur_personal(self, request):
        return not ist_verwaltung(request.user) and ist_personalverwaltung(request.user)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(zielgruppe="personal") if self._nur_personal(request) else qs

    def formfield_for_choice_field(self, db_field, request, **kwargs):
        if db_field.name == "zielgruppe" and self._nur_personal(request):
            kwargs["choices"] = [("personal", "Personal")]
        return super().formfield_for_choice_field(db_field, request, **kwargs)
