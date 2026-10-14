from django.contrib import admin

from .models import OfficeKachel


@admin.register(OfficeKachel)
class OfficeKachelAdmin(admin.ModelAdmin):
    list_display = ("titel", "url", "symbol", "reihenfolge", "aktiv")
    list_editable = ("reihenfolge", "aktiv")
    search_fields = ("titel", "titel_en", "url")
