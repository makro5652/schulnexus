# Schulverwaltung (Version 0.4.7.0, Entwicklungsstand)

Open-Source-Schulverwaltung für die DSN: Stammdaten, Klassen und Lerngruppen,
Noten mit Gewichtung, Fehlzeiten, Nachmittagsprogramm, Anhänge zur Schülerakte,
Förderpläne und Nachteilsausgleiche, Neuanmeldungen, Zeugnisse und Konferenzen, Schuljahreswechsel,
Abgänge mit Abgangszeugnis, Archiv und Löschfristen, Schulkalender, Raumbuchung, Elternsprechtage und
Lern- und Entwicklungsgespräche, Office-Startseite für Microsoft 365, Noten-Schnelleingabe und Pflichtnoten mit Frist. Verschlüsselte Ablage von Anhängen und
Sicherungen, Zwei-Faktor-Anmeldung, HTTPS-Betrieb. Läuft im Browser, betrieben mit Docker.

> Nur mit **erfundenen Testdaten** verwenden. Vor echten Schülerdaten: HTTPS einrichten (`HTTPS=1`),
> verschlüsselte Festplatten (Unraid), Schlüssel sicher hinterlegen, Zwei-Faktor-Anmeldung für Leitung und IT
> verpflichtend machen und die Freigabe durch den Datenschutz einholen (siehe „Sicherheit und Verschlüsselung“).

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
| `it` | IT-Administration (Vollzugriff, Benutzer und Einzelrechte, Sicherung) | `DEMO_PASSWORT` in `.env` |
| `schueler`, `eltern` | kein Portalzugang (`eltern` nur mit eingeschaltetem Elternportal) | `DEMO_PASSWORT` in `.env` |

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

## Elternkommunikation

**Menüband › Schüler:innen › Eltern.** Lehrkräfte schreiben den Eltern ihrer Schüler:innen, Eltern antworten,
bestätigen den Erhalt (z. B. des Zeugnisses) – und bei Fehlzeiten oder Verspätungen benachrichtigt das System
die Eltern automatisch.

- **Zustellung ohne Elternkonto:** Eltern erhalten eine E-Mail mit einem persönlichen, signierten und befristeten
  Link (`ELTERN_LINK_TAGE`, Standard 60). Darüber lesen sie die Nachricht, bestätigen den Erhalt und antworten.
  Die E-Mail enthält standardmäßig nur Hinweis und Link, nicht den Inhalt (`ELTERN_EMAIL_INHALT=0`).
  Die Seite erscheint in der bevorzugten Sprache der Kontaktperson (Deutsch/Englisch, umschaltbar).
- **Versand ist ausgeschaltet** (`ELTERN_EMAIL_VERSAND=0`): Nachrichten bleiben im **Postausgang**; der Erhalt kann
  von der Schule vermerkt werden (z. B. Rücklaufzettel). Nach dem Einschalten verschickt
  `python manage.py elternpost_senden` den Postausgang. SMTP-Zugang über `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`,
  `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`.
- **Wichtig:** Eltern müssen den Link öffnen können – der Server muss dafür unter `ELTERN_LINK_BASIS` aus dem Internet
  per HTTPS erreichbar sein (z. B. Reverse Proxy oder Tailscale Funnel). Eine reine Tailscale-Adresse genügt nicht.
- **Empfänger:innen:** nur Kontaktpersonen mit Auskunftsrecht; vorausgewählt sind die Sorgeberechtigten.
  Nachrichten an eine Klasse oder Lerngruppe erzeugen je Familie ein eigenes Gespräch.
  Eltern sehen die Beiträge der Schule und ihre eigenen Antworten, nicht die anderer Kontaktpersonen.
- **Zeugnisempfang:** Auf der Zeugnisseite einer Klasse fordert die Klassenleitung (oder Koordination, Sekretariat)
  für alle freigegebenen Zeugnisse die Empfangsbestätigung an; die Spalte „Erhalt (Eltern)“ zeigt den Stand.
- **Automatische Benachrichtigung bei Fehlzeiten:** Unter **Benachrichtigungsregeln** legen Schulleitung und
  erweiterte Schulleitung (Verwaltungsleitung, Mittel- und Oberstufenkoordination – diese nur für ihre Jahrgänge)
  Schwellen fest: Fehltage, Fehlstunden, Anzahl oder Minuten der Verspätungen; alle, nicht entschuldigte oder nur
  unentschuldigte Einträge; je Halbjahr oder Schuljahr; auf Wunsch erneut bei jedem Vielfachen. Geprüft wird nach jedem
  Speichern einer Fehlzeit; schulische Veranstaltungen zählen nicht. Beim Anlegen einer Regel werden bereits erreichte
  Schwellen still vorgemerkt – oder, wenn angehakt, sofort benachrichtigt. „Vorschau“ zeigt vorher, wer betroffen wäre.
  Für eine tägliche Prüfung aller Schüler:innen: `python manage.py fehlzeiten_pruefen`.
