"""
Änderungen der Schullaufbahn im laufenden Schuljahr: Klassenwechsel, Höher- oder Zurückstufung, Abgang.
Jede Änderung speichert die Daten für ihre Rücknahme; zurückgenommen werden kann jeweils die letzte Änderung.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import formats, timezone
from django.utils.translation import gettext

from stammdaten.models import Abschnitt, Gruppe, Laufbahnabschnitt, Mitgliedschaft, Schuljahr

from .models import Laufbahnereignis
from .wechsel import _datum, _iso, passender_bildungsgang


def _d(datum):
    return formats.date_format(datum, "SHORT_DATE_FORMAT")


def _stammmitgliedschaft(s, datum):
    return (Mitgliedschaft.objects.aktiv(datum).filter(schueler=s, gruppe__typ=Gruppe.STAMMKLASSE)
            .select_related("gruppe__schuljahr").first())


def _laufbahn_am(s, schuljahr, datum):
    return (s.laufbahn.filter(schuljahr=schuljahr).filter(Q(von__isnull=True) | Q(von__lte=datum))
            .filter(Q(bis__isnull=True) | Q(bis__gte=datum)).select_related("bildungsgang").order_by("-von", "-pk").first())


@transaction.atomic
def umstufen(s, zielklasse, datum, user=None, bemerkung=""):
    """Klassenwechsel bzw. Höher-/Zurückstufung zum `datum` in eine Stammklasse desselben Schuljahres."""
    sj = zielklasse.schuljahr
    if not (sj.beginn <= datum <= sj.ende):
        raise ValidationError(gettext("Das Datum liegt nicht im Schuljahr der Zielklasse."))
    m = _stammmitgliedschaft(s, datum)
    if m and m.gruppe_id == zielklasse.pk:
        raise ValidationError(gettext("Die Schülerin / der Schüler ist an diesem Tag bereits in dieser Klasse."))
    if m and m.gruppe.schuljahr_id != sj.pk:
        m = None
    daten = {"mitgliedschaft": None, "lb_alt": None, "lb_neu": None}
    lb = _laufbahn_am(s, sj, datum)
    alt_jg = lb.jahrgang if lb else (m.gruppe.jahrgang if m else None)
    neu_jg = zielklasse.jahrgang if zielklasse.jahrgang is not None else alt_jg
    if alt_jg is not None and neu_jg is not None and neu_jg > alt_jg:
        art = Laufbahnereignis.HOCHGESTUFT
    elif alt_jg is not None and neu_jg is not None and neu_jg < alt_jg:
        art = Laufbahnereignis.ZURUECKGESTUFT
    else:
        art = Laufbahnereignis.KLASSENWECHSEL
    if m:
        if m.von >= datum:
            raise ValidationError(gettext("Der Wechsel muss nach Beginn der bisherigen Klassenzugehörigkeit (%(d)s) liegen.")
                                  % {"d": _d(m.von)})
        daten["mitgliedschaft"] = [m.pk, _iso(m.bis)]
        m.bis = datum - timedelta(days=1)
        m.save()
    neu_m = Mitgliedschaft.objects.create(gruppe=zielklasse, schueler=s, von=datum)
    daten["neue_mitgliedschaft"] = neu_m.pk
    if lb and art == Laufbahnereignis.KLASSENWECHSEL:
        daten["lb_alt"] = {"pk": lb.pk, "stammklasse": lb.stammklasse_id}
        lb.stammklasse = zielklasse
        lb.save(update_fields=["stammklasse"])
    elif lb:
        if lb.von and lb.von >= datum:
            raise ValidationError(gettext("Der Wechsel muss nach Beginn des bisherigen Laufbahnabschnitts liegen."))
        daten["lb_alt"] = {"pk": lb.pk, "bis": _iso(lb.bis), "ergebnis": lb.ergebnis}
        lb.bis = datum - timedelta(days=1)
        lb.ergebnis = "uebersprungen" if art == Laufbahnereignis.HOCHGESTUFT else "zurueckgestuft"
        lb.save(update_fields=["bis", "ergebnis"])
        neu = Laufbahnabschnitt.objects.create(schueler=s, schuljahr=sj, jahrgang=neu_jg, stammklasse=zielklasse, von=datum,
                                               bildungsgang=passender_bildungsgang(lb.bildungsgang, neu_jg), bis=None,
                                               bemerkung=(bemerkung or "")[:200])
        daten["lb_neu"] = neu.pk
    elif neu_jg is not None:
        bg = passender_bildungsgang(None, neu_jg)
        if bg:
            neu = Laufbahnabschnitt.objects.create(schueler=s, schuljahr=sj, jahrgang=neu_jg, stammklasse=zielklasse,
                                                   von=datum if datum > sj.beginn else None, bildungsgang=bg)
            daten["lb_neu"] = neu.pk
    vorher = m.gruppe.name if m else "–"
    text = {
        Laufbahnereignis.KLASSENWECHSEL: gettext("Klassenwechsel %(alt)s → %(neu)s"),
        Laufbahnereignis.HOCHGESTUFT: gettext("Höherstufung %(alt)s → %(neu)s (Jahrgang %(jg)s)"),
        Laufbahnereignis.ZURUECKGESTUFT: gettext("Zurückstufung %(alt)s → %(neu)s (Jahrgang %(jg)s)"),
    }[art] % {"alt": vorher, "neu": zielklasse.name, "jg": neu_jg}
    return Laufbahnereignis.objects.create(schueler=s, art=art, datum=datum, text=text[:250], bemerkung=(bemerkung or "")[:250],
                                           daten=daten, erstellt_von=user)


def abgangsarten():
    return [("schulwechsel", gettext("Schulwechsel")), ("umzug", gettext("Umzug / Rückkehr ins Heimatland")),
            ("abschluss", gettext("Abschluss")), ("sonstiges", gettext("Sonstiger Grund"))]


def _abschnitt_am(datum):
    return (Abschnitt.objects.filter(beginn__lte=datum, ende__gte=datum).select_related("schuljahr").first()
            or Abschnitt.objects.filter(beginn__lte=datum).select_related("schuljahr").order_by("-ende").first())


@transaction.atomic
def abgang_erfassen(s, datum, art, grund="", user=None, zeugnis=True, vermerk=""):
    """Abgang zum `datum` (letzter Schultag). Rückgabe: (Ereignis, Abgangszeugnis oder None, Hinweis)."""
    from zeugnisse.ansichten import zeugnis_fuer
    from zeugnisse.models import Zeugnis

    if s.status == "abgang":
        raise ValidationError(gettext("Der Abgang ist bereits erfasst."))
    arten = dict(abgangsarten())
    daten = {"schueler": {"status": s.status, "austrittsdatum": _iso(s.austrittsdatum), "austrittsgrund": s.austrittsgrund},
             "mitgliedschaften": [], "geloeschte_mitgliedschaften": [], "lb": [], "geloeschte_lb": [], "konto": None, "zeugnis": None}
    # Mitgliedschaften: laufende enden am Abgangstag, spätere entfallen
    for m in Mitgliedschaft.objects.filter(schueler=s).filter(Q(bis__isnull=True) | Q(bis__gt=datum)):
        if m.von > datum:
            daten["geloeschte_mitgliedschaften"].append({"gruppe": m.gruppe_id, "von": _iso(m.von), "bis": _iso(m.bis), "rolle": m.rolle})
            m.delete()
        else:
            daten["mitgliedschaften"].append([m.pk, _iso(m.bis)])
            m.bis = datum
            m.save()
    # Laufbahn: laufender Abschnitt endet, spätere entfallen
    ergebnis = "abschluss" if art == "abschluss" else "abgang"
    for lb in s.laufbahn.select_related("schuljahr"):
        anfang = lb.von or lb.schuljahr.beginn
        if anfang > datum:
            daten["geloeschte_lb"].append({"schuljahr": lb.schuljahr_id, "jahrgang": lb.jahrgang, "bildungsgang": lb.bildungsgang_id,
                                           "stammklasse": lb.stammklasse_id, "von": _iso(lb.von), "bis": _iso(lb.bis),
                                           "ergebnis": lb.ergebnis, "bemerkung": lb.bemerkung})
            lb.delete()
        elif (lb.bis or lb.schuljahr.ende) >= datum:
            daten["lb"].append({"pk": lb.pk, "bis": _iso(lb.bis), "ergebnis": lb.ergebnis})
            lb.bis = datum if datum < lb.schuljahr.ende else lb.bis
            lb.ergebnis = ergebnis
            lb.save(update_fields=["bis", "ergebnis"])
    s.status = "abgang"
    s.austrittsdatum = datum
    s.austrittsgrund = (grund or arten.get(art, ""))[:200]
    s.save()
    konto = getattr(s.person, "benutzer", None)
    if konto and konto.is_active:
        konto.is_active = False
        konto.save(update_fields=["is_active"])
        daten["konto"] = konto.pk
    z, hinweis = None, ""
    if zeugnis:
        abschnitt = _abschnitt_am(datum)
        if abschnitt is None:
            hinweis = gettext("Kein Halbjahr zum Abgangsdatum gefunden – das Abgangszeugnis wurde nicht angelegt.")
        else:
            vorhanden = Zeugnis.objects.filter(schueler=s, abschnitt=abschnitt).first()
            if vorhanden and vorhanden.freigegeben:
                hinweis = gettext("Für %(a)s ist bereits ein Zeugnis freigegeben. Um daraus ein Abgangszeugnis zu machen, "
                                  "zuerst die Freigabe aufheben.") % {"a": abschnitt}
            else:
                daten["zeugnis"] = {"pk": vorhanden.pk, "art": vorhanden.art, "datum": _iso(vorhanden.zeugnisdatum),
                                    "vermerk": vorhanden.abgangsvermerk} if vorhanden else {"neu": True}
                z = vorhanden or zeugnis_fuer(s, abschnitt)
                if not vorhanden:
                    daten["zeugnis"]["pk"] = z.pk
                z.art = Zeugnis.ABGANG
                z.zeugnisdatum = datum
                z.ort = z.ort or settings.SCHULORT
                if vermerk:
                    z.abgangsvermerk = vermerk[:1000]
                z.save()
    text = gettext("Abgang zum %(d)s: %(grund)s") % {"d": _d(datum), "grund": s.austrittsgrund or arten.get(art, "")}
    e = Laufbahnereignis.objects.create(schueler=s, art=Laufbahnereignis.ABGANG, datum=datum, text=text[:250],
                                        bemerkung=(vermerk or "")[:250], daten=daten, erstellt_von=user)
    return e, z, hinweis


def letztes_ereignis(s):
    return s.laufbahnereignisse.filter(zurueckgenommen_am__isnull=True).order_by("-erstellt_am", "-pk").first()


@transaction.atomic
def zuruecknehmen(e):
    """Nimmt ein Ereignis zurück – nur das jeweils letzte, damit die Laufbahn stimmig bleibt."""
    from zeugnisse.models import Zeugnis

    if e.zurueckgenommen_am or letztes_ereignis(e.schueler) != e:
        raise ValidationError(gettext("Zurückgenommen werden kann nur die letzte Änderung."))
    d, s = e.daten or {}, e.schueler
    if e.art == Laufbahnereignis.ABGANG:
        z = d.get("zeugnis")
        if z and z.get("pk"):
            zeugnis = Zeugnis.objects.filter(pk=z["pk"]).first()
            if zeugnis and zeugnis.freigegeben:
                raise ValidationError(gettext("Das Abgangszeugnis ist bereits freigegeben. Bitte zuerst die Freigabe aufheben."))
            if zeugnis and z.get("neu"):
                zeugnis.delete()
            elif zeugnis:
                zeugnis.art, zeugnis.zeugnisdatum, zeugnis.abgangsvermerk = z["art"], _datum(z["datum"]), z.get("vermerk", "")
                zeugnis.save()
        for pk, bis in d.get("mitgliedschaften", []):
            m = Mitgliedschaft.objects.filter(pk=pk).first()
            if m:
                m.bis = _datum(bis)
                m.save()
        for g in d.get("geloeschte_mitgliedschaften", []):
            if Gruppe.objects.filter(pk=g["gruppe"]).exists():
                Mitgliedschaft.objects.create(gruppe_id=g["gruppe"], schueler=s, von=_datum(g["von"]), bis=_datum(g["bis"]), rolle=g["rolle"])
        for lb in d.get("lb", []):
            Laufbahnabschnitt.objects.filter(pk=lb["pk"]).update(bis=_datum(lb["bis"]), ergebnis=lb["ergebnis"])
        for lb in d.get("geloeschte_lb", []):
            if Schuljahr.objects.filter(pk=lb["schuljahr"]).exists():
                Laufbahnabschnitt.objects.create(
                    schueler=s, schuljahr_id=lb["schuljahr"], jahrgang=lb["jahrgang"], bildungsgang_id=lb["bildungsgang"],
                    stammklasse_id=lb["stammklasse"] if Gruppe.objects.filter(pk=lb["stammklasse"] or 0).exists() else None,
                    von=_datum(lb["von"]), bis=_datum(lb["bis"]), ergebnis=lb["ergebnis"], bemerkung=lb["bemerkung"])
        alt = d.get("schueler") or {}
        s.status = alt.get("status", "aktiv")
        s.austrittsdatum = _datum(alt.get("austrittsdatum"))
        s.austrittsgrund = alt.get("austrittsgrund", "")
        s.save()
        if d.get("konto"):
            get_user_model().objects.filter(pk=d["konto"]).update(is_active=True)
    else:
        if d.get("neue_mitgliedschaft"):
            Mitgliedschaft.objects.filter(pk=d["neue_mitgliedschaft"]).delete()
        if d.get("mitgliedschaft"):
            pk, bis = d["mitgliedschaft"]
            m = Mitgliedschaft.objects.filter(pk=pk).first()
            if m:
                m.bis = _datum(bis)
                m.save()
        if d.get("lb_neu"):
            Laufbahnabschnitt.objects.filter(pk=d["lb_neu"]).delete()
        alt = d.get("lb_alt")
        if alt and "stammklasse" in alt:
            Laufbahnabschnitt.objects.filter(pk=alt["pk"]).update(stammklasse_id=alt["stammklasse"])
        elif alt:
            Laufbahnabschnitt.objects.filter(pk=alt["pk"]).update(bis=_datum(alt["bis"]), ergebnis=alt["ergebnis"])
    e.zurueckgenommen_am = timezone.now()
    e.save(update_fields=["zurueckgenommen_am"])
    return True


def stationen(s):
    """Zeitstrahl Aufnahme → Klasse → Versetzung → Schuljahreswechsel → Abgang → Archiv."""
    from aufnahme.models import Anmeldung

    st = []
    anm = Anmeldung.objects.filter(schueler=s).first()
    st.append({"schritt": "aufnahme", "titel": gettext("Aufnahme"), "datum": s.eintrittsdatum,
               "text": (gettext("Anmeldung %(nr)s") % {"nr": anm.nummer}) if anm else
               (gettext("Eintritt in Jahrgang %(jg)s") % {"jg": s.eintritt_jahrgang} if s.eintritt_jahrgang else ""),
               "erledigt": bool(s.eintrittsdatum or anm)})
    for lb in s.laufbahn.select_related("schuljahr", "stammklasse", "bildungsgang").order_by("schuljahr__beginn", "von", "pk"):
        st.append({"schritt": "klasse", "titel": gettext("Schuljahr %(sj)s") % {"sj": lb.schuljahr},
                   "datum": lb.von or lb.schuljahr.beginn,
                   "text": gettext("Jahrgang %(jg)s · %(k)s · %(bg)s") % {"jg": lb.jahrgang, "k": lb.stammklasse.name if lb.stammklasse else "–",
                                                                          "bg": lb.bildungsgang.lokal_name},
                   "ergebnis": lb.get_ergebnis_display() if lb.ergebnis != "laufend" else "", "erledigt": lb.ergebnis != "laufend",
                   "laufend": lb.ergebnis == "laufend"})
    if s.status == "abgang":
        st.append({"schritt": "abgang", "titel": gettext("Abgang"), "datum": s.austrittsdatum, "text": s.austrittsgrund, "erledigt": True})
        st.append({"schritt": "archiv", "titel": gettext("Archiv"), "datum": None,
                   "text": gettext("Nur lesend; Löschfristen laufen ab dem Austritt."), "erledigt": True})
    return st
