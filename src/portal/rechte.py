"""Zentrale Rechteprüfung. Rollen werden als Django-Benutzergruppen abgebildet (siehe portal/rollen.py)."""
from django.conf import settings
from django.db.models import Q

from . import rollen as R

VERWALTUNGSGRUPPEN = {R.SEKRETARIAT, R.VERWALTUNGSLEITUNG, R.SCHULLEITUNG}
PERSONALGRUPPEN = {R.HR, R.VERWALTUNGSLEITUNG, R.SCHULLEITUNG}
FOERDERGRUPPEN = {R.FOERDERKOORDINATION, R.SCHULLEITUNG}
LEITUNGSGRUPPEN = {R.SCHULLEITUNG}
FINANZGRUPPEN = {R.FINANZEN, R.VERWALTUNGSLEITUNG, R.SCHULLEITUNG}
SYSTEMGRUPPEN = {R.VERWALTUNGSLEITUNG, R.SCHULLEITUNG}
STUFENGRUPPEN = {R.MITTELSTUFE: "mittelstufe", R.OBERSTUFE: "oberstufe"}


def _in_gruppen(user, gruppen) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    # Pro Anfrage zwischenspeichern – wird auf Listen-Seiten oft aufgerufen.
    cache = getattr(user, "_gruppen_cache", None)
    if cache is None:
        cache = set(user.groups.values_list("name", flat=True))
        user._gruppen_cache = cache
    return bool(cache & gruppen)


def ist_verwaltung(user) -> bool:
    return _in_gruppen(user, VERWALTUNGSGRUPPEN)


def ist_personalverwaltung(user) -> bool:
    return _in_gruppen(user, PERSONALGRUPPEN)


def ist_foerderkoordination(user) -> bool:
    return _in_gruppen(user, FOERDERGRUPPEN)


def ist_schulleitung(user) -> bool:
    return _in_gruppen(user, LEITUNGSGRUPPEN)


def ist_it(user) -> bool:
    """IT-Administration (oder Superuser): Benutzer, Rollen und Einzelrechte verwalten."""
    return _in_gruppen(user, {R.IT})


def darf_sichern(user) -> bool:
    """Sicherung, Wiederherstellung und PDF-Export: Schulleitung und IT."""
    return _in_gruppen(user, {R.SCHULLEITUNG, R.IT})


def ist_finanzen(user) -> bool:
    return _in_gruppen(user, FINANZGRUPPEN)


def ist_systemverwaltung(user) -> bool:
    """Schuljahre, Kataloge, Benutzerkonten: Verwaltungsleitung und Schulleitung."""
    return _in_gruppen(user, SYSTEMGRUPPEN)


def koordinierte_stufen(user) -> list:
    """Schlüssel der Stufen, die die Person koordiniert (Schulleitung: alle)."""
    if not user.is_authenticated:
        return []
    if ist_schulleitung(user):
        return list(settings.STUFEN)
    return [stufe for gruppe, stufe in STUFENGRUPPEN.items() if _in_gruppen(user, {gruppe})]


def koordinierte_jahrgaenge(user) -> set:
    jahrgaenge = set()
    for stufe in koordinierte_stufen(user):
        jahrgaenge |= set(settings.STUFEN.get(stufe, ()))
    return jahrgaenge


def koordinierte_schueler_ids(user) -> set:
    """Schüler:innen der Stammklassen in den koordinierten Jahrgängen (aktuelles Schuljahr)."""
    from stammdaten.models import Gruppe, Mitgliedschaft, Schuljahr

    if hasattr(user, "_ko_ids"):
        return user._ko_ids
    ids = set()
    jahrgaenge = koordinierte_jahrgaenge(user) if not ist_schulleitung(user) else set()
    if jahrgaenge:
        ids = set(Mitgliedschaft.objects.aktiv().filter(
            gruppe__typ=Gruppe.STAMMKLASSE, gruppe__schuljahr=Schuljahr.aktuelles(), gruppe__jahrgang__in=jahrgaenge,
        ).values_list("schueler_id", flat=True))
    user._ko_ids = ids
    return ids


def ist_stufenkoordination_von(user, schueler) -> bool:
    return schueler.pk in koordinierte_schueler_ids(user)


def personal_von(user):
    person = getattr(user, "person", None) if user.is_authenticated else None
    return getattr(person, "personal", None) if person else None


def klassenleitung_schueler_ids(user) -> set:
    """Schüler:innen der Stammklassen, die die Person im aktuellen Schuljahr leitet."""
    from stammdaten.models import Gruppe, Mitgliedschaft, Schuljahr

    if hasattr(user, "_kl_ids"):
        return user._kl_ids
    personal = personal_von(user)
    ids = set()
    if personal:
        ids = set(Mitgliedschaft.objects.aktiv().filter(
            gruppe__leitung=personal, gruppe__typ=Gruppe.STAMMKLASSE, gruppe__schuljahr=Schuljahr.aktuelles(),
        ).values_list("schueler_id", flat=True))
    user._kl_ids = ids
    return ids