- **Elternportal mit Anmeldung** ist vorbereitet, aber ausgeschaltet (`ELTERNPORTAL_AKTIV=0`). Eltern mit Benutzerkonto
  (Rolle „Eltern“) sehen dann alle ihre Nachrichten unter `/eltern/`. **Erst nach Zwei-Faktor-Anmeldung und
  Datenschutzfreigabe einschalten**; die Systemprüfung warnt, solange es aktiv ist.

| Rolle | Elternkommunikation |
| --- | --- |
| Lehrer:in | Eltern der eigenen Schüler:innen schreiben; eigene Gespräche; als Klassenleitung alle Gespräche der Klasse |
| Stufenkoordination | alle Gespräche der Stufe; Benachrichtigungsregeln für die Jahrgänge der Stufe |
| Schulleitung | alles |
| Verwaltungsleitung | Zeugnisempfang und automatische Fehlzeiten-Nachrichten, allen Eltern schreiben; Benachrichtigungsregeln |
| Sekretariat | Zeugnisempfang und automatische Fehlzeiten-Nachrichten, allen Eltern schreiben; Regeln lesen |

Persönliche Gespräche zwischen Lehrkräften und Eltern sehen Sekretariat und Verwaltungsleitung nicht.

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
Zugewiesen werden sie unter **System › Benutzerkonten**; die vollständige Rechtetabelle steht im Portal
unter **System › Rollen und Rechte** (für Verwaltungsleitung und Schulleitung).

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
| IT-Administration | Vollzugriff (Superuser): alle Daten, Benutzerkonten, Rollen und Einzelrechte, Sicherung, Wiederherstellung, PDF-Export |
| Schüler:in, Eltern | vorbereitet für Stundenplan bzw. Elternportal; derzeit kein Zugang |

**Einzelrechte (ab 0.4.3.0):** Unter **System › Benutzer und Rechte › Einzelrechte** (nur IT) lassen sich je Konto
Rollen setzen, das Konto sperren, ein vorläufiges Passwort erzeugen und einzelne Rechte zusätzlich **erteilen** oder trotz
Rolle **entziehen** (je Bereich: ansehen, anlegen, ändern, löschen, dazu Sonderrechte). Die Vergabe der Rolle
IT-Administration macht das Konto zum Administrator; man kann sie sich nicht selbst entziehen und das eigene Konto nicht
sperren. Alle Änderungen stehen im Protokoll. Einschränkung: Entzogene Rechte wirken überall dort, wo Modellrechte
geprüft werden (Menüband, Verwaltungsoberfläche, Bearbeiten). Die Sichtbarkeitsregeln nach Klasse und Stufe
(z. B. „Klassenleitung sieht die Akte ihrer Klasse“) hängen an der Rolle und bleiben bestehen.

Die Jahrgänge der Stufen stehen in der `.env` (`MITTELSTUFE=5-10`, `OBERSTUFE=11-12`).
Rechte werden beim Start nur ergänzt, nie entfernt – eigene Anpassungen bleiben erhalten.
Auf die Standardrechte zurücksetzen:
`docker compose exec web python manage.py grundeinrichtung --rechte-zuruecksetzen`.

Beim Update von älteren Versionen werden die Gruppen umbenannt (Lehrkraft → Lehrer:in,
Verwaltung → Sekretariat, Personalverwaltung → HR-Management); die Mitglieder bleiben erhalten.
Das Sekretariat erhält dabei die neuen, engeren Standardrechte.

## Sicherung, Wiederherstellung und PDF-Export

**Menüband › System › Sicherung** – nur Schulleitung und IT-Administration.

- **Sicherung je Modul:** Stammdaten, Unterricht und Noten, Fehlzeiten, Nachmittag/AGs, Förderung, Neuanmeldungen,
  Zeugnisse und Konferenzen, Elternkommunikation, Schuljahreswechsel/Abgänge/Löschfristen, Startseite/Einstellungen,
  Benutzerkonten und Rollen – einzeln oder
  alle zusammen, auf Wunsch mit den hochgeladenen Dateien. Jede Sicherung ist eine ZIP-Datei (Daten als JSON,
  Prüfsummen, Programmversion) zum Herunterladen; Sicherungen anderer Systeme lassen sich hochladen und werden geprüft.
