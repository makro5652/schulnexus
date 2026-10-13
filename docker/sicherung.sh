#!/bin/sh
# Tägliche Sicherung der Datenbank (pg_dump im Custom-Format), erstmals beim Start.
# Alte Sicherungen werden nach SICHERUNG_BEHALTEN_TAGE Tagen gelöscht.
set -u
ZIEL=/sicherungen
TAGE="${SICHERUNG_BEHALTEN_TAGE:-14}"
mkdir -p "$ZIEL"

until pg_isready -q; do sleep 5; done

while true; do
  datei="$ZIEL/schulverwaltung-$(date +%Y-%m-%d_%H%M).dump"
  if pg_dump --format=custom --file="$datei.tmp"; then
    mv "$datei.tmp" "$datei"
    echo "$(date '+%Y-%m-%d %H:%M') Sicherung erstellt: $(basename "$datei")"
  else
    rm -f "$datei.tmp"
    echo "$(date '+%Y-%m-%d %H:%M') FEHLER: Sicherung fehlgeschlagen" >&2
  fi
  find "$ZIEL" -name 'schulverwaltung-*.dump' -type f -mtime +"$TAGE" -delete
  sleep 86400
done
