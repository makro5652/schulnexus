"""
Erzeugt docs/schulnexus-spezifikation.json – eine maschinenlesbare Beschreibung des gesamten Projekts, mit der eine KI
Schulnexus nachbauen kann.

Technische Teile (Modelle mit allen Feldern, URLs und Ansichten, Rollen und Rechte, Einstellungen, Befehle, Vorlagen,
statische Dateien, Tests, Betrieb) werden direkt aus dem Code gelesen und sind damit immer aktuell. Die fachlichen
Leitlinien, Geschäftsregeln je Modul und die Bau-Reihenfolge stehen weiter unten in FACHLICH und werden von Hand gepflegt.

Enthält keine Daten aus der Datenbank (weder echte noch Demo-Daten) – nur die Struktur des Programms.

Aufruf (im Projektordner, z. B. in einem Container mit den Abhängigkeiten):
  SECRET_KEY=x DATABASE_URL=postgres://x:x@localhost/x python tools/spezifikation_erzeugen.py > docs/schulnexus-spezifikation.json
"""
import ast
import inspect
import json
import os
import re
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
SRC = WURZEL / "src"
sys.path.insert(0, str(SRC))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django  # noqa: E402

django.setup()

from django.apps import apps  # noqa: E402
from django.conf import settings  # noqa: E402
from django.contrib import admin  # noqa: E402
from django.core.management import get_commands, load_command_class  # noqa: E402
from django.db import models  # noqa: E402
from django.urls import URLPattern, URLResolver, get_resolver  # noqa: E402
from django.utils import translation  # noqa: E402

translation.activate("de")

EIGENE_APPS = ["stammdaten", "noten", "fehlzeiten", "nachmittag", "portal", "foerderung", "zeugnisse", "sicherung",
               "elternkontakt", "laufbahn", "termine", "aufnahme"]
# Demo-Daten gehören nicht in die Beschreibung (nur Zweck des Befehls)
AUSLASSEN = {"portal/management/commands/demodaten.py"}


# ---------------------------------------------------------------- Hilfen

def text(wert):
    return str(wert) if wert is not None else None


def erster_absatz(doc):
    return (doc or "").strip().split("\n\n")[0].replace("\n", " ").strip() or None


def voll(doc):
    return inspect.cleandoc(doc).strip() if doc else None


def standardwert(feld):
    if feld.default is models.NOT_PROVIDED:
        return None
    if callable(feld.default):
        return f"<{getattr(feld.default, '__name__', 'callable')}()>"
    return feld.default if isinstance(feld.default, (str, int, float, bool, type(None))) else str(feld.default)


# ---------------------------------------------------------------- Modelle

def feld_beschreibung(f):
    d = {"name": f.name, "typ": type(f).__name__, "bezeichnung": text(getattr(f, "verbose_name", None))}
    for attr in ("null", "blank", "unique", "editable", "db_index"):
        wert = getattr(f, attr, None)
        if wert:
            d[attr] = wert
    if getattr(f, "max_length", None):
        d["max_length"] = f.max_length
    if isinstance(f, models.DecimalField):
        d["max_digits"], d["decimal_places"] = f.max_digits, f.decimal_places
    if getattr(f, "choices", None):
        d["auswahl"] = [[k, text(v)] for k, v in f.flatchoices]
    if hasattr(f, "default") and standardwert(f) is not None:
        d["standard"] = standardwert(f)
    if getattr(f, "auto_now", False):
        d["auto_now"] = True
    if getattr(f, "auto_now_add", False):
        d["auto_now_add"] = True
    if getattr(f, "help_text", ""):
        d["hilfe"] = text(f.help_text)
    if f.is_relation and f.related_model is not None:
        d["ziel"] = f.related_model._meta.label
        if f.remote_field is not None:
            if hasattr(f.remote_field, "on_delete") and f.remote_field.on_delete is not None:
                d["on_delete"] = f.remote_field.on_delete.__name__
            if f.remote_field.related_name:
                d["related_name"] = f.remote_field.related_name
            if getattr(f.remote_field, "limit_choices_to", None):
                d["limit_choices_to"] = str(f.remote_field.limit_choices_to)
    if f.validators:
        d["validatoren"] = [f"{type(v).__name__}({getattr(v, 'limit_value', '')})" for v in f.validators
                            if type(v).__name__ not in ("MaxLengthValidator", "DecimalValidator")]
        if not d["validatoren"]:
            del d["validatoren"]
    return d