- **Wiederherstellen** setzt die gewählten Module auf den Stand der Sicherung zurück. Die **Vorschau** zeigt je Modul,
  was neu angelegt, überschrieben und gelöscht wird, und welche Daten **anderer Module** dadurch mitbetroffen sind
  (z. B. Fehlzeiten einer seither neu aufgenommenen Schülerin beim Zurücksetzen der Stammdaten). Fehlen Bezüge
  (z. B. Noten zu einer inzwischen gelöschten Schülerin), wird die Wiederherstellung verweigert – dann beide Module
  gemeinsam wiederherstellen. Bestätigung per Häkchen und Eingabe von „WIEDERHERSTELLEN“. **Vor jeder Wiederherstellung
  entsteht automatisch eine Gesamtsicherung.** Wiederherstellen ist nur mit derselben Programmversion (Datenbankstand)
  möglich, mit der gesichert wurde. Das eigene Konto bleibt beim Zurücksetzen der Benutzerkonten erhalten.
- **PDF-Export:** Module wählen, Zeitraum (aktuelles Halbjahr, Schuljahr, letzte 30 Tage, eigener Zeitraum oder ohne
  Begrenzung), Aufteilung (automatisch, je Monat, je Halbjahr, keine). Einträge mit Datum (Fehlzeiten, Noten,
  Nachrichten, Zeugnisse …) werden nach dem Zeitraum gefiltert; Einträge ohne Datum (Personen, Klassen, Kataloge)
  erscheinen als „Bestand“ in eigener Datei; optional das Änderungsprotokoll. Höchstens `PDF_EINTRAEGE_JE_DATEI`
  Einträge (Standard 1500) je Datei, darüber „Teil 1 von n“. Herunterladen einzeln oder als ZIP. Passwörter und
  Link-Schlüssel erscheinen nie im PDF. Die PDFs werden im Hintergrund erstellt; die Seite aktualisiert sich selbst.
- **Protokoll:** Sicherungen, Downloads, Wiederherstellungen, PDF-Exporte, Rechte- und Kontoänderungen,
  Zwei-Faktor-Einstellungen mit Zeit und Person.
- **Ablage:** `MODUL_SICHERUNGEN` (Docker: Volume `modulsicherungen`, Unraid: `${APPDATA}/modulsicherungen`).
  Automatisch, z. B. täglich per Zeitplan: `python manage.py modulsicherung` (bewahrt `SICHERUNG_BEHALTEN_AUTOMATISCH`
  Sicherungen auf). Die tägliche Gesamtsicherung der Datenbank (pg_dump, Unraid) bleibt davon unabhängig bestehen.
- Sicherungen und PDF-Exporte liegen auf dem Server verschlüsselt (`DATEN_SCHLUESSEL`, siehe „Sicherheit und
  Verschlüsselung“). Heruntergeladene Sicherungen am besten mit Passwort verschlüsseln; PDFs zugriffsgeschützt aufbewahren.

## Sicherheit und Verschlüsselung

Ab 0.4.6.0. Ausführliche Einrichtung auf Unraid: `ANLEITUNG-UNRAID.md`, Abschnitte „HTTPS“ und „Verschlüsselung“.

- **Verschlüsselte Ablage (AES-256-GCM):** Anhänge der Personenakten, Bewerbungsunterlagen, Modulsicherungen und
  PDF-Exporte werden mit dem Schlüssel `DATEN_SCHLUESSEL` aus der `.env` verschlüsselt gespeichert und beim Öffnen in
  der Anwendung entschlüsselt. `start.sh` bzw. `unraid/einrichten.sh` erzeugen den Schlüssel beim Einrichten bzw. beim
  ersten Update und zeigen ihn einmal an. Beim Start des Containers werden ältere, noch unverschlüsselte Dateien
  automatisch nachverschlüsselt (`manage.py dateien_verschluesseln`). Die Datenbankfelder selbst bleiben lesbar; sie
  werden durch die verschlüsselten Festplatten des Servers geschützt.
  **Den Schlüssel getrennt vom Server aufbewahren** (ausgedruckt im Tresor): Ohne ihn sind verschlüsselte Dateien und
  Sicherungen nicht wiederherstellbar. Den Schlüssel nicht austauschen, solange Dateien damit verschlüsselt sind.
- **Sicherungen herunterladen:** mit Passwort (mind. 10 Zeichen; AES-256, Schlüssel aus dem Passwort per scrypt) als
  `.enc`-Datei oder bewusst unverschlüsselt als ZIP. Hochladen nimmt ZIP, passwortverschlüsselte Dateien (Passwort
  angeben) und Dateien mit dem Serverschlüssel derselben Installation an.
