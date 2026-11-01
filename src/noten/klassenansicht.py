"""
Noten nach Klasse (ab 0.4.12.0): Halbjahr → Klasse → Kurs bzw. Lerngruppe (mit Lehrkraft) → Notentabelle.

Die Notentabelle zeigt alle Leistungsnachweise des Kurses als Spalten und lässt sich direkt bearbeiten (gleiche
Schnelleingabe wie „Noten eintragen“: 2+, 2, 2-, e, u, b, nb). Gespeichert werden nur geänderte Zellen; hat jemand
anderes eine Zelle inzwischen geändert, wird diese Zelle nicht überschrieben (Hinweis). Leistungsnachweise mit
Notenschlüssel (Bewertungseinheiten) und gesperrte Schüler:innen sind nur lesbar.
Von hier aus: neuer Leistungsnachweis, Bewertungsstruktur, Excel-Notentabelle herunterladen und hochladen.

Ab 0.4.17.0 geht es schneller: „+ Klassenarbeit“ bzw. „+ SoMi-Note“ legt direkt eine neue Spalte an (bis zur Höchstzahl der
Notenregel), das Gewicht jeder Spalte steht im Tabellenkopf, und die Zeugnisnote lässt sich in der letzten Spalte festsetzen
(„automatisch“ = gerundete Note aus den Einzelnoten).
"""
from decimal import Decimal, InvalidOperation

from collections import defaultdict

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.utils.translation import gettext as _, ngettext

from portal.rechte import darf_unterricht_sehen
from zeugnisse import rechte as zeugnisrechte
from stammdaten.models import Abschnitt, Gruppe, Mitgliedschaft, Schuljahr

from . import eingabe as E
from . import notenimport as I
from . import rechte
from . import zeugnisnoten as Z
from .ansichten import gewicht_text
from .berechnung import Baum, Vorhalbjahr, vorschlagsnote
from .models import PROZENT, Bewertungsordner, Leistungsnachweis, Note, Unterricht


def _abschnitte():
    sj = Schuljahr.aktuelles()
    if sj is None:
        return [], None
    liste = list(Abschnitt.objects.filter(schuljahr=sj).select_related("schuljahr").order_by("nummer"))
    heute = timezone.localdate()
    laufend = next((a for a in liste if a.beginn <= heute <= a.ende), None) or (liste[0] if liste else None)
    return liste, laufend


def klassen_und_kurse(user, abschnitt):
    """{Stammklasse: [Unterricht, …]} der für `user` sichtbaren Kurse im Halbjahr. Lerngruppen/Kurse erscheinen bei jeder
    Stammklasse, aus der sie Schüler:innen haben."""
    kurse = [u for u in Unterricht.objects.filter(abschnitt=abschnitt)
             .select_related("fach__fachbereich__leitung", "fach__fachbereich__leitung2", "gruppe__leitung", "gruppe__leitung2",
                             "lehrkraft__person", "skala", "abschnitt__schuljahr")
             if darf_unterricht_sehen(user, u)]
    stichtag = min(max(timezone.localdate(), abschnitt.beginn), abschnitt.ende)
    stammklasse_von = dict(Mitgliedschaft.objects.aktiv(stichtag)
                           .filter(gruppe__typ=Gruppe.STAMMKLASSE, gruppe__schuljahr=abschnitt.schuljahr)
                           .values_list("schueler_id", "gruppe_id"))
    mitglieder = defaultdict(set)
    for g, s in Mitgliedschaft.objects.aktiv(stichtag).filter(gruppe__in={u.gruppe_id for u in kurse}).values_list("gruppe_id", "schueler_id"):
        mitglieder[g].add(s)
    klassen = {g.pk: g for g in Gruppe.objects.filter(typ=Gruppe.STAMMKLASSE, schuljahr=abschnitt.schuljahr)}
    ergebnis = defaultdict(list)
    for u in kurse:
        if u.gruppe.typ == Gruppe.STAMMKLASSE:
            ziele = {u.gruppe_id}
        else:
            ziele = {stammklasse_von[s] for s in mitglieder[u.gruppe_id] if s in stammklasse_von}
        for k in ziele:
            if k in klassen:
                ergebnis[klassen[k]].append(u)
    for liste in ergebnis.values():
        liste.sort(key=lambda u: (u.gruppe.typ != Gruppe.STAMMKLASSE, u.fach.reihenfolge, u.fach.name, u.gruppe.name))
    return dict(sorted(ergebnis.items(), key=lambda kv: (kv[0].jahrgang or 99, kv[0].name)))


