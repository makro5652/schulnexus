"""
Zwei-Faktor-Anmeldung (ab 0.4.6.0): Passwort + sechsstelliger Code aus einer Authenticator-App
(z. B. Microsoft Authenticator, Google Authenticator, Aegis). Verfahren: TOTP nach RFC 6238 (SHA-1, 30 s, 6 Ziffern),
Toleranz ±1 Zeitschritt, jeder Code nur einmal verwendbar. Zehn Ersatzcodes für den Fall eines verlorenen Telefons.
"""
import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from urllib.parse import quote

from django.conf import settings
from django.utils import timezone

from .krypto import geheim_entschluesseln, geheim_verschluesseln
from .models import Zweifaktor

SCHRITT, STELLEN, TOLERANZ = 30, 6, 1


def neues_geheimnis():
    return base64.b32encode(os.urandom(20)).decode().rstrip("=")


def _code(geheimnis, schritt):
    schluessel = base64.b32decode(geheimnis + "=" * (-len(geheimnis) % 8))
    digest = hmac.new(schluessel, struct.pack(">Q", schritt), hashlib.sha1).digest()
    versatz = digest[-1] & 0x0F
    zahl = struct.unpack(">I", digest[versatz:versatz + 4])[0] & 0x7FFFFFFF
    return str(zahl % 10 ** STELLEN).zfill(STELLEN)


def code_fuer(geheimnis, zeitpunkt=None):
    return _code(geheimnis, int((zeitpunkt or time.time()) // SCHRITT))


def pruefen_geheimnis(geheimnis, code, letzter_schritt=0, zeitpunkt=None):
    """Gibt den passenden Zeitschritt zurück (oder None). Bereits verwendete Schritte werden abgelehnt."""
    code = "".join(c for c in str(code) if c.isdigit())
    if len(code) != STELLEN:
        return None
    jetzt = int((zeitpunkt or time.time()) // SCHRITT)
    for schritt in range(jetzt - TOLERANZ, jetzt + TOLERANZ + 1):
        if schritt > letzter_schritt and hmac.compare_digest(_code(geheimnis, schritt), code):
            return schritt
    return None


def uri(geheimnis, user):
    aussteller = settings.SCHULNAME
    konto = user.get_username()
    return (f"otpauth://totp/{quote(aussteller)}:{quote(konto)}?secret={geheimnis}&issuer={quote(aussteller)}"
            f"&algorithm=SHA1&digits={STELLEN}&period={SCHRITT}")


def qr_svg(text):
    import segno

    return segno.make(text, error="m").svg_inline(scale=5, dark="#111", light="#fff", omitsize=False)


def eintrag(user):
    z, _neu = Zweifaktor.objects.get_or_create(benutzer=user)
    return z


def ist_aktiv(user):
    z = getattr(user, "zweifaktor", None) if user.is_authenticated else None
    return bool(z and z.aktiv)


def muss_einrichten(user):
    z = getattr(user, "zweifaktor", None) if user.is_authenticated else None
    return bool(z and z.pflicht and not z.aktiv)


def geheimnis_von(z):
    return geheim_entschluesseln(z.geheimnis) if z.geheimnis else ""


def _pruefwert(code):
    code = code.replace("-", "").replace(" ", "").lower()
    return hmac.new(settings.SECRET_KEY.encode(), code.encode(), hashlib.sha256).hexdigest()


def ersatzcodes_erzeugen(z):
    codes = []
    for _ in range(10):
        roh = secrets.token_hex(4)
        codes.append(f"{roh[:4]}-{roh[4:]}")
    z.ersatzcodes = [_pruefwert(c) for c in codes]
    z.save(update_fields=["ersatzcodes"])
    return codes


def einrichten_beginnen(z):
    """Neues Geheimnis vormerken (noch nicht aktiv)."""
    g = neues_geheimnis()
    z.geheimnis = geheim_verschluesseln(g)
    z.aktiv = False
    z.save(update_fields=["geheimnis", "aktiv"])
    return g


def einrichten_bestaetigen(z, code):
    schritt = pruefen_geheimnis(geheimnis_von(z), code)
    if schritt is None:
        return None
    z.aktiv, z.letzter_schritt, z.eingerichtet_am = True, schritt, timezone.now()
    z.save(update_fields=["aktiv", "letzter_schritt", "eingerichtet_am"])
    return ersatzcodes_erzeugen(z)


def code_pruefen(z, code):
    """Prüft einen Anmeldecode oder Ersatzcode; Ersatzcodes verfallen nach Gebrauch. Rückgabe: 'app', 'ersatz' oder None."""
    if not z.aktiv:
        return None
    schritt = pruefen_geheimnis(geheimnis_von(z), code, z.letzter_schritt)
    if schritt is not None:
        z.letzter_schritt, z.zuletzt_verwendet = schritt, timezone.now()
        z.save(update_fields=["letzter_schritt", "zuletzt_verwendet"])
        return "app"
    wert = _pruefwert(str(code))
    if wert in (z.ersatzcodes or []):
        z.ersatzcodes = [c for c in z.ersatzcodes if c != wert]
        z.zuletzt_verwendet = timezone.now()
        z.save(update_fields=["ersatzcodes", "zuletzt_verwendet"])
        return "ersatz"
    return None


def abschalten(z):
    z.geheimnis, z.aktiv, z.ersatzcodes, z.letzter_schritt, z.eingerichtet_am = "", False, [], 0, None
    z.save()
