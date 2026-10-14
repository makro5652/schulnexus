"""Systemprüfungen: Hinweise, wenn das Elternportal oder der Versand ohne nötige Absicherung eingeschaltet wird."""
from django.conf import settings
from django.core.checks import Warning, register


@register()
def elternkontakt_pruefen(app_configs, **kwargs):
    meldungen = []
    if settings.ELTERNPORTAL_AKTIV:
        meldungen.append(Warning(
            "ELTERNPORTAL_AKTIV=1: Eltern können sich anmelden. Mit echten Daten nur über HTTPS (HTTPS=1) betreiben; "
            "Eltern können unter „Sicherheit“ die Zwei-Faktor-Anmeldung einrichten.", id="elternkontakt.W001"))
    if settings.ELTERN_EMAIL_VERSAND and settings.ELTERN_LINK_BASIS.startswith("http://") and not settings.DEBUG:
        meldungen.append(Warning(
            "ELTERN_LINK_BASIS beginnt mit http:// – persönliche Elternlinks sollten nur über HTTPS erreichbar sein.",
            id="elternkontakt.W002"))
    return meldungen