# ---------------------------------------------------------------- Notentabelle eines Kurses

def notentabelle_daten(request, u, eingaben=None, fehler=None):
    """Spalten und Zeilen der bearbeitbaren Notentabelle."""
    from .sperre import gesperrte_schueler

    baum = Baum(u)
    art_von = {o.pk: o.gewichtsart for o in baum.ordner}
    spalten = [{"ln": ln, "pfad": pfad, "gewicht": gewicht_text(ln.gewicht, art_von.get(ln.ordner_id)),
                "gewicht_zahl": format(ln.gewicht.normalize(), "f").replace(".", ","), "prozent": art_von.get(ln.ordner_id) == "prozent",
                "nur_lesen": bool(ln.schluessel_id)} for ln, pfad in baum.nachweise_in_reihenfolge()]
    gruppen = []
    for sp in spalten:
        if gruppen and gruppen[-1]["pfad"] == sp["pfad"]:
            gruppen[-1]["breite"] += 1
        else:
            gruppen.append({"pfad": sp["pfad"], "breite": 1})
    schueler = list(u.schueler())
    gesperrt = gesperrte_schueler(u, [s.pk for s in schueler])
    noten = defaultdict(dict)
    noten_liste = defaultdict(list)
    for n in Note.objects.filter(leistungsnachweis__unterricht=u).select_related("stufe", "leistungsnachweis"):
        noten[n.schueler_id][n.leistungsnachweis_id] = n
        noten_liste[n.schueler_id].append(n)
    jahr = Vorhalbjahr(u) if u.mit_jahresnote else False
    darf = rechte.darf_noten_eintragen(request.user, u)
    stammklasse = {}
    if u.gruppe.typ != Gruppe.STAMMKLASSE:
        stichtag = min(max(timezone.localdate(), u.abschnitt.beginn), u.abschnitt.ende)
        stammklasse = dict(Mitgliedschaft.objects.aktiv(stichtag)
                           .filter(gruppe__typ=Gruppe.STAMMKLASSE, gruppe__schuljahr=u.abschnitt.schuljahr,
                                   schueler__in=[s.pk for s in schueler]).values_list("schueler_id", "gruppe__name"))
    zeugnis = Z.aktuell(u)
    darf_zn = zeugnisrechte.darf_zeugnisnote_setzen(request.user, u)
    zn_sperre = Z.gesperrt(u, [s.pk for s in schueler]) if darf_zn else set()
    zn_optionen = [(str(w), st.bezeichnung) for w, st in sorted(Z.ganze_stufen(u.skala).items())]
    zeilen = []
    for s in schueler:
        zellen = []
        for sp in spalten:
            n = noten[s.pk].get(sp["ln"].pk)
            wert = E.anzeige(n) if n else ""
            name = f"n_{sp['ln'].pk}_{s.pk}"
            # Notenschlüssel: statt der BE die daraus berechnete Note zeigen (BE als Tooltip)
            lesen = (n.stufe.bezeichnung if n.stufe_id else E.anzeige(n)) if n and sp["nur_lesen"] else wert
            zellen.append({
                "name": name, "orig": wert, "anzeige": lesen, "be": E._zahl(n.erreichte_be) if n and n.erreichte_be is not None else "",
                "wert": (eingaben or {}).get(name, wert),
                "fehler": (fehler or {}).get(name),
                "bearbeitbar": darf and not sp["nur_lesen"] and s.pk not in gesperrt,
                "note": n,
            })
        zn = zeugnis.get(s.pk)
        fest = zn is not None and zn.quelle != Z.AUTO
        zeilen.append({"s": s, "gesperrt": s.pk in gesperrt, "zellen": zellen, "klasse": stammklasse.get(s.pk, ""),
                       "zn_wahl": darf_zn and s.pk not in zn_sperre, "zn_wert": Z.formwert(zn) if fest else "",
                       "zn_auto": Z.anzeige(zn) if zn is not None and not fest else "",
                       "zn_fehler": (fehler or {}).get(f"zk_{s.pk}"), "zn_eingabe": (eingaben or {}).get(f"zk_{s.pk}"),
                       "vorschlag": vorschlagsnote(u, s, noten_liste[s.pk], baum, jahr=jahr),
                       "zeugnisnote": Z.anzeige(zn), "zeugnis_quelle": zn.get_quelle_display() if zn and zn.quelle and zn.quelle != Z.AUTO else "",
                       "zeugnis_quelle_art": zn.quelle if zn else ""})
    haupt = [o.name for o in baum.wurzeln()]
    for z in zeilen:
        nach_ordner = {e.ordner_id: e.schnitt for e in z["vorschlag"].hauptordner}
        z["bereiche"] = [nach_ordner.get(o.pk) for o in baum.wurzeln()]
        z["ganz"] = u.skala.ganz_runden(z["vorschlag"].schnitt) if z["vorschlag"].schnitt is not None else None
    quellen = sorted({z["zeugnis_quelle"] for z in zeilen if z["zeugnis_quelle"]})
    gewichte_offen = darf and not gesperrt
    for sp in spalten:
        sp["gewicht_bearbeitbar"] = gewichte_offen
    return {"spalten": spalten, "gruppen": gruppen, "zeilen": zeilen, "darf_eintragen": darf, "gesperrt_anzahl": len(gesperrt),
            "neue_spalten": neue_spalten(baum) if darf else [], "darf_zn": darf_zn, "zn_optionen": zn_optionen,
            "zeugnis_quellen": quellen, "zeugnis_vorhanden": any(z["zeugnisnote"] for z in zeilen),
            "bereiche": haupt, "jahresnote": bool(jahr),
            "gemischt": bool(stammklasse) and len(set(stammklasse.values())) > 1,
            "erlaubt": [st.bezeichnung for st in u.skala.stufen.all()], "ordner_fehlen": not baum.ordner}


