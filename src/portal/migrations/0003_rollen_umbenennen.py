"""
Rollen umbenennen (Version 0.4.2.3): Lehrkraft → Lehrer:in, Verwaltung → Sekretariat,
Personalverwaltung → HR-Management. Mitglieder bleiben erhalten.

Das Sekretariat hat weniger Rechte als die frühere Rolle „Verwaltung“ (Einstellungen, Unterrichtsverteilung
und Personal nur noch lesend, dafür gibt es die Verwaltungsleitung). Seine Rechte werden deshalb einmalig
geleert; `grundeinrichtung` (läuft bei jedem Containerstart) setzt danach die neuen Standardrechte.
"""
from django.db import migrations

UMBENENNUNG = {"Lehrkraft": "Lehrer:in", "Verwaltung": "Sekretariat", "Personalverwaltung": "HR-Management"}


def umbenennen(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for alt, neu in UMBENENNUNG.items():
        alte = Group.objects.filter(name=alt).first()
        if alte is None:
            continue
        ziel = Group.objects.filter(name=neu).first()
        if ziel is None:
            alte.name = neu
            alte.save(update_fields=["name"])
            ziel = alte
        else:
            for user in alte.user_set.all():
                user.groups.add(ziel)
            ziel.permissions.add(*alte.permissions.all())
            alte.delete()
        if neu == "Sekretariat":
            ziel.permissions.clear()


def zurueck(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for alt, neu in UMBENENNUNG.items():
        Group.objects.filter(name=neu).exclude(name=alt).update(name=alt)


class Migration(migrations.Migration):
    dependencies = [
        ("portal", "0002_notizen"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]
    operations = [migrations.RunPython(umbenennen, zurueck)]
