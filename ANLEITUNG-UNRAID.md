# edunex auf Unraid (Zugriff über Tailscale)

edunex läuft auf Unraid als Gruppe von drei Docker-Containern:

- **web:** die Anwendung
- **db:** die Datenbank
- **sicherung:** die tägliche Datenbanksicherung

Ein kurzlebiger Hilfscontainer **vorbereitung** setzt beim Start nur die Ordnerrechte.

Nach außen geöffnet ist genau ein Port, voreingestellt **8010**. Über das Tailscale, das bereits auf dem
Unraid-Server läuft, erreichen alle Geräte deines Tailnets diesen Port. Die Datenbank hat keinen Port und
keinen Internetzugang.

> Nur mit **erfundenen Testdaten** betreiben. Vor echten Schülerdaten: HTTPS (unten), verschlüsselte
> Festplatten, sicher hinterlegter Datenschlüssel, Zwei-Faktor-Anmeldung für Leitung und IT, Datenschutzfreigabe.

## Voraussetzungen

1. **Docker** ist in Unraid aktiviert (*Settings › Docker*).
2. Das Plugin **„Docker Compose Manager“** ist installiert (*Apps*, danach suchen). Es bringt den
   Befehl `docker compose` mit.
3. **Tailscale** läuft auf dem Unraid-Server, und das Gerät, mit dem du zugreifen willst, ist im selben
   Tailnet angemeldet.

## Installation

1. ZIP auf dem Mac entpacken. Den Ordner `edunex` (das Programm) auf eine Unraid-Freigabe
   kopieren, z. B. in die Freigabe `appdata`. Er liegt dann unter `/mnt/user/appdata/edunex`.
   Ist `appdata` im Finder nicht sichtbar, in Unraid unter *Shares › appdata › SMB Security Settings*
   den Export einschalten oder eine andere Freigabe verwenden (Pfade unten entsprechend anpassen).
2. In Unraid oben rechts das **Terminal** öffnen (Symbol `>_`) und eingeben:

   ```sh
   cd /mnt/user/appdata/edunex
   sh unraid/einrichten.sh
   ```

3. Das Skript stellt beim ersten Start drei Fragen:
   - **Ablageort der Daten:** Eingabetaste übernimmt `/mnt/user/appdata/edunex-daten`.
     Programm und Daten liegen so getrennt.
   - **Port:** Eingabetaste übernimmt `8010`.
   - **Nur über Tailscale erreichbar?** Mit `j` ist der Port nur im Tailnet offen, mit Eingabetaste
     zusätzlich im Heimnetz. Siehe dazu die Hinweise unten.

   Danach baut es die Anwendung. Beim ersten Mal dauert das einige Minuten.
4. Am Ende zeigt das Skript die Adresse und die Zugangsdaten an, z. B.:

   ```
   http://tower.tail1234.ts.net:8010
   http://100.101.102.103:8010
   ```

   Die Zugangsdaten stehen außerdem in `unraid/.env`. Mit `ADMIN_BENUTZER` und `ADMIN_PASSWORT`
   meldest du dich als Administrator an. Die Demo-Konten verwenden `DEMO_PASSWORT`.

Die Container erscheinen danach im Unraid-Reiter *Docker* (Namen beginnen mit `edunex-`)
und starten nach einem Neustart des Servers automatisch.

## Aktualisieren

Den neuen Ordnerinhalt über den alten kopieren. Die Datei `unraid/.env` dabei **behalten**. Dann erneut:

```sh
cd /mnt/user/appdata/edunex
sh unraid/einrichten.sh
```

## Wo liegen die Daten?

Unter dem Ablageort, voreingestellt `/mnt/user/appdata/edunex-daten`:

| Ordner | Inhalt |
| --- | --- |
| `datenbank/` | PostgreSQL-Datenbank |
| `dokumente/` | hochgeladene Anhänge und Bewerbungsunterlagen (verschlüsselt, ab 0.4.6.0) |
| `modulsicherungen/` | Modulsicherungen und PDF-Exporte aus dem Portal (verschlüsselt, ab 0.4.6.0) |
| `sicherungen/` | tägliche Datenbanksicherungen (`*.dump`, 14 Tage aufbewahrt) |

Das Plugin **„Appdata Backup“** kann diese Ordner zusätzlich mitsichern.

## Wichtige Befehle