def _art(wurzel):
    """Bezeichnung einer neuen Spalte im obersten Ordner: Klassenarbeit, Klausur, SoMi-Note oder der Ordnername."""
    name = wurzel.name.strip().lower()
    if name.startswith("klassenarbeit"):
        return _("Klassenarbeit")
    if name.startswith("klausur") or wurzel.vorgegeben == Bewertungsordner.KLAUSUR:
        return _("Klausur")
    if wurzel.vorgegeben == Bewertungsordner.MITARBEIT or name.startswith("sonstige"):
        return _("SoMi-Note")
    return wurzel.name


def neue_spalten(baum):
    """Je oberstem Ordner ein Knopf „+ …“: Ziel ist der zuletzt angelegte Unterordner (bzw. der Ordner selbst)."""
    def letzter(o):
        kinder = baum.kinder[o.pk]
        return letzter(kinder[-1]) if kinder else o

    def teilbaum(o):
        return [o] + [x for k in baum.kinder[o.pk] for x in teilbaum(k)]

    knoepfe = []
    for w in baum.wurzeln():
        anzahl = sum(len(baum.nachweise_in[o.pk]) for o in teilbaum(w))
        knoepfe.append({"ziel": letzter(w), "wurzel": w, "label": _art(w), "anzahl": anzahl, "max": w.max_nachweise,
                        "voll": w.max_nachweise is not None and anzahl >= w.max_nachweise})
    return knoepfe


def spalte_anlegen(u, ordner_pk):
    """Neue Spalte (Leistungsnachweis mit heutigem Datum, Gewicht 1). Gibt (Leistungsnachweis, Fehlertext) zurück."""
    o = Bewertungsordner.objects.filter(pk=ordner_pk, unterricht=u).first()
    if o is None:
        return None, _("Ordner nicht gefunden.")
    wurzel = ([o] + o.vorfahren())[-1]
    g = o.grenze()
    if g is not None and g[1] >= g[2]:
        from .models import grenze_text

        return None, grenze_text(g)
    anzahl = Leistungsnachweis.objects.filter(ordner_id__in=wurzel.teilbaum_ids()).count()
    datum = min(max(timezone.localdate(), u.abschnitt.beginn), u.abschnitt.ende)
    art = _art(wurzel)
    titel = f"{art} {anzahl + 1}" if art != _("SoMi-Note") else f"SoMi {datum:%d.%m.}"
    ln = Leistungsnachweis(unterricht=u, ordner=o, titel=titel, datum=datum, gewicht=Decimal(1))
    try:
        ln.full_clean()
    except ValidationError as e:
        return None, " ".join(e.messages)
    ln.save()
    ln.notenzeilen_anlegen()
    return ln, None