- **Zwei-Faktor-Anmeldung (TOTP):** Kontomenü › **Sicherheit** bzw. Menüband › Start › Konto › Sicherheit. Für alle
  freiwillig; QR-Code mit einer Authenticator-App scannen (Microsoft Authenticator, Google Authenticator, Aegis …),
  Code bestätigen, zehn **Ersatzcodes** ausdrucken. Danach fragt die Anmeldung nach Passwort und sechsstelligem Code
  (5 Versuche, 5 Minuten). Die **IT** kann sie je Konto **verpflichtend** machen und bei verlorenem Telefon
  **zurücksetzen** (System › Benutzer und Rechte › Konto); alles wird protokolliert. Die Verwaltungsoberfläche
  (`/verwaltung/`) meldet sich ebenfalls über diese Anmeldung an.
- **HTTPS:** `HTTPS=1` setzen, sobald die Seite über https erreichbar ist (z. B. `tailscale serve`), und die
  https-Adresse in `CSRF_TRUSTED_ORIGINS` eintragen. Dann gelten sichere Cookies und HSTS. `HINTER_PROXY=1` und
  `HTTPS_UMLEITUNG=1` nur, wenn der vorgeschaltete Proxy den Kopf `X-Forwarded-Proto` zuverlässig setzt.
- **Sicherheitsköpfe:** Content-Security-Policy (keine fremden Skripte, keine Einbettung in fremde Seiten),
  Permissions-Policy, Cross-Origin-Opener-Policy, Referrer-Policy `same-origin`, X-Frame-Options `DENY`.
- **Startprüfung:** `manage.py check` warnt ohne `DATEN_SCHLUESSEL`, ohne HTTPS und bei fehlender https-Adresse in
  `CSRF_TRUSTED_ORIGINS`.

## Office (Microsoft 365)

**Menüband › Start › Office** bzw. Kontomenü › Office. Kacheln für Outlook, Kalender, Teams, OneDrive, Word, Excel,
PowerPoint, OneNote, SharePoint, Forms und die Microsoft-365-Startseite; jede öffnet die Anwendung **in einem neuen
Tab**. Einbetten ist nicht möglich, weil Microsoft das Anzeigen in fremden Seiten untersagt. Mit **„Menüband
ausblenden“** verschwindet die Menüleiste auf dieser Seite vollständig (der Browser merkt sich die Wahl); die
schwebende Schaltfläche **„Menüband einblenden“** holt sie zurück.
Die IT pflegt die Kacheln unter **Office › Kacheln verwalten** (Titel deutsch/englisch, Adresse, Symbol, Farbe,
Reihenfolge). In Adressen wird `{mandant}` durch `OFFICE_MANDANT` ersetzt, z. B. `https://{mandant}.sharepoint.com`.

## Schuljahre, Schuljahreswechsel, Abgang und Archiv

Ablauf der Schullaufbahn: **Aufnahme → Klasse → Versetzung → Schuljahreswechsel → Abgang mit Abgangszeugnis → Archiv.**

- **Schuljahre** (Menüband › Schulleitung › Schuljahr › Schuljahreswechsel; nur Schulleitung und IT): neues Schuljahr anlegen (Vorschlag: gleiche Lage ein Jahr später, Halbjahre werden verschoben
  übernommen), ein Schuljahr als **aktuelles** setzen.
- **Schuljahreswechsel in drei Schritten:**
  1. *Klassen planen:* Für jede Stammklasse wird eine Nachfolgeklasse vorgeschlagen (9a → 10a, Klassenleitung bleibt,
     Vorgängerklasse wird verknüpft); Klassen der höchsten Jahrgangsstufe laufen aus. Weitere Klassen (z. B. neue
     Eingangsklassen, Klassen für Wiederholer:innen) lassen sich ergänzen.
  2. *Entscheidungen:* je Schüler:in versetzt, nicht versetzt (Wiederholung), freiwillige Wiederholung, Überspringen,
     Zurückstufung, Abschluss oder Abgang – vorgeschlagen aus dem Beschluss der **Versetzungskonferenz**, sonst aus dem
     Vermerk im **Jahreszeugnis**, sonst aus der Schullaufbahn. Die Zielklasse wird passend zum neuen Jahrgang
     vorgeschlagen; Unvollständiges wird markiert.
  3. *Durchführen:* Alte Klassen und Gruppen enden mit dem letzten Schultag, die neuen Klassen gelten ab dem ersten
     Schultag des neuen Schuljahres; je Schüler:in entsteht ein neuer Laufbahnabschnitt (Bildungsgang wird bei Bedarf
     angepasst, z. B. Sek I → Oberstufe). Wer die Schule verlässt, geht ins Archiv. Optional wird das neue Schuljahr
     zugleich das aktuelle.