Alle Befehle im Ordner `unraid` des Projekts ausführen (`cd /mnt/user/appdata/edunex/unraid`):

| Zweck | Befehl |
| --- | --- |
| Status | `docker compose ps` |
| Protokoll | `docker compose logs -f web` |
| Stoppen | `docker compose down` (Daten bleiben erhalten) |
| Starten | `docker compose up -d` |
| Sicherung zurückspielen | siehe unten |

**Sicherung zurückspielen.** Damit wird der aktuelle Stand überschrieben. Den Dateinamen anpassen:

```sh
docker compose stop web sicherung
docker compose exec -T db pg_restore --clean --if-exists --no-owner -U schule -d edunex \
  < /mnt/user/appdata/edunex-daten/sicherungen/edunex-2026-10-13_0200.dump
docker compose start web sicherung
```

## Hinweise

- **Port belegt?** 8000 nutzt z. B. Paperless-ngx. Deshalb ist 8010 voreingestellt. Einen anderen Port
  trägst du in `unraid/.env` bei `PORT` ein und startest das Skript erneut.
- **Nur Tailscale oder auch Heimnetz?**
  - Mit `BIND_ADRESSE=0.0.0.0` ist die Seite auch im Heimnetz unter `http://<IP des Servers>:8010` erreichbar.
  - Mit der Tailscale-IP des Servers (`100.x.y.z`) ist sie nur im Tailnet erreichbar.
  - Bei dieser engeren Variante muss Tailscale beim Start von Docker bereits verbunden sein. Ist die Seite
    nach einem Neustart des Servers nicht erreichbar, hilft `docker compose up -d` im Ordner `unraid`.
- **Verbindung:** Mit `http://` ist der Weg durchs Tailnet trotzdem durch Tailscale (WireGuard) verschlüsselt.
  Im Heimnetz (`BIND_ADRESSE=0.0.0.0`) läuft der Verkehr dagegen unverschlüsselt. Für echte Daten HTTPS einrichten
  (Abschnitt unten).
- **Zugriff im Tailnet einschränken:** Wer im Tailnet ist, erreicht den Port. Mit den Zugriffsregeln
  (*Access Controls*) in der Tailscale-Verwaltung lässt sich der Zugriff auf einzelne Geräte oder Personen
  begrenzen.
- **Elternnachrichten (ab 0.4.2.9):** Eltern sind nicht im Tailnet und können persönliche Links über eine
  Tailscale-Adresse nicht öffnen. Solange `ELTERN_EMAIL_VERSAND=0` bleibt, wird nichts verschickt (Postausgang).
  Für den echten Versand braucht es eine **öffentliche HTTPS-Adresse** (`ELTERN_LINK_BASIS`), etwa über einen
  Reverse Proxy, der nach außen **nur** `/eltern/n/` und `/static/` freigibt – nicht die Anmeldung des Kollegiums.
  Das öffnet das System ins Internet: erst nach Zwei-Faktor-Anmeldung und Datenschutzfreigabe.
- **Modulsicherungen (ab 0.4.3.0):** Sicherungen und PDF-Exporte aus dem Portal liegen in
  `${APPDATA}/modulsicherungen`. Der Ordner wird beim Start angelegt. Für eine tägliche automatische Modulsicherung
  in Unraid unter *User Scripts* einen Zeitplan anlegen mit
  `docker compose -f /mnt/user/appdata/edunex/unraid/docker-compose.yml exec -T web python manage.py modulsicherung`
  (Pfad an den eigenen Installationsordner anpassen).

## HTTPS mit „tailscale serve“ (ab 0.4.6.0 empfohlen)

1. In der Tailscale-Verwaltung unter *DNS* **MagicDNS** und **HTTPS Certificates** einschalten.
2. Im Unraid-Terminal (Port an die eigene Einstellung anpassen):

   ```sh
   tailscale serve --bg --https=8443 http://127.0.0.1:8010
   ```

   Unsicherheit: Die Schreibweise der `serve`-Befehle hat sich zwischen Tailscale-Versionen geändert. Meldet der
   Befehl einen Fehler, hilft `tailscale serve --help`; gemeint ist „https auf Port 8443 an http://127.0.0.1:8010
   weiterreichen, im Hintergrund dauerhaft“.
