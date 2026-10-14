#!/bin/sh
# Schulverwaltung auf Unraid einrichten oder aktualisieren.
# Aufruf im Unraid-Terminal aus dem Projektordner:   sh unraid/einrichten.sh
# Beim ersten Aufruf wird unraid/.env mit zufälligen Passwörtern erzeugt. Spätere Aufrufe bauen
# die neue Version und starten neu; Daten und Einstellungen bleiben erhalten.
set -e
cd "$(dirname "$0")"

if ! docker info >/dev/null 2>&1; then
  echo "Docker läuft nicht. In Unraid unter Settings > Docker den Docker-Dienst aktivieren."
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "Der Befehl 'docker compose' fehlt. Bitte in Unraid unter Apps das Plugin"
  echo "„Docker Compose Manager“ installieren und das Skript erneut starten."
  exit 1
fi

zufall() { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$1"; }
# 32 Zufallsbytes, Base64 (URL-sicher) – Schlüssel für die Verschlüsselung gespeicherter Dateien
schluessel() { head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n'; }
wert() { grep "^$1=" .env | head -n 1 | cut -d= -f2-; }
setzen() { sed -i "s|^$1=.*|$1=$2|" .env; }

# Tailscale des Unraid-Servers (Plugin) – nur zur Anzeige der Adresse und für die Option „nur Tailscale“
TS_IP="$(tailscale ip -4 2>/dev/null | head -n 1 || true)"
TS_NAME="$(tailscale status --json 2>/dev/null | grep -o '"DNSName": *"[^"]*"' | head -n 1 | sed 's/.*"\([^"]*\)"$/\1/; s/\.$//' || true)"

if [ ! -f .env ]; then
  echo "Erzeuge unraid/.env mit zufälligen Passwörtern ..."
  sed -e "s|^SECRET_KEY=.*|SECRET_KEY=$(zufall 50)|" \
      -e "s|^DB_PASSWORT=.*|DB_PASSWORT=$(zufall 24)|" \
      -e "s|^ADMIN_PASSWORT=.*|ADMIN_PASSWORT=$(zufall 16)|" \
      -e "s|^DEMO_PASSWORT=.*|DEMO_PASSWORT=$(zufall 12)|" \
      -e "s|^DATEN_SCHLUESSEL=.*|DATEN_SCHLUESSEL=$(schluessel)|" \
      .env.example > .env
  chmod 600 .env
  NEUER_SCHLUESSEL=1
  printf "Ablageort der Daten [%s]: " "$(wert APPDATA)"
  read -r ANTWORT || true
  [ -n "$ANTWORT" ] && setzen APPDATA "$ANTWORT"
  printf "Port [%s]: " "$(wert PORT)"
  read -r ANTWORT || true
  [ -n "$ANTWORT" ] && setzen PORT "$ANTWORT"
  if [ -n "$TS_IP" ]; then
    printf "Nur über Tailscale erreichbar machen (Port nur an %s binden)? [j/N]: " "$TS_IP"
    read -r ANTWORT || true
    case "$ANTWORT" in j|J|ja|Ja) setzen BIND_ADRESSE "$TS_IP" ;; esac
  fi
fi

# Ab 0.4.6.0: bestehende .env um den Schlüssel für die Verschlüsselung ergänzen (einmalig)
if ! grep -q '^DATEN_SCHLUESSEL=' .env; then
  printf '\n# Verschlüsselung gespeicherter Dateien (ab 0.4.6.0) – getrennt vom Server sicher aufbewahren!\nDATEN_SCHLUESSEL=%s\nOFFICE_MANDANT=\nHTTPS=0\n' "$(schluessel)" >> .env
  NEUER_SCHLUESSEL=1
fi

APPDATA="$(wert APPDATA)"; PORT="$(wert PORT)"; BIND="$(wert BIND_ADRESSE)"
if [ -z "$APPDATA" ]; then echo "APPDATA ist in unraid/.env nicht gesetzt."; exit 1; fi
mkdir -p "$APPDATA"

if [ "$BIND" = "0.0.0.0" ] || [ -z "$BIND" ]; then
  BELEGT="$(docker ps --format '{{.Names}} {{.Ports}}' | grep -E "(0\.0\.0\.0|:::):${PORT}->" | grep -v '^schulverwaltung-' || true)"
else
  BELEGT="$(docker ps --format '{{.Names}} {{.Ports}}' | grep -E "(0\.0\.0\.0|${BIND}):${PORT}->" | grep -v '^schulverwaltung-' || true)"
fi
if [ -n "$BELEGT" ]; then
  echo "Port ${PORT} wird bereits verwendet von: $(echo "$BELEGT" | cut -d' ' -f1)"
  echo "Bitte in unraid/.env bei PORT einen anderen Port eintragen und das Skript erneut starten."
  exit 1
fi

echo ""
echo "Baue und starte die Container (beim ersten Mal einige Minuten) ..."
docker compose up -d --build --remove-orphans

printf "Warte, bis die Anwendung bereit ist "
i=0
while :; do
  ID="$(docker compose ps -q web 2>/dev/null || true)"
  STATUS="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$ID" 2>/dev/null || true)"
  [ "$STATUS" = "healthy" ] && break
  i=$((i+1))
  if [ "$i" -gt 120 ]; then
    echo ""
    echo "Die Anwendung meldet sich nicht. Protokoll ansehen mit:"
    echo "  docker compose -f unraid/docker-compose.yml logs web"
    exit 1
  fi
  printf "."
  sleep 3
done
echo " bereit."

echo ""
echo "Schulverwaltung läuft. Aufruf von einem Gerät im Tailnet:"
[ -n "$TS_NAME" ] && echo "  http://${TS_NAME}:${PORT}"
[ -n "$TS_IP" ] && echo "  http://${TS_IP}:${PORT}"
[ -z "$TS_NAME$TS_IP" ] && echo "  http://<Tailscale-Name oder -IP des Unraid-Servers>:${PORT}"
if [ "$BIND" = "0.0.0.0" ] || [ -z "$BIND" ]; then
  echo "  (zusätzlich im Heimnetz: http://<IP des Unraid-Servers>:${PORT})"
fi
echo ""
echo "Zugangsdaten (stehen auch in unraid/.env):"
grep -E '^(ADMIN_BENUTZER|ADMIN_PASSWORT|DEMO_PASSWORT)=' .env | sed 's/^/  /'
if [ "$(wert DEMO_DATEN)" = "1" ]; then
  echo "  Demo-Konten (Passwort = DEMO_PASSWORT): lehrkraft, mittelstufe, oberstufe, schulleitung, verwaltung,"
  echo "  verwaltungsleitung, personal, finanzen, foerderung"
fi
echo ""
echo "Datenbanksicherungen: $APPDATA/sicherungen (täglich, $(wert SICHERUNG_BEHALTEN_TAGE) Tage aufbewahrt)"

if [ -n "${NEUER_SCHLUESSEL:-}" ]; then
  echo ""
  echo "WICHTIG: In unraid/.env wurde ein Schlüssel für die Verschlüsselung erzeugt (DATEN_SCHLUESSEL)."
  echo "Bitte ausdrucken bzw. getrennt vom Server sicher aufbewahren. Ohne ihn sind Anhänge und"
  echo "Modulsicherungen nicht mehr lesbar:"
  grep '^DATEN_SCHLUESSEL=' .env | sed 's/^/  /'
fi
