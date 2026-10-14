"""Systemprüfungen zu HTTPS und Verschlüsselung (python manage.py check, auch beim Start des Containers)."""
from django.conf import settings
from django.core.checks import Error, Warning, register


@register()
def sicherheit_pruefen(app_configs, **kwargs):
    from .krypto import KryptoFehler, aktiv

    meldungen = []
    try:
        if not aktiv() and not settings.DEBUG:
            meldungen.append(Warning(
                "DATEN_SCHLUESSEL fehlt: Anhänge und Modulsicherungen werden unverschlüsselt gespeichert. "
                "Schlüssel erzeugen mit „python manage.py schluessel_erzeugen“ und in die .env eintragen.", id="portal.W001"))
    except KryptoFehler as f:
        meldungen.append(Error(str(f), id="portal.E001"))
    if settings.HTTPS and not any(o.startswith("https://") for o in settings.CSRF_TRUSTED_ORIGINS):
        meldungen.append(Warning(
            "HTTPS=1, aber CSRF_TRUSTED_ORIGINS enthält keine https-Adresse (z. B. https://tower.tailXXXX.ts.net). "
            "Ohne passenden Eintrag schlagen Formulare hinter einem Proxy fehl.", id="portal.W002"))
    if not settings.HTTPS and not settings.DEBUG:
        meldungen.append(Warning(
            "HTTPS=0: Die Seite läuft ohne HTTPS. Für echte Daten HTTPS einrichten (z. B. „tailscale serve“) und HTTPS=1 setzen.",
            id="portal.W003"))
    return meldungen
