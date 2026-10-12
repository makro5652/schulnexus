# Schulverwaltung (Version 0.3, Entwicklungsstand)

Open-Source-Schulverwaltung für die DSN: Stammdaten, Klassen und Lerngruppen,
Noten mit Gewichtung, Fehlzeiten, Nachmittagsprogramm. Läuft im Browser,
betrieben mit Docker.

> Nur mit **erfundenen Testdaten** verwenden. Für echte Schülerdaten fehlen noch
> HTTPS, Backups, Zwei-Faktor-Anmeldung und die Freigabe durch den Datenschutz.

## Starten auf dem MacBook

1. **Docker Desktop** installieren und starten: https://www.docker.com/products/docker-desktop/
2. Den Ordner `schulverwaltung` entpacken, z. B. nach `~/Projekte/schulverwaltung`.
3. Terminal öffnen und eingeben:

   ```sh
   cd ~/Projekte/schulverwaltung
   ./start.sh
   ```

Falls „Permission denied“ erscheint: `sh start.sh` verwenden.

Beim ersten Start dauert es einige Minuten. Danach öffnet sich der Browser mit
http://localhost:8000. Die Zugangsdaten stehen in der Datei `.env`
(sie wird beim ersten Start mit zufälligen Passwörtern erzeugt).

| Konto | Rolle | Passwort |
| --- | --- | --- |
| `admin` | Vollzugriff | `ADMIN_PASSWORT` in `.env` |
| `lehrkraft` | Demo-Lehrkraft, Klassenleitung 9a, Chemie 9a/9b, Biologie 9a | `DEMO_PASSWORT` in `.env` |
| `verwaltung` | Demo-Sekretariat | `DEMO_PASSWORT` in `.env` |

## Noten mit Bewertungsordnern

Jeder Unterricht hat eine frei gestaltbare Ordnerstruktur, z. B.:

```
Schriftlich (Gewicht 50)
├─ 1. Klassenarbeit (Gewicht 1)
└─ Test Atombau (Gewicht 0,5)
Sonstige Mitarbeit (Gewicht 50)
├─ Quartal 1 (Gewicht 1)
│  ├─ Mitarbeit September (Gewicht 1)
│  └─ Protokoll Flammenfärbung (Gewicht 0,5)
├─ Quartal 2 (Gewicht 1)
└─ Referate (Gewicht 2)
```

- Ordner und Leistungsnachweise sind **frei benennbar**, Leistungsnachweise haben ein **Datum**.
- Jedes Gewicht gilt **relativ zu den anderen Einträgen derselben Ebene** (50/50 = 1/1).
- Ein Ordner kann Unterordner und Leistungsnachweise gleichzeitig enthalten (bis zu 5 Ebenen).
- **Leere Ordner** (z. B. ein noch nicht begonnenes Quartal) werden bei der Berechnung übersprungen.
- Die Notenübersicht zeigt für jeden Eintrag seinen planmäßigen Anteil an der Gesamtnote.
- Bedienung: Notenübersicht → „Bewertungsstruktur“ → „+ Unterordner“ bzw. „+ Leistungsnachweis“.
  Die Noten trägt man ein, indem man auf den Namen des Leistungsnachweises klickt.
- Die Gewichtungsvorlage legt beim Anlegen eines Unterrichts nur die **Start-Ordner** an.

**Gewichtung pro einzelner Note:** Zusätzlich zum Gewicht des Leistungsnachweises kann jede
einzelne Note ein individuelles Gewicht bekommen (z. B. verkürzte Nachschreibarbeit). Eine
Abweichung muss begründet werden und ist in der Notenübersicht mit „×Gewicht“ markiert.

## Personenakten

