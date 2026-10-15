"""
Sicherung und Wiederherstellung einzelner Module, PDF-Exporte und Protokoll.

Die Einträge dieser App gehören selbst zu keinem Modul: Eine Wiederherstellung verändert weder die Liste der
Sicherungen noch das Protokoll.
"""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Sicherung(models.Model):
    MANUELL = "manuell"
    AUTOMATISCH = "automatisch"
    VOR_WIEDERHERSTELLUNG = "vor_wiederherstellung"
    HOCHGELADEN = "hochgeladen"
    ARTEN = [(MANUELL, _("manuell")), (AUTOMATISCH, _("automatisch")),
             (VOR_WIEDERHERSTELLUNG, _("vor einer Wiederherstellung")), (HOCHGELADEN, _("hochgeladen"))]

    datei = models.CharField(_("Datei"), max_length=200, unique=True)
    art = models.CharField(_("Art"), max_length=24, choices=ARTEN, default=MANUELL)
    module = models.JSONField(_("Module"), default=list)
    anzahl = models.JSONField(_("Anzahl Einträge je Modul"), default=dict)
    mit_dateien = models.BooleanField(_("mit Dateien"), default=False)
    groesse = models.BigIntegerField(_("Größe (Bytes)"), default=0)
    version = models.CharField(_("Programmversion"), max_length=20, blank=True)
    bemerkung = models.CharField(_("Bemerkung"), max_length=200, blank=True)
    erstellt_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="+", verbose_name=_("Erstellt von"))
    erstellt_am = models.DateTimeField(_("Erstellt am"), auto_now_add=True)

    class Meta:
        verbose_name = _("Sicherung")
        verbose_name_plural = _("Sicherungen")
        ordering = ["-erstellt_am"]

    def __str__(self):
        return self.datei

    @property
    def pfad(self):
        return settings.MODUL_SICHERUNGEN / self.datei

    @property
    def gesamt(self):
        return sum(self.anzahl.values()) if isinstance(self.anzahl, dict) else 0


class Exportauftrag(models.Model):
    WARTET, LAEUFT, FERTIG, FEHLER = "wartet", "laeuft", "fertig", "fehler"
    STATUS = [(WARTET, _("wartet")), (LAEUFT, _("wird erstellt")), (FERTIG, _("fertig")), (FEHLER, _("Fehler"))]
    AUFTEILUNG = [("auto", _("automatisch (nach Monaten, wenn nötig)")), ("monat", _("je Monat")),
                  ("halbjahr", _("je Halbjahr")), ("keine", _("nicht aufteilen"))]

    module = models.JSONField(_("Module"), default=list)
    von = models.DateField(_("Von"), null=True, blank=True)
    bis = models.DateField(_("Bis"), null=True, blank=True)
    aufteilung = models.CharField(_("Aufteilung"), max_length=10, choices=AUFTEILUNG, default="auto")
    mit_bestand = models.BooleanField(_("Bestandsdaten ohne Datum einbeziehen"), default=True)
    mit_protokoll = models.BooleanField(_("Änderungsprotokoll einbeziehen"), default=False)
    sprache = models.CharField(_("Sprache"), max_length=8, default="de")
    status = models.CharField(_("Status"), max_length=10, choices=STATUS, default=WARTET)
    dateien = models.JSONField(_("Dateien"), default=list)
    fehler = models.TextField(_("Fehlermeldung"), blank=True)
    erstellt_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="+", verbose_name=_("Erstellt von"))
    erstellt_am = models.DateTimeField(_("Erstellt am"), auto_now_add=True)
    fertig_am = models.DateTimeField(_("Fertig am"), null=True, blank=True)

    class Meta:
        verbose_name = _("PDF-Export")
        verbose_name_plural = _("PDF-Exporte")
        ordering = ["-erstellt_am"]

    def __str__(self):
        return f"PDF-Export {self.pk}"

    @property
    def ordner(self):
        return settings.MODUL_SICHERUNGEN / "pdf" / str(self.pk)


class Protokoll(models.Model):
    AKTIONEN = [
        ("sicherung", _("Sicherung erstellt")), ("hochgeladen", _("Sicherung hochgeladen")),
        ("heruntergeladen", _("Sicherung heruntergeladen")), ("geloescht", _("Sicherung gelöscht")),
        ("wiederhergestellt", _("Wiederherstellung")), ("pdf", _("PDF-Export")), ("rechte", _("Rollen und Rechte geändert")),
        ("passwort", _("Passwort zurückgesetzt")), ("konto", _("Benutzerkonto geändert")),
        ("zweifaktor", _("Zwei-Faktor-Anmeldung")), ("noten", _("Notensperre")),
    ]
    zeit = models.DateTimeField(_("Zeit"), auto_now_add=True)
    benutzer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="+", verbose_name=_("Benutzer:in"))
    benutzername = models.CharField(_("Benutzername"), max_length=150, blank=True)
    aktion = models.CharField(_("Aktion"), max_length=20, choices=AKTIONEN)
    text = models.TextField(_("Beschreibung"), blank=True)

    class Meta:
        verbose_name = _("Protokolleintrag")
        verbose_name_plural = _("Protokoll (Sicherung und Rechte)")
        ordering = ["-zeit"]

    def __str__(self):
        return f"{self.zeit:%Y-%m-%d %H:%M} {self.get_aktion_display()}"

    @classmethod
    def schreiben(cls, benutzer, aktion, text=""):
        return cls.objects.create(benutzer=benutzer if getattr(benutzer, "pk", None) else None,
                                  benutzername=getattr(benutzer, "username", "") or "", aktion=aktion, text=text)
