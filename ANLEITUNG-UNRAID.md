# Schulverwaltung auf Unraid (Zugriff über Tailscale)

Die Schulverwaltung läuft auf Unraid als Gruppe von drei Docker-Containern:

- **web:** die Anwendung
- **db:** die Datenbank
- **sicherung:** die tägliche Datenbanksicherung

Ein kurzlebiger Hilfscontainer **vorbereitung** setzt beim Start nur die Ordnerrechte.

Nach außen geöffnet ist genau ein Port, voreingestellt **8010**. Über das Tailscale, das bereits auf dem
Unraid-Server läuft, erreichen alle Geräte deines Tailnets diesen Port. Die Datenbank hat keinen Port und
keinen Internetzugang.

> Nur mit **erfundenen Testdaten** betreiben. Für echte Schülerdaten fehlen noch Zwei-Faktor-Anmeldung
> und die Freigabe durch den Datenschutz (Kenya Data Protection Act 2019).

## Voraussetzungen

1. **Docker** ist in Unraid aktiviert (*Settings › Docker*).
2. Das Plugin **„Docker Compose Manager“** ist installiert (*Apps*, danach suchen). Es bringt den
   Befehl `docker compose` mit.
3. **Tailscale** läuft auf dem Unraid-Server, und das Gerät, mit dem du zugreifen willst, ist im selben
   Tailnet angemeldet.

## Installation

1. ZIP auf dem Mac entpacken. Den Ordner `schulverwaltung` (das Programm) auf eine Unraid-Freigabe
   kopieren, z. B. in die Freigabe `appdata`. Er liegt dann unter `/mnt/user/appdata/schulverwaltung`.
   Ist `appdata` im Finder nicht sichtbar, in Unraid unter *Shares › appdata › SMB Security Settings*
   den Export einschalten oder eine andere Freigabe verwenden (Pfade unten entsprechend anpassen).
2. In Unraid oben rechts das **Terminal** öffnen (Symbol `>_`) und eingeben:

   ```sh
   cd /mnt/user/appdata/schulverwaltung
   sh unraid/einrichten.sh
   ```

3. Das Skript stellt beim ersten Start drei Fragen:
   - **Ablageort der Daten:** Eingabetaste übernimmt `/mnt/user/appdata/schulverwaltung-daten`.
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

Die Container erscheinen danach im Unraid-Reiter *Docker* (Namen beginnen mit `schulverwaltung-`)
und starten nach einem Neustart des Servers automatisch.

## Aktualisieren

Den neuen Ordnerinhalt über den alten kopieren. Die Datei `unraid/.env` dabei **behalten**. Dann erneut:

```sh
cd /mnt/user/appdata/schulverwaltung
sh unraid/einrichten.sh
```

## Wo liegen die Daten?

Unter dem Ablageort, voreingestellt `/mnt/user/appdata/schulverwaltung-daten`:

| Ordner | Inhalt |
| --- | --- |
| `datenbank/` | PostgreSQL-Datenbank |
| `dokumente/` | hochgeladene Anhänge und Bewerbungsunterlagen |
| `sicherungen/` | tägliche Datenbanksicherungen (`*.dump`, 14 Tage aufbewahrt) |

Das Plugin **„Appdata Backup“** kann diese Ordner zusätzlich mitsichern.

## Wichtige Befehle

Alle Befehle im Ordner `unraid` des Projekts ausführen (`cd /mnt/user/appdata/schulverwaltung/unraid`):

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
docker compose exec -T db pg_restore --clean --if-exists --no-owner -U schule -d schulverwaltung \
  < /mnt/user/appdata/schulverwaltung-daten/sicherungen/schulverwaltung-2026-10-13_0200.dump
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
- **Verschlüsselung:** Die Adresse beginnt mit `http://`. Der Weg durchs Tailnet ist trotzdem durch
  Tailscale (WireGuard) verschlüsselt. Im Heimnetz (`0.0.0.0`) dagegen läuft der Verkehr unverschlüsselt.
- **Optional echtes HTTPS mit „tailscale serve“.** Dafür müssen in der Tailscale-Verwaltung unter *DNS*
  **MagicDNS** und **HTTPS Certificates** eingeschaltet sein. Dann im Unraid-Terminal:

  ```sh
  tailscale serve --bg --https=8443 http://127.0.0.1:8010
  ```

  Danach in `unraid/.env` setzen und `sh unraid/einrichten.sh` erneut ausführen:

  ```
  CSRF_TRUSTED_ORIGINS=https://*.ts.net:8443
  SECURE_COOKIES=1
  ```

  Aufruf dann unter `https://tower.tail1234.ts.net:8443`. Ist der Port nur an die Tailscale-IP gebunden,
  im `serve`-Befehl statt `127.0.0.1` diese IP eintragen.
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
  `docker compose -f /mnt/user/appdata/schulverwaltung/unraid/docker-compose.yml exec -T web python manage.py modulsicherung`
  (Pfad an den eigenen Installationsordner anpassen).

