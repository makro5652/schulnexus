"""
Verschlüsselung gespeicherter Daten (ab 0.4.6.0).

- Schlüssel: DATEN_SCHLUESSEL in der .env (32 Byte, Base64). Ohne Schlüssel bleibt alles unverschlüsselt.
  Für jeden Zweck wird ein eigener Teilschlüssel abgeleitet (HKDF-SHA256): Dateien, Sicherungen, Geheimnisse.
- Format für Dateien und Sicherungen (AES-256-GCM, abschnittsweise, gegen Abschneiden geschützt):
      "SVENC1" | Modus (0 = Serverschlüssel, 1 = Passwort) | [16 Byte Salz bei Passwort]
      je Abschnitt: Länge (4 Byte) | Nonce (12 Byte) | Geheimtext mit Prüfwert
  Zusatzdaten je Abschnitt: laufende Nummer und Kennzeichen „letzter Abschnitt“.
- Passwortschlüssel: scrypt (n=2^15, r=8, p=1).
- Kurze Geheimnisse (z. B. Zwei-Faktor-Schlüssel): Fernet; ohne DATEN_SCHLUESSEL aus SECRET_KEY abgeleitet.

WICHTIG: Wer DATEN_SCHLUESSEL verliert, kann verschlüsselte Anhänge und Sicherungen nicht mehr lesen.
Den Schlüssel getrennt vom Server sicher aufbewahren (z. B. ausgedruckt im Tresor).
"""
import base64
import io
import os
import struct

from django.conf import settings
from django.core.files.base import ContentFile, File
from django.core.files.storage import FileSystemStorage

MAGIC = b"SVENC1"
SERVER, PASSWORT = 0, 1
ABSCHNITT = 1024 * 1024


class KryptoFehler(Exception):
    pass


def _roh_schluessel():
    wert = (getattr(settings, "DATEN_SCHLUESSEL", "") or "").strip()
    if not wert:
        return None
    try:
        roh = base64.urlsafe_b64decode(wert + "=" * (-len(wert) % 4))
    except (ValueError, TypeError):
        raise KryptoFehler("DATEN_SCHLUESSEL ist kein gültiger Base64-Wert.") from None
    if len(roh) != 32:
        raise KryptoFehler("DATEN_SCHLUESSEL muss 32 Byte lang sein (python manage.py schluessel_erzeugen).")
    return roh


def aktiv():
    return _roh_schluessel() is not None


def neuer_schluessel():
    return base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("=")


def _hkdf(material, zweck):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    # Fester Wert aus der Zeit vor der Umbenennung (0.4.9.0) – nie ändern, sonst sind Dateien unlesbar.
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"schulverwaltung", info=zweck.encode()).derive(material)


def teilschluessel(zweck):
    roh = _roh_schluessel()
    if roh is None:
        raise KryptoFehler("Keine Verschlüsselung eingerichtet (DATEN_SCHLUESSEL fehlt).")
    return _hkdf(roh, zweck)


def passwort_schluessel(passwort, salz):
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    return Scrypt(salt=salz, length=32, n=2 ** 15, r=8, p=1).derive(passwort.encode("utf-8"))


# ---------------------------------------------------------------- Ströme (Dateien, Sicherungen)

def _aad(nr, letzter):
    return struct.pack(">QB", nr, 1 if letzter else 0)


def verschluesseln(quelle, ziel, schluessel, modus=SERVER, salz=b""):
    """Liest aus `quelle` (Datei-Objekt) und schreibt verschlüsselt nach `ziel`."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    aes = AESGCM(schluessel)
    ziel.write(MAGIC + bytes([modus]) + (salz if modus == PASSWORT else b""))
    nr, stueck = 0, quelle.read(ABSCHNITT)
    while True:
        naechstes = quelle.read(ABSCHNITT)
        letzter = not naechstes
        nonce = os.urandom(12)
        geheim = aes.encrypt(nonce, stueck, _aad(nr, letzter))
        ziel.write(struct.pack(">I", len(geheim)) + nonce + geheim)
        if letzter:
            break
        nr, stueck = nr + 1, naechstes


def kopf(quelle):
    """Liest den Kopf: (Modus, Salz) – oder None bei unverschlüsselten Daten (Position bleibt dann am Anfang)."""
    anfang = quelle.read(len(MAGIC))
    if anfang != MAGIC:
        quelle.seek(0)
        return None
    modus = quelle.read(1)[0]
    salz = quelle.read(16) if modus == PASSWORT else b""
    return modus, salz


def entschluesseln(quelle, ziel, schluessel):
    """Erwartet `quelle` direkt hinter dem Kopf; prüft jeden Abschnitt und das Ende."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    aes = AESGCM(schluessel)
    nr = 0
    while True:
        laenge = quelle.read(4)
        if len(laenge) < 4:
            raise KryptoFehler("Die verschlüsselte Datei ist unvollständig.")
        (n,) = struct.unpack(">I", laenge)
        nonce = quelle.read(12)
        geheim = quelle.read(n)
        for letzter in (False, True):
            try:
                klar = aes.decrypt(nonce, geheim, _aad(nr, letzter))
                break
            except InvalidTag:
                klar = None
        if klar is None:
            raise KryptoFehler("Entschlüsselung fehlgeschlagen – falscher Schlüssel bzw. falsches Passwort oder beschädigte Datei.")
        ziel.write(klar)
        if letzter:
            if quelle.read(1):
                raise KryptoFehler("Die verschlüsselte Datei enthält unerwartete Daten.")
            return
        nr += 1


