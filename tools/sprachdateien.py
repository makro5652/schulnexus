"""
Pflege der Übersetzungen (Deutsch -> Englisch).

Ablauf nach neuen oder geänderten Texten im Code:
  1. cd src && python manage.py makemessages -l en --no-obsolete --ignore "*/migrations/*" --ignore "staticfiles/*"
  2. Neue Einträge in src/locale/en/LC_MESSAGES/django.po übersetzen (msgstr ausfüllen)
  3. python ../tools/sprachdateien.py pruefen     -> listet fehlende Übersetzungen
     python ../tools/sprachdateien.py kompilieren -> erzeugt django.mo (ohne GNU gettext, nur mit polib)

Der Test portal.tests_sprache.UebersetzungVollstaendig schlägt fehl, solange Übersetzungen fehlen.
"""
import sys
from pathlib import Path

import polib

PO = Path(__file__).resolve().parent.parent / "src" / "locale" / "en" / "LC_MESSAGES" / "django.po"


def fehlende(po):
    return [e for e in po if not e.obsolete and (not e.translated() or "fuzzy" in e.flags)]


if __name__ == "__main__":
    befehl = sys.argv[1] if len(sys.argv) > 1 else "pruefen"
    po = polib.pofile(str(PO))
    if befehl == "pruefen":
        offen = fehlende(po)
        for e in offen:
            print(f"FEHLT: {e.msgid!r}")
        print(f"{len(po) - len(offen)} von {len(po)} Texten übersetzt.")
        sys.exit(1 if offen else 0)
    if befehl == "kompilieren":
        # Hinweiskommentare früherer Fassungen („#| msgid …“) entfernen – sie stören msgmerge, wenn sie unvollständig sind
        for e in po:
            e.previous_msgid = e.previous_msgid_plural = e.previous_msgctxt = None
        po.save()
        po.save_as_mofile(str(PO.with_suffix(".mo")))
        print(f"{PO.with_suffix('.mo')} geschrieben.")
