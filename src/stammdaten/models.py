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

    GESCHLECHT = [("w", "weiblich"), ("m", "männlich"), ("d", "divers"), ("", "keine Angabe")]

    anrede = models.CharField("Anrede", max_length=20, blank=True, help_text="z. B. Frau, Herr")
    titel = models.CharField("Titel", max_length=30, blank=True, help_text="z. B. Dr.")
    vorname = models.CharField("Vorname(n)", max_length=80)
    nachname = models.CharField("Nachname", max_length=80)
    rufname = models.CharField("Rufname", max_length=80, blank=True)
    geschlecht = models.CharField("Geschlecht", max_length=1, choices=GESCHLECHT, blank=True)
    geburtsdatum = models.DateField("Geburtsdatum", null=True, blank=True)
    geburtsort = models.CharField("Geburtsort", max_length=80, blank=True)
    geburtsland = models.CharField("Geburtsland", max_length=60, blank=True)
    staatsangehoerigkeiten = models.CharField(
        "Staatsangehörigkeit(en)", max_length=120, blank=True, help_text="mehrere durch Komma trennen"
    )
    email = models.EmailField("E-Mail", blank=True)
    telefon = models.CharField("Telefon (privat)", max_length=40, blank=True)
    mobil = models.CharField("Mobil", max_length=40, blank=True)
    telefon_dienstlich = models.CharField("Telefon (dienstlich)", max_length=40, blank=True)
    strasse = models.CharField("Straße / Hausnummer / Estate", max_length=120, blank=True)
    postfach = models.CharField("Postfach (P.O. Box)", max_length=40, blank=True)
    plz = models.CharField("PLZ / Postal Code", max_length=12, blank=True)
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

    RELIGIONSUNTERRICHT = [
        ("", "—"), ("ev", "Evangelische Religion"), ("kath", "Katholische Religion"),
        ("ethik", "Ethik"), ("sonstige", "Sonstiges / befreit"),
    ]
    SCHULWEG = [("", "—"), ("bus", "Schulbus"), ("abgeholt", "Wird gebracht / abgeholt"), ("selbst", "Selbstständig")]

    person = models.OneToOneField(Person, on_delete=models.CASCADE, related_name="schueler", verbose_name="Person")
    schuelernummer = models.CharField("Schülernummer", max_length=20, unique=True)
    eintrittsdatum = models.DateField("Eintritt", null=True, blank=True)
    eintritt_jahrgang = models.PositiveSmallIntegerField("Eingeschult / eingetreten in Jahrgang", null=True, blank=True)
    austrittsdatum = models.DateField("Austritt", null=True, blank=True)
    austrittsgrund = models.CharField("Austrittsgrund / Zielschule", max_length=200, blank=True)
    status = models.CharField("Status", max_length=10, choices=STATUS, default="aktiv")

    # Sprache und Förderung
    muttersprache = models.CharField("Erstsprache(n)", max_length=80, blank=True)
    familiensprache = models.CharField("Familiensprache(n)", max_length=80, blank=True)
    daz = models.BooleanField("DaZ-/DaF-Förderung", default=False)
    nachteilsausgleich = models.BooleanField("Nachteilsausgleich", default=False)
    foerderbedarf = models.CharField("Förderbedarf / Förderschwerpunkt", max_length=200, blank=True)
    religionsunterricht = models.CharField("Religion / Ethik", max_length=10, choices=RELIGIONSUNTERRICHT, blank=True)

    # Organisatorisches
    lebt_bei = models.CharField("Lebt bei", max_length=120, blank=True, help_text="z. B. beiden Eltern, Mutter, Gastfamilie")
    schulweg = models.CharField("Schulweg", max_length=10, choices=SCHULWEG, blank=True)
    buslinie = models.CharField("Buslinie / Haltestelle", max_length=80, blank=True)
    abholhinweise = models.CharField("Abholhinweise", max_length=200, blank=True)
    bemerkungen = models.TextField("Bemerkungen (Verwaltung)", blank=True)
    zusatzfelder = models.JSONField("Zusatzfelder", default=dict, blank=True, editable=False)
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

    def aktueller_laufbahnabschnitt(self):
        return self.laufbahn.select_related("bildungsgang", "schuljahr").order_by("-schuljahr__beginn", "-von").first()


