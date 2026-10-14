"""
Schulkalender, Räume und Sprechtage.

- Termin: Eintrag im Schulkalender (Ferien, Feiertage, Veranstaltungen, Konferenzen, Prüfungen …), optional mit Raum.
- Raum / Raumbuchung: buchbare Räume; Buchungen dürfen sich im selben Raum zeitlich nicht überschneiden.
- Sprechtag: Elternsprechtag oder Lern- und Entwicklungsgespräche (LEG). Die (stellvertretende) Schulleitung legt
  das Zeitraster fest (Tage mit Zeitfenstern, Gesprächsdauer, Wechselzeit); jede teilnehmende Lehrkraft schränkt ihre
  Verfügbarkeit ein bzw. sperrt einzelne Zeitfenster. Eltern buchen über das Elternportal (wenn freigeschaltet),
  außerdem kann die Schule (Sekretariat, Lehrkraft, Planung) Termine eintragen.
"""
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy as _
from simple_history.models import HistoricalRecords

from stammdaten.models import Person, Personalprofil, Schuelerprofil, Schuljahr
from stammdaten.sprache import englisch_aktiv


class Raum(models.Model):
    ARTEN = [("klassenraum", _("Klassenraum")), ("fachraum", _("Fachraum")), ("sport", _("Sporthalle / Sportplatz")),
             ("aula", _("Aula / Mehrzweckraum")), ("besprechung", _("Besprechungsraum")), ("sonstiges", _("Sonstiger Raum"))]

    name = models.CharField(_("Bezeichnung"), max_length=60, unique=True)
    kuerzel = models.CharField(_("Kürzel"), max_length=20, blank=True)
    art = models.CharField(_("Art"), max_length=12, choices=ARTEN, default="klassenraum")
    plaetze = models.PositiveSmallIntegerField(_("Plätze"), null=True, blank=True)
    ausstattung = models.CharField(_("Ausstattung"), max_length=200, blank=True, help_text=_("z. B. Beamer, Abzug, 30 Tablets"))
    buchbar = models.BooleanField(_("Buchbar"), default=True)
    aktiv = models.BooleanField(_("Aktiv"), default=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Raum"))

    class Meta:
        verbose_name = _("Raum")
        verbose_name_plural = _("Räume")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Termin(models.Model):
    ARTEN = [
        ("ferien", _("Ferien")), ("feiertag", _("Feiertag")), ("veranstaltung", _("Schulveranstaltung")),
        ("konferenz", _("Konferenz / Sitzung")), ("pruefung", _("Prüfung")), ("eltern", _("Elternabend / Elterninformation")),
        ("fahrt", _("Ausflug / Fahrt")), ("frist", _("Frist / Abgabe")), ("sonstiges", _("Sonstiges")),
    ]

    titel = models.CharField(_("Titel"), max_length=150)
    titel_en = models.CharField(_("Titel (Englisch)"), max_length=150, blank=True)
    art = models.CharField(_("Art"), max_length=14, choices=ARTEN, default="veranstaltung")
    beginn = models.DateField(_("Datum / Beginn"))
    ende = models.DateField(_("Ende (mehrtägig)"), null=True, blank=True)
    uhrzeit_von = models.TimeField(_("Uhrzeit von"), null=True, blank=True, help_text=_("leer = ganztägig"))
    uhrzeit_bis = models.TimeField(_("Uhrzeit bis"), null=True, blank=True)
    raum = models.ForeignKey(Raum, on_delete=models.SET_NULL, null=True, blank=True, related_name="termine", verbose_name=_("Raum"))
    ort = models.CharField(_("Ort"), max_length=120, blank=True, help_text=_("falls kein Raum der Schule"))
    zielgruppe = models.CharField(_("Für"), max_length=120, blank=True, help_text=_("z. B. Jahrgang 9, Kollegium, alle"))
    beschreibung = models.TextField(_("Beschreibung"), blank=True)
    unterrichtsfrei = models.BooleanField(_("Unterrichtsfrei"), default=False)
    fuer_eltern = models.BooleanField(_("Im Elternportal anzeigen"), default=False)
    erstellt_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                     editable=False, verbose_name=_("Eingetragen von"))
    erstellt_am = models.DateTimeField(_("Eingetragen am"), auto_now_add=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Termin"))

    class Meta:
        verbose_name = _("Termin")
        verbose_name_plural = _("Termine")
        ordering = ["beginn", "uhrzeit_von", "titel"]

    def __str__(self):
        return self.lokal_titel

    @property
    def lokal_titel(self):
        return self.titel_en if englisch_aktiv() and self.titel_en else self.titel

    @property
    def bis(self):
        return self.ende or self.beginn

    @property
    def ganztaegig(self):
        return self.uhrzeit_von is None

    def clean(self):
        if self.ende and self.ende < self.beginn:
            raise ValidationError({"ende": _("Das Ende darf nicht vor dem Beginn liegen.")})
        if self.uhrzeit_bis and not self.uhrzeit_von:
            raise ValidationError({"uhrzeit_von": _("Bitte auch die Anfangszeit angeben.")})
        if self.uhrzeit_von and self.uhrzeit_bis and self.uhrzeit_bis <= self.uhrzeit_von and not self.ende:
            raise ValidationError({"uhrzeit_bis": _("Die Endzeit muss nach der Anfangszeit liegen.")})


class Raumbuchung(models.Model):
    raum = models.ForeignKey(Raum, on_delete=models.CASCADE, related_name="buchungen", verbose_name=_("Raum"))
    datum = models.DateField(_("Datum"))
    von = models.TimeField(_("Von"))
    bis = models.TimeField(_("Bis"))
    zweck = models.CharField(_("Zweck"), max_length=150)
    gebucht_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                    verbose_name=_("Gebucht von"))
    termin = models.ForeignKey(Termin, on_delete=models.CASCADE, null=True, blank=True, related_name="raumbuchungen",
                               verbose_name=_("Termin"))
    sprechtag = models.ForeignKey("Sprechtag", on_delete=models.CASCADE, null=True, blank=True, related_name="raumbuchungen",
                                  verbose_name=_("Sprechtag"))
    serie = models.CharField(_("Serie"), max_length=36, blank=True, editable=False)
    erstellt_am = models.DateTimeField(_("Gebucht am"), auto_now_add=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Raumbuchung"))

    class Meta:
        verbose_name = _("Raumbuchung")
        verbose_name_plural = _("Raumbuchungen")
        ordering = ["datum", "von", "raum__name"]

    def __str__(self):
        return f"{self.raum} · {self.datum:%d.%m.%Y} {self.von:%H:%M}–{self.bis:%H:%M} · {self.zweck}"

    def ueberschneidungen(self):
        return (Raumbuchung.objects.filter(raum_id=self.raum_id, datum=self.datum, von__lt=self.bis, bis__gt=self.von)
                .exclude(pk=self.pk).select_related("gebucht_von"))

    def clean(self):
        if self.von and self.bis and self.bis <= self.von:
            raise ValidationError({"bis": _("Das Ende muss nach dem Beginn liegen.")})
        if self.raum_id and self.datum and self.von and self.bis:
            andere = self.ueberschneidungen().first()
            if andere:
                raise ValidationError(gettext("Der Raum ist zu dieser Zeit bereits gebucht: %(b)s") % {
                    "b": f"{andere.von:%H:%M}–{andere.bis:%H:%M} {andere.zweck}"})


class Sprechtag(models.Model):
    ELTERNSPRECHTAG, LEG = "elternsprechtag", "leg"
    ARTEN = [(ELTERNSPRECHTAG, _("Elternsprechtag")), (LEG, _("Lern- und Entwicklungsgespräche (LEG)"))]
    ENTWURF, VERFUEGBARKEIT, BUCHUNG, GESCHLOSSEN = "entwurf", "verfuegbarkeit", "buchung", "geschlossen"
    STATUS = [(ENTWURF, _("Entwurf")), (VERFUEGBARKEIT, _("Lehrkräfte tragen Verfügbarkeit ein")),
              (BUCHUNG, _("Buchung offen")), (GESCHLOSSEN, _("Buchung geschlossen"))]

    art = models.CharField(_("Art"), max_length=16, choices=ARTEN, default=ELTERNSPRECHTAG)
    titel = models.CharField(_("Titel"), max_length=120)
    schuljahr = models.ForeignKey(Schuljahr, on_delete=models.PROTECT, related_name="sprechtage", verbose_name=_("Schuljahr"))
    jahrgang_von = models.PositiveSmallIntegerField(_("ab Jahrgang"), null=True, blank=True)
    jahrgang_bis = models.PositiveSmallIntegerField(_("bis Jahrgang"), null=True, blank=True)
    slot_minuten = models.PositiveSmallIntegerField(_("Gesprächsdauer (Minuten)"), default=10)
    puffer_minuten = models.PositiveSmallIntegerField(_("Wechselzeit (Minuten)"), default=0,
                                                      help_text=_("Pause zwischen zwei Gesprächen"))
    max_je_kind = models.PositiveSmallIntegerField(_("Höchstens Gespräche je Kind"), null=True, blank=True,
                                                   help_text=_("leer = unbegrenzt; bei LEG in der Regel 1"))
    eltern_buchen = models.BooleanField(_("Eltern buchen selbst (Elternportal)"), default=True)
    buchung_ab = models.DateTimeField(_("Buchung möglich ab"), null=True, blank=True)
    buchung_bis = models.DateTimeField(_("Buchung möglich bis"), null=True, blank=True)
    hinweis = models.TextField(_("Hinweis für Eltern"), blank=True)
    status = models.CharField(_("Status"), max_length=16, choices=STATUS, default=ENTWURF)
    erstellt_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                     editable=False, verbose_name=_("Angelegt von"))
    erstellt_am = models.DateTimeField(_("Angelegt am"), auto_now_add=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Sprechtag"))

    class Meta:
        verbose_name = _("Sprechtag")
        verbose_name_plural = _("Sprechtage")
        ordering = ["-erstellt_am"]

    def __str__(self):
        return self.titel

    def clean(self):
        if self.jahrgang_von and self.jahrgang_bis and self.jahrgang_bis < self.jahrgang_von:
            raise ValidationError({"jahrgang_bis": _("Bitte einen gültigen Jahrgangsbereich angeben.")})
        if not 5 <= (self.slot_minuten or 0) <= 120:
            raise ValidationError({"slot_minuten": _("Die Gesprächsdauer muss zwischen 5 und 120 Minuten liegen.")})
        if self.buchung_ab and self.buchung_bis and self.buchung_bis <= self.buchung_ab:
            raise ValidationError({"buchung_bis": _("Das Ende des Buchungszeitraums muss nach dem Beginn liegen.")})

    @property
    def ist_leg(self):
        return self.art == self.LEG

    def jahrgang_passt(self, jahrgang):
        if jahrgang is None:
            return self.jahrgang_von is None and self.jahrgang_bis is None
        return (self.jahrgang_von is None or jahrgang >= self.jahrgang_von) and (self.jahrgang_bis is None or jahrgang <= self.jahrgang_bis)

    def buchung_offen(self, jetzt=None):
        """Eltern dürfen buchen bzw. absagen."""
        jetzt = jetzt or timezone.now()
        return (self.status == self.BUCHUNG and self.eltern_buchen
                and (self.buchung_ab is None or self.buchung_ab <= jetzt) and (self.buchung_bis is None or jetzt <= self.buchung_bis))

    @property
    def tage(self):
        return sorted({z.datum for z in self.zeitfenster.all()})

    def slots(self):
        """Alle Gesprächszeiten des Rasters als Liste (beginn, ende), zeitlich sortiert."""
        ergebnis = []
        for z in self.zeitfenster.all():
            ergebnis.extend(z.slots(self.slot_minuten, self.puffer_minuten))
        return sorted(ergebnis)


class Zeitfenster(models.Model):
    """Zeitraum an einem Tag, in dem Gespräche stattfinden (mehrere je Tag möglich, z. B. vor und nach einer Pause)."""

    sprechtag = models.ForeignKey(Sprechtag, on_delete=models.CASCADE, related_name="zeitfenster", verbose_name=_("Sprechtag"))
    datum = models.DateField(_("Datum"))
    von = models.TimeField(_("Von"))
    bis = models.TimeField(_("Bis"))

    class Meta:
        verbose_name = _("Zeitfenster")
        verbose_name_plural = _("Zeitfenster")
        ordering = ["datum", "von"]

    def __str__(self):
        return f"{self.datum:%d.%m.%Y} {self.von:%H:%M}–{self.bis:%H:%M}"

    def clean(self):
        if self.von and self.bis and self.bis <= self.von:
            raise ValidationError({"bis": _("Das Ende muss nach dem Beginn liegen.")})

    def slots(self, minuten, puffer=0):
        tz = timezone.get_current_timezone()
        beginn = timezone.make_aware(datetime.combine(self.datum, self.von), tz)
        ende = timezone.make_aware(datetime.combine(self.datum, self.bis), tz)
        schritt, dauer = timedelta(minutes=minuten + puffer), timedelta(minutes=minuten)
        ergebnis = []
        while beginn + dauer <= ende:
            ergebnis.append((beginn, beginn + dauer))
            beginn += schritt
        return ergebnis


class Teilnahme(models.Model):
    """Lehrkraft beim Sprechtag mit Raum und eigener Verfügbarkeit (gesperrte Gesprächszeiten)."""

    sprechtag = models.ForeignKey(Sprechtag, on_delete=models.CASCADE, related_name="teilnahmen", verbose_name=_("Sprechtag"))
    lehrkraft = models.ForeignKey(Personalprofil, on_delete=models.CASCADE, related_name="sprechtage", verbose_name=_("Lehrkraft"))
    raum = models.ForeignKey(Raum, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name=_("Raum"))
    nimmt_teil = models.BooleanField(_("Nimmt teil"), default=True)
    gesperrt = models.JSONField(_("Gesperrte Zeiten"), default=list, blank=True)
    bemerkung = models.CharField(_("Hinweis für Eltern"), max_length=200, blank=True, help_text=_("z. B. „nur bis 17 Uhr“"))
    bestaetigt_am = models.DateTimeField(_("Verfügbarkeit bestätigt am"), null=True, blank=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Teilnahme"))

    class Meta:
        verbose_name = _("Teilnahme")
        verbose_name_plural = _("Teilnahmen")
        unique_together = [("sprechtag", "lehrkraft")]
        ordering = ["lehrkraft__person__nachname"]

    def __str__(self):
        return f"{self.lehrkraft} · {self.sprechtag}"

    @staticmethod
    def schluessel(beginn):
        return timezone.localtime(beginn).strftime("%Y-%m-%dT%H:%M")

    def ist_gesperrt(self, beginn):
        return self.schluessel(beginn) in set(self.gesperrt or [])


class Gespraechstermin(models.Model):
    PORTAL, SCHULE = "portal", "schule"
    UEBER = [(PORTAL, _("Elternportal")), (SCHULE, _("Schule"))]

    sprechtag = models.ForeignKey(Sprechtag, on_delete=models.CASCADE, related_name="termine", verbose_name=_("Sprechtag"))
    teilnahme = models.ForeignKey(Teilnahme, on_delete=models.CASCADE, related_name="termine", verbose_name=_("Lehrkraft"))
    beginn = models.DateTimeField(_("Beginn"))
    ende = models.DateTimeField(_("Ende"))
    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="gespraechstermine", verbose_name=_("Schüler:in"))
    eltern = models.ForeignKey(Person, on_delete=models.SET_NULL, null=True, blank=True, related_name="gespraechstermine",
                               verbose_name=_("Eltern / Kontaktperson"))
    anliegen = models.CharField(_("Anliegen"), max_length=300, blank=True)
    ueber = models.CharField(_("Gebucht über"), max_length=8, choices=UEBER, default=SCHULE)
    gebucht_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                    verbose_name=_("Gebucht von"))
    erstellt_am = models.DateTimeField(_("Gebucht am"), auto_now_add=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Gesprächstermin"))

    class Meta:
        verbose_name = _("Gesprächstermin")
        verbose_name_plural = _("Gesprächstermine")
        ordering = ["beginn", "teilnahme__lehrkraft__person__nachname"]
        constraints = [models.UniqueConstraint(fields=["teilnahme", "beginn"], name="ein_gespraech_je_zeit")]

    def __str__(self):
        return f"{timezone.localtime(self.beginn):%d.%m. %H:%M} · {self.teilnahme.lehrkraft} · {self.schueler}"

    def ueberschneidung_familie(self):
        """Andere Termine desselben Kindes bzw. derselben Kontaktperson, die sich zeitlich überschneiden."""
        q = Q(schueler_id=self.schueler_id)
        if self.eltern_id:
            q |= Q(eltern_id=self.eltern_id)
        return (Gespraechstermin.objects.filter(sprechtag_id=self.sprechtag_id, beginn__lt=self.ende, ende__gt=self.beginn)
                .filter(q).exclude(pk=self.pk))
