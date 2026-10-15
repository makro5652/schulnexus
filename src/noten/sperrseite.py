"""Seite „Notensperre“ (ab 0.4.8.0): Stand je Klasse und Halbjahr, sperren, freigeben, zurück zur Automatik."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext

from sicherung.models import Protokoll
from stammdaten.models import Abschnitt, Gruppe, Mitgliedschaft

from . import rechte
from .ansichten import _abschnitt_waehlen
from .models import Notensperre
from .sperre import Sperrstand


def _darf_seite(user):
    return rechte.darf_noten_sperren(user, None) or rechte.ist_koordination(user)


@login_required
def notensperre(request):
    if not _darf_seite(request.user):
        raise PermissionDenied
    if request.method == "POST":
        a = get_object_or_404(Abschnitt, pk=request.POST.get("abschnitt"))
        k = get_object_or_404(Gruppe, pk=request.POST.get("klasse"), typ=Gruppe.STAMMKLASSE)
        if not rechte.darf_noten_sperren(request.user, k.jahrgang):
            raise PermissionDenied
        aktion, grund = request.POST.get("aktion"), (request.POST.get("grund") or "").strip()[:200]
        if aktion in ("sperren", "freigeben"):
            Notensperre.objects.update_or_create(abschnitt=a, klasse=k, defaults={
                "gesperrt": aktion == "sperren", "grund": grund, "geaendert_von": request.user})
            text = gettext("Noten gesperrt") if aktion == "sperren" else gettext("Noten zur Korrektur freigegeben")
        elif aktion == "automatik":
            Notensperre.objects.filter(abschnitt=a, klasse=k).delete()
            text = gettext("Notensperre wieder automatisch (Konferenz/Zeugnisfreigabe)")
        else:
            raise PermissionDenied
        Protokoll.schreiben(request.user, "noten", f"{k.name} {a}: {text}" + (f" – {grund}" if grund else ""))
        messages.success(request, f"{k.name}: {text}.")
        return redirect(reverse("notensperre") + f"?abschnitt={a.pk}")

    abschnitte, a = _abschnitt_waehlen(request)
    zeilen = []
    if a is not None:
        stand = Sperrstand(a)


        for k in Gruppe.objects.filter(schuljahr=a.schuljahr, typ=Gruppe.STAMMKLASSE).order_by("jahrgang", "name"):
            if not rechte.darf_noten_sperren(request.user, k.jahrgang):
                continue
            mitglieder = set(Mitgliedschaft.objects.filter(gruppe=k).values_list("schueler_id", flat=True))
            freigegeben = len(mitglieder & stand.freigegeben)
            konf = stand.konferenz.get(k.pk)
            zeilen.append({"k": k, "explizit": stand.explizit.get(k.pk), "konferenz": konf,
                           "konferenz_gehalten": stand.konferenz_gehalten(k.pk), "freigegeben": freigegeben,
                           "anzahl": len(mitglieder), "gesperrt": stand.klasse_gesperrt(k.pk),
                           "teilweise": not stand.klasse_gesperrt(k.pk) and freigegeben > 0
                           and k.pk not in stand.explizit})

    return render(request, "noten/notensperre.html", {"abschnitte": abschnitte, "a": a, "zeilen": zeilen})