- **Zurücknehmen:** für einzelne Schüler:innen (danach Entscheidung ändern und erneut übertragen) oder für den ganzen
  Wechsel (stellt Klassen, Laufbahn, Status und das aktuelle Schuljahr wieder her; leere, neu angelegte Klassen
  werden entfernt). Bereits erfasste Noten, Fehlzeiten und Zeugnisse bleiben erhalten.
- **Im laufenden Schuljahr** (Schülerakte › Laufbahn und Abgang): Klassenwechsel, Höherstufung (Überspringen) oder
  Zurückstufung zu einem Datum; der Laufbahnabschnitt wird geteilt. Die jeweils letzte Änderung lässt sich zurücknehmen.
- **Abgang:** letzter Schultag, Art (Schulwechsel, Umzug, Abschluss, Sonstiges), Grund/Zielschule. Klassen und Gruppen
  enden, ein Schülerkonto wird gesperrt, die Akte geht ins **Archiv**. Das **Abgangszeugnis** entsteht als Entwurf im
  Zeugnismodul (Noten des laufenden Halbjahres, im 2. Halbjahr einschließlich epochaler Fächer des 1. Halbjahres,
  Abgangsvermerk) und wird dort wie jedes Zeugnis freigegeben und gedruckt. Rücknahme = Wiederaufnahme.
- **Archiv** (Schulleitung › Archiv bzw. Verwaltung › Sekretariat › Archiv): abgegangene Schüler:innen mit letzter Klasse, Austritt,
  Abgangszeugnis und nächster Löschung. Archivierte Akten sind nur lesbar (Änderungen in der Verwaltungsoberfläche nur
  durch Schulleitung und IT) und erscheinen in keiner Klassenliste.
- **Schuljahre beachten:** Die Schülerakte zeigt Fehlzeiten, Noten und Klasse für ein wählbares Schuljahr der Laufbahn;
  Klassenlisten vergangener und künftiger Schuljahre zeigen die Mitglieder zum passenden Stichtag; ein Klassenwechsel
  über „Zuordnen“ führt die Schullaufbahn mit.
- **Erinnerung:** Ab sechs Wochen vor Ende des aktuellen Schuljahres erinnert die Startseite an den Schuljahreswechsel.

## Löschfristen

**Menüband › Schulleitung › Archiv › Löschfristen** – festlegen und löschen: Schulleitung und IT; lesen: Verwaltungsleitung.

- Aufbewahrungsfristen je Datenkategorie für **abgegangene** Schüler:innen (Fehlzeiten und AG-Teilnahme,
  Elternnachrichten, Gesundheitsangaben, Förderung, Noten, Anhänge, Anmeldeunterlagen, Halbjahres-/Jahreszeugnisse,
  Kontaktdaten, gesamte Akte). Frist in Jahren ab Austritt oder ab Ende des Kalenderjahres des Austritts; je Kategorie
  „erinnern und nach Bestätigung löschen“ oder „nur erinnern“; abschaltbar; Feld für Grundlage/Hinweis.
- Die **Vorschlagswerte** (1 bis 5 Jahre, gesamte Akte mit Abgangszeugnis 50 Jahre) sind bewusst vorsichtig und
  ersetzen keine Festlegung durch die Schulleitung.
- Ist eine Frist abgelaufen, zeigt die **Startseite der Schulleitung** die Zahl fälliger Löschungen. Auf der Seite
  Löschfristen: endgültig löschen (mit Bestätigung) oder mit Datum und Grund aufschieben. Gelöscht werden die Einträge,
  ihr Änderungsprotokoll und zugehörige Dateien; „Kontaktdaten“ leert Anschrift und Telefon, löst Elternverknüpfungen,
  entfernt Elternpersonen ohne weitere Kinder und das Schülerkonto. Der Nachweis enthält nur Schülernummer,
  Kategorie, Anzahl, Zeitpunkt und Person. **Ältere Modulsicherungen enthalten gelöschte Daten weiterhin**, bis sie
  selbst gelöscht werden.

## Schulkalender, Räume, Elternsprechtag und LEG

**Menüband › Termine** – für alle Beschäftigten.

- **Schulkalender:** Monatsansicht (auf dem Handy als Liste), Filter nach Art (Ferien, Feiertag, Schulveranstaltung,
  Konferenz, Prüfung, Elternabend, Fahrt, Frist), Liste der nächsten 30 Tage, Startseitenkarte „Nächste Termine“.
  Eintragen: Sekretariat, Verwaltungsleitung, Schulleitung, Stellvertretung, Stufenkoordination; Lehrkräfte lesen.
  Termine können zweisprachig sein, als unterrichtsfrei markiert und im Elternportal angezeigt werden. Mit Raum und
  Uhrzeit wird der Raum automatisch belegt. **Kalender abonnieren** lädt eine iCalendar-Datei (z. B. für Outlook).
