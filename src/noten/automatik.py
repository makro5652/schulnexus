"""
Zeugnisnoten automatisch aus den Einzelnoten (ab 0.4.15.0).

Ändert sich etwas, das den Vorschlag beeinflusst (Note, Leistungsnachweis, Ordner, Unterricht) oder wird eine
Zeugnisnote entfernt, wird der Unterricht vorgemerkt und nach dem Abschluss der Transaktion einmal neu berechnet
(siehe zeugnisnoten.automatisch). Im 2. Halbjahr mit Jahresnote hängt die Note vom 1. Halbjahr ab – dann wird
das 2. Halbjahr desselben Fachs mitgerechnet.
"""
import threading

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

_lokal = threading.local()


def _offen():
    if getattr(_lokal, "offen", None) is None:
        _lokal.offen = set()
    return _lokal.offen


def vormerken(unterricht_id):
    if unterricht_id is None or getattr(_lokal, "aktiv", False):
        return
    _offen().add(unterricht_id)
    # Ein Rückruf je Änderung; der erste nach dem Commit erledigt alle vorgemerkten, die übrigen finden nichts mehr vor.
    transaction.on_commit(_ausfuehren)


def _ausfuehren():
    ids, _lokal.offen = _offen(), None
    if ids:
        aktualisieren(ids)


def aktualisieren(ids):
    from . import zeugnisnoten as Z
    from .models import Unterricht

    ids = set(ids)
    for u in Unterricht.objects.filter(pk__in=ids, abschnitt__nummer=1).select_related("abschnitt"):
        ids |= set(Unterricht.objects.filter(abschnitt__schuljahr_id=u.abschnitt.schuljahr_id, abschnitt__nummer=2,
                                             fach_id=u.fach_id, anteil_vorhalbjahr__gt=0).values_list("pk", flat=True))
    _lokal.aktiv = True
    try:
        geaendert = 0
        for u in Unterricht.objects.filter(pk__in=ids).select_related("skala", "abschnitt", "gruppe", "fach"):
            with transaction.atomic():
                geaendert += Z.automatisch(u)
        return geaendert
    finally:
        _lokal.aktiv = False


def _verbinden():
    from .models import Bewertungsordner, Leistungsnachweis, Note, Unterricht, Zeugnisnote

    def note(sender, instance, **kwargs):
        ln = Leistungsnachweis.objects.filter(pk=instance.leistungsnachweis_id).values_list("unterricht_id", flat=True).first()
        vormerken(ln)

    def ueber_unterricht(sender, instance, **kwargs):
        vormerken(instance.unterricht_id)

    def unterricht(sender, instance, created=False, **kwargs):
        if not created:
            vormerken(instance.pk)

    def zeugnisnote(sender, instance, **kwargs):
        # Entfernt oder im 1. Halbjahr geändert (Grundlage der Jahresnote) → neu berechnen
        if kwargs.get("signal") is post_delete or instance.quelle != "auto":
            vormerken(instance.unterricht_id)

    for signal in (post_save, post_delete):
        receiver(signal, sender=Note, weak=False)(note)
        receiver(signal, sender=Leistungsnachweis, weak=False)(ueber_unterricht)
        receiver(signal, sender=Bewertungsordner, weak=False)(ueber_unterricht)
        receiver(signal, sender=Zeugnisnote, weak=False)(zeugnisnote)
    receiver(post_save, sender=Unterricht, weak=False)(unterricht)