class Personalbereich(models.Model):
    """
    Arbeitsbereich / Abteilung, frei pflegbar: z. B. Lehrkräfte, HR, Reinigung, Sicherheit,
    Facility, Coaches im Nachmittagsbereich, Küche, Transport.
    """

    kuerzel = models.CharField("Kürzel", max_length=12, unique=True)
    name = models.CharField("Bezeichnung", max_length=80)
    unterrichtet = models.BooleanField(
        "Unterrichtender Bereich", default=False,
        help_text="Für unterrichtendes Personal sind Kürzel (Stundenplan) und Lehrbefähigungen relevant.",
    )
    reihenfolge = models.PositiveSmallIntegerField("Reihenfolge", default=10)

    class Meta:
        verbose_name = "Personalbereich"
        verbose_name_plural = "Personalbereiche"
        ordering = ["reihenfolge", "name"]

    def __str__(self):
        return self.name


class Dienstleister(models.Model):
    """Externe Firma, über die Personal eingesetzt wird (z. B. Sicherheits- oder Reinigungsfirma)."""

    name = models.CharField("Firma", max_length=120, unique=True)
    leistung = models.CharField("Leistung", max_length=120, blank=True, help_text="z. B. Sicherheitsdienst, Gebäudereinigung")
    ansprechperson = models.CharField("Ansprechperson", max_length=120, blank=True)
    telefon = models.CharField("Telefon", max_length=40, blank=True)
    email = models.EmailField("E-Mail", blank=True)
    vertrag_bis = models.DateField("Vertrag bis", null=True, blank=True)
    bemerkungen = models.TextField("Bemerkungen", blank=True)

    class Meta:
        verbose_name = "Dienstleister (Firma)"
        verbose_name_plural = "Dienstleister (Firmen)"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Personalprofil(models.Model):
    ANSTELLUNG = [
        ("adlk", "Auslandsdienstlehrkraft (ADLK)"),
        ("bplk", "Bundesprogrammlehrkraft (BPLK)"),
        ("lplk", "Landesprogrammlehrkraft (LPLK)"),
        ("olk", "Ortslehrkraft (OLK)"),
        ("ortskraft", "Ortskraft (direkt angestellt)"),
        ("teilzeit", "Ortskraft in Teilzeit / Aushilfe"),
        ("honorar", "Honorarkraft / Coach auf Honorarbasis"),
        ("dienstleister", "Über externen Dienstleister eingesetzt"),
        ("praktikum", "Praktikum / Referendariat / Freiwilligendienst"),
        ("sonstige", "Sonstige"),
    ]

    person = models.OneToOneField(Person, on_delete=models.CASCADE, related_name="personal", verbose_name="Person")
    bereich = models.ForeignKey(
        Personalbereich, null=True, blank=True, on_delete=models.PROTECT, related_name="personal", verbose_name="Bereich"
    )
    stellenbezeichnung = models.CharField(
        "Stellenbezeichnung", max_length=100, blank=True,
        help_text="z. B. Reinigungskraft, Head of Security, Fußballcoach, HR-Referentin",
    )
    kuerzel = models.CharField(
        "Kürzel", max_length=8, unique=True, null=True, blank=True,
        help_text="wie im Stundenplan, z. B. KRO – Pflicht für unterrichtende Bereiche",
    )
    aktiv = models.BooleanField("Aktiv", default=True)
    vorgesetzt = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="mitarbeitende", verbose_name="Vorgesetzte:r"
    )

    # Dienstverhältnis
    personalnummer = models.CharField("Personalnummer", max_length=20, blank=True)
    anstellungsart = models.CharField("Anstellungsart", max_length=14, choices=ANSTELLUNG, blank=True)
    dienstleister = models.ForeignKey(
        Dienstleister, null=True, blank=True, on_delete=models.PROTECT, related_name="personal",
        verbose_name="Dienstleister (Firma)", help_text="nur bei Einsatz über eine externe Firma",
    )
    dienstbeginn = models.DateField("Dienstbeginn an der Schule", null=True, blank=True)
    vertragsende = models.DateField("Vertragsende / Rückkehr", null=True, blank=True)
    wochenstunden = models.DecimalField(
        "Deputat / Wochenstunden", max_digits=4, decimal_places=1, null=True, blank=True,
        help_text="bei Lehrkräften Unterrichtsstunden, sonst Arbeitsstunden",
    )
    ermaessigung = models.DecimalField("Ermäßigung / Anrechnung (Std.)", max_digits=4, decimal_places=1, null=True, blank=True)
    arbeitszeit = models.CharField("Arbeitszeit / Schicht", max_length=120, blank=True, help_text="z. B. Mo–Fr 6–14 Uhr, Nachtschicht")
    arbeitserlaubnis_bis = models.DateField("Arbeitserlaubnis gültig bis", null=True, blank=True)

    # Tätigkeit
    lehrbefaehigungen = models.ManyToManyField("Fach", blank=True, related_name="lehrkraefte", verbose_name="Lehrbefähigungen")
    weitere_funktionen = models.CharField(
        "Weitere Funktionen", max_length=200, blank=True, help_text="z. B. Mittelstufenkoordination, Fachleitung Chemie, Ersthelfer:in"
    )
    dienst_email = models.EmailField("Dienstliche E-Mail", blank=True)
    raum = models.CharField("Büro / Fachraum / Einsatzort", max_length=60, blank=True)
    ausweisnummer = models.CharField("Dienstausweis / Badge-Nr.", max_length=30, blank=True)
    bemerkungen = models.TextField("Bemerkungen (Personalverwaltung)", blank=True)
    zusatzfelder = models.JSONField("Zusatzfelder", default=dict, blank=True, editable=False)
    history = HistoricalRecords(verbose_name="Änderungsprotokoll Personal", m2m_fields=[lehrbefaehigungen])

    class Meta:
        verbose_name = "Personal"
        verbose_name_plural = "Personal"
        ordering = ["person__nachname", "person__vorname"]
        permissions = [("view_hr_daten", "Darf HR-Daten sehen (Dienstverhältnis, Nachweise, Abwesenheiten)")]

    def __str__(self):
        return f"{self.kuerzel} – {self.person.anzeigename}" if self.kuerzel else self.person.anzeigename

    def clean(self):
        if self.dienstbeginn and self.vertragsende and self.vertragsende < self.dienstbeginn:
            raise ValidationError("Das Vertragsende liegt vor dem Dienstbeginn.")
        if self.bereich_id and self.bereich.unterrichtet and not self.kuerzel:
            raise ValidationError({"kuerzel": "Für unterrichtendes Personal ist ein Kürzel erforderlich (Stundenplan)."})
        if self.anstellungsart == "dienstleister" and not self.dienstleister_id:
            raise ValidationError({"dienstleister": "Bitte die Firma angeben, über die die Person eingesetzt wird."})
        if self.vorgesetzt_id and self.vorgesetzt_id == self.pk:
            raise ValidationError({"vorgesetzt": "Eine Person kann nicht ihre eigene Vorgesetzte sein."})

    def save(self, *args, **kwargs):
        self.kuerzel = (self.kuerzel or "").strip().upper() or None
        super().save(*args, **kwargs)

    @property
    def ist_lehrkraft(self):
        return bool(self.bereich_id and self.bereich.unterrichtet)

    def nachweisstatus(self, heute=None, vorlauf_tage=60):
        """
        Liste von (Nachweisart, Status, Nachweis|None) für alle relevanten Nachweisarten.
        Status: "fehlt", "abgelaufen", "laeuft_ab", "gueltig".
        """
        from datetime import timedelta

        heute = heute or timezone.localdate()
        vorhandene = {}
        for n in self.nachweise.select_related("art").order_by("art_id", "-gueltig_bis"):
            vorhandene.setdefault(n.art_id, n)
        arten = {n.art for n in vorhandene.values()}
        if self.bereich_id:
            arten |= set(self.bereich.pflichtnachweise.all())
        ergebnis = []
        for art in sorted(arten, key=lambda a: (a.reihenfolge, a.name)):
            n = vorhandene.get(art.pk)
            if n is None:
                status = "fehlt"
            elif n.gueltig_bis and n.gueltig_bis < heute:
                status = "abgelaufen"
            elif n.gueltig_bis and n.gueltig_bis <= heute + timedelta(days=vorlauf_tage):
                status = "laeuft_ab"
            else:
                status = "gueltig"
            ergebnis.append((art, status, n))
        return ergebnis

    def offene_nachweise(self, **kw):
        return [(a, st, n) for a, st, n in self.nachweisstatus(**kw) if st != "gueltig"]


