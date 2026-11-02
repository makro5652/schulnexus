"""
Einstellungen von Schulnexus (Open-Source-Schulverwaltung).

Alle umgebungsabhängigen Werte kommen aus Umgebungsvariablen (siehe .env.example).
So läuft derselbe Code auf dem MacBook, dem Testserver und später in Produktion.
"""
import os
import sys
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "ja", "on"}


def env_int(name: str, default: int) -> int:
    """Ganzzahl aus der Umgebung; leere Angabe (z. B. „HSTS_SEKUNDEN=“ in der .env) zählt als nicht gesetzt (ab 0.4.9.6)."""
    wert = os.environ.get(name, "").strip()
    return int(wert) if wert else default


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


SECRET_KEY = os.environ.get("SECRET_KEY", "nur-fuer-lokale-entwicklung-unsicher")
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "simple_history",
    # Fachliche Module
    "stammdaten",
    "noten",
    "fehlzeiten",
    "nachmittag",
    "foerderung",
    "aufnahme",
    "zeugnisse",
    "elternkontakt",
    "sicherung",
    "laufbahn",
    "termine",
    "portal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "portal.middleware.BenutzerspracheMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "portal.middleware.NurPersonalMiddleware",
    "portal.sicherheit.ZweifaktorPflichtMiddleware",
    "portal.middleware.SicherheitsKoepfeMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "portal.context.schulinfo",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Datenbank: im Container PostgreSQL, Verbindung über DATABASE_URL.
DATABASES = {
    "default": dj_database_url.config(
        default="postgres://schule:schule@localhost:5432/schulnexus",
        conn_max_age=60,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Passwörter mit Argon2 hashen, falls installiert; sonst Djangos PBKDF2-Standard.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

# Sprachen: Standard Deutsch, umschaltbar auf Englisch (Menü oben rechts).
# Die Wahl wird je Benutzerkonto gespeichert (portal.Benutzereinstellung).
LANGUAGE_CODE = "de"
LANGUAGES = [("de", "Deutsch"), ("en", "English")]
LOCALE_PATHS = [BASE_DIR / "locale"]
FORMAT_MODULE_PATH = ["config.formate"]
LANGUAGE_COOKIE_NAME = "sprache"
LANGUAGE_COOKIE_AGE = 60 * 60 * 24 * 365
TIME_ZONE = os.environ.get("TIME_ZONE", "Africa/Nairobi")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
TESTLAUF = len(sys.argv) > 1 and sys.argv[1] == "test"
STORAGES = {
    "default": {"BACKEND": "portal.krypto.VerschluesselterSpeicher"},
    # Im Container: komprimierte Dateien mit Versions-Hash (nach collectstatic).
    # Bei Tests und lokaler Entwicklung: einfache Auslieferung ohne Manifest.
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        if (DEBUG or TESTLAUF)
        else "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

# Hochgeladene Dokumente (Atteste, Einverständnisse) liegen außerhalb des
# öffentlichen Webpfads und werden nur über eine rechtegeprüfte Ansicht ausgeliefert.
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))
MEDIA_URL = "/dokumente/"
if TESTLAUF:  # Tests schreiben Anhänge in ein Wegwerf-Verzeichnis
    import tempfile

    MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="sv-test-medien-"))
# Jahrgänge der Stufen (für Mittel- und Oberstufenkoordination), z. B. MITTELSTUFE=5-10, OBERSTUFE=11-12
def _jahrgaenge(name, standard):
    von, _, bis = os.environ.get(name, standard).partition("-")
    return tuple(range(int(von), int(bis or von) + 1))


STUFEN = {"mittelstufe": _jahrgaenge("MITTELSTUFE", "5-10"), "oberstufe": _jahrgaenge("OBERSTUFE", "11-12")}
# Jahresnote (ab 0.4.8.0): In diesen Jahrgängen fließt das 1. Halbjahr mit diesem Anteil (%) in den Vorschlag des
# 2. Halbjahres ein; die Lehrkraft kann den Anteil je Kurs ändern (0 = aus).
JAHRESNOTE_JAHRGAENGE = _jahrgaenge("JAHRESNOTE_JAHRGAENGE", "5-10")
JAHRESNOTE_ANTEIL_HJ1 = env_int("JAHRESNOTE_ANTEIL_HJ1", 40)

