"""
Individuelle Förderung: Förderpläne (mit Zielen und Verlaufsdokumentation), Nachteilsausgleiche
und die Bestätigung der Eltern, dass sie die Unterlagen erhalten haben.

Rechte: Förderkoordination und Schulleitung sehen alles; die Klassenleitung bearbeitet die Unterlagen
ihrer Klasse; Fachlehrkräfte sehen die Unterlagen der Schüler:innen, die sie unterrichten.
"""
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy as _
from simple_history.models import HistoricalRecords

from stammdaten.models import Fach, Person, Personalprofil, Schuelerprofil, Schuljahr
from stammdaten.sprache import LokalerNameMixin, datum


class Foerderschwerpunkt(LokalerNameMixin, models.Model):
    name = models.CharField(_("Bezeichnung"), max_length=80, unique=True)
    name_en = models.CharField(_("Bezeichnung (Englisch)"), max_length=80, blank=True)
    reihenfolge = models.PositiveSmallIntegerField(_("Reihenfolge"), default=100)
    aktiv = models.BooleanField(_("Aktiv"), default=True)

    class Meta:
        verbose_name = _("Förderschwerpunkt")
        verbose_name_plural = _("Förderschwerpunkte")
        ordering = ["reihenfolge", "name"]


class Ausgleichsmassnahme(LokalerNameMixin, models.Model):
    """Katalog möglicher Maßnahmen, z. B. Zeitverlängerung, separater Raum, Vorlesen."""

    name = models.CharField(_("Bezeichnung"), max_length=100, unique=True)
    name_en = models.CharField(_("Bezeichnung (Englisch)"), max_length=100, blank=True)
    notenschutz = models.BooleanField(
        _("Notenschutz"), default=False,
        help_text=_("Abweichung von den allgemeinen Bewertungsgrundsätzen (z. B. Rechtschreibung wird nicht bewertet). "
                    "Notenschutz wird in der Regel im Zeugnis vermerkt – bitte die geltenden Vorgaben prüfen."),
    )
    reihenfolge = models.PositiveSmallIntegerField(_("Reihenfolge"), default=100)
    aktiv = models.BooleanField(_("Aktiv"), default=True)

    class Meta:
        verbose_name = _("Ausgleichsmaßnahme")
        verbose_name_plural = _("Ausgleichsmaßnahmen")
        ordering = ["reihenfolge", "name"]


class ElternstatusMixin:
    """Zusammenfassung der Aushändigungen: fehlt · offen · veraltet · ok."""

    STATUS_TEXTE = {
        "fehlt": _("noch nicht ausgehändigt"),
        "offen": _("Erhalt noch nicht bestätigt"),
        "veraltet": _("seit Aushändigung geändert"),
        "ok": _("Erhalt bestätigt"),
    }

    @property
    def eltern_status(self):
        aush = list(self.aushaendigungen.all())
        if not aush:
            return "fehlt"
        if any(a.bestaetigt_am is None for a in aush):
            return "offen"
        neueste = max((a.stand for a in aush if a.stand), default=None)
        if neueste and self.geaendert_am > neueste + timedelta(minutes=1):
            return "veraltet"
        return "ok"

    @property
    def eltern_status_text(self):
        return self.STATUS_TEXTE[self.eltern_status]


