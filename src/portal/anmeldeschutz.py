"""
Schutz gegen das Durchprobieren von Passwörtern und Codes (ab 0.4.9.2).

Gezählt werden fehlgeschlagene Anmeldungen im Zeitfenster ANMELDUNG_SPERRE_MINUTEN – je Konto (Benutzername) und je
IP-Adresse. Ist eine Grenze erreicht, lehnt die Anmeldung jeden weiteren Versuch ab, ohne das Passwort zu prüfen; die
Sperre endet von selbst, sobald die ältesten Fehlversuche aus dem Zeitfenster fallen. Fehlversuche beim zweiten Faktor
zählen für das Konto mit, damit sich Codes nicht durch wiederholtes Neuanmelden durchprobieren lassen. Nach einer
vollständigen Anmeldung werden die Fehlversuche des Kontos gelöscht.

Hinter einem Reverse-Proxy (HINTER_PROXY=1) gilt die letzte Adresse im Kopf X-Forwarded-For – die trägt der eigene Proxy
ein; weiter links stehende Einträge kann der Browser frei setzen.
"""
import ipaddress
import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone

log = logging.getLogger("schulnexus.anmeldung")


def client_ip(request):
    adresse = request.META.get("REMOTE_ADDR", "")
    if getattr(settings, "HINTER_PROXY", False):
        weitergeleitet = [a.strip() for a in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if a.strip()]
        if weitergeleitet:
            adresse = weitergeleitet[-1]
    try:
        return str(ipaddress.ip_address(adresse))
    except ValueError:
        return None


def _fenster():
    return timezone.now() - timedelta(minutes=settings.ANMELDUNG_SPERRE_MINUTEN)


def _name(benutzername):
    return (benutzername or "").strip().lower()[:150]


def gesperrt(benutzername, ip) -> bool:
    from .models import Anmeldeversuch

    seit = _fenster()
    name = _name(benutzername)
    if name and Anmeldeversuch.objects.filter(benutzername=name, zeit__gte=seit).count() >= settings.ANMELDUNG_MAX_FEHLVERSUCHE:
        return True
    return bool(ip) and Anmeldeversuch.objects.filter(ip=ip, zeit__gte=seit).count() >= settings.ANMELDUNG_MAX_JE_IP


def fehlversuch(benutzername, ip):
    from .models import Anmeldeversuch

    name = _name(benutzername)
    Anmeldeversuch.objects.create(benutzername=name, ip=ip)
    Anmeldeversuch.objects.filter(zeit__lt=timezone.now() - timedelta(days=1)).delete()
    if gesperrt(name, ip):
        log.warning("Anmeldung vorübergehend gesperrt: Konto %s, IP %s", name or "–", ip or "–")


def zuruecksetzen(benutzername):
    from .models import Anmeldeversuch

    Anmeldeversuch.objects.filter(benutzername=_name(benutzername)).delete()


@receiver(user_logged_in)
def _nach_anmeldung(sender, request, user, **kwargs):
    zuruecksetzen(user.get_username())
