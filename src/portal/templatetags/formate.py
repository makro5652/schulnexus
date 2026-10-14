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


LANGDATUM = {"de": "l, j. F Y", "en": "l j F Y"}
WOCHENTAG_DATUM = {"de": "l, j. F", "en": "l j F"}


def _sprache():
    return (translation.get_language() or "de")[:2]


@register.filter
def langdatum(wert):
    """Dienstag, 13. Oktober 2026 / Tuesday 13 October 2026"""
    return formats.date_format(wert, LANGDATUM.get(_sprache(), LANGDATUM["de"])) if wert else ""


@register.filter
def wochentag_datum(wert):
    """Donnerstag, 15. Oktober / Thursday 15 October"""
    return formats.date_format(wert, WOCHENTAG_DATUM.get(_sprache(), WOCHENTAG_DATUM["de"])) if wert else ""


@register.filter
def benutzername(benutzer, ersatz="–"):
    """Anzeigename eines Benutzerkontos (Name der Person, sonst Benutzername) – auch wenn das Konto fehlt (None)."""
    if not benutzer:
        return ersatz
    person = getattr(benutzer, "person", None) if hasattr(benutzer, "_meta") else None
    try:
        name = person.anzeigename if person else ""
    except Exception:
        name = ""
    return name or benutzer.get_full_name() or benutzer.get_username()
