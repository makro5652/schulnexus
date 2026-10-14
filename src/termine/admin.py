from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import Raum, Raumbuchung, Termin


@admin.register(Raum)
class RaumAdmin(SimpleHistoryAdmin):
    list_display = ["name", "kuerzel", "art", "plaetze", "buchbar", "aktiv"]
    list_filter = ["art", "buchbar", "aktiv"]
    search_fields = ["name", "kuerzel", "ausstattung"]


@admin.register(Termin)
class TerminAdmin(SimpleHistoryAdmin):
    list_display = ["titel", "art", "beginn", "ende", "uhrzeit_von", "raum", "unterrichtsfrei", "fuer_eltern"]
    list_filter = ["art", "unterrichtsfrei", "fuer_eltern"]
    search_fields = ["titel", "titel_en", "ort", "zielgruppe"]
    date_hierarchy = "beginn"


@admin.register(Raumbuchung)
class RaumbuchungAdmin(SimpleHistoryAdmin):
    list_display = ["raum", "datum", "von", "bis", "zweck", "gebucht_von"]
    list_filter = ["raum"]
    search_fields = ["zweck"]
    date_hierarchy = "datum"
