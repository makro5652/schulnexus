# Schulverwaltung (Version 0.4.2.8, Entwicklungsstand)

Open-Source-Schulverwaltung für die DSN: Stammdaten, Klassen und Lerngruppen,
Noten mit Gewichtung, Fehlzeiten, Nachmittagsprogramm, Anhänge zur Schülerakte,
Förderpläne und Nachteilsausgleiche, Neuanmeldungen, Zeugnisse und Konferenzen. Läuft im Browser,
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
| `lehrkraft` | Lehrer:in, Klassenleitung 9a, Chemie 9a/9b, Biologie 9a | `DEMO_PASSWORT` in `.env` |
| `mittelstufe` | Lehrer:in und Mittelstufenkoordination (Klassenleitung 8a) | `DEMO_PASSWORT` in `.env` |
| `oberstufe` | Lehrer:in und Oberstufenkoordination | `DEMO_PASSWORT` in `.env` |
| `schulleitung` | Schulleitung | `DEMO_PASSWORT` in `.env` |
| `verwaltung` | Sekretariat | `DEMO_PASSWORT` in `.env` |
| `verwaltungsleitung` | Verwaltungsleitung | `DEMO_PASSWORT` in `.env` |
| `personal` | HR-Management | `DEMO_PASSWORT` in `.env` |
| `finanzen` | Finanzen | `DEMO_PASSWORT` in `.env` |
| `foerderung` | Förderkoordination (zugleich Klassenleitung 9b) | `DEMO_PASSWORT` in `.env` |
| `schueler`, `eltern` | vorbereitet, derzeit **kein** Portalzugang | `DEMO_PASSWORT` in `.env` |

## Klassen und Gruppen zuordnen

**Menüband › Schüler:innen › Zuordnen** (oder in der Klassenliste „Mitglieder zuordnen“) öffnet eine
Arbeitsseite mit drei Spalten:

1. **Gruppen** des gewählten Schuljahres (Stammklassen, Lerngruppen, AGs) mit Suchfeld und
   Mitgliederzahl; darunter „Neue Gruppe“ (Name, Typ, Jahrgang, Leitung, Vorjahresgruppe).
2. **Mitglieder** der gewählten Gruppe: mehrere auf einmal zum Stichtag entfernen; Rolle
   (z. B. Klassensprecher:in) direkt in der Zeile eintragen und mit ✓ speichern.
3. **Schüler:innen hinzufügen:** Sofortfilter nach Name (Taste `/`), Klasse(n), Jahrgang,
   Religion/Ethik, „ohne Klasse“; Häkchen, Umschalt-Klick für Bereiche, „alle sichtbaren“;
   dann „Hinzufügen“ – oder die Auswahl in die Mitgliederliste ziehen.

- **Stichtag:** gilt für Ein- und Austritte (Standard: heute, innerhalb des Schuljahres).
  Mitgliedschaften werden nicht gelöscht, sondern zum Vortag beendet – die Historie bleibt.
  Nur wer am selben Tag wieder entfernt wird (Versehen), wird gelöscht.
- **Klassenwechsel:** Wer einer Stammklasse zugeordnet wird und schon in einer anderen ist,
  wechselt automatisch.
- **Neues Schuljahr:** Ist bei einer Klasse die Vorjahresklasse eingetragen, übernimmt
  „Alle übernehmen“ deren Schüler:innen mit einem Klick.
- **Lerngruppen** (z. B. Ethik 9): Der Filter ist auf die Ursprungs-Stammklassen und – wenn der
  Name es nahelegt – auf Ethik bzw. Religion voreingestellt.
- **Rechte:** Sekretariat, Verwaltungsleitung, Schulleitung alle Gruppen; Stufenkoordination die
  Gruppen ihrer Stufe (AGs ohne Jahrgang bleiben bei der Verwaltung).

## Betrieb auf Unraid (Zugriff über Tailscale)

Für den Dauerbetrieb auf einem Unraid-Server gibt es eine eigene Variante im Ordner `unraid/`:
ein veröffentlichter Port (voreingestellt 8010), erreichbar über das Tailscale des Servers,
Daten unter `/mnt/user/appdata/schulverwaltung-daten`, tägliche Datenbanksicherung.
Einrichtung im Unraid-Terminal mit `sh unraid/einrichten.sh` – Schritt für Schritt in
[ANLEITUNG-UNRAID.md](ANLEITUNG-UNRAID.md).

