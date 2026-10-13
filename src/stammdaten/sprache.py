"""Hilfen für zweisprachige Stammdaten (Deutsch/Englisch)."""
from django.utils import formats
from django.utils.translation import get_language


def englisch_aktiv():
    return (get_language() or "de").startswith("en")


def lokal(obj, feld="name"):
    """Gibt bei englischer Oberfläche `feld_en` zurück, sofern gepflegt – sonst das deutsche Feld."""
    if englisch_aktiv():
        wert = getattr(obj, f"{feld}_en", "")
        if wert:
            return wert
    return getattr(obj, feld)


def datum(wert):
    return formats.date_format(wert, "SHORT_DATE_FORMAT") if wert else ""


class LokalerNameMixin:
    @property
    def lokal_name(self):
        return lokal(self, "name")

    def __str__(self):
        return self.lokal_name
