#!/bin/sh
# Startablauf im Container:
# 1. auf die Datenbank warten  2. Migrationen  3. Grundeinrichtung
# 4. Admin-Konto anlegen (falls angegeben)  5. optional Demo-Daten  6. Server starten
set -e

echo "Warte auf die Datenbank ..."
python - <<'PY'
import os, sys, time
import psycopg
url = os.environ["DATABASE_URL"]
for versuch in range(60):
    try:
        psycopg.connect(url, connect_timeout=3).close()
        print("Datenbank erreichbar.")
        sys.exit(0)
    except Exception as fehler:
        time.sleep(2)
print("Datenbank nicht erreichbar:", fehler)
sys.exit(1)
PY

python manage.py migrate --noinput
python manage.py grundeinrichtung

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