- **Räume:** Tagesplan aller Räume mit Zeitleiste, Buchung einmalig oder wöchentlich (z. B. AG); Überschneidungen im
  selben Raum sind ausgeschlossen – bei einer Serie wird nichts gebucht, wenn ein Termin kollidiert. Eigene Buchungen
  löscht man selbst, fremde nur die Verwaltung. Räume pflegt die Verwaltung (Termine › Räume verwalten).
- **Elternsprechtag und Lern- und Entwicklungsgespräche (LEG):** plant die **Stellvertretende Schulleitung** (neue
  Rolle, Demo-Konto `stellvertretung`) bzw. die Schulleitung:
  1. *Entwurf:* Art, Jahrgänge, Gesprächsdauer, Wechselzeit, Höchstzahl je Kind; **flexibles Zeitraster** aus beliebig
     vielen Zeitfenstern je Tag (Pausen ergeben sich aus Lücken) und mehreren Tagen. Teilnehmende Lehrkräfte werden
     vorgeschlagen – beim Elternsprechtag alle Lehrkräfte, die die Jahrgänge unterrichten, und die Klassenleitungen;
     beim LEG die Klassenleitungen. Raum je Lehrkraft, Räume werden auf Wunsch im Raumplan belegt.
  2. *Verfügbarkeit:* Jede Lehrkraft sperrt einzelne Zeiten oder schränkt sich auf „nur von … bis …“ ein, gibt Raum und
     einen Hinweis für Eltern an und bestätigt. Die Startseite erinnert daran.
  3. *Buchung offen:* Eltern buchen im **Elternportal** (nur wenn `ELTERNPORTAL_AKTIV=1`; Anmeldung mit Elternkonto)
     innerhalb des Buchungszeitraums – nur für ihre Kinder (Sorge- oder Auskunftsrecht) und nur bei deren Lehrkräften;
     Absagen ebenso. Sekretariat und Planung tragen Gespräche für alle Lehrkräfte ein, Lehrkräfte für ihre
     Schüler:innen.
  4. *Buchung geschlossen:* Eltern sehen ihre Termine; die Schule kann weiter eintragen.
  Regeln: eine Zeit je Lehrkraft nur einmal, kein Kind bzw. keine Kontaktperson zu zwei Gesprächen gleichzeitig,
  je Lehrkraft und Kind höchstens ein Gespräch, Höchstzahl je Kind. Übersicht aller Gespräche zum Drucken, Liste je
  Lehrkraft zum Drucken, beim LEG Liste der Schüler:innen ohne Termin.

## Noten mit Bewertungsordnern

Jeder Unterricht hat eine frei gestaltbare Ordnerstruktur, z. B.:

```
Quartal 1 (50)
├─ Klausur Quartal 1 (50)
└─ Sonstige Mitarbeit Quartal 1 (50)        Gewichte darin: Prozent
   ├─ Test (20 %)
   ├─ Mitarbeit 31.10. (4 %)   → Note 2+
   └─ …
Quartal 2 (50)
└─ …
```

- Ordner und Leistungsnachweise sind **frei benennbar**, Leistungsnachweise haben ein **Datum** und ein **Gewicht**.
- **Gewichtsart je Ebene** (ab 0.4.7.0): Für die oberste Ebene und für jeden Ordner wählt die Lehrkraft, ob die
  Gewichte darin **relativ** (z. B. 2 : 1 oder 50 : 50) oder **in Prozent** angegeben werden. Bei Prozent zeigt die
  Struktur die Summe und meldet, wie viel bis 100 % fehlt oder zu viel ist; ein einzelner Wert darf 100 nicht
  übersteigen. Gerechnet wird in beiden Fällen als gewichteter Mittelwert; **leere Einträge** (z. B. ein noch nicht
  begonnenes Quartal) werden übersprungen, die übrigen tragen dann entsprechend mehr.
- Ein Ordner kann Unterordner und Leistungsnachweise gleichzeitig enthalten (bis zu 5 Ebenen).
- Notenübersicht und Struktur zeigen für jeden Eintrag seinen planmäßigen **Anteil an der Gesamtnote**.
- **Bewertungsstruktur im Portal:** Notenübersicht › „Bewertungsstruktur“ – Ordner anlegen, umbenennen, Gewichte und
  Gewichtsart ändern, Reihenfolge, leere Ordner und Leistungsnachweise löschen. Die Verwaltungsoberfläche ist dafür
  nicht mehr nötig.
