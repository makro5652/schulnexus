#!/bin/sh
# Schulnexus auf einem VPS ohne Traefik einrichten oder aktualisieren (mitgelieferter Caddy-Proxy, automatisches HTTPS).
# Aufruf aus dem Projektordner:   sh vps/einrichten-caddy.sh            (fragt nach der Adresse)
#                                 sh vps/einrichten-caddy.sh schule.example.org
# Beim ersten Aufruf wird .env mit zufälligen Passwörtern erzeugt und für den Betrieb hinter dem Proxy (HTTPS)
# eingestellt. Spätere Aufrufe bauen die neue Version und starten neu; Daten und Einstellungen bleiben erhalten.
set -e
cd "$(dirname "$0")/.."

if ! docker info >/dev/null 2>&1; then
  echo "Docker läuft nicht oder fehlt. Bitte Docker installieren bzw. starten."
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "Der Befehl 'docker compose' fehlt (Paket docker-compose-plugin)."
  exit 1
fi

zufall() { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$1"; }
# 32 Zufallsbytes, Base64 (URL-sicher) – Schlüssel für die Verschlüsselung gespeicherter Dateien
schluessel() { head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n'; }
wert() { grep "^$1=" .env | head -n 1 | cut -d= -f2-; }
setzen() {
  if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else printf '%s=%s\n' "$1" "$2" >> .env; fi
}

# --------------------------------------------------------------- Ports 80 und 443 müssen frei sein
# (beim Aktualisieren belegt unser eigener Caddy sie bereits – das ist in Ordnung)
EIGENER="$(docker compose -f docker-compose.yml -f vps/caddy.yml ps -q caddy 2>/dev/null || true)"
if [ -z "$EIGENER" ]; then
  for p in 80 443; do
    BELEGT="$(docker ps --format '{{.Names}} {{.Ports}}' | grep -E "(0\.0\.0\.0|\[::\]|:::?):$p->" | head -n 1 || true)"
    if [ -z "$BELEGT" ] && command -v ss >/dev/null 2>&1; then
      BELEGT="$(ss -ltnH "sport = :$p" 2>/dev/null | head -n 1)"
    fi
    if [ -n "$BELEGT" ]; then
      echo "Port $p ist auf diesem Server bereits belegt (z. B. durch Traefik, Nginx oder Apache):"
      echo "  $BELEGT"
      echo "Dieses Skript braucht freie Ports 80 und 443. Mit vorhandenem Traefik stattdessen: sh vps/einrichten.sh"
      echo "Belegung ansehen:  ss -ltnp | grep -E ':(80|443) '"
      exit 1
    fi
  done
fi

# --------------------------------------------------------------- .env beim ersten Aufruf
if [ ! -f .env ]; then
  echo "Erzeuge .env mit zufälligen Passwörtern ..."
  sed -e "s|^SECRET_KEY=.*|SECRET_KEY=$(zufall 50)|" \
      -e "s|^DB_PASSWORT=.*|DB_PASSWORT=$(zufall 24)|" \
      -e "s|^ADMIN_PASSWORT=.*|ADMIN_PASSWORT=$(zufall 16)|" \
      -e "s|^DEMO_PASSWORT=.*|DEMO_PASSWORT=$(zufall 12)|" \
      -e "s|^DATEN_SCHLUESSEL=.*|DATEN_SCHLUESSEL=$(schluessel)|" \
      .env.example > .env
  chmod 600 .env
  NEUER_SCHLUESSEL=1
fi

# Adresse und HTTPS-Betrieb einstellen: beim ersten Aufruf, wenn eine Adresse übergeben wird, oder wenn sie in
# einer vorhandenen .env fehlt (z. B. nach einem abgebrochenen Versuch mit vps/einrichten.sh)
DOMAIN="${1:-}"
if [ -n "$DOMAIN" ] || [ -z "$(wert DOMAIN)" ]; then
  while [ -z "$DOMAIN" ]; do
    printf "Adresse (Domain), unter der Schulnexus erreichbar sein soll, z. B. schule.example.org: "
    read -r DOMAIN || exit 1
  done
  setzen DOMAIN "$DOMAIN"
  setzen PORT "127.0.0.1:8000"
  setzen ALLOWED_HOSTS "$DOMAIN,localhost,127.0.0.1"
  setzen CSRF_TRUSTED_ORIGINS "https://$DOMAIN"
  setzen HTTPS 1
  setzen HINTER_PROXY 1
  setzen ELTERN_LINK_BASIS "https://$DOMAIN"
fi

# Ab 0.4.6.0: bestehende .env um den Schlüssel für die Verschlüsselung ergänzen (einmalig)
if ! grep -q '^DATEN_SCHLUESSEL=' .env; then
  printf '\n# Verschlüsselung gespeicherter Dateien (ab 0.4.6.0) – getrennt vom Server sicher aufbewahren!\nDATEN_SCHLUESSEL=%s\n' "$(schluessel)" >> .env
  NEUER_SCHLUESSEL=1
fi

DOMAIN="$(wert DOMAIN)"
if [ -z "$DOMAIN" ]; then echo "DOMAIN ist in .env nicht gesetzt."; exit 1; fi

echo ""
echo "Baue und starte die Container (beim ersten Mal einige Minuten) ..."
docker compose -f docker-compose.yml -f vps/caddy.yml up -d --build --remove-orphans

printf "Warte, bis die Anwendung bereit ist "
i=0
while :; do
  ID="$(docker compose -f docker-compose.yml -f vps/caddy.yml ps -q web 2>/dev/null || true)"
  STATUS="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$ID" 2>/dev/null || true)"
  [ "$STATUS" = "healthy" ] && break
  i=$((i+1))
  if [ "$i" -gt 120 ]; then
    echo ""
    echo "Die Anwendung meldet sich nicht. Protokoll ansehen mit:"
    echo "  docker compose -f docker-compose.yml -f vps/caddy.yml logs web"
    exit 1
  fi
  printf "."
  sleep 3
done
echo " bereit."

echo ""
echo "Schulnexus läuft:  https://${DOMAIN}"
echo "(Das Zertifikat holt Caddy beim ersten Aufruf; das kann einige Sekunden dauern."
echo " Voraussetzung: Ein DNS-Eintrag für ${DOMAIN} zeigt auf diesen Server, Ports 80 und 443 sind von außen erreichbar."
echo " Bei Problemen: docker compose -f docker-compose.yml -f vps/caddy.yml logs caddy)"
echo ""
echo "Zugangsdaten (stehen auch in .env):"
grep -E '^(ADMIN_BENUTZER|ADMIN_PASSWORT|DEMO_PASSWORT)=' .env | sed 's/^/  /'
if [ "$(wert DEMO_DATEN)" = "1" ]; then
  echo "  Demo-Konten (Passwort = DEMO_PASSWORT): lehrkraft, mittelstufe, oberstufe, schulleitung,"
  echo "  stellvertretung, verwaltung, verwaltungsleitung, personal, finanzen, foerderung, it"
  echo ""
  echo "Achtung: Die Seite ist öffentlich erreichbar. Nur die erfundenen Demo-Daten verwenden."
fi

if [ -n "${NEUER_SCHLUESSEL:-}" ]; then
  echo ""
  echo "WICHTIG: In .env wurde ein Schlüssel für die Verschlüsselung erzeugt (DATEN_SCHLUESSEL)."
  echo "Bitte getrennt vom Server sicher aufbewahren. Ohne ihn sind Anhänge und"
  echo "Modulsicherungen nicht mehr lesbar:"
  grep '^DATEN_SCHLUESSEL=' .env | sed 's/^/  /'
fi
