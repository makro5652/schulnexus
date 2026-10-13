"""
Einstellungen der Schulverwaltung.

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
        default="postgres://schule:schule@localhost:5432/schulverwaltung",
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
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
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

# Höchstgröße je Anhang in Megabyte (in .env änderbar).
DOKUMENT_MAX_MB = int(os.environ.get("DOKUMENT_MAX_MB", "25"))
DATA_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
FILE_UPLOAD_PERMISSIONS = 0o640

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "start"
LOGOUT_REDIRECT_URL = "login"

# Sitzungen laufen nach 8 Stunden ab; Cookies nur per HTTPS, sobald HTTPS aktiv ist.
SESSION_COOKIE_AGE = 60 * 60 * 8
SECURE_COOKIES = env_bool("SECURE_COOKIES", False)
SESSION_COOKIE_SECURE = SECURE_COOKIES
CSRF_COOKIE_SECURE = SECURE_COOKIES
SESSION_COOKIE_HTTPONLY = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

SCHULNAME = os.environ.get("SCHULNAME", "Deutsche Schule Nairobi")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}
