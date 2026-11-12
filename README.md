# Schulnexus (Version 0.4.9.2, Entwicklungsstand)

**Schulnexus** ist eine Open-Source-Schulverwaltung für Schulen (bis 0.4.8.1 „Schulverwaltung“, in 0.4.9.0 kurz „edunex“): Stammdaten, Klassen und Lerngruppen,
Noten mit Gewichtung, Fehlzeiten, Nachmittagsprogramm, Anhänge zur Schülerakte,
Förderpläne und Nachteilsausgleiche, Neuanmeldungen, Zeugnisse und Konferenzen, Schuljahreswechsel,
Abgänge mit Abgangszeugnis, Archiv und Löschfristen, Schulkalender, Raumbuchung, Elternsprechtage und
Lern- und Entwicklungsgespräche, Office-Startseite für Microsoft 365, Noten-Schnelleingabe, Pflichtnoten mit Frist,
Jahresnote, Klausurregeln, Notensperre sowie Notenübersicht als Excel und Notenbogen als PDF. Verschlüsselte Ablage von Anhängen und
Sicherungen, Zwei-Faktor-Anmeldung, HTTPS-Betrieb. Läuft im Browser, betrieben mit Docker.

> Nur mit **erfundenen Testdaten** verwenden. Vor echten Schülerdaten: HTTPS einrichten (`HTTPS=1`),
> verschlüsselte Festplatten (Unraid), Schlüssel sicher hinterlegen, Zwei-Faktor-Anmeldung für Leitung und IT
> verpflichtend machen und die Freigabe durch den Datenschutz einholen (siehe „Sicherheit und Verschlüsselung“).

## Starten auf dem MacBook

1. **Docker Desktop** installieren und starten: https://www.docker.com/products/docker-desktop/
2. Den Ordner `schulnexus` entpacken, z. B. nach `~/Projekte/schulnexus`.
3. Terminal öffnen und eingeben:

   ```sh
   cd ~/Projekte/schulnexus
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

**Menüband › Schüler:innen › Klassen und Gruppen** (oder in der Klassenliste „Mitglieder zuordnen“) öffnet eine
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
- **Rechte:** Sekretariat, Verwaltungsleitung, Schulleitung und IT-Administration alle Gruppen; Stufenkoordination die
  Gruppen ihrer Stufe (AGs ohne Jahrgang bleiben bei der Verwaltung).
- **Fächer und Lehrkräfte, Klasse bearbeiten, neue Schüler:innen:** siehe „Klassen und Gruppen: Fächer und Lehrkräfte (ab 0.4.14.0)“.

## Quellcode von GitHub holen

Der Quellcode liegt im privaten Repository `makro5652/schulnexus`. Auf einem Server:

```sh
git clone https://github.com/makro5652/schulnexus.git
cd schulnexus
```

Bei einem privaten Repository fragt `git clone` nach Benutzername und Passwort: Als Passwort einen
*Personal Access Token* eingeben (github.com/settings/tokens, „Fine-grained“, nur Lesezugriff auf
„Contents“ dieses Repositorys). Neue Versionen später mit `git pull` holen und das jeweilige
Einrichtungsskript erneut starten (die `.env` bleibt erhalten, sie steht nicht im Repository).

## Betrieb auf einem VPS mit Traefik (ab 0.4.9.0)

Für einen Server im Internet, auf dem bereits **Traefik** als Reverse-Proxy mit Let's Encrypt läuft
(z. B. ein Hostinger-VPS mit Docker). Schulnexus ist dann nur über `https://<Domain>` erreichbar; der
Port 8000 wird ausschließlich an `127.0.0.1` gebunden.

1. DNS-Eintrag (A-Eintrag) für die gewünschte Adresse, z. B. `schule.example.org`, auf die IP des Servers setzen.
2. Quellcode auf den Server holen (siehe oben, oder ZIP hochladen und mit `unzip` entpacken).
3. Im Projektordner ausführen:

   ```sh
   sh vps/einrichten.sh schule.example.org
   ```

   Das Skript erzeugt die `.env` mit zufälligen Passwörtern und dem Verschlüsselungsschlüssel, stellt
   HTTPS-Betrieb hinter dem Proxy ein (`HTTPS=1`, `HINTER_PROXY=1`, `ALLOWED_HOSTS`,
   `CSRF_TRUSTED_ORIGINS`) und ermittelt Docker-Netzwerk, Entrypoint und Zertifikats-Resolver aus dem
   laufenden Traefik und den Labels der übrigen Container. Die Vorschläge lassen sich mit der
   Eingabetaste übernehmen oder überschreiben.
4. Am Ende zeigt das Skript Adresse und Zugangsdaten. Den `DATEN_SCHLUESSEL` getrennt vom Server aufbewahren.

Update: `git pull` (oder neues ZIP entpacken, `.env` behalten) und `sh vps/einrichten.sh` erneut ausführen.
Befehle für den laufenden Betrieb immer mit beiden Dateien, z. B.
`docker compose -f docker-compose.yml -f vps/traefik.yml logs -f web`.
Entfernen samt aller Daten: `docker compose -f docker-compose.yml -f vps/traefik.yml down -v`.

> Ein öffentlich erreichbarer Server ist für **Demo-Daten** gedacht. Das Elternportal bleibt aus
> (`ELTERNPORTAL_AKTIV=0`); für Leitung und IT die Zwei-Faktor-Anmeldung verpflichtend machen.

**Traefik im Host-Netzwerk** (ab 0.4.9.5): Läuft Traefik mit `network_mode: host` – so beim Traefik aus dem
Docker-Manager eines Hostinger-VPS (erkennbar daran, dass `docker ps` beim Traefik-Container keine Ports anzeigt,
`ss -ltnp` aber `traefik` auf 80 und 443) –, erkennt das Skript dies, fragt nicht nach einem Netzwerk und verwendet
`vps/traefik-host.yml` (nur Labels, kein gemeinsames Netzwerk). Das Skript trägt die verwendeten Dateien als
`COMPOSE_FILE` in die `.env` ein; danach genügen im Projektordner einfache Befehle wie `docker compose logs -f web`.

Ohne Traefik: siehe nächsten Abschnitt (mitgelieferter Caddy). Alternativ einen eigenen Reverse-Proxy
(z. B. Nginx Proxy Manager) auf `127.0.0.1:8000` zeigen lassen; die Einstellungen in der `.env` sind dieselben.

## Betrieb auf einem VPS ohne Traefik (Caddy, ab 0.4.9.4)

Für einen Server im Internet **ohne** vorhandenen Reverse-Proxy (z. B. ein frischer Hostinger-VPS mit Docker).
Mitgeliefert wird ein kleiner **Caddy**-Container, der das HTTPS-Zertifikat von Let's Encrypt selbst holt und
erneuert. Die Anwendung selbst ist nur an `127.0.0.1:8000` gebunden; von außen sind nur die Ports 80 und 443 offen.

Voraussetzungen: DNS-A-Eintrag der Adresse zeigt auf die IP des Servers; Ports **80 und 443 sind frei** (kein
Traefik, Nginx oder Apache auf dem Server) und in der Firewall freigegeben. Läuft bereits ein Traefik, stattdessen
den Abschnitt „Betrieb auf einem VPS mit Traefik“ verwenden.

```sh
git clone https://github.com/makro5652/schulnexus.git
cd schulnexus
sh vps/einrichten-caddy.sh schule.example.org
```

Das Skript prüft, ob die Ports 80/443 frei sind, erzeugt beim ersten Aufruf die `.env` mit zufälligen
Passwörtern und dem Verschlüsselungsschlüssel, stellt HTTPS-Betrieb hinter dem Proxy ein, baut und startet die
Container und zeigt am Ende Adresse und Zugangsdaten. Eine vorhandene `.env` (z. B. aus einem abgebrochenen
Versuch mit Traefik) wird weiterverwendet und nur um Adresse und HTTPS-Einstellungen ergänzt.

