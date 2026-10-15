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
from decimal import ROUND_HALF_DOWN, ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext, gettext_lazy as _, pgettext_lazy
from simple_history.models import HistoricalRecords

from stammdaten.sprache import LokalerNameMixin
from stammdaten.models import Abschnitt, Fach, Gruppe, Personalprofil, Schuelerprofil


# Wie die Gewichte der Einträge einer Ebene eingegeben werden (ab 0.4.7.0). Gerechnet wird in beiden Fällen gleich:
# gewichteter Mittelwert, leere Einträge werden übersprungen. „Prozent“ zeigt % an und prüft die Summe auf 100.
RELATIV, PROZENT = "relativ", "prozent"
GEWICHTSARTEN = [(RELATIV, _("relativ (z. B. 2 : 1)")), (PROZENT, _("in Prozent (Summe 100)"))]

# Rundung eines Schnitts auf eine Note (ab 0.4.8.0). „Zugunsten“: bei Gleichstand (x,50) die bessere Note.
HUNDERT = Decimal(100)
ZUGUNSTEN, KAUFMAENNISCH = "zugunsten", "kaufmaennisch"
RUNDUNGEN = [(ZUGUNSTEN, _("bei Gleichstand zur besseren Note (z. B. 2,50 → 2)")),
             (KAUFMAENNISCH, _("kaufmännisch (x,50 aufrunden)"))]


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
        help_text=_("Grenze zur nicht mehr ausreichenden Leistung, z. B. 4,50 (Sek I) oder 4,49 Punkte (Sek II). Gefährdet ist, "
                    "wessen auf eine ganze Note gerundeter Schnitt jenseits dieser Grenze liegt (Rundung siehe unten)."),
    )
    rundung = models.CharField(_("Rundung auf ganze Noten"), max_length=14, choices=RUNDUNGEN, default=ZUGUNSTEN)
    unentschuldigt_stufe = models.ForeignKey(
        "Notenstufe", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name=_("Note bei unentschuldigtem Versäumnis"),
        help_text=_("Gilt, wenn „unentschuldigt“ ohne eigene Note eingetragen ist, z. B. 6 bzw. 0 Punkte. Leer = zählt nicht."),
    )

    class Meta:
        verbose_name = _("Notenskala")
        verbose_name_plural = _("Notenskalen")

    def runden(self, wert: Decimal) -> Decimal:
        quant = Decimal(1).scaleb(-self.nachkommastellen)
        return wert.quantize(quant, rounding=ROUND_HALF_UP)

    def ganz_runden(self, wert: Decimal | None) -> Decimal | None:
        """Schnitt → ganze Note bzw. ganze Punktzahl; bei x,50 je nach Einstellung zur besseren Note oder aufgerundet."""
        if wert is None:
            return None
        if self.rundung == ZUGUNSTEN:
            art = ROUND_HALF_UP if self.hoeher_ist_besser else ROUND_HALF_DOWN
        else:
            art = ROUND_HALF_UP
        return Decimal(wert).quantize(Decimal(1), rounding=art)

    def ist_gefaehrdet(self, wert: Decimal | None) -> bool:
        """Gefährdet ist, wessen auf eine ganze Note gerundeter Schnitt jenseits der Grenze liegt (gleiche Rundung wie Zeugnis)."""
        if wert is None or self.gefaehrdung_ab is None:
            return False
        ganz = self.ganz_runden(wert)
        if self.hoeher_ist_besser:
            return ganz <= self.gefaehrdung_ab
        return ganz >= self.gefaehrdung_ab

    def naechste_stufe(self, wert: Decimal):
        """Notenstufe, deren interner Wert dem Schnitt am nächsten liegt; bei Gleichstand nach der Rundungsregel."""
        stufen = list(self.stufen.all())
        if not stufen or wert is None:
            return None
        zur_besseren = self.rundung == ZUGUNSTEN
        if zur_besseren:
            vorzug = (lambda s: -s.wert) if self.hoeher_ist_besser else (lambda s: s.wert)
        else:
            vorzug = lambda s: -s.wert           # kaufmännisch: der höhere Wert
        return min(stufen, key=lambda s: (abs(s.wert - wert), vorzug(s), s.reihenfolge))


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
    gewichtsart = models.CharField(_("Gewichte der obersten Ebene"), max_length=8, choices=GEWICHTSARTEN, default=RELATIV)
    SCHNITT, ZEUGNISNOTE = "schnitt", "zeugnis"
    BASEN = [(SCHNITT, _("rechnerischer Schnitt des 1. Halbjahres")), (ZEUGNISNOTE, _("Halbjahreszeugnisnote"))]
    anteil_vorhalbjahr = models.DecimalField(
        _("Anteil 1. Halbjahr an der Jahresnote (%)"), max_digits=5, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text=_("Nur im 2. Halbjahr: so viel Prozent zählt das 1. Halbjahr im Vorschlag, z. B. 40. Leer oder 0 = nur 2. Halbjahr."),
    )
    vorhalbjahr_basis = models.CharField(_("Grundlage 1. Halbjahr"), max_length=8, choices=BASEN, default=SCHNITT)

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
        if neu and self.anteil_vorhalbjahr is None and self.abschnitt_id and self.gruppe_id:
            if self.abschnitt.nummer == 2 and self.gruppe.jahrgang in settings.JAHRESNOTE_JAHRGAENGE:
                self.anteil_vorhalbjahr = Decimal(settings.JAHRESNOTE_ANTEIL_HJ1)
        super().save(*args, **kwargs)
        if neu:
            self.ordner_aus_vorlage()
            regel = Klausurregel.fuer(self)
            if regel is not None:
                regel.anwenden(self)

    @property
    def mit_jahresnote(self):
        return self.abschnitt.nummer == 2 and bool(self.anteil_vorhalbjahr)

    def vorhalbjahr(self):
        """1. Halbjahr desselben Schuljahres (nur für einen Unterricht im 2. Halbjahr)."""
        if self.abschnitt.nummer != 2:
            return None
        return Abschnitt.objects.filter(schuljahr_id=self.abschnitt.schuljahr_id, nummer=1).first()

    def klausurregel(self):
        return Klausurregel.fuer(self)

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
    gewichtsart = models.CharField(_("Gewichte der Einträge in diesem Ordner"), max_length=8, choices=GEWICHTSARTEN, default=RELATIV)
    KLAUSUR, MITARBEIT = "klausur", "mitarbeit"
    VORGABEN = [("", "—"), (KLAUSUR, _("Klausuren (Vorgabe der Schulleitung)")), (MITARBEIT, _("Sonstige Mitarbeit (Vorgabe der Schulleitung)"))]
    vorgegeben = models.CharField(_("Vorgegeben"), max_length=10, choices=VORGABEN, blank=True, default="", editable=False,
                                  help_text=_("Von einer Klausurregel der Schulleitung festgelegt: Name und Gewicht sind gesperrt."))
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
            a = self.ordner.unterricht.abschnitt
            if self.datum and not (a.beginn <= self.datum <= a.ende):
                raise ValidationError({"datum": gettext("Das Datum muss im Halbjahr liegen (%(von)s bis %(bis)s).") % {
                    "von": a.beginn.strftime("%d.%m.%Y"), "bis": a.ende.strftime("%d.%m.%Y")}})
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
    VERMERKE = [("", "—"), ("nb", _("n.b. (nicht bewertet)")), ("befreit", _("befreit"))]

    stufe = models.ForeignKey(Notenstufe, on_delete=models.PROTECT, null=True, blank=True, verbose_name=_("Festgesetzte Note"))
    vermerk = models.CharField(
        _("Vermerk statt Note"), max_length=8, choices=VERMERKE, blank=True, default="",
        help_text=_("n.b., wenn weniger als sechs Wochen am Stück bzw. acht Wochen insgesamt teilgenommen (Rili Sek I, 3.8)"),
    )
    begruendung = models.TextField(_("Pädagogische Begründung"), blank=True, help_text=_("Pflicht bei Abweichung vom Vorschlag"))
    festgesetzt_am = models.DateTimeField(auto_now=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Zeugnisnote"))

    class Meta:
        verbose_name = _("Zeugnisnote")
        verbose_name_plural = _("Zeugnisnoten")
        unique_together = [("unterricht", "schueler")]

    def __str__(self):
        return f"{self.unterricht.fach.kuerzel} {self.schueler}: {self.stufe or self.get_vermerk_display()}"

    def clean(self):
        if self.vermerk:
            self.stufe = None
            return
        if not self.stufe_id:
            raise ValidationError({"stufe": _("Bitte eine Note oder einen Vermerk angeben.")})
        if not self.unterricht_id:
            return
        if self.stufe.skala_id != self.unterricht.skala_id:
            raise ValidationError(_("Die Note gehört nicht zur Notenskala des Unterrichts."))
        if self.vorschlag is not None:
            vorgeschlagen = self.unterricht.skala.naechste_stufe(self.vorschlag)
            if not self.unterricht.skala.hoeher_ist_besser and vorgeschlagen:
                # Zeugnisnoten sind ganze Noten (Rili Sek I 3.5): verglichen wird die gerundete Note, nicht die Tendenz.
                ganz = self.unterricht.skala.ganz_runden(self.vorschlag)
                abweichung = self.stufe.wert.quantize(Decimal(1), rounding=ROUND_HALF_UP) != ganz
                vorgeschlagen = next((s for s in self.unterricht.skala.stufen.all() if s.wert == ganz), vorgeschlagen)
            else:
                abweichung = bool(vorgeschlagen and vorgeschlagen.pk != self.stufe_id)
            if abweichung and not self.begruendung.strip():
                raise ValidationError(
                    {"begruendung": gettext("Die Note weicht vom Vorschlag (%(vorschlag)s) ab. Bitte pädagogisch begründen.")
                     % {"vorschlag": vorgeschlagen}}
                )


class Leistungsvorgabe(models.Model):
    """
    Pflicht-Leistungsnachweis mit Frist (ab 0.4.7.0), festgelegt von Schulleitung, Stellvertretung oder
    Stufenkoordination (nur eigene Jahrgänge). Beispiel: „Quartalsnote Sonstige Mitarbeit“, Jahrgänge 5–10,
    alle Fächer, Ordner enthält „Quartal 1“, mindestens 1, bis 31.10.

    Erfüllt ist die Vorgabe für einen Unterricht, wenn bis zur Frist mindestens `mindestanzahl` passende
    Leistungsnachweise angelegt sind, in denen für alle Schüler:innen eine Note oder ein Vermerk steht.
    """

    titel = models.CharField(_("Bezeichnung"), max_length=120, help_text=_("z. B. Quartalsnote Sonstige Mitarbeit Q1"))
    titel_en = models.CharField(_("Bezeichnung (Englisch)"), max_length=120, blank=True)
    abschnitt = models.ForeignKey(Abschnitt, on_delete=models.CASCADE, related_name="leistungsvorgaben", verbose_name=_("Halbjahr"))
    jahrgang_von = models.PositiveSmallIntegerField(_("ab Jahrgang"))
    jahrgang_bis = models.PositiveSmallIntegerField(_("bis Jahrgang"))
    faecher = models.ManyToManyField(Fach, blank=True, related_name="leistungsvorgaben", verbose_name=_("Fächer"),
                                     help_text=_("Keine Auswahl = alle Fächer."))
    ordner_enthaelt = models.CharField(
        _("Ordner enthält"), max_length=80, blank=True,
        help_text=_("Optional: Nur Leistungsnachweise in Ordnern, deren Pfad diesen Text enthält, z. B. „Schriftlich“ oder „Quartal 1“."))
    titel_enthaelt = models.CharField(
        _("Bezeichnung enthält"), max_length=80, blank=True,
        help_text=_("Optional: Nur Leistungsnachweise, deren Bezeichnung diesen Text enthält, z. B. „Klassenarbeit“."))
    mindestanzahl = models.PositiveSmallIntegerField(_("Mindestanzahl"), default=1, validators=[MinValueValidator(1)])
    frist = models.DateField(_("Frist"))
    hinweis = models.CharField(_("Hinweis für Lehrkräfte"), max_length=300, blank=True)
    angelegt_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                     verbose_name=_("Angelegt von"))
    angelegt_am = models.DateTimeField(_("Angelegt am"), auto_now_add=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Leistungsvorgabe"))

    class Meta:
        verbose_name = _("Leistungsvorgabe")
        verbose_name_plural = _("Leistungsvorgaben")
        ordering = ["frist", "titel"]

    def __str__(self):
        return self.titel

    def lokal_titel(self, sprache=None):
        from django.utils.translation import get_language

        sprache = sprache or get_language() or "de"
        return self.titel_en if sprache.startswith("en") and self.titel_en else self.titel

    @property
    def jahrgaenge(self):
        return range(self.jahrgang_von, self.jahrgang_bis + 1)

    def clean(self):
        if self.jahrgang_von and self.jahrgang_bis and self.jahrgang_von > self.jahrgang_bis:
            raise ValidationError({"jahrgang_bis": _("„bis Jahrgang“ darf nicht kleiner sein als „ab Jahrgang“.")})
        if self.abschnitt_id and self.frist and not (self.abschnitt.beginn <= self.frist <= self.abschnitt.ende):
            raise ValidationError({"frist": gettext("Die Frist muss im Halbjahr liegen (%(von)s bis %(bis)s).") % {
                "von": self.abschnitt.beginn.strftime("%d.%m.%Y"), "bis": self.abschnitt.ende.strftime("%d.%m.%Y")}})

    def unterrichte(self):
        qs = Unterricht.objects.filter(abschnitt=self.abschnitt, gruppe__jahrgang__gte=self.jahrgang_von,
                                       gruppe__jahrgang__lte=self.jahrgang_bis)
        if self.pk and self.faecher.exists():
            qs = qs.filter(fach__in=self.faecher.all())
        return qs.select_related("fach", "gruppe", "lehrkraft__person", "abschnitt")


class Klausurregel(models.Model):
    """
    Klausuren bzw. Klassenarbeiten je Fach und Jahrgangsbereich (ab 0.4.8.0), festgelegt von der Schulleitung
    (z. B. nach Beschluss der Fachkonferenz). Betroffene Kurse erhalten zwei vorgegebene oberste Ordner
    „Klausuren“ und „Sonstige Mitarbeit“ mit festem Prozentanteil (Standard 50 / 50); darunter gliedert die Lehrkraft frei.
    """

    faecher = models.ManyToManyField(Fach, related_name="klausurregeln", verbose_name=_("Fächer"))
    jahrgang_von = models.PositiveSmallIntegerField(_("ab Jahrgang"))
    jahrgang_bis = models.PositiveSmallIntegerField(_("bis Jahrgang"))
    anteil_klausur = models.DecimalField(_("Anteil Klausuren (%)"), max_digits=5, decimal_places=2, default=Decimal(50),
                                         validators=[MinValueValidator(Decimal("1")), MaxValueValidator(Decimal("99"))])
    name_klausur = models.CharField(_("Name des Klausurordners"), max_length=60, default="Klausuren")
    name_mitarbeit = models.CharField(_("Name des Ordners für die übrigen Leistungen"), max_length=60, default="Sonstige Mitarbeit")
    bemerkung = models.CharField(_("Bemerkung"), max_length=200, blank=True, help_text=_("z. B. Beschluss der Fachkonferenz vom …"))
    angelegt_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                     verbose_name=_("Angelegt von"))
    geaendert_am = models.DateTimeField(_("Geändert am"), auto_now=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Klausurregel"))

    class Meta:
        verbose_name = _("Klausurregel")
        verbose_name_plural = _("Klausurregeln")
        ordering = ["jahrgang_von", "jahrgang_bis"]

    def __str__(self):
        return gettext("Klausuren Jahrgang %(von)s–%(bis)s") % {"von": self.jahrgang_von, "bis": self.jahrgang_bis}

    @property
    def anteil_mitarbeit(self):
        return HUNDERT - self.anteil_klausur

    def clean(self):
        if self.jahrgang_von and self.jahrgang_bis and self.jahrgang_von > self.jahrgang_bis:
            raise ValidationError({"jahrgang_bis": _("„bis Jahrgang“ darf nicht kleiner sein als „ab Jahrgang“.")})
        if (self.name_klausur or "").strip().lower() == (self.name_mitarbeit or "").strip().lower():
            raise ValidationError({"name_mitarbeit": _("Die beiden Ordner brauchen verschiedene Namen.")})

    @classmethod
    def fuer(cls, unterricht):
        j = unterricht.gruppe.jahrgang
        if j is None:
            return None
        return cls.objects.filter(faecher=unterricht.fach_id, jahrgang_von__lte=j, jahrgang_bis__gte=j).order_by("-geaendert_am").first()

    def unterrichte(self):
        """Betroffener Unterricht des laufenden und künftiger Schuljahre."""
        from stammdaten.models import Schuljahr

        sj = Schuljahr.aktuelles()
        qs = Unterricht.objects.filter(fach__in=self.faecher.all(), gruppe__jahrgang__gte=self.jahrgang_von,
                                       gruppe__jahrgang__lte=self.jahrgang_bis)
        if sj is not None:
            qs = qs.filter(abschnitt__schuljahr__beginn__gte=sj.beginn)
        return qs.select_related("fach", "gruppe", "abschnitt")

    def anwenden(self, unterricht):
        """
        Legt die beiden vorgegebenen Ordner an bzw. übernimmt passende vorhandene, setzt Prozentgewichte und verschiebt
        weitere Ordner der obersten Ebene in den Mitarbeitsordner. Gibt die Zahl verschobener Ordner zurück.
        """
        oben = list(Bewertungsordner.objects.filter(unterricht=unterricht, eltern=None))
        def finden(art, name, *alternativ):
            for o in oben:
                if o.vorgegeben == art:
                    return o
            namen = [n.lower() for n in (name, *alternativ)]
            for o in oben:
                if o.name.strip().lower() in namen and not o.vorgegeben:
                    return o
            return None
        klausur = finden(Bewertungsordner.KLAUSUR, self.name_klausur, "schriftlich", "klassenarbeiten", "klausuren")
        mitarbeit = finden(Bewertungsordner.MITARBEIT, self.name_mitarbeit, "sonstige mitarbeit", "mündlich", "sonstige leistungen")
        if mitarbeit is not None and mitarbeit == klausur:
            mitarbeit = None
        if klausur is None:
            klausur = Bewertungsordner(unterricht=unterricht, eltern=None, name=self.name_klausur)
        if mitarbeit is None:
            mitarbeit = Bewertungsordner(unterricht=unterricht, eltern=None, name=self.name_mitarbeit)
        for o, art, anteil, rf in ((klausur, Bewertungsordner.KLAUSUR, self.anteil_klausur, 10),
                                   (mitarbeit, Bewertungsordner.MITARBEIT, self.anteil_mitarbeit, 20)):
            o.vorgegeben, o.gewicht = art, anteil
            if not o.pk:
                o.reihenfolge = rf
            o.save()
        verschoben = 0
        for o in oben:
            if o.pk not in (klausur.pk, mitarbeit.pk):
                o.eltern, o.vorgegeben = mitarbeit, ""
                o.save(update_fields=["eltern", "vorgegeben"])
                verschoben += 1
        if unterricht.gewichtsart != PROZENT:
            unterricht.gewichtsart = PROZENT
            Unterricht.objects.filter(pk=unterricht.pk).update(gewichtsart=PROZENT)
        return verschoben

    @staticmethod
    def freigeben(unterricht):
        """Hebt die Vorgabe auf (z. B. wenn die Regel gelöscht wird); die Ordner bleiben frei bearbeitbar erhalten."""
        Bewertungsordner.objects.filter(unterricht=unterricht).exclude(vorgegeben="").update(vorgegeben="")


class Notensperre(models.Model):
    """
    Ausdrückliche Sperre bzw. Freigabe der Noten einer Klasse in einem Halbjahr (ab 0.4.8.0).
    Ohne Eintrag gilt: gesperrt, sobald die Zeugniskonferenz durchgeführt bzw. das Zeugnis freigegeben ist.
    Ein Eintrag (durch Stufenkoordination, Schulleitung oder Stellvertretung) geht dieser Automatik vor.
    """

    abschnitt = models.ForeignKey(Abschnitt, on_delete=models.CASCADE, related_name="notensperren", verbose_name=_("Halbjahr"))
    klasse = models.ForeignKey(Gruppe, on_delete=models.CASCADE, related_name="notensperren", verbose_name=_("Klasse"))
    gesperrt = models.BooleanField(_("Gesperrt"), default=True)
    grund = models.CharField(_("Grund"), max_length=200, blank=True)
    geaendert_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                      verbose_name=_("Geändert von"))
    geaendert_am = models.DateTimeField(_("Geändert am"), auto_now=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Notensperre"))

    class Meta:
        verbose_name = _("Notensperre")
        verbose_name_plural = _("Notensperren")
        unique_together = [("abschnitt", "klasse")]

    def __str__(self):
        return f"{self.klasse} {self.abschnitt}: {'gesperrt' if self.gesperrt else 'offen'}"
