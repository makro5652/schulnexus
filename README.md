# Schulverwaltung (Version 0.4, Entwicklungsstand)

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
| `personal` | Demo-Personalverwaltung (HR) | `DEMO_PASSWORT` in `.env` |

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
| Personal | Bereich, Stellenbezeichnung, Kürzel (nur für Unterrichtende Pflicht), Vorgesetzte:r, Personalnummer, Anstellungsart (ADLK, BPLK, LPLK, OLK, Ortskraft, Honorar/Coach, externer Dienstleister …), Firma, Dienstbeginn, Vertragsende, Deputat/Wochenstunden, Arbeitszeit/Schicht, Arbeitserlaubnis, Lehrbefähigungen, Dienstausweis, Nachweise, Abwesenheiten, Fortbildungen, Notfallkontakte |

Bildungsgänge und Abschlussarten sind unter „Stammdaten“ frei anpassbar. Die **Schülerakte**
(Link in der Klassenliste und in der Schülerliste) zeigt alles auf einer Seite; sie ist für
Verwaltung, Schulleitung und die Klassenleitung der aktuellen Stammklasse sichtbar.

Klassenleitungen sollen Gesundheitsangaben der eigenen Klasse sehen? Dann in der Verwaltung
unter „Gruppen“ der Rolle „Lehrkraft“ das Recht „Darf Gesundheitsangaben der eigenen Klasse sehen“ geben.

## Personal aller Bereiche und HR

**Personalbereiche** sind frei pflegbar (Stammdaten › Personalbereiche). Voreingestellt:
Schulleitung, Lehrkräfte, Kindergarten/Vorschule, Nachmittagsbereich/Coaches, Verwaltung,
Personalverwaltung (HR), Finanzen, IT, Facility/Haustechnik, Reinigung, Sicherheit,
Küche/Cafeteria, Transport/Fahrdienst, Schulgesundheit, Bibliothek.

- **Externe Dienstleister** (z. B. Sicherheits- oder Reinigungsfirma) werden als Firma erfasst;
  die eingesetzten Personen sind trotzdem einzeln geführt (wichtig für Zutritt und Kinderschutz).
- **Coaches** im Nachmittagsbereich sind normales Personal (z. B. Honorarbasis) und können als
  AG-Leitung eingetragen werden.
- **Nachweise mit Ablaufdatum**: Führungszeugnis / Certificate of Good Conduct, Kinderschutz-Schulung,
  Erste Hilfe, Gesundheitszeugnis Küche, Fahrerlaubnis, Rettungsschwimmer, Trainerlizenz …
  Je Nachweisart: Gültigkeitsdauer und für welche Bereiche sie Pflicht ist. „Gültig bis“ wird
  automatisch berechnet. Fehlende, abgelaufene und bald (60 Tage) ablaufende Nachweise erscheinen
  auf der Startseite der Personalverwaltung und als Filter in der Personalliste.
- **Personalabwesenheiten**: Urlaub, Krankmeldung (ohne Diagnosen), Fortbildung, Dienstreise
  mit Status beantragt/genehmigt/abgelehnt und Arbeitstage-Berechnung.

**Rollen:** Die neue Rolle *Personalverwaltung* sieht Dienstverhältnis, Nachweise, Abwesenheiten
und vertrauliche Personal-Zusatzfelder, aber keine Noten und keine Gesundheitsangaben von
Schüler:innen. Das *Sekretariat* sieht Personal (Kontakt, Einsatz), aber keine HR-Daten.
Rechte lassen sich unter „Gruppen“ anpassen; beim Neustart werden Anpassungen nicht mehr
überschrieben (es werden nur fehlende Standardrechte ergänzt).

## Eigene Datenfelder (Zusatzfelder)

Unter **Stammdaten › Zusatzfelder** lassen sich beliebig viele eigene Felder für Schüler:innen,
Personal und Eltern anlegen – ohne Programmierung:

| Einstellung | Möglichkeiten |
| --- | --- |
| Feldtyp | Text, mehrzeiliger Text, Zahl, Datum, Ja/Nein, Auswahl, Mehrfachauswahl |
| Pflichtfeld | ja/nein |
| Abschnitt | Überschrift zur Gruppierung im Formular, z. B. „Schulleben“, „Ausstattung“ |
| Sichtbar für | alle mit Aktenzugriff (inkl. Klassenleitung) · Verwaltung, Leitung, HR · nur HR und Leitung |
| In Liste | Feld erscheint als Spalte in der Übersichtsliste |
| Aktiv | Deaktivieren blendet das Feld aus; gespeicherte Werte bleiben erhalten |

Die Felder erscheinen automatisch in den Formularen und (bei Schüler:innen) in der Schülerakte.
Werte unsichtbarer Felder bleiben beim Speichern durch andere Rollen unverändert. Alle Änderungen
stehen im Änderungsprotokoll.

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
