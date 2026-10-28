"""
Excel-Notentabelle in Schulnexus (ab 0.4.11.0): Vorlage je Unterricht herunterladen, ausgefüllte Tabelle hochladen.

Ablauf beim Hochladen:
  1. `lesen` liest die Datei (feste Positionen der Notentabelle, siehe noten.notentabelle) in ein JSON-fähiges dict.
  2. `pruefen` vergleicht sie mit dem Unterricht: Klasse (muss stimmen), Namen (nur gefundene Schüler:innen werden
     übernommen), Noten (müssen gültig sein), Notensperre, Ordner. Ergebnis ist eine Vorschau; nichts wird gespeichert.
  3. `uebernehmen` speichert nach Bestätigung: je Spalte mit Noten ein Leistungsnachweis (gleicher Titel im Zielordner
     → wird aktualisiert, sonst neu angelegt), Noten über dieselbe Prüfung wie die Schnelleingabe.
Leere Zellen löschen keine vorhandenen Noten.
"""
import io
import re
import unicodedata
from datetime import date, datetime
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _, ngettext

from . import eingabe as E
from . import notentabelle as T
from .berechnung import Baum
from .models import KAUFMAENNISCH, Bewertungsordner, Leistungsnachweis, Note, Unterricht

GROESSE_MAX = 5 * 1024 * 1024
BEREICHE = ("ka", "somi")
NEU = {"ka": "Klassenarbeiten", "somi": "Sonstige Mitarbeit"}
MUSTER_KA = re.compile(r"schrift|klassenarbeit|klausur|arbeiten|test")
MUSTER_SOMI = re.compile(r"sonst|mitarbeit|somi|mündlich|muendlich|mündl")


class ImportFehler(ValueError):
    pass


def norm(text):
    """Vergleichsform von Namen und Klassen: Unicode NFC, ohne Leerzeichen, ohne Groß-/Kleinschreibung."""
    t = unicodedata.normalize("NFC", str(text or "")).casefold()
    return re.sub(r"\s+", "", t)


def nur_sek1(u):
    return not u.skala.hoeher_ist_besser


# ---------------------------------------------------------------- Ordner

def bereichsordner(u, baum=None):
    """Vorschlag für die Zielordner {ka: Ordner|None, somi: Ordner|None} nach den Namen der obersten Ordner."""
    wurzeln = (baum or Baum(u)).wurzeln()
    ka = next((o for o in wurzeln if MUSTER_KA.search(o.name.casefold())), None)
    somi = next((o for o in wurzeln if MUSTER_SOMI.search(o.name.casefold()) and o != ka), None)
    rest = [o for o in wurzeln if o not in (ka, somi)]
    if ka is None and rest:
        ka = rest.pop(0)
    if somi is None and rest:
        somi = rest.pop(0)
    return {"ka": ka, "somi": somi}


def _teilbaum_ids(baum, ordner):
    ids, offen = [], [ordner]
    while offen:
        o = offen.pop()
        ids.append(o.pk)
        offen.extend(baum.kinder[o.pk])
    return ids


def _nachweise_im_teilbaum(baum, ordner):
    ids = set(_teilbaum_ids(baum, ordner))
    return sorted((ln for ln in baum.nachweise if ln.ordner_id in ids), key=lambda ln: (ln.datum, ln.titel, ln.pk))


# ---------------------------------------------------------------- Vorlage

def _text_fuer_tabelle(n):
    """Gespeicherte Note → Eingabe der Excel-Tabelle (Bezeichnung oder e/b/nb/u)."""
    if n.sonderstatus:
        return E.KUERZEL.get(n.sonderstatus, "")
    return n.stufe.bezeichnung if n.stufe_id else ""