def eigene_methoden(cls):
    erg = []
    for name, obj in cls.__dict__.items():
        if name.startswith("_") and name not in ("__str__",):
            continue
        ziel = obj.fget if isinstance(obj, property) else getattr(obj, "__func__", obj)
        if not callable(ziel) and not isinstance(obj, property):
            continue
        if not inspect.isfunction(ziel):
            continue
        try:
            signatur = str(inspect.signature(ziel))
        except (TypeError, ValueError):
            signatur = "()"
        erg.append({"name": name, "art": "property" if isinstance(obj, property) else
                    ("classmethod" if isinstance(obj, classmethod) else "staticmethod" if isinstance(obj, staticmethod) else "methode"),
                    "signatur": signatur, "doc": voll(ziel.__doc__)})
    return erg


def modelle(app):
    erg = []
    for m in app.get_models():
        if m.__name__.startswith("Historical"):
            continue
        meta = m._meta
        erg.append({
            "name": m.__name__, "tabelle": meta.db_table, "bezeichnung": text(meta.verbose_name),
            "mehrzahl": text(meta.verbose_name_plural), "doc": voll(m.__doc__) if m.__doc__ and not m.__doc__.startswith(m.__name__ + "(") else None,
            "basisklassen": [b.__name__ for b in m.__mro__[1:] if b not in (models.Model, object) and not b.__name__.startswith("_")][:3],
            "felder": [feld_beschreibung(f) for f in meta.get_fields() if getattr(f, "concrete", False) or f.many_to_many and not f.auto_created],
            "ordering": list(meta.ordering) if meta.ordering else None,
            "unique_together": [list(u) for u in meta.unique_together] or None,
            "constraints": [str(c) for c in meta.constraints] or None,
            "eigene_rechte": [list(p) for p in meta.permissions] or None,
            "aenderungsprotokoll": any(type(getattr(m, attr, None)).__name__ == "HistoryManager" or attr == "history"
                                       for attr in ("history",) if hasattr(m, attr)),
            "verwaltungsoberflaeche": _admin(m),
            "methoden": eigene_methoden(m),
        })
    return erg


def _admin(m):
    ma = admin.site._registry.get(m)
    if ma is None:
        return None
    d = {"klasse": type(ma).__name__}
    for attr in ("list_display", "list_filter", "search_fields", "list_editable", "autocomplete_fields", "readonly_fields"):
        wert = getattr(ma, attr, None)
        if wert:
            d[attr] = [w if isinstance(w, str) else getattr(w, "__name__", str(w)) for w in wert]
    if getattr(ma, "inlines", None):
        d["inlines"] = [i.model.__name__ for i in ma.inlines]
    return d


# ---------------------------------------------------------------- Python-Module (Docstrings, Klassen, Funktionen)

def python_module(app_pfad, label):
    erg = []
    for datei in sorted(app_pfad.rglob("*.py")):
        rel = datei.relative_to(SRC).as_posix()
        if "/migrations/" in rel or "/tests" in rel or datei.name.startswith("tests") or rel in AUSLASSEN:
            continue
        baum = ast.parse(datei.read_text(encoding="utf-8"))
        eintrag = {"datei": f"src/{rel}", "doc": ast.get_docstring(baum), "klassen": [], "funktionen": []}
        for knoten in baum.body:
            if isinstance(knoten, ast.ClassDef):
                eintrag["klassen"].append({
                    "name": knoten.name, "basen": [ast.unparse(b) for b in knoten.bases], "doc": ast.get_docstring(knoten),
                    "methoden": [{"name": f.name, "signatur": "(" + ast.unparse(f.args) + ")", "doc": erster_absatz(ast.get_docstring(f))}
                                 for f in knoten.body if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
                                 and (not f.name.startswith("_") or f.name in ("__init__", "__str__"))]})
            elif isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef)):
                eintrag["funktionen"].append({
                    "name": knoten.name, "signatur": "(" + ast.unparse(knoten.args) + ")",
                    "dekoratoren": [ast.unparse(d) for d in knoten.decorator_list] or None,
                    "doc": ast.get_docstring(knoten)})
        if eintrag["doc"] or eintrag["klassen"] or eintrag["funktionen"]:
            erg.append(eintrag)
    return erg