def ist_verschluesselt_datei(pfad):
    with open(pfad, "rb") as f:
        return f.read(len(MAGIC)) == MAGIC


def modus_datei(pfad):
    with open(pfad, "rb") as f:
        k = kopf(f)
    return None if k is None else k[0]


def datei_verschluesseln(quelle_pfad, ziel_pfad, *, passwort=None):
    with open(quelle_pfad, "rb") as q, open(ziel_pfad, "wb") as z:
        if passwort:
            salz = os.urandom(16)
            verschluesseln(q, z, passwort_schluessel(passwort, salz), PASSWORT, salz)
        else:
            verschluesseln(q, z, teilschluessel("sicherungen"), SERVER)


def datei_entschluesseln(quelle_pfad, ziel_pfad, *, passwort=None):
    """Entschlüsselt (Server- oder Passwortschlüssel je nach Kopf); unverschlüsselte Dateien werden kopiert."""
    with open(quelle_pfad, "rb") as q, open(ziel_pfad, "wb") as z:
        k = kopf(q)
        if k is None:
            while True:
                stueck = q.read(ABSCHNITT)
                if not stueck:
                    return
                z.write(stueck)
        modus, salz = k
        if modus == PASSWORT:
            if not passwort:
                raise KryptoFehler("Diese Datei ist mit einem Passwort verschlüsselt.")
            entschluesseln(q, z, passwort_schluessel(passwort, salz))
        else:
            entschluesseln(q, z, teilschluessel("sicherungen"))


# ---------------------------------------------------------------- Bytes (Anhänge)

def bytes_verschluesseln(daten, zweck="dateien"):
    aus = io.BytesIO()
    verschluesseln(io.BytesIO(daten), aus, teilschluessel(zweck))
    return aus.getvalue()


def bytes_entschluesseln(daten, zweck="dateien"):
    ein = io.BytesIO(daten)
    k = kopf(ein)
    if k is None:
        return daten
    aus = io.BytesIO()
    entschluesseln(ein, aus, teilschluessel(zweck))
    return aus.getvalue()


class VerschluesselterSpeicher(FileSystemStorage):
    """
    Dateisystem-Speicher, der neue Dateien verschlüsselt ablegt (sofern DATEN_SCHLUESSEL gesetzt ist) und beim Lesen
    transparent entschlüsselt. Ältere, unverschlüsselte Dateien bleiben lesbar (manage.py dateien_verschluesseln).
    """

    def _save(self, name, content):
        if aktiv():
            if hasattr(content, "seek"):
                content.seek(0)
            content = ContentFile(bytes_verschluesseln(content.read()), name=name)
        return super()._save(name, content)

    def _open(self, name, mode="rb"):
        roh = super()._open(name, "rb")
        try:
            daten = roh.read()
        finally:
            roh.close()
        if daten[:len(MAGIC)] == MAGIC:
            daten = bytes_entschluesseln(daten)
        return File(io.BytesIO(daten), name=name)


# ---------------------------------------------------------------- Kurze Geheimnisse

def _fernet():
    from cryptography.fernet import Fernet

    roh = _roh_schluessel()
    material = _hkdf(roh, "geheimnisse") if roh else _hkdf(settings.SECRET_KEY.encode(), "geheimnisse-ohne-datenschluessel")
    return Fernet(base64.urlsafe_b64encode(material))


def geheim_verschluesseln(text):
    return _fernet().encrypt(text.encode()).decode()


def geheim_entschluesseln(token):
    from cryptography.fernet import InvalidToken

    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        raise KryptoFehler("Geheimnis nicht lesbar (Schlüssel geändert?).") from None


# ---------------------------------------------------------------- Ablage mit Serverschlüssel (Sicherungen, PDF-Exporte)

def ablage_lesen(pfad):
    """Inhalt einer abgelegten Datei – entschlüsselt, falls verschlüsselt."""
    with open(pfad, "rb") as q:
        k = kopf(q)
        if k is None:
            return q.read()
        if k[0] != SERVER:
            raise KryptoFehler("Diese Datei ist mit einem Passwort verschlüsselt.")
        aus = io.BytesIO()
        entschluesseln(q, aus, teilschluessel("sicherungen"))
        return aus.getvalue()


def ablage_verschluesseln(pfad):
    """Verschlüsselt eine abgelegte Datei an Ort und Stelle (wenn DATEN_SCHLUESSEL gesetzt und noch nicht verschlüsselt)."""
    if not aktiv() or ist_verschluesselt_datei(pfad):
        return False
    tmp = f"{pfad}.verschluesseln"
    datei_verschluesseln(pfad, tmp)
    os.replace(tmp, pfad)
    return True


def ablage_temporaer(pfad):
    """Entschlüsselte Fassung als anonyme temporäre Datei (wird beim Schließen gelöscht)."""
    import tempfile

    tmp = tempfile.TemporaryFile()
    with open(pfad, "rb") as q:
        k = kopf(q)
        if k is None:
            while True:
                stueck = q.read(ABSCHNITT)
                if not stueck:
                    break
                tmp.write(stueck)
        else:
            if k[0] != SERVER:
                raise KryptoFehler("Diese Datei ist mit einem Passwort verschlüsselt.")
            entschluesseln(q, tmp, teilschluessel("sicherungen"))
    tmp.seek(0)
    return tmp