class Foerderplan(ElternstatusMixin, models.Model):
    ENTWURF, AKTIV, ABGESCHLOSSEN = "entwurf", "aktiv", "abgeschlossen"
    STATUS = [(ENTWURF, _("Entwurf")), (AKTIV, _("Aktiv")), (ABGESCHLOSSEN, _("Abgeschlossen / evaluiert"))]

    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="foerderplaene", verbose_name=_("Schüler:in"))
    schuljahr = models.ForeignKey(Schuljahr, on_delete=models.PROTECT, related_name="foerderplaene", verbose_name=_("Schuljahr"))
    titel = models.CharField(_("Titel"), max_length=120, blank=True, help_text=_("optional, z. B. „Lesen und Rechtschreiben“"))
    schwerpunkte = models.ManyToManyField(Foerderschwerpunkt, blank=True, verbose_name=_("Förderschwerpunkte"))
    status = models.CharField(_("Status"), max_length=15, choices=STATUS, default=ENTWURF)
    gueltig_von = models.DateField(_("Gültig von"))
    gueltig_bis = models.DateField(_("Gültig bis"), null=True, blank=True)
    evaluation_am = models.DateField(_("Evaluation geplant am"), null=True, blank=True)
    verantwortlich = models.ForeignKey(
        Personalprofil, null=True, blank=True, on_delete=models.SET_NULL, related_name="verantwortete_foerderplaene",
        verbose_name=_("Verantwortlich"),
    )
    beteiligte = models.ManyToManyField(
        Personalprofil, blank=True, related_name="beteiligte_foerderplaene", verbose_name=_("Weitere Beteiligte"),
    )
    ausgangslage = models.TextField(_("Lernausgangslage"), blank=True, help_text=_("Beobachtungen, Testergebnisse, Leistungsstand"))
    staerken = models.TextField(_("Stärken und Interessen"), blank=True)
    grundlagen = models.TextField(_("Grundlagen / Diagnostik"), blank=True, help_text=_("z. B. Gutachten, Testverfahren, Konferenzbeschluss"))
    vereinbarungen = models.TextField(_("Vereinbarungen mit Schüler:in und Eltern"), blank=True)
    evaluation = models.TextField(_("Evaluation (Gesamtergebnis)"), blank=True)
    vorgaenger = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="fortschreibungen",
        verbose_name=_("Fortschreibung von"),
    )
    erstellt_von = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+", verbose_name=_("Erstellt von"))
    erstellt_am = models.DateTimeField(_("Erstellt am"), auto_now_add=True)
    geaendert_am = models.DateTimeField(_("Inhalt geändert am"), default=timezone.now, editable=False)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Förderplan"), m2m_fields=[schwerpunkte])

    class Meta:
        verbose_name = _("Förderplan")
        verbose_name_plural = _("Förderpläne")
        ordering = ["-gueltig_von", "schueler"]

    def __str__(self):
        teile = [gettext("Förderplan"), str(self.schueler)]
        if self.titel:
            teile.append(self.titel)
        teile.append(datum(self.gueltig_von))
        return " · ".join(teile)

    def clean(self):
        if self.gueltig_von and self.gueltig_bis and self.gueltig_bis < self.gueltig_von:
            raise ValidationError({"gueltig_bis": _("Das Ende darf nicht vor dem Beginn liegen.")})
        if self.vorgaenger_id and self.vorgaenger.schueler_id != self.schueler_id:
            raise ValidationError({"vorgaenger": _("Fortgeschrieben werden kann nur ein Plan derselben Person.")})

    @property
    def evaluation_faellig(self):
        return (self.status == self.AKTIV and self.evaluation_am is not None
                and self.evaluation_am <= timezone.localdate() + timedelta(days=14))

    @property
    def schwerpunkt_text(self):
        return ", ".join(s.lokal_name for s in self.schwerpunkte.all())


class Foerderziel(models.Model):
    OFFEN, ERREICHT, TEILWEISE, NICHT = "offen", "erreicht", "teilweise", "nicht"
    ERGEBNIS = [(OFFEN, _("offen")), (ERREICHT, _("erreicht")), (TEILWEISE, _("teilweise erreicht")), (NICHT, _("nicht erreicht"))]

    plan = models.ForeignKey(Foerderplan, on_delete=models.CASCADE, related_name="ziele", verbose_name=_("Förderplan"))
    fach = models.ForeignKey(Fach, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("Fach"))
    bereich = models.CharField(_("Bereich"), max_length=80, blank=True, help_text=_("falls kein Fach, z. B. Arbeitsverhalten"))
    ziel = models.TextField(_("Ziel"), help_text=_("möglichst konkret und überprüfbar formulieren"))
    massnahmen = models.TextField(_("Maßnahmen"), blank=True)
    zustaendig = models.CharField(_("Zuständig"), max_length=120, blank=True, help_text=_("z. B. Deutschlehrkraft, Eltern, Schüler:in"))
    bis = models.DateField(_("Bis"), null=True, blank=True)
    ergebnis = models.CharField(_("Ergebnis"), max_length=10, choices=ERGEBNIS, default=OFFEN)
    bewertung = models.TextField(_("Bewertung / Begründung"), blank=True)
    reihenfolge = models.PositiveSmallIntegerField(_("Reihenfolge"), default=1)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Förderziel"))

    class Meta:
        verbose_name = _("Förderziel")
        verbose_name_plural = _("Förderziele")
        ordering = ["plan", "reihenfolge", "pk"]

    def __str__(self):
        return self.ziel[:60]

    @property
    def bereich_anzeige(self):
        return self.fach.lokal_name if self.fach else self.bereich