def klassenuebersicht(klasse, abschnitt, kurse, user=None):
    """Schüler:innen × Fächer: je Zelle der rechnerische Stand (Schnitt, Tendenz, ganze Note) und die Zeugnisnote – wer sie
    festsetzen darf, trägt sie hier direkt ein (ab 0.4.13.0)."""
    from zeugnisse.noten import klassen_mitglieder

    schueler = klassen_mitglieder(klasse, abschnitt)
    ids = {s.pk for s in schueler}
    faecher, zellen = {}, defaultdict(dict)
    for u in kurse:
        teilnehmer = [s for s in u.schueler() if s.pk in ids]
        if not teilnehmer:
            continue
        faecher.setdefault(u.fach_id, {"fach": u.fach, "kurse": []})["kurse"].append(u)
        baum = Baum(u)
        jahr = Vorhalbjahr(u) if u.mit_jahresnote else False
        noten = defaultdict(list)
        for n in Note.objects.filter(leistungsnachweis__unterricht=u, schueler__in=[s.pk for s in teilnehmer]).select_related("stufe"):
            noten[n.schueler_id].append(n)
        zn = Z.aktuell(u)
        darf = bool(user) and zeugnisrechte.darf_zeugnisnote_setzen(user, u)
        sperre = Z.gesperrt(u, [s.pk for s in teilnehmer]) if darf else set()
        frei = Z.freigegebene(u, sperre) if sperre else set()
        optionen = [(str(w), st.bezeichnung) for w, st in sorted(Z.ganze_stufen(u.skala).items())]
        for s in teilnehmer:
            v = vorschlagsnote(u, s, noten[s.pk], baum, jahr=jahr)
            z = zn.get(s.pk)
            zn_gefaehrdet = bool(z and z.stufe_id and u.skala.ist_gefaehrdet(z.stufe.wert))
            zellen[s.pk][u.fach_id] = {
                "u": u, "schnitt": v.schnitt, "stufe": v.stufe, "gefaehrdet": v.gefaehrdet or zn_gefaehrdet,
                "ganz": u.skala.ganz_runden(v.schnitt) if v.schnitt is not None else None,
                "zeugnis": Z.anzeige(z), "zn": z, "auto": bool(z and z.quelle == Z.AUTO),
                "quelle": z.get_quelle_display() if z and z.quelle and z.quelle != Z.AUTO else "",
                "name": f"zn_{u.pk}_{s.pk}", "optionen": optionen, "wert": Z.formwert(z),
                "extra": Z.formwert(z) if Z.formwert(z) not in {w for w, _t in optionen} | {"", "nb", "befreit"} else "",
                "bearbeitbar": darf and s.pk not in sperre, "gesperrt": darf and s.pk in sperre, "zeugnis_frei": s.pk in frei,
                "anzahl": len([n for n in noten[s.pk] if n.stufe_id or n.sonderstatus]),
            }
    spalten = sorted(faecher.values(), key=lambda f: (f["fach"].reihenfolge, f["fach"].name))
    zeilen = []
    for s in schueler:
        reihe = [zellen[s.pk].get(f["fach"].pk) for f in spalten]
        zeilen.append({"s": s, "zellen": reihe, "gefaehrdet": sum(1 for c in reihe if c and c["gefaehrdet"])})
    freigegeben = len({s.pk for s in schueler for c in zellen[s.pk].values() if c["zeugnis_frei"]})
    return {"spalten": spalten, "zeilen": zeilen, "freigegeben": freigegeben}


