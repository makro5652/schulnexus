"""
Modulsicherung als ZIP-Datei und Wiederherstellung einzelner Module.

Aufbau einer Sicherung:
    manifest.json            Format, Programmversion, Zeitpunkt, je Modul Anzahl, Prüfsumme und Migrationsstand
    daten/<modul>.json       alle Einträge der Modelle des Moduls (Django-Serialisierung, Bezüge auf
                             Benutzerkonten, Rechte und Inhaltstypen über natürliche Schlüssel)
    dateien/<modell>/<feld>/<pfad>   hochgeladene Dateien (optional)

Wiederherstellen setzt ein Modul auf den Stand der Sicherung zurück: Einträge der Sicherung werden angelegt bzw.
überschrieben, Einträge, die es damals nicht gab, werden gelöscht (mit den davon abhängigen Daten, auch in anderen
Modulen). Vorher zeigt planen() die Auswirkungen; vor jeder Wiederherstellung entsteht automatisch eine Gesamtsicherung.
"""
import hashlib
import json
import shutil
import zipfile
from collections import Counter, defaultdict

from django.conf import settings
from django.core import serializers
from django.core.management.color import no_style
from django.db import IntegrityError, connection, transaction
from django.db.migrations.loader import MigrationLoader
from django.db.models import FileField, ProtectedError, RestrictedError
from django.db.models.deletion import Collector
from django.utils import timezone
from django.utils.translation import gettext as _

from config.version import VERSION
from portal import krypto

from .models import Protokoll, Sicherung
from .module import MODULE, NAMEN, SCHLUESSEL, ist_protokollmodell, modellname, modelle, modul_von

FORMAT = "schulverwaltung-modulsicherung"
FORMATVERSION = 1


class SicherungFehler(Exception):
    pass


def _apps(schluessel):
    return dict((m[0], m[2]) for m in MODULE)[schluessel]


def migrationsstand(schluessel):
    loader = MigrationLoader(None, ignore_no_migrations=True)
    return {app: sorted(name for _a, name in loader.graph.leaf_nodes(app)) for app in _apps(schluessel)}


def _sha(daten):
    return hashlib.sha256(daten).hexdigest()


def _dateifelder(model):
    return [f for f in model._meta.concrete_fields if isinstance(f, FileField)]


def _serialisieren(model, qs=None):
    qs = model._default_manager.order_by("pk") if qs is None else qs
    return json.loads(serializers.serialize("json", qs, use_natural_foreign_keys=True))


# ---------------------------------------------------------------- Sichern

def sicherung_erstellen(module, benutzer=None, art=Sicherung.MANUELL, mit_dateien=False, bemerkung="", dateien_fuer=()):
    """Legt eine ZIP-Datei mit den gewählten Modulen an und gibt den Sicherung-Eintrag zurück."""
    module = [m for m in SCHLUESSEL if m in module]
    if not module:
        raise SicherungFehler(_("Bitte mindestens ein Modul wählen."))
    ordner = settings.MODUL_SICHERUNGEN
    ordner.mkdir(parents=True, exist_ok=True)
    zeit = timezone.localtime()
    teil = "alle" if len(module) == len(SCHLUESSEL) else "-".join(module)
    name = f"sicherung-{zeit:%Y%m%d-%H%M%S}-{teil}"[:150]
    endung = ".zip.enc" if krypto.aktiv() else ".zip"
    nr, datei = 1, f"{name}{endung}"
    while (ordner / datei).exists() or Sicherung.objects.filter(datei=datei).exists():
        nr += 1
        datei = f"{name}-{nr}{endung}"
    manifest = {"format": FORMAT, "formatversion": FORMATVERSION, "version": VERSION, "erstellt": zeit.isoformat(),
                "erstellt_von": getattr(benutzer, "username", ""), "schule": settings.SCHULNAME, "module": {},
                "dateien": {"enthalten": bool(mit_dateien or dateien_fuer), "anzahl": 0}}
    anzahl_gesamt = {}
    zwischen = ordner / f".{datei}.teil"
    try:
        with zipfile.ZipFile(zwischen, "w", zipfile.ZIP_DEFLATED) as zf:
            for key in module:
                objekte, anzahl = [], {}
                for model in modelle(key):
                    liste = _serialisieren(model)
                    objekte += liste
                    anzahl[model._meta.label_lower] = len(liste)
                inhalt = json.dumps(objekte, ensure_ascii=False).encode("utf-8")
                zf.writestr(f"daten/{key}.json", inhalt)
                manifest["module"][key] = {"datei": f"daten/{key}.json", "sha256": _sha(inhalt), "anzahl": anzahl,
                                           "migrationen": migrationsstand(key)}
                anzahl_gesamt[key] = len(objekte)
                if mit_dateien or key in dateien_fuer:
                    manifest["dateien"]["anzahl"] += _dateien_schreiben(zf, key)
            zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        if krypto.aktiv():
            krypto.datei_verschluesseln(zwischen, ordner / datei)
        else:
            zwischen.rename(ordner / datei)
    finally:
        if zwischen.exists():
            zwischen.unlink()
    s = Sicherung.objects.create(datei=datei, art=art, module=module, anzahl=anzahl_gesamt,
                                 mit_dateien=manifest["dateien"]["enthalten"], groesse=(ordner / datei).stat().st_size,
                                 version=VERSION, bemerkung=bemerkung[:200], erstellt_von=benutzer)
    Protokoll.schreiben(benutzer, "sicherung", _("%(datei)s (%(art)s): %(module)s") % {
        "datei": datei, "art": s.get_art_display(), "module": ", ".join(str(NAMEN[m]) for m in module)})
    return s


