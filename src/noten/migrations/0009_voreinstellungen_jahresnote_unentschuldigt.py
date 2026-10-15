from decimal import Decimal

from django.conf import settings
from django.db import migrations


def voreinstellungen(apps, schema_editor):
    """Bestehende Skalen: unentschuldigt ohne Note = schlechteste Stufe. Bestehender Unterricht im 2. Halbjahr (Jg. 5–10): 40 %."""
    Notenskala = apps.get_model("noten", "Notenskala")
    Unterricht = apps.get_model("noten", "Unterricht")
    for skala in Notenskala.objects.filter(unentschuldigt_stufe__isnull=True):
        stufen = skala.stufen.order_by("wert")
        schlechteste = stufen.first() if skala.hoeher_ist_besser else stufen.last()
        if schlechteste is not None:
            skala.unentschuldigt_stufe = schlechteste
            skala.save(update_fields=["unentschuldigt_stufe"])
    Unterricht.objects.filter(abschnitt__nummer=2, anteil_vorhalbjahr__isnull=True,
                              gruppe__jahrgang__in=list(settings.JAHRESNOTE_JAHRGAENGE)).update(
        anteil_vorhalbjahr=Decimal(settings.JAHRESNOTE_ANTEIL_HJ1))


class Migration(migrations.Migration):
    dependencies = [("noten", "0008_rundung_jahresnote_klausurregel_notensperre")]
    operations = [migrations.RunPython(voreinstellungen, migrations.RunPython.noop)]