class Nachweisart(models.Model):
    """z. B. Führungszeugnis / Certificate of Good Conduct, Erste-Hilfe-Kurs, Kinderschutzschulung."""

    name = models.CharField("Bezeichnung", max_length=120, unique=True)
    gueltigkeit_monate = models.PositiveSmallIntegerField(
        "Gültigkeit (Monate)", null=True, blank=True, help_text="leer = unbefristet; dient als Vorschlag für „gültig bis“"
    )
    pflicht_fuer = models.ManyToManyField(
        Personalbereich, blank=True, related_name="pflichtnachweise", verbose_name="Pflicht für Bereiche"
    )
    reihenfolge = models.PositiveSmallIntegerField("Reihenfolge", default=10)
    beschreibung = models.CharField("Beschreibung", max_length=200, blank=True)

    class Meta:
        verbose_name = "Nachweisart"
        verbose_name_plural = "Nachweisarten"
        ordering = ["reihenfolge", "name"]

    def __str__(self):
        return self.name


class Nachweis(models.Model):
    personal = models.ForeignKey(Personalprofil, on_delete=models.CASCADE, related_name="nachweise", verbose_name="Personal")
    art = models.ForeignKey(Nachweisart, on_delete=models.PROTECT, verbose_name="Nachweis")
    ausgestellt_am = models.DateField("Ausgestellt am", null=True, blank=True)
    gueltig_bis = models.DateField("Gültig bis", null=True, blank=True, help_text="leer = wird aus der Nachweisart berechnet bzw. unbefristet")
    datei = models.FileField("Datei", upload_to="nachweise/%Y/", blank=True)
    bemerkung = models.CharField("Bemerkung", max_length=200, blank=True)
    history = HistoricalRecords(verbose_name="Änderungsprotokoll Nachweis")

    class Meta:
        verbose_name = "Nachweis"
        verbose_name_plural = "Nachweise"
        ordering = ["personal", "art__reihenfolge", "-gueltig_bis"]

    def __str__(self):
        return f"{self.art} – {self.personal}"

    def save(self, *args, **kwargs):
        if not self.gueltig_bis and self.ausgestellt_am and self.art.gueltigkeit_monate:
            m = self.ausgestellt_am.month - 1 + self.art.gueltigkeit_monate
            jahr, monat = self.ausgestellt_am.year + m // 12, m % 12 + 1
            import calendar

            tag = min(self.ausgestellt_am.day, calendar.monthrange(jahr, monat)[1])
            self.gueltig_bis = self.ausgestellt_am.replace(year=jahr, month=monat, day=tag)
        super().save(*args, **kwargs)

    def clean(self):
        if self.ausgestellt_am and self.gueltig_bis and self.gueltig_bis < self.ausgestellt_am:
            raise ValidationError("„Gültig bis“ liegt vor dem Ausstellungsdatum.")