def tests(app_pfad):
    erg = []
    for datei in sorted(app_pfad.glob("tests*.py")):
        baum = ast.parse(datei.read_text(encoding="utf-8"))
        klassen = []
        for k in baum.body:
            if isinstance(k, ast.ClassDef):
                klassen.append({"klasse": k.name, "doc": ast.get_docstring(k),
                                "faelle": [f.name for f in k.body if isinstance(f, ast.FunctionDef) and f.name.startswith("test")]})
        erg.append({"datei": f"src/{datei.relative_to(SRC).as_posix()}", "doc": ast.get_docstring(baum), "klassen": klassen})
    return erg


# ---------------------------------------------------------------- URLs

def urls():
    erg = []

    def gehe(muster, praefix="", namensraum=""):
        for p in muster:
            if isinstance(p, URLResolver):
                ns = p.namespace or ""
                if ns == "admin":
                    continue
                gehe(p.url_patterns, praefix + str(p.pattern), f"{namensraum}{ns}:" if ns else namensraum)
            elif isinstance(p, URLPattern):
                view = p.callback
                ziel = getattr(view, "view_class", None) or view
                while hasattr(ziel, "__wrapped__"):
                    ziel = ziel.__wrapped__
                erg.append({"route": "/" + praefix + str(p.pattern), "name": f"{namensraum}{p.name}" if p.name else None,
                            "view": f"{ziel.__module__}.{getattr(ziel, '__qualname__', getattr(ziel, '__name__', ''))}",
                            "doc": erster_absatz(ziel.__doc__)})
    gehe(get_resolver().url_patterns)
    return erg


# ---------------------------------------------------------------- Rollen, Einstellungen, Befehle

def rollen():
    from portal import rechte as R
    from portal import rollen as RO

    def rechte_von(wert):
        return wert if isinstance(wert, str) else sorted(wert)
    return {
        "doc": voll(RO.__doc__),
        "reihenfolge": RO.REIHENFOLGE,
        "rollen": [{"name": r, "anzeige": text(RO.ANZEIGE.get(r)), "beschreibung": text(RO.BESCHREIBUNG.get(r)),
                    "standardrechte": rechte_von(RO.ROLLEN_RECHTE.get(r, "__foerderung__" if r == RO.FOERDERKOORDINATION else []))}
                   for r in RO.REIHENFOLGE],
        "foerderkoordination_zusaetzlich": sorted(RO.FOERDERKOORDINATION_EXTRA),
        "portal_rollen": sorted(RO.PORTAL_ROLLEN),
        "rollen_apps": RO.APPS,
        "uebersicht_bereiche": [[k, text(v)] for k, v in RO.BEREICHE],
        "uebersicht_matrix": RO.MATRIX,
        "uebersicht_werte": {k: text(v) for k, v in RO.WERTE.items()},
        "gruppenkonstanten_rechte_py": {name: sorted(getattr(R, name)) if isinstance(getattr(R, name), set) else getattr(R, name)
                                        for name in dir(R) if name.endswith("GRUPPEN")},
        "zeilenweise_rechte": "Neben den Modellrechten prüfen die Module rechte.py zeilenweise (eigener Unterricht, eigene Klasse, "
                              "koordinierte Jahrgänge, Fachbereich, Sperren). Siehe python_module der jeweiligen App.",
    }


def einstellungen():
    zeilen = (SRC / "config" / "settings.py").read_text(encoding="utf-8").splitlines()
    erg, kommentar = [], []
    muster = re.compile(r'(env_bool|env_int|env_list|_jahrgaenge|os\.environ\.get|os\.environ\[)\(?\s*["\']([A-Z0-9_]+)["\'](?:\s*,\s*([^)]*))?')
    for zeile in zeilen:
        s = zeile.strip()
        if s.startswith("#"):
            kommentar.append(s.lstrip("# "))
            continue
        for treffer in muster.finditer(zeile):
            erg.append({"variable": treffer.group(2), "art": treffer.group(1), "standard": (treffer.group(3) or "").strip() or None,
                        "zeile": s, "kommentar": " ".join(kommentar) or None})
        if s:
            kommentar = []
    eindeutig = {}
    for e in erg:
        eindeutig.setdefault(e["variable"], e)
    return {"umgebungsvariablen": list(eindeutig.values()),
            "werte": {k: _jsonbar(getattr(settings, k)) for k in (
                "LANGUAGE_CODE", "LANGUAGES", "TIME_ZONE", "STUFEN", "JAHRESNOTE_JAHRGAENGE", "JAHRESNOTE_ANTEIL_HJ1",
                "INSTALLED_APPS", "MIDDLEWARE", "AUTHENTICATION_BACKENDS", "PASSWORD_HASHERS", "STATIC_URL",
                "ZEUGNIS_FEHLZEITEN", "ZEUGNIS_KOMMENTAR_MAX", "ELTERNPORTAL_AKTIV") if hasattr(settings, k)},
            "context_processors": settings.TEMPLATES[0]["OPTIONS"].get("context_processors")}


