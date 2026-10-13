from django.contrib import admin, messages
from django.utils.translation import gettext, gettext_lazy as _
from simple_history.admin import SimpleHistoryAdmin

from .models import AGAngebot, AGWahl, AGZuteilung
from .zuteilung import lose_zuteilen


class WahlInline(admin.TabularInline):
    model = AGWahl
    extra = 0
    autocomplete_fields = ["schueler"]


class ZuteilungInline(admin.TabularInline):
    model = AGZuteilung
    extra = 0
    autocomplete_fields = ["schueler"]
    readonly_fields = ["erfuellter_wunsch"]


@admin.register(AGAngebot)
class AGAngebotAdmin(SimpleHistoryAdmin):
    list_display = ["titel", "wochentag", "beginn", "ende", "leitung", "plaetze", "erstwuensche", "anmeldung_offen"]
    list_filter = ["abschnitt", "wochentag", "anmeldung_offen"]
    search_fields = ["titel"]
    autocomplete_fields = ["leitung"]
    inlines = [WahlInline, ZuteilungInline]
    actions = ["losverfahren"]

    @admin.display(description=_("Belegt / Plätze"))
    def plaetze(self, obj):
        return f"{obj.belegt} / {obj.kapazitaet}"

    @admin.display(description=_("Erstwünsche"))
    def erstwuensche(self, obj):
        return obj.wahlen.filter(prioritaet=1).count()

    @admin.action(description=_("Plätze per Losverfahren zuteilen (Halbjahr der Auswahl)"))
    def losverfahren(self, request, queryset):
        for abschnitt in {a.abschnitt for a in queryset}:
            ergebnis = lose_zuteilen(abschnitt)
            z = ergebnis.zugeteilt
            self.message_user(
                request,
                gettext("%(abschnitt)s: %(e1)s Erstwünsche, %(e2)s Zweitwünsche, %(e3)s Drittwünsche erfüllt; %(ohne)s ohne Platz.")
                % {"abschnitt": abschnitt, "e1": z[1], "e2": z[2], "e3": z[3], "ohne": len(ergebnis.ohne_platz)},
                messages.WARNING if ergebnis.ohne_platz else messages.SUCCESS,
            )


@admin.register(AGWahl)
class AGWahlAdmin(admin.ModelAdmin):
    list_display = ["schueler", "angebot", "prioritaet"]
    list_filter = ["angebot__abschnitt", "prioritaet", "angebot"]
    search_fields = ["schueler__person__nachname", "angebot__titel"]
    autocomplete_fields = ["schueler", "angebot"]


@admin.register(AGZuteilung)
class AGZuteilungAdmin(admin.ModelAdmin):
    list_display = ["schueler", "angebot", "erfuellter_wunsch"]
    list_filter = ["angebot__abschnitt", "angebot", "erfuellter_wunsch"]
    search_fields = ["schueler__person__nachname"]
    autocomplete_fields = ["schueler", "angebot"]