class Personalabwesenheit(models.Model):
    ARTEN = [
        ("urlaub", "Urlaub"),
        ("krank", "Krankmeldung"),
        ("fortbildung", "Fortbildung"),
        ("dienstreise", "Dienstreise / Klassenfahrt"),
        ("sonderurlaub", "Sonderurlaub"),
        ("sonstige", "Sonstiges"),
    ]
    STATUS = [("beantragt", "beantragt"), ("genehmigt", "genehmigt"), ("abgelehnt", "abgelehnt")]

    personal = models.ForeignKey(Personalprofil, on_delete=models.CASCADE, related_name="abwesenheiten", verbose_name="Personal")
    art = models.CharField("Art", max_length=14, choices=ARTEN)
    von = models.DateField("Von")
    bis = models.DateField("Bis")
    halbtags = models.BooleanField("Nur halbtags", default=False)
    status = models.CharField("Status", max_length=10, choices=STATUS, default="genehmigt")
    bemerkung = models.CharField(
        "Bemerkung", max_length=200, blank=True, help_text="Keine Diagnosen oder Gesundheitsdaten eintragen."
    )
    history = HistoricalRecords(verbose_name="Änderungsprotokoll Personalabwesenheit")

    class Meta:
        verbose_name = "Personalabwesenheit"
        verbose_name_plural = "Personalabwesenheiten"
        ordering = ["-von"]

    def __str__(self):
        return f"{self.personal}: {self.get_art_display()} {self.von:%d.%m.}–{self.bis:%d.%m.%Y}"

    def clean(self):
        if self.von and self.bis and self.bis < self.von:
            raise ValidationError("„Bis“ darf nicht vor „Von“ liegen.")

    @property
    def arbeitstage(self):
        from datetime import timedelta

        tag, n = self.von, 0
        while tag <= self.bis:
            n += tag.weekday() < 5
            tag += timedelta(days=1)
        return n / 2 if self.halbtags else n