@transaction.atomic
def speichern(request, u):
    """Geänderte Zellen speichern. Gibt (geändert, konflikte, fehler{name: text}) zurück; bei Fehlern wird nichts gespeichert."""
    from .sperre import gesperrte_schueler

    if not rechte.darf_noten_eintragen(request.user, u):
        raise PermissionDenied
    baum = Baum(u)
    schueler = {s.pk: s for s in u.schueler()}
    gesperrt = gesperrte_schueler(u, list(schueler))
    aenderungen = defaultdict(dict)      # ln → {schueler: text}
    for schluessel, wert in request.POST.items():
        if not schluessel.startswith("n_"):
            continue
        try:
            _n, ln_pk, s_pk = schluessel.split("_")
            ln_pk, s_pk = int(ln_pk), int(s_pk)
        except ValueError:
            continue
        orig = request.POST.get(f"o_{ln_pk}_{s_pk}", "")
        if E.normalisieren(wert) == E.normalisieren(orig) or s_pk not in schueler or s_pk in gesperrt:
            continue
        aenderungen[ln_pk][s_pk] = (wert, orig)
    nachweise = {ln.pk: ln for ln in baum.nachweise}
    geaendert, konflikte, fehler = 0, [], {}
    for ln_pk, zellen in aenderungen.items():
        ln = nachweise.get(ln_pk)
        if ln is None or ln.schluessel_id:
            continue
        vorhanden = {n.schueler_id: n for n in Note.objects.filter(leistungsnachweis=ln).select_related("stufe", "leistungsnachweis")}
        eingaben = {}
        for s_pk, (wert, orig) in zellen.items():
            n = vorhanden.get(s_pk)
            if E.normalisieren(E.anzeige(n) if n else "") != E.normalisieren(orig):
                konflikte.append(f"{schueler[s_pk].person}: {ln.titel}")
                continue
            eingaben[s_pk] = {"note": wert, "kommentar": n.kommentar if n else "",
                              "gewicht": E._zahl(n.gewicht_individuell) if n else "",
                              "begruendung": n.gewicht_begruendung if n else ""}
        ergebnisse, f = E.pruefen(ln, eingaben, [schueler[pk] for pk in eingaben])
        for s_pk, text in f.items():
            fehler[f"n_{ln_pk}_{s_pk}"] = text
        if not f and ergebnisse:
            ln.notenzeilen_anlegen()
            geaendert += E.speichern(ln, ergebnisse)
    # Gewichte im Tabellenkopf (ab 0.4.17.0) – nicht, solange Noten von Schüler:innen gesperrt sind
    if not gesperrt:
        for ln_pk, ln in nachweise.items():
            neu, alt = (request.POST.get(f"g_{ln_pk}") or "").strip(), (request.POST.get(f"go_{ln_pk}") or "").strip()
            if f"g_{ln_pk}" not in request.POST or neu == alt:
                continue
            try:
                wert = Decimal(neu.replace(",", "."))
            except InvalidOperation:
                wert = None
            obergrenze = Decimal(100) if ln.ordner.gewichtsart == PROZENT else Decimal(1000)
            if wert is None or wert <= 0 or wert > obergrenze:
                fehler[f"g_{ln_pk}"] = _("%(titel)s: Gewicht „%(wert)s“ muss eine Zahl größer als 0 (höchstens %(max)s) sein.") % {
                    "titel": ln.titel, "wert": neu, "max": obergrenze}
                continue
            if ln.gewicht != wert:
                ln.gewicht = wert
                ln.save(update_fields=["gewicht"])
                geaendert += 1
    # Zeugnisnote in der letzten Spalte (ab 0.4.17.0): leer = automatisch aus den Einzelnoten
    if zeugnisrechte.darf_zeugnisnote_setzen(request.user, u):
        zn_aenderungen = {}
        for s_pk in schueler:
            if f"zk_{s_pk}" in request.POST:
                neu, alt = request.POST[f"zk_{s_pk}"].strip(), request.POST.get(f"zko_{s_pk}", "").strip()
                if neu != alt:
                    zn_aenderungen[s_pk] = (neu, alt)
        if zn_aenderungen:
            n, f, k = _zeugnis_kurs(u, schueler, zn_aenderungen)
            geaendert += n
            fehler.update(f)
            konflikte += k
    if fehler:
        transaction.set_rollback(True)
        return 0, konflikte, fehler
    return geaendert, konflikte, fehler