def _jsonbar(w):
    if isinstance(w, (set, frozenset, tuple, range)):
        return list(w)
    if isinstance(w, dict):
        return {k: _jsonbar(v) for k, v in w.items()}
    if isinstance(w, list):
        return [_jsonbar(x) for x in w]
    return w if isinstance(w, (str, int, float, bool, type(None))) else str(w)


def befehle():
    erg = []
    for name, app in sorted(get_commands().items()):
        if app not in EIGENE_APPS:
            continue
        cmd = load_command_class(app, name)
        modul = sys.modules[type(cmd).__module__]
        erg.append({"befehl": name, "app": app, "hilfe": text(getattr(cmd, "help", "")),
                    "doc": None if name == "demodaten" else voll(modul.__doc__)})
    return erg


def dateien(ordner, muster):
    erg = []
    for d in sorted((SRC / ordner).rglob(muster)):
        rel = d.relative_to(SRC / ordner).as_posix()
        if "/" in rel and rel.split("/")[0] in ("admin",):
            continue
        erster = ""
        inhalt = d.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"/\*(.*?)\*/", inhalt, re.S) if d.suffix in (".js", ".css") else re.search(r"\{#(.*?)#\}", inhalt, re.S)
        if m:
            erster = " ".join(m.group(1).split())
        eintrag = {"datei": f"src/{ordner}/{rel}", "zeilen": inhalt.count("\n") + 1}
        if d.suffix == ".html":
            basis = re.search(r'{%\s*extends\s+"([^"]+)"', inhalt)
            eintrag["erbt_von"] = basis.group(1) if basis else None
            eintrag["einbindungen"] = sorted(set(re.findall(r'{%\s*include\s+"([^"]+)"', inhalt))) or None
        if erster:
            eintrag["beschreibung"] = erster[:400]
        erg.append(eintrag)
    return erg


def betrieb():
    def lesen(pfad):
        p = WURZEL / pfad
        return p.read_text(encoding="utf-8") if p.exists() else None

    env_beispiel = []
    kommentar = []
    for zeile in (lesen(".env.example") or "").splitlines():
        s = zeile.strip()
        if s.startswith("#"):
            kommentar.append(s.lstrip("# "))
        elif "=" in s:
            env_beispiel.append({"variable": s.split("=", 1)[0], "kommentar": " ".join(kommentar) or None})
            kommentar = []
        else:
            kommentar = []
    return {
        "requirements_txt": lesen("requirements.txt"),
        "dockerfile": lesen("Dockerfile"),
        "docker_compose_yml": lesen("docker-compose.yml"),
        "entrypoint_sh": lesen("docker/entrypoint.sh"),
        "sicherung_sh": lesen("docker/sicherung.sh"),
        "vps_traefik_host_yml": lesen("vps/traefik-host.yml"),
        "vps_traefik_yml": lesen("vps/traefik.yml"),
        "vps_caddy_yml": lesen("vps/caddy.yml"),
        "vps_caddyfile": lesen("vps/Caddyfile"),
        "ci_github_actions": lesen(".github/workflows/pruefung.yml"),
        "ruff_toml": lesen("ruff.toml"),
        "env_beispiel_variablen": env_beispiel,
        "werkzeuge": {"tools/sprachdateien.py": voll(ast.get_docstring(ast.parse(lesen("tools/sprachdateien.py") or ""))),
                      "tools/oberflaeche_pruefen.py": voll(ast.get_docstring(ast.parse(lesen("tools/oberflaeche_pruefen.py") or ""))),
                      "tools/spezifikation_erzeugen.py": voll(__doc__)},
    }


# ---------------------------------------------------------------- Fachliche Beschreibung (von Hand gepflegt)

