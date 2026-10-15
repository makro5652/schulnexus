#!/bin/sh
# Startet Schulnexus lokal mit Docker.
# Beim ersten Start wird eine .env mit zufälligen Passwörtern erzeugt.
set -e
cd "$(dirname "$0")"

if ! docker info >/dev/null 2>&1; then
  echo "Docker läuft nicht. Bitte Docker Desktop starten und das Skript erneut ausführen."
  exit 1
fi

zufall() { LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$1"; }
# 32 Zufallsbytes, Base64 (URL-sicher) – Schlüssel für die Verschlüsselung gespeicherter Dateien
schluessel() { head -c 32 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n'; }

if [ ! -f .env ]; then
  echo "Erzeuge .env mit zufälligen Passwörtern ..."
  ADMIN_PW="$(zufall 16)"
  DEMO_PW="$(zufall 12)"
  sed -e "s|^SECRET_KEY=.*|SECRET_KEY=$(zufall 50)|" \
      -e "s|^DB_PASSWORT=.*|DB_PASSWORT=$(zufall 24)|" \
      -e "s|^ADMIN_PASSWORT=.*|ADMIN_PASSWORT=${ADMIN_PW}|" \
      -e "s|^DEMO_PASSWORT=.*|DEMO_PASSWORT=${DEMO_PW}|" \
      -e "s|^DATEN_SCHLUESSEL=.*|DATEN_SCHLUESSEL=$(schluessel)|" \
      .env.example > .env
  chmod 600 .env
  NEUER_SCHLUESSEL=1
fi

# Ab 0.4.6.0: bestehende .env um den Schlüssel für die Verschlüsselung ergänzen (einmalig)
if ! grep -q '^DATEN_SCHLUESSEL=' .env; then
  printf '\n# Verschlüsselung gespeicherter Dateien (ab 0.4.6.0) – getrennt vom Server sicher aufbewahren!\nDATEN_SCHLUESSEL=%s\nOFFICE_MANDANT=\nHTTPS=0\n' "$(schluessel)" >> .env
  NEUER_SCHLUESSEL=1
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
echo "Schulnexus läuft:  http://localhost:${PORT}"
echo "Verwaltungsoberfläche:  http://localhost:${PORT}/verwaltung/"
echo ""
echo "Zugangsdaten stehen in der Datei .env:"
grep -E '^(ADMIN_BENUTZER|ADMIN_PASSWORT|DEMO_PASSWORT)=' .env | sed 's/^/  /'
echo "  Demo-Konten (Passwort = DEMO_PASSWORT): lehrkraft, mittelstufe, oberstufe, schulleitung, verwaltung,"
echo "  verwaltungsleitung, personal, finanzen, foerderung"
echo ""
echo "Stoppen mit:  docker compose down"

if command -v open >/dev/null 2>&1; then open "http://localhost:${PORT}"; fi

if [ -n "${NEUER_SCHLUESSEL:-}" ]; then
  echo ""
  echo "WICHTIG: In der .env wurde ein Schlüssel für die Verschlüsselung erzeugt (DATEN_SCHLUESSEL)."
  echo "Bitte ausdrucken bzw. getrennt vom Server sicher aufbewahren. Ohne ihn sind Anhänge und"
  echo "Modulsicherungen nicht mehr lesbar:"
  grep '^DATEN_SCHLUESSEL=' .env | sed 's/^/  /'
fi
