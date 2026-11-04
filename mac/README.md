# Schulnexus – macOS-Desktopapp

Native SwiftUI-Hülle (WKWebView) um den unveränderten Django-Server aus `src/`.
Kein Docker nötig: die App startet gunicorn lokal auf `127.0.0.1` und nutzt SQLite.

## Bauen

    cd mac
    ./build-app.sh          # erzeugt dist/Schulnexus.app

Voraussetzung: Xcode-Kommandozeilenwerkzeuge (Swift 5.9+) und Python 3.12 oder neuer
(z. B. `brew install python@3.13`).

## Erster Start

- Python-Umgebung unter `~/Library/Application Support/Schulnexus/venv` (einmalig, einige Minuten).
- Zugangsdaten für `admin` und der Verschlüsselungsschlüssel werden einmal angezeigt
  und in `geheimnisse.json` (Rechte 0600) gespeichert.
- Einstellungen (Schulname, Ort, Zeitzone) in `einstellungen.env` im selben Ordner.

## Wichtig

- Der Verschlüsselungsschlüssel (`datenSchluessel`) muss gesichert werden. Ohne ihn sind
  Anhänge und Sicherungen nicht lesbar.
- Die App ist für **eine Person auf einem Rechner** gedacht. Für mehrere Nutzer im Netz
  weiterhin den Docker-Betrieb verwenden (siehe `README.md`).
- HTTPS ist in der Desktopvariante nicht eingerichtet (`HTTPS=0`).
- Der Server beendet sich beim regulären Beenden der App. Ein Restprozess aus einem
  Absturz wird beim nächsten Start automatisch beendet.
