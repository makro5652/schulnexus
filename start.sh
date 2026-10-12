#!/bin/sh
# Startet die Schulverwaltung lokal mit Docker.
# Beim ersten Start wird eine .env mit zufälligen Passwörtern erzeugt.
set -e
cd "$(dirname "$0")"

if ! docker info >/dev/null 2>&1; then
  echo "Docker läuft nicht. Bitte Docker Desktop starten und das Skript erneut ausführen."
  exit 1
fi

zufall() { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$1"; }

if [ ! -f .env ]; then
  echo "Erzeuge .env mit zufälligen Passwörtern ..."
  ADMIN_PW="$(zufall 16)"
  DEMO_PW="$(zufall 12)"
  sed -e "s|^SECRET_KEY=.*|SECRET_KEY=$(zufall 50)|" \
      -e "s|^DB_PASSWORT=.*|DB_PASSWORT=$(zufall 24)|" \
      -e "s|^ADMIN_PASSWORT=.*|ADMIN_PASSWORT=${ADMIN_PW}|" \
      -e "s|^DEMO_PASSWORT=.*|DEMO_PASSWORT=${DEMO_PW}|" \
      .env.example > .env
  chmod 600 .env
fi

PORT="$(grep '^PORT=' .env | cut -d= -f2)"; PORT="${PORT:-8000}"

echo "Baue und starte die Container (beim ersten Mal einige Minuten) ..."
docker compose up --build -d

printf "Warte, bis die Anwendung bereit ist "
i=0
until curl -fsS "http://localhost:${PORT}/gesundheit/" >/dev/null 2>&1; do
  i=$((i+1))
  if [ "$i" -gt 90 ]; then
    echo ""
    echo "Die Anwendung antwortet nicht. Protokoll ansehen mit:  docker compose logs web"
    exit 1
  fi
  printf "."
  sleep 2
done
echo " bereit."

echo ""
echo "Schulverwaltung läuft:  http://localhost:${PORT}"
echo "Verwaltungsoberfläche:  http://localhost:${PORT}/verwaltung/"
echo ""
echo "Zugangsdaten stehen in der Datei .env:"
grep -E '^(ADMIN_BENUTZER|ADMIN_PASSWORT|DEMO_PASSWORT)=' .env | sed 's/^/  /'
echo "  Demo-Konten (Passwort = DEMO_PASSWORT): lehrkraft, verwaltung"
echo ""
echo "Stoppen mit:  docker compose down"

if command -v open >/dev/null 2>&1; then open "http://localhost:${PORT}"; fi