def _dateien_schreiben(zf, key):
    n = 0
    for model in modelle(key):
        felder = _dateifelder(model)
        if not felder:
            continue
        for obj in model._default_manager.only("pk", *[f.name for f in felder]):
            for f in felder:
                name = getattr(obj, f.attname).name
                if not name or not f.storage.exists(name):
                    continue
                with f.storage.open(name, "rb") as quelle, zf.open(f"dateien/{model._meta.label_lower}/{f.name}/{name}", "w") as ziel:
                    shutil.copyfileobj(quelle, ziel, 1024 * 1024)
                n += 1
    return n


# ---------------------------------------------------------------- Lesen und prüfen

def _zip(pfad):
    """ZipFile einer (ggf. mit dem Serverschlüssel verschlüsselten) Sicherung."""
    try:
        return zipfile.ZipFile(krypto.ablage_temporaer(pfad))
    except krypto.KryptoFehler as f:
        raise SicherungFehler(str(f)) from None


def oeffnen(pfad):
    """Öffnet eine Sicherung und prüft Format und Prüfsummen. Gibt (ZipFile, Manifest) zurück."""
    try:
        zf = _zip(pfad)
        manifest = json.loads(zf.read("manifest.json"))
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        raise SicherungFehler(_("Die Datei ist keine gültige Sicherung der Schulverwaltung.")) from None
    if manifest.get("format") != FORMAT or manifest.get("formatversion", 0) > FORMATVERSION:
        zf.close()
        raise SicherungFehler(_("Die Datei ist keine gültige Sicherung der Schulverwaltung."))
    for key, info in manifest.get("module", {}).items():
        if key not in SCHLUESSEL:
            continue
        try:
            inhalt = zf.read(info["datei"])
        except KeyError:
            zf.close()
            raise SicherungFehler(_("In der Sicherung fehlt die Datei für %(modul)s.") % {"modul": NAMEN[key]}) from None
        if _sha(inhalt) != info.get("sha256"):
            zf.close()
            raise SicherungFehler(_("Die Sicherung ist beschädigt (Prüfsumme von %(modul)s stimmt nicht).") % {"modul": NAMEN[key]})
    return zf, manifest


