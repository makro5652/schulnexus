"""
Ablauf der Sprechtage (Elternsprechtag und LEG): Teilnehmende, Verfügbarkeit, Buchung, Absage, Raumbelegung.

Wer spricht mit wem?
- Elternsprechtag: alle Lehrkräfte, die das Kind im Halbjahr des Sprechtags unterrichten, und die Klassenleitung.
- LEG (Lern- und Entwicklungsgespräch): die Klassenleitung, gemeinsam mit Kind und Eltern.
"""
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext

from stammdaten.models import Abschnitt, Beziehung, Gruppe, Mitgliedschaft, Schuelerprofil

from .models import Gespraechstermin, Raumbuchung, Sprechtag, Teilnahme


def stichtag(st):
    tage = st.tage
    return tage[0] if tage else st.schuljahr.stichtag()


def klassen(st):
    qs = Gruppe.objects.filter(schuljahr=st.schuljahr, typ=Gruppe.STAMMKLASSE)
    if st.jahrgang_von:
        qs = qs.filter(jahrgang__gte=st.jahrgang_von)
    if st.jahrgang_bis:
        qs = qs.filter(jahrgang__lte=st.jahrgang_bis)
    return qs


def _unterricht(st):
    from noten.models import Unterricht

    tag = stichtag(st)
    a = Abschnitt.objects.filter(schuljahr=st.schuljahr, beginn__lte=tag, ende__gte=tag).first()
    qs = Unterricht.objects.filter(abschnitt=a) if a else Unterricht.objects.filter(abschnitt__schuljahr=st.schuljahr)
    return qs


def schueler_ids(st):
    tag = stichtag(st)
    return set(Mitgliedschaft.objects.aktiv(tag).filter(gruppe__in=klassen(st)).values_list("schueler_id", flat=True))


def lehrkraefte_vorschlag(st):
    """IDs der Lehrkräfte, die nach Art und Jahrgängen teilnehmen."""
    ids = set(klassen(st).exclude(leitung=None).values_list("leitung_id", flat=True))
    if not st.ist_leg:
        tag = stichtag(st)
        gruppen = Mitgliedschaft.objects.aktiv(tag).filter(schueler_id__in=schueler_ids(st)).values("gruppe")
        ids |= set(_unterricht(st).filter(gruppe__in=gruppen).values_list("lehrkraft_id", flat=True))
    ids.discard(None)
    return ids


@transaction.atomic
def teilnahmen_ergaenzen(st):
    vorhanden = set(st.teilnahmen.values_list("lehrkraft_id", flat=True))
    neu = [Teilnahme(sprechtag=st, lehrkraft_id=i) for i in lehrkraefte_vorschlag(st) - vorhanden]
    Teilnahme.objects.bulk_create(neu)
    return len(neu)


def teilnahmen_fuer_schueler(st, s):
    """Teilnahmen (Lehrkräfte), bei denen für dieses Kind ein Gespräch gebucht werden kann."""
    tag = stichtag(st)
    klasse = s.stammklasse(st.schuljahr, tag)
    if klasse is None or not st.jahrgang_passt(klasse.jahrgang):
        return Teilnahme.objects.none()
    ids = {klasse.leitung_id} if klasse.leitung_id else set()
    if not st.ist_leg:
        gruppen = Mitgliedschaft.objects.aktiv(tag).filter(schueler=s).values("gruppe")
        ids |= set(_unterricht(st).filter(gruppe__in=gruppen).values_list("lehrkraft_id", flat=True))
    return (st.teilnahmen.filter(lehrkraft_id__in=ids, nimmt_teil=True)
            .select_related("lehrkraft__person", "raum").order_by("lehrkraft__person__nachname"))


def schueler_fuer_teilnahme(t):
    """Schüler:innen, mit deren Eltern diese Lehrkraft beim Sprechtag sprechen kann."""
    st = t.sprechtag
    tag = stichtag(st)
    alle = schueler_ids(st)
    geleitet = set(Mitgliedschaft.objects.aktiv(tag).filter(gruppe__in=klassen(st).filter(leitung=t.lehrkraft))
                   .values_list("schueler_id", flat=True))
    ids = geleitet
    if not st.ist_leg:
        gruppen = _unterricht(st).filter(lehrkraft=t.lehrkraft).values("gruppe")
        ids |= set(Mitgliedschaft.objects.aktiv(tag).filter(gruppe__in=gruppen, schueler_id__in=alle)
                   .values_list("schueler_id", flat=True))
    return Schuelerprofil.objects.filter(pk__in=ids, status="aktiv").select_related("person").order_by(
        "person__nachname", "person__vorname")


# ---------------------------------------------------------------- Raster und Verfügbarkeit

def raster(t, mit_terminen=True):
    """Gesprächszeiten einer Lehrkraft: [{"beginn", "ende", "schluessel", "status": frei|gesperrt|gebucht, "termin"}]."""
    st = t.sprechtag
    termine = {}
    if mit_terminen:
        termine = {Teilnahme.schluessel(g.beginn): g for g in t.termine.select_related("schueler__person", "eltern")}
    zeilen = []
    for beginn, ende in st.slots():
        k = Teilnahme.schluessel(beginn)
        g = termine.get(k)
        status = "gebucht" if g else ("gesperrt" if t.ist_gesperrt(beginn) or not t.nimmt_teil else "frei")
        zeilen.append({"beginn": beginn, "ende": ende, "schluessel": k, "status": status, "termin": g,
                       "datum": timezone.localtime(beginn).date()})
    return zeilen


def freie_zeiten(t):
    return [z for z in raster(t) if z["status"] == "frei"]


