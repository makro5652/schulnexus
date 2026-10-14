"""
Schuljahreswechsel: neues Schuljahr anlegen, Klassen fortschreiben, Schüler:innen versetzen – und zurücknehmen.

Ablauf
1. Neues Schuljahr (mit Halbjahren) anlegen bzw. wählen.
2. Klassenplan: Nachfolgeklassen vorschlagen (9a → 10a, Klassenleitung bleibt) und anlegen.
3. Entscheidungen je Schüler:in: Vorschlag aus dem Beschluss der Versetzungskonferenz, sonst aus dem Vermerk im
   Jahreszeugnis, sonst aus der Schullaufbahn; Zielklasse aus dem Klassenplan.
4. Durchführen: alte Mitgliedschaften enden mit dem letzten Tag des alten Schuljahres, neue beginnen mit dem ersten
   Tag des neuen; neuer Laufbahnabschnitt; wer die Schule verlässt, geht ins Archiv. Optional wird das neue Schuljahr
   zum aktuellen Schuljahr.
5. Rücknahme: je Schüler:in oder für den ganzen Wechsel – stellt den vorherigen Stand wieder her.
"""
import re
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone
from django.utils.translation import gettext

from stammdaten.models import Abschnitt, Bildungsgang, Gruppe, Laufbahnabschnitt, Mitgliedschaft, Schuelerprofil, Schuljahr

from .models import ERGEBNIS_FUER, Klassenplan, Schuljahreswechsel, Wechselposten


# ---------------------------------------------------------------- Schuljahre

def _iso(d):
    return d.isoformat() if d else None


def _datum(s):
    return date.fromisoformat(s) if s else None


def folgename(name):
    """„2026/27“ → „2027/28“, „2026-2027“ → „2027-2028“, „2026“ → „2027“."""
    m = re.fullmatch(r"(\d{4})([/-])(\d{2}|\d{4})", name.strip())
    if m:
        a, trenner, b = int(m.group(1)) + 1, m.group(2), int(m.group(3)) + 1
        return f"{a}{trenner}{b % 100:02d}" if len(m.group(3)) == 2 else f"{a}{trenner}{b}"
    m = re.fullmatch(r"\d{4}", name.strip())
    return str(int(name) + 1) if m else ""


def naechstes_schuljahr(sj):
    return Schuljahr.objects.filter(beginn__gt=sj.beginn).order_by("beginn").first()


def vorschlag_neues_schuljahr(sj):
    """Gleiche Lage ein Jahr später (52 Wochen – derselbe Wochentag)."""
    versatz = timedelta(weeks=52)
    return {"name": folgename(sj.name), "beginn": sj.beginn + versatz, "ende": sj.ende + versatz}


@transaction.atomic
def schuljahr_anlegen(name, beginn, ende, vorlage=None):
    """Legt ein Schuljahr an und übernimmt die Halbjahre der Vorlage zeitlich verschoben."""
    neu = Schuljahr(name=name, beginn=beginn, ende=ende)
    neu.full_clean()
    neu.save()
    if vorlage:
        versatz = beginn - vorlage.beginn
        abschnitte = list(vorlage.abschnitte.order_by("nummer"))
        for i, a in enumerate(abschnitte):
            a_beginn = beginn if i == 0 else a.beginn + versatz
            a_ende = ende if i == len(abschnitte) - 1 else a.ende + versatz
            Abschnitt.objects.create(schuljahr=neu, name=a.name, name_en=a.name_en, nummer=a.nummer, beginn=a_beginn, ende=a_ende)
    return neu


@transaction.atomic
def aktivieren(sj):
    Schuljahr.objects.filter(aktiv=True).exclude(pk=sj.pk).update(aktiv=False)
    Schuljahr.objects.filter(pk=sj.pk).update(aktiv=True)
    sj.aktiv = True


# ---------------------------------------------------------------- Klassenplan

def folgeklasse(name, jahrgang):
    """„9a“ → „10a“, „Klasse 9b“ → „Klasse 10b“; ohne Jahrgangszahl im Namen bleibt der Name."""
    if jahrgang is None:
        return name
    neu = re.sub(rf"(?<!\d){jahrgang}(?!\d)", str(jahrgang + 1), name, count=1)
    return neu


def hoechster_jahrgang():
    return Bildungsgang.objects.aggregate(m=Max("jahrgang_bis"))["m"] or 12