def sicherung_hochladen(datei, benutzer, passwort=None):
    """
    Speichert eine hochgeladene Sicherung nach Prüfung. Angenommen werden unverschlüsselte ZIP-Dateien, mit Passwort
    verschlüsselte Downloads (Passwort nötig) und mit dem Serverschlüssel dieser Installation verschlüsselte Dateien.
    """
    ordner = settings.MODUL_SICHERUNGEN
    ordner.mkdir(parents=True, exist_ok=True)
    zeit = timezone.localtime()
    endung = ".zip.enc" if krypto.aktiv() else ".zip"
    name = f"hochgeladen-{zeit:%Y%m%d-%H%M%S}{endung}"
    nr = 1
    while (ordner / name).exists():
        nr += 1
        name = f"hochgeladen-{zeit:%Y%m%d-%H%M%S}-{nr}{endung}"
    ziel = ordner / name
    roh, klar = ordner / f".{name}.hoch", ordner / f".{name}.klar"
    try:
        with open(roh, "wb") as f:
            for stueck in datei.chunks():
                f.write(stueck)
        try:
            krypto.datei_entschluesseln(roh, klar, passwort=passwort or None)
        except krypto.KryptoFehler as f:
            raise SicherungFehler(str(f)) from None
        zf, manifest = oeffnen(klar)
        zf.close()
        if krypto.aktiv():
            krypto.datei_verschluesseln(klar, ziel)
        else:
            klar.rename(ziel)
    finally:
        for p in (roh, klar):
            if p.exists():
                p.unlink()
    module = [k for k in SCHLUESSEL if k in manifest["module"]]
    anzahl = {k: sum(manifest["module"][k]["anzahl"].values()) for k in module}
    s = Sicherung.objects.create(datei=name, art=Sicherung.HOCHGELADEN, module=module, anzahl=anzahl,
                                 mit_dateien=manifest.get("dateien", {}).get("enthalten", False), groesse=ziel.stat().st_size,
                                 version=manifest.get("version", ""), erstellt_von=benutzer,
                                 bemerkung=(_("erstellt %(zeit)s von %(wer)s") % {"zeit": manifest.get("erstellt", "")[:16].replace("T", " "),
                                                                                    "wer": manifest.get("erstellt_von") or "?"})[:200])
    Protokoll.schreiben(benutzer, "hochgeladen", f"{name} ({datei.name})")
    return s


# ---------------------------------------------------------------- Planen (Vorschau)

def _natuerlicher_schluessel(label, felder):
    if label == "auth.user":
        return (felder.get("username"),)
    if label == "auth.group":
        return (felder.get("name"),)
    return None