def _spalten(u, schueler):
    zeile = {s.pk: i for i, s in enumerate(schueler)}
    baum = Baum(u)
    ordner = bereichsordner(u, baum)
    noten = {}
    for n in Note.objects.filter(leistungsnachweis__unterricht=u).select_related("stufe"):
        noten.setdefault(n.leistungsnachweis_id, []).append(n)
    spalten = {}
    for b in BEREICHE:
        liste = []
        if ordner[b] is not None:
            for ln in _nachweise_im_teilbaum(baum, ordner[b]):
                werte = {zeile[n.schueler_id]: _text_fuer_tabelle(n) for n in noten.get(ln.pk, []) if n.schueler_id in zeile}
                liste.append({"titel": ln.titel, "datum": ln.datum, "gewicht": float(ln.gewicht),
                              "noten": {k: v for k, v in werte.items() if v}})
        spalten[b] = liste
    gewichte = (float(ordner["ka"].gewicht) if ordner["ka"] else 50, float(ordner["somi"].gewicht) if ordner["somi"] else 50)
    return spalten, gewichte


def partner(u):
    """Der Unterricht des anderen Halbjahres (gleiche Gruppe, gleiches Fach, gleiches Schuljahr) oder None."""
    nummer = 2 if u.abschnitt.nummer == 1 else 1
    return (Unterricht.objects.filter(gruppe=u.gruppe, fach=u.fach, abschnitt__schuljahr=u.abschnitt.schuljahr, abschnitt__nummer=nummer)
            .select_related("abschnitt", "skala", "gruppe").first())


def vorlage_daten(u):
    """Vorbelegung der Notentabelle für einen Unterricht (Namen, vorhandene Leistungsnachweise und Noten, Gewichte)."""
    schueler = list(u.schueler()[:T.ANZAHL])
    skala = u.skala
    d = {
        "klasse": u.gruppe.name, "fach": u.fach.name, "lehrkraft": u.lehrkraft.person.anzeigename,
        "schuljahr": str(u.abschnitt.schuljahr.name if hasattr(u.abschnitt.schuljahr, "name") else u.abschnitt.schuljahr),
        "regel": "kaufmännisch" if skala.rundung == KAUFMAENNISCH else "zugunsten",
        "ersatz": float(skala.unentschuldigt_stufe.wert) if skala.unentschuldigt_stufe_id else None,
        "stufen": [(s.bezeichnung, float(s.wert)) for s in sorted(skala.stufen.all(), key=lambda s: s.wert)],
        "schueler": [(s.person.nachname, s.person.rufname or s.person.vorname) for s in schueler],
        "spalten": {}, "bereiche": {1: (50, 50), 2: (50, 50)},
    }
    anderer = partner(u)
    kurse = {u.abschnitt.nummer: u}
    if anderer is not None and anderer.skala_id == u.skala_id:
        kurse[anderer.abschnitt.nummer] = anderer
    for nr, k in kurse.items():
        d["spalten"][nr], d["bereiche"][nr] = _spalten(k, schueler)
    hj2 = kurse.get(2)
    if hj2 is not None and hj2.anteil_vorhalbjahr is not None:
        a = float(hj2.anteil_vorhalbjahr)
        d["gewicht_hj"] = (a, 100 - a)
        d["grundlage"] = "Zeugnisnote" if hj2.vorhalbjahr_basis == Unterricht.ZEUGNISNOTE else "Schnitt"
    else:
        a = float(settings.JAHRESNOTE_ANTEIL_HJ1) if u.gruppe.jahrgang in settings.JAHRESNOTE_JAHRGAENGE else 0.0
        d["gewicht_hj"] = (a, 100 - a)
    return d


def vorlage(u):
    return T.erstellen(vorlage_daten(u))


def dateiname(u):
    teile = ["Notentabelle", u.fach.kuerzel, u.gruppe.name, f"{u.abschnitt.nummer}Hj"]
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", "_".join(teile)) + ".xlsx"


# ---------------------------------------------------------------- Datei lesen

def _zelltext(wert):
    """Zellinhalt → Eingabetext (Zahlen mit Komma, ganze Zahlen ohne Nachkommastellen)."""
    if wert is None:
        return ""
    if isinstance(wert, bool):
        return ""
    if isinstance(wert, (int, float, Decimal)):
        d = Decimal(str(wert))
        if d == d.to_integral_value():
            return str(int(d))
        return format(d.normalize(), "f").replace(".", ",")
    return str(wert).strip()