# Höchstgröße je Anhang in Megabyte (in .env änderbar).
DOKUMENT_MAX_MB = env_int("DOKUMENT_MAX_MB", 25)
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_PERMISSIONS = 0o640

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "start"
LOGOUT_REDIRECT_URL = "login"

# ---------------------------------------------------------------- HTTPS und Sitzungen (ab 0.4.6.0 erweitert)
# HTTPS=1, sobald die Seite über https erreichbar ist (z. B. „tailscale serve“ oder ein Reverse-Proxy):
# Cookies nur noch per HTTPS, HSTS (Browser merkt sich „nur HTTPS“), Weiterleitung http → https.
HTTPS = env_bool("HTTPS", False)
# Läuft ein Reverse-Proxy davor, der die Verbindung entschlüsselt (Tailscale Serve, Nginx Proxy Manager, Caddy …),
# erkennt Django HTTPS am Kopf X-Forwarded-Proto. Nur setzen, wenn der Proxy diesen Kopf zuverlässig setzt.
HINTER_PROXY = env_bool("HINTER_PROXY", False)
if HINTER_PROXY:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# Weiterleitung http → https durch Django (nur zusammen mit HINTER_PROXY=1, sonst Endlosschleife hinter einem Proxy)
SECURE_SSL_REDIRECT = env_bool("HTTPS_UMLEITUNG", False)
SECURE_REDIRECT_EXEMPT = [r"^gesundheit/$"]          # Docker-Healthcheck fragt intern per http
SECURE_HSTS_SECONDS = env_int("HSTS_SEKUNDEN", 31536000 if HTTPS else 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
# Sitzungen laufen nach 8 Stunden ab; Cookies nur per HTTPS, sobald HTTPS aktiv ist.
SESSION_COOKIE_AGE = 60 * 60 * 8
SECURE_COOKIES = HTTPS or env_bool("SECURE_COOKIES", False)
SESSION_COOKIE_SECURE = SECURE_COOKIES
CSRF_COOKIE_SECURE = SECURE_COOKIES
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# Schutz gegen Passwort- und Code-Raten (ab 0.4.9.2): nach zu vielen Fehlversuchen ist die Anmeldung für ein Konto
# bzw. von einer IP-Adresse vorübergehend gesperrt. Fehlversuche beim zweiten Faktor zählen mit.
ANMELDUNG_MAX_FEHLVERSUCHE = env_int("ANMELDUNG_MAX_FEHLVERSUCHE", 10)     # je Konto
ANMELDUNG_MAX_JE_IP = env_int("ANMELDUNG_MAX_JE_IP", 50)                  # je IP-Adresse
ANMELDUNG_SPERRE_MINUTEN = env_int("ANMELDUNG_SPERRE_MINUTEN", 15)

# ---------------------------------------------------------------- Verschlüsselung gespeicherter Daten (ab 0.4.6.0)
# 32 Byte (Base64), erzeugen mit:  python manage.py schluessel_erzeugen
# Leer = keine Verschlüsselung. Ein verlorener Schlüssel macht verschlüsselte Anhänge und Sicherungen unlesbar!
DATEN_SCHLUESSEL = os.environ.get("DATEN_SCHLUESSEL", "").strip()
if TESTLAUF and not DATEN_SCHLUESSEL:
    DATEN_SCHLUESSEL = "dGVzdHNjaGx1ZXNzZWwtbnVyLWZ1ZXItdGVzdHMtMzI"  # fester Testschlüssel (32 Byte)

# ---------------------------------------------------------------- Office-Seite (ab 0.4.6.0)
# Microsoft-365-Mandant (z. B. meineschule.onmicrosoft.com oder meineschule.example); ergänzt Anmeldelinks um den Mandanten.
OFFICE_MANDANT = os.environ.get("OFFICE_MANDANT", "").strip()

SCHULNAME = os.environ.get("SCHULNAME", "Meine Schule")
SCHULORT = os.environ.get("SCHULORT", "Nairobi")
# Fehltage auf dem Zeugnis ausweisen (im KMK-Muster nicht vorgesehen; 1 = ja)
ZEUGNIS_FEHLZEITEN = env_bool("ZEUGNIS_FEHLZEITEN", False)
# Höchstzahl Zeichen im Zeugniskommentar (ab 0.4.16.0; 0 = keine Grenze)
ZEUGNIS_KOMMENTAR_MAX = env_int("ZEUGNIS_KOMMENTAR_MAX", 0)

# ---------------------------------------------------------------- Sicherung, Wiederherstellung, PDF-Export (ab 0.4.3.0)
# Ablage der Modulsicherungen und PDF-Exporte – muss auf einem dauerhaften Datenträger liegen (Docker: eigenes Volume).
MODUL_SICHERUNGEN = Path(os.environ.get("MODUL_SICHERUNGEN", BASE_DIR / "modulsicherungen"))
if TESTLAUF:
    import tempfile

    MODUL_SICHERUNGEN = Path(tempfile.mkdtemp(prefix="sv-test-sicherungen-"))
SICHERUNG_UPLOAD_MAX_MB = env_int("SICHERUNG_UPLOAD_MAX_MB", 500)
SICHERUNG_BEHALTEN_AUTOMATISCH = env_int("SICHERUNG_BEHALTEN_AUTOMATISCH", 14)
# PDF-Export: höchstens so viele Einträge je PDF-Datei; mehr werden auf mehrere Dateien verteilt
PDF_EINTRAEGE_JE_DATEI = env_int("PDF_EINTRAEGE_JE_DATEI", 1500)
# PDF-Exporte im Hintergrund erstellen (in Tests sofort)
SICHERUNG_HINTERGRUND = not TESTLAUF

# Einzelnen Konten können Rechte ihrer Rollen entzogen werden (Benutzer und Rechte)
AUTHENTICATION_BACKENDS = ["portal.backends.RechteBackend"]

# ---------------------------------------------------------------- Elternkommunikation (ab 0.4.2.9)
# Eltern erhalten eine E-Mail mit einem persönlichen, befristeten Link (ohne Konto): lesen, bestätigen, antworten.
# Solange ELTERN_EMAIL_VERSAND=0 ist, wird nichts verschickt – Nachrichten bleiben im Postausgang
# (später: manage.py elternpost_senden). Der Erhalt kann von der Schule vermerkt werden (z. B. Rücklaufzettel).
ELTERN_EMAIL_VERSAND = env_bool("ELTERN_EMAIL_VERSAND", False)
# Öffentliche Adresse, unter der Eltern die Links öffnen. Eine reine Tailscale-Adresse ist für Eltern NICHT erreichbar.
ELTERN_LINK_BASIS = os.environ.get("ELTERN_LINK_BASIS", "http://localhost:8000").rstrip("/")
ELTERN_LINK_TAGE = env_int("ELTERN_LINK_TAGE", 60)
# Nachrichtentext zusätzlich in die E-Mail schreiben (Standard: nur Hinweis und Link – datensparsamer)
ELTERN_EMAIL_INHALT = env_bool("ELTERN_EMAIL_INHALT", False)
# Elternportal mit eigener Anmeldung (vorbereitet). Erst nach Zwei-Faktor-Anmeldung und Datenschutzfreigabe einschalten.
ELTERNPORTAL_AKTIV = env_bool("ELTERNPORTAL_AKTIV", False)

EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend" if ELTERN_EMAIL_VERSAND else "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)
EMAIL_TIMEOUT = 20
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", f"{SCHULNAME} <schulnexus@localhost>")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}