## Zeugnisse, Zeugniskommentare und Konferenzen

Grundlage: Ordnung für den Abschluss der Sekundarstufe I an Deutschen Schulen im Ausland (Sek I-PO, KMK 16.03.2017;
Zeugnismuster Anlage 11) und Richtlinie zur Gestaltung von Bildungsgängen und Abschlüssen in der Sekundarstufe I an
Deutschen Schulen im Ausland (Beschluss vom 18.03.2026). **Menüband › Unterricht › Zeugnisse.**

1. **Zeugnisnoten** (je Kurs, auch über „Zeugnisnoten und Kommentare“ in der Notenübersicht): ganze Noten,
   vorausgewählt ist der gerundete Vorschlag; Abweichung nur mit pädagogischer Begründung; Vermerke „n.b.“ und „befreit“.
2. **Zeugniskommentar:** schreibt die Klassenleitung. Alle Lehrkräfte, die die Schülerin oder den Schüler unterrichten,
   sehen ihn bei ihren Noten, **zeichnen digital ab** und können **Anmerkungen** hinterlassen. Ändert sich der Text,
   werden Abzeichnungen als veraltet markiert. Der Kommentar wird als Beiblatt gedruckt.
3. **Zeugnis je Schüler:in:** Fachnoten (Kernfächer markiert), Bemerkungen, GeR-Niveaustufen, Datum und Ort,
   Versetzungs- bzw. Berechtigungsvermerk; **Freigabe** schreibt die Noten fest. Druckansicht nach Anlage 11
   (Halbjahreszeugnis / Zeugnis, Noten in Worten, epochale Fächer mit Halbjahresangabe, Bildungsgang, Unterschriftsfelder),
   einzeln oder für die ganze Klasse, Entwürfe mit Aufdruck; nicht amtliche englische Übersetzung.
   Drucken über den Browser (A4, Kopf- und Fußzeilen ausschalten) – auch als PDF.
4. **Konferenz** je Klasse und Halbjahr: Notenliste mit Kernfächern, automatischer Vorschlag nach Ziffer 5.3
   (Ausgleichsregeln, Nachprüfung ab Jahrgang 7, „ungenügend“ im Kernfach schließt aus), im Halbjahr die
   Gefährdungen mit Mitteilungsschreiben an die Eltern; Beschluss je Schüler:in mit Abstimmung, Notenausgleich und
   Begründung (Pflicht bei Nichtversetzung); druckbare Niederschrift. Beim Abschluss der Versetzungskonferenz werden
   die Entscheidungen in die Jahreszeugnisse übernommen.

Je Fach legt die Verwaltung unter **Fächer** fest, welche Rolle es für Versetzung und Zeugnis hat (Deutsch, Mathematik,
Fremdsprache, Kunst/Musik/Sport, Religion/Ethik, weiteres Fach) und in welcher Zeugnisspalte es steht; bekannte
Fachnamen werden automatisch eingeordnet. Welche Fremdsprache die erste bzw. zweite ist, steht in der Sprachenfolge.
Fehltage erscheinen auf dem Zeugnis nur mit `ZEUGNIS_FEHLZEITEN=1` (im KMK-Muster nicht vorgesehen); der Ort kommt aus `SCHULORT`.

| Rolle | Zeugnisse |
| --- | --- |
| Lehrer:in | Zeugnisnoten der eigenen Kurse; Kommentare der eigenen Schüler:innen lesen, abzeichnen, anmerken; als Klassenleitung Kommentare schreiben und Zeugnisse der Klasse bearbeiten |
| Stufenkoordination | Zeugnisse der Stufe bearbeiten und freigeben, Konferenzen leiten |
| Schulleitung | alles |
| Sekretariat, Verwaltungsleitung | Zeugnisse vorbereiten (Bemerkungen, Datum, GeR) und drucken, Konferenzen lesen |

## Neuanmeldungen

**Menüband › Schüler:innen › Neuanmeldungen** verwaltet Bewerbungen bis zur Aufnahme – getrennt von
den regulären Stammdaten.