def klassenplan_aktualisieren(w):
    """Legt für jede Stammklasse des alten Schuljahres eine Zeile an und sucht eine passende vorhandene Nachfolgeklasse."""
    maximal = hoechster_jahrgang()
    neue = {g.name.lower(): g for g in Gruppe.objects.filter(schuljahr=w.nach, typ=Gruppe.STAMMKLASSE)}
    for alt in Gruppe.objects.filter(schuljahr=w.von, typ=Gruppe.STAMMKLASSE):
        plan, neu = Klassenplan.objects.get_or_create(wechsel=w, alt=alt)
        if plan.neu_id:
            continue
        nachfolger = Gruppe.objects.filter(schuljahr=w.nach, vorgaenger=alt, typ=Gruppe.STAMMKLASSE).first()
        if not nachfolger and (alt.jahrgang or 0) < maximal:
            nachfolger = neue.get(folgeklasse(alt.name, alt.jahrgang).lower())
        if nachfolger:
            plan.neu = nachfolger
            plan.save(update_fields=["neu"])


def klassenplan_zeilen(w):
    maximal = hoechster_jahrgang()
    zeilen = []
    for plan in w.klassenplan.select_related("alt__leitung__person", "neu__leitung__person").order_by("alt__jahrgang", "alt__name"):
        auslaufend = (plan.alt.jahrgang or 0) >= maximal
        zeilen.append({"plan": plan, "auslaufend": auslaufend, "vorschlag": "" if auslaufend else folgeklasse(plan.alt.name, plan.alt.jahrgang),
                       "jahrgang": None if auslaufend or plan.alt.jahrgang is None else plan.alt.jahrgang + 1,
                       "anzahl": plan.alt.aktuelle_mitglieder(w.von.ende).count()})
    return zeilen


@transaction.atomic
def klasse_anlegen(w, name, jahrgang, leitung=None, vorgaenger=None):
    name = (name or "").strip()
    if not name:
        raise ValidationError(gettext("Bitte einen Namen für die Klasse angeben."))
    vorhanden = Gruppe.objects.filter(schuljahr=w.nach, name__iexact=name).first()
    if vorhanden:
        return vorhanden, False
    g = Gruppe.objects.create(schuljahr=w.nach, typ=Gruppe.STAMMKLASSE, name=name, kuerzel=name[:20], jahrgang=jahrgang,
                              leitung=leitung, vorgaenger=vorgaenger)
    return g, True


# ---------------------------------------------------------------- Vorschläge je Schüler:in

def _laufbahn_im(s, sj):
    return s.laufbahn.filter(schuljahr=sj).select_related("bildungsgang").order_by("-von", "-pk").first()


def _klasse_im(s, sj):
    m = (Mitgliedschaft.objects.filter(schueler=s, gruppe__schuljahr=sj, gruppe__typ=Gruppe.STAMMKLASSE)
         .select_related("gruppe").order_by("-von").first())
    return m.gruppe if m else None


def entscheidung_vorschlagen(w, s, klasse, lb):
    """(Entscheidung, Grundlage) aus Konferenzbeschluss, Jahreszeugnis oder Schullaufbahn."""
    from zeugnisse.models import Beschluss, Konferenz, Zeugnis

    b = (Beschluss.objects.filter(schueler=s, konferenz__art=Konferenz.VERSETZUNG, konferenz__abschnitt__schuljahr=w.von)
         .exclude(entscheidung__in=["", "keine"]).select_related("konferenz").first())
    if b:
        e = {"versetzt": "versetzt", "versetzt_ausgleich": "versetzt", "qp_ja": "versetzt", "nachpruefung": "nicht_versetzt",
             "nicht_versetzt": "nicht_versetzt", "qp_nein": "nicht_versetzt", "wiederholung": "freiwillig"}.get(b.entscheidung)
        if e:
            grund = gettext("Versetzungskonferenz: %(e)s") % {"e": b.get_entscheidung_display()}
            if b.entscheidung == "nachpruefung":
                grund += " – " + gettext("Ergebnis der Nachprüfung beachten")
            return e, grund
    z = (Zeugnis.objects.filter(schueler=s, abschnitt__schuljahr=w.von, art__in=[Zeugnis.JAHR, Zeugnis.ABGANG])
         .exclude(versetzung="").order_by("-abschnitt__nummer").first())
    if z:
        e = {"versetzt": "versetzt", "qp_ja": "versetzt", "nicht_versetzt": "nicht_versetzt", "qp_nein": "nicht_versetzt",
             "wiederholung": "freiwillig"}.get(z.versetzung)
        if e:
            return e, gettext("Vermerk im Jahreszeugnis: %(v)s") % {"v": z.get_versetzung_display()}
    if lb and lb.ergebnis not in ("laufend", ""):
        e = {v: k for k, v in ERGEBNIS_FUER.items()}.get(lb.ergebnis)
        if lb.ergebnis == "versetzt_auflage":
            e = "versetzt"
        if e:
            return e, gettext("Schullaufbahn: %(v)s") % {"v": lb.get_ergebnis_display()}
    jg = lb.jahrgang if lb else getattr(klasse, "jahrgang", None)
    if jg and jg >= hoechster_jahrgang():
        return "abschluss", gettext("Höchste Jahrgangsstufe der Schule")
    return "versetzt", gettext("Kein Beschluss erfasst – Vorschlag")