Update: `git pull` und `sh vps/einrichten-caddy.sh` erneut ausführen. Befehle für den laufenden Betrieb immer
mit beiden Dateien, z. B. `docker compose -f docker-compose.yml -f vps/caddy.yml logs -f caddy web`.
Entfernen samt aller Daten: `docker compose -f docker-compose.yml -f vps/caddy.yml down -v`.

## Betrieb auf Unraid (Zugriff über Tailscale)

Für den Dauerbetrieb auf einem Unraid-Server gibt es eine eigene Variante im Ordner `unraid/`:
ein veröffentlichter Port (voreingestellt 8010), erreichbar über das Tailscale des Servers,
Daten unter `/mnt/user/appdata/schulnexus-daten`, tägliche Datenbanksicherung.
Einrichtung im Unraid-Terminal mit `sh unraid/einrichten.sh` – Schritt für Schritt in
[ANLEITUNG-UNRAID.md](ANLEITUNG-UNRAID.md).

## Schulname und Ort einstellen

Der Schulname erscheint auf Zeugnissen, Förderplänen, Druckköpfen, in der Titelleiste und in E-Mails an Eltern.
Der Ort steht auf dem Zeugnis unter dem Datum und auf Briefen.

Beides steht in der Datei `.env` (bei Docker im Projektordner, bei Unraid in `unraid/.env`):

```
SCHULNAME=Name deiner Schule
SCHULORT=Ort deiner Schule
```

Danach den Container neu starten, damit die Änderung wirkt. Ohne Neustart bleibt der alte Name stehen.
Die `.env` gehört nicht ins Repository; die Vorlage `.env.example` enthält nur Platzhalter.

## Zeugnisse, Zeugniskommentare und Konferenzen

Grundlage: Ordnung für den Abschluss der Sekundarstufe I an Deutschen Schulen im Ausland (Sek I-PO, KMK 16.03.2017;
Zeugnismuster Anlage 11) und Richtlinie zur Gestaltung von Bildungsgängen und Abschlüssen in der Sekundarstufe I an
Deutschen Schulen im Ausland (Beschluss vom 18.03.2026). **Menüband › Unterricht › Zeugnisse.**

1. **Zeugnisnoten** (je Kurs, auch über „Zeugnisnoten und Kommentare“ in der Notenübersicht): ganze Noten,
   vorausgewählt ist der gerundete Vorschlag; die Lehrkraft hat die Notenhoheit – Abweichungen werden nur farbig markiert,
   eine Begründung ist freiwillig (ab 0.4.8.1); Vermerke „n.b.“ und „befreit“. Auf dem Zeugnis steht immer die festgesetzte Zeugnisnote.
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

   **Anwesenheit** (ab 0.4.10.0): Namen oder Kürzel tippen, mit den Pfeiltasten wählen, **Tab** oder **Enter**
   übernimmt; jede Person erscheint als Marke mit ×. „Liste öffnen“ zeigt alle Beschäftigten zum Anklicken (mit
   Suchfeld), oben die Lehrkräfte der Klasse; „Alle Lehrkräfte der Klasse übernehmen“ trägt sie gesammelt ein. Gäste
   wie Schulleitung oder Förderkoordination lassen sich ebenso eintragen. In der Verwaltungsoberfläche stehen bei den
   Konferenzbeschlüssen nur die Schüler:innen der Klasse zur Auswahl.

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

**Einzelrechte (ab 0.4.3.0):** Unter **System › Benutzer und Rechte › Konten und Rechte** (nur IT; bis 0.5.0 „Einzelrechte“) lassen sich je Konto
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
  der Anwendung entschlüsselt. `start.sh`, `unraid/einrichten.sh` bzw. `vps/einrichten.sh` erzeugen den Schlüssel beim Einrichten bzw. beim
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
- **Schutz gegen Passwort-Raten (ab 0.4.9.2):** Nach 10 fehlgeschlagenen Anmeldungen eines Kontos bzw. 50 von einer
  IP-Adresse innerhalb von 15 Minuten lehnt die Anmeldung weitere Versuche ab, ohne das Passwort zu prüfen; die Sperre
  endet von selbst. Falsche Codes beim zweiten Faktor zählen mit. Einstellbar mit `ANMELDUNG_MAX_FEHLVERSUCHE`,
  `ANMELDUNG_MAX_JE_IP` und `ANMELDUNG_SPERRE_MINUTEN`. Die IT sieht die Fehlversuche in der Verwaltungsoberfläche
  (Portal › Fehlgeschlagene Anmeldungen) und hebt eine Sperre durch Löschen der Einträge vorzeitig auf. Hinter einem
  Reverse-Proxy (`HINTER_PROXY=1`) zählt die vom Proxy angehängte Adresse im Kopf `X-Forwarded-For`.
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
- **Ordner verschieben** (ab 0.4.8.0): In der Bewertungsstruktur legt „Liegt in“ fest, in welchem Ordner ein Ordner
  liegt; Zyklen und mehr als fünf Ebenen werden abgelehnt.

**Berechnung und Rundung** (ab 0.4.8.0)

- **Rundung zugunsten der Schüler:innen:** Liegt ein Schnitt genau zwischen zwei Noten (x,50), gilt überall die
  bessere Note – in der Tendenzanzeige der Notenübersicht, im Zeugnisvorschlag und bei der Gefährdungsprüfung.
  Beispiele: Ø 2,50 → 2− bzw. Zeugnisnote 2; Ø 4,50 → 4, nicht gefährdet; Sek II 4,50 Punkte → 5 Punkte.
  Je Notenskala umstellbar auf „kaufmännisch“ (Schulleitung › Notenskalen).
- **Unentschuldigt ohne Note** zählt als 6 bzw. 0 Punkte (je Skala einstellbar, leer = zählt nicht). Die
  Notenübersicht zeigt das als „unentsch. (6)“.
- **Datum** eines Leistungsnachweises muss im Halbjahr liegen.
- **Vorläufige Schnitte:** Ist ein Prozent-Ordner noch nicht zu 100 % belegt, weist die Notenübersicht darauf hin
  („Sonstige Mitarbeit ist erst zu 24 % belegt“); fehlende Anteile werden übersprungen. Ob ein Ordner Prozent oder
  relative Gewichte verwendet, wählt die Lehrkraft je Ordner.
- **Jahresnote (Jahrgang 5–10):** Im 2. Halbjahr verrechnet der Vorschlag das 1. Halbjahr mit 40 % und das
  2. Halbjahr mit 60 %. Die Lehrkraft ändert den Anteil je Kurs in der Bewertungsstruktur (0 = nur 2. Halbjahr) und
  wählt als Grundlage den rechnerischen Schnitt oder die festgesetzte Halbjahreszeugnisnote. Die Notenübersicht
  zeigt dann „Ø 2. Halbjahr“, „1. Halbjahr (40 %)“ und den „Jahresvorschlag“. Jahrgänge und Anteil:
  `JAHRESNOTE_JAHRGAENGE` (Standard 5-10) und `JAHRESNOTE_ANTEIL_HJ1` (Standard 40) in der `.env`.
- **Klausuren je Fach** (Schulleitung › Unterrichtsorganisation › Notenregeln; Schulleitung und
  Stellvertretung): Nach Beschluss der Fachkonferenz legt die Schulleitung fest, in welchen Fächern und Jahrgängen
  Klausuren bzw. Klassenarbeiten geschrieben werden, mit festem Anteil (Standard 50 % Klausuren / 50 % Sonstige
  Mitarbeit). Betroffene Kurse erhalten diese beiden obersten Ordner; vorhandene passende Ordner („Schriftlich“,
  „Sonstige Mitarbeit“) werden übernommen, weitere oberste Ordner in „Sonstige Mitarbeit“ verschoben. Lehrkräfte können
  die beiden Ordner nicht umbenennen, umgewichten oder löschen, gliedern darunter aber frei. Fächer ohne Regel bleiben
  frei gestaltbar. Abgeschlossene Halbjahre werden nicht verändert.