def planen(pfad, module, benutzer=None):
    """
    Ermittelt, was eine Wiederherstellung der gewählten Module ändern würde, ohne etwas zu ändern.
    Ergebnis: dict mit „module“ (je Modul Zählung), „kaskade“ (betroffene Daten anderer Module), „blockiert“ (Gründe),
    „hinweise“ sowie intern „_daten“ (bereinigte Objekte) und „_loeschen“ (Modell → Primärschlüssel).
    """
    zf, manifest = oeffnen(pfad)
    try:
        module = [m for m in SCHLUESSEL if m in module and m in manifest["module"]]
        if not module:
            raise SicherungFehler(_("Die gewählten Module sind in dieser Sicherung nicht enthalten."))
        daten = {key: json.loads(zf.read(manifest["module"][key]["datei"])) for key in module}
    finally:
        zf.close()

    plan = {"module": [], "kaskade": [], "blockiert": [], "hinweise": [], "_daten": {}, "_loeschen": {}}
    modelle_nach_label = {m._meta.label_lower: m for key in module for m in modelle(key)}

    # Programmstand: nur gleicher Migrationsstand ist sicher wiederherstellbar
    for key in module:
        if manifest["module"][key].get("migrationen") != migrationsstand(key):
            plan["blockiert"].append(_("%(modul)s: Die Sicherung stammt von einem anderen Programmstand (Version %(v)s). "
                                       "Bitte mit derselben Version wiederherstellen.") % {"modul": NAMEN[key], "v": manifest.get("version", "?")})

    # Bezüge auf Daten außerhalb der wiederhergestellten Module prüfen
    pks_in_sicherung = defaultdict(set)
    nat_in_sicherung = defaultdict(set)
    for key in module:
        for o in daten[key]:
            pks_in_sicherung[o["model"]].add(o["pk"])
            nk = _natuerlicher_schluessel(o["model"], o["fields"])
            if nk:
                nat_in_sicherung[o["model"]].add(nk)
    unbekannt = Counter()
    vorkommen = []          # (objekt, feldname, wert, feld, m2m)
    zu_pruefen = defaultdict(set)
    for key in module:
        for o in daten[key]:
            model = modelle_nach_label.get(o["model"])
            if model is None:
                unbekannt[o["model"]] += 1
                continue
            for f in model._meta.concrete_fields:
                if not f.is_relation or f.name not in o["fields"]:
                    continue
                if not getattr(f, "db_constraint", True):      # z. B. Änderungsprotokolle: Bezug darf ins Leere zeigen
                    continue
                wert = o["fields"][f.name]
                if wert is None:
                    continue
                vorkommen.append((o, f, wert, False))
                zu_pruefen[f.related_model].add(tuple(wert) if isinstance(wert, list) else wert)
            for f in model._meta.many_to_many:
                for wert in o["fields"].get(f.name) or []:
                    vorkommen.append((o, f, wert, True))
                    zu_pruefen[f.related_model].add(tuple(wert) if isinstance(wert, list) else wert)
    vorhanden = {}
    for ziel, werte in zu_pruefen.items():
        label = ziel._meta.label_lower
        nat = {w for w in werte if isinstance(w, tuple)}
        pks = werte - nat
        da = set()
        if label in modelle_nach_label:
            da |= pks & pks_in_sicherung[label]
            da |= nat & nat_in_sicherung[label]
            pks -= da
            nat -= da
        if pks:
            da |= set(ziel._default_manager.filter(pk__in=pks).values_list("pk", flat=True))
        for w in nat:
            try:
                ziel._default_manager.get_by_natural_key(*w)
                da.add(w)
            except ziel.DoesNotExist:
                pass
        vorhanden[ziel] = da
    fehlend_geloest, fehlend_block = Counter(), Counter()
    for o, f, wert, m2m in vorkommen:
        schluessel = tuple(wert) if isinstance(wert, list) else wert
        if schluessel in vorhanden[f.related_model]:
            continue
        beschreibung = f"{modellname(modelle_nach_label[o['model']])} → {modellname(f.related_model)}"
        if m2m:
            o["fields"][f.name] = [w for w in o["fields"][f.name] if (tuple(w) if isinstance(w, list) else w) != schluessel]
            fehlend_geloest[beschreibung] += 1
        elif f.null:
            o["fields"][f.name] = None
            fehlend_geloest[beschreibung] += 1
        else:
            fehlend_block[beschreibung] += 1
    for b, n in fehlend_block.items():
        plan["blockiert"].append(_("%(n)d Verweise %(b)s fehlen im System – bitte zuerst das zugehörige Modul wiederherstellen "
                                   "oder beide gemeinsam.") % {"n": n, "b": b})
    for b, n in fehlend_geloest.items():
        plan["hinweise"].append(_("%(n)d Verweise %(b)s gibt es nicht mehr; sie werden leer gelassen.") % {"n": n, "b": b})
    for label, n in unbekannt.items():
        plan["hinweise"].append(_("%(n)d Einträge des nicht mehr vorhandenen Modells %(m)s werden übersprungen.") % {"n": n, "m": label})

    # Vergleich mit dem aktuellen Stand
    loeschen = {}
    for key in module:
        nach_modell = defaultdict(dict)
        for o in daten[key]:
            nach_modell[o["model"]][o["pk"]] = o["fields"]
        zeile = {"schluessel": key, "name": NAMEN[key], "neu": 0, "geaendert": 0, "gleich": 0, "loeschen": 0, "modelle": []}
        for model in modelle(key):
            label = model._meta.label_lower
            gesichert = nach_modell.get(label, {})
            aktuell = {o["pk"]: o["fields"] for o in _serialisieren(model)}
            neu = len(gesichert.keys() - aktuell.keys())
            weg = set(aktuell.keys() - gesichert.keys())
            if label == "auth.user" and benutzer is not None and benutzer.pk in weg:
                weg.discard(benutzer.pk)
                plan["hinweise"].append(_("Ihr eigenes Benutzerkonto ist nicht in der Sicherung enthalten und bleibt erhalten."))
            geaendert = sum(1 for pk in gesichert.keys() & aktuell.keys() if gesichert[pk] != aktuell[pk])
            gleich = len(gesichert.keys() & aktuell.keys()) - geaendert
            if weg:
                loeschen[model] = weg
            zeile["neu"] += neu
            zeile["geaendert"] += geaendert
            zeile["gleich"] += gleich
            zeile["loeschen"] += len(weg)
            if neu or geaendert or weg:
                zeile["modelle"].append({"name": modellname(model), "neu": neu, "geaendert": geaendert,
                                         "loeschen": len(weg), "protokoll": ist_protokollmodell(model)})
        plan["module"].append(zeile)

    # Folgen der Löschungen in anderen Modulen (CASCADE, SET_NULL) und geschützte Einträge
    kaskade = Counter()
    collector = Collector(using="default")
    try:
        for model, pks in loeschen.items():
            collector.collect(list(model._default_manager.filter(pk__in=pks)))
    except (ProtectedError, RestrictedError) as fehler:
        geschuetzt = {modellname(type(o)) for o in getattr(fehler, "protected_objects", None) or getattr(fehler, "restricted_objects", [])}
        plan["blockiert"].append(_("Einige Einträge können nicht gelöscht werden, weil andere Daten sie benötigen (%(was)s). "
                                   "Bitte die abhängigen Module mit wiederherstellen.") % {"was": ", ".join(sorted(geschuetzt))})
    else:
        for model, objekte in collector.data.items():
            if model._meta.label_lower not in modelle_nach_label:
                kaskade[model] += len(objekte)
        for qs in collector.fast_deletes:
            if qs.model._meta.label_lower not in modelle_nach_label:
                kaskade[qs.model] += qs.count()
    for model, n in sorted(kaskade.items(), key=lambda e: (str(modul_von(e[0]) or ""), modellname(e[0]))):
        if n:
            plan["kaskade"].append({"modul": NAMEN.get(modul_von(model), "–"), "name": modellname(model), "anzahl": n,
                                    "protokoll": ist_protokollmodell(model)})
    plan["_daten"] = daten
    plan["_loeschen"] = loeschen
    plan["_modelle"] = [m for key in module for m in modelle(key)]
    plan["gewaehlt"] = module
    return plan