def zielklasse_vorschlagen(p, plan_neu, klassen_nach):
    """Nachfolgeklasse der bisherigen Klasse, sonst gleiche Parallelbezeichnung, sonst die erste passende Klasse."""
    jg = p.neuer_jahrgang
    if jg is None:
        return None
    passend = [g for g in klassen_nach if g.jahrgang == jg]
    nachfolger = plan_neu.get(p.alte_klasse_id)
    if nachfolger and nachfolger.jahrgang == jg:
        return nachfolger
    if p.alte_klasse:
        zusatz = re.sub(r"\d+", "", p.alte_klasse.name).strip().lower()
        for g in passend:
            if re.sub(r"\d+", "", g.name).strip().lower() == zusatz:
                return g
    return passend[0] if passend else None


def betroffene(w):
    """Aktive Schüler:innen mit Stammklasse oder Laufbahnabschnitt im alten Schuljahr."""
    in_klasse = Mitgliedschaft.objects.filter(gruppe__schuljahr=w.von, gruppe__typ=Gruppe.STAMMKLASSE).filter(
        Q(bis__isnull=True) | Q(bis__gte=w.von.ende)).values("schueler")
    mit_laufbahn = Laufbahnabschnitt.objects.filter(schuljahr=w.von).filter(Q(bis__isnull=True) | Q(bis__gte=w.von.ende)).values("schueler")
    return (Schuelerprofil.objects.filter(status="aktiv").filter(Q(pk__in=in_klasse) | Q(pk__in=mit_laufbahn))
            .select_related("person"))


@transaction.atomic
def posten_aktualisieren(w):
    """Legt fehlende Posten mit Vorschlag an; offene Posten ohne Zielklasse erhalten einen Klassenvorschlag."""
    plan_neu = {pl.alt_id: pl.neu for pl in w.klassenplan.select_related("neu")}
    klassen_nach = list(Gruppe.objects.filter(schuljahr=w.nach, typ=Gruppe.STAMMKLASSE).order_by("name"))
    vorhanden = set(w.posten.values_list("schueler_id", flat=True))
    neu = 0
    for s in betroffene(w):
        if s.pk in vorhanden:
            continue
        klasse = _klasse_im(s, w.von)
        lb = _laufbahn_im(s, w.von)
        e, grund = entscheidung_vorschlagen(w, s, klasse, lb)
        p = Wechselposten(wechsel=w, schueler=s, alte_klasse=klasse, alter_jahrgang=(lb.jahrgang if lb else getattr(klasse, "jahrgang", None)),
                          entscheidung=e, grundlage=grund[:200])
        p.neue_klasse = zielklasse_vorschlagen(p, plan_neu, klassen_nach)
        p.save()
        neu += 1
    for p in w.posten.filter(status=Wechselposten.OFFEN, neue_klasse__isnull=True).select_related("alte_klasse"):
        k = zielklasse_vorschlagen(p, plan_neu, klassen_nach)
        if k:
            p.neue_klasse = k
            p.save(update_fields=["neue_klasse"])
    return neu