FACHLICH = {
    "zweck": "Schulnexus ist eine Open-Source-Schulverwaltung für eine Schule (Jahrgänge 1–12,"
             " Sek I nach der Richtlinie für Deutsche Schulen im Ausland, Sek II mit Punkten 0–15). Sie deckt "
             "Stammdaten, Klassen und Kurse, Noten, Zeugnisse und Konferenzen, Fehlzeiten, Förderung, Neuanmeldungen, "
             "Elternkommunikation, Termine, Personal, Schuljahreswechsel, Archiv, Sicherung und Rechte ab.",
    "zielgruppen": ["Lehrkräfte (eigener Unterricht, Klassenleitung)", "Stufenkoordination (Mittel- und Oberstufe)",
                    "Schulleitung und Stellvertretung", "Sekretariat und Verwaltungsleitung", "HR, Finanzen, Förderkoordination",
                    "IT-Administration", "Eltern (persönlicher Link, optional Elternportal)"],
    "technik": {
        "sprache": "Python 3.12, Django 5.2, PostgreSQL 16; serverseitig gerenderte Django-Templates, kein SPA-Framework.",
        "javascript": "Kleines, abhängigkeitsfreies Vanilla-JS je Seite (static/*.js), progressive Verbesserung: Seiten funktionieren "
                      "auch ohne JS (Formulare mit POST, noscript-Knöpfe).",
        "css": "Eine eigene Datei static/portal.css mit CSS-Variablen (--akzent, --linie, --grund, …), drei Designs "
               "(Standard, Catppuccin Latte, Catppuccin Mocha) über data-design am html-Element; menueband.css; zeugnis.css für Druck.",
        "auslieferung": "gunicorn hinter Traefik bzw. Caddy; statische Dateien mit WhiteNoise (Manifest-Hashes).",
        "protokoll": "django-simple-history an allen fachlich wichtigen Modellen (Änderungsprotokoll, Feld 'aenderungsprotokoll'), "
                     "zusätzlich sicherung.Protokoll für Aktionen (Sperren, Export, Wiederherstellung).",
        "sicherheit": "Argon2-Passwörter, Anmeldesperre gegen Durchprobieren, Zwei-Faktor-Anmeldung (TOTP), HTTPS-Einstellungen, "
                      "CSP, Verschlüsselung von Anhängen und Sicherungen mit AES-256-GCM (DATEN_SCHLUESSEL), "
                      "geschützter Download von Anhängen nur über rechtegeprüfte Ansichten.",
        "sprachen": "Oberfläche Deutsch, vollständig nach Englisch übersetzt (gettext, src/locale/en; Test schlägt bei fehlender "
                    "Übersetzung fehl). Stammdaten mit name/name_en (LokalerNameMixin, lokal_name).",
        "verwaltungsoberflaeche": "Django-Admin als 'Verwaltung' für Kataloge und Detailpflege, mit rollenabhängigem Queryset; "
                                  "die täglichen Arbeitsabläufe laufen über eigene Portalseiten.",
    },
    "leitlinien": [
        "Alle Bezeichner, Texte und Kommentare auf Deutsch (Modelle wie Schuelerprofil, Gruppe, Mitgliedschaft, Unterricht).",
        "Rollen sind Django-Benutzergruppen (portal/rollen.py); Modellrechte werden von 'manage.py grundeinrichtung' nur ergänzt, "
        "nie entzogen. Zeilenweise Regeln stehen in je einem Modul rechte.py pro App.",
        "Geschichte bleibt erhalten: Mitgliedschaften werden zum Stichtag beendet statt gelöscht; Laufbahnereignisse sind rücknehmbar; "
        "freigegebene Zeugnisse schreiben ihre Fachnoten fest (ZeugnisFachnote).",
        "Gespeichert wird nur, was sich geändert hat; was inzwischen von anderer Seite geändert wurde, wird nicht überschrieben "
        "(Formulare senden den Ausgangswert als verstecktes Feld mit).",
        "Jede Funktion hat Tests (Django TestCase mit 'manage.py demodaten' als Ausgangslage); ruff für den Stil; GitHub Actions "
        "prüfen Tests, ruff, Sicherheit (bandit, pip-audit) und die Oberfläche (Playwright, tools/oberflaeche_pruefen.py).",
        "Versionsnummer in src/config/version.py (0.4.x.y); jede Version mit Abschnitt in der README.",
        "Personenbezogene Echtdaten gehören nie ins Repository.",
    ],
    "module": {
        "stammdaten": {
            "zweck": "Grunddaten aller anderen Module.",
            "regeln": [
                "Schuljahr mit genau einem aktiven Schuljahr; Abschnitt = Halbjahr (nummer 1/2) mit Beginn/Ende; Stichtag eines "
                "Schuljahres = heute, begrenzt auf Beginn/Ende.",
                "Person ist die gemeinsame Basis; Rollenprofile: Schuelerprofil (Schülernummer, Status aktiv/bewerber/…), "
                "Personalprofil (Kürzel, Bereich, Deputat, Lehrbefähigungen), Elternprofil; Beziehung verbindet Schüler:in und Kontaktperson "
                "(Sorgerecht, Abholung, Rechnungsempfänger).",
                "Gruppe: Typ stammklasse | lerngruppe | ag, Jahrgang, Leitung und stellvertretende Leitung (gleiche Rechte), Raum, "
                "Höchstzahl, Vorgängergruppe (Vorjahr), gebildet_aus (Stammklassen einer Lerngruppe).",
                "Mitgliedschaft mit von/bis; eine Person ist zu einem Zeitpunkt in höchstens einer Stammklasse je Schuljahr; "
                "Zuordnen in eine andere Stammklasse beendet die alte zum Vortag (Klassenwechsel).",
                "Fach mit Kürzel, Reihenfolge, Zeugnisrolle (deutsch, mathematik, fremdsprache, musisch, religion, sonstiges), "
                "Zeugnisspalte (links/rechts), Fachbereich mit bis zu zwei Fachleitungen und Farbe; Stundentafel je Fach und Jahrgang.",
                "Laufbahnabschnitt: Schuljahr, Jahrgang, Bildungsgang, Stammklasse, Ergebnis (versetzt, nicht versetzt, Abschluss …).",
                "Dokument: Anhang zu einer Person mit Kategorie und Zugriffsstufe (akte, verwaltung, foerderung, leitung), "
                "verschlüsselt gespeichert.",
                "Zusatzfeld: frei definierbare Felder an Schüler-, Personal- und Elternprofilen (JSON-Feld zusatzfelder) mit Sichtbarkeit.",
            ],
        },
        "noten": {
            "zweck": "Leistungsbewertung je Unterricht bis zur Zeugnisnote.",
            "regeln": [
                "Unterricht = Halbjahr + Gruppe + Fach (eindeutig) + Lehrkraft + Notenskala; optional Startvorlage (Gewichtungsvorlage), "
                "Wochenstunden (sonst aus der Stundentafel), im 2. Halbjahr Anteil des 1. Halbjahres an der Jahresnote.",
                "Bewertungsordner bilden einen Baum (höchstens 5 Ebenen); Gewichte je Ebene relativ oder in Prozent; Leistungsnachweise "
                "(Titel, Datum im Halbjahr, Gewicht, optional Notenschlüssel mit max. BE) liegen in Ordnern; Note je Schüler:in mit Stufe "
                "oder Sonderstatus (entschuldigt, unentschuldigt → Ersatznote der Skala, befreit, nicht bewertbar) und individuellem Gewicht.",
                "Vorschlag = gewichteter Schnitt über den Ordnerbaum, leere Ordner/Nachweise werden übersprungen; Rundung je Skala "
                "(Nachkommastellen, 'zugunsten' der Schüler:innen); Tendenz = nächste Notenstufe; gefährdet ab Schwelle der Skala.",
                "Jahresnote: im 2. Halbjahr fließt das 1. Halbjahr (Schnitt oder Zeugnisnote) mit dem eingestellten Anteil ein.",
                "Notenregel (Klausurregel) der Schulleitung je Fächer und Jahrgangsbereich: zwei vorgegebene oberste Ordner "
                "(z. B. Klassenarbeiten/Klausuren und Sonstige Mitarbeit) mit festem Prozentanteil und Höchstzahl je Halbjahr "
                "(Standard 2 und 30); geprüft beim Anlegen, Import, Kopieren und Verschieben.",
                "Zeugnisnote je Unterricht und Schüler:in: Stufe oder Vermerk (nb, befreit); ohne Festsetzung automatisch die gerundete "
                "Note aus den Einzelnoten (Herkunft 'auto', per Signal nach jeder Änderung neu berechnet); festgesetzte Noten (Herkunft "
                "excel, klasse, kurs oder leer) haben Vorrang; ohne Einzelnoten nur mit Freigabe 'Zeugnisnote ohne Einzelnoten'.",
                "Notensperre: gesperrt, wenn eine ausdrückliche Sperre gesetzt ist, sonst nach durchgeführter Konferenz, nach dem "
                "Notenschluss-Datum des Jahrgangs oder bei freigegebenem Zeugnis; eine ausdrückliche Freigabe hebt die Automatik auf; "
                "Zeugnisnoten freigegebener Zeugnisse bleiben immer gesperrt.",
                "Leistungsvorgaben: Pflicht-Leistungsnachweise mit Frist je Halbjahr, Jahrgangsbereich und Fächern.",
                "Eingabe: Schnelleingabe (2+, 2, 2-, e, u, b, nb), Notentabelle 'Noten nach Klasse' mit Kacheln je Fach, neuen Spalten "
                "per Knopf, Gewicht im Kopf und Zeugnisnote; Excel-Notentabelle zum Herunterladen/Hochladen mit Vorschau; "
                "Bewertungsstruktur von einem Kurs übernehmen oder auf andere übertragen; Export als Excel und PDF-Notenbogen.",
            ],
        },
        "zeugnisse": {
            "zweck": "Zeugnisse, Kommentare, Konferenzen und Versetzung.",
            "regeln": [
                "Zeugnis je Schüler:in und Halbjahr (Art Halbjahr, Jahr, Abgang); Status Entwurf → freigegeben; bei Freigabe werden die "
                "Fachnoten als ZeugnisFachnote festgeschrieben; Freigabe einzeln oder für eine Klasse aufhebbar (Schulleitung, Stufe).",
                "Zeugniskommentar mit Abzeichnung durch alle unterrichtenden Lehrkräfte; jede inhaltliche Änderung macht Abzeichnungen "
                "ungültig; Anmerkungen als Vorschläge; Textbausteine je Kategorie/Jahrgang mit {vorname}/{sie_er}; optionale Zeichengrenze.",
                "Konferenz (Halbjahres- bzw. Versetzungskonferenz) mit Notenliste der Klasse, Vorschlag je Schüler:in, Beschluss, "
                "Stimmen, Protokoll und Gefährdungsmitteilungen; Abschluss überträgt Versetzungsvermerke in die Jahreszeugnisse.",
                "Versetzung nach Ziffer 5.3–5.5 der Richtlinie Sek I: Kernfächer aus der Zeugnisrolle, Ausgleichsregeln, Nachprüfung.",
                "Notenliste: jede Klasse und jedes Halbjahr (auch vergangene/gesperrte) lesend wie in der Konferenz.",
                "Druck: Zeugnis nach KMK-Muster mit Beiblatt (Kommentar), Unterzeichner:in je Jahrgangsbereich, Englische Übersetzung.",
            ],
        },
        "portal": {
            "zweck": "Startseite, Menüband, Navigation und übergreifende Arbeitsseiten.",
            "regeln": [
                "Menüband (Ribbon) mit Registerkarten und Befehlsgruppen; jeder Befehl erscheint nur mit passendem Recht.",
                "Klassen und Gruppen: Gruppen anlegen/bearbeiten, Schüler:innen zum Stichtag hinzufügen oder abmelden, neue Schüler:innen "
                "anlegen, Reiter 'Fächer und Lehrkräfte' (je Fach und Halbjahr eine Lehrkraft → Unterricht; mit Noten nie löschen).",
                "Schülerakte, Klassenliste, Stufenübersicht, Personensuche, Notizen, Geburtstage, Office-Kacheln.",
                "Rechteprüfung zentral (rechte.py); Konten können einzelne Rollenrechte entzogen bekommen (Benutzereinstellung).",
                "Zwei-Faktor-Anmeldung (TOTP, Wiederherstellungscodes), Anmeldeschutz, Verschlüsselung (krypto.py).",
                "Stundentafel-Seite; Suchauswahl-Widget statt Hin-und-her-Listen.",
            ],
        },
        "fehlzeiten": {"zweck": "Fehlzeiten (ganztägig, stundenweise, Verspätung) mit Status und Zeitraster (Stunden)."},
        "nachmittag": {"zweck": "AG-Angebote, Wünsche der Schüler:innen und Zuteilung per Losverfahren."},
        "foerderung": {"zweck": "Förderpläne mit Zielen und Verlauf, Nachteilsausgleiche mit Genehmigung, Elternbestätigung."},
        "aufnahme": {"zweck": "Neuanmeldungen: Bewerbungsakte mit Kontakten, Unterlagen, Checkliste aus Vorlagen, vorläufiger Klasse "
                              "und Übernahme in die Stammdaten (Person, Schülerprofil, Laufbahn, Mitgliedschaft)."},
        "elternkontakt": {"zweck": "Nachrichten an Eltern mit persönlichem Link oder Elternportal, Antworten, Lese-/Empfangsbestätigung "
                                   "(z. B. Zeugnisempfang), automatische Benachrichtigung bei Fehlzeiten nach Regeln."},
        "laufbahn": {"zweck": "Schuljahreswechsel (neues Schuljahr, Klassen fortschreiben, versetzen, rücknehmbar), Klassenwechsel und "
                              "Abgang im Schuljahr, Archiv und Löschfristen."},
        "termine": {"zweck": "Schulkalender, Räume und Raumbuchung, Elternsprechtage und Lern- und Entwicklungsgespräche mit Zeitraster, "
                             "Verfügbarkeit und Buchung."},
        "sicherung": {"zweck": "Modulweise Sicherung als ZIP (optional verschlüsselt) und Wiederherstellung, PDF-Export je Modul und "
                               "Zeitraum, Benutzerkonten/Rollen/Einzelrechte, Protokoll."},
    },
    "nachbau_reihenfolge": [
        "1. Projektgerüst: Django-Projekt 'config', Einstellungen aus Umgebungsvariablen (siehe einstellungen), PostgreSQL, "
        "WhiteNoise, gettext Deutsch/Englisch, Dockerfile, docker-compose (db + web), entrypoint (migrate, grundeinrichtung, "
        "zeugnisnoten_automatisch, gunicorn).",
        "2. stammdaten (alle Modelle) und portal (Rollen, Rechte, Backend, Menüband, Startseite, base.html, portal.css).",
        "3. 'manage.py grundeinrichtung' (Rollen und Rechte, Notenskalen Sek I/II, Personalbereiche, Kataloge) und "
        "'manage.py demodaten' (erfundene Testschule) als Grundlage der Tests.",
        "4. noten (Modelle, berechnung.py, Eingabe, Bewertungsstruktur, Notentabelle, Sperre, Automatik, Import/Export).",
        "5. zeugnisse (Zeugnisse, Kommentare, Konferenzen, Versetzung, Druck, Notenliste).",
        "6. fehlzeiten, nachmittag, foerderung, aufnahme, elternkontakt, termine, laufbahn, sicherung.",
        "7. Portal-Arbeitsseiten: Klassen und Gruppen, Fächer und Lehrkräfte, Stundentafel, Notenregeln, Notensperre.",
        "8. Englische Übersetzung, Designs, Tests je Funktion, CI.",
    ],
}