1. **Neue Anmeldung:** Kind, gewünschter Jahrgang und Eintritt, Bildungsgang, bisherige Schule,
   Erziehungsberechtigte (Adresse wie Kind oder abweichend), Checklisten-Vorlagen und gleich
   mehrere Zeugnisse auf einmal (auch per Ziehen und Ablegen).
2. **Bewerbungsakte:** Status (Eingegangen › In Prüfung › Warteliste › Zugesagt, außerdem Abgelehnt
   und Zurückgezogen) mit einem Klick; **vorläufige Klasse** mit aktueller Klassengröße und weiteren
   vorläufigen Zuordnungen; **Unterlagen** sortiert nach Upload-Datum, je Datei einstellbar, ob und für
   wen sie später in der Schülerakte sichtbar ist; **Verlauf** der Änderungen.
3. **Checkliste:** Punkte abhaken (mit Datum und Person), Bemerkung ergänzen, als Pflicht oder optional
   markieren, einzelne Punkte ergänzen oder entfernen, weitere Vorlagen hinzufügen. Jeder Punkt hat
   eine Zuständigkeit (Sekretariat, Finanzen, Stufenkoordination, Schulleitung); „für mich“ zeigt die
   eigenen offenen Punkte – auch auf der Startseite.
   Vorlagen pflegen: **Menüband › Schüler:innen › Checklisten-Vorlagen** (zweisprachig, mit
   Jahrgangsbereich; „Immer vorschlagen“ für die Grundausstattung).
4. **Übernahme** (Status „Zugesagt“, alle Pflichtpunkte erledigt): legt Schüler:in mit neuer
   Schülernummer, Erziehungsberechtigte mit Elternprofil und Beziehung, bisherige Schule, Schullaufbahn
   und die Mitgliedschaft in der vorläufigen Klasse ab dem Eintrittsdatum an und kopiert die
   ausgewählten Unterlagen samt ursprünglichem Upload-Datum in die Schülerakte; das Checklisten-
   Protokoll wird als Anhang (nur Verwaltung) gespeichert. Vorher werden **Dubletten** gesucht (gleicher
   Name bzw. Geburtsdatum); bei Eltern von Geschwisterkindern kann die vorhandene Person verknüpft
   werden. Die Bewerbungsakte ist danach abgeschlossen und mit der Schülerakte verlinkt.

| Rolle | Neuanmeldungen |
| --- | --- |
| Sekretariat, Verwaltungsleitung, Schulleitung | alles, einschließlich Übernahme und Löschen |
| Mittel-/Oberstufenkoordination | Anmeldungen der eigenen Jahrgänge (und ohne Jahrgang): anlegen, bearbeiten, Status, Klasse, Checkliste, Unterlagen; keine Übernahme |
| Finanzen | alle Anmeldungen lesen, Checkliste abhaken, Kontakte (z. B. Rechnungsempfänger:in) ändern, Unterlagen hochladen |

Abgelehnte und zurückgezogene Anmeldungen bleiben bis zur Löschung erhalten; „Anmeldung löschen“
entfernt auch alle Dateien.

## Rollen und Rechte

Rollen sind Benutzergruppen; eine Person kann mehrere haben (z. B. Lehrer:in + Mittelstufenkoordination).
Zugewiesen werden sie unter **Verwaltung › Benutzerkonten**; die vollständige Rechtetabelle steht im Portal
unter **Verwaltung › Rollen und Rechte** (für Verwaltungsleitung und Schulleitung).