**Zeugnisnote** (ab 0.4.8.1)

- **Notenhoheit:** Die Lehrkraft setzt die Zeugnisnote fest. Weicht sie vom gerundeten rechnerischen Vorschlag ab, wird
  das **farbig markiert** (Seite „Zeugnisnoten und Kommentare“, Notenübersicht, Excel, Notenbogen) – eine Begründung
  ist freiwillig. Auf dem Zeugnis steht immer die festgesetzte Zeugnisnote.
- **Nur die Zeugnisnote eintragen:** Unter Schulleitung › Notenregeln › „Zeugnisnote ohne Einzelnoten“ gibt die
  Schulleitung bzw. Stellvertretung frei, in welchen Fächern und Jahrgängen Lehrkräfte die Zeugnisnote ohne
  Einzelnoten eintragen dürfen (keine Fächer gewählt = alle Fächer). Ohne Freigabe braucht eine Zeugnisnote mindestens
  eine Einzelnote; Vermerke („befreit“, „n.b.“) gehen immer. Demo-Daten: Musik, Kunst und Sport in Jahrgang 5–10.

**Notensperre** (ab 0.4.8.0; Unterricht › Zeugnis › Notensperre)

- Automatisch gesperrt sind die Noten einer Klasse und eines Halbjahres, sobald die **Zeugniskonferenz durchgeführt**
  bzw. abgeschlossen ist, und die Noten einer Schülerin / eines Schülers, sobald ihr bzw. sein **Zeugnis freigegeben**
  ist. Gesperrt heißt: keine Noten, Einzelgewichte oder Zeugnisnoten ändern; keine Gewichte, Gliederung oder
  Jahresanteile ändern; keine Leistungsnachweise mit gesperrten Noten löschen; Gewicht, Ordner, Datum und
  Notenschlüssel solcher Leistungsnachweise bleiben unverändert. Das gilt auch in der Verwaltungsoberfläche.
- **Stufenkoordination** (für ihre Jahrgänge), **Schulleitung** und **Stellvertretung** sehen je Klasse den Stand
  (Konferenz, freigegebene Zeugnisse) und können eine Klasse von Hand **sperren**, **zur Korrektur freigeben** oder
  **zurück zur Automatik** stellen – mit Grund und Eintrag im Protokoll.

**Druck und Export** (ab 0.4.8.0): In der Notenübersicht
- **Excel:** Notenübersicht mit allen Noten, Ordnerschnitten, Vorschlag und Zeugnisnote; dazu die Blätter
  „Leistungsnachweise“ (mit Schnitt je Arbeit) und „Bewertungsstruktur“.
- **Notenbogen (PDF):** zuerst die Kursübersicht (quer), dann je Schüler:in ein Bogen mit allen Noten, Gewichten,
  Anteilen, Kommentaren und dem Rechenweg bis zum Vorschlag sowie Unterschriftszeile. Der Knopf „PDF“ neben einem
  Namen erzeugt nur den Bogen dieser Schülerin bzw. dieses Schülers.
- Die Dateien werden nicht auf dem Server gespeichert; jeder Abruf steht im Protokoll.

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
  - *System* (IT): Konten und Rechte (Rollen, Sammelaktionen, Einzelrechte), Benutzerkonten, eigene Datenfelder, Sicherung,
    PDF-Export, Protokoll.
- Jede Rolle sieht nur die Karten und Befehle, für die sie Rechte hat. Beim Öffnen einer Seite
  ist die passende Karte aktiv und der aktuelle Befehl hervorgehoben.
- Mit dem Pfeil rechts neben den Registerkarten lässt sich das Band einklappen; der Browser
  merkt sich die Einstellung. Tastatur: Pfeiltasten wechseln die Karte, Esc schließt Menüs.

**Mein Unterricht – Kursauswahl** (ab 0.4.7.1): Statt einer Kachel je Kurs gibt es eine **Auswahlliste** mit allen
eigenen Kursen des Schuljahres, nach Halbjahr gegliedert (das laufende ist markiert), dazu die Knöpfe
**Notenübersicht**, **Noten eintragen** und **Zeugnisnoten**. Sie steht im Menüband (Unterricht › Mein Unterricht) und
auf der Startseite. Vorausgewählt ist der zuletzt geöffnete Kurs, sonst der erste des laufenden Halbjahres; in der
Liste springt man durch Tippen der Anfangsbuchstaben. Auf Notenübersicht, Schnelleingabe, Bewertungsstruktur und
Zeugnisnoten wechselt **„Kurs wechseln“** direkt zum selben Bereich eines anderen Kurses. So bleiben auch zehn und
mehr Kurse übersichtlich.

Das Portal ist **nur für Beschäftigte** (Verwaltung und Lehrkräfte). Konten ohne Personalakte
und ohne Verwaltungszugang können sich nicht anmelden.

## Startseite

- **Kopf:** Begrüßung, Kalenderblatt mit Datum und Kalenderwoche. Die Suche (Schüler:innen,
  Kolleg:innen, für die Verwaltung auch Eltern) steht in der Titelleiste; gefunden wird nur, wen man sehen darf.
- **Schnellzugriff:** eigene Klassen und Gruppen; **Mein Unterricht** als Auswahlliste (siehe unten).
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

## Design: elf Farbschemata

Oben rechts neben der Sprachauswahl (Paletten-Symbol, „Design“) stehen elf Farbschemata zur Wahl –
im Portal, in der Verwaltungsoberfläche und auf der Anmeldeseite. Das Menü ist gegliedert in
„Automatisch“, „Hell“ und „Dunkel“ (ab 0.6.1; bis dahin Standard, Latte und Mocha):