class Foerdereintrag(models.Model):
    """Verlaufsdokumentation: Beobachtungen, Gespräche, durchgeführte Maßnahmen."""

    ARTEN = [
        ("beobachtung", _("Beobachtung")),
        ("massnahme", _("Maßnahme durchgeführt")),
        ("gespraech_schueler", _("Gespräch mit Schüler:in")),
        ("gespraech_eltern", _("Gespräch mit Eltern")),
        ("konferenz", _("Konferenz / Teamgespräch")),
        ("diagnostik", _("Diagnostik / Test")),
        ("evaluation", _("Evaluation")),
        ("sonstiges", _("Sonstiges")),
    ]

    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="foerdereintraege", verbose_name=_("Schüler:in"))
    plan = models.ForeignKey(Foerderplan, null=True, blank=True, on_delete=models.CASCADE, related_name="eintraege",
                             verbose_name=_("Förderplan"))
    datum = models.DateField(_("Datum"), default=timezone.localdate)
    art = models.CharField(_("Art"), max_length=20, choices=ARTEN, default="beobachtung")
    text = models.TextField(_("Eintrag"))
    verfasst_von = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+", verbose_name=_("Verfasst von"))
    erstellt_am = models.DateTimeField(_("Erstellt am"), auto_now_add=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Fördereintrag"))

    class Meta:
        verbose_name = _("Verlaufseintrag")
        verbose_name_plural = _("Verlaufsdokumentation")
        ordering = ["-datum", "-erstellt_am"]

    def __str__(self):
        return f"{datum(self.datum)} · {self.get_art_display()} · {self.schueler}"

    def clean(self):
        if self.plan_id and self.schueler_id and self.plan.schueler_id != self.schueler_id:
            raise ValidationError({"plan": _("Der Förderplan gehört zu einer anderen Person.")})

    def save(self, *args, **kwargs):
        if self.plan_id and not self.schueler_id:
            self.schueler_id = self.plan.schueler_id
        super().save(*args, **kwargs)


class Nachteilsausgleich(ElternstatusMixin, models.Model):
    BEANTRAGT, GENEHMIGT, ABGELEHNT, AUFGEHOBEN = "beantragt", "genehmigt", "abgelehnt", "aufgehoben"
    STATUS = [(BEANTRAGT, _("beantragt")), (GENEHMIGT, _("genehmigt")), (ABGELEHNT, _("abgelehnt")), (AUFGEHOBEN, _("aufgehoben"))]

    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="nachteilsausgleiche", verbose_name=_("Schüler:in"))
    schwerpunkte = models.ManyToManyField(Foerderschwerpunkt, blank=True, verbose_name=_("Förderschwerpunkte"))
    begruendung = models.TextField(_("Begründung / Grundlage"), help_text=_("z. B. Gutachten vom …, Beobachtungen der Klassenkonferenz"))
    massnahmen = models.ManyToManyField(Ausgleichsmassnahme, blank=True, verbose_name=_("Maßnahmen"))
    zeitverlaengerung = models.PositiveSmallIntegerField(
        _("Zeitverlängerung (%)"), null=True, blank=True, help_text=_("z. B. 25 für 25 % mehr Bearbeitungszeit"),
    )
    weitere_massnahmen = models.TextField(_("Weitere Maßnahmen / Erläuterungen"), blank=True)
    faecher = models.ManyToManyField(Fach, blank=True, verbose_name=_("Fächer"), help_text=_("leer = alle Fächer"))
    gueltig_von = models.DateField(_("Gültig von"))
    gueltig_bis = models.DateField(_("Gültig bis"), null=True, blank=True, help_text=_("leer = bis auf Weiteres; Überprüfung empfohlen"))
    status = models.CharField(_("Status"), max_length=10, choices=STATUS, default=BEANTRAGT)
    beschlossen_am = models.DateField(_("Beschlossen am"), null=True, blank=True)
    beschlossen_durch = models.CharField(_("Beschlossen durch"), max_length=120, blank=True,
                                         help_text=_("z. B. Klassenkonferenz, Schulleitung"))
    foerderplan = models.ForeignKey(Foerderplan, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="nachteilsausgleiche", verbose_name=_("Zugehöriger Förderplan"))
    erstellt_von = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+", verbose_name=_("Erstellt von"))
    erstellt_am = models.DateTimeField(_("Erstellt am"), auto_now_add=True)
    geaendert_am = models.DateTimeField(_("Inhalt geändert am"), default=timezone.now, editable=False)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Nachteilsausgleich"), m2m_fields=[massnahmen, faecher])

    class Meta:
        verbose_name = _("Nachteilsausgleich")
        verbose_name_plural = _("Nachteilsausgleiche")
        ordering = ["-gueltig_von", "schueler"]

    def __str__(self):
        return gettext("Nachteilsausgleich · %(schueler)s · ab %(datum)s") % {"schueler": self.schueler, "datum": datum(self.gueltig_von)}

    def clean(self):
        if self.gueltig_von and self.gueltig_bis and self.gueltig_bis < self.gueltig_von:
            raise ValidationError({"gueltig_bis": _("Das Ende darf nicht vor dem Beginn liegen.")})
        if self.status == self.GENEHMIGT and not self.beschlossen_am:
            raise ValidationError({"beschlossen_am": _("Bei einem genehmigten Nachteilsausgleich bitte das Beschlussdatum angeben.")})
        if self.foerderplan_id and self.schueler_id and self.foerderplan.schueler_id != self.schueler_id:
            raise ValidationError({"foerderplan": _("Der Förderplan gehört zu einer anderen Person.")})

    @property
    def aktiv(self):
        heute = timezone.localdate()
        return (self.status == self.GENEHMIGT and self.gueltig_von <= heute
                and (self.gueltig_bis is None or self.gueltig_bis >= heute))

    @property
    def laeuft_bald_ab(self):
        return self.aktiv and self.gueltig_bis is not None and self.gueltig_bis <= timezone.localdate() + timedelta(days=30)

    @property
    def mit_notenschutz(self):
        return any(m.notenschutz for m in self.massnahmen.all())

    @property
    def faecher_text(self):
        f = list(self.faecher.all())
        return ", ".join(x.lokal_name for x in f) if f else gettext("alle Fächer")

    def massnahmen_liste(self):
        teile = []
        if self.zeitverlaengerung:
            teile.append(gettext("Zeitverlängerung %(p)s %%") % {"p": self.zeitverlaengerung})
        teile += [m.lokal_name for m in self.massnahmen.all()]
        return teile

    @classmethod
    def aktive(cls, stichtag=None):
        tag = stichtag or timezone.localdate()
        return cls.objects.filter(status=cls.GENEHMIGT, gueltig_von__lte=tag).filter(
            Q(gueltig_bis__isnull=True) | Q(gueltig_bis__gte=tag)
        )