# ---------------------------------------------------------------- Wiederherstellen

def wiederherstellen(sicherung, module, benutzer):
    """Stellt die gewählten Module aus der Sicherung wieder her. Gibt (Plan, Sicherung vorher) zurück."""
    plan = planen(sicherung.pfad, module, benutzer)
    if plan["blockiert"]:
        raise SicherungFehler(" ".join(str(b) for b in plan["blockiert"]))
    gewaehlt = plan["gewaehlt"]
    vorher = sicherung_erstellen(SCHLUESSEL, benutzer, art=Sicherung.VOR_WIEDERHERSTELLUNG, dateien_fuer=gewaehlt,
                                 bemerkung=_("vor Wiederherstellung aus %(datei)s") % {"datei": sicherung.datei})
    try:
        with transaction.atomic():
            # 1. Einträge löschen, die es zum Zeitpunkt der Sicherung nicht gab (vermeidet Konflikte bei eindeutigen Feldern)
            for model, pks in plan["_loeschen"].items():
                model._default_manager.filter(pk__in=pks).delete()
            # 2. Stand der Sicherung schreiben (Fremdschlüssel werden in PostgreSQL erst am Ende geprüft)
            objekte = [o for key in gewaehlt for o in plan["_daten"][key]]
            spaeter = []
            for d in serializers.deserialize("python", objekte, ignorenonexistent=True, handle_forward_references=True):
                d.save()
                if d.deferred_fields:
                    spaeter.append(d)
            for d in spaeter:
                d.save_deferred_fields()
            # 3. Zähler der Primärschlüssel anpassen
            befehle = connection.ops.sequence_reset_sql(no_style(), plan["_modelle"])
            with connection.cursor() as cursor:
                for befehl in befehle:
                    cursor.execute(befehl)
    except IntegrityError as fehler:
        raise SicherungFehler(_("Die Wiederherstellung wurde abgebrochen, es wurde nichts verändert: %(f)s") % {"f": fehler}) from None
    n_dateien = _dateien_wiederherstellen(sicherung.pfad, gewaehlt)
    Protokoll.schreiben(benutzer, "wiederhergestellt", _("%(module)s aus %(datei)s; vorher gesichert in %(vorher)s; %(n)d Dateien ergänzt") % {
        "module": ", ".join(str(NAMEN[m]) for m in gewaehlt), "datei": sicherung.datei, "vorher": vorher.datei, "n": n_dateien})
    return plan, vorher


def _dateien_wiederherstellen(pfad, module):
    """Legt fehlende Dateien der wiederhergestellten Module wieder an (vorhandene bleiben unverändert)."""
    felder = {}
    for key in module:
        for model in modelle(key):
            for f in _dateifelder(model):
                felder[f"{model._meta.label_lower}/{f.name}/"] = f
    n = 0
    with _zip(pfad) as zf:
        for eintrag in zf.namelist():
            if not eintrag.startswith("dateien/") or eintrag.endswith("/"):
                continue
            rest = eintrag[len("dateien/"):]
            for praefix, f in felder.items():
                if rest.startswith(praefix):
                    name = rest[len(praefix):]
                    if ".." in name.split("/") or name.startswith("/"):
                        break
                    if not f.storage.exists(name):
                        with zf.open(eintrag) as quelle:
                            from django.core.files import File

                            gespeichert = f.storage.save(name, File(quelle, name=name.rsplit("/", 1)[-1]))
                        n += gespeichert == name
                    break
    return n


def sicherung_loeschen(sicherung, benutzer):
    if sicherung.pfad.exists():
        sicherung.pfad.unlink()
    Protokoll.schreiben(benutzer, "geloescht", sicherung.datei)
    sicherung.delete()