def wechsel_anlegen(von, nach, user):
    if nach.beginn <= von.beginn:
        raise ValidationError(gettext("Das neue Schuljahr muss nach dem bisherigen beginnen."))
    w, neu = Schuljahreswechsel.objects.get_or_create(von=von, defaults={"nach": nach, "erstellt_von": user})
    if not neu and w.nach_id != nach.pk:
        if w.durchgefuehrt:
            raise ValidationError(gettext("Für dieses Schuljahr wurde der Wechsel bereits durchgeführt."))
        w.nach = nach
        w.save(update_fields=["nach"])
        w.klassenplan.all().delete()
        w.posten.filter(status=Wechselposten.OFFEN).update(neue_klasse=None)
    klassenplan_aktualisieren(w)
    posten_aktualisieren(w)
    return w


def hindernis(p):
    """Grund, warum ein offener Posten (noch) nicht durchgeführt werden kann – oder ''."""
    if p.verlaesst_schule:
        return ""
    if p.alter_jahrgang is None:
        return gettext("Bisheriger Jahrgang unbekannt")
    if not p.neue_klasse_id:
        return gettext("Keine Zielklasse gewählt")
    if p.neue_klasse.jahrgang not in (None, p.neuer_jahrgang):
        return gettext("Zielklasse %(k)s passt nicht zu Jahrgang %(jg)s") % {"k": p.neue_klasse.name, "jg": p.neuer_jahrgang}
    return ""


# ---------------------------------------------------------------- Durchführen und Rücknahme

def passender_bildungsgang(bisher, jahrgang):
    def passt(bg):
        return (bg.jahrgang_von is None or bg.jahrgang_von <= jahrgang) and (bg.jahrgang_bis is None or jahrgang <= bg.jahrgang_bis)
    if bisher and passt(bisher):
        return bisher
    for bg in Bildungsgang.objects.exclude(jahrgang_von__isnull=True).order_by("reihenfolge"):
        if passt(bg):
            return bg
    return bisher


def _mitgliedschaft_setzen(m, bis):
    """Ende einer Mitgliedschaft setzen (mit Protokoll); fällt die Prüfung aus, ohne Prüfung."""
    m.bis = bis
    try:
        m.save()
    except ValidationError:
        Mitgliedschaft.objects.filter(pk=m.pk).update(bis=bis)


@transaction.atomic
def posten_durchfuehren(p, user=None):
    w, s = p.wechsel, p.schueler
    if p.status != Wechselposten.OFFEN or hindernis(p):
        return False
    undo = {"mitgliedschaften": [], "konto": None}
    lb = _laufbahn_im(s, w.von)
    if lb:
        undo["lb"] = {"pk": lb.pk, "ergebnis": lb.ergebnis}
        lb.ergebnis = ERGEBNIS_FUER[p.entscheidung]
        lb.save(update_fields=["ergebnis"])
    for m in Mitgliedschaft.objects.filter(schueler=s, gruppe__schuljahr=w.von).filter(Q(bis__isnull=True) | Q(bis__gt=w.von.ende)):
        undo["mitgliedschaften"].append([m.pk, _iso(m.bis)])
        _mitgliedschaft_setzen(m, max(w.von.ende, m.von))
    if not p.verlaesst_schule:
        jg = p.neuer_jahrgang
        if not Laufbahnabschnitt.objects.filter(schueler=s, schuljahr=w.nach).exists():
            bg = passender_bildungsgang(lb.bildungsgang if lb else None, jg)
            if bg:
                neu = Laufbahnabschnitt.objects.create(
                    schueler=s, schuljahr=w.nach, jahrgang=jg, bildungsgang=bg, stammklasse=p.neue_klasse,
                    bemerkung=gettext("Schuljahreswechsel %(von)s → %(nach)s") % {"von": w.von, "nach": w.nach})
                undo["neuer_lb"] = neu.pk
        if not Mitgliedschaft.objects.filter(schueler=s, gruppe__schuljahr=w.nach, gruppe__typ=Gruppe.STAMMKLASSE).exists():
            m = Mitgliedschaft.objects.create(gruppe=p.neue_klasse, schueler=s, von=w.nach.beginn)
            undo["neue_mitgliedschaft"] = m.pk
    else:
        undo["schueler"] = {"status": s.status, "austrittsdatum": _iso(s.austrittsdatum), "austrittsgrund": s.austrittsgrund}
        s.status = "abgang"
        s.austrittsdatum = s.austrittsdatum or w.von.ende
        if not s.austrittsgrund:
            s.austrittsgrund = gettext("Abschluss") if p.entscheidung == "abschluss" else gettext("Abgang zum Schuljahresende")
        s.save()
        konto = getattr(s.person, "benutzer", None)
        if konto and konto.is_active:
            konto.is_active = False
            konto.save(update_fields=["is_active"])
            undo["konto"] = konto.pk
    p.rueckgaengig = undo
    p.status = Wechselposten.DURCHGEFUEHRT
    p.durchgefuehrt_am = timezone.now()
    p.save()
    return True


