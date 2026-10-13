"""
Zeilenweise Rechte für Neuanmeldungen.

Modellrechte (portal/rollen.py) legen fest, WAS eine Rolle darf; hier wird festgelegt, WELCHE Anmeldungen:
Sekretariat, Verwaltungsleitung, Schulleitung und Finanzen sehen alle; die Stufenkoordination sieht
Anmeldungen ihrer Jahrgänge und solche, bei denen noch kein Jahrgang eingetragen ist.
"""
from django.db.models import Q

from portal.context import darf_portal_nutzen
from portal.rechte import ist_finanzen, ist_verwaltung, koordinierte_jahrgaenge

from .models import Anmeldung


def darf_aufnahme(user) -> bool:
    return user.is_authenticated and darf_portal_nutzen(user) and user.has_perm("aufnahme.view_anmeldung")


def sieht_alle(user) -> bool:
    return ist_verwaltung(user) or ist_finanzen(user)


def anmeldungen_fuer(user):
    if not darf_aufnahme(user):
        return Anmeldung.objects.none()
    qs = Anmeldung.objects.all()
    if sieht_alle(user):
        return qs
    jahrgaenge = koordinierte_jahrgaenge(user)
    if not jahrgaenge:
        return qs.none()
    return qs.filter(Q(jahrgang__in=jahrgaenge) | Q(jahrgang__isnull=True))


def darf_sehen(user, anmeldung) -> bool:
    if not darf_aufnahme(user):
        return False
    if sieht_alle(user):
        return True
    return anmeldung.jahrgang is None or anmeldung.jahrgang in koordinierte_jahrgaenge(user)


def _offen_und_sichtbar(user, a):
    return not a.abgeschlossen and darf_sehen(user, a)


def darf_bearbeiten(user, a) -> bool:
    """Angaben zum Kind, Status, vorläufige Klasse."""
    return user.has_perm("aufnahme.change_anmeldung") and _offen_und_sichtbar(user, a)


def darf_kontakte_bearbeiten(user, a) -> bool:
    return user.has_perm("aufnahme.change_anmeldekontakt") and _offen_und_sichtbar(user, a)


def darf_dateien_hochladen(user, a) -> bool:
    return user.has_perm("aufnahme.add_anmeldedatei") and _offen_und_sichtbar(user, a)


def darf_datei_loeschen(user, datei) -> bool:
    return (_offen_und_sichtbar(user, datei.anmeldung)
            and (user.has_perm("aufnahme.delete_anmeldedatei") or datei.hochgeladen_von_id == user.pk))


def darf_abhaken(user, a) -> bool:
    return user.has_perm("aufnahme.change_anmeldepunkt") and _offen_und_sichtbar(user, a)


def darf_checkliste_zusammenstellen(user, a) -> bool:
    """Punkte ergänzen oder entfernen."""
    return (user.has_perm("aufnahme.add_anmeldepunkt") and user.has_perm("aufnahme.delete_anmeldepunkt")
            and _offen_und_sichtbar(user, a))


def darf_uebernehmen(user, a) -> bool:
    return (user.has_perm("aufnahme.uebernehmen_anmeldung") and user.has_perm("stammdaten.add_person")
            and user.has_perm("stammdaten.add_schuelerprofil") and _offen_und_sichtbar(user, a))


def darf_loeschen(user, a) -> bool:
    return user.has_perm("aufnahme.delete_anmeldung") and darf_sehen(user, a) and not a.abgeschlossen


def erlaubte_jahrgaenge(user):
    """None = alle; sonst die Jahrgänge, die die Stufenkoordination eintragen darf."""
    return None if sieht_alle(user) else sorted(koordinierte_jahrgaenge(user))


def eigene_zustaendigkeiten(user) -> set:
    """Zuständigkeiten der Checkliste, die zur Rolle der Person passen (für „meine offenen Punkte“)."""
    from portal import rollen as R

    if user.is_superuser:
        return {"sekretariat", "finanzen", "koordination", "schulleitung"}
    namen = getattr(user, "_gruppen_cache", None)
    if namen is None:
        namen = set(user.groups.values_list("name", flat=True))
    z = set()
    if namen & {R.SEKRETARIAT, R.VERWALTUNGSLEITUNG}:
        z.add("sekretariat")
    if namen & {R.FINANZEN, R.VERWALTUNGSLEITUNG}:
        z.add("finanzen")
    if namen & {R.MITTELSTUFE, R.OBERSTUFE}:
        z.add("koordination")
    if R.SCHULLEITUNG in namen:
        z.add("schulleitung")
    return z
