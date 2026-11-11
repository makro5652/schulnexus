---
titel: Daten sichern, wiederherstellen und als PDF exportieren
art: anleitung
kurz: Modulsicherung anlegen und herunterladen, Wiederherstellung mit Vorschau, PDF-Export eines Zeitraums
stichworte: Sicherung, Backup, Wiederherstellung, Wiederherstellen, ZIP, Passwort, Verschlüsselung, PDF, Export, Archivierung
reihenfolge: 14
pfade: /system/sicherung/, /system/pdf/
---
**System › Sicherung** – nur Schulleitung und IT-Administration.

## Sicherung anlegen

1. **System › Sicherung › Sicherung.**
2. **Module** wählen: Stammdaten, Unterricht und Noten, Fehlzeiten, Nachmittag/AGs, Förderung, Neuanmeldungen, Zeugnisse und Konferenzen, Elternkommunikation, Schuljahreswechsel/Abgänge/Löschfristen, Startseite/Einstellungen, Benutzerkonten und Rollen – einzeln oder alle.
3. Optional **Hochgeladene Dateien einschließen** (Anhänge, Bewerbungsunterlagen).
4. Eine **Bemerkung** eintragen (zum Beispiel „vor dem Schuljahreswechsel“) und sichern.

Jede Sicherung ist eine ZIP-Datei mit den Daten, Prüfsummen und der Programmversion. Auf dem Server liegt sie verschlüsselt.

## Herunterladen

- **Mit Passwort** (mindestens 10 Zeichen) als verschlüsselte `.enc`-Datei – empfohlen.
- Oder bewusst unverschlüsselt als ZIP.

Bewahren Sie heruntergeladene Sicherungen geschützt auf; sie enthalten personenbezogene Daten.

## Wiederherstellen

1. Bei der Sicherung **Wiederherstellen** (oder eine Sicherung zuerst **hochladen**).
2. Module wählen. Die **Vorschau** zeigt je Modul, was neu angelegt, überschrieben und gelöscht wird – und welche Daten anderer Module mitbetroffen sind.
3. Fehlen Bezüge (zum Beispiel Noten zu einer inzwischen gelöschten Schülerin), wird die Wiederherstellung verweigert; dann beide Module gemeinsam wiederherstellen.
4. Bestätigen per Häkchen und Eingabe von `WIEDERHERSTELLEN`.

> Vor jeder Wiederherstellung entsteht automatisch eine Gesamtsicherung. Wiederherstellen geht nur mit derselben Programmversion, mit der gesichert wurde. Das eigene Konto bleibt beim Zurücksetzen der Benutzerkonten erhalten.

## PDF-Export

**System › Sicherung › PDF-Export** erstellt PDF-Dateien zur Archivierung oder für eine Auskunft:

1. Module wählen.
2. **Zeitraum:** aktuelles Halbjahr, Schuljahr, letzte 30 Tage, eigener Zeitraum oder ohne Begrenzung. Einträge mit Datum (Fehlzeiten, Noten, Nachrichten, Zeugnisse …) werden gefiltert; Einträge ohne Datum (Personen, Klassen) erscheinen als „Bestand“.
3. **Aufteilung:** automatisch, je Monat, je Halbjahr oder keine. Große Exporte werden in „Teil 1 von n“ geteilt.
4. Optional das Änderungsprotokoll.

Die PDFs entstehen im Hintergrund; die Seite aktualisiert sich selbst. Herunterladen einzeln oder als ZIP. Passwörter und Link-Schlüssel erscheinen nie im PDF.

## Protokoll

**System › Sicherung › Protokoll** zeigt Sicherungen, Downloads, Wiederherstellungen, PDF-Exporte, Rechte- und Kontoänderungen und Zwei-Faktor-Einstellungen mit Zeit und Person.

> Unabhängig davon sichert der Server die gesamte Datenbank regelmäßig. Diese Gesamtsicherung betreut die IT.