def _zeugnis_kurs(u, schueler, aenderungen):
    """Zeugnisnoten aus der Notentabelle: (gespeichert, fehler{feld: text}, konflikte)."""
    bestehend = Z.aktuell(u, list(aenderungen))
    sperre = Z.gesperrt(u, list(aenderungen))
    stufen = Z.ganze_stufen(u.skala)
    wuensche, fehler, konflikte, n = {}, {}, [], 0
    for s_pk, (wert, orig) in aenderungen.items():
        z = bestehend.get(s_pk)
        if (Z.formwert(z) if z is not None and z.quelle != Z.AUTO else "") != orig:
            konflikte.append(f"{schueler[s_pk].person}: {_('Zeugnisnote')}")
            continue
        if s_pk in sperre:
            continue
        if wert == "":
            if z is not None and z.quelle != Z.AUTO:
                z.delete()                       # zurück auf automatisch
                n += 1
            continue
        try:
            wuensche[schueler[s_pk]] = Z.lesen(wert, stufen)
        except ValueError as e:
            fehler[f"zk_{s_pk}"] = str(e)
    zeilen = Z.pruefen(u, wuensche)
    n += Z.speichern(u, zeilen, "kurs")
    for zeile in zeilen:
        if zeile["status"] == "fehler":
            fehler[f"zk_{zeile['s'].pk}"] = zeile["text"]
    return n, fehler, konflikte


@transaction.atomic
def zeugnis_speichern(request, kurse, klasse, abschnitt):
    """Zeugnisnoten aus der Klassenübersicht speichern. Gibt (gespeichert, geloescht, meldungen) zurück; `meldungen` nennt
    Zellen, die nicht gespeichert wurden (inzwischen geändert, gesperrt, ohne Einzelnoten)."""
    from zeugnisse.noten import klassen_mitglieder

    ids = {s.pk for s in klassen_mitglieder(klasse, abschnitt)}
    nach_pk = {u.pk: u for u in kurse}
    aenderungen = defaultdict(dict)
    for schluessel, wert in request.POST.items():
        if not schluessel.startswith("zn_"):
            continue
        try:
            _p, u_pk, s_pk = schluessel.split("_")
            u_pk, s_pk = int(u_pk), int(s_pk)
        except ValueError:
            continue
        if u_pk not in nach_pk or s_pk not in ids or wert.strip() == request.POST.get(f"zo_{u_pk}_{s_pk}", "").strip():
            continue
        aenderungen[u_pk][s_pk] = (wert.strip(), request.POST.get(f"zo_{u_pk}_{s_pk}", "").strip())
    gespeichert, geloescht, meldungen = 0, 0, []
    for u_pk, zellen in aenderungen.items():
        u = nach_pk[u_pk]
        if not zeugnisrechte.darf_zeugnisnote_setzen(request.user, u):
            raise PermissionDenied
        schueler = {s.pk: s for s in u.schueler() if s.pk in zellen}
        bestehend = Z.aktuell(u, schueler)
        sperre = Z.gesperrt(u, list(schueler))
        stufen = Z.ganze_stufen(u.skala)
        wuensche = {}
        for s_pk, (wert, orig) in zellen.items():
            s = schueler.get(s_pk)
            if s is None:
                continue
            name = f"{s.person} ({u.fach.kuerzel})"
            if Z.formwert(bestehend.get(s_pk)) != orig:
                meldungen.append(_("%(name)s: inzwischen von anderer Seite geändert – nicht überschrieben.") % {"name": name})
            elif s_pk in sperre:
                meldungen.append(_("%(name)s: gesperrt – nicht geändert.") % {"name": name})
            elif wert == "":
                bestehend[s_pk].delete()
                geloescht += 1
            else:
                try:
                    wuensche[s] = Z.lesen(wert, stufen)
                except ValueError as f:
                    meldungen.append(f"{name}: {f}")
        zeilen = Z.pruefen(u, wuensche)
        gespeichert += Z.speichern(u, zeilen, "klasse")
        meldungen += [f"{z['s'].person} ({u.fach.kuerzel}): {z['text']}" for z in zeilen if z["status"] == "fehler"]
    return gespeichert, geloescht, meldungen


