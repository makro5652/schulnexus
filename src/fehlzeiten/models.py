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
from django.utils import formats
from django.utils.translation import gettext, gettext_lazy as _
from simple_history.models import HistoricalRecords

from stammdaten.models import Schuelerprofil, Schuljahr


class Stunde(models.Model):
    schuljahr = models.ForeignKey(Schuljahr, on_delete=models.CASCADE, related_name="zeitraster", verbose_name=_("Schuljahr"))
    nummer = models.PositiveSmallIntegerField(_("Stunde"))
    beginn = models.TimeField(_("Beginn"))
    ende = models.TimeField(_("Ende"))

    class Meta:
        verbose_name = _("Unterrichtsstunde (Zeitraster)")
        verbose_name_plural = _("Zeitraster")
        ordering = ["schuljahr", "nummer"]
        unique_together = [("schuljahr", "nummer")]

    def __str__(self):
        return gettext("%(nr)s. Std. (%(von)s–%(bis)s)") % {"nr": self.nummer, "von": f"{self.beginn:%H:%M}", "bis": f"{self.ende:%H:%M}"}


class Fehlzeit(models.Model):
    GANZTAEGIG = "ganztaegig"
    STUNDEN = "stunden"
    VERSPAETUNG = "verspaetung"
    ARTEN = [(GANZTAEGIG, _("Ganztägig")), (STUNDEN, _("Einzelne Stunden")), (VERSPAETUNG, _("Verspätung"))]

    STATUS = [("offen", _("Offen")), ("entschuldigt", _("Entschuldigt")), ("unentschuldigt", _("Unentschuldigt"))]
    QUELLEN = [
        ("lehrkraft", _("Lehrkraft")),
        ("sekretariat", _("Sekretariat")),
        ("eltern", _("Eltern (Krankmeldung)")),
        ("schulisch", _("Schulische Veranstaltung")),
    ]

    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="fehlzeiten", verbose_name=_("Schüler:in"))
    art = models.CharField(_("Art"), max_length=12, choices=ARTEN, default=GANZTAEGIG)
    datum_von = models.DateField(_("Datum (von)"))
    datum_bis = models.DateField(_("Datum (bis)"), null=True, blank=True, help_text=_("nur bei mehrtägiger Abwesenheit"))
    stunde_von = models.PositiveSmallIntegerField(_("Ab Stunde"), null=True, blank=True)
    stunde_bis = models.PositiveSmallIntegerField(_("Bis Stunde"), null=True, blank=True)
    minuten = models.PositiveSmallIntegerField(_("Verspätung (Minuten)"), null=True, blank=True)
    status = models.CharField(_("Status"), max_length=14, choices=STATUS, default="offen")
    grund = models.CharField(_("Grund"), max_length=200, blank=True)
    quelle = models.CharField(_("Gemeldet durch"), max_length=12, choices=QUELLEN, default="lehrkraft")
    erfasst_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("Erfasst von")
    )
    erfasst_am = models.DateTimeField(auto_now_add=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Fehlzeit"))

    class Meta:
        verbose_name = _("Fehlzeit")
        verbose_name_plural = _("Fehlzeiten")
        ordering = ["-datum_von", "schueler__person__nachname"]

    def __str__(self):
        return gettext("%(schueler)s – %(art)s am %(datum)s") % {
            "schueler": self.schueler, "art": self.get_art_display(), "datum": formats.date_format(self.datum_von, "SHORT_DATE_FORMAT")}

    def clean(self):
        if self.art == self.GANZTAEGIG:
            if self.datum_bis and self.datum_bis < self.datum_von:
                raise ValidationError(_("'Datum (bis)' darf nicht vor 'Datum (von)' liegen."))
        elif self.art == self.STUNDEN:
            if not (self.stunde_von and self.stunde_bis):
                raise ValidationError(_("Bitte erste und letzte versäumte Stunde angeben."))
            if self.stunde_bis < self.stunde_von:
                raise ValidationError(_("'Bis Stunde' darf nicht vor 'Ab Stunde' liegen."))
            if self.datum_bis and self.datum_bis != self.datum_von:
                raise ValidationError(_("Stundenweise Fehlzeiten gelten nur für einen Tag."))
        elif self.art == self.VERSPAETUNG:
            if not self.minuten:
                raise ValidationError(_("Bitte die Verspätung in Minuten angeben."))

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