class Fortbildung(models.Model):
    personal = models.ForeignKey(Personalprofil, on_delete=models.CASCADE, related_name="fortbildungen", verbose_name="Personal")
    titel = models.CharField("Titel", max_length=150)
    anbieter = models.CharField("Anbieter", max_length=100, blank=True, help_text="z. B. ZfA, Regionale Fortbildung, schulintern")
    datum = models.DateField("Datum")
    umfang_stunden = models.DecimalField("Umfang (Std.)", max_digits=5, decimal_places=1, null=True, blank=True)
    nachweis_liegt_vor = models.BooleanField("Nachweis liegt vor", default=False)

    class Meta:
        verbose_name = "Fortbildung"
        verbose_name_plural = "Fortbildungen"
        ordering = ["-datum"]

    def __str__(self):
        return f"{self.titel} ({self.datum:%d.%m.%Y})"


class Notfallkontakt(models.Model):
    """Notfallkontakte für Personal (bei Schüler:innen über die Beziehungen zu Eltern / Kontaktpersonen)."""

    personal = models.ForeignKey(Personalprofil, on_delete=models.CASCADE, related_name="notfallkontakte", verbose_name="Personal")
    name = models.CharField("Name", max_length=120)
    beziehung = models.CharField("Beziehung", max_length=60, blank=True, help_text="z. B. Ehepartner:in")
    telefon = models.CharField("Telefon", max_length=40)
    reihenfolge = models.PositiveSmallIntegerField("Reihenfolge", default=1)

    class Meta:
        verbose_name = "Notfallkontakt"
        verbose_name_plural = "Notfallkontakte"
        ordering = ["personal", "reihenfolge"]

    def __str__(self):
        return f"{self.name} ({self.telefon})"


class Elternprofil(models.Model):
    """Zusatzdaten für Erziehungsberechtigte und Kontaktpersonen."""

    KORRESPONDENZ = [("email", "E-Mail"), ("app", "App / Portal"), ("post", "Post"), ("telefon", "Telefon")]

    person = models.OneToOneField(Person, on_delete=models.CASCADE, related_name="elternprofil", verbose_name="Person")
    beruf = models.CharField("Beruf", max_length=100, blank=True)
    arbeitgeber = models.CharField("Arbeitgeber / Organisation", max_length=120, blank=True)
    korrespondenzweg = models.CharField("Bevorzugter Kommunikationsweg", max_length=10, choices=KORRESPONDENZ, default="email")
    schulverein_mitglied = models.BooleanField("Mitglied im Schulverein", default=False)
    mitgliedsnummer = models.CharField("Mitgliedsnummer Schulverein", max_length=30, blank=True)
    elternvertretung = models.CharField(
        "Funktion in der Elternvertretung", max_length=100, blank=True, help_text="z. B. Klassenelternsprecher:in 9a"
    )
    kontaktdaten_weitergabe = models.BooleanField(
        "Einverstanden mit Weitergabe der Kontaktdaten an die Klassenelternschaft", default=False
    )
    zusatzfelder = models.JSONField("Zusatzfelder", default=dict, blank=True, editable=False)
    history = HistoricalRecords(verbose_name="Änderungsprotokoll Elternprofil")

    class Meta:
        verbose_name = "Elternprofil"
        verbose_name_plural = "Elternprofile"

    def __str__(self):
        return f"Elternprofil {self.person}"


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


class Bildungsgang(models.Model):
    """Konfigurierbar, z. B. Grundschule, Hauptschul-, Realschul-, Gymnasialer Bildungsgang, Oberstufe."""

    kuerzel = models.CharField("Kürzel", max_length=10, unique=True)
    name = models.CharField("Bezeichnung", max_length=80)
    angestrebter_abschluss = models.CharField("Angestrebter Abschluss", max_length=120, blank=True)
    jahrgang_von = models.PositiveSmallIntegerField("ab Jahrgang", null=True, blank=True)
    jahrgang_bis = models.PositiveSmallIntegerField("bis Jahrgang", null=True, blank=True)
    reihenfolge = models.PositiveSmallIntegerField("Reihenfolge", default=10)

    class Meta:
        verbose_name = "Bildungsgang"
        verbose_name_plural = "Bildungsgänge"
        ordering = ["reihenfolge", "name"]

    def __str__(self):
        return self.name


