"""
Stammdaten: Schuljahre, Personen, Gruppen und Mitgliedschaften.

Kernidee: Stammklassen, Lerngruppen (Ethik, Religion, Rallye ...) und AGs sind
alle "Gruppen" eines Schuljahres. Schüler:innen gehören ihnen über zeitlich
begrenzte Mitgliedschaften an. Nichts wird überschrieben, nur beendet – so
bleibt die Historie aller Schuljahre erhalten.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from simple_history.models import HistoricalRecords


class Schuljahr(models.Model):
    name = models.CharField("Bezeichnung", max_length=20, unique=True, help_text="z. B. 2026/27")
    beginn = models.DateField("Beginn")
    ende = models.DateField("Ende")
    aktiv = models.BooleanField("Aktuelles Schuljahr", default=False)

    class Meta:
        verbose_name = "Schuljahr"
        verbose_name_plural = "Schuljahre"
        ordering = ["-beginn"]
        constraints = [
            models.UniqueConstraint(fields=["aktiv"], condition=Q(aktiv=True), name="nur_ein_aktives_schuljahr"),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.beginn and self.ende and self.ende <= self.beginn:
            raise ValidationError("Das Ende muss nach dem Beginn liegen.")

    @classmethod
    def aktuelles(cls):
        return cls.objects.filter(aktiv=True).first()


class Abschnitt(models.Model):
    """Halbjahr bzw. Term innerhalb eines Schuljahres."""

    schuljahr = models.ForeignKey(Schuljahr, on_delete=models.CASCADE, related_name="abschnitte", verbose_name="Schuljahr")
    name = models.CharField("Bezeichnung", max_length=40, help_text="z. B. 1. Halbjahr")
    nummer = models.PositiveSmallIntegerField("Nummer", default=1)
    beginn = models.DateField("Beginn")
    ende = models.DateField("Ende")

    class Meta:
        verbose_name = "Abschnitt (Halbjahr)"
        verbose_name_plural = "Abschnitte (Halbjahre)"
        ordering = ["schuljahr", "nummer"]
        unique_together = [("schuljahr", "nummer")]

    def __str__(self):
        return f"{self.schuljahr} – {self.name}"

    def clean(self):
        if self.beginn and self.ende and self.ende <= self.beginn:
            raise ValidationError("Das Ende muss nach dem Beginn liegen.")


class Person(models.Model):
    """Gemeinsamer Kern aller Menschen im System (Schüler:innen, Eltern, Personal)."""

    vorname = models.CharField("Vorname", max_length=80)
    nachname = models.CharField("Nachname", max_length=80)
    rufname = models.CharField("Rufname", max_length=80, blank=True)
    geburtsdatum = models.DateField("Geburtsdatum", null=True, blank=True)
    email = models.EmailField("E-Mail", blank=True)
    telefon = models.CharField("Telefon", max_length=40, blank=True)
    strasse = models.CharField("Straße / Hausnummer", max_length=120, blank=True)
    ort = models.CharField("Ort", max_length=80, blank=True)
    land = models.CharField("Land", max_length=60, blank=True, default="Kenia")
    sprache = models.CharField(
        "Bevorzugte Sprache", max_length=2, choices=[("de", "Deutsch"), ("en", "Englisch")], default="de"
    )
    benutzer = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="person", verbose_name="Benutzerkonto",
    )
    notizen = models.TextField("Interne Notizen", blank=True)
    erstellt = models.DateTimeField(auto_now_add=True)
    geaendert = models.DateTimeField(auto_now=True)
    history = HistoricalRecords(verbose_name="Änderungsprotokoll Person")

    class Meta:
        verbose_name = "Person"
        verbose_name_plural = "Personen"
        ordering = ["nachname", "vorname"]

    def __str__(self):
        return f"{self.nachname}, {self.rufname or self.vorname}"

    @property
    def anzeigename(self):
        return f"{self.rufname or self.vorname} {self.nachname}"


class Schuelerprofil(models.Model):
    STATUS = [("aktiv", "Aktiv"), ("abgang", "Abgegangen"), ("bewerber", "Bewerber:in")]

    person = models.OneToOneField(Person, on_delete=models.CASCADE, related_name="schueler", verbose_name="Person")
    schuelernummer = models.CharField("Schülernummer", max_length=20, unique=True)
    eintrittsdatum = models.DateField("Eintritt", null=True, blank=True)
    austrittsdatum = models.DateField("Austritt", null=True, blank=True)
    status = models.CharField("Status", max_length=10, choices=STATUS, default="aktiv")
    history = HistoricalRecords(verbose_name="Änderungsprotokoll Schüler:in")

    class Meta:
        verbose_name = "Schüler:in"
        verbose_name_plural = "Schüler:innen"
        ordering = ["person__nachname", "person__vorname"]

    def __str__(self):
        return str(self.person)

    def stammklasse(self, schuljahr=None, stichtag=None):
        schuljahr = schuljahr or Schuljahr.aktuelles()
        qs = Mitgliedschaft.objects.aktiv(stichtag).filter(
            schueler=self, gruppe__typ=Gruppe.STAMMKLASSE, gruppe__schuljahr=schuljahr
        )
        m = qs.select_related("gruppe").first()
        return m.gruppe if m else None


class Personalprofil(models.Model):
    FUNKTIONEN = [
        ("lehrkraft", "Lehrkraft"),
        ("verwaltung", "Verwaltung / Sekretariat"),
        ("leitung", "Schulleitung"),
        ("sonstige", "Sonstiges Personal"),
    ]

    person = models.OneToOneField(Person, on_delete=models.CASCADE, related_name="personal", verbose_name="Person")
    kuerzel = models.CharField("Kürzel", max_length=8, unique=True, help_text="wie im Stundenplan, z. B. KRO")
    funktion = models.CharField("Funktion", max_length=12, choices=FUNKTIONEN, default="lehrkraft")
    aktiv = models.BooleanField("Aktiv", default=True)
    history = HistoricalRecords(verbose_name="Änderungsprotokoll Personal")

    class Meta:
        verbose_name = "Personal"
        verbose_name_plural = "Personal"
        ordering = ["kuerzel"]

    def __str__(self):
        return f"{self.kuerzel} – {self.person.anzeigename}"


class Beziehung(models.Model):
    """Verbindet eine Schülerin / einen Schüler mit einer erziehungsberechtigten oder Kontaktperson."""

    ARTEN = [
        ("mutter", "Mutter"),
        ("vater", "Vater"),
        ("elternteil", "Elternteil"),
        ("vormund", "Vormund"),
        ("grosseltern", "Großelternteil"),
        ("gastfamilie", "Gastfamilie"),
        ("sonstige", "Sonstige Kontaktperson"),
    ]

    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="beziehungen", verbose_name="Schüler:in")
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="kinder_beziehungen", verbose_name="Kontaktperson")
    art = models.CharField("Art", max_length=12, choices=ARTEN)
    sorgerecht = models.BooleanField("Sorgerecht", default=True)
    auskunftsrecht = models.BooleanField("Auskunftsrecht", default=True)
    abholberechtigt = models.BooleanField("Abholberechtigt", default=True)
    notfallkontakt = models.BooleanField("Notfallkontakt", default=False)
    rechnungsempfaenger = models.BooleanField("Rechnungsempfänger:in", default=False)
    history = HistoricalRecords(verbose_name="Änderungsprotokoll Beziehung")

    class Meta:
        verbose_name = "Beziehung"
        verbose_name_plural = "Beziehungen (Eltern / Kontakte)"
        unique_together = [("schueler", "person")]

    def __str__(self):
        return f"{self.person} ({self.get_art_display()}) → {self.schueler}"

    def clean(self):
        if self.schueler_id and self.person_id and self.schueler.person_id == self.person_id:
            raise ValidationError("Eine Person kann nicht ihre eigene Kontaktperson sein.")


class Gruppe(models.Model):
    STAMMKLASSE = "stammklasse"
    LERNGRUPPE = "lerngruppe"
    AG = "ag"
    TYPEN = [(STAMMKLASSE, "Stammklasse"), (LERNGRUPPE, "Lerngruppe / Kurs"), (AG, "AG / Nachmittag")]

    schuljahr = models.ForeignKey(Schuljahr, on_delete=models.PROTECT, related_name="gruppen", verbose_name="Schuljahr")
    typ = models.CharField("Typ", max_length=12, choices=TYPEN, default=STAMMKLASSE)
    name = models.CharField("Bezeichnung", max_length=60, help_text="z. B. 9a, Ethik 9, AG Robotik")
    kuerzel = models.CharField("Kürzel", max_length=20, blank=True, help_text="wie im Stundenplan")
    jahrgang = models.PositiveSmallIntegerField("Jahrgang", null=True, blank=True)
    leitung = models.ForeignKey(
        Personalprofil, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="geleitete_gruppen", verbose_name="Leitung (Klassenleitung / AG-Leitung)",
    )
    gebildet_aus = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="abgeleitete_gruppen",
        limit_choices_to={"typ": STAMMKLASSE}, verbose_name="Gebildet aus (Stammklassen)",
        help_text="Nur zur Orientierung und Filterung; gemischte Gruppen bleiben möglich.",
    )
    vorgaenger = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="nachfolger",
        verbose_name="Vorgängergruppe (Vorjahr)",
    )
    history = HistoricalRecords(verbose_name="Änderungsprotokoll Gruppe", m2m_fields=[gebildet_aus])

    class Meta:
        verbose_name = "Gruppe / Klasse"
        verbose_name_plural = "Gruppen / Klassen"
        ordering = ["schuljahr", "typ", "jahrgang", "name"]
        unique_together = [("schuljahr", "name")]

    def __str__(self):
        return f"{self.name} ({self.schuljahr})"

    def aktuelle_mitglieder(self, stichtag=None):
        return Schuelerprofil.objects.filter(
            mitgliedschaften__in=Mitgliedschaft.objects.aktiv(stichtag).filter(gruppe=self)
        ).select_related("person").distinct()


class MitgliedschaftQuerySet(models.QuerySet):
    def aktiv(self, stichtag=None):
        tag = stichtag or timezone.localdate()
        return self.filter(von__lte=tag).filter(Q(bis__isnull=True) | Q(bis__gte=tag))


class Mitgliedschaft(models.Model):
    gruppe = models.ForeignKey(Gruppe, on_delete=models.CASCADE, related_name="mitgliedschaften", verbose_name="Gruppe")
    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="mitgliedschaften", verbose_name="Schüler:in")
    von = models.DateField("Von")
    bis = models.DateField("Bis", null=True, blank=True, help_text="leer = bis auf Weiteres")
    rolle = models.CharField("Rolle", max_length=40, blank=True, help_text="z. B. Klassensprecher:in")
    history = HistoricalRecords(verbose_name="Änderungsprotokoll Mitgliedschaft")

    objects = MitgliedschaftQuerySet.as_manager()

    class Meta:
        verbose_name = "Mitgliedschaft"
        verbose_name_plural = "Mitgliedschaften"
        ordering = ["gruppe", "schueler__person__nachname"]

    def __str__(self):
        return f"{self.schueler} in {self.gruppe.name}"

    def clean(self):
        if self.von and self.bis and self.bis < self.von:
            raise ValidationError("'Bis' darf nicht vor 'Von' liegen.")
        if not (self.gruppe_id and self.schueler_id and self.von):
            return
        # Eine Schülerin / ein Schüler darf zu einem Zeitpunkt nur in einer Stammklasse sein.
        if self.gruppe.typ == Gruppe.STAMMKLASSE:
            ueberlappend = Mitgliedschaft.objects.filter(
                schueler_id=self.schueler_id,
                gruppe__typ=Gruppe.STAMMKLASSE,
                gruppe__schuljahr=self.gruppe.schuljahr,
            ).exclude(pk=self.pk)
            ende = self.bis or self.gruppe.schuljahr.ende
            ueberlappend = ueberlappend.filter(von__lte=ende).filter(Q(bis__isnull=True) | Q(bis__gte=self.von))
            if ueberlappend.exists():
                raise ValidationError(
                    "Diese Person ist im gewählten Zeitraum bereits Mitglied einer anderen Stammklasse. "
                    "Bitte die alte Mitgliedschaft zuerst mit einem Enddatum beenden."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Fach(models.Model):
    kuerzel = models.CharField("Kürzel", max_length=10, unique=True, help_text="wie im Stundenplan, z. B. CH")
    name = models.CharField("Bezeichnung", max_length=60)
    reihenfolge = models.PositiveSmallIntegerField("Reihenfolge auf dem Zeugnis", default=100)

    class Meta:
        verbose_name = "Fach"
        verbose_name_plural = "Fächer"
        ordering = ["reihenfolge", "name"]

    def __str__(self):
        return f"{self.name} ({self.kuerzel})"


class Einwilligung(models.Model):
    ZWECKE = [
        ("foto_intern", "Fotos für schulinterne Zwecke"),
        ("foto_web", "Fotos auf Website / Social Media"),
        ("kontaktliste", "Weitergabe in Klassenkontaktliste"),
        ("ausfluege", "Teilnahme an Ausflügen"),
        ("sonstige", "Sonstiges"),
    ]

    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="einwilligungen", verbose_name="Schüler:in")
    zweck = models.CharField("Zweck", max_length=20, choices=ZWECKE)
    beschreibung = models.CharField("Beschreibung", max_length=200, blank=True)
    erteilt_durch = models.ForeignKey(Person, on_delete=models.PROTECT, verbose_name="Erteilt durch")
    erteilt_am = models.DateField("Erteilt am")
    widerrufen_am = models.DateField("Widerrufen am", null=True, blank=True)
    history = HistoricalRecords(verbose_name="Änderungsprotokoll Einwilligung")

    class Meta:
        verbose_name = "Einwilligung"
        verbose_name_plural = "Einwilligungen"
        ordering = ["schueler", "zweck"]

    def __str__(self):
        return f"{self.get_zweck_display()} – {self.schueler}"

    @property
    def gueltig(self):
        return self.widerrufen_am is None or self.widerrufen_am > timezone.localdate()


class Dokument(models.Model):
    KATEGORIEN = [
        ("attest", "Attest / Entschuldigung"),
        ("zeugnis", "Zeugnis"),
        ("einwilligung", "Einverständniserklärung"),
        ("vertrag", "Vertrag / Anmeldung"),
        ("foerderung", "Förderplan / Nachteilsausgleich"),
        ("sonstiges", "Sonstiges"),
    ]
    STUFEN = [("normal", "Normal (Klassenleitung, Verwaltung)"), ("vertraulich", "Vertraulich (nur Verwaltung, Leitung)")]

    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="dokumente", verbose_name="Person")
    kategorie = models.CharField("Kategorie", max_length=15, choices=KATEGORIEN)
    titel = models.CharField("Titel", max_length=120)
    datei = models.FileField("Datei", upload_to="personen/%Y/")
    zugriffsstufe = models.CharField("Zugriffsstufe", max_length=12, choices=STUFEN, default="normal")
    aufbewahren_bis = models.DateField("Aufbewahren bis", null=True, blank=True)
    hochgeladen_am = models.DateTimeField(auto_now_add=True)
    hochgeladen_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name="Hochgeladen von"
    )

    class Meta:
        verbose_name = "Dokument"
        verbose_name_plural = "Dokumente"
        ordering = ["-hochgeladen_am"]

    def __str__(self):
        return f"{self.titel} ({self.person})"