@login_required
def noten_klassen(request):
    abschnitte, laufend = _abschnitte()
    abschnitt = next((a for a in abschnitte if str(a.pk) == request.GET.get("abschnitt")), laufend)
    if abschnitt is None:
        return render(request, "noten/klassen.html", {"abschnitte": [], "klassen": {}})
    zuordnung = klassen_und_kurse(request.user, abschnitt)
    klasse = next((k for k in zuordnung if str(k.pk) == request.GET.get("klasse")), None)
    if klasse is None and len(zuordnung) == 1:
        klasse = next(iter(zuordnung))
    kurse = zuordnung.get(klasse, [])
    kurs = next((u for u in kurse if str(u.pk) == request.GET.get("kurs")), None)
    hier = reverse("noten_klassen") + "?" + urlencode(
        {k: v for k, v in (("abschnitt", abschnitt.pk), ("klasse", klasse.pk if klasse else ""), ("kurs", kurs.pk if kurs else "")) if v})

    eingaben = fehler = None
    aktion = request.POST.get("aktion", "") if request.method == "POST" else ""
    if kurs is not None and (aktion == "speichern" or aktion.startswith("spalte:")):
        geaendert, konflikte, fehler = speichern(request, kurs)
        if fehler:
            eingaben = {k: v for k, v in request.POST.items() if k.startswith(("n_", "zk_", "g_"))}
            messages.error(request, ngettext("%(n)s Eingabe ist nicht gültig – es wurde nichts gespeichert.",
                                             "%(n)s Eingaben sind nicht gültig – es wurde nichts gespeichert.", len(fehler)) % {"n": len(fehler)})
        else:
            if konflikte:
                messages.warning(request, _("Inzwischen von anderer Seite geändert und daher nicht überschrieben: %(liste)s")
                                 % {"liste": "; ".join(konflikte)})
            if geaendert or aktion == "speichern":
                messages.success(request, ngettext("%(n)s Änderung gespeichert.", "%(n)s Änderungen gespeichert.", geaendert) % {"n": geaendert})
            if aktion.startswith("spalte:"):
                ln, text = spalte_anlegen(kurs, aktion.partition(":")[2])
                if ln is None:
                    messages.error(request, text)
                else:
                    messages.success(request, _("Neue Spalte „%(titel)s“ angelegt – jetzt die Noten eintragen.") % {"titel": ln.titel})
                    return redirect(f"{hier}&neu={ln.pk}")      # ohne #kurs: der Sprung würde den Fokus wegnehmen
            return redirect(hier + "#kurs")

    if request.method == "POST" and klasse is not None and request.POST.get("aktion") == "zeugnis":
        gespeichert, geloescht, meldungen = zeugnis_speichern(request, kurse, klasse, abschnitt)
        if gespeichert or geloescht:
            messages.success(request, ngettext("%(n)s Zeugnisnote festgesetzt.", "%(n)s Zeugnisnoten festgesetzt.", gespeichert + geloescht)
                             % {"n": gespeichert + geloescht})
        if meldungen:
            messages.warning(request, _("Nicht gespeichert:") + " " + "; ".join(meldungen))
        elif not (gespeichert or geloescht):
            messages.info(request, _("Keine Änderungen."))
        return redirect(hier + "#uebersicht")

    kurs_daten = []
    for u in kurse:
        kurs_daten.append({"u": u, "anzahl_ln": u.leistungsnachweise.count(),
                           "lerngruppe": u.gruppe.typ != Gruppe.STAMMKLASSE, "darf": rechte.darf_noten_eintragen(request.user, u)})
    tabelle = notentabelle_daten(request, kurs, eingaben, fehler) if kurs else None
    uebersicht = klassenuebersicht(klasse, abschnitt, kurse, request.user) if klasse and not kurs else None
    return render(request, "noten/klassen.html", {
        "abschnitte": abschnitte, "abschnitt": abschnitt, "klassen": list(zuordnung), "klasse": klasse,
        "kurse": kurs_daten, "kurs": kurs, "tabelle": tabelle, "hier": hier, "uebersicht": uebersicht,
        "sek1": bool(kurs and I.nur_sek1(kurs)),
    })