class Laufbahnabschnitt(models.Model):
    """
    Ein Abschnitt der Schullaufbahn, in der Regel ein Schuljahr.
    Wechselt jemand im laufenden Schuljahr den Bildungsgang, entstehen zwei Abschnitte mit Von-/Bis-Datum.
    """

    ERGEBNISSE = [
        ("laufend", "laufend"),
        ("versetzt", "versetzt"),
        ("versetzt_auflage", "versetzt mit Auflage / auf Probe"),
        ("nicht_versetzt", "nicht versetzt (Wiederholung)"),
        ("freiwillig_wiederholt", "freiwillige Wiederholung"),
        ("wechsel", "Wechsel des Bildungsgangs"),
        ("abschluss", "Abschluss erreicht"),
        ("abgang", "Abgang ohne Abschluss / Schulwechsel"),
    ]

    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="laufbahn", verbose_name="Schüler:in")
    schuljahr = models.ForeignKey(Schuljahr, on_delete=models.PROTECT, related_name="laufbahnabschnitte", verbose_name="Schuljahr")
    jahrgang = models.PositiveSmallIntegerField("Jahrgang")
    bildungsgang = models.ForeignKey(Bildungsgang, on_delete=models.PROTECT, verbose_name="Bildungsgang")
    stammklasse = models.ForeignKey(
        Gruppe, null=True, blank=True, on_delete=models.SET_NULL, limit_choices_to={"typ": "stammklasse"},
        verbose_name="Stammklasse",
    )
    von = models.DateField("Von", null=True, blank=True, help_text="leer = Beginn des Schuljahres")
    bis = models.DateField("Bis", null=True, blank=True, help_text="leer = Ende des Schuljahres")
    ergebnis = models.CharField("Ergebnis", max_length=24, choices=ERGEBNISSE, default="laufend")
    bemerkung = models.CharField("Bemerkung", max_length=200, blank=True, help_text="z. B. Konferenzbeschluss vom ...")
    history = HistoricalRecords(verbose_name="Änderungsprotokoll Schullaufbahn")

    class Meta:
        verbose_name = "Laufbahnabschnitt"
        verbose_name_plural = "Schullaufbahn"
        ordering = ["schueler", "schuljahr__beginn", "von"]

    def __str__(self):
        return f"{self.schuljahr} · Jg. {self.jahrgang} · {self.bildungsgang}"

    def clean(self):
        if self.von and self.bis and self.bis < self.von:
            raise ValidationError("'Bis' darf nicht vor 'Von' liegen.")
        if self.stammklasse_id and self.schuljahr_id and self.stammklasse.schuljahr_id != self.schuljahr_id:
            raise ValidationError({"stammklasse": "Die Stammklasse gehört zu einem anderen Schuljahr."})
        bg = self.bildungsgang if self.bildungsgang_id else None
        if bg and self.jahrgang and ((bg.jahrgang_von and self.jahrgang < bg.jahrgang_von) or (bg.jahrgang_bis and self.jahrgang > bg.jahrgang_bis)):
            raise ValidationError({"jahrgang": f"Jahrgang {self.jahrgang} liegt außerhalb des Bildungsgangs {bg}."})


class Abschlussart(models.Model):
    kuerzel = models.CharField("Kürzel", max_length=12, unique=True)
    name = models.CharField("Bezeichnung", max_length=120)
    reihenfolge = models.PositiveSmallIntegerField("Reihenfolge", default=10)

    class Meta:
        verbose_name = "Abschlussart"
        verbose_name_plural = "Abschlussarten"
        ordering = ["reihenfolge", "name"]

    def __str__(self):
        return self.name


class Abschluss(models.Model):
    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="abschluesse", verbose_name="Schüler:in")
    art = models.ForeignKey(Abschlussart, on_delete=models.PROTECT, verbose_name="Abschluss / Zertifikat")
    datum = models.DateField("Datum")
    durchschnitt = models.DecimalField("Durchschnitt / Gesamtnote", max_digits=4, decimal_places=2, null=True, blank=True)
    niveau = models.CharField("Niveau / Stufe", max_length=30, blank=True, help_text="z. B. B1 / C1 beim DSD")
    an_dieser_schule = models.BooleanField("An dieser Schule erworben", default=True)
    bemerkung = models.CharField("Bemerkung", max_length=200, blank=True)
    history = HistoricalRecords(verbose_name="Änderungsprotokoll Abschluss")

    class Meta:
        verbose_name = "Abschluss / Zertifikat"
        verbose_name_plural = "Abschlüsse / Zertifikate"
        ordering = ["schueler", "datum"]

    def __str__(self):
        return f"{self.art} ({self.datum:%m/%Y})"


