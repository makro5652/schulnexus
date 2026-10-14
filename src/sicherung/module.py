"""Welche Daten gehören zu welchem Modul (für Sicherung, Wiederherstellung und PDF-Export)."""
from django.apps import apps
from django.utils.translation import gettext_lazy as _

# Schlüssel, Bezeichnung, Django-Apps
MODULE = [
    ("stammdaten", _("Stammdaten (Personen, Schüler:innen, Eltern, Personal, Klassen, Kataloge)"), ["stammdaten"]),
    ("noten", _("Unterricht und Noten"), ["noten"]),
    ("fehlzeiten", _("Fehlzeiten"), ["fehlzeiten"]),
    ("nachmittag", _("Nachmittag und AGs"), ["nachmittag"]),
    ("foerderung", _("Förderung"), ["foerderung"]),
    ("aufnahme", _("Neuanmeldungen"), ["aufnahme"]),
    ("zeugnisse", _("Zeugnisse und Konferenzen"), ["zeugnisse"]),
    ("elternkontakt", _("Elternkommunikation"), ["elternkontakt"]),
    ("laufbahn", _("Schuljahreswechsel, Abgänge und Löschfristen"), ["laufbahn"]),
    ("portal", _("Startseite und persönliche Einstellungen"), ["portal"]),
    ("konten", _("Benutzerkonten und Rollen"), ["auth"]),
]
SCHLUESSEL = [m[0] for m in MODULE]
NAMEN = {m[0]: m[1] for m in MODULE}

# Aus „auth“ werden nur Konten und Rollen gesichert; Rechte (Permission) erzeugt Django selbst.
NUR_MODELLE = {"auth": ("group", "user")}


def modelle(schluessel):
    """Modelle eines Moduls in der Reihenfolge der App (Bezugsmodelle zuerst)."""
    ergebnis = []
    for app in dict((m[0], m[2]) for m in MODULE)[schluessel]:
        for model in apps.get_app_config(app).get_models():
            if model._meta.proxy or not model._meta.managed:
                continue
            if app in NUR_MODELLE and model._meta.model_name not in NUR_MODELLE[app]:
                continue
            ergebnis.append(model)
    return ergebnis


def modul_von(model):
    for schluessel in SCHLUESSEL:
        if model in modelle(schluessel):
            return schluessel
    return None


def ist_protokollmodell(model):
    """Änderungsprotokolle von django-simple-history (HistoricalXyz, auch deren Zwischentabellen)."""
    return model.__name__.startswith("Historical") or any(f.name == "history_date" for f in model._meta.fields)


def modellname(model):
    """Lesbarer Name (Mehrzahl); Änderungsprotokolle als „Änderungsprotokoll: …“."""
    from django.utils.translation import gettext

    if ist_protokollmodell(model) and getattr(model, "instance_type", None) is not None:
        return gettext("Änderungsprotokoll: %(was)s") % {"was": model.instance_type._meta.verbose_name_plural}
    return str(model._meta.verbose_name_plural)
