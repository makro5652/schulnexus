"""Sprachabhängige Datumsformate für Vorlagen: {% load formate %} … {{ datum|kurzdatum }} / {{ datum|tagmonat }}"""
from django import template
from django.utils import formats, translation

register = template.Library()

TAG_MONAT = {"de": "d.m.", "en": "d/m"}


@register.filter
def kurzdatum(wert):
    return formats.date_format(wert, "SHORT_DATE_FORMAT") if wert else ""


@register.filter
def tagmonat(wert):
    if not wert:
        return ""
    return formats.date_format(wert, TAG_MONAT.get((translation.get_language() or "de")[:2], "d.m."))