class VorherigeSchule(models.Model):
    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="vorherige_schulen", verbose_name="Schüler:in")
    name = models.CharField("Schule", max_length=150)
    ort = models.CharField("Ort", max_length=80, blank=True)
    land = models.CharField("Land", max_length=60, blank=True)
    schulform = models.CharField("Schulform / System", max_length=80, blank=True, help_text="z. B. Gymnasium (DE), CBC (KE), IGCSE")
    von = models.DateField("Von", null=True, blank=True)
    bis = models.DateField("Bis", null=True, blank=True)
    letzter_jahrgang = models.CharField("Zuletzt besuchte Klasse", max_length=20, blank=True)

    class Meta:
        verbose_name = "Vorherige Schule"
        verbose_name_plural = "Vorherige Schulen"
        ordering = ["schueler", "von"]

    def __str__(self):
        return self.name


class Sprachenfolge(models.Model):
    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="sprachenfolge", verbose_name="Schüler:in")
    position = models.PositiveSmallIntegerField("Fremdsprache Nr.", help_text="1 = erste Fremdsprache usw.")
    fach = models.ForeignKey(Fach, on_delete=models.PROTECT, verbose_name="Sprache")
    ab_jahrgang = models.PositiveSmallIntegerField("ab Jahrgang")
    bis_jahrgang = models.PositiveSmallIntegerField("bis Jahrgang", null=True, blank=True)

    class Meta:
        verbose_name = "Sprachenfolge"
        verbose_name_plural = "Sprachenfolge"
        ordering = ["schueler", "position"]
        unique_together = [("schueler", "position")]

    def __str__(self):
        return f"{self.position}. Fremdsprache: {self.fach.name} ab Jg. {self.ab_jahrgang}"


class Gesundheitsangaben(models.Model):
    """
    Besonders schützenswerte Daten. Eigene Tabelle mit eigenem Zugriffsrecht:
    Lehrkräfte sehen sie standardmäßig NICHT, nur Verwaltung und Schulleitung.
    """

    schueler = models.OneToOneField(Schuelerprofil, on_delete=models.CASCADE, related_name="gesundheit", verbose_name="Schüler:in")
    allergien = models.CharField("Allergien / Unverträglichkeiten", max_length=200, blank=True)
    erkrankungen = models.CharField("Chronische Erkrankungen", max_length=200, blank=True)
    medikamente = models.CharField("Medikamente in der Schule", max_length=200, blank=True)
    notfallhinweise = models.TextField("Hinweise für Notfälle", blank=True)
    arzt = models.CharField("Ärztin / Arzt (Name, Telefon)", max_length=150, blank=True)
    krankenversicherung = models.CharField("Krankenversicherung", max_length=120, blank=True)
    schwimmen_erlaubt = models.BooleanField("Teilnahme am Schwimmunterricht", default=True)
    history = HistoricalRecords(verbose_name="Änderungsprotokoll Gesundheitsangaben")

    class Meta:
        verbose_name = "Gesundheitsangaben"
        verbose_name_plural = "Gesundheitsangaben"
        permissions = [("view_gesundheit_klasse", "Darf Gesundheitsangaben der eigenen Klasse sehen")]

    def __str__(self):
        return f"Gesundheitsangaben {self.schueler}"

    @property
    def hat_eintraege(self):
        return any([self.allergien, self.erkrankungen, self.medikamente, self.notfallhinweise])