| Rolle | Rechte |
| --- | --- |
| Lehrer:in | eigener Unterricht (Leistungsnachweise, Noten, Zeugnisnoten); als Klassenleitung Akte, Fehlzeiten, Anhänge, Förderung der eigenen Klasse |
| Mittelstufenkoordination | wie Lehrer:in, zusätzlich alle Klassen der Mittelstufe: Akten, Notenübersichten, Fehlzeiten, Gesundheitshinweise, Förderpläne/Nachteilsausgleiche bearbeiten, Schullaufbahn, Neuanmeldungen der Stufe; Stufenübersicht |
| Oberstufenkoordination | dasselbe für die Oberstufe |
| Schulleitung | alles |
| Sekretariat | Schüler- und Elternstammdaten, Klassen, Fehlzeiten, AGs, Anhänge, Gesundheitsangaben, Neuanmeldungen mit Übernahme; Noten und Einstellungen lesend; keine Förderpläne, keine HR-Daten |
| Verwaltungsleitung | wie Sekretariat, dazu Schuljahre, Fächer, Notenskalen, Unterrichtsverteilung, eigene Felder, Benutzerkonten und Rollen, Personal inkl. HR, Finanzen |
| HR-Management | Personal aller Bereiche inkl. Dienstverhältnis, Nachweise, Abwesenheiten |
| Finanzen | Rechnungsempfänger, Eltern- und Schülerstammdaten (lesend), Dienstleister, Vertragsunterlagen; Neuanmeldungen lesen und Checkliste abhaken |
| Förderkoordination | alle Förderpläne und Nachteilsausgleiche, Genehmigung, Kataloge |
| Schüler:in, Eltern | vorbereitet für Stundenplan bzw. Elternkommunikation; derzeit kein Zugang |

Die Jahrgänge der Stufen stehen in der `.env` (`MITTELSTUFE=5-10`, `OBERSTUFE=11-12`).
Rechte werden beim Start nur ergänzt, nie entfernt – eigene Anpassungen bleiben erhalten.
Auf die Standardrechte zurücksetzen:
`docker compose exec web python manage.py grundeinrichtung --rechte-zuruecksetzen`.

Beim Update von älteren Versionen werden die Gruppen umbenannt (Lehrkraft → Lehrer:in,
Verwaltung → Sekretariat, Personalverwaltung → HR-Management); die Mitglieder bleiben erhalten.
Das Sekretariat erhält dabei die neuen, engeren Standardrechte.

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

## Navigation: Menüband

Portal und Verwaltungsoberfläche haben oben dasselbe **Menüband** (wie in Word):

- **Titelleiste:** Schulname und Schuljahr, Personensuche, Sprache, Benutzermenü
  (Passwort ändern, Abmelden).
- **Registerkarten:** Start · Schüler:innen · Unterricht · Förderung · Personal · Verwaltung,
  jeweils mit beschrifteten Befehlsgruppen (z. B. Unterricht: Mein Unterricht, Bewertung,
  Zeugnis, Nachmittag, Einstellungen).
- Jede Rolle sieht nur die Karten und Befehle, für die sie Rechte hat. Beim Öffnen einer Seite
  ist die passende Karte aktiv und der aktuelle Befehl hervorgehoben.
- Mit dem Pfeil rechts neben den Registerkarten lässt sich das Band einklappen; der Browser
  merkt sich die Einstellung. Tastatur: Pfeiltasten wechseln die Karte, Esc schließt Menüs.

Das Portal ist **nur für Beschäftigte** (Verwaltung und Lehrkräfte). Konten ohne Personalakte
und ohne Verwaltungszugang können sich nicht anmelden.

## Startseite

- **Kopf:** Begrüßung, Kalenderblatt mit Datum und Kalenderwoche. Die Suche (Schüler:innen,
  Kolleg:innen, für die Verwaltung auch Eltern) steht in der Titelleiste; gefunden wird nur, wen man sehen darf.
- **Schnellzugriff:** eigene Klassen und Gruppen sowie eigener Unterricht (direkt zur Notenübersicht).
- **Notizen:** nur für die eigene Person sichtbar; Farbe, optionales Fälligkeitsdatum
  (ab diesem Tag hervorgehoben), anheften, abhaken, bearbeiten, löschen.
  Verwaltung und Schulleitung können eine Notiz als **Mitteilung an alle** veröffentlichen;
  mit Datum verschwindet sie nach diesem Tag automatisch.
- **Geburtstage:** heute und die nächsten 7 Tage. Lehrkräfte sehen die Schüler:innen ihrer
  Klassen, Gruppen und Kurse, Verwaltung, Leitung und Förderkoordination alle aktiven
  Schüler:innen; dazu alle aktiven Kolleg:innen (ohne Alter). Wer nicht erscheinen soll:
  in der Personenakte „Geburtstag auf der Startseite anzeigen“ abwählen.
  Am 29. Februar Geborene erscheinen in Nicht-Schaltjahren am 28. Februar.