def _datum(wert):
    if wert is None or wert == "":
        return None
    if isinstance(wert, datetime):
        return wert.date()
    if isinstance(wert, date):
        return wert
    text = str(wert).strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    raise ImportFehler(_("„%(text)s“ ist kein gültiges Datum.") % {"text": text})


def _gewicht(wert):
    if wert is None or str(wert).strip() == "":
        return None
    z = E.zahl_lesen(_zelltext(wert))
    if z is None or z < 0:
        raise ImportFehler(_("„%(text)s“ ist kein gültiges Gewicht.") % {"text": wert})
    return z


def lesen(datei):
    """Liest eine hochgeladene Notentabelle. Gibt ein JSON-fähiges dict zurück oder wirft ImportFehler."""
    from openpyxl import load_workbook

    if getattr(datei, "size", 0) > GROESSE_MAX:
        raise ImportFehler(_("Die Datei ist größer als 5 MB."))
    inhalt = datei.read() if hasattr(datei, "read") else datei
    try:
        wb = load_workbook(io.BytesIO(inhalt), data_only=True)
    except Exception:
        raise ImportFehler(_("Die Datei ließ sich nicht als Excel-Datei (.xlsx) öffnen."))
    fehlend = [n for n in ("Master", T.BLATT_HJ[1], T.BLATT_HJ[2]) if n not in wb.sheetnames]
    if fehlend:
        raise ImportFehler(_("Das ist keine Notentabelle von Schulnexus – es fehlt das Blatt „%(blatt)s“.") % {"blatt": fehlend[0]})
    ms = wb["Master"]
    tabelle = {k: _zelltext(ms[ref].value) for k, ref in T.MASTER.items()}
    tabelle["gewichte"] = {}
    for k, ref in (("hj1", "B12"), ("hj2", "B13"), ("ka1", "B17"), ("somi1", "B18"), ("ka2", "C17"), ("somi2", "C18")):
        try:
            g = _gewicht(ms[ref].value)
        except ImportFehler:
            g = None
        tabelle["gewichte"][k] = str(g) if g is not None else None
    hj1 = wb[T.BLATT_HJ[1]]
    namen = []
    for i in range(T.ANZAHL):
        r = T.ERSTE + i
        namen.append({"zeile": i, "nachname": _zelltext(hj1.cell(row=r, column=2).value),
                      "vorname": _zelltext(hj1.cell(row=r, column=3).value)})
    tabelle["namen"] = namen
    tabelle["blaetter"] = {}
    for nr, blatt in T.BLATT_HJ.items():
        ws = wb[blatt]
        spalten = []
        for sp in range(T.SP_K, T.SP_ENDE + 1):
            bereich = "ka" if sp < T.SP_S else "somi"
            noten = {}
            for i in range(T.ANZAHL):
                text = _zelltext(ws.cell(row=T.ERSTE + i, column=sp).value)
                if text:
                    noten[str(i)] = text
            if not noten:
                continue
            fehler = []
            try:
                datum = _datum(ws.cell(row=7, column=sp).value)
            except ImportFehler as f:
                datum, fehler = None, [str(f)]
            try:
                gewicht = _gewicht(ws.cell(row=8, column=sp).value)
            except ImportFehler as f:
                gewicht = None
                fehler.append(str(f))
            nummer = sp - T.SP_K + 1 if bereich == "ka" else sp - T.SP_S + 1
            titel = _zelltext(ws.cell(row=6, column=sp).value)[:100] or (f"KA {nummer}" if bereich == "ka" else f"SoMi {nummer}")
            spalten.append({"bereich": bereich, "nummer": nummer, "titel": titel,
                            "datum": datum.isoformat() if datum else None,
                            "gewicht": str(gewicht) if gewicht is not None else None, "noten": noten, "fehler": fehler})
        tabelle["blaetter"][str(nr)] = spalten
    return tabelle


