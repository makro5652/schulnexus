#!/bin/sh
# Startablauf im Container:
# 1. auf die Datenbank warten  2. Migrationen  3. Grundeinrichtung
# 4. vorhandene Dateien verschlüsseln (falls DATEN_SCHLUESSEL gesetzt)
# 5. Admin-Konto anlegen (falls angegeben)  6. optional Demo-Daten  7. Server starten
set -e

echo "Warte auf die Datenbank ..."
python - <<'PY'
import os, sys, time
import psycopg
url = os.environ["DATABASE_URL"]
letzter = None
for versuch in range(60):
    try:
        psycopg.connect(url, connect_timeout=3).close()
        print("Datenbank erreichbar.")
        sys.exit(0)
    except Exception as fehler:
        letzter = fehler
        time.sleep(2)
print("Datenbank nicht erreichbar:", letzter)
sys.exit(1)
PY

python manage.py migrate --noinput
python manage.py grundeinrichtung

if [ -n "$DATEN_SCHLUESSEL" ]; then
    python manage.py dateien_verschluesseln
fi

if [ -n "$ADMIN_BENUTZER" ] && [ -n "$ADMIN_PASSWORT" ]; then
python - <<'PY'
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.contrib.auth import get_user_model
U = get_user_model()
name, pw = os.environ["ADMIN_BENUTZER"], os.environ["ADMIN_PASSWORT"]
if not U.objects.filter(username=name).exists():
    U.objects.create_superuser(name, os.environ.get("ADMIN_EMAIL", ""), pw)
    print(f"Admin-Konto '{name}' angelegt.")
else:
    print(f"Admin-Konto '{name}' existiert bereits.")
PY
fi

if [ "$DEMO_DATEN" = "1" ]; then
    python manage.py demodaten
fi

exec "$@"
