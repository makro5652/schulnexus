"""
Zeilenweise Rechte der Elternkommunikation.

- Schreiben an die Eltern einer Schülerin / eines Schülers: wer sie/ihn unterrichtet, die Klassenleitung,
  die Stufenkoordination sowie Sekretariat, Verwaltungsleitung und Schulleitung.
- Lesen eines Gesprächs: wer es begonnen oder darin geschrieben hat, die Klassenleitung, die Stufenkoordination
  und die Schulleitung. Sekretariat und Verwaltungsleitung sehen Zeugnisempfang und automatische Fehlzeiten-
  Nachrichten (nicht aber persönliche Gespräche zwischen Lehrkräften und Eltern).
- Benachrichtigungsregeln: Schulleitung und erweiterte Schulleitung (Verwaltungsleitung, Mittel- und
  Oberstufenkoordination); die Koordinationen nur für die Jahrgänge ihrer Stufe.
"""
from django.db.models import Q

from portal import rollen as R
from portal.rechte import (_in_gruppen, ist_klassenleitung_von, ist_schulleitung, ist_stufenkoordination_von,
                           ist_verwaltung, klassenleitung_schueler_ids, koordinierte_jahrgaenge, koordinierte_schueler_ids,
                           unterrichtete_schueler_ids)

ERWEITERTE_SCHULLEITUNG = {R.SCHULLEITUNG, R.VERWALTUNGSLEITUNG, R.MITTELSTUFE, R.OBERSTUFE}


def darf_schreiben(user, schueler) -> bool:
    if not user.is_authenticated:
        return False
    return (ist_verwaltung(user) or ist_klassenleitung_von(user, schueler) or ist_stufenkoordination_von(user, schueler)
            or schueler.pk in unterrichtete_schueler_ids(user))


def anschreibbare_schueler_ids(user):
    """IDs der Schüler:innen, deren Eltern die Person anschreiben darf; None = alle."""
    if ist_verwaltung(user):
        return None
    return klassenleitung_schueler_ids(user) | koordinierte_schueler_ids(user) | unterrichtete_schueler_ids(user)


def sichtbar_filter(user):
    """Q-Filter auf Gespraech."""
    from .models import Gespraech

    if ist_schulleitung(user):
        return Q()
    q = Q(erstellt_von=user) | Q(beitraege__von_benutzer=user)
    ids = klassenleitung_schueler_ids(user) | koordinierte_schueler_ids(user)
    if ids:
        q |= Q(schueler__in=ids)
    if ist_verwaltung(user):
        q |= Q(art__in=[Gespraech.ZEUGNIS, Gespraech.FEHLZEITEN])
    return q


def sichtbare_gespraeche(user):
    from .models import Gespraech

    if not user.is_authenticated:
        return Gespraech.objects.none()
    qs = Gespraech.objects.all()
    if ist_schulleitung(user):
        return qs
    return qs.filter(pk__in=Gespraech.objects.filter(sichtbar_filter(user)).values("pk"))


def darf_sehen(user, gespraech) -> bool:
    return sichtbare_gespraeche(user).filter(pk=gespraech.pk).exists()


def darf_antworten(user, gespraech) -> bool:
    """Im Verlauf schreiben: wer das Gespräch sieht und die Eltern anschreiben darf."""
    return darf_sehen(user, gespraech) and darf_schreiben(user, gespraech.schueler)


def darf_verwalten(user, gespraech) -> bool:
    """Abschließen, Empfang vermerken, erneut senden: Beginnende, Klassenleitung, Koordination, Verwaltung."""
    if not darf_sehen(user, gespraech):
        return False
    return (gespraech.erstellt_von_id == user.pk or ist_verwaltung(user) or ist_klassenleitung_von(user, gespraech.schueler)
            or ist_stufenkoordination_von(user, gespraech.schueler))


# ---------------------------------------------------------------- Benachrichtigungsregeln

def darf_regeln(user) -> bool:
    return user.is_authenticated and _in_gruppen(user, ERWEITERTE_SCHULLEITUNG)


def regel_jahrgaenge(user):
    """Erlaubte Jahrgänge für Regeln: None = alle (Schulleitung, Verwaltungsleitung), sonst die koordinierten."""
    if ist_schulleitung(user) or _in_gruppen(user, {R.VERWALTUNGSLEITUNG}):
        return None
    return koordinierte_jahrgaenge(user)


def darf_regel_bearbeiten(user, regel) -> bool:
    if not darf_regeln(user):
        return False
    erlaubt = regel_jahrgaenge(user)
    if erlaubt is None:
        return True
    jahrgaenge = regel.jahrgaenge()
    return jahrgaenge is not None and jahrgaenge <= erlaubt


# ---------------------------------------------------------------- Zeugnisempfang

def darf_zeugnisempfang(user, klasse) -> bool:
    """Empfangsbestätigung für Zeugnisse anfordern: Klassenleitung, Stufenkoordination, Verwaltung."""
    if ist_verwaltung(user):
        return True
    person = getattr(user, "person", None)
    if person and klasse.leitung_id and klasse.leitung.person_id == person.pk:
        return True
    return klasse.jahrgang in koordinierte_jahrgaenge(user)
