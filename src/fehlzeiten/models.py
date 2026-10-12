"""
Fehlzeiten.

Ohne Untis-Anbindung arbeitet das Modul mit einem eigenen Zeitraster
(1. Stunde, 2. Stunde ...). Erfasst werden:
- ganztägige Abwesenheit (auch über mehrere Tage),
- stundenweise Abwesenheit (von Stunde X bis Stunde Y an einem Tag),
- Verspätungen in Minuten.
"""
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from simple_history.models import HistoricalRecords

from stammdaten.models import Schuelerprofil, Schuljahr


class Stunde(models.Model):
    schuljahr = models.ForeignKey(Schuljahr, on_delete=models.CASCADE, related_name="zeitraster", verbose_name="Schuljahr")
    nummer = models.PositiveSmallIntegerField("Stunde")
    beginn = models.TimeField("Beginn")
    ende = models.TimeField("Ende")

    class Meta:
        verbose_name = "Unterrichtsstunde (Zeitraster)"
        verbose_name_plural = "Zeitraster"
        ordering = ["schuljahr", "nummer"]
        unique_together = [("schuljahr", "nummer")]

    def __str__(self):
        return f"{self.nummer}. Std. ({self.beginn:%H:%M}–{self.ende:%H:%M})"


class Fehlzeit(models.Model):
    GANZTAEGIG = "ganztaegig"
    STUNDEN = "stunden"
    VERSPAETUNG = "verspaetung"
    ARTEN = [(GANZTAEGIG, "Ganztägig"), (STUNDEN, "Einzelne Stunden"), (VERSPAETUNG, "Verspätung")]

    STATUS = [("offen", "Offen"), ("entschuldigt", "Entschuldigt"), ("unentschuldigt", "Unentschuldigt")]
    QUELLEN = [
        ("lehrkraft", "Lehrkraft"),
        ("sekretariat", "Sekretariat"),
        ("eltern", "Eltern (Krankmeldung)"),
        ("schulisch", "Schulische Veranstaltung"),
    ]

    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="fehlzeiten", verbose_name="Schüler:in")
    art = models.CharField("Art", max_length=12, choices=ARTEN, default=GANZTAEGIG)
    datum_von = models.DateField("Datum (von)")
    datum_bis = models.DateField("Datum (bis)", null=True, blank=True, help_text="nur bei mehrtägiger Abwesenheit")
    stunde_von = models.PositiveSmallIntegerField("Ab Stunde", null=True, blank=True)
    stunde_bis = models.PositiveSmallIntegerField("Bis Stunde", null=True, blank=True)
    minuten = models.PositiveSmallIntegerField("Verspätung (Minuten)", null=True, blank=True)
    status = models.CharField("Status", max_length=14, choices=STATUS, default="offen")
    grund = models.CharField("Grund", max_length=200, blank=True)
    quelle = models.CharField("Gemeldet durch", max_length=12, choices=QUELLEN, default="lehrkraft")
    erfasst_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Erfasst von"
    )
    erfasst_am = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords(verbose_name="Änderungsprotokoll Fehlzeit")

    class Meta:
        verbose_name = "Fehlzeit"
        verbose_name_plural = "Fehlzeiten"
        ordering = ["-datum_von", "schueler__person__nachname"]

    def __str__(self):
        return f"{self.schueler} – {self.get_art_display()} am {self.datum_von:%d.%m.%Y}"

    def clean(self):
        if self.art == self.GANZTAEGIG:
            if self.datum_bis and self.datum_bis < self.datum_von:
                raise ValidationError("'Datum (bis)' darf nicht vor 'Datum (von)' liegen.")
        elif self.art == self.STUNDEN:
            if not (self.stunde_von and self.stunde_bis):
                raise ValidationError("Bitte erste und letzte versäumte Stunde angeben.")
            if self.stunde_bis < self.stunde_von:
                raise ValidationError("'Bis Stunde' darf nicht vor 'Ab Stunde' liegen.")
            if self.datum_bis and self.datum_bis != self.datum_von:
                raise ValidationError("Stundenweise Fehlzeiten gelten nur für einen Tag.")
        elif self.art == self.VERSPAETUNG:
            if not self.minuten:
                raise ValidationError("Bitte die Verspätung in Minuten angeben.")

    def schultage(self):
        """Montag bis Freitag im Zeitraum (Ferien werden in einer späteren Ausbaustufe berücksichtigt)."""
        ende = self.datum_bis or self.datum_von
        tag, anzahl = self.datum_von, 0
        while tag <= ende:
            if tag.weekday() < 5:
                anzahl += 1
            tag += timedelta(days=1)
        return anzahl

    def fehlstunden(self, stunden_pro_tag: int | None = None) -> int:
        if self.art == self.VERSPAETUNG:
            return 0
        if self.art == self.STUNDEN:
            return self.stunde_bis - self.stunde_von + 1
        if stunden_pro_tag is None:
            schuljahr = Schuljahr.objects.filter(beginn__lte=self.datum_von, ende__gte=self.datum_von).first()
            stunden_pro_tag = schuljahr.zeitraster.count() if schuljahr else 0
        return self.schultage() * stunden_pro_tag
