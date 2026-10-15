#!/bin/sh
# edunex auf einem VPS hinter einem vorhandenen Traefik einrichten oder aktualisieren.
# Aufruf aus dem Projektordner:   sh vps/einrichten.sh            (fragt nach der Adresse)
#                                 sh vps/einrichten.sh schule.example.org
# Beim ersten Aufruf wird .env mit zufälligen Passwörtern erzeugt und für den Betrieb hinter Traefik
# (HTTPS) eingestellt. Netzwerk, Entrypoint und Zertifikats-Resolver von Traefik werden aus den
# laufenden Containern ermittelt und zur Bestätigung angezeigt. Spätere Aufrufe bauen die neue Version
# und starten neu; Daten und Einstellungen bleiben erhalten.
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
fragen() {  # fragen "Text" Vorgabe  -> Antwort oder Vorgabe
  printf "%s [%s]: " "$1" "$2" >&2
  read -r ANTWORT || true
  if [ -n "$ANTWORT" ]; then echo "$ANTWORT"; else echo "$2"; fi
}
haeufigster() { sort | uniq -c | sort -rn | head -n 1 | awk '{print $2}'; }

# --------------------------------------------------------------- Traefik ermitteln
TRAEFIK="$(docker ps --format '{{.Names}} {{.Image}}' | awk 'tolower($2) ~ /traefik/ {print $1; exit}')"
if [ -z "$TRAEFIK" ]; then
  echo "Es läuft kein Traefik-Container. Dieses Skript setzt einen vorhandenen Traefik voraus."
  echo "Ohne Traefik: README.md, Abschnitt „Betrieb auf einem VPS mit Traefik“, Hinweis am Ende."
  exit 1
fi
NETZ_VORSCHLAG="$(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}{{"\n"}}{{end}}' "$TRAEFIK" \
  | grep -vE '^(bridge|host|none)?$' | head -n 1)"
LABELS="$(docker ps -q | xargs -r docker inspect -f '{{range $k, $v := .Config.Labels}}{{$k}}={{$v}}{{"\n"}}{{end}}' 2>/dev/null || true)"
ARGS="$(docker inspect -f '{{range .Config.Cmd}}{{.}}{{"\n"}}{{end}}{{range .Args}}{{.}}{{"\n"}}{{end}}' "$TRAEFIK" 2>/dev/null || true)"
EP_VORSCHLAG="$(echo "$LABELS" | grep -E '^traefik\.http\.routers\.[^=]+\.entrypoints=' | grep -v 'edunex' | cut -d= -f2 | cut -d, -f1 | haeufigster)"
[ -z "$EP_VORSCHLAG" ] && EP_VORSCHLAG="$(echo "$ARGS" | grep -oE 'entrypoints\.[A-Za-z0-9_-]+\.address=:443' | head -n 1 | cut -d. -f2)"
RES_VORSCHLAG="$(echo "$LABELS" | grep -E '^traefik\.http\.routers\.[^=]+\.tls\.certresolver=' | grep -v 'edunex' | cut -d= -f2 | haeufigster)"
[ -z "$RES_VORSCHLAG" ] && RES_VORSCHLAG="$(echo "$ARGS" | grep -oE 'certificatesresolvers\.[A-Za-z0-9_-]+\.' | head -n 1 | cut -d. -f2)"

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

  DOMAIN="${1:-}"
  while [ -z "$DOMAIN" ]; do
    printf "Adresse (Domain), unter der edunex erreichbar sein soll, z. B. schule.example.org: "
    read -r DOMAIN || exit 1
  done
  echo "Gefundener Traefik-Container: $TRAEFIK"
  NETZ="$(fragen "Docker-Netzwerk von Traefik" "${NETZ_VORSCHLAG:-traefik}")"
  EP="$(fragen "Entrypoint für https" "${EP_VORSCHLAG:-websecure}")"
  RES="$(fragen "Zertifikats-Resolver" "${RES_VORSCHLAG:-letsencrypt}")"
  LPORT="$(fragen "Lokaler Port (nur auf dem Server selbst erreichbar)" "8000")"

  setzen DOMAIN "$DOMAIN"
  setzen TRAEFIK_NETZWERK "$NETZ"
  setzen TRAEFIK_ENTRYPOINT "$EP"
  setzen TRAEFIK_RESOLVER "$RES"
  setzen PORT "127.0.0.1:$LPORT"
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

DOMAIN="$(wert DOMAIN)"; NETZ="$(wert TRAEFIK_NETZWERK)"
for n in DOMAIN TRAEFIK_NETZWERK; do
  if [ -z "$(wert $n)" ]; then echo "$n ist in .env nicht gesetzt."; exit 1; fi
done
if ! docker network inspect "$NETZ" >/dev/null 2>&1; then
  echo "Das Docker-Netzwerk „$NETZ“ gibt es nicht. Vorhandene Netzwerke:"
  docker network ls --format '  {{.Name}}'
  echo "Bitte in .env bei TRAEFIK_NETZWERK den richtigen Namen eintragen und das Skript erneut starten."
  exit 1
fi

echo ""
echo "Baue und starte die Container (beim ersten Mal einige Minuten) ..."
docker compose -f docker-compose.yml -f vps/traefik.yml up -d --build --remove-orphans

printf "Warte, bis die Anwendung bereit ist "
i=0
while :; do
  ID="$(docker compose -f docker-compose.yml -f vps/traefik.yml ps -q web 2>/dev/null || true)"
  STATUS="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{end}}' "$ID" 2>/dev/null || true)"
  [ "$STATUS" = "healthy" ] && break
  i=$((i+1))
  if [ "$i" -gt 120 ]; then
    echo ""
    echo "Die Anwendung meldet sich nicht. Protokoll ansehen mit:"
    echo "  docker compose -f docker-compose.yml -f vps/traefik.yml logs web"
    exit 1
  fi
  printf "."
  sleep 3
done
echo " bereit."

echo ""
echo "edunex läuft:  https://${DOMAIN}"
echo "(Das Zertifikat holt Traefik beim ersten Aufruf; das kann einige Sekunden dauern."
echo " Voraussetzung: Ein DNS-Eintrag für ${DOMAIN} zeigt auf diesen Server.)"
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
