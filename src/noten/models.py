"""
Notenmodul.

- Notenskala + Notenstufen: frei konfigurierbar (Sek I mit Tendenzen, 0–15 Punkte ...).
- Notenschlüssel: eigene Tabellen Prozent -> Notenstufe (z. B. für Klassenarbeiten mit BE).
- Gewichtungsvorlage + Kategorien: Startvorlage, z. B. schriftlich 50 %, sonstige Mitarbeit 50 %.
- Unterricht: Gruppe x Fach x Lehrkraft x Halbjahr.
- Bewertungsordner: frei benennbar und verschachtelbar (z. B. „Sonstige Mitarbeit › Quartal 1“),
  jeder mit eigenem Gewicht relativ zu seiner Ebene.
- Leistungsnachweis + Note: einzelne Bewertungen mit freier Bezeichnung, Datum und Gewicht im Ordner.
- Zeugnisnote: von der Lehrkraft festgesetzt; Abweichung vom Vorschlag braucht Begründung.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext, gettext_lazy as _, pgettext_lazy
from simple_history.models import HistoricalRecords

from stammdaten.sprache import LokalerNameMixin
from stammdaten.models import Abschnitt, Fach, Gruppe, Personalprofil, Schuelerprofil


class Notenskala(LokalerNameMixin, models.Model):
    name = models.CharField(_("Bezeichnung"), max_length=60, unique=True)
    name_en = models.CharField(_("Bezeichnung (Englisch)"), max_length=60, blank=True)
    beschreibung = models.TextField(_("Beschreibung"), blank=True)
    hoeher_ist_besser = models.BooleanField(
        _("Höherer Wert ist besser"), default=False,
        help_text=_("Aus bei Noten 1–6 (1 ist am besten), an bei Punkten 0–15."),
    )
    nachkommastellen = models.PositiveSmallIntegerField(_("Nachkommastellen im Schnitt"), default=2)
    gefaehrdung_ab = models.DecimalField(
        _("Gefährdung ab Wert"), max_digits=5, decimal_places=2, null=True, blank=True,
        help_text=_("Ab diesem Durchschnitt wird eine Gefährdung markiert, z. B. 4,50 (Sek I) oder 4,49 Punkte (Sek II)."),
    )

    class Meta:
        verbose_name = _("Notenskala")
        verbose_name_plural = _("Notenskalen")

    def runden(self, wert: Decimal) -> Decimal:
        quant = Decimal(1).scaleb(-self.nachkommastellen)
        return wert.quantize(quant, rounding=ROUND_HALF_UP)

    def ist_gefaehrdet(self, wert: Decimal | None) -> bool:
        if wert is None or self.gefaehrdung_ab is None:
            return False
        return wert <= self.gefaehrdung_ab if self.hoeher_ist_besser else wert >= self.gefaehrdung_ab

    def naechste_stufe(self, wert: Decimal):
        """Notenstufe, deren interner Wert dem Schnitt am nächsten liegt."""
        stufen = list(self.stufen.all())
        if not stufen or wert is None:
            return None
        return min(stufen, key=lambda s: (abs(s.wert - wert), s.reihenfolge))


class Notenstufe(models.Model):
    skala = models.ForeignKey(Notenskala, on_delete=models.CASCADE, related_name="stufen", verbose_name=_("Skala"))
    bezeichnung = models.CharField(_("Anzeige"), max_length=10, help_text=_("z. B. 2+ oder 11"))
    wert = models.DecimalField(_("Interner Wert"), max_digits=5, decimal_places=2, help_text=_("z. B. 1,70 für 2+"))
    reihenfolge = models.PositiveSmallIntegerField(_("Reihenfolge"), default=0)

    class Meta:
        verbose_name = _("Notenstufe")
        verbose_name_plural = _("Notenstufen")
        ordering = ["skala", "reihenfolge"]
        unique_together = [("skala", "bezeichnung")]

    def __str__(self):
        return self.bezeichnung


class Notenschluessel(models.Model):
    name = models.CharField(_("Bezeichnung"), max_length=80, unique=True)
    skala = models.ForeignKey(Notenskala, on_delete=models.PROTECT, verbose_name=_("Skala"))
    beschreibung = models.TextField(_("Beschreibung"), blank=True)

    class Meta:
        verbose_name = _("Notenschlüssel")
        verbose_name_plural = _("Notenschlüssel")

    def __str__(self):
        return self.name

    def stufe_fuer_prozent(self, prozent: Decimal):
        """Höchste Schwelle, die erreicht wurde."""
        schwelle = self.schwellen.filter(min_prozent__lte=prozent).order_by("-min_prozent").first()
        return schwelle.stufe if schwelle else None


class Schluesselschwelle(models.Model):
    schluessel = models.ForeignKey(Notenschluessel, on_delete=models.CASCADE, related_name="schwellen", verbose_name=_("Schlüssel"))
    min_prozent = models.DecimalField(
        _("ab Prozent"), max_digits=5, decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    stufe = models.ForeignKey(Notenstufe, on_delete=models.PROTECT, verbose_name=_("Notenstufe"))

    class Meta:
        verbose_name = _("Schwelle")
        verbose_name_plural = _("Schwellen")
        ordering = ["schluessel", "-min_prozent"]
        unique_together = [("schluessel", "min_prozent")]

    def __str__(self):
        return gettext("ab %(prozent)s %% → %(stufe)s") % {"prozent": self.min_prozent, "stufe": self.stufe}

    def clean(self):
        if self.stufe_id and self.schluessel_id and self.stufe.skala_id != self.schluessel.skala_id:
            raise ValidationError(_("Die Notenstufe gehört nicht zur Skala dieses Schlüssels."))


class Gewichtungsvorlage(models.Model):
    name = models.CharField(_("Bezeichnung"), max_length=80, unique=True, help_text=_("z. B. Naturwissenschaften Sek I"))
    beschreibung = models.TextField(_("Beschreibung / Fachschaftsbeschluss"), blank=True)

    class Meta:
        verbose_name = _("Gewichtungsvorlage")
        verbose_name_plural = _("Gewichtungsvorlagen")

    def __str__(self):
        summe = sum(k.anteil for k in self.kategorien.all())
        return f"{self.name} ({summe} %)"

    def clean(self):
        pass


class Leistungskategorie(models.Model):
    vorlage = models.ForeignKey(Gewichtungsvorlage, on_delete=models.CASCADE, related_name="kategorien", verbose_name=_("Vorlage"))
    name = models.CharField(_("Kategorie"), max_length=60, help_text=_("z. B. Schriftlich, Sonstige Leistungen"))
    anteil = models.DecimalField(
        _("Anteil in %"), max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    class Meta:
        verbose_name = _("Leistungskategorie")
        verbose_name_plural = _("Leistungskategorien")
        ordering = ["vorlage", "-anteil", "name"]
        unique_together = [("vorlage", "name")]

    def __str__(self):
        return f"{self.name} ({self.anteil} %)"


class Unterricht(models.Model):
    abschnitt = models.ForeignKey(Abschnitt, on_delete=models.PROTECT, related_name="unterrichte", verbose_name=_("Halbjahr"))
    gruppe = models.ForeignKey(Gruppe, on_delete=models.PROTECT, related_name="unterrichte", verbose_name=_("Gruppe / Klasse"))
    fach = models.ForeignKey(Fach, on_delete=models.PROTECT, related_name="unterrichte", verbose_name=_("Fach"))
    lehrkraft = models.ForeignKey(Personalprofil, on_delete=models.PROTECT, related_name="unterrichte", verbose_name=_("Lehrkraft"))
    skala = models.ForeignKey(Notenskala, on_delete=models.PROTECT, verbose_name=_("Notenskala"))
    gewichtung = models.ForeignKey(
        Gewichtungsvorlage, null=True, blank=True, on_delete=models.PROTECT, verbose_name=_("Startvorlage für Bewertungsordner"),
        help_text=_("Beim Anlegen werden daraus die obersten Ordner erzeugt. Danach sind die Ordner frei änderbar."),
    )

    class Meta:
        verbose_name = _("Unterricht")
        verbose_name_plural = pgettext_lazy("Mehrzahl", "Unterricht")
        ordering = ["abschnitt", "gruppe__name", "fach__reihenfolge"]
        unique_together = [("abschnitt", "gruppe", "fach")]

    def __str__(self):
        return f"{self.fach.kuerzel} {self.gruppe.name} – {self.lehrkraft.kuerzel} ({self.abschnitt.name})"

    def schueler(self):
        """Mitglieder der Gruppe, die innerhalb des Halbjahres irgendwann dazugehörten."""
        from django.db.models import Q

        return (
            Schuelerprofil.objects.filter(
                mitgliedschaften__gruppe=self.gruppe,
                mitgliedschaften__von__lte=self.abschnitt.ende,
            )
            .filter(Q(mitgliedschaften__bis__isnull=True) | Q(mitgliedschaften__bis__gte=self.abschnitt.beginn))
            .select_related("person")
            .distinct()
            .order_by("person__nachname", "person__vorname")
        )

    def save(self, *args, **kwargs):
        neu = self._state.adding
        super().save(*args, **kwargs)
        if neu:
            self.ordner_aus_vorlage()

    def ordner_aus_vorlage(self):
        """Legt die obersten Bewertungsordner aus der Startvorlage an, falls noch keine existieren."""
        if not self.gewichtung_id or self.bewertungsordner.exists():
            return
        for i, kat in enumerate(self.gewichtung.kategorien.all()):
            Bewertungsordner.objects.create(unterricht=self, name=kat.name, gewicht=kat.anteil, reihenfolge=(i + 1) * 10)


class Bewertungsordner(models.Model):
    """
    Frei benennbarer, verschachtelbarer Ordner für Leistungsnachweise eines Unterrichts,
    z. B. „Schriftlich“ oder „Sonstige Mitarbeit › Quartal 1“.

    Das Gewicht gilt relativ zu den anderen Einträgen derselben Ebene (Ordner und
    Leistungsnachweise). 50 und 50 ergeben also dasselbe wie 1 und 1.
    """

    MAX_TIEFE = 5

    unterricht = models.ForeignKey(Unterricht, on_delete=models.CASCADE, related_name="bewertungsordner", verbose_name=_("Unterricht"))
    eltern = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="unterordner",
        verbose_name=_("Übergeordneter Ordner"), help_text=_("leer = oberste Ebene"),
    )
    name = models.CharField(_("Name"), max_length=80, help_text=_("z. B. Sonstige Mitarbeit oder Quartal 1"))
    gewicht = models.DecimalField(
        _("Gewicht"), max_digits=6, decimal_places=2, default=Decimal("1"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Relativ zu den anderen Einträgen derselben Ebene, z. B. 50 / 50 oder 2 / 1."),
    )
    reihenfolge = models.PositiveSmallIntegerField(_("Reihenfolge"), default=10)
    beschreibung = models.CharField(_("Beschreibung"), max_length=200, blank=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Bewertungsordner"))

    class Meta:
        verbose_name = _("Bewertungsordner")
        verbose_name_plural = _("Bewertungsordner")
        ordering = ["unterricht", "reihenfolge", "name"]
        constraints = [
            models.UniqueConstraint(fields=["unterricht", "eltern", "name"], name="ordnername_je_ebene_eindeutig"),
            models.UniqueConstraint(
                fields=["unterricht", "name"], condition=Q(eltern__isnull=True), name="ordnername_oberste_ebene_eindeutig"
            ),
        ]

    def __str__(self):
        return f"{self.unterricht.fach.kuerzel} {self.unterricht.gruppe.name}: {self.pfad}"

    @property
    def pfad(self):
        return " › ".join([v.name for v in reversed(self.vorfahren())] + [self.name])

    def vorfahren(self):
        """Übergeordnete Ordner von innen nach außen. Bricht bei einem Zyklus ab, statt endlos zu laufen."""
        liste, gesehen = [], {self.pk} if self.pk else set()
        o = self.eltern
        while o is not None and o.pk not in gesehen:
            liste.append(o)
            gesehen.add(o.pk)
            o = o.eltern
        return liste

    def _erzeugt_zyklus(self):
        if not (self.pk and self.eltern_id):
            return False
        o, schritte = Bewertungsordner.objects.filter(pk=self.eltern_id).first(), 0
        while o is not None and schritte <= self.MAX_TIEFE + 1:
            if o.pk == self.pk:
                return True
            o = Bewertungsordner.objects.filter(pk=o.eltern_id).first() if o.eltern_id else None
            schritte += 1
        return False

    def clean(self):
        if self.eltern_id:
            if self.eltern.unterricht_id != self.unterricht_id:
                raise ValidationError({"eltern": _("Der übergeordnete Ordner gehört zu einem anderen Unterricht.")})
            if self.eltern_id == self.pk or self._erzeugt_zyklus():
                raise ValidationError({"eltern": _("Ein Ordner kann nicht in sich selbst oder einem seiner Unterordner liegen.")})
            if len(self.eltern.vorfahren()) + 2 > self.MAX_TIEFE:
                raise ValidationError({"eltern": gettext("Höchstens %(n)s Ordnerebenen sind möglich.") % {"n": self.MAX_TIEFE}})


class Leistungsnachweis(models.Model):
    unterricht = models.ForeignKey(
        Unterricht, on_delete=models.CASCADE, related_name="leistungsnachweise", verbose_name=_("Unterricht"), editable=False
    )
    ordner = models.ForeignKey(Bewertungsordner, on_delete=models.PROTECT, related_name="leistungsnachweise", verbose_name=_("Ordner"))
    titel = models.CharField(_("Bezeichnung"), max_length=100, help_text=_("frei wählbar, z. B. 1. Klassenarbeit oder Referat Säuren"))
    datum = models.DateField(_("Datum"))
    gewicht = models.DecimalField(
        _("Gewicht im Ordner"), max_digits=6, decimal_places=2, default=Decimal("1"),
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text=_("Relativ zu den anderen Einträgen im selben Ordner."),
    )
    schluessel = models.ForeignKey(
        Notenschluessel, null=True, blank=True, on_delete=models.PROTECT, verbose_name=_("Notenschlüssel"),
        help_text=_("Optional: Note wird aus erreichten Bewertungseinheiten (BE) berechnet."),
    )
    max_be = models.DecimalField(_("Maximale BE"), max_digits=6, decimal_places=2, null=True, blank=True)

    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Leistungsnachweis"))

    class Meta:
        verbose_name = _("Leistungsnachweis")
        verbose_name_plural = _("Leistungsnachweise")
        ordering = ["unterricht", "datum"]

    def __str__(self):
        return f"{self.titel} ({self.unterricht})"

    def clean(self):
        if self.ordner_id:
            self.unterricht_id = self.ordner.unterricht_id
        if self.schluessel_id and not self.max_be:
            raise ValidationError(_("Bei Verwendung eines Notenschlüssels bitte die maximalen BE angeben."))
        if self.schluessel_id and self.unterricht_id and self.schluessel.skala_id != self.unterricht.skala_id:
            raise ValidationError(_("Der Notenschlüssel passt nicht zur Notenskala des Unterrichts."))

    def save(self, *args, **kwargs):
        # Der Unterricht ergibt sich immer aus dem Ordner.
        self.unterricht_id = self.ordner.unterricht_id
        super().save(*args, **kwargs)

    def notenzeilen_anlegen(self):
        """Legt für jede Schülerin / jeden Schüler der Gruppe eine leere Notenzeile an."""
        vorhanden = set(self.noten.values_list("schueler_id", flat=True))
        neue = [Note(leistungsnachweis=self, schueler=s) for s in self.unterricht.schueler() if s.pk not in vorhanden]
        Note.objects.bulk_create(neue)
        return len(neue)


class Note(models.Model):
    SONDERSTATUS = [
        ("", "—"),
        ("entschuldigt", _("Entschuldigt gefehlt")),
        ("unentschuldigt", _("Unentschuldigt gefehlt")),
        ("befreit", _("Befreit")),
        ("nicht_bewertbar", _("Nicht bewertbar")),
    ]

    leistungsnachweis = models.ForeignKey(Leistungsnachweis, on_delete=models.CASCADE, related_name="noten", verbose_name=_("Leistungsnachweis"))
    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="noten", verbose_name=_("Schüler:in"))
    erreichte_be = models.DecimalField(_("Erreichte BE"), max_digits=6, decimal_places=2, null=True, blank=True)
    stufe = models.ForeignKey(Notenstufe, null=True, blank=True, on_delete=models.PROTECT, verbose_name=_("Note"))
    sonderstatus = models.CharField(_("Sonderstatus"), max_length=16, choices=SONDERSTATUS, blank=True, default="")
    gewicht_individuell = models.DecimalField(
        _("Individuelles Gewicht"), max_digits=6, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=_("Nur ausfüllen, wenn diese eine Note anders zählen soll als der Leistungsnachweis "
                  "(z. B. Nachschreibarbeit, Nachteilsausgleich). Leer = Gewicht des Leistungsnachweises."),
    )
    gewicht_begruendung = models.CharField(_("Begründung für abweichendes Gewicht"), max_length=200, blank=True)
    kommentar = models.CharField(_("Kommentar"), max_length=200, blank=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Note"))

    class Meta:
        verbose_name = _("Note")
        verbose_name_plural = _("Noten")
        unique_together = [("leistungsnachweis", "schueler")]

    def __str__(self):
        return f"{self.schueler}: {self.stufe or self.get_sonderstatus_display()}"

    SONDERSTATUS_KURZ = {
        "entschuldigt": _("entsch."), "unentschuldigt": _("unentsch."), "befreit": _("befreit"), "nicht_bewertbar": _("n. b."),
    }

    @property
    def sonderstatus_kurz(self):
        return self.SONDERSTATUS_KURZ.get(self.sonderstatus, "")

    @property
    def wirksames_gewicht(self):
        return self.gewicht_individuell if self.gewicht_individuell is not None else self.leistungsnachweis.gewicht

    @property
    def gewicht_abweichend(self):
        return self.gewicht_individuell is not None and self.gewicht_individuell != self.leistungsnachweis.gewicht

    def clean(self):
        if self.gewicht_individuell is not None and self.leistungsnachweis_id \
                and self.gewicht_individuell != self.leistungsnachweis.gewicht and not self.gewicht_begruendung.strip():
            raise ValidationError({"gewicht_begruendung": _("Bitte begründen, warum diese Note anders gewichtet wird.")})
        ln = self.leistungsnachweis
        if self.erreichte_be is not None and ln.max_be and self.erreichte_be > ln.max_be:
            raise ValidationError(_("Die erreichten BE überschreiten die maximalen BE."))
        if self.stufe_id and self.stufe.skala_id != ln.unterricht.skala_id:
            raise ValidationError(_("Die Note gehört nicht zur Notenskala des Unterrichts."))

    def save(self, *args, **kwargs):
        ln = self.leistungsnachweis
        if self.erreichte_be is not None and ln.schluessel_id and ln.max_be:
            prozent = (self.erreichte_be / ln.max_be * 100).quantize(Decimal("0.01"))
            self.stufe = ln.schluessel.stufe_fuer_prozent(prozent)
        if self.sonderstatus:
            self.stufe = None if self.sonderstatus != "unentschuldigt" else self.stufe
        super().save(*args, **kwargs)

    @property
    def prozent(self):
        ln = self.leistungsnachweis
        if self.erreichte_be is None or not ln.max_be:
            return None
        return (self.erreichte_be / ln.max_be * 100).quantize(Decimal("0.1"))


class Zeugnisnote(models.Model):
    unterricht = models.ForeignKey(Unterricht, on_delete=models.CASCADE, related_name="zeugnisnoten", verbose_name=_("Unterricht"))
    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="zeugnisnoten", verbose_name=_("Schüler:in"))
    vorschlag = models.DecimalField(_("Berechneter Vorschlag"), max_digits=5, decimal_places=2, null=True, blank=True)
    stufe = models.ForeignKey(Notenstufe, on_delete=models.PROTECT, verbose_name=_("Festgesetzte Note"))
    begruendung = models.TextField(_("Pädagogische Begründung"), blank=True, help_text=_("Pflicht bei Abweichung vom Vorschlag"))
    festgesetzt_am = models.DateTimeField(auto_now=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Zeugnisnote"))

    class Meta:
        verbose_name = _("Zeugnisnote")
        verbose_name_plural = _("Zeugnisnoten")
        unique_together = [("unterricht", "schueler")]

    def __str__(self):
        return f"{self.unterricht.fach.kuerzel} {self.schueler}: {self.stufe}"

    def clean(self):
        if not (self.unterricht_id and self.stufe_id):
            return
        if self.stufe.skala_id != self.unterricht.skala_id:
            raise ValidationError(_("Die Note gehört nicht zur Notenskala des Unterrichts."))
        if self.vorschlag is not None:
            vorgeschlagen = self.unterricht.skala.naechste_stufe(self.vorschlag)
            if vorgeschlagen and vorgeschlagen.pk != self.stufe_id and not self.begruendung.strip():
                raise ValidationError(
                    {"begruendung": gettext("Die Note weicht vom Vorschlag (%(vorschlag)s) ab. Bitte pädagogisch begründen.")
                     % {"vorschlag": vorgeschlagen}}
                )
