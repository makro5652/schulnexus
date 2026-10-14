from django.db import migrations

# Adressen von Microsoft 365 (Stand 2026; Microsoft ändert sie gelegentlich – in der Verwaltung anpassbar).
STANDARD = [
    ("Outlook", "", "E-Mail", "Email", "https://outlook.office.com/mail/", "brief", "#0078d4"),
    ("Kalender", "Calendar", "Outlook-Kalender", "Outlook calendar", "https://outlook.office.com/calendar/", "kalender", "#0f6cbd"),
    ("Teams", "", "Chat und Besprechungen", "Chat and meetings", "https://teams.microsoft.com/", "personen", "#5b5fc7"),
    ("OneDrive", "", "Eigene Dateien", "My files", "https://www.microsoft365.com/launch/onedrive", "ordner", "#0364b8"),
    ("Word", "", "Texte", "Documents", "https://www.microsoft365.com/launch/word", "stift", "#185abd"),
    ("Excel", "", "Tabellen", "Spreadsheets", "https://www.microsoft365.com/launch/excel", "liste", "#107c41"),
    ("PowerPoint", "", "Präsentationen", "Presentations", "https://www.microsoft365.com/launch/powerpoint", "tafel", "#c43e1c"),
    ("OneNote", "", "Notizbücher", "Notebooks", "https://www.microsoft365.com/launch/onenote", "buch", "#7719aa"),
    ("SharePoint", "", "Teamseiten und Ablagen", "Team sites and libraries", "https://www.microsoft365.com/launch/sharepoint", "gebaeude", "#038387"),
    ("Forms", "", "Umfragen und Tests", "Surveys and quizzes", "https://forms.office.com/", "haken", "#008272"),
    ("Microsoft 365", "", "Alle Anwendungen", "All apps", "https://www.microsoft365.com/", "haus", "#d83b01"),
]


def anlegen(apps, schema_editor):
    Kachel = apps.get_model("portal", "OfficeKachel")
    if Kachel.objects.exists():
        return
    for nr, (titel, titel_en, besch, besch_en, url, symbol, farbe) in enumerate(STANDARD, start=1):
        Kachel.objects.create(titel=titel, titel_en=titel_en, beschreibung=besch, beschreibung_en=besch_en, url=url,
                              symbol=symbol, farbe=farbe, reihenfolge=nr * 10)


class Migration(migrations.Migration):
    dependencies = [("portal", "0007_officekachel")]
    operations = [migrations.RunPython(anlegen, migrations.RunPython.noop)]