## Anhänge zur Schülerakte

In der Schülerakte (Abschnitt **Anhänge**) lassen sich beliebige Dateien hochladen – PDF, Fotos,
Word, Excel, Scans usw. – oder reine Notizen ohne Datei. Die Liste ist nach Upload-Datum sortiert
(neueste zuerst, umschaltbar) und nach Kategorie filterbar.

| Sichtbar für | Wer sieht den Anhang |
| --- | --- |
| Alle mit Aktenzugriff | Verwaltung, Schulleitung, Förderkoordination, Klassenleitung |
| Verwaltung und Schulleitung | z. B. Anmeldung, Verträge |
| Förderteam | Förderkoordination, Klassenleitung, Schulleitung – z. B. Gutachten |
| Nur Schulleitung | besonders vertrauliche Unterlagen |

Dateien werden nie über einen öffentlichen Link ausgeliefert, sondern nur nach Rechteprüfung;
auf dem Datenträger tragen sie einen Zufallsnamen. Gelöschte Anhänge werden auch als Datei
entfernt. Höchstgröße je Datei: `DOKUMENT_MAX_MB` in `.env` (Standard 25). Personalunterlagen
sehen ausschließlich Personalverwaltung und Schulleitung.

## Förderung: Förderpläne und Nachteilsausgleiche

**Förderpläne** (Verwaltung › Förderung › Förderpläne oder aus der Schülerakte):
Förderschwerpunkte, Lernausgangslage, Stärken, Förderziele mit Maßnahmen, Zuständigkeit und
Evaluation, Verlaufsdokumentation, Fortschreibung des Vorjahresplans. Eine Druckansicht
(„Drucken / PDF“) enthält Unterschriftsfelder für die Aushändigung.

**Nachteilsausgleiche**: Maßnahmen aus einem anpassbaren Katalog (z. B. Zeitverlängerung,
separater Raum, Vorlesen), betroffene Fächer, Geltungsdauer, Beschluss. Maßnahmen mit
**Notenschutz** sind gekennzeichnet. Lehrkräfte sehen in der Notenübersicht und Klassenliste
eine Markierung „NTA“ bei allen Schüler:innen mit gültigem Nachteilsausgleich im eigenen Fach.

**Elternbestätigung**: Bei jedem Plan und Nachteilsausgleich wird vermerkt, wann er wem
ausgehändigt wurde und wann die Eltern den Erhalt bestätigt haben („Erhalt bestätigen“).
Wird ein Dokument danach inhaltlich geändert, erscheint der Hinweis „seit Aushändigung
geändert“. Die Startseite zeigt offene Bestätigungen, fällige Evaluationen und ablaufende
Nachteilsausgleiche. Sobald es ein Elternportal gibt, können Eltern dort selbst abhaken.

| Rolle | Rechte in der Förderung |
| --- | --- |
| Förderkoordination, Schulleitung | alles, auch Genehmigung von Nachteilsausgleichen |
| Klassenleitung | Förderpläne der eigenen Klasse anlegen und bearbeiten, Nachteilsausgleiche beantragen, Aushändigung und Erhalt vermerken |
| Fachlehrkraft | Förderpläne und Nachteilsausgleiche der eigenen Schüler:innen lesen, Verlaufseinträge ergänzen |
| Sekretariat | nur gültige Nachteilsausgleiche (für die Prüfungsorganisation), keine Förderpläne |

Die Rolle *Förderkoordination* wird unter Verwaltung › Benutzer zugewiesen.

## Sprache: Deutsch und Englisch

Oben rechts (Weltkugel-Symbol) lässt sich die Oberfläche zwischen **Deutsch** und **English**
umschalten – im Portal ebenso wie in der Verwaltungsoberfläche.

- Die Wahl wird **im Benutzerkonto gespeichert** und gilt danach auf jedem Gerät und Browser.
- Wer noch nie gewählt hat, behält die Sprache, in der er sich zum ersten Mal angemeldet hat
  (vor der Anmeldung: Cookie oder Browsersprache, sonst Deutsch).