# ---------------------------------------------------------------- Zusammenbau

def erzeugen():
    from config.version import VERSION

    module = {}
    for label in EIGENE_APPS:
        app = apps.get_app_config(label)
        pfad = Path(app.path)
        module[label] = {
            "bezeichnung": text(app.verbose_name),
            "fachlich": FACHLICH["module"].get(label),
            "modelle": modelle(app),
            "python_module": python_module(pfad, label),
            "tests": tests(pfad),
        }
    return {
        "format": "schulnexus-spezifikation", "formatversion": 1, "schulnexus_version": VERSION,
        "hinweis": "Automatisch erzeugt mit tools/spezifikation_erzeugen.py. Enthält nur die Programmstruktur, keine Daten.",
        "projekt": {k: v for k, v in FACHLICH.items() if k != "module"},
        "verzeichnisse": {"src/config": "Einstellungen, URLs, Version", "src/<app>": "Django-Apps (siehe module)",
                          "src/templates": "Templates", "src/static": "CSS/JS", "src/locale": "Übersetzungen",
                          "docker": "Startskript, Sicherungsskript", "vps": "Betrieb hinter Traefik/Caddy",
                          "unraid": "Betrieb auf Unraid", "tools": "Hilfsskripte", "docs": "diese Spezifikation"},
        "module": module,
        "config_module": python_module(SRC / "config", "config"),
        "urls": urls(),
        "rollen_und_rechte": rollen(),
        "einstellungen": einstellungen(),
        "verwaltungsbefehle": befehle(),
        "signale": {"noten.automatik": voll(sys.modules["noten.automatik"].__doc__)},
        "templates": dateien("templates", "*.html"),
        "statische_dateien": dateien("static", "*.js") + dateien("static", "*.css"),
        "betrieb": betrieb(),
    }


if __name__ == "__main__":
    json.dump(erzeugen(), sys.stdout, ensure_ascii=False, indent=1, default=str)
    sys.stdout.write("\n")