@transaction.atomic
def posten_zuruecknehmen(p):
    if p.status != Wechselposten.DURCHGEFUEHRT:
        return False
    u, s = p.rueckgaengig or {}, p.schueler
    if u.get("neue_mitgliedschaft"):
        Mitgliedschaft.objects.filter(pk=u["neue_mitgliedschaft"]).delete()
    if u.get("neuer_lb"):
        Laufbahnabschnitt.objects.filter(pk=u["neuer_lb"]).delete()
    for pk, bis in u.get("mitgliedschaften", []):
        m = Mitgliedschaft.objects.filter(pk=pk).first()
        if m:
            _mitgliedschaft_setzen(m, _datum(bis))
    if u.get("lb"):
        Laufbahnabschnitt.objects.filter(pk=u["lb"]["pk"]).update(ergebnis=u["lb"]["ergebnis"])
    if u.get("schueler"):
        alt = u["schueler"]
        s.status, s.austrittsdatum, s.austrittsgrund = alt["status"], _datum(alt["austrittsdatum"]), alt["austrittsgrund"]
        s.save()
    if u.get("konto"):
        from django.contrib.auth import get_user_model
        get_user_model().objects.filter(pk=u["konto"]).update(is_active=True)
    p.status = Wechselposten.OFFEN
    p.rueckgaengig = {}
    p.zurueckgenommen_am = timezone.now()
    p.save()
    return True


def wechsel_durchfuehren(w, user=None, schuljahr_aktivieren=True):
    """Führt alle offenen, vollständigen Posten aus; gibt (durchgeführt, übersprungen) zurück."""
    ok = offen = 0
    with transaction.atomic():
        for p in w.posten.filter(status=Wechselposten.OFFEN).select_related("schueler__person", "neue_klasse", "alte_klasse"):
            if posten_durchfuehren(p, user):
                ok += 1
            else:
                offen += 1
        if w.status != Schuljahreswechsel.DURCHGEFUEHRT:
            w.status = Schuljahreswechsel.DURCHGEFUEHRT
            w.durchgefuehrt_von, w.durchgefuehrt_am = user, timezone.now()
            if schuljahr_aktivieren and w.von.aktiv:
                aktivieren(w.nach)
                w.aktiv_umgestellt = True
            w.save()
    return ok, offen


def _leer(g):
    from noten.models import Unterricht
    from zeugnisse.models import Konferenz, Zeugnis

    return not (Mitgliedschaft.objects.filter(gruppe=g).exists() or Unterricht.objects.filter(gruppe=g).exists()
                or Zeugnis.objects.filter(klasse=g).exists() or Konferenz.objects.filter(klasse=g).exists()
                or Laufbahnabschnitt.objects.filter(stammklasse=g).exists())


@transaction.atomic
def wechsel_zuruecknehmen(w, klassen_loeschen=True):
    """Nimmt alle Posten zurück, stellt das aktuelle Schuljahr wieder her und entfernt leere, neu angelegte Klassen."""
    n = sum(1 for p in w.posten.filter(status=Wechselposten.DURCHGEFUEHRT).select_related("schueler__person")
            if posten_zuruecknehmen(p))
    if w.aktiv_umgestellt:
        aktivieren(w.von)
        w.aktiv_umgestellt = False
    geloescht = 0
    if klassen_loeschen:
        for plan in w.klassenplan.filter(neu_angelegt=True).select_related("neu"):
            if plan.neu and _leer(plan.neu):
                plan.neu.delete()
                geloescht += 1
                Klassenplan.objects.filter(pk=plan.pk).update(neu=None, neu_angelegt=False)
    w.status = Schuljahreswechsel.VORBEREITET
    w.durchgefuehrt_am = None
    w.durchgefuehrt_von = None
    w.save()
    return n, geloescht
