from collections import defaultdict

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import connection
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from fehlzeiten.models import Fehlzeit
from nachmittag.models import AGAngebot
from noten.berechnung import Baum, nominale_anteile, vorschlagsnote
from noten.models import Note, Unterricht
from stammdaten.models import Gruppe, Mitgliedschaft, Schuelerprofil, Schuljahr

from .rechte import darf_unterricht_sehen, ist_verwaltung


def gesundheit(request):
    """Für Docker-Healthcheck und Monitoring: prüft die Datenbankverbindung."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return JsonResponse({"status": "ok"})


@login_required
def start(request):
    sj = Schuljahr.aktuelles()
    heute = timezone.localdate()
    person = getattr(request.user, "person", None)

    meine_unterrichte = Unterricht.objects.none()
    meine_klassen = Gruppe.objects.none()
    if person and hasattr(person, "personal"):
        meine_unterrichte = (
            Unterricht.objects.filter(lehrkraft=person.personal, abschnitt__schuljahr=sj)
            .select_related("gruppe", "fach", "abschnitt")
        )
        meine_klassen = Gruppe.objects.filter(leitung=person.personal, schuljahr=sj)

    kennzahlen = None
    if ist_verwaltung(request.user):
        meine_unterrichte = (
            Unterricht.objects.filter(abschnitt__schuljahr=sj).select_related("gruppe", "fach", "abschnitt", "lehrkraft")
            if not meine_unterrichte.exists() else meine_unterrichte
        )
        kennzahlen = {
            "schueler": Schuelerprofil.objects.filter(status="aktiv").count(),
            "klassen": Gruppe.objects.filter(schuljahr=sj, typ=Gruppe.STAMMKLASSE).count(),
            "lerngruppen": Gruppe.objects.filter(schuljahr=sj, typ=Gruppe.LERNGRUPPE).count(),
            "ags": AGAngebot.objects.filter(abschnitt__schuljahr=sj).count(),
            "fehlzeiten_heute": Fehlzeit.objects.filter(
                Q(datum_von=heute) | Q(datum_von__lte=heute, datum_bis__gte=heute)
            ).count(),
            "offene_entschuldigungen": Fehlzeit.objects.filter(status="offen").count(),
        }

    klassen_info = [
        {"gruppe": g, "anzahl": Mitgliedschaft.objects.aktiv().filter(gruppe=g).count()} for g in meine_klassen
    ]
    return render(
        request,
        "portal/start.html",
        {"unterrichte": meine_unterrichte, "klassen": klassen_info, "kennzahlen": kennzahlen, "ist_verwaltung": ist_verwaltung(request.user)},
    )


@login_required
def notenuebersicht(request, pk):
    unterricht = get_object_or_404(
        Unterricht.objects.select_related("gruppe", "fach", "lehrkraft__person", "skala", "abschnitt"), pk=pk
    )
    if not darf_unterricht_sehen(request.user, unterricht):
        raise PermissionDenied

    baum = Baum(unterricht)
    anteil_ordner, anteil_ln = nominale_anteile(baum.ordner, baum.nachweise)
    spalten = [
        {"ln": ln, "pfad": pfad, "anteil": anteil_ln.get(ln.pk)} for ln, pfad in baum.nachweise_in_reihenfolge()
    ]
    # Kopfzeile: aufeinanderfolgende Leistungsnachweise desselben Ordners zusammenfassen
    gruppen = []
    for sp in spalten:
        if gruppen and gruppen[-1]["pfad"] == sp["pfad"]:
            gruppen[-1]["breite"] += 1
        else:
            gruppen.append({"pfad": sp["pfad"], "breite": 1})

    struktur = [
        {"ordner": o, "ebene": ebene, "pfad": pfad, "anteil": anteil_ordner.get(o.pk),
         "anzahl": len(baum.nachweise_in[o.pk]), "einzug": ebene * 1.4}
        for o, ebene, pfad in baum.in_reihenfolge()
    ]

    alle_noten = Note.objects.filter(leistungsnachweis__unterricht=unterricht).select_related("stufe")
    noten_je_schueler = defaultdict(list)
    for n in alle_noten:
        noten_je_schueler[n.schueler_id].append(n)

    zeilen = []
    for s in unterricht.schueler():
        noten = noten_je_schueler[s.pk]
        nach_ln = {n.leistungsnachweis_id: n for n in noten}
        zeilen.append({
            "schueler": s,
            "zellen": [nach_ln.get(sp["ln"].pk) for sp in spalten],
            "vorschlag": vorschlagsnote(unterricht, s, noten, baum),
        })

    return render(
        request,
        "portal/notenuebersicht.html",
        {"unterricht": unterricht, "spalten": spalten, "gruppen": gruppen, "zeilen": zeilen, "struktur": struktur},
    )


@login_required
def klassenliste(request, pk):
    gruppe = get_object_or_404(Gruppe.objects.select_related("leitung__person", "schuljahr"), pk=pk)
    person = getattr(request.user, "person", None)
    ist_leitung = person and gruppe.leitung and gruppe.leitung.person_id == person.pk
    if not (ist_verwaltung(request.user) or ist_leitung):
        raise PermissionDenied

    schueler = gruppe.aktuelle_mitglieder().annotate(
        offene=Count("fehlzeiten", filter=Q(fehlzeiten__status="offen"), distinct=True)
    ).order_by("person__nachname", "person__vorname")
    zeilen = []
    for s in schueler:
        fz = list(s.fehlzeiten.filter(datum_von__gte=gruppe.schuljahr.beginn, datum_von__lte=gruppe.schuljahr.ende))
        stunden_pro_tag = gruppe.schuljahr.zeitraster.count()
        zeilen.append({
            "schueler": s,
            "fehlstunden": sum(f.fehlstunden(stunden_pro_tag) for f in fz),
            "unentschuldigt": sum(f.fehlstunden(stunden_pro_tag) for f in fz if f.status == "unentschuldigt"),
            "verspaetungen": sum(1 for f in fz if f.art == Fehlzeit.VERSPAETUNG),
            "offene": s.offene,
            "kontakte": s.beziehungen.select_related("person").all(),
        })
    return render(request, "portal/klassenliste.html", {"gruppe": gruppe, "zeilen": zeilen})