def unterrichtete_schueler_ids(user) -> set:
    """Schüler:innen aller Lerngruppen, in denen die Person im aktuellen Schuljahr unterrichtet."""
    from noten.models import Unterricht
    from stammdaten.models import Mitgliedschaft, Schuljahr

    if hasattr(user, "_ut_ids"):
        return user._ut_ids
    personal = personal_von(user)
    ids = set()
    if personal:
        gruppen = Unterricht.objects.filter(lehrkraft=personal, abschnitt__schuljahr=Schuljahr.aktuelles()).values("gruppe")
        ids = set(Mitgliedschaft.objects.aktiv().filter(gruppe__in=gruppen).values_list("schueler_id", flat=True))
    user._ut_ids = ids
    return ids


def ist_klassenleitung_von(user, schueler) -> bool:
    return schueler.pk in klassenleitung_schueler_ids(user)


def darf_akte_sehen(user, schueler) -> bool:
    """Schülerakte im Portal: Verwaltung, Leitung, Förderkoordination und die Klassenleitung."""
    return (ist_verwaltung(user) or ist_foerderkoordination(user) or ist_klassenleitung_von(user, schueler)
            or ist_stufenkoordination_von(user, schueler))


def darf_foerderung_sehen(user, schueler) -> bool:
    """Förderpläne: Förderkoordination, Leitung, Klassenleitung und alle, die die Person unterrichten."""
    return (ist_foerderkoordination(user) or ist_klassenleitung_von(user, schueler)
            or ist_stufenkoordination_von(user, schueler) or schueler.pk in unterrichtete_schueler_ids(user))


def darf_foerderung_bearbeiten(user, schueler) -> bool:
    return ist_foerderkoordination(user) or ist_klassenleitung_von(user, schueler) or ist_stufenkoordination_von(user, schueler)


def darf_nachteilsausgleich_sehen(user, schueler) -> bool:
    """Nachteilsausgleiche braucht zusätzlich das Sekretariat (Prüfungsorganisation)."""
    return darf_foerderung_sehen(user, schueler) or ist_verwaltung(user)


def foerder_schueler_filter(user, feld="schueler"):
    """Q-Filter für Listen: alle Schüler:innen, deren Förderunterlagen die Person sehen darf."""
    if ist_foerderkoordination(user):
        return Q()
    ids = klassenleitung_schueler_ids(user) | unterrichtete_schueler_ids(user) | koordinierte_schueler_ids(user)
    return Q(**{f"{feld}__in": ids})


def darf_unterricht_sehen(user, unterricht) -> bool:
    if ist_verwaltung(user):
        return True
    person = getattr(user, "person", None)
    if person is None:
        return False
    if unterricht.lehrkraft.person_id == person.pk:
        return True
    # Stufenkoordination: alle Gruppen der koordinierten Jahrgänge (gemischte Gruppen über ihre Mitglieder)
    jahrgaenge = koordinierte_jahrgaenge(user)
    if jahrgaenge:
        if unterricht.gruppe.jahrgang in jahrgaenge:
            return True
        if unterricht.gruppe.jahrgang is None and set(
                unterricht.gruppe.mitgliedschaften.values_list("schueler_id", flat=True)) & koordinierte_schueler_ids(user):
            return True
    # Klassenleitung darf die Noten der eigenen Stammklasse einsehen.
    return unterricht.gruppe.leitung_id is not None and unterricht.gruppe.leitung.person_id == person.pk


# ---------------------------------------------------------------- Dokumente / Anhänge

def dokument_stufen_fuer(user, person):
    """Zugriffsstufen, die die Person bei Dokumenten zu `person` sehen (und vergeben) darf."""
    if user.is_superuser:
        return {"akte", "verwaltung", "foerderung", "leitung"}
    schueler = getattr(person, "schueler", None)
    stufen = set()
    if schueler is not None:
        if darf_akte_sehen(user, schueler):
            stufen.add("akte")
        if ist_verwaltung(user) or ist_finanzen(user):
            stufen.add("verwaltung")
        if darf_foerderung_bearbeiten(user, schueler):
            stufen.add("foerderung")
    elif hasattr(person, "personal"):
        # Personalunterlagen: ausschließlich Personalverwaltung und Leitung.
        if ist_personalverwaltung(user):
            stufen |= {"akte", "verwaltung", "foerderung"}
    elif ist_verwaltung(user) or ist_finanzen(user):  # Eltern / Kontaktpersonen
        stufen |= {"akte", "verwaltung"}
    if ist_schulleitung(user):
        stufen.add("leitung")
    return stufen


def darf_dokument_sehen(user, dokument) -> bool:
    if not user.is_authenticated:
        return False
    if dokument.hochgeladen_von_id == user.pk:
        return True
    return dokument.zugriffsstufe in dokument_stufen_fuer(user, dokument.person)


def darf_dokument_loeschen(user, dokument) -> bool:
    return darf_dokument_sehen(user, dokument) and (
        dokument.hochgeladen_von_id == user.pk or ist_verwaltung(user) or ist_personalverwaltung(user)
    )


def sichtbare_dokumente(user, qs):
    """Filtert eine Dokument-Abfrage auf das, was die Person sehen darf."""
    if user.is_superuser:
        return qs
    erlaubt = [d.pk for d in qs.select_related("person", "person__schueler", "person__personal") if darf_dokument_sehen(user, d)]
    return qs.filter(pk__in=erlaubt)