- Die Gewichtungsvorlage legt beim Anlegen eines Unterrichts nur die **Start-Ordner** an.
- **Notenformat:** je Unterricht eine Skala – Sek I „1 bis 6 mit Tendenzen“ (1+ … 6) oder Sek II „0 bis 15 Punkte“;
  zusätzlich je Leistungsnachweis optional BE mit Notenschlüssel.

**Schnelleingabe** (ab 0.4.7.0): Notenübersicht › „Noten eintragen“ oder Klick auf einen Leistungsnachweis.
Oben Ordner, Bezeichnung (mit Vorschlägen aus früheren Einträgen), Datum und Gewicht; bei einem Prozent-Ordner wird
angezeigt, wie viel Prozent im Ordner schon vergeben sind. Darunter die Klassenliste mit einem Textfeld je
Schüler:in:

| Eingabe | Bedeutung |
| --- | --- |
| `2+`, `2`, `2-` (Sek II: `15` … `0`) | Note der Skala |
| `34`, `34,5` | erreichte BE, wenn ein Notenschlüssel gewählt ist (Note wird berechnet und sofort angezeigt) |
| `=2+` | Note direkt, auch bei Notenschlüssel |
| `e`, `u`, `b`, `nb` | entschuldigt, unentschuldigt, befreit, nicht bewertbar |
| `u 6` | unentschuldigt mit Note |
| leer | keine Note |

Enter oder ↓ springt zur nächsten Zeile, ↑ zur vorigen; eine Notenspalte aus Excel lässt sich in das erste Feld
einfügen. Jede Eingabe wird sofort geprüft; ist eine ungültig, wird **nichts** gespeichert und die Zeile markiert.
„Speichern und nächsten anlegen“ öffnet gleich den nächsten Eintrag im selben Ordner. Einzelgewichte mit Begründung
sind über „Einzelgewichte anzeigen“ erreichbar. Eintragen dürfen die unterrichtende Lehrkraft, die Schulleitung und
die IT.

**Gewichtung pro einzelner Note:** Zusätzlich zum Gewicht des Leistungsnachweises kann jede
einzelne Note ein individuelles Gewicht bekommen (z. B. verkürzte Nachschreibarbeit). Eine
Abweichung muss begründet werden und ist in der Notenübersicht mit „×Gewicht“ markiert.

**Leistungsvorgaben – Pflichtnoten mit Frist** (ab 0.4.7.0): Menüband › Unterricht › Leistungsvorgaben.
Schulleitung und Stellvertretung legen Vorgaben für alle Jahrgänge an, die Stufenkoordination für ihre Jahrgänge.
Eine Vorgabe nennt Halbjahr, Jahrgänge, Fächer (keine Auswahl = alle), optional „Ordner enthält“ (z. B. „Quartal 1“)
und „Bezeichnung enthält“ (z. B. „Klassenarbeit“), eine Mindestanzahl und eine Frist, z. B. „Quartalsnote Sonstige
Mitarbeit Q1, Jahrgänge 5–10, alle Fächer, bis 30.10.“. Ein Leistungsnachweis zählt, wenn sein Datum spätestens am
Tag der Frist liegt, er passt und für alle Schüler:innen, die an diesem Tag zur Gruppe gehörten, eine Note oder ein
Vermerk eingetragen ist. Die Übersicht zeigt je Unterricht eine Ampel (erfüllt, in Arbeit, offen, überfällig);
Lehrkräfte sehen ihren eigenen Unterricht, Koordination und Leitung ihre Jahrgänge bzw. alle. Lehrkräfte werden auf
der Startseite 14 Tage vor der Frist erinnert, die Leitung sieht die Zahl überfälliger Vorgaben; die Notenübersicht
eines Unterrichts zeigt den Stand seiner Vorgaben. Die Bewertungsstruktur selbst bleibt frei.

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
- **Registerkarten:** Start · Termine · Schüler:innen · Unterricht · Förderung · Schulleitung · Verwaltung · Personal · System,
  jeweils mit beschrifteten Befehlsgruppen. Getrennt sind die **akademische Verwaltung** und die **Administration**:
  - *Schulleitung* (akademisch): Schuljahr (Schuljahreswechsel, Schuljahre, Zeitraster, Bildungsgänge, Abschlussarten),
    Unterrichtsorganisation (Unterrichtsverteilung, Fächer, Notenskalen, Gewichtungsvorlagen), Archiv und Löschfristen.
  - *Verwaltung* (Administration): Sekretariat (Schüler:in anlegen, Eltern und Kontakte, Klassen und Gruppen,
    Mitgliedschaften, Schullaufbahn, Archiv), Nachmittag (AG-Angebote, Wünsche, Zuteilungen), Finanzen
    (Rechnungsempfänger, Elternprofile, Dienstleister, Vertragsunterlagen).
  - *System* (IT): Benutzerkonten, Rollen und Einzelrechte, eigene Datenfelder, Sicherung, PDF-Export, Protokoll.
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