3. In `unraid/.env` setzen (Name des Servers anpassen) und `sh unraid/einrichten.sh` erneut ausführen:

   ```
   HTTPS=1
   CSRF_TRUSTED_ORIGINS=https://tower.tail1234.ts.net:8443
   BIND_ADRESSE=127.0.0.1
   ```

   `BIND_ADRESSE=127.0.0.1` sorgt dafür, dass die Anwendung **nur noch über https** erreichbar ist: Der Port 8010
   ist dann weder im Heimnetz noch im Tailnet offen, nur `tailscale serve` auf demselben Server erreicht ihn.
4. Aufruf: `https://tower.tail1234.ts.net:8443`.

`HINTER_PROXY` und `HTTPS_UMLEITUNG` bleiben auf `0`. Unsicherheit: Ob `tailscale serve` den Kopf
`X-Forwarded-Proto` setzt, ist nicht sicher belegt; mit `HINTER_PROXY=1` und `HTTPS_UMLEITUNG=1` ohne diesen Kopf
entstünde eine Endlosweiterleitung. Mit `BIND_ADRESSE=127.0.0.1` ist die Umleitung ohnehin unnötig. Der HSTS-Kopf
wird ohne `HINTER_PROXY=1` nicht gesendet; das ist bei einer reinen Tailnet-Adresse ohne http-Zugang vertretbar.

## Verschlüsselung (ab 0.4.6.0)

Drei Ebenen ergänzen sich:

1. **Datenschlüssel der Anwendung (`DATEN_SCHLUESSEL` in `unraid/.env`).** `einrichten.sh` erzeugt ihn beim ersten
   Aufruf bzw. beim ersten Update auf 0.4.6.0 und zeigt ihn einmal an. Damit werden Anhänge, Bewerbungsunterlagen,
   Modulsicherungen und PDF-Exporte mit AES-256 verschlüsselt abgelegt; vorhandene Dateien werden beim Start
   nachverschlüsselt. **Den Schlüssel ausdrucken und getrennt vom Server aufbewahren** (z. B. Tresor der
   Schulleitung). Ohne ihn lassen sich diese Dateien – auch aus Sicherungen – nicht wiederherstellen. Den Schlüssel
   nie ändern, solange damit verschlüsselte Dateien existieren.
2. **Verschlüsselte Festplatten in Unraid (LUKS).** Schützt Datenbank, Dokumente und die täglichen
   Datenbanksicherungen (`*.dump`), falls Server oder Platten gestohlen oder ausgemustert werden. Unraid bietet die
   Dateisysteme „XFS – encrypted“ bzw. „BTRFS – encrypted“ je Platte und Pool an; das Passwort bzw. die Schlüsseldatei
   wird beim Starten des Arrays eingegeben. Wichtig:
   - Eine Platte wird nur durch **Neuformatieren** verschlüsselt. Vorher alle Daten auf andere Platten verschieben
     (z. B. mit dem Plugin „unBALANCE“), dann die leere Platte im gestoppten Array auf das verschlüsselte Dateisystem
     umstellen und formatieren, Platte für Platte.
   - Der **Cache-Pool** (dort liegt meist `appdata`) muss ebenfalls verschlüsselt werden.
   - Die Passphrase sicher hinterlegen; ohne sie ist das ganze Array verloren.
   - Ein laufender, entsperrter Server ist dadurch nicht geschützt – dafür sorgen Anmeldung, Zwei-Faktor und Tailscale.
   Unsicherheit: Die genauen Menüpunkte unterscheiden sich je nach Unraid-Version (*Main › Platte › File system type*);
   bitte in der Unraid-Dokumentation zur eigenen Version nachsehen.
3. **Verschlüsselte Downloads.** Sicherungen im Portal mit Passwort herunterladen (System › Sicherung ›
   Herunterladen); die Datei ist dann auch auf dem Mac oder einem USB-Stick geschützt.

## Zwei-Faktor-Anmeldung (ab 0.4.6.0)

Jede Person richtet sie selbst unter Kontomenü › **Sicherheit** ein (Authenticator-App, QR-Code, Ersatzcodes).
Die IT macht sie unter System › Benutzer und Rechte › Konto für einzelne Konten **verpflichtend** (empfohlen:
Schulleitung, Verwaltungsleitung, IT, HR) und setzt sie bei Verlust des Telefons zurück. Die Uhr des Unraid-Servers
muss stimmen (NTP ist in Unraid voreingestellt), sonst passen die Codes nicht.
