from django.db import migrations, models

QUELLEN = [("", "—"), ("excel", "aus der Excel-Notentabelle übernommen"), ("klasse", "in der Klassenübersicht festgesetzt")]
FELD = dict(blank=True, default="", max_length=10, choices=QUELLEN, verbose_name="Herkunft",
            help_text="Wie die Zeugnisnote zuletzt gesetzt wurde; leer = in der Zeugnisnoten-Eingabe.")


class Migration(migrations.Migration):

    dependencies = [
        ("noten", "0010_zeugnisnote_ohne_einzelnoten"),
    ]

    operations = [
        migrations.AddField(model_name="zeugnisnote", name="quelle", field=models.CharField(**FELD)),
        migrations.AddField(model_name="historicalzeugnisnote", name="quelle", field=models.CharField(**FELD)),
    ]