**Förderpläne** (Menüband › Förderung › Förderpläne oder aus der Schülerakte):
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

Die Rolle *Förderkoordination* wird unter System › Benutzerkonten zugewiesen.

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
ausführen. Ab 0.4.6.0 ergänzt das Skript die `.env` einmalig um `DATEN_SCHLUESSEL` (wird angezeigt –
sicher aufbewahren) sowie `OFFICE_MANDANT` und `HTTPS`; vorhandene Dateien werden beim Start verschlüsselt. Die Datenbank wird automatisch umgestellt; vorhandene Kategorien werden zu Ordnern.
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
| Elternpost versenden (nach dem Einschalten) | `docker compose exec web python manage.py elternpost_senden` |
| Fehlzeitenregeln für alle prüfen | `docker compose exec web python manage.py fehlzeiten_pruefen` |
| Modulsicherung aller Module | `docker compose exec web python manage.py modulsicherung` |
| Neuen Datenschlüssel erzeugen (nur Ersteinrichtung) | `docker compose exec web python manage.py schluessel_erzeugen` |
| Vorhandene Dateien verschlüsseln (läuft auch beim Start) | `docker compose exec web python manage.py dateien_verschluesseln` |
| Sicherheitsprüfung | `docker compose exec web python manage.py check --deploy` |

## Aufbau

| Ordner | Inhalt |
| --- | --- |
| `src/stammdaten` | Schuljahre, Halbjahre, Personen, Schüler:innen, Personal, Eltern-Beziehungen, Gruppen, Mitgliedschaften, Fächer, Einwilligungen, Dokumente |
| `src/noten` | Notenskalen, Notenschlüssel (BE → Note), Gewichtungsvorlagen, Unterricht, Leistungsnachweise, Noten, Zeugnisnoten; Berechnung in `berechnung.py` |
| `src/fehlzeiten` | Zeitraster, Fehlzeiten (ganztägig, stundenweise, Verspätung) |
| `src/nachmittag` | AG-Angebote, Wünsche, Losverfahren in `zuteilung.py` |
| `src/portal` | Startseite, Menüband, Office-Kacheln, Verschlüsselung (`krypto.py`), Zwei-Faktor-Anmeldung (`zweifaktor.py`, `sicherheit.py`), Notenübersicht, Klassenliste, Schülerakte, Stufenübersicht, Rollen (`rollen.py`) und Rechteprüfung (`rechte.py`), Sprachwahl, Demo-Daten |
| `src/foerderung` | Förderpläne, Nachteilsausgleiche, Elternbestätigung |
| `src/zeugnisse` | Zeugnisse, Kommentare mit Abzeichnung, Konferenzen; Versetzungsregeln in `versetzung.py` |
| `src/sicherung` | Modulsicherung und Wiederherstellung (`archiv.py`), PDF-Export (`pdf.py`), Benutzer und Einzelrechte (`konten.py`), Protokoll |
| `src/elternkontakt` | Elternkommunikation: Gespräche, Empfänger:innen, Links und E-Mail (`versand.py`), Fehlzeitenregeln (`pruefung.py`), Elternseite (`eltern.py`) |
| `src/laufbahn` | Schuljahreswechsel (`wechsel.py`), Klassenwechsel und Abgang (`ereignisse.py`), Archiv, Löschfristen (`loeschung.py`) |
| `src/termine` | Schulkalender, Räume und Raumbuchung, Sprechtage (`sprechtag.py`), Elternportal-Buchung (`eltern.py`) |
| `src/aufnahme` | Neuanmeldungen: Bewerbungsakte, Checklisten, Unterlagen, Übernahme (`uebernahme.py`), Rechte (`rechte.py`) |
| `src/locale` | Übersetzungen (Englisch) |
| `unraid/` | Betrieb auf Unraid: `docker-compose.yml`, `.env.example`, `einrichten.sh` |
| `docker/` | Startskript des Containers, Sicherungsskript |
| `src/config/version.py` | Versionsnummer (kleine Änderungen erhöhen die letzte Stelle) |

Alle Änderungen an Personen, Noten, Fehlzeiten und Mitgliedschaften werden
protokolliert (Schaltfläche „Geschichte“ in der Verwaltungsoberfläche).

Lizenz: vorgesehen AGPL-3.0 (noch zu bestätigen).