# ---------------------------------------------------------------- Prüfen

def _schueler_index(u):
    index, doppelt = {}, set()
    for s in u.schueler():
        p = s.person
        for vorname in {p.vorname, p.rufname} - {"", None}:
            schluessel = (norm(p.nachname), norm(vorname))
            if schluessel in index and index[schluessel].pk != s.pk:
                doppelt.add(schluessel)
            index[schluessel] = s
    return index, doppelt


def _fach_passt(u, fach):
    if not fach:
        return True
    return norm(fach) in {norm(u.fach.name), norm(u.fach.kuerzel), norm(getattr(u.fach, "name_en", ""))} - {""}


def ordner_auswahl(u, baum=None):
    """[(wert, text)] für die Auswahl der Zielordner: alle Ordner des Unterrichts plus „neu anlegen“."""
    baum = baum or Baum(u)
    return [(str(o.pk), pfad) for o, _e, pfad in baum.in_reihenfolge()]


def _zielordner(u, wahl, baum):
    """wahl: {bereich: "pk" | "neu"} → {bereich: Ordner | None (= neu anlegen)}."""
    alle = {str(o.pk): o for o in baum.ordner}
    vorschlag = bereichsordner(u, baum)
    ziel = {}
    for b in BEREICHE:
        w = (wahl or {}).get(b)
        if w == "neu":
            ziel[b] = None
        elif w in alle:
            ziel[b] = alle[w]
        else:
            ziel[b] = vorschlag[b]
    return ziel


def _passender_nachweis(baum, ordner, titel):
    if ordner is None:
        return None
    ids = set(_teilbaum_ids(baum, ordner))
    return next((ln for ln in sorted(baum.nachweise, key=lambda x: (x.datum, x.pk))
                 if ln.ordner_id in ids and norm(ln.titel) == norm(titel)), None)


def _eingabe_fuer_skala(text, verzeichnis, stufen_nach_wert):
    """Excel-Eingabe → Text für die Schnelleingabe: Dezimalnoten (2,3) auf die Stufe mit diesem Wert abbilden."""
    t = E.normalisieren(text)
    if t in verzeichnis or t in E.STATUS:
        return text
    z = E.zahl_lesen(t)
    if z is not None:
        s = stufen_nach_wert.get(z.quantize(Decimal("0.01")))
        if s is not None:
            return s.bezeichnung
        raise ImportFehler(_("Die Dezimalnote %(text)s entspricht keiner Notenstufe der Skala (z. B. 2,3 = 2-).") % {"text": text})
    return text


