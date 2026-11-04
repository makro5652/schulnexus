"""Legt beim ersten Start das Verwaltungskonto an (idempotent). Läuft im Projektordner der App."""
import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402

U = get_user_model()
name = os.environ["ADMIN_BENUTZER"]
pw = os.environ["ADMIN_PASSWORT"]
if U.objects.filter(username=name).exists():
    print(f"Admin-Konto '{name}' existiert bereits.")
else:
    U.objects.create_superuser(name, "", pw)
    print(f"Admin-Konto '{name}' angelegt.")
