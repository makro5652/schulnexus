"""Benutzerkonten, Rollen und Einzelrechte (nur IT-Administration)."""
import secrets
import string

from django.contrib.auth.models import Group, Permission
from django.db import transaction
from django.utils.translation import gettext as _

from portal import rollen as R
from portal.models import Benutzereinstellung

from .models import Protokoll

AKTIONEN = ("view", "add", "change", "delete")


class KontoFehler(Exception):
    pass


def verwaltete_rechte():
    return (Permission.objects.filter(content_type__app_label__in=R.APPS)
            .exclude(content_type__app_label="auth", content_type__model="permission")
            .select_related("content_type").order_by("content_type__app_label", "content_type__model", "codename"))


def rechte_tabelle(benutzer):
    """
    Je App: Zeilen (Modell → Zellen für ansehen/anlegen/ändern/löschen) und Sonderrechte.
    Zelle: {"perm", "rolle" (bool), "zustand" ("", "+", "-")}.
    """
    from django.apps import apps

    aus_rollen = set(Permission.objects.filter(group__user=benutzer).values_list("pk", flat=True))
    erteilt = set(benutzer.user_permissions.values_list("pk", flat=True))
    einstellung = Benutzereinstellung.objects.filter(benutzer=benutzer).first()
    entzogen = set(einstellung.entzogene_rechte.values_list("pk", flat=True)) if einstellung else set()
    gruppen = {}
    for p in verwaltete_rechte():
        ct = p.content_type
        app = gruppen.setdefault(ct.app_label, {"name": str(apps.get_app_config(ct.app_label).verbose_name), "modelle": {},
                                                "sonder": [], "geaendert": 0})
        zelle = {"perm": p, "rolle": p.pk in aus_rollen, "zustand": "+" if p.pk in erteilt else "-" if p.pk in entzogen else ""}
        if zelle["zustand"]:
            app["geaendert"] += 1
        aktion = p.codename.split("_", 1)[0]
        if aktion in AKTIONEN and p.codename == f"{aktion}_{ct.model}":
            model = ct.model_class()
            if model is None or model.__name__.startswith("Historical"):
                continue
            zeile = app["modelle"].setdefault(ct.model, {"name": str(model._meta.verbose_name_plural), "zellen": {}})
            zeile["zellen"][aktion] = zelle
        else:
            zelle["name"] = str(p.name)
            app["sonder"].append(zelle)
    ergebnis = []
    for label in R.APPS:
        if label in gruppen:
            g = gruppen[label]
            g["label"] = label
            g["zeilen"] = sorted(([z["name"], [z["zellen"].get(a) for a in AKTIONEN]] for z in g["modelle"].values()),
                                 key=lambda e: e[0].lower())
            ergebnis.append(g)
    return ergebnis


def _anzahl_admins(ohne=None):
    from django.contrib.auth import get_user_model

    qs = get_user_model().objects.filter(is_active=True, is_superuser=True)
    if ohne is not None:
        qs = qs.exclude(pk=ohne.pk)
    return qs.count()


@transaction.atomic
def konto_speichern(benutzer, rollen, aktiv, durch):
    """Rollen setzen (bekannte Rollen; andere Gruppen bleiben), Vollzugriff für IT, Konto sperren/entsperren."""
    alt_rollen = set(benutzer.groups.values_list("name", flat=True))
    neu_rollen = {r for r in rollen if r in R.REIHENFOLGE}
    if benutzer == durch and R.IT in alt_rollen and R.IT not in neu_rollen:
        raise KontoFehler(_("Sie können sich die Rolle IT-Administration nicht selbst entziehen."))
    if benutzer == durch and not aktiv:
        raise KontoFehler(_("Sie können Ihr eigenes Konto nicht sperren."))
    wird_admin = R.IT in neu_rollen
    if benutzer.is_superuser and (not wird_admin or not aktiv) and R.IT in alt_rollen and _anzahl_admins(ohne=benutzer) == 0:
        raise KontoFehler(_("Es muss mindestens ein aktives Konto mit Vollzugriff bleiben."))
    behalten = alt_rollen - set(R.REIHENFOLGE)
    benutzer.groups.set(Group.objects.filter(name__in=neu_rollen | behalten))
    if wird_admin:
        benutzer.is_superuser = True
    elif R.IT in alt_rollen:
        benutzer.is_superuser = False
    benutzer.is_staff = bool(neu_rollen & R.PORTAL_ROLLEN) or benutzer.is_superuser
    benutzer.is_active = aktiv
    benutzer.save(update_fields=["is_superuser", "is_staff", "is_active"])
    teile = []
    if neu_rollen - alt_rollen:
        teile.append("+ " + ", ".join(str(R.ANZEIGE.get(r, r)) for r in sorted(neu_rollen - alt_rollen)))
    if (alt_rollen & set(R.REIHENFOLGE)) - neu_rollen:
        teile.append("− " + ", ".join(str(R.ANZEIGE.get(r, r)) for r in sorted((alt_rollen & set(R.REIHENFOLGE)) - neu_rollen)))
    teile.append(_("aktiv") if aktiv else _("gesperrt"))
    Protokoll.schreiben(durch, "konto", f"{benutzer.username}: " + "; ".join(teile))


@transaction.atomic
def einzelrechte_speichern(benutzer, zustaende, durch):
    """zustaende: {permission_pk: "" | "+" | "-"}"""
    erlaubt = set(verwaltete_rechte().values_list("pk", flat=True))
    plus = {pk for pk, z in zustaende.items() if z == "+" and pk in erlaubt}
    minus = {pk for pk, z in zustaende.items() if z == "-" and pk in erlaubt}
    alt_plus = set(benutzer.user_permissions.filter(pk__in=erlaubt).values_list("pk", flat=True))
    einstellung, _neu = Benutzereinstellung.objects.get_or_create(benutzer=benutzer)
    alt_minus = set(einstellung.entzogene_rechte.values_list("pk", flat=True))
    andere = set(benutzer.user_permissions.exclude(pk__in=erlaubt).values_list("pk", flat=True))
    benutzer.user_permissions.set(plus | andere)
    einstellung.entzogene_rechte.set(minus)
    namen = {p.pk: f"{p.content_type.app_label}.{p.codename}" for p in Permission.objects.filter(pk__in=plus ^ alt_plus | minus ^ alt_minus)
             .select_related("content_type")}
    aenderungen = ([f"+{namen[p]}" for p in sorted(plus - alt_plus)] + [f"(+){namen[p]} aufgehoben" for p in sorted(alt_plus - plus)]
                   + [f"−{namen[p]}" for p in sorted(minus - alt_minus)] + [f"(−){namen[p]} aufgehoben" for p in sorted(alt_minus - minus)])
    if aenderungen:
        Protokoll.schreiben(durch, "rechte", f"{benutzer.username}: " + ", ".join(aenderungen))
    return len(aenderungen)


def passwort_zuruecksetzen(benutzer, durch):
    zeichen = string.ascii_letters + string.digits
    while True:
        pw = "-".join("".join(secrets.choice(zeichen) for _ in range(4)) for _ in range(4))
        if any(c.isdigit() for c in pw) and any(c.isupper() for c in pw):
            break
    benutzer.set_password(pw)
    benutzer.save(update_fields=["password"])
    Protokoll.schreiben(durch, "passwort", benutzer.username)
    return pw