| Akte | Inhalt |
| --- | --- |
| Person (für alle) | Anrede, Titel, Namen, Geschlecht, Geburtsdatum/-ort/-land, Staatsangehörigkeiten, E-Mail, Telefon privat/mobil/dienstlich, Anschrift mit Postfach (P.O. Box), Sprache, Dokumente |
| Schüler:in | Schülernummer, Status, Ein-/Austritt, Erst-/Familiensprachen, DaZ/DaF, Nachteilsausgleich, Förderbedarf, Religion/Ethik, Lebt bei, Schulweg/Bus, Abholhinweise; dazu Schullaufbahn, Klassen/Gruppen, Eltern, Abschlüsse, Sprachenfolge, vorherige Schulen, Einwilligungen |
| Schullaufbahn | je Schuljahr: Jahrgang, **Bildungsgang** (Haupt-/Realschul-/gymnasialer Bildungsgang, Oberstufe …), Stammklasse, Ergebnis (versetzt, Wiederholung, Wechsel, Abschluss …), Bemerkung; Wechsel im Schuljahr über Von/Bis |
| Gesundheitsangaben | Allergien, Erkrankungen, Medikamente, Notfallhinweise, Arzt, Versicherung, Schwimmen – **eigene Tabelle mit eigenem Zugriffsrecht**, Lehrkräfte sehen sie standardmäßig nicht |
| Eltern | Beruf, Arbeitgeber, bevorzugter Kommunikationsweg, Schulverein (Mitgliedschaft, Nummer), Elternvertretung, Einverständnis zur Kontaktweitergabe; je Kind: Sorgerecht, Auskunftsrecht, Abholberechtigung, Notfallkontakt, Rechnungsempfang |
| Personal | Kürzel, Funktion, Personalnummer, Anstellungsart (ADLK, BPLK, LPLK, OLK, Ortskraft …), Dienstbeginn, Vertragsende, Deputat, Ermäßigung, Arbeitserlaubnis bis, Lehrbefähigungen, weitere Funktionen, Fortbildungen, Notfallkontakte |

Bildungsgänge und Abschlussarten sind unter „Stammdaten“ frei anpassbar. Die **Schülerakte**
(Link in der Klassenliste und in der Schülerliste) zeigt alles auf einer Seite; sie ist für
Verwaltung, Schulleitung und die Klassenleitung der aktuellen Stammklasse sichtbar.

Klassenleitungen sollen Gesundheitsangaben der eigenen Klasse sehen? Dann in der Verwaltung
unter „Gruppen“ der Rolle „Lehrkraft“ das Recht „Darf Gesundheitsangaben der eigenen Klasse sehen“ geben.

## Update von einer älteren Version

Neuen Ordnerinhalt über den alten kopieren (die `.env` behalten) und erneut `./start.sh`
ausführen. Die Datenbank wird automatisch umgestellt; vorhandene Kategorien werden zu Ordnern.

## Wichtige Befehle

| Zweck | Befehl |
| --- | --- |
| Starten | `./start.sh` |
| Stoppen (Daten bleiben) | `docker compose down` |
| Protokoll ansehen | `docker compose logs -f web` |
| Alles löschen und neu beginnen | `docker compose down -v` und danach `./start.sh` |
| Tests ausführen | `docker compose exec web python manage.py test` |

## Aufbau

| Ordner | Inhalt |
| --- | --- |
| `src/stammdaten` | Schuljahre, Halbjahre, Personen, Schüler:innen, Personal, Eltern-Beziehungen, Gruppen, Mitgliedschaften, Fächer, Einwilligungen, Dokumente |
| `src/noten` | Notenskalen, Notenschlüssel (BE → Note), Gewichtungsvorlagen, Unterricht, Leistungsnachweise, Noten, Zeugnisnoten; Berechnung in `berechnung.py` |
| `src/fehlzeiten` | Zeitraster, Fehlzeiten (ganztägig, stundenweise, Verspätung) |
| `src/nachmittag` | AG-Angebote, Wünsche, Losverfahren in `zuteilung.py` |
| `src/portal` | Startseite, Notenübersicht, Klassenliste, Rechteprüfung, Demo-Daten |

Alle Änderungen an Personen, Noten, Fehlzeiten und Mitgliedschaften werden
protokolliert (Schaltfläche „Geschichte“ in der Verwaltungsoberfläche).

Lizenz: vorgesehen AGPL-3.0 (noch zu bestätigen).