def pruefen(u, tabelle, wahl=None):
    """Vorschau ohne zu speichern. Ergebnis: dict mit fehler (blockierend), warnungen, spalten, zeilen, zuordnung."""
    from .sperre import gesperrte_schueler

    nr = u.abschnitt.nummer
    fehler, warnungen = [], []
    if not nur_sek1(u):
        fehler.append(_("Die Notentabelle ist für Noten 1–6 (Sek I) gedacht; dieser Unterricht verwendet Punkte."))
    if norm(tabelle.get("klasse")) != norm(u.gruppe.name):
        fehler.append(_("Die Klasse in der Datei („%(datei)s“) passt nicht zu diesem Unterricht („%(kurs)s“). "
                        "Bitte im Blatt „Master“ die Klasse eintragen oder die Datei beim richtigen Unterricht hochladen.")
                      % {"datei": tabelle.get("klasse") or "–", "kurs": u.gruppe.name})
    if not _fach_passt(u, tabelle.get("fach")):
        warnungen.append(_("Das Fach in der Datei („%(datei)s“) weicht vom Unterricht ab („%(kurs)s“).")
                         % {"datei": tabelle.get("fach"), "kurs": u.fach.name})
    sj = str(getattr(u.abschnitt.schuljahr, "name", u.abschnitt.schuljahr))
    if tabelle.get("schuljahr") and norm(tabelle["schuljahr"]) != norm(sj):
        warnungen.append(_("Das Schuljahr in der Datei („%(datei)s“) weicht ab („%(kurs)s“).") % {"datei": tabelle["schuljahr"], "kurs": sj})

    # Namen
    index, doppelt = _schueler_index(u)
    alle_ids = {s.pk for s in index.values()}
    gesperrt = gesperrte_schueler(u, list(alle_ids)) if alle_ids else set()
    zeilen, zuordnung, gefunden = [], {}, set()
    for z in tabelle.get("namen", []):
        if not (z["nachname"] or z["vorname"]):
            continue
        name = f"{z['nachname']}, {z['vorname']}"
        schluessel = (norm(z["nachname"]), norm(z["vorname"]))
        s = index.get(schluessel)
        if schluessel in doppelt:
            zeilen.append({"zeile": z["zeile"] + 1, "name": name, "status": "doppelt", "text": _("mehrdeutig – nicht übernommen")})
        elif s is None:
            zeilen.append({"zeile": z["zeile"] + 1, "name": name, "status": "fehlt",
                           "text": _("nicht in diesem Unterricht gefunden – nicht übernommen")})
        elif s.pk in gefunden:
            zeilen.append({"zeile": z["zeile"] + 1, "name": name, "status": "doppelt", "text": _("steht mehrfach in der Datei – nur die erste Zeile zählt")})
        elif s.pk in gesperrt:
            zeilen.append({"zeile": z["zeile"] + 1, "name": name, "status": "gesperrt", "text": _("Noten gesperrt – nicht übernommen")})
            gefunden.add(s.pk)
        else:
            zeilen.append({"zeile": z["zeile"] + 1, "name": name, "status": "ok", "text": str(s.person), "schueler": s.pk})
            zuordnung[str(z["zeile"])] = s.pk
            gefunden.add(s.pk)
    if not zuordnung and not fehler:
        fehler.append(_("Keine Schülerin und kein Schüler der Datei wurde in diesem Unterricht gefunden (Nachname und Vorname müssen übereinstimmen)."))
    ohne = sorted((s for s in {x.pk: x for x in index.values()}.values() if s.pk not in gefunden), key=lambda s: (s.person.nachname, s.person.vorname))

    # Spalten
    baum = Baum(u)
    ziel = _zielordner(u, wahl, baum)
    verzeichnis = E.stufen_verzeichnis(u.skala)
    stufen_nach_wert = {s.wert.quantize(Decimal("0.01")): s for s in u.skala.stufen.all()}
    a = u.abschnitt
    spalten = []
    for sp in tabelle.get("blaetter", {}).get(str(nr), []):
        info = {"bereich": sp["bereich"], "titel": sp["titel"], "datum": sp["datum"], "gewicht": sp["gewicht"],
                "datum_anzeige": date.fromisoformat(sp["datum"]).strftime("%d.%m.%Y") if sp["datum"] else "",
                "gewicht_anzeige": E._zahl(Decimal(sp["gewicht"])) if sp["gewicht"] is not None else "1",
                "fehler": list(sp.get("fehler", [])), "zellen": [], "aktion": "neu", "neu": 0, "geaendert": 0, "gleich": 0,
                "ignoriert": 0}
        ordner = ziel[sp["bereich"]]
        info["ordner"] = ordner.name if ordner else NEU[sp["bereich"]] + " " + _("(neu)")
        ln = _passender_nachweis(baum, ordner, sp["titel"])
        if ln is not None:
            info["aktion"] = "aktualisieren"
            info["ln"] = ln.pk
            if ln.schluessel_id:
                info["aktion"] = "uebersprungen"
        if sp["datum"]:
            d = date.fromisoformat(sp["datum"])
            if not (a.beginn <= d <= a.ende):
                info["fehler"].append(_("Das Datum %(datum)s liegt nicht im Halbjahr (%(von)s bis %(bis)s).") % {
                    "datum": d.strftime("%d.%m.%Y"), "von": a.beginn.strftime("%d.%m.%Y"), "bis": a.ende.strftime("%d.%m.%Y")})
        if sp["gewicht"] is not None and Decimal(sp["gewicht"]) == 0:
            info["fehler"].append(_("Gewicht 0 ist in Schulnexus nicht möglich – Spalte leeren oder ein Gewicht über 0 eintragen."))
        if info["aktion"] == "uebersprungen":
            # Notenschlüssel/BE: nur melden, wenn die Tabelle andere Noten enthält
            stand = {n.schueler_id: _text_fuer_tabelle(n) for n in Note.objects.filter(leistungsnachweis=ln).select_related("stufe")}
            abweichend = sum(1 for zeile, text in sp["noten"].items()
                             if zuordnung.get(zeile) and E.normalisieren(stand.get(zuordnung[zeile], "")) != E.normalisieren(text))
            if abweichend:
                warnungen.append(ngettext(
                    "„%(titel)s“ wird in Schulnexus mit Bewertungseinheiten und Notenschlüssel geführt; %(n)s abweichende Note "
                    "aus der Tabelle wird nicht übernommen.",
                    "„%(titel)s“ wird in Schulnexus mit Bewertungseinheiten und Notenschlüssel geführt; %(n)s abweichende Noten "
                    "aus der Tabelle werden nicht übernommen.", abweichend) % {"titel": ln.titel, "n": abweichend})
            spalten.append(info)
            continue
        bisher = {}
        if ln is not None:
            bisher = {n.schueler_id: E.anzeige(n) for n in Note.objects.filter(leistungsnachweis=ln).select_related("stufe", "leistungsnachweis")}
        for zeile, text in sp["noten"].items():
            s_pk = zuordnung.get(zeile)
            if s_pk is None:
                info["ignoriert"] += 1
                continue
            try:
                eintrag = _eingabe_fuer_skala(text, verzeichnis, stufen_nach_wert)
                dummy = Leistungsnachweis(gewicht=Decimal(1))
                E.deuten(eintrag, dummy, verzeichnis)
            except (ImportFehler, E.EingabeFehler) as f:
                info["fehler"].append(_("Zeile %(zeile)s: %(fehler)s") % {"zeile": int(zeile) + 1, "fehler": f})
                continue
            vorher = bisher.get(s_pk, "")
            if not vorher:
                info["neu"] += 1
            elif E.normalisieren(vorher) == E.normalisieren(eintrag):
                info["gleich"] += 1
            else:
                info["geaendert"] += 1
            info["zellen"].append([s_pk, eintrag])
        if info["fehler"]:
            fehler.extend(f"„{sp['titel']}“: {f}" for f in info["fehler"])
        spalten.append(info)
    if not spalten and not fehler:
        fehler.append(_("Im Blatt „%(blatt)s“ stehen keine Noten.") % {"blatt": T.BLATT_HJ[nr]})

    gew = tabelle.get("gewichte", {})
    datei_gewichte = {b: E._zahl(Decimal(gew[f"{b}{nr}"])) if gew.get(f"{b}{nr}") is not None else None for b in BEREICHE}
    kurs_gewichte = {b: (E._zahl(ziel[b].gewicht) if ziel[b] is not None and ziel[b].eltern_id is None else None) for b in BEREICHE}
    anteil = None
    if nr == 2 and gew.get("hj1") is not None and gew.get("hj2") is not None:
        summe = Decimal(gew["hj1"]) + Decimal(gew["hj2"])
        anteil = str((Decimal(gew["hj1"]) / summe * 100).quantize(Decimal("0.01")).normalize()) if summe else None
    return {"fehler": fehler, "warnungen": warnungen, "spalten": spalten, "zeilen": zeilen, "ohne": [str(s.person) for s in ohne],
            "ziel": {b: (str(ziel[b].pk) if ziel[b] else "neu") for b in BEREICHE},
            "datei_gewichte": datei_gewichte, "kurs_gewichte": kurs_gewichte,
            "anteil_datei": E._zahl(Decimal(anteil)) if anteil else None,
            "anteil_kurs": E._zahl(u.anteil_vorhalbjahr) if u.anteil_vorhalbjahr is not None else None,
            "anteil_wert": anteil,
            "summe": {k: sum(s[k] for s in spalten) for k in ("neu", "geaendert", "gleich", "ignoriert")}}