- Datumsangaben: Deutsch `03.10.2026`, Englisch britisch `03/10/2026`; Dezimalzeichen Komma bzw. Punkt.
- **Kataloge** (Fächer, Halbjahre, Bildungsgänge, Abschlussarten, Personalbereiche,
  Nachweisarten, Notenskalen, Zusatzfelder) haben ein Feld „Bezeichnung (Englisch)“. Ist es leer,
  erscheint auf Englisch die deutsche Bezeichnung.
- **Freie Eingaben** (Namen, Bemerkungen, Ordner- und Prüfungsbezeichnungen, Berufe usw.) werden
  nicht übersetzt.

**Regel ab Version 0.4.1.1:** Jede neue Funktion wird zweisprachig gebaut. Die Übersetzungen
liegen in `src/locale/en/LC_MESSAGES/django.po`; Pflege mit `tools/sprachdateien.py`
(Ablauf in der Datei beschrieben). Ein Test schlägt fehl, sobald ein Text ohne Übersetzung ist.

## Design: Standard, Catppuccin Latte, Catppuccin Mocha

Oben rechts neben der Sprachauswahl (Paletten-Symbol, „Design“) stehen drei Farbschemata zur Wahl –
im Portal, in der Verwaltungsoberfläche und auf der Anmeldeseite:

| Design | Beschreibung |
|---|---|
| **Standard** | das bisherige Grün-Schema; hell oder dunkel je nach Einstellung des Betriebssystems |
| **Catppuccin Latte** | helle Palette von [Catppuccin](https://catppuccin.com) (Akzent Mauve), immer hell |
| **Catppuccin Mocha** | dunkle Palette von Catppuccin, immer dunkel |

- Die Wahl wird wie die Sprache **im Benutzerkonto gespeichert** und gilt auf jedem Gerät;
  vor der Anmeldung merkt sich der Browser sie per Cookie.
- Die Druckansichten (Zeugnis, Protokoll, Gefährdungsmitteilungen) bleiben weiß; nur die
  Bildschirmleiste darüber folgt dem Design.
- Technisch: `data-design` am `<html>`-Element; die Farben stehen als CSS-Variablen in
  `portal.css`, `menueband.css` und `verwaltung.css` (Abschnitte „Designs“). Schriftfarben auf
  getönten Flächen sind gegenüber der Palette leicht abgedunkelt, damit der Kontrast reicht.
  Catppuccin steht unter MIT-Lizenz.

## Update von einer älteren Version

Neuen Ordnerinhalt über den alten kopieren (die `.env` behalten) und erneut `./start.sh`
ausführen. Die Datenbank wird automatisch umgestellt; vorhandene Kategorien werden zu Ordnern.
Bei eingeschalteten Demo-Daten werden die englischen Bezeichnungen der Beispieldaten nachgetragen
und fehlende Beispiele (z. B. Neuanmeldungen) ergänzt. Checklisten-Vorlagen werden beim Start angelegt.

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
| `src/portal` | Startseite, Menüband, Notenübersicht, Klassenliste, Schülerakte, Stufenübersicht, Rollen (`rollen.py`) und Rechteprüfung (`rechte.py`), Sprachwahl, Demo-Daten |
| `src/foerderung` | Förderpläne, Nachteilsausgleiche, Elternbestätigung |
| `src/zeugnisse` | Zeugnisse, Kommentare mit Abzeichnung, Konferenzen; Versetzungsregeln in `versetzung.py` |
| `src/aufnahme` | Neuanmeldungen: Bewerbungsakte, Checklisten, Unterlagen, Übernahme (`uebernahme.py`), Rechte (`rechte.py`) |
| `src/locale` | Übersetzungen (Englisch) |
| `unraid/` | Betrieb auf Unraid: `docker-compose.yml`, `.env.example`, `einrichten.sh` |
| `docker/` | Startskript des Containers, Sicherungsskript |
| `src/config/version.py` | Versionsnummer (kleine Änderungen erhöhen die letzte Stelle) |

Alle Änderungen an Personen, Noten, Fehlzeiten und Mitgliedschaften werden
protokolliert (Schaltfläche „Geschichte“ in der Verwaltungsoberfläche).

Lizenz: vorgesehen AGPL-3.0 (noch zu bestätigen).
