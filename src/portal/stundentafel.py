"""
Stundentafel (ab 0.4.16.0): Wochenstunden je Fach und Jahrgang als Tabelle. Neuer Unterricht übernimmt die Stunden;
die Seite „Klassen und Gruppen“ zeigt damit die Stunden je Lehrkraft.
"""
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils.translation import gettext

from stammdaten.models import Fach, Gruppe, Stundentafel


def jahrgaenge():
    jg = {j for stufe in settings.STUFEN.values() for j in stufe}
    jg |= set(Gruppe.objects.exclude(jahrgang__isnull=True).values_list("jahrgang", flat=True).distinct())
    return sorted(jg)


def _zahl(text):
    text = (text or "").strip().replace(",", ".")
    if not text:
        return None
    try:
        wert = Decimal(text)
    except InvalidOperation:
        raise ValueError(text)
    if wert < 0 or wert > 40:
        raise ValueError(text)
    return wert.quantize(Decimal("0.1"))


@login_required
def stundentafel(request):
    if not request.user.has_perm("stammdaten.view_stundentafel"):
        raise PermissionDenied
    darf = request.user.has_perms(("stammdaten.add_stundentafel", "stammdaten.change_stundentafel", "stammdaten.delete_stundentafel"))
    jg = jahrgaenge()
    faecher = list(Fach.objects.select_related("fachbereich"))
    vorhanden = {(s.fach_id, s.jahrgang): s for s in Stundentafel.objects.all()}
    if request.method == "POST":
        if not darf:
            raise PermissionDenied
        fehler, geaendert = [], 0
        with transaction.atomic():
            for f in faecher:
                for j in jg:
                    feld = f"st_{f.pk}_{j}"
                    if feld not in request.POST:
                        continue
                    try:
                        wert = _zahl(request.POST[feld])
                    except ValueError as e:
                        fehler.append(f"{f.kuerzel} {j}: {e}")
                        continue
                    alt = vorhanden.get((f.pk, j))
                    if wert is None and alt is not None:
                        alt.delete()
                        geaendert += 1
                    elif wert is not None and alt is None:
                        Stundentafel.objects.create(fach=f, jahrgang=j, wochenstunden=wert)
                        geaendert += 1
                    elif wert is not None and alt.wochenstunden != wert:
                        alt.wochenstunden = wert
                        alt.save()
                        geaendert += 1
            if fehler:
                transaction.set_rollback(True)
        if fehler:
            messages.error(request, gettext("Nicht gespeichert – ungültige Stundenzahl (0 bis 40): %(liste)s") % {"liste": ", ".join(fehler)})
        else:
            messages.success(request, gettext("Stundentafel gespeichert (%(n)s Änderungen).") % {"n": geaendert})
        return redirect("stundentafel")
    zeilen = [{"f": f, "zellen": [{"jg": j, "feld": f"st_{f.pk}_{j}", "wert": vorhanden[(f.pk, j)].wochenstunden if (f.pk, j) in vorhanden else None}
                                  for j in jg]} for f in faecher]
    summen = [sum((s.wochenstunden for (fid, j2), s in vorhanden.items() if j2 == j), Decimal(0)) for j in jg]
    return render(request, "portal/stundentafel.html", {"jahrgaenge": jg, "zeilen": zeilen, "summen": summen, "darf": darf})