# ---------------------------------------------------------------- Übernehmen

@transaction.atomic
def uebernehmen(u, tabelle, wahl, gewichte_uebernehmen=False):
    """Speichert nach erneuter Prüfung. Gibt die Vorschau (mit Zählung) zurück; wirft ImportFehler bei Fehlern."""
    vorschau = pruefen(u, tabelle, wahl)
    if vorschau["fehler"]:
        raise ImportFehler(" ".join(vorschau["fehler"]))
    baum = Baum(u)
    ziel = _zielordner(u, wahl, baum)
    nr = u.abschnitt.nummer
    gew = tabelle.get("gewichte", {})
    for b in BEREICHE:
        if ziel[b] is None and any(s["bereich"] == b and s["aktion"] != "uebersprungen" for s in vorschau["spalten"]):
            g = Decimal(gew.get(f"{b}{nr}") or 50) or Decimal(50)
            ziel[b], _neu = Bewertungsordner.objects.get_or_create(unterricht=u, eltern=None, name=NEU[b], defaults={"gewicht": g})
    if gewichte_uebernehmen:
        for b in BEREICHE:
            g = gew.get(f"{b}{nr}")
            if ziel[b] is not None and ziel[b].eltern_id is None and g is not None and Decimal(g) > 0:
                ziel[b].gewicht = Decimal(g)
                ziel[b].save(update_fields=["gewicht"])
        if nr == 2 and vorschau["anteil_wert"] is not None:
            u.anteil_vorhalbjahr = Decimal(vorschau["anteil_wert"])
            u.save(update_fields=["anteil_vorhalbjahr"])
    from .sperre import gesperrte_schueler

    schueler = list(u.schueler())
    gesperrt = gesperrte_schueler(u, [s.pk for s in schueler])
    heute = timezone.localdate()
    standarddatum = min(max(heute, u.abschnitt.beginn), u.abschnitt.ende)
    for info in vorschau["spalten"]:
        if info["aktion"] == "uebersprungen" or not info["zellen"]:
            continue
        ordner = ziel[info["bereich"]]
        ln = Leistungsnachweis.objects.filter(pk=info.get("ln")).first() if info.get("ln") else None
        if ln is None:
            ln = Leistungsnachweis(ordner=ordner, titel=info["titel"], datum=standarddatum, gewicht=Decimal(1))
        kopf_gesperrt = bool(ln.pk and gesperrt and Note.objects.filter(leistungsnachweis=ln, schueler_id__in=gesperrt)
                             .exclude(stufe__isnull=True, sonderstatus="").exists())
        if not kopf_gesperrt:
            if info["datum"]:
                ln.datum = date.fromisoformat(info["datum"])
            if info["gewicht"] is not None:
                ln.gewicht = Decimal(info["gewicht"])
        ln.save()
        ln.notenzeilen_anlegen()
        # Kommentar und Einzelgewicht vorhandener Noten bleiben erhalten
        vorhanden = {n.schueler_id: n for n in Note.objects.filter(leistungsnachweis=ln)}
        eingaben = {}
        for s_pk, text in info["zellen"]:
            if s_pk in gesperrt:
                continue
            n = vorhanden.get(s_pk)
            eingaben[s_pk] = {"note": text, "kommentar": n.kommentar if n else "",
                              "gewicht": E._zahl(n.gewicht_individuell) if n else "",
                              "begruendung": n.gewicht_begruendung if n else ""}
        ergebnisse, fehler = E.pruefen(ln, eingaben, [s for s in schueler if s.pk in eingaben])
        if fehler:
            raise ImportFehler(" ".join(fehler.values()))
        E.speichern(ln, ergebnisse)
    return vorschau