class Aushaendigung(models.Model):
    """
    Nachweis, dass ein Förderplan oder Nachteilsausgleich an Erziehungsberechtigte ausgehändigt wurde
    und wann diese den Erhalt bestätigt haben. Später können Eltern im Elternportal selbst bestätigen
    (Feld „bestaetigt_durch_konto“).
    """

    WEGE = [("persoenlich", _("persönlich übergeben")), ("gespraech", _("im Elterngespräch")), ("email", _("per E-Mail")),
            ("post", _("per Post / Schulranzen")), ("portal", _("über das Elternportal"))]
    BESTAETIGUNG = [("unterschrift", _("Unterschrift auf Rücklauf")), ("email", _("Antwort per E-Mail")),
                    ("muendlich", _("mündlich / im Gespräch")), ("portal", _("im Elternportal abgehakt"))]

    foerderplan = models.ForeignKey(Foerderplan, null=True, blank=True, on_delete=models.CASCADE,
                                    related_name="aushaendigungen", verbose_name=_("Förderplan"))
    nachteilsausgleich = models.ForeignKey(Nachteilsausgleich, null=True, blank=True, on_delete=models.CASCADE,
                                           related_name="aushaendigungen", verbose_name=_("Nachteilsausgleich"))
    empfaenger = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="erhaltene_foerderunterlagen",
                                   verbose_name=_("Empfänger:in"))
    ausgehaendigt_am = models.DateField(_("Ausgehändigt am"), default=timezone.localdate)
    weg = models.CharField(_("Weg"), max_length=12, choices=WEGE, default="persoenlich")
    stand = models.DateTimeField(_("Stand des Dokuments"), null=True, blank=True, editable=False,
                                 help_text=_("Änderungszeitpunkt des Dokuments bei der Aushändigung"))
    bestaetigt_am = models.DateField(_("Erhalt bestätigt am"), null=True, blank=True)
    bestaetigung = models.CharField(_("Bestätigt durch"), max_length=12, choices=BESTAETIGUNG, blank=True)
    bestaetigt_durch_konto = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
        verbose_name=_("Bestätigung erfasst von"),
    )
    bemerkung = models.CharField(_("Bemerkung"), max_length=200, blank=True)
    erfasst_von = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name="+", verbose_name=_("Erfasst von"))
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Aushändigung"))

    class Meta:
        verbose_name = _("Aushändigung / Elternbestätigung")
        verbose_name_plural = _("Aushändigungen / Elternbestätigungen")
        ordering = ["-ausgehaendigt_am", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=(Q(foerderplan__isnull=False, nachteilsausgleich__isnull=True)
                           | Q(foerderplan__isnull=True, nachteilsausgleich__isnull=False)),
                name="aushaendigung_genau_ein_dokument",
            ),
        ]

    def __str__(self):
        return gettext("%(dokument)s an %(person)s (%(datum)s)") % {
            "dokument": self.dokument_art, "person": self.empfaenger, "datum": datum(self.ausgehaendigt_am)}

    @property
    def dokument(self):
        return self.foerderplan or self.nachteilsausgleich

    @property
    def dokument_art(self):
        return gettext("Förderplan") if self.foerderplan_id else gettext("Nachteilsausgleich")

    @property
    def schueler(self):
        return self.dokument.schueler

    @property
    def bestaetigt(self):
        return self.bestaetigt_am is not None

    @property
    def veraltet(self):
        """Das Dokument wurde nach der Aushändigung geändert – ggf. erneut aushändigen."""
        doc = self.dokument
        return bool(self.stand and doc and doc.geaendert_am and doc.geaendert_am > self.stand + timedelta(minutes=1))

    def clean(self):
        # Objekte statt IDs prüfen: beim Anlegen eines neuen Plans samt Aushändigung ist der Plan noch ungespeichert.
        if (self.foerderplan is None) == (self.nachteilsausgleich is None):
            raise ValidationError(_("Bitte genau einen Förderplan oder einen Nachteilsausgleich auswählen."))
        if self.bestaetigt_am and self.ausgehaendigt_am and self.bestaetigt_am < self.ausgehaendigt_am:
            raise ValidationError({"bestaetigt_am": _("Die Bestätigung kann nicht vor der Aushändigung liegen.")})
        schueler = getattr(self.dokument, "schueler", None) if getattr(self.dokument, "schueler_id", None) else None
        if self.empfaenger_id and schueler is not None:
            if not schueler.beziehungen.filter(person_id=self.empfaenger_id).exists():
                raise ValidationError({"empfaenger": _("Die Person ist nicht als Elternteil oder Kontaktperson eingetragen.")})

    def save(self, *args, **kwargs):
        if self.stand is None and self.dokument is not None and self.dokument.pk:
            self.stand = self.dokument.geaendert_am or timezone.now()
        if self.bestaetigt_am and not self.bestaetigung:
            self.bestaetigung = "unterschrift"
        super().save(*args, **kwargs)