class Zusatzfeld(models.Model):
    """
    Frei definierbares Datenfeld für Schüler:innen, Personal oder Eltern.
    Die Werte liegen im Feld „zusatzfelder“ der jeweiligen Akte (JSON, Schlüssel = `schluessel`).
    Der Schlüssel bleibt nach dem Anlegen fest, damit gespeicherte Werte zugeordnet bleiben;
    Bezeichnung, Reihenfolge, Abschnitt usw. sind jederzeit änderbar.
    """

    ZIELGRUPPEN = [("schueler", "Schüler:innen"), ("personal", "Personal"), ("eltern", "Eltern / Kontaktpersonen")]
    TYPEN = [
        ("text", "Text (einzeilig)"),
        ("langtext", "Text (mehrzeilig)"),
        ("zahl", "Zahl"),
        ("datum", "Datum"),
        ("janein", "Ja / Nein"),
        ("auswahl", "Auswahl (eine Option)"),
        ("mehrfach", "Mehrfachauswahl"),
    ]
    SICHTBARKEIT = [
        ("alle", "Alle mit Aktenzugriff"),
        ("verwaltung", "Verwaltung, Leitung, HR"),
        ("hr", "Nur HR und Leitung"),
    ]

    zielgruppe = models.CharField("Für", max_length=10, choices=ZIELGRUPPEN)
    name = models.CharField("Bezeichnung", max_length=80)
    schluessel = models.SlugField(
        "Technischer Schlüssel", max_length=50, blank=True,
        help_text="wird automatisch aus der Bezeichnung erzeugt und ist danach fest",
    )
    typ = models.CharField("Feldtyp", max_length=10, choices=TYPEN, default="text")
    optionen = models.TextField("Optionen", blank=True, help_text="nur bei Auswahl / Mehrfachauswahl: eine Option pro Zeile")
    abschnitt = models.CharField("Abschnitt", max_length=60, blank=True, help_text="Überschrift zur Gruppierung, z. B. Sport, Logistik")
    hilfetext = models.CharField("Hilfetext", max_length=200, blank=True)
    pflicht = models.BooleanField("Pflichtfeld", default=False)
    sichtbarkeit = models.CharField(
        "Sichtbar für", max_length=10, choices=SICHTBARKEIT, default="verwaltung",
        help_text="„Alle mit Aktenzugriff“ schließt bei Schüler:innen die Klassenleitung ein; "
                  "„Nur HR und Leitung“ eignet sich für vertrauliche Personaldaten.",
    )
    in_liste = models.BooleanField("In Liste", default=False, help_text="als Spalte in der Übersichtsliste zeigen")
    reihenfolge = models.PositiveSmallIntegerField("Reihenfolge", default=10)
    aktiv = models.BooleanField("Aktiv", default=True, help_text="Deaktivieren statt löschen – gespeicherte Werte bleiben erhalten.")

    class Meta:
        verbose_name = "Zusatzfeld"
        verbose_name_plural = "Zusatzfelder (eigene Datenfelder)"
        ordering = ["zielgruppe", "abschnitt", "reihenfolge", "name"]
        constraints = [models.UniqueConstraint(fields=["zielgruppe", "schluessel"], name="zusatzfeld_schluessel_eindeutig")]

    def __str__(self):
        return f"{self.name} ({self.get_zielgruppe_display()})"

    @property
    def optionsliste(self):
        return [o.strip() for o in self.optionen.splitlines() if o.strip()]

    @property
    def formularname(self):
        return f"zusatz__{self.schluessel}"

    def clean(self):
        if self.typ in {"auswahl", "mehrfach"} and not self.optionsliste:
            raise ValidationError({"optionen": "Bitte mindestens eine Option angeben (eine pro Zeile)."})
        if not self.schluessel and self.name:
            self.schluessel = self._erzeuge_schluessel()

    def _erzeuge_schluessel(self):
        import re

        from django.utils.text import slugify

        basis = slugify(self.name.replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue"))
        basis = re.sub(r"[^a-z0-9]+", "_", basis).strip("_")[:40] or "feld"
        kandidat, n = basis, 2
        while Zusatzfeld.objects.filter(zielgruppe=self.zielgruppe, schluessel=kandidat).exclude(pk=self.pk).exists():
            kandidat, n = f"{basis}_{n}", n + 1
        return kandidat

    def save(self, *args, **kwargs):
        if not self.schluessel:
            self.schluessel = self._erzeuge_schluessel()
        super().save(*args, **kwargs)

    # ---- Umwandlung zwischen Formular, Speicher (JSON) und Anzeige

    def in_speicher(self, wert):
        if wert in (None, "", []):
            return None
        if self.typ == "datum":
            return wert.isoformat()
        if self.typ == "zahl":
            return str(wert)
        if self.typ == "mehrfach":
            return list(wert)
        return wert

    def aus_speicher(self, wert):
        from datetime import date
        from decimal import Decimal, InvalidOperation

        if wert in (None, ""):
            return None
        try:
            if self.typ == "datum":
                return date.fromisoformat(wert)
            if self.typ == "zahl":
                return Decimal(str(wert))
        except (ValueError, InvalidOperation):
            return None
        return wert

    def anzeigewert(self, wert):
        wert = self.aus_speicher(wert)
        if wert is None or wert == []:
            return "—"
        if self.typ == "datum":
            return wert.strftime("%d.%m.%Y")
        if self.typ == "janein":
            return "ja" if wert else "nein"
        if self.typ == "mehrfach":
            return ", ".join(wert)
        if self.typ == "zahl":
            return format(wert.normalize(), "f").replace(".", ",")
        return str(wert)
