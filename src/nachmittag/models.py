"""
Nachmittagsprogramm (AGs).

Jedes AG-Angebot besitzt eine eigene Gruppe vom Typ "AG"; die Zuteilung erzeugt
dort ganz normale Mitgliedschaften. Dadurch funktionieren Listen, Fehlzeiten
und Kommunikation für AGs genauso wie für Klassen.
"""
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from stammdaten.models import Abschnitt, Gruppe, Personalprofil, Schuelerprofil

WOCHENTAGE = [(0, _("Montag")), (1, _("Dienstag")), (2, _("Mittwoch")), (3, _("Donnerstag")), (4, _("Freitag")), (5, _("Samstag"))]


class AGAngebot(models.Model):
    abschnitt = models.ForeignKey(Abschnitt, on_delete=models.PROTECT, related_name="ag_angebote", verbose_name=_("Halbjahr"))
    titel = models.CharField(_("Titel"), max_length=80)
    beschreibung = models.TextField(_("Beschreibung"), blank=True)
    leitung = models.ForeignKey(Personalprofil, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("Leitung"))
    externe_leitung = models.CharField(_("Externe Leitung"), max_length=80, blank=True)
    wochentag = models.PositiveSmallIntegerField(_("Wochentag"), choices=WOCHENTAGE)
    beginn = models.TimeField(_("Beginn"))
    ende = models.TimeField(_("Ende"))
    raum = models.CharField(_("Raum / Ort"), max_length=40, blank=True)
    kapazitaet = models.PositiveSmallIntegerField(_("Plätze"))
    jahrgang_min = models.PositiveSmallIntegerField(_("ab Jahrgang"), default=5)
    jahrgang_max = models.PositiveSmallIntegerField(_("bis Jahrgang"), default=12)
    anmeldung_offen = models.BooleanField(_("Wahl geöffnet"), default=True)
    gruppe = models.OneToOneField(
        Gruppe, null=True, blank=True, editable=False, on_delete=models.SET_NULL, related_name="ag_angebot"
    )
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll AG-Angebot"))

    class Meta:
        verbose_name = _("AG-Angebot")
        verbose_name_plural = _("AG-Angebote")
        ordering = ["abschnitt", "wochentag", "beginn", "titel"]

    def __str__(self):
        return f"{self.titel} ({self.get_wochentag_display()}, {self.beginn:%H:%M})"

    def clean(self):
        if self.beginn and self.ende and self.ende <= self.beginn:
            raise ValidationError(_("Das Ende muss nach dem Beginn liegen."))
        if self.jahrgang_max < self.jahrgang_min:
            raise ValidationError(_("'bis Jahrgang' darf nicht kleiner als 'ab Jahrgang' sein."))

    def save(self, *args, **kwargs):
        if self.gruppe_id is None:
            name = f"AG {self.titel}"
            self.gruppe, _ = Gruppe.objects.get_or_create(
                schuljahr=self.abschnitt.schuljahr, name=name[:60],
                defaults={"typ": Gruppe.AG, "leitung": self.leitung},
            )
        super().save(*args, **kwargs)

    @property
    def belegt(self):
        return self.zuteilungen.count()


class AGWahl(models.Model):
    PRIORITAETEN = [(1, _("Erstwunsch")), (2, _("Zweitwunsch")), (3, _("Drittwunsch"))]

    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="ag_wahlen", verbose_name=_("Schüler:in"))
    angebot = models.ForeignKey(AGAngebot, on_delete=models.CASCADE, related_name="wahlen", verbose_name=_("AG-Angebot"))
    prioritaet = models.PositiveSmallIntegerField(_("Priorität"), choices=PRIORITAETEN)
    erstellt = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("AG-Wunsch")
        verbose_name_plural = _("AG-Wünsche")
        ordering = ["schueler", "prioritaet"]
        unique_together = [("schueler", "angebot")]

    def __str__(self):
        return f"{self.schueler}: {self.get_prioritaet_display()} {self.angebot.titel}"

    def clean(self):
        if not (self.schueler_id and self.angebot_id and self.prioritaet):
            return
        doppelt = AGWahl.objects.filter(
            schueler_id=self.schueler_id, prioritaet=self.prioritaet, angebot__abschnitt=self.angebot.abschnitt
        ).exclude(pk=self.pk)
        if doppelt.exists():
            raise ValidationError(_("Für diese Priorität existiert in diesem Halbjahr bereits ein Wunsch."))


class AGZuteilung(models.Model):
    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="ag_zuteilungen", verbose_name=_("Schüler:in"))
    angebot = models.ForeignKey(AGAngebot, on_delete=models.CASCADE, related_name="zuteilungen", verbose_name=_("AG-Angebot"))
    erfuellter_wunsch = models.PositiveSmallIntegerField(_("Erfüllter Wunsch"), null=True, blank=True)
    erstellt = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("AG-Zuteilung")
        verbose_name_plural = _("AG-Zuteilungen")
        unique_together = [("schueler", "angebot")]

    def __str__(self):
        return f"{self.schueler} → {self.angebot.titel}"