def sperren_setzen(t, gesperrt):
    """Speichert die gesperrten Zeiten; bereits gebuchte Zeiten bleiben buchbar (sie werden nicht gesperrt)."""
    gueltig = {Teilnahme.schluessel(b) for b, _e in t.sprechtag.slots()}
    gebucht = {Teilnahme.schluessel(b) for b in t.termine.values_list("beginn", flat=True)}
    t.gesperrt = sorted((set(gesperrt) & gueltig) - gebucht)
    t.save(update_fields=["gesperrt"])
    return len(t.gesperrt)


def nur_verfuegbar(t, datum, von, bis):
    """Sperrt an diesem Tag alle Zeiten außerhalb von–bis (Einschränkung der Verfügbarkeit)."""
    gesperrt = set(t.gesperrt or [])
    for beginn, ende in t.sprechtag.slots():
        lokal_b, lokal_e = timezone.localtime(beginn), timezone.localtime(ende)
        if lokal_b.date() != datum:
            continue
        k = Teilnahme.schluessel(beginn)
        if lokal_b.time() < von or lokal_e.time() > bis:
            gesperrt.add(k)
        else:
            gesperrt.discard(k)
    return sperren_setzen(t, gesperrt)


# ---------------------------------------------------------------- Buchen und Absagen

def kinder_von(person):
    """Kinder, für die die Person Auskunfts- oder Sorgerecht hat (aktive Schüler:innen)."""
    ids = Beziehung.objects.filter(person=person).filter(Q(sorgerecht=True) | Q(auskunftsrecht=True)).values("schueler")
    return Schuelerprofil.objects.filter(pk__in=ids, status="aktiv").select_related("person").order_by("person__vorname")


def buchen(t, beginn, schueler, *, eltern=None, user=None, ueber=Gespraechstermin.SCHULE, anliegen=""):
    """Bucht eine Gesprächszeit. Wirft ValidationError mit verständlicher Begründung."""
    st = t.sprechtag
    if ueber == Gespraechstermin.PORTAL:
        if not st.buchung_offen():
            raise ValidationError(gettext("Die Buchung ist derzeit nicht geöffnet."))
        if eltern is None or not kinder_von(eltern).filter(pk=schueler.pk).exists():
            raise ValidationError(gettext("Für dieses Kind können Sie keinen Termin buchen."))
    elif st.status == Sprechtag.ENTWURF:
        raise ValidationError(gettext("Der Sprechtag ist noch ein Entwurf."))
    if not teilnahmen_fuer_schueler(st, schueler).filter(pk=t.pk).exists():
        raise ValidationError(gettext("%(lk)s ist für %(kind)s bei diesem Sprechtag nicht vorgesehen.")
                              % {"lk": t.lehrkraft.person.anzeigename, "kind": schueler.person.anzeigename})
    zeit = next((z for z in raster(t) if z["beginn"] == beginn), None)
    if zeit is None:
        raise ValidationError(gettext("Diese Zeit gibt es im Raster nicht."))
    if zeit["status"] == "gebucht":
        raise ValidationError(gettext("Diese Zeit ist bereits vergeben."))
    if zeit["status"] == "gesperrt":
        raise ValidationError(gettext("Zu dieser Zeit steht die Lehrkraft nicht zur Verfügung."))
    if st.max_je_kind and Gespraechstermin.objects.filter(sprechtag=st, schueler=schueler).count() >= st.max_je_kind:
        raise ValidationError(gettext("Für %(kind)s sind bereits %(n)s Gespräche gebucht (Höchstzahl).")
                              % {"kind": schueler.person.anzeigename, "n": st.max_je_kind})
    if Gespraechstermin.objects.filter(sprechtag=st, schueler=schueler, teilnahme=t).exists():
        raise ValidationError(gettext("Mit dieser Lehrkraft ist für %(kind)s bereits ein Gespräch gebucht.")
                              % {"kind": schueler.person.anzeigename})
    g = Gespraechstermin(sprechtag=st, teilnahme=t, beginn=zeit["beginn"], ende=zeit["ende"], schueler=schueler, eltern=eltern,
                         ueber=ueber, gebucht_von=user, anliegen=(anliegen or "")[:300])
    if g.ueberschneidung_familie().exists():
        raise ValidationError(gettext("Zu dieser Zeit ist bereits ein anderes Gespräch gebucht."))
    try:
        with transaction.atomic():
            g.save()
    except IntegrityError:
        raise ValidationError(gettext("Diese Zeit wurde gerade vergeben. Bitte eine andere wählen."))
    return g


def darf_absagen_eltern(g, person):
    return g.sprechtag.buchung_offen() and (g.eltern_id == person.pk or kinder_von(person).filter(pk=g.schueler_id).exists())


# ---------------------------------------------------------------- Räume

@transaction.atomic
def raeume_buchen(st, user=None):
    """Belegt die Räume der Lehrkräfte für alle Zeitfenster; Überschneidungen werden übersprungen und gemeldet."""
    st.raumbuchungen.all().delete()
    konflikte, n = [], 0
    raeume = {t.raum_id: t.raum for t in st.teilnahmen.filter(nimmt_teil=True, raum__isnull=False).select_related("raum")}
    for raum in raeume.values():
        for z in st.zeitfenster.all():
            b = Raumbuchung(raum=raum, datum=z.datum, von=z.von, bis=z.bis, zweck=st.titel[:150], gebucht_von=user, sprechtag=st)
            andere = b.ueberschneidungen().first()
            if andere:
                konflikte.append(f"{raum}: {andere}")
                continue
            b.save()
            n += 1
    return n, konflikte