| Design | Beschreibung |
|---|---|
| **Standard** | das Grün-Schema; hell oder dunkel je nach Einstellung des Betriebssystems |
| **Schulnexus Hell** | das Grün-Schema, immer hell |
| **Ozean** | hell, blauer Akzent |
| **Sepia** | hell, warme Papierfarben – angenehm bei langem Lesen |
| **Catppuccin Latte** | helle Palette von [Catppuccin](https://catppuccin.com) (Akzent Mauve) |
| **Hoher Kontrast** | Schwarz auf Weiß, kräftige Linien, deutlicher Fokusrahmen |
| **Schulnexus Dunkel** | das Grün-Schema, immer dunkel |
| **Nord** | dunkel, kühle Blautöne ([Nord](https://www.nordtheme.com)) |
| **Catppuccin Frappé**, **Macchiato**, **Mocha** | dunkle Paletten von Catppuccin, von mild bis sehr dunkel |

- Die Wahl wird wie die Sprache **im Benutzerkonto gespeichert** und gilt auf jedem Gerät;
  vor der Anmeldung merkt sich der Browser sie per Cookie.
- Die Druckansichten (Zeugnis, Protokoll, Gefährdungsmitteilungen) bleiben weiß; nur die
  Bildschirmleiste darüber folgt dem Design.
- Technisch: `data-design` am `<html>`-Element; die Farben stehen als CSS-Variablen in
  `portal.css`, `menueband.css` und `verwaltung.css` (Abschnitte „Designs“). Schriftfarben auf
  getönten Flächen sind gegenüber der Palette leicht abgedunkelt, damit der Kontrast reicht.
  Catppuccin steht unter MIT-Lizenz.
- Die acht Designs ab 0.6.1 stehen als Paletten in `tools/designs_erzeugen.py`; das Skript schreibt die
  CSS-Abschnitte in die vier Dateien und prüft jede Farbpaarung auf Kontrast (WCAG AA, 4,5 : 1). Neues Design:
  Palette dort eintragen, in `portal/models.py` (`DESIGNS`, `DESIGN_GRUPPEN`) ergänzen, Skript ausführen.
  `python tools/designs_erzeugen.py pruefen` läuft in der automatischen Prüfung mit. Nord steht unter MIT-Lizenz.

## Automatische Prüfungen auf GitHub (ab 0.4.9.3)

Bei jedem Push auf `main`, bei Pull Requests, wöchentlich (montags) und auf Knopfdruck („Actions“ → „Prüfung“ → „Run workflow“) läuft `.github/workflows/pruefung.yml` mit vier Aufträgen:

| Auftrag | Inhalt |
|---|---|
| Code-Qualität | `ruff` (Syntax- und Namensfehler, Konfiguration `ruff.toml`), `manage.py check`, `makemigrations --check` (vergessene Migrationen), vollständige Übersetzungen, `shellcheck` für alle Skripte |
| Tests | gesamte Testsuite gegen PostgreSQL 16 (parallel) |
| Sicherheit | `pip-audit` (bekannte Schwachstellen in Abhängigkeiten), `bandit` (mittlere und hohe Schwere) |
| Oberfläche | baut den Docker-Container, startet ihn mit Demodaten, meldet sich mit sechs Rollen an und prüft bis zu 40 Seitentypen je Rolle am Telefon (390 px) und am Desktop: kein Serverfehler, kein JavaScript-Fehler, kein seitliches Überlaufen. Die Bildschirmfotos stehen danach unter „Artifacts“ des Laufs (14 Tage) |

Es sind keine Geheimnisse hinterlegt; verwendet werden nur erfundene Demodaten und bei jedem Lauf neu erzeugte Wegwerf-Schlüssel. `.github/dependabot.yml` meldet wöchentlich veraltete Python-Pakete und monatlich Aktionen und Basis-Images als Pull Request.

Die Oberflächenprüfung lässt sich auch lokal ausführen (Playwright für Python nötig): `python tools/oberflaeche_pruefen.py http://localhost:8000 ausgabeordner`. Rückgabewert 1 bei Befunden.

Hinweis: Private Repositories haben ein monatliches Kontingent an Actions-Minuten (je nach Tarif; der genaue Wert sollte auf GitHub unter „Settings → Billing“ nachgesehen werden). Ein vollständiger Lauf dauert etwa 10–15 Minuten.

## Maschinenlesbare Spezifikation

`docs/schulnexus-spezifikation.json` beschreibt das gesamte Projekt so, dass eine KI es nachbauen kann: Zweck,
Technik und Leitlinien, je Modul die fachlichen Regeln, alle Modelle mit Feldern, Beziehungen, Auswahlwerten und
Verwaltungsoberfläche, alle Python-Module mit Klassen, Funktionen und Docstrings, URLs mit Ansichten, Rollen und
Standardrechte, Umgebungsvariablen, Verwaltungsbefehle, Templates, CSS/JS, Tests (Fälle als Akzeptanzkriterien),
Docker- und Server-Betrieb sowie eine Bau-Reihenfolge. Sie enthält nur die Programmstruktur, keine Daten.

Neu erzeugen nach Änderungen am Code (die fachlichen Abschnitte stehen in `FACHLICH` im Skript):

```sh
# mit dem Image des Web-Containers (im Projektordner):
docker run --rm -v "$PWD":/x -w /x --entrypoint python -e SECRET_KEY=x -e DATABASE_URL=postgres://x:x@localhost/x \
  schulnexus-web tools/spezifikation_erzeugen.py > docs/schulnexus-spezifikation.json
# oder mit lokal installierten Abhängigkeiten aus requirements.txt:
SECRET_KEY=x DATABASE_URL=postgres://x:x@localhost/x python tools/spezifikation_erzeugen.py > docs/schulnexus-spezifikation.json
```

Eine Datenbank ist dafür nicht nötig.

## Fehlzeiten nach Klasse (ab 0.7.1)

**Schüler:innen › Fehlzeiten** ist jetzt eine eigene Arbeitsseite statt der allgemeinen Liste:

1. **Klasse antippen** – Kacheln nach Jahrgang, mit Klassenleitung und Zahl der offenen Entschuldigungen; oben das Datum
   (Standard heute). Sekretariat, Verwaltungsleitung, Schulleitung und IT sehen alle Klassen, die Stufenkoordination die
   Klassen ihrer Jahrgänge, Lehrkräfte die Klassen, die sie leiten oder als ganze Klasse unterrichten.
2. **Eintragen:** alle Schüler:innen alphabetisch; je Zeile „ganztägig“ (optional bis Datum), „Stunden“ (von/bis nach
   Zeitraster) oder „Verspätung“ (Minuten) antippen, Status und Grund ergänzen, „Gemeldet durch“ wählen und alle Zeilen
   zusammen speichern. Was am Tag schon eingetragen ist, steht in der Zeile. Namensfilter, „nur mit Eintrag“, ‹ › für
   den vorigen bzw. nächsten Schultag, Klassenwechsel oben rechts. Unvollständige Zeilen verhindern das Speichern.
3. **Offene Entschuldigungen** der Klasse ankreuzen und als entschuldigt bzw. unentschuldigt markieren; über alle
   Klassen unter „Offene Entschuldigungen“ (nach Klasse und Name geordnet).
4. **Übersicht des Halbjahres** je Schüler:in (Fehltage, Fehlstunden, davon unentschuldigt, Verspätungen, Minuten,
   offen), per Klick auf den Spaltenkopf sortierbar; aufklappbar alle Einträge des Halbjahres mit Bearbeiten und Löschen.

Die Klassenliste hat einen Knopf „Fehlzeiten“. Die bisherige Liste der Verwaltungsoberfläche und das Einzelformular
bleiben als „Alle Fehlzeiten (Liste)“ und „Fehlzeit erfassen“ erreichbar. Die automatische Elternbenachrichtigung greift
auch beim Eintragen über die Klassenseite. Code: `fehlzeiten/ansichten.py`, `templates/fehlzeiten/`,
`static/fehlzeiten.js`; Tests in `fehlzeiten/tests.py`.

## Hilfe und Dokumentation in der Anwendung (ab 0.7.0)

- **Hilfe-Knopf auf jeder Seite:** Am rechten Rand steht überall der Knopf **Hilfe** (Portal und Verwaltungsoberfläche).
  Er öffnet von rechts eine Einblendung mit der Erklärung **zur gerade geöffneten Seite** – zum Beispiel auf
  „Schuljahre“ die Anleitung zum Schuljahreswechsel, in der Fehlzeitenliste die Anleitung zu Fehlzeiten, sonst das
  Menü der aktiven Registerkarte. „Alle Themen“ zeigt die Übersicht, das Suchfeld durchsucht den gesamten Hilfetext;
  Verweise zwischen Themen öffnen in der Einblendung, „Ganze Seite“ öffnet das Thema unter `/hilfe/`. Esc schließt.
- **Inhalt (29 Themen):** *Grundlagen* (Bedienung, Rollen), *Menüs erklärt* – jede Registerkarte mit jeder Gruppe und
  jedem Befehl – und *Anleitungen* für typische Aufgaben: Schuljahreswechsel einleiten, Neuaufnahme, Klassen bilden und
  Unterricht festlegen, Noten eintragen, Excel-Notentabelle, Zeugnisse, Zeugniskonferenz, Notensperre, Fehlzeiten,
  Elternnachrichten, Förderung, Abgang/Archiv/Löschfristen, Konten und Rollen, Sicherung, Sprechtag, Zwei-Faktor,
  Leistungsvorgaben und Notenregeln, Schülerakte.
- **Hilfe** steht auch im Menüband (Start › Übersicht) und in der Befehlssuche (Strg+K).
- **Version und Datum** stehen unten auf jeder Seite („Version 0.7.0 · Stand 11.11.2026“); das Datum steht in
  `src/config/version.py` (`VERSION_DATUM`) und wird mit jeder Version angepasst.
- **Texte pflegen:** Die Hilfetexte liegen als einfache Textdateien in `src/portal/hilfetexte/*.md` (Kopf mit Titel,
  Art, Kurzbeschreibung, Seiten, Stichworten; Auszeichnung siehe `src/portal/hilfe.py`). HTML in den Dateien wird nie
  ausgeführt. Ein Test prüft, dass jede Karte des Menübands ein Hilfethema hat, das alle Gruppen und Befehle nennt, und
  dass alle Verweise zwischen Themen gültig sind – wer einen Befehl hinzufügt, muss ihn also auch erklären.
- Die Hilfetexte sind derzeit nur auf Deutsch; in der englischen Oberfläche weist die Einblendung darauf hin.

## Mehr Designs und stabiler Importtest (0.6.1)

- **Acht weitere Designs** (Schulnexus Hell und Dunkel, Ozean, Sepia, Hoher Kontrast, Nord, Catppuccin Frappé und
  Macchiato) – siehe „Design: elf Farbschemata“. Die Migration `portal/0010` ändert nur die Auswahlliste.
- **Excel-Notentabelle:** Der Import arbeitete richtig; der Test „erneutes Hochladen ändert nichts“ wählte seinen
  Kurs aber ohne feste Reihenfolge und erwischte im Gesamtlauf einen Demo-Kurs ohne Noten (dort meldet der Import zu
  Recht „stehen keine Noten“). Der Test nimmt jetzt eindeutig den ersten Kurs mit Noten.

## Einfachere Bedienung, Rechteverwaltung und Klassenfilter (ab 0.6.0)

Es wurde keine Funktion entfernt; Befehle wurden nur neu geordnet und ergänzt. Die Rechte der Rollen sind unverändert.

**Befehlssuche und Favoriten**

- **Strg+K** (Mac: ⌘+K) oder der Knopf **Befehle** in der Titelleiste öffnet eine Suche über alle Befehle des Menübands,
  die das eigene Konto nutzen darf: tippen („Fehlzeit“, „Zeugnis“, „Rollen“), mit ↑/↓ wählen, Enter öffnet. Ohne
  Eingabe stehen Favoriten, zuletzt verwendete und alle Befehle in der Liste. Ab zwei Zeichen lässt sich mit derselben
  Eingabe auch eine Person suchen.
- Der **Stern** neben einem Befehl merkt ihn als Favorit. Favoriten stehen als Leiste unter dem Menüband – auf jeder
  Seite einen Klick entfernt. Favoriten und „zuletzt verwendet“ merkt sich der Browser, nicht der Server.

**Menüband neu geordnet**

- *Schüler:innen:* Meine Klassen · Stufenkoordination · Schülerakten · Klassen und Gruppen · Fehlzeiten · Eltern ·
  Neuanmeldung (das Alltägliche steht vorn).
- *Unterricht:* „Bewertung“ ist geteilt in **Noten** (Noten nach Klasse, Leistungsvorgaben) und **Listen**
  (Leistungsnachweise, Neuer Leistungsnachweis, Bewertungsordner, Einzelnoten); „Zeugnis“ in **Zeugnis** (Zeugnisse,
  Notenliste, Notensperre) und **Konferenz und Vorlagen** (Konferenzen, Textbausteine, Unterzeichnung).
- *System:* **Konten und Rechte** ist der eine Einstieg für die IT (bisher „Einzelrechte“); Benutzerkonten, Rollen und
  die Übersicht „Rollen und Rechte“ bleiben daneben erreichbar.

**Rechteverwaltung (System › Konten und Rechte, nur IT)**

- **Filter:** Suche (Name, Benutzername, E-Mail), Rolle, Status (aktiv/gesperrt) und Merkmal (mit Einzelrechten, ohne
  Rolle, Vollzugriff, Zwei-Faktor eingerichtet/nicht eingerichtet/Pflicht offen, noch nie angemeldet).
- **Sammelaktionen:** Konten ankreuzen – einzeln, mit Umschalt+Klick als Bereich oder mit „alle angezeigten Konten
  auswählen“ – und für alle zugleich eine Rolle hinzufügen oder entziehen, Konten sperren oder entsperren, die
  Zwei-Faktor-Anmeldung verpflichtend oder freiwillig machen. Andere Rollen der Konten bleiben erhalten. Es gelten
  dieselben Schutzregeln wie beim einzelnen Konto (eigenes Konto nicht sperren, eigene IT-Rolle nicht entziehen, ein
  Konto mit Vollzugriff muss bleiben); betroffene Konten werden übersprungen und genannt. Alles steht im Protokoll.
- **Einzelrechte je Konto:** Suchfeld über alle Rechte („Fehlzeiten“), „nur Abweichungen von der Rolle“, alle Bereiche
  auf- und zuklappen.
- **Rollen und Rechte:** Die Zahl der Konten je Rolle führt direkt zur gefilterten Kontenliste.

**Klassen statt der ganzen Schule auswählen**

- Listen mit Einträgen zu Schüler:innen (Fehlzeiten, Kontakte und Sorgeberechtigte, Einwilligungen, Gesundheitsangaben,
  AG-Wünsche und -Zuteilungen, Förderpläne, Nachteilsausgleiche, Verlaufsdokumentation, Einzelnoten, Zeugnisnoten)
  haben die Filter **Klasse (aktuell)** und **Jahrgang (aktuell)**; die Schülerliste zusätzlich den Jahrgang. Nach
  dem Filtern wählt das Ankreuzfeld im Tabellenkopf die ganze Klasse für eine Sammelaktion aus.
- In allen **Auswahlfeldern für Schüler:innen** (z. B. Fehlzeit erfassen, Förderplan, AG-Zuteilung) und in der Suche
  der Schülerliste zeigt der Klassenname die Klasse: „9a“ listet die 9a, „9a mei“ sucht darin weiter.

Technisch: `static/befehle.js`, `static/rechte.js`, `stammdaten/filter.py`, `sicherung/konten.py` (`sammelaktion`),
`sicherung/ansichten.py`, `portal/navigation.py`; Tests in `sicherung/tests_060.py`. Keine neuen Abhängigkeiten, keine
Migrationen.

## Noteneingabe mit Statistik, Filter, Tastenkürzeln und Entwurf (ab 0.5.0)

Die Seite **Noten eintragen** (Schnelleingabe je Leistungsnachweis) ist komfortabler geworden. An Rechten, Berechnung
und Speicherung ändert sich nichts.

- **Statistik beim Tippen:** Neben der Tabelle stehen Durchschnitt, Verteilung der Noten als Balken sowie die Zahl der
  Einträge „entschuldigt“, „unentschuldigt“, „befreit“, „nicht bewertbar“ und „ohne Eintrag“. Bei Bewertung über BE
  zählt die Note, die sich aus dem Notenschlüssel ergibt. Die Statistik dient der Orientierung und wird nicht gespeichert.
- **Filter:** „Name suchen …“ blendet die übrigen Zeilen aus (Umlaute und Akzente werden großzügig verglichen);
  „nur ohne Note“ zeigt die noch fehlenden Einträge. Enter und die Pfeiltasten springen nur durch sichtbare Zeilen,
  auch das Einfügen einer Excel-Spalte füllt nur sichtbare Zeilen. Ausgeblendete Zeilen werden trotzdem gespeichert.
- **Tastenkürzel:** Strg+S (Mac: ⌘+S) speichert, Strg+Enter speichert und legt den nächsten Leistungsnachweis an,
  Esc leert den Filter, F1 zeigt die Übersicht aller Kürzel.
- **Entwurf:** Ungespeicherte Eingaben merkt sich der Browser im aktuellen Fenster (sessionStorage). Nach
  versehentlichem Neuladen, Zurück-Klick oder abgelaufener Anmeldung bietet die Seite „Wiederherstellen“ oder
  „Verwerfen“ an. Der Entwurf verlässt den Rechner nicht, gilt je Konto, Kurs und Leistungsnachweis, verschwindet
  nach dem Speichern und spätestens beim Schließen des Fensters; Entwürfe anderer Konten im selben Fenster werden
  entfernt.

Technisch: `static/noten.js`, `templates/noten/eingabe.html`, `noten/ansichten.py` (`entwurf_schluessel`), Tests in
`noten/tests_050.py`. Es kommen keine neuen Abhängigkeiten und keine Migrationen hinzu.

## Noten schnell eintragen (ab 0.4.17.0)

- **Vorlage über die Notenregel** (Schulleitung › Notenregeln): je Jahrgangsbereich und Fächern zwei vorgegebene Ordner,
  z. B. „Klassenarbeiten“ (bzw. „Klausuren“) und „Sonstige Mitarbeit“ mit festem Anteil. Neu: **Höchstzahl je Halbjahr**
  (Standard 2 Klassenarbeiten/Klausuren und 30 Noten sonstige Mitarbeit; leer = keine Grenze). Die Grenze gilt beim
  Anlegen, im Excel-Import, beim Kopieren der Struktur und beim Verschieben eines Leistungsnachweises.
- **Noten nach Klasse › Fach:** Über der Tabelle legen „+ Klassenarbeit (1/2)“ und „+ SoMi-Note (5/30)“ sofort eine neue
  Spalte mit heutigem Datum an (vorher werden die Eingaben gespeichert); der Cursor steht danach in der neuen Spalte.
  Das **Gewicht jeder Spalte** steht im Tabellenkopf und lässt sich direkt ändern (z. B. 0,5 für eine kurze
  Mitarbeitsphase). Titel, Datum und Kommentare über den Spaltentitel.
- **Zeugnisnote:** In der letzten Spalte wählt die Lehrkraft eine Note – oder lässt „auto“ stehen (gerundete Note aus
  den Einzelnoten, rechnet bei jeder Änderung mit). Sie muss also nichts eintragen, kann aber.

## Neu in 0.4.16.0 (angelehnt an Ed-admin)

- **Noten nach Klasse als Kacheln:** Nach der Klassenwahl stehen alle Fächer der Klasse als Kacheln mit Fach- und
  Lehrkraftkürzel (z. B. „CH KRA“) über der Eingabetabelle; vorne die Kachel „Klasse“ für die Klassenübersicht. Grün
  hinterlegt = es gibt schon Leistungsnachweise; links die Fachfarbe. Die bisherige Liste steht aufklappbar darunter.
- **Textbausteine für Zeugniskommentare** (Verwaltung › Textbausteine; Schulleitung und Koordination pflegen sie): je
  Kategorie und optional je Jahrgangsbereich. Auf der Zeugnisseite fügt „Textbausteine einfügen“ den Text an der
  Schreibmarke ein; `{vorname}` wird durch den Rufnamen, `{sie_er}` durch „sie“/„er“ ersetzt.
  **Zeichengrenze:** `ZEUGNIS_KOMMENTAR_MAX` in der `.env` (0 = keine Grenze).
- **Bewertungsstruktur kopieren** (Seite „Bewertungsstruktur“ eines Kurses): von einem anderen Kurs übernehmen (gleiches
  Fach oder gleiche Lehrkraft, auch Vorhalbjahr und Vorjahr) oder auf andere Kurse übertragen (Parallelklassen, alle
  Fächer des Jahrgangs – als Schulleitung). Optional mit den Leistungsnachweisen ohne Noten. Ziele mit Leistungsnachweisen
  oder gesperrten Noten werden nicht überschrieben; Vorgaben der Klausurregel bleiben.
- **Notenschluss zu einem Datum** (Seite „Notensperre“): je Halbjahr und Jahrgangsbereich ein Termin; ab dem Folgetag
  sind die Noten automatisch gesperrt. „Zur Korrektur freigeben“ geht vor.
- **Fachbereiche** (Schulleitung › Fachbereiche) mit bis zu zwei Fachleitungen und Farbe; Fächer erhalten Fachbereich und
  eigene Farbe. Die **Fachleitung sieht alle Kurse der Fächer ihres Fachbereichs** (lesend, z. B. Notenübersicht).
- **Klassen-Details:** stellvertretende Klassenleitung (mit denselben Rechten wie die Klassenleitung), Klassenraum und
  Höchstzahl der Schüler:innen (Warnung beim Zuordnen).
- **Stundentafel** (Schulleitung › Stundentafel): Wochenstunden je Fach und Jahrgang. Neuer Unterricht übernimmt die
  Stunden; im Reiter „Fächer und Lehrkräfte“ stehen die Stunden je Fach und eine Übersicht der Lehrkräfte (in dieser
  Gruppe, gesamt im Halbjahr, Soll = Deputat minus Ermäßigung).
- **Unterzeichnung der Zeugnisse** (Verwaltung › Unterzeichnung): wer für welche Jahrgänge als Schulleitung unterschreibt
  (z. B. „Leiterin der Grundschule“). Funktion und Name stehen unter der Unterschriftslinie, ebenso der Name der
  Klassenleitung.

## Automatische Zeugnisnote und Notenliste (ab 0.4.15.0)

- **Zeugnisnote automatisch:** Solange niemand eine Zeugnisnote festsetzt, gilt die gerundete Note aus den Einzelnoten
  (wie in der Spalte „Vorschlag“). Sie folgt jeder Änderung der Einzelnoten, Gewichte und Ordner. Ohne Einzelnoten in dem
  Kurs gibt es keine automatische Note. Festgesetzte Noten (Excel-Spalte „Zeugnisnote (festgesetzt)“, Klassenübersicht,
  Seite „Zeugnisnoten“) haben Vorrang und bleiben stehen; „–“ stellt wieder auf automatisch. Gesperrte Noten und
  freigegebene Zeugnisse werden nicht verändert. Herkunft im Änderungsprotokoll: „automatisch aus den Einzelnoten“.
  Beim Start des Containers zieht `manage.py zeugnisnoten_automatisch` fehlende Noten für vorhandene Einzelnoten nach.
- **Notenliste** (Menüband › Unterricht › Notenliste, ersetzt „Zeugnisnoten (Liste)“): Schuljahr, Halbjahr und Klasse
  wählen – auch vergangene und gesperrte – und alle Zeugnisnoten wie in der Konferenz sehen: Kernfächer, 5/6 markiert,
  fehlende Noten (?), Schnitt und Gefährdung bzw. Versetzungsvorschlag. Nur lesend; mit Links zur Konferenz und zu den
  Zeugnissen der Klasse. Sichtbar für Verwaltung, Schulleitung, Klassenleitung (eigene Klasse) und Koordination (Stufe).
- **Freigegebene Zeugnisse (0.4.15.1):** Die Zeugnisnoten eines freigegebenen Zeugnisses bleiben gesperrt, auch wenn die
  Klasse unter „Notensperre“ zur Korrektur freigegeben ist – das gedruckte Zeugnis soll sich nicht nachträglich ändern.
  Neu: „Freigabe aufheben (n)“ auf der Seite „Zeugnisse“ der Klasse hebt die Freigabe für alle Zeugnisse der Klasse auf
  (Schulleitung, Stufenkoordination). Klassenübersicht, Notensperre-Seite und die Meldung beim Entsperren weisen auf
  freigegebene Zeugnisse hin; das Schloss nennt den Grund der Sperre.
- **Noten nach Klasse:** Ist ein Kurs geöffnet, stehen alle Fächer der Klasse als Schaltflächen unter Schritt 2 – ein
  Klick wechselt das Fach.

## Klassen und Gruppen: Fächer und Lehrkräfte (ab 0.4.14.0)

Die Seite **Menüband › Schüler:innen › Klassen und Gruppen** (vorher „Zuordnen“) deckt jetzt den ganzen Ablauf ab:
Klasse anlegen → Schüler:innen hinzufügen → Fächer wählen → Lehrkräfte zuweisen.

1. **Klasse anlegen:** links „Neue Klasse / Gruppe“ (Name, Typ, Jahrgang, Klassenleitung).
2. **Schüler:innen** (Reiter „Schüler:innen“): wie bisher aus der Liste rechts hinzufügen; „Abmelden“ beendet die
   Mitgliedschaft zum Stichtag (die Historie bleibt). Neu: **„Neue:n Schüler:in anlegen“** – Vorname, Nachname,
   Geschlecht, Geburtsdatum, Religion/Ethik; die Person erhält eine Schülernummer und ist sofort Mitglied der Gruppe.
   Gibt es schon eine gleichnamige Person, muss „Trotzdem anlegen“ angekreuzt werden. Alles Weitere in der Schülerakte.
3. **Fächer und Lehrkräfte** (Reiter): Tabelle mit allen Fächern und je einer Spalte pro Halbjahr. Wer eine Lehrkraft
   wählt, legt den Unterricht an; Lehrkräfte mit passender Lehrbefähigung stehen oben. Eine Wahl im 1. Halbjahr füllt das
   leere 2. Halbjahr gleich mit, „1. Halbjahr → 2. Halbjahr“ übernimmt alle auf einmal. „–“ entfernt einen Unterricht,
   solange es keine Noten gibt; sonst lässt sich nur die Lehrkraft wechseln. Notenskala und Startvorlage werden wie bei
   den anderen Klassen des Jahrgangs gesetzt (sonst Sek I bzw. für die Oberstufe Sek II). Geänderte Felder sind
   markiert; was inzwischen von anderer Seite geändert wurde, wird nicht überschrieben.
4. **Klasse bearbeiten:** „Klasse / Gruppe bearbeiten“ im Kopf (Name, Jahrgang, Klassenleitung, Kürzel, Vorjahresklasse).

**Rechte:** Sekretariat, Verwaltungsleitung, Schulleitung und IT-Administration für alle Klassen; Mittel- und
Oberstufenkoordination für die Jahrgänge ihrer Stufe. Sekretariat und Koordinationen erhalten dafür beim Start
(`grundeinrichtung`) die Rechte für Unterricht. Neue Schüler:innen anlegen dürfen nur Rollen mit dem Recht auf
Schülerstammdaten (Sekretariat, Verwaltungsleitung, Schulleitung, IT); die Koordinationen nehmen Schüler:innen über
Neuanmeldungen auf.

## Zeugnisnoten aus Excel und Klassenübersicht (ab 0.4.13.0)

Die **festgesetzte Zeugnisnote** lässt sich jetzt auf zwei weiteren Wegen setzen. Beide nutzen dieselben Regeln wie die
Seite „Zeugnisnoten“ (Lehrkraft des Unterrichts und Schulleitung; gesperrte Schüler:innen und freigegebene Zeugnisse
bleiben unverändert; ohne Einzelnoten nur mit der Freigabe „Zeugnisnote ohne Einzelnoten“; eine Abweichung vom Vorschlag
wird nur markiert). Die Note gilt sofort für das Zeugnis.

- **Excel-Import:** Die Spalte **„Zeugnisnote (festgesetzt)“** wird beim Hochladen mit übernommen – im 1. Halbjahr aus
  dem Blatt „1. Halbjahr“, im 2. Halbjahr aus dem Blatt „2. Halbjahr“, bei einem Kurs mit Jahresnote aus dem Blatt
  „Jahresnote“. Erlaubt sind ganze Noten 1–6 sowie nb und befreit. Die Vorschau zeigt je Schüler:in bisher/neu; leere
  Zellen ändern nichts. Ungültige Eingaben blockieren die Übernahme, nicht übernehmbare Zeilen (gesperrt, ohne
  Einzelnoten) werden gemeldet und ausgelassen.
- **Klassenübersicht:** Wo man die Zeugnisnote festsetzen darf, steht in der Zelle **ZN** eine Auswahl (für alle Fächer der
  Klasse). „Zeugnisnoten speichern“ übernimmt nur geänderte Zellen; eine inzwischen von anderer Seite geänderte Zelle wird
  nicht überschrieben. „–“ entfernt die Zeugnisnote wieder.
- **Hinweis in den Einzelnoten:** In der Notentabelle eines Kurses erscheint die Spalte **Zeugnisnote**; darunter steht,
  woher sie stammt („aus der Excel-Notentabelle übernommen“ bzw. „in der Klassenübersicht festgesetzt“). Wird die Note
  auf der Seite „Zeugnisnoten“ geändert, entfällt der Hinweis. Die Herkunft steht auch im Änderungsprotokoll.

## Noten nach Klasse (ab 0.4.12.0)

Menüband „Unterricht“ → **Noten nach Klasse** (`/noten/`):

1. **Halbjahr** wählen (Voreinstellung: das laufende) und die **Klasse** antippen. Angeboten werden die Klassen, in denen
   man Unterricht sehen darf.
2. **Kurse bzw. Lerngruppen** der Klasse mit Fach, Gruppe und **zugewiesener Lehrkraft**. Lerngruppen und Kurse
   (z. B. Religion/Ethik, zweite Fremdsprache) erscheinen bei jeder Klasse, aus der sie Schüler:innen haben.
   Darunter die **Klassenübersicht** – gedacht für die Klassenleitung: je Schüler:in eine Zeile, je Fach eine Spalte mit
   dem aktuellen Stand (Tendenz, darunter der Schnitt, „ZN“ = festgesetzte Zeugnisnote), gefährdete Fächer rot und
   gezählt. Ein Klick auf das Fach öffnet den Kurs.
3. **Kurs geöffnet:** die Notentabelle wie in der Excel-Tabelle – Schüler:innen untereinander, Leistungsnachweise
   nebeneinander (nach Ordnern gruppiert), rechts Ø je Bereich, Halbjahres- bzw. Jahresschnitt, Tendenz und Note.
   Wer Noten eintragen darf, bearbeitet die Zellen direkt (2+, 2, 2-, e, u, b, nb; leeren = Note entfernen; Enter und
   Pfeiltasten springen zeilenweise; geänderte Zellen sind markiert) und speichert alles auf einmal. Ungültige Eingaben
   verhindern das Speichern; eine inzwischen von anderer Seite geänderte Zelle wird nicht überschrieben (Hinweis).
   Leistungsnachweise mit Notenschlüssel (BE) und gesperrte Schüler:innen sind nur lesbar. Von hier aus: neuer
   Leistungsnachweis, Bewertungsstruktur, ausführliche Notenübersicht, **Excel-Tabelle herunterladen und hochladen**
   (nach der Vorschau führt die Übernahme hierher zurück).

## Excel-Notentabelle: herunterladen, offline ausfüllen, hochladen (ab 0.4.11.0)

In der **Notenübersicht** eines Unterrichts (Sek I, Noten 1–6) führt „Excel-Notentabelle“ zu einer eigenen Seite:

1. **Vorlage herunterladen:** Die Datei enthält die Schüler:innen des Kurses, die vorhandenen Leistungsnachweise mit
   Noten (Klassenarbeiten aus dem schriftlichen, SoMi aus dem Ordner „Sonstige Mitarbeit“, jeweils samt Unterordnern),
   Bereichsgewichte, den Anteil des 1. Halbjahres und die Rundungsregel der Skala. Im 2. Halbjahr ist auch das Blatt des
   1. Halbjahres aus dem zugehörigen Kurs gefüllt. Die Tabelle rechnet ohne Schulnexus (Excel, Numbers, LibreOffice;
   nur Grundfunktionen), hat ein Blatt „Master“ für alle Gewichte und ein Blatt „Erklärung“ mit Rechenbeispiel.
2. **Hochladen:** Voraussetzung ist, dass die **Klasse** im Blatt „Master“ zur Gruppe des Unterrichts passt
   (Groß-/Kleinschreibung und Leerzeichen egal) und **Nachname und Vorname** (oder Rufname) mit den Schüler:innen
   übereinstimmen. Übernommen wird das Blatt des passenden Halbjahres.
3. **Vorschau:** Schulnexus zeigt je Spalte, ob ein Leistungsnachweis neu angelegt oder aktualisiert wird (gleicher Titel
   im Zielordner), wie viele Noten neu, geändert oder unverändert sind, welche Namen nicht zugeordnet werden konnten und
   welche Schüler:innen gesperrt sind. Zielordner lassen sich wählen oder neu anlegen; die Bereichsgewichte (und im
   2. Halbjahr der Anteil des 1. Halbjahres) können optional aus der Datei übernommen werden.
4. **Übernehmen:** erst nach Bestätigung. Ungültige Noten, ein falsches Datum oder eine falsche Klasse verhindern die
   Übernahme vollständig. Leere Zellen löschen keine vorhandenen Noten; Kommentare und Einzelgewichte bleiben erhalten.
   Leistungsnachweise mit Notenschlüssel (Bewertungseinheiten) werden nicht überschrieben. Download und Übernahme stehen
   im Protokoll.

Erlaubte Eingaben: 1+ … 6, Dezimalnoten mit passender Stufe (2,3 = 2-), e, b, nb, u. Code: `noten/notentabelle.py`
(Erzeugung), `noten/notenimport.py` (Lesen, Prüfen, Übernehmen), `noten/importseite.py` (Seite).

## Suchauswahl statt Hin-und-her-Listen (ab 0.4.10.0)

Alle Mehrfachauswahlen der Verwaltungsoberfläche (Anwesende einer Konferenz, Beteiligte eines Förderplans, Fächer,
Förderschwerpunkte, Maßnahmen, Lehrbefähigungen, gebildet aus Klassen, Pflichtnachweise) nutzen statt der zwei Listen
zum Hin- und Herschieben eine **Suchauswahl**: tippen, Tab oder Enter übernimmt, × entfernt, „Liste öffnen“ zeigt alle
Einträge im Overlay zum Anklicken. Wo es sinnvoll ist, stehen **Vorschläge** oben (Konferenz: Lehrkräfte der Klasse;
Förderplan: die im laufenden Halbjahr unterrichtenden Lehrkräfte) und lassen sich gesammelt übernehmen. Ohne
JavaScript bleibt die gewöhnliche Mehrfachauswahl nutzbar. Baustein: `portal/suchauswahl.py`, `static/suchauswahl.js`.

Geprüft wurde dabei auch, wo Schüler:innen aus der ganzen Schule angeboten werden, obwohl der Zusammenhang eine Klasse
oder einen Kurs vorgibt. Gefunden und eingeschränkt: Konferenzbeschlüsse in der Verwaltungsoberfläche (jetzt nur die
Klasse, zuzüglich bereits erfasster Beschlüsse). Bereits eingeschränkt waren: Konferenzseite, Zeugnisnoten,
Notenzeilen eines Leistungsnachweises (werden je Kursmitglied angelegt), Sprechtag-Buchungen (nur unterrichtete bzw.
geleitete Schüler:innen), Förderpläne für Klassenleitungen (nur die eigene Klasse). Bewusst schulweit bleiben die
Zuordnung zu Klassen und Gruppen, neue Förderpläne der Förderkoordination und Fehlzeiten in der Verwaltungsoberfläche
(dort mit Suchfeld statt Liste).

## Code-Prüfung 0.4.9.2

Systematische Prüfung des gesamten Codes: statische Analyse (ruff, bandit), Abhängigkeiten (pip-audit: keine bekannten
Lücken), Shell-Skripte (shellcheck), `manage.py check --deploy`, alle 92 Vorlagen übersetzt, Migrationsstand, Testabdeckung
(89 %) sowie ein automatischer Aufruf aller verlinkten Seiten für jede der 13 Demo-Rollen (je Seitentyp bis zu drei Varianten, rund 4 700 Aufrufe). Behoben:

- Zeugnisseite stürzte ab, wenn das freigebende Konto gelöscht war; Personensuche bei Personal ohne Bereich.
- Zahlenfelder (Gewichte, BE, Anteil des 1. Halbjahres) nehmen „NaN“, „Infinity“ und zu große Werte nicht mehr an
  (vorher Serverfehler).
- Anmeldesperre nach zu vielen Fehlversuchen (siehe „Sicherheit und Verschlüsselung“).
- Links nur noch dort, wo die Zielseite für die angemeldete Person auch geöffnet werden darf (Klassenliste,
  Schülerakte, Zeugnis, Konferenz, Förderplan, Nachteilsausgleich, Laufbahn, Verwaltungsliste der Schüler:innen).
- Klassenliste lädt die Fehlzeiten in einer Abfrage statt einer je Schüler:in.
- Wiederherstellung einer Modulsicherung: auch Daten- und Formatfehler (nicht nur Konflikte) brechen sauber mit Meldung ab;
  wie bisher wird nichts verändert und vorher automatisch gesichert.

Bewusst so belassen: Das Öffnen der Zeugnisseiten legt fehlende Zeugnis-Entwürfe an und gleicht Klasse und Jahrgang ab
(gewollt, damit jede Schülerin und jeder Schüler einen Eintrag hat); die Seite „Sicherheit“ legt beim ersten Aufruf den
leeren Zwei-Faktor-Eintrag an. In der Verwaltungsoberfläche zeigt Django bei Verweisfeldern teils Links zu Einträgen,
die die Person nicht öffnen darf (Ergebnis: „Zugriff verweigert“, keine Datenpreisgabe).

## Update von einer älteren Version

**Umbenennung in Schulnexus (ab 0.4.9.1; 0.4.9.0 hieß kurz „edunex“):** Die Docker-Projekte heißen jetzt fest `schulnexus` (Container
`schulnexus-web-1` usw., Datenträger `schulnexus_datenbank` …), die Vorgaben für Datenbankname und Unraid-Ablageort
lauten `schulnexus` bzw. `/mnt/user/appdata/schulnexus-daten`. Eine bereits laufende Installation unter dem alten
Namen behält ihre `.env` (dort stehen `DB_NAME` und `APPDATA` weiterhin auf dem alten Wert); vor dem
ersten Start der neuen Version die alten Container mit `docker compose -p schulverwaltung down`
(ohne `-v`) stoppen und in der `.env` `COMPOSE_PROJECT_NAME=schulverwaltung` ergänzen, damit die
vorhandenen Datenträger weiterverwendet werden. Modulsicherungen älterer Versionen lassen sich weiterhin
einlesen; verschlüsselte Dateien bleiben lesbar.

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
| `vps/` | Betrieb auf einem VPS hinter Traefik: `traefik.yml` (Ergänzung zur `docker-compose.yml`), `einrichten.sh` |
| `docker/` | Startskript des Containers, Sicherungsskript |
| `src/config/version.py` | Versionsnummer (kleine Änderungen erhöhen die letzte Stelle) |

Alle Änderungen an Personen, Noten, Fehlzeiten und Mitgliedschaften werden
protokolliert (Schaltfläche „Geschichte“ in der Verwaltungsoberfläche).

Lizenz: vorgesehen AGPL-3.0 (noch zu bestätigen).
