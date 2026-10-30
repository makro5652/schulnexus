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
from django.utils.translation import gettext, gettext_lazy as _
from simple_history.models import HistoricalRecords

from .dokumente import ablagepfad, geschuetzter_speicher, groesse_lesbar, groesse_pruefen
from .sprache import LokalerNameMixin, datum, englisch_aktiv, lokal


class Schuljahr(models.Model):
    name = models.CharField(_("Bezeichnung"), max_length=20, unique=True, help_text=_("z. B. 2026/27"))
    beginn = models.DateField(_("Beginn"))
    ende = models.DateField(_("Ende"))
    aktiv = models.BooleanField(_("Aktuelles Schuljahr"), default=False)

    class Meta:
        verbose_name = _("Schuljahr")
        verbose_name_plural = _("Schuljahre")
        ordering = ["-beginn"]
        constraints = [
            models.UniqueConstraint(fields=["aktiv"], condition=Q(aktiv=True), name="nur_ein_aktives_schuljahr"),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.beginn and self.ende and self.ende <= self.beginn:
            raise ValidationError(_("Das Ende muss nach dem Beginn liegen."))

    @classmethod
    def aktuelles(cls):
        return cls.objects.filter(aktiv=True).first()

    def stichtag(self, datum=None):
        """Bezugstag innerhalb dieses Schuljahres: heute, aber nicht vor Beginn und nicht nach Ende."""
        datum = datum or timezone.localdate()
        return min(max(datum, self.beginn), self.ende)


class Abschnitt(LokalerNameMixin, models.Model):
    """Halbjahr bzw. Term innerhalb eines Schuljahres."""

    schuljahr = models.ForeignKey(Schuljahr, on_delete=models.CASCADE, related_name="abschnitte", verbose_name=_("Schuljahr"))
    name = models.CharField(_("Bezeichnung"), max_length=40, help_text=_("z. B. 1. Halbjahr"))
    name_en = models.CharField(_("Bezeichnung (Englisch)"), max_length=40, blank=True, help_text=_("z. B. 1st semester"))
    nummer = models.PositiveSmallIntegerField(_("Nummer"), default=1)
    beginn = models.DateField(_("Beginn"))
    ende = models.DateField(_("Ende"))

    class Meta:
        verbose_name = _("Abschnitt (Halbjahr)")
        verbose_name_plural = _("Abschnitte (Halbjahre)")
        ordering = ["schuljahr", "nummer"]
        unique_together = [("schuljahr", "nummer")]

    def __str__(self):
        return f"{self.schuljahr} – {self.lokal_name}"

    def clean(self):
        if self.beginn and self.ende and self.ende <= self.beginn:
            raise ValidationError(_("Das Ende muss nach dem Beginn liegen."))


class Person(models.Model):
    """Gemeinsamer Kern aller Menschen im System (Schüler:innen, Eltern, Personal)."""

    GESCHLECHT = [("w", _("weiblich")), ("m", _("männlich")), ("d", _("divers")), ("", _("keine Angabe"))]

    anrede = models.CharField(_("Anrede"), max_length=20, blank=True, help_text=_("z. B. Frau, Herr"))
    titel = models.CharField(_("Titel"), max_length=30, blank=True, help_text=_("z. B. Dr."))
    vorname = models.CharField(_("Vorname(n)"), max_length=80)
    nachname = models.CharField(_("Nachname"), max_length=80)
    rufname = models.CharField(_("Rufname"), max_length=80, blank=True)
    geschlecht = models.CharField(_("Geschlecht"), max_length=1, choices=GESCHLECHT, blank=True)
    geburtsdatum = models.DateField(_("Geburtsdatum"), null=True, blank=True)
    geburtsort = models.CharField(_("Geburtsort"), max_length=80, blank=True)
    geburtsland = models.CharField(_("Geburtsland"), max_length=60, blank=True)
    staatsangehoerigkeiten = models.CharField(
        _("Staatsangehörigkeit(en)"), max_length=120, blank=True, help_text=_("mehrere durch Komma trennen")
    )
    email = models.EmailField(_("E-Mail"), blank=True)
    telefon = models.CharField(_("Telefon (privat)"), max_length=40, blank=True)
    mobil = models.CharField(_("Mobil"), max_length=40, blank=True)
    telefon_dienstlich = models.CharField(_("Telefon (dienstlich)"), max_length=40, blank=True)
    strasse = models.CharField(_("Straße / Hausnummer / Estate"), max_length=120, blank=True)
    postfach = models.CharField(_("Postfach (P.O. Box)"), max_length=40, blank=True)
    plz = models.CharField(_("PLZ / Postal Code"), max_length=12, blank=True)
    ort = models.CharField(_("Ort"), max_length=80, blank=True)
    land = models.CharField(_("Land"), max_length=60, blank=True, default="Kenia")
    sprache = models.CharField(
        _("Bevorzugte Sprache"), max_length=2, choices=[("de", _("Deutsch")), ("en", _("Englisch"))], default="de"
    )
    benutzer = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="person", verbose_name=_("Benutzerkonto"),
    )
    notizen = models.TextField(_("Interne Notizen"), blank=True)
    geburtstag_anzeigen = models.BooleanField(
        _("Geburtstag auf der Startseite anzeigen"), default=True,
        help_text=_("Tag und Monat erscheinen in der Geburtstagsübersicht; das Alter nur bei Schüler:innen."),
    )
    erstellt = models.DateTimeField(auto_now_add=True)
    geaendert = models.DateTimeField(auto_now=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Person"))

    class Meta:
        verbose_name = _("Person")
        verbose_name_plural = _("Personen")
        ordering = ["nachname", "vorname"]

    def __str__(self):
        return f"{self.nachname}, {self.rufname or self.vorname}"

    @property
    def anzeigename(self):
        return f"{self.rufname or self.vorname} {self.nachname}"


class Schuelerprofil(models.Model):
    STATUS = [("aktiv", _("Aktiv")), ("abgang", _("Abgegangen")), ("bewerber", _("Bewerber:in"))]

    RELIGIONSUNTERRICHT = [
        ("", "—"), ("ev", _("Evangelische Religion")), ("kath", _("Katholische Religion")),
        ("ethik", _("Ethik")), ("sonstige", _("Sonstiges / befreit")),
    ]
    SCHULWEG = [("", "—"), ("bus", _("Schulbus")), ("abgeholt", _("Wird gebracht / abgeholt")), ("selbst", _("Selbstständig"))]

    person = models.OneToOneField(Person, on_delete=models.CASCADE, related_name="schueler", verbose_name=_("Person"))
    schuelernummer = models.CharField(_("Schülernummer"), max_length=20, unique=True)
    eintrittsdatum = models.DateField(_("Eintritt"), null=True, blank=True)
    eintritt_jahrgang = models.PositiveSmallIntegerField(_("Eingeschult / eingetreten in Jahrgang"), null=True, blank=True)
    austrittsdatum = models.DateField(_("Austritt"), null=True, blank=True)
    austrittsgrund = models.CharField(_("Austrittsgrund / Zielschule"), max_length=200, blank=True)
    status = models.CharField(_("Status"), max_length=10, choices=STATUS, default="aktiv")

    # Sprache und Förderung
    muttersprache = models.CharField(_("Erstsprache(n)"), max_length=80, blank=True)
    familiensprache = models.CharField(_("Familiensprache(n)"), max_length=80, blank=True)
    daz = models.BooleanField(_("DaZ-/DaF-Förderung"), default=False)
    nachteilsausgleich = models.BooleanField(
        _("Nachteilsausgleich"), default=False, help_text=_("Einzelheiten im Bereich Förderung › Nachteilsausgleiche")
    )
    foerderbedarf = models.CharField(_("Förderbedarf / Förderschwerpunkt"), max_length=200, blank=True)
    religionsunterricht = models.CharField(_("Religion / Ethik"), max_length=10, choices=RELIGIONSUNTERRICHT, blank=True)

    # Organisatorisches
    lebt_bei = models.CharField(_("Lebt bei"), max_length=120, blank=True, help_text=_("z. B. beiden Eltern, Mutter, Gastfamilie"))
    schulweg = models.CharField(_("Schulweg"), max_length=10, choices=SCHULWEG, blank=True)
    buslinie = models.CharField(_("Buslinie / Haltestelle"), max_length=80, blank=True)
    abholhinweise = models.CharField(_("Abholhinweise"), max_length=200, blank=True)
    bemerkungen = models.TextField(_("Bemerkungen (Verwaltung)"), blank=True)
    zusatzfelder = models.JSONField(_("Zusatzfelder"), default=dict, blank=True, editable=False)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Schüler:in"))

    class Meta:
        verbose_name = _("Schüler:in")
        verbose_name_plural = _("Schüler:innen")
        ordering = ["person__nachname", "person__vorname"]

    def __str__(self):
        return str(self.person)

    @property
    def archiviert(self):
        """Abgegangene Schüler:innen stehen im Archiv (nur lesend, Löschfristen laufen)."""
        return self.status == "abgang"

    def stammklasse(self, schuljahr=None, stichtag=None):
        schuljahr = schuljahr or Schuljahr.aktuelles()
        if schuljahr and stichtag is None:
            stichtag = schuljahr.stichtag()
        qs = Mitgliedschaft.objects.aktiv(stichtag).filter(
            schueler=self, gruppe__typ=Gruppe.STAMMKLASSE, gruppe__schuljahr=schuljahr
        )
        m = qs.select_related("gruppe").first()
        return m.gruppe if m else None

    def aktueller_laufbahnabschnitt(self):
        return self.laufbahn.select_related("bildungsgang", "schuljahr").order_by("-schuljahr__beginn", "-von").first()


class Personalbereich(LokalerNameMixin, models.Model):
    """
    Arbeitsbereich / Abteilung, frei pflegbar: z. B. Lehrkräfte, HR, Reinigung, Sicherheit,
    Facility, Coaches im Nachmittagsbereich, Küche, Transport.
    """

    kuerzel = models.CharField(_("Kürzel"), max_length=12, unique=True)
    name = models.CharField(_("Bezeichnung"), max_length=80)
    name_en = models.CharField(_("Bezeichnung (Englisch)"), max_length=80, blank=True)
    unterrichtet = models.BooleanField(
        _("Unterrichtender Bereich"), default=False,
        help_text=_("Für unterrichtendes Personal sind Kürzel (Stundenplan) und Lehrbefähigungen relevant."),
    )
    reihenfolge = models.PositiveSmallIntegerField(_("Reihenfolge"), default=10)

    class Meta:
        verbose_name = _("Personalbereich")
        verbose_name_plural = _("Personalbereiche")
        ordering = ["reihenfolge", "name"]



class Dienstleister(models.Model):
    """Externe Firma, über die Personal eingesetzt wird (z. B. Sicherheits- oder Reinigungsfirma)."""

    name = models.CharField(_("Firma"), max_length=120, unique=True)
    leistung = models.CharField(_("Leistung"), max_length=120, blank=True, help_text=_("z. B. Sicherheitsdienst, Gebäudereinigung"))
    ansprechperson = models.CharField(_("Ansprechperson"), max_length=120, blank=True)
    telefon = models.CharField(_("Telefon"), max_length=40, blank=True)
    email = models.EmailField(_("E-Mail"), blank=True)
    vertrag_bis = models.DateField(_("Vertrag bis"), null=True, blank=True)
    bemerkungen = models.TextField(_("Bemerkungen"), blank=True)

    class Meta:
        verbose_name = _("Dienstleister (Firma)")
        verbose_name_plural = _("Dienstleister (Firmen)")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Personalprofil(models.Model):
    ANSTELLUNG = [
        ("adlk", _("Auslandsdienstlehrkraft (ADLK)")),
        ("bplk", _("Bundesprogrammlehrkraft (BPLK)")),
        ("lplk", _("Landesprogrammlehrkraft (LPLK)")),
        ("olk", _("Ortslehrkraft (OLK)")),
        ("ortskraft", _("Ortskraft (direkt angestellt)")),
        ("teilzeit", _("Ortskraft in Teilzeit / Aushilfe")),
        ("honorar", _("Honorarkraft / Coach auf Honorarbasis")),
        ("dienstleister", _("Über externen Dienstleister eingesetzt")),
        ("praktikum", _("Praktikum / Referendariat / Freiwilligendienst")),
        ("sonstige", _("Sonstige")),
    ]

    person = models.OneToOneField(Person, on_delete=models.CASCADE, related_name="personal", verbose_name=_("Person"))
    bereich = models.ForeignKey(
        Personalbereich, null=True, blank=True, on_delete=models.PROTECT, related_name="personal", verbose_name=_("Bereich")
    )
    stellenbezeichnung = models.CharField(
        _("Stellenbezeichnung"), max_length=100, blank=True,
        help_text=_("z. B. Reinigungskraft, Head of Security, Fußballcoach, HR-Referentin"),
    )
    kuerzel = models.CharField(
        _("Kürzel"), max_length=8, unique=True, null=True, blank=True,
        help_text=_("wie im Stundenplan, z. B. KRO – Pflicht für unterrichtende Bereiche"),
    )
    aktiv = models.BooleanField(_("Aktiv"), default=True)
    vorgesetzt = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="mitarbeitende", verbose_name=_("Vorgesetzte:r")
    )

    # Dienstverhältnis
    personalnummer = models.CharField(_("Personalnummer"), max_length=20, blank=True)
    anstellungsart = models.CharField(_("Anstellungsart"), max_length=14, choices=ANSTELLUNG, blank=True)
    dienstleister = models.ForeignKey(
        Dienstleister, null=True, blank=True, on_delete=models.PROTECT, related_name="personal",
        verbose_name=_("Dienstleister (Firma)"), help_text=_("nur bei Einsatz über eine externe Firma"),
    )
    dienstbeginn = models.DateField(_("Dienstbeginn an der Schule"), null=True, blank=True)
    vertragsende = models.DateField(_("Vertragsende / Rückkehr"), null=True, blank=True)
    wochenstunden = models.DecimalField(
        _("Deputat / Wochenstunden"), max_digits=4, decimal_places=1, null=True, blank=True,
        help_text=_("bei Lehrkräften Unterrichtsstunden, sonst Arbeitsstunden"),
    )
    ermaessigung = models.DecimalField(_("Ermäßigung / Anrechnung (Std.)"), max_digits=4, decimal_places=1, null=True, blank=True)
    arbeitszeit = models.CharField(_("Arbeitszeit / Schicht"), max_length=120, blank=True, help_text=_("z. B. Mo–Fr 6–14 Uhr, Nachtschicht"))
    arbeitserlaubnis_bis = models.DateField(_("Arbeitserlaubnis gültig bis"), null=True, blank=True)

    # Tätigkeit
    lehrbefaehigungen = models.ManyToManyField("Fach", blank=True, related_name="lehrkraefte", verbose_name=_("Lehrbefähigungen"))
    weitere_funktionen = models.CharField(
        _("Weitere Funktionen"), max_length=200, blank=True, help_text=_("z. B. Mittelstufenkoordination, Fachleitung Chemie, Ersthelfer:in")
    )
    dienst_email = models.EmailField(_("Dienstliche E-Mail"), blank=True)
    raum = models.CharField(_("Büro / Fachraum / Einsatzort"), max_length=60, blank=True)
    ausweisnummer = models.CharField(_("Dienstausweis / Badge-Nr."), max_length=30, blank=True)
    bemerkungen = models.TextField(_("Bemerkungen (Personalverwaltung)"), blank=True)
    zusatzfelder = models.JSONField(_("Zusatzfelder"), default=dict, blank=True, editable=False)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Personal"), m2m_fields=[lehrbefaehigungen])

    class Meta:
        verbose_name = _("Personal")
        verbose_name_plural = _("Personal")
        ordering = ["person__nachname", "person__vorname"]
        permissions = [("view_hr_daten", _("Darf HR-Daten sehen (Dienstverhältnis, Nachweise, Abwesenheiten)"))]

    def __str__(self):
        return f"{self.kuerzel} – {self.person.anzeigename}" if self.kuerzel else self.person.anzeigename

    def clean(self):
        if self.dienstbeginn and self.vertragsende and self.vertragsende < self.dienstbeginn:
            raise ValidationError(_("Das Vertragsende liegt vor dem Dienstbeginn."))
        if self.bereich_id and self.bereich.unterrichtet and not self.kuerzel:
            raise ValidationError({"kuerzel": _("Für unterrichtendes Personal ist ein Kürzel erforderlich (Stundenplan).")})
        if self.anstellungsart == "dienstleister" and not self.dienstleister_id:
            raise ValidationError({"dienstleister": _("Bitte die Firma angeben, über die die Person eingesetzt wird.")})
        if self.vorgesetzt_id and self.vorgesetzt_id == self.pk:
            raise ValidationError({"vorgesetzt": _("Eine Person kann nicht ihre eigene Vorgesetzte sein.")})

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


class Nachweisart(LokalerNameMixin, models.Model):
    """z. B. Führungszeugnis / Certificate of Good Conduct, Erste-Hilfe-Kurs, Kinderschutzschulung."""

    name = models.CharField(_("Bezeichnung"), max_length=120, unique=True)
    name_en = models.CharField(_("Bezeichnung (Englisch)"), max_length=120, blank=True)
    gueltigkeit_monate = models.PositiveSmallIntegerField(
        _("Gültigkeit (Monate)"), null=True, blank=True, help_text=_("leer = unbefristet; dient als Vorschlag für „gültig bis“")
    )
    pflicht_fuer = models.ManyToManyField(
        Personalbereich, blank=True, related_name="pflichtnachweise", verbose_name=_("Pflicht für Bereiche")
    )
    reihenfolge = models.PositiveSmallIntegerField(_("Reihenfolge"), default=10)
    beschreibung = models.CharField(_("Beschreibung"), max_length=200, blank=True)

    class Meta:
        verbose_name = _("Nachweisart")
        verbose_name_plural = _("Nachweisarten")
        ordering = ["reihenfolge", "name"]



class Nachweis(models.Model):
    personal = models.ForeignKey(Personalprofil, on_delete=models.CASCADE, related_name="nachweise", verbose_name=_("Personal"))
    art = models.ForeignKey(Nachweisart, on_delete=models.PROTECT, verbose_name=_("Nachweis"))
    ausgestellt_am = models.DateField(_("Ausgestellt am"), null=True, blank=True)
    gueltig_bis = models.DateField(_("Gültig bis"), null=True, blank=True, help_text=_("leer = wird aus der Nachweisart berechnet bzw. unbefristet"))
    datei = models.FileField(_("Datei"), upload_to="nachweise/%Y/", blank=True)
    bemerkung = models.CharField(_("Bemerkung"), max_length=200, blank=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Nachweis"))

    class Meta:
        verbose_name = _("Nachweis")
        verbose_name_plural = _("Nachweise")
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
            raise ValidationError(_("„Gültig bis“ liegt vor dem Ausstellungsdatum."))


class Personalabwesenheit(models.Model):
    ARTEN = [
        ("urlaub", _("Urlaub")),
        ("krank", _("Krankmeldung")),
        ("fortbildung", _("Fortbildung")),
        ("dienstreise", _("Dienstreise / Klassenfahrt")),
        ("sonderurlaub", _("Sonderurlaub")),
        ("sonstige", _("Sonstiges")),
    ]
    STATUS = [("beantragt", _("beantragt")), ("genehmigt", _("genehmigt")), ("abgelehnt", _("abgelehnt"))]

    personal = models.ForeignKey(Personalprofil, on_delete=models.CASCADE, related_name="abwesenheiten", verbose_name=_("Personal"))
    art = models.CharField(_("Art"), max_length=14, choices=ARTEN)
    von = models.DateField(_("Von"))
    bis = models.DateField(_("Bis"))
    halbtags = models.BooleanField(_("Nur halbtags"), default=False)
    status = models.CharField(_("Status"), max_length=10, choices=STATUS, default="genehmigt")
    bemerkung = models.CharField(
        _("Bemerkung"), max_length=200, blank=True, help_text=_("Keine Diagnosen oder Gesundheitsdaten eintragen.")
    )
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Personalabwesenheit"))

    class Meta:
        verbose_name = _("Personalabwesenheit")
        verbose_name_plural = _("Personalabwesenheiten")
        ordering = ["-von"]

    def __str__(self):
        return f"{self.personal}: {self.get_art_display()} {datum(self.von)}–{datum(self.bis)}"

    def clean(self):
        if self.von and self.bis and self.bis < self.von:
            raise ValidationError(_("„Bis“ darf nicht vor „Von“ liegen."))

    @property
    def arbeitstage(self):
        from datetime import timedelta

        tag, n = self.von, 0
        while tag <= self.bis:
            n += tag.weekday() < 5
            tag += timedelta(days=1)
        return n / 2 if self.halbtags else n


class Fortbildung(models.Model):
    personal = models.ForeignKey(Personalprofil, on_delete=models.CASCADE, related_name="fortbildungen", verbose_name=_("Personal"))
    titel = models.CharField(_("Titel"), max_length=150)
    anbieter = models.CharField(_("Anbieter"), max_length=100, blank=True, help_text=_("z. B. ZfA, Regionale Fortbildung, schulintern"))
    datum = models.DateField(_("Datum"))
    umfang_stunden = models.DecimalField(_("Umfang (Std.)"), max_digits=5, decimal_places=1, null=True, blank=True)
    nachweis_liegt_vor = models.BooleanField(_("Nachweis liegt vor"), default=False)

    class Meta:
        verbose_name = _("Fortbildung")
        verbose_name_plural = _("Fortbildungen")
        ordering = ["-datum"]

    def __str__(self):
        return f"{self.titel} ({datum(self.datum)})"


class Notfallkontakt(models.Model):
    """Notfallkontakte für Personal (bei Schüler:innen über die Beziehungen zu Eltern / Kontaktpersonen)."""

    personal = models.ForeignKey(Personalprofil, on_delete=models.CASCADE, related_name="notfallkontakte", verbose_name=_("Personal"))
    name = models.CharField(_("Name"), max_length=120)
    beziehung = models.CharField(_("Beziehung"), max_length=60, blank=True, help_text=_("z. B. Ehepartner:in"))
    telefon = models.CharField(_("Telefon"), max_length=40)
    reihenfolge = models.PositiveSmallIntegerField(_("Reihenfolge"), default=1)

    class Meta:
        verbose_name = _("Notfallkontakt")
        verbose_name_plural = _("Notfallkontakte")
        ordering = ["personal", "reihenfolge"]

    def __str__(self):
        return f"{self.name} ({self.telefon})"


class Elternprofil(models.Model):
    """Zusatzdaten für Erziehungsberechtigte und Kontaktpersonen."""

    KORRESPONDENZ = [("email", _("E-Mail")), ("app", _("App / Portal")), ("post", _("Post")), ("telefon", _("Telefon"))]

    person = models.OneToOneField(Person, on_delete=models.CASCADE, related_name="elternprofil", verbose_name=_("Person"))
    beruf = models.CharField(_("Beruf"), max_length=100, blank=True)
    arbeitgeber = models.CharField(_("Arbeitgeber / Organisation"), max_length=120, blank=True)
    korrespondenzweg = models.CharField(_("Bevorzugter Kommunikationsweg"), max_length=10, choices=KORRESPONDENZ, default="email")
    schulverein_mitglied = models.BooleanField(_("Mitglied im Schulverein"), default=False)
    mitgliedsnummer = models.CharField(_("Mitgliedsnummer Schulverein"), max_length=30, blank=True)
    elternvertretung = models.CharField(
        _("Funktion in der Elternvertretung"), max_length=100, blank=True, help_text=_("z. B. Klassenelternsprecher:in 9a")
    )
    kontaktdaten_weitergabe = models.BooleanField(
        _("Einverstanden mit Weitergabe der Kontaktdaten an die Klassenelternschaft"), default=False
    )
    zusatzfelder = models.JSONField(_("Zusatzfelder"), default=dict, blank=True, editable=False)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Elternprofil"))

    class Meta:
        verbose_name = _("Elternprofil")
        verbose_name_plural = _("Elternprofile")

    def __str__(self):
        return gettext("Elternprofil %(person)s") % {"person": self.person}


class Beziehung(models.Model):
    """Verbindet eine Schülerin / einen Schüler mit einer erziehungsberechtigten oder Kontaktperson."""

    ARTEN = [
        ("mutter", _("Mutter")),
        ("vater", _("Vater")),
        ("elternteil", _("Elternteil")),
        ("vormund", _("Vormund")),
        ("grosseltern", _("Großelternteil")),
        ("gastfamilie", _("Gastfamilie")),
        ("sonstige", _("Sonstige Kontaktperson")),
    ]

    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="beziehungen", verbose_name=_("Schüler:in"))
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="kinder_beziehungen", verbose_name=_("Kontaktperson"))
    art = models.CharField(_("Art"), max_length=12, choices=ARTEN)
    sorgerecht = models.BooleanField(_("Sorgerecht"), default=True)
    auskunftsrecht = models.BooleanField(_("Auskunftsrecht"), default=True)
    abholberechtigt = models.BooleanField(_("Abholberechtigt"), default=True)
    notfallkontakt = models.BooleanField(_("Notfallkontakt"), default=False)
    rechnungsempfaenger = models.BooleanField(_("Rechnungsempfänger:in"), default=False)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Beziehung"))

    class Meta:
        verbose_name = _("Beziehung")
        verbose_name_plural = _("Beziehungen (Eltern / Kontakte)")
        unique_together = [("schueler", "person")]

    def __str__(self):
        return f"{self.person} ({self.get_art_display()}) → {self.schueler}"

    def clean(self):
        if self.schueler_id and self.person_id and self.schueler.person_id == self.person_id:
            raise ValidationError(_("Eine Person kann nicht ihre eigene Kontaktperson sein."))


class Gruppe(models.Model):
    STAMMKLASSE = "stammklasse"
    LERNGRUPPE = "lerngruppe"
    AG = "ag"
    TYPEN = [(STAMMKLASSE, _("Stammklasse")), (LERNGRUPPE, _("Lerngruppe / Kurs")), (AG, _("AG / Nachmittag"))]

    schuljahr = models.ForeignKey(Schuljahr, on_delete=models.PROTECT, related_name="gruppen", verbose_name=_("Schuljahr"))
    typ = models.CharField(_("Typ"), max_length=12, choices=TYPEN, default=STAMMKLASSE)
    name = models.CharField(_("Bezeichnung"), max_length=60, help_text=_("z. B. 9a, Ethik 9, AG Robotik"))
    kuerzel = models.CharField(_("Kürzel"), max_length=20, blank=True, help_text=_("wie im Stundenplan"))
    jahrgang = models.PositiveSmallIntegerField(_("Jahrgang"), null=True, blank=True)
    leitung = models.ForeignKey(
        Personalprofil, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="geleitete_gruppen", verbose_name=_("Leitung (Klassenleitung / AG-Leitung)"),
    )
    # ab 0.4.16.0: Stellvertretung mit denselben Rechten wie die Klassenleitung, Klassenraum, Höchstzahl
    leitung2 = models.ForeignKey(
        Personalprofil, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="vertretene_gruppen", verbose_name=_("Stellvertretende Leitung"),
        help_text=_("Hat dieselben Rechte wie die Klassenleitung."),
    )
    raum = models.CharField(_("Klassenraum"), max_length=40, blank=True)
    kapazitaet = models.PositiveSmallIntegerField(_("Höchstzahl Schüler:innen"), null=True, blank=True,
                                                  help_text=_("leer = keine Grenze; beim Zuordnen wird gewarnt"))
    gebildet_aus = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="abgeleitete_gruppen",
        limit_choices_to={"typ": STAMMKLASSE}, verbose_name=_("Gebildet aus (Stammklassen)"),
        help_text=_("Nur zur Orientierung und Filterung; gemischte Gruppen bleiben möglich."),
    )
    vorgaenger = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="nachfolger",
        verbose_name=_("Vorgängergruppe (Vorjahr)"),
    )
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Gruppe"), m2m_fields=[gebildet_aus])

    class Meta:
        verbose_name = _("Gruppe / Klasse")
        verbose_name_plural = _("Gruppen / Klassen")
        ordering = ["schuljahr", "typ", "jahrgang", "name"]
        unique_together = [("schuljahr", "name")]

    def __str__(self):
        return f"{self.name} ({self.schuljahr})"

    def aktuelle_mitglieder(self, stichtag=None):
        stichtag = stichtag or self.schuljahr.stichtag()
        return Schuelerprofil.objects.filter(
            mitgliedschaften__in=Mitgliedschaft.objects.aktiv(stichtag).filter(gruppe=self)
        ).select_related("person").distinct()


class MitgliedschaftQuerySet(models.QuerySet):
    def aktiv(self, stichtag=None):
        tag = stichtag or timezone.localdate()
        return self.filter(von__lte=tag).filter(Q(bis__isnull=True) | Q(bis__gte=tag))


class Mitgliedschaft(models.Model):
    gruppe = models.ForeignKey(Gruppe, on_delete=models.CASCADE, related_name="mitgliedschaften", verbose_name=_("Gruppe"))
    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="mitgliedschaften", verbose_name=_("Schüler:in"))
    von = models.DateField(_("Von"))
    bis = models.DateField(_("Bis"), null=True, blank=True, help_text=_("leer = bis auf Weiteres"))
    rolle = models.CharField(_("Rolle"), max_length=40, blank=True, help_text=_("z. B. Klassensprecher:in"))
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Mitgliedschaft"))

    objects = MitgliedschaftQuerySet.as_manager()

    class Meta:
        verbose_name = _("Mitgliedschaft")
        verbose_name_plural = _("Mitgliedschaften")
        ordering = ["gruppe", "schueler__person__nachname"]

    def __str__(self):
        return gettext("%(schueler)s in %(gruppe)s") % {"schueler": self.schueler, "gruppe": self.gruppe.name}

    def clean(self):
        if self.von and self.bis and self.bis < self.von:
            raise ValidationError(_("'Bis' darf nicht vor 'Von' liegen."))
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
                    _("Diese Person ist im gewählten Zeitraum bereits Mitglied einer anderen Stammklasse. "
                    "Bitte die alte Mitgliedschaft zuerst mit einem Enddatum beenden.")
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class Fachbereich(LokalerNameMixin, models.Model):
    """Fachbereich / Fachschaft (ab 0.4.16.0), z. B. Naturwissenschaften, mit bis zu zwei Fachleitungen."""

    name = models.CharField(_("Bezeichnung"), max_length=80, unique=True, help_text=_("z. B. Naturwissenschaften"))
    name_en = models.CharField(_("Bezeichnung (Englisch)"), max_length=80, blank=True)
    leitung = models.ForeignKey(Personalprofil, null=True, blank=True, on_delete=models.SET_NULL, related_name="fachbereiche",
                                verbose_name=_("Fachleitung"))
    leitung2 = models.ForeignKey(Personalprofil, null=True, blank=True, on_delete=models.SET_NULL, related_name="fachbereiche2",
                                 verbose_name=_("Zweite Fachleitung"))
    farbe = models.CharField(_("Farbe"), max_length=7, blank=True, help_text=_("z. B. #2E7D6B; gilt für Fächer ohne eigene Farbe"))
    reihenfolge = models.PositiveSmallIntegerField(_("Reihenfolge"), default=10)

    class Meta:
        verbose_name = _("Fachbereich")
        verbose_name_plural = _("Fachbereiche")
        ordering = ["reihenfolge", "name"]

    def __str__(self):
        return self.lokal_name

    def leitungen(self):
        return [p for p in (self.leitung, self.leitung2) if p is not None]


class Fach(LokalerNameMixin, models.Model):
    kuerzel = models.CharField(_("Kürzel"), max_length=10, unique=True, help_text=_("wie im Stundenplan, z. B. CH"))
    name = models.CharField(_("Bezeichnung"), max_length=60)
    name_en = models.CharField(_("Bezeichnung (Englisch)"), max_length=60, blank=True)
    reihenfolge = models.PositiveSmallIntegerField(_("Reihenfolge auf dem Zeugnis"), default=100)

    # Zeugnis und Versetzung (Richtlinie Sek I an DAS, Ziffer 5.3)
    ZEUGNISROLLEN = [
        ("deutsch", _("Deutsch")),
        ("mathematik", _("Mathematik")),
        ("fremdsprache", _("Fremdsprache / Landessprache")),
        ("musisch", _("Kunst, Musik, Sport (Ausgleich höchstens ein Fach)")),
        ("religion", _("Religion / Ethik / Philosophie")),
        ("sonstiges", _("Weiteres Fach")),
    ]
    zeugnisrolle = models.CharField(
        _("Rolle für Zeugnis und Versetzung"), max_length=14, choices=ZEUGNISROLLEN, default="sonstiges",
        help_text=_("Bestimmt Kernfächer und Ausgleichsregeln. Welche Fremdsprache die erste ist, steht in der Sprachenfolge."),
    )
    zeugnisspalte = models.PositiveSmallIntegerField(
        _("Spalte auf dem Zeugnis"), choices=[(1, _("links")), (2, _("rechts"))], default=1,
        help_text=_("Muster: links Sprachen, Gesellschaftswissenschaften, Religion; rechts Mathematik, Naturwissenschaften, Kunst, Musik, Sport."),
    )
    auf_zeugnis = models.BooleanField(_("Auf dem Zeugnis ausweisen"), default=True)
    fachbereich = models.ForeignKey(Fachbereich, null=True, blank=True, on_delete=models.SET_NULL, related_name="faecher",
                                    verbose_name=_("Fachbereich"))
    farbe = models.CharField(_("Farbe"), max_length=7, blank=True, help_text=_("z. B. #4A90D9; für Übersichten und den Stundenplan"))

    class Meta:
        verbose_name = _("Fach")
        verbose_name_plural = _("Fächer")
        ordering = ["reihenfolge", "name"]

    def __str__(self):
        return f"{self.lokal_name} ({self.kuerzel})"

    @property
    def anzeigefarbe(self):
        return self.farbe or (self.fachbereich.farbe if self.fachbereich_id else "")


class Stundentafel(models.Model):
    """Wochenstunden je Fach und Jahrgang (ab 0.4.16.0) – Vorgabe für neuen Unterricht und die Übersicht der Deputate."""

    fach = models.ForeignKey(Fach, on_delete=models.CASCADE, related_name="stundentafel", verbose_name=_("Fach"))
    jahrgang = models.PositiveSmallIntegerField(_("Jahrgang"))
    wochenstunden = models.DecimalField(_("Wochenstunden"), max_digits=4, decimal_places=1)

    class Meta:
        verbose_name = _("Stundentafel")
        verbose_name_plural = _("Stundentafel")
        unique_together = [("fach", "jahrgang")]
        ordering = ["jahrgang", "fach__reihenfolge"]

    def __str__(self):
        return f"{self.fach.kuerzel} Jg. {self.jahrgang}: {self.wochenstunden}"

    @classmethod
    def stunden(cls, fach_id, jahrgang):
        if not jahrgang:
            return None
        return cls.objects.filter(fach_id=fach_id, jahrgang=jahrgang).values_list("wochenstunden", flat=True).first()


class Einwilligung(models.Model):
    ZWECKE = [
        ("foto_intern", _("Fotos für schulinterne Zwecke")),
        ("foto_web", _("Fotos auf Website / Social Media")),
        ("kontaktliste", _("Weitergabe in Klassenkontaktliste")),
        ("ausfluege", _("Teilnahme an Ausflügen")),
        ("sonstige", _("Sonstiges")),
    ]

    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="einwilligungen", verbose_name=_("Schüler:in"))
    zweck = models.CharField(_("Zweck"), max_length=20, choices=ZWECKE)
    beschreibung = models.CharField(_("Beschreibung"), max_length=200, blank=True)
    erteilt_durch = models.ForeignKey(Person, on_delete=models.PROTECT, verbose_name=_("Erteilt durch"))
    erteilt_am = models.DateField(_("Erteilt am"))
    widerrufen_am = models.DateField(_("Widerrufen am"), null=True, blank=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Einwilligung"))

    class Meta:
        verbose_name = _("Einwilligung")
        verbose_name_plural = _("Einwilligungen")
        ordering = ["schueler", "zweck"]

    def __str__(self):
        return f"{self.get_zweck_display()} – {self.schueler}"

    @property
    def gueltig(self):
        return self.widerrufen_am is None or self.widerrufen_am > timezone.localdate()


class Dokument(models.Model):
    """Anhang zu einer Person – beliebige Dateien (oder reine Notizen), sortiert nach Upload-Datum."""

    KATEGORIEN = [
        ("attest", _("Attest / Entschuldigung")),
        ("zeugnis", _("Zeugnis")),
        ("diagnostik", _("Gutachten / Diagnostik")),
        ("foerderung", _("Förderplan / Nachteilsausgleich")),
        ("korrespondenz", _("Elternkorrespondenz")),
        ("einwilligung", _("Einverständniserklärung")),
        ("vertrag", _("Vertrag / Anmeldung")),
        ("ausweis", _("Ausweis / Pass / Visum")),
        ("sonstiges", _("Sonstiges")),
    ]
    STUFEN = [
        ("akte", _("Alle mit Aktenzugriff (inkl. Klassenleitung)")),
        ("verwaltung", _("Verwaltung und Schulleitung")),
        ("foerderung", _("Förderteam (Förderkoordination, Klassenleitung, Leitung)")),
        ("leitung", _("Nur Schulleitung")),
    ]

    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="dokumente", verbose_name=_("Person"))
    kategorie = models.CharField(_("Kategorie"), max_length=15, choices=KATEGORIEN, default="sonstiges")
    titel = models.CharField(_("Titel"), max_length=120)
    notiz = models.TextField(_("Notiz"), blank=True, help_text=_("Beschreibung oder Inhalt, falls keine Datei angehängt wird"))
    datei = models.FileField(
        _("Datei"), upload_to=ablagepfad, storage=geschuetzter_speicher, blank=True, max_length=200,
        validators=[groesse_pruefen],
    )
    originalname = models.CharField(_("Dateiname"), max_length=200, blank=True, editable=False)
    groesse = models.PositiveBigIntegerField(_("Größe (Byte)"), default=0, editable=False)
    inhaltstyp = models.CharField(_("Dateityp"), max_length=100, blank=True, editable=False)
    zugriffsstufe = models.CharField(
        _("Sichtbar für"), max_length=12, choices=STUFEN, default="akte",
        help_text=_("Bei Personalunterlagen gilt immer: nur Personalverwaltung und Leitung."),
    )
    aufbewahren_bis = models.DateField(_("Aufbewahren bis"), null=True, blank=True)
    hochgeladen_am = models.DateTimeField(_("Hochgeladen am"), auto_now_add=True)
    hochgeladen_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, verbose_name=_("Hochgeladen von")
    )
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Dokument"))

    class Meta:
        verbose_name = _("Anhang / Dokument")
        verbose_name_plural = _("Anhänge / Dokumente")
        ordering = ["-hochgeladen_am", "-pk"]

    def __str__(self):
        return f"{self.titel} ({self.person})"

    def clean(self):
        if not self.datei and not self.notiz.strip():
            raise ValidationError(_("Bitte eine Datei anhängen oder eine Notiz eingeben."))

    def save(self, *args, **kwargs):
        datei = self.datei
        if datei and not getattr(datei, "_committed", True):
            # Neue Datei: Originalname, Größe und Typ festhalten.
            import mimetypes
            import os

            self.originalname = os.path.basename(datei.name)[:200]
            self.groesse = datei.size or 0
            self.inhaltstyp = (getattr(datei.file, "content_type", None)
                               or mimetypes.guess_type(datei.name)[0] or "application/octet-stream")[:100]
        super().save(*args, **kwargs)

    @property
    def groesse_lesbar(self):
        return groesse_lesbar(self.groesse)

    @property
    def dateiendung(self):
        import os

        return os.path.splitext(self.originalname or self.datei.name or "")[1].lstrip(".").upper()


class Bildungsgang(LokalerNameMixin, models.Model):
    """Konfigurierbar, z. B. Grundschule, Hauptschul-, Realschul-, Gymnasialer Bildungsgang, Oberstufe."""

    kuerzel = models.CharField(_("Kürzel"), max_length=10, unique=True)
    name = models.CharField(_("Bezeichnung"), max_length=80)
    name_en = models.CharField(_("Bezeichnung (Englisch)"), max_length=80, blank=True)
    angestrebter_abschluss = models.CharField(_("Angestrebter Abschluss"), max_length=120, blank=True)
    angestrebter_abschluss_en = models.CharField(_("Angestrebter Abschluss (Englisch)"), max_length=120, blank=True)
    jahrgang_von = models.PositiveSmallIntegerField(_("ab Jahrgang"), null=True, blank=True)
    jahrgang_bis = models.PositiveSmallIntegerField(_("bis Jahrgang"), null=True, blank=True)
    reihenfolge = models.PositiveSmallIntegerField(_("Reihenfolge"), default=10)

    class Meta:
        verbose_name = _("Bildungsgang")
        verbose_name_plural = _("Bildungsgänge")
        ordering = ["reihenfolge", "name"]



class Laufbahnabschnitt(models.Model):
    """
    Ein Abschnitt der Schullaufbahn, in der Regel ein Schuljahr.
    Wechselt jemand im laufenden Schuljahr den Bildungsgang, entstehen zwei Abschnitte mit Von-/Bis-Datum.
    """

    ERGEBNISSE = [
        ("laufend", _("laufend")),
        ("versetzt", _("versetzt")),
        ("versetzt_auflage", _("versetzt mit Auflage / auf Probe")),
        ("uebersprungen", _("Jahrgangsstufe übersprungen")),
        ("zurueckgestuft", _("zurückgestuft")),
        ("nicht_versetzt", _("nicht versetzt (Wiederholung)")),
        ("freiwillig_wiederholt", _("freiwillige Wiederholung")),
        ("wechsel", _("Wechsel des Bildungsgangs")),
        ("abschluss", _("Abschluss erreicht")),
        ("abgang", _("Abgang ohne Abschluss / Schulwechsel")),
    ]

    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="laufbahn", verbose_name=_("Schüler:in"))
    schuljahr = models.ForeignKey(Schuljahr, on_delete=models.PROTECT, related_name="laufbahnabschnitte", verbose_name=_("Schuljahr"))
    jahrgang = models.PositiveSmallIntegerField(_("Jahrgang"))
    bildungsgang = models.ForeignKey(Bildungsgang, on_delete=models.PROTECT, verbose_name=_("Bildungsgang"))
    stammklasse = models.ForeignKey(
        Gruppe, null=True, blank=True, on_delete=models.SET_NULL, limit_choices_to={"typ": "stammklasse"},
        verbose_name=_("Stammklasse"),
    )
    von = models.DateField(_("Von"), null=True, blank=True, help_text=_("leer = Beginn des Schuljahres"))
    bis = models.DateField(_("Bis"), null=True, blank=True, help_text=_("leer = Ende des Schuljahres"))
    ergebnis = models.CharField(_("Ergebnis"), max_length=24, choices=ERGEBNISSE, default="laufend")
    bemerkung = models.CharField(_("Bemerkung"), max_length=200, blank=True, help_text=_("z. B. Konferenzbeschluss vom ..."))
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Schullaufbahn"))

    class Meta:
        verbose_name = _("Laufbahnabschnitt")
        verbose_name_plural = _("Schullaufbahn")
        ordering = ["schueler", "schuljahr__beginn", "von"]

    def __str__(self):
        return gettext("%(schuljahr)s · Jg. %(jahrgang)s · %(bildungsgang)s") % {
            "schuljahr": self.schuljahr, "jahrgang": self.jahrgang, "bildungsgang": self.bildungsgang}

    def clean(self):
        if self.von and self.bis and self.bis < self.von:
            raise ValidationError(_("'Bis' darf nicht vor 'Von' liegen."))
        if self.stammklasse_id and self.schuljahr_id and self.stammklasse.schuljahr_id != self.schuljahr_id:
            raise ValidationError({"stammklasse": _("Die Stammklasse gehört zu einem anderen Schuljahr.")})
        bg = self.bildungsgang if self.bildungsgang_id else None
        if bg and self.jahrgang and ((bg.jahrgang_von and self.jahrgang < bg.jahrgang_von) or (bg.jahrgang_bis and self.jahrgang > bg.jahrgang_bis)):
            raise ValidationError({"jahrgang": gettext("Jahrgang %(jahrgang)s liegt außerhalb des Bildungsgangs %(bildungsgang)s.")
                                   % {"jahrgang": self.jahrgang, "bildungsgang": bg}})


class Abschlussart(LokalerNameMixin, models.Model):
    kuerzel = models.CharField(_("Kürzel"), max_length=12, unique=True)
    name = models.CharField(_("Bezeichnung"), max_length=120)
    name_en = models.CharField(_("Bezeichnung (Englisch)"), max_length=120, blank=True)
    reihenfolge = models.PositiveSmallIntegerField(_("Reihenfolge"), default=10)

    class Meta:
        verbose_name = _("Abschlussart")
        verbose_name_plural = _("Abschlussarten")
        ordering = ["reihenfolge", "name"]



class Abschluss(models.Model):
    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="abschluesse", verbose_name=_("Schüler:in"))
    art = models.ForeignKey(Abschlussart, on_delete=models.PROTECT, verbose_name=_("Abschluss / Zertifikat"))
    datum = models.DateField(_("Datum"))
    durchschnitt = models.DecimalField(_("Durchschnitt / Gesamtnote"), max_digits=4, decimal_places=2, null=True, blank=True)
    niveau = models.CharField(_("Niveau / Stufe"), max_length=30, blank=True, help_text=_("z. B. B1 / C1 beim DSD"))
    an_dieser_schule = models.BooleanField(_("An dieser Schule erworben"), default=True)
    bemerkung = models.CharField(_("Bemerkung"), max_length=200, blank=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Abschluss"))

    class Meta:
        verbose_name = _("Abschluss / Zertifikat")
        verbose_name_plural = _("Abschlüsse / Zertifikate")
        ordering = ["schueler", "datum"]

    def __str__(self):
        return f"{self.art} ({self.datum:%m/%Y})"


class VorherigeSchule(models.Model):
    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="vorherige_schulen", verbose_name=_("Schüler:in"))
    name = models.CharField(_("Schule"), max_length=150)
    ort = models.CharField(_("Ort"), max_length=80, blank=True)
    land = models.CharField(_("Land"), max_length=60, blank=True)
    schulform = models.CharField(_("Schulform / System"), max_length=80, blank=True, help_text=_("z. B. Gymnasium (DE), CBC (KE), IGCSE"))
    von = models.DateField(_("Von"), null=True, blank=True)
    bis = models.DateField(_("Bis"), null=True, blank=True)
    letzter_jahrgang = models.CharField(_("Zuletzt besuchte Klasse"), max_length=20, blank=True)

    class Meta:
        verbose_name = _("Vorherige Schule")
        verbose_name_plural = _("Vorherige Schulen")
        ordering = ["schueler", "von"]

    def __str__(self):
        return self.name


class Sprachenfolge(models.Model):
    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="sprachenfolge", verbose_name=_("Schüler:in"))
    position = models.PositiveSmallIntegerField(_("Fremdsprache Nr."), help_text=_("1 = erste Fremdsprache usw."))
    fach = models.ForeignKey(Fach, on_delete=models.PROTECT, verbose_name=_("Sprache"))
    ab_jahrgang = models.PositiveSmallIntegerField(_("ab Jahrgang"))
    bis_jahrgang = models.PositiveSmallIntegerField(_("bis Jahrgang"), null=True, blank=True)

    class Meta:
        verbose_name = _("Sprachenfolge")
        verbose_name_plural = _("Sprachenfolge")
        ordering = ["schueler", "position"]
        unique_together = [("schueler", "position")]

    def __str__(self):
        return gettext("%(nr)s. Fremdsprache: %(fach)s ab Jg. %(jg)s") % {
            "nr": self.position, "fach": self.fach.lokal_name, "jg": self.ab_jahrgang}


class Gesundheitsangaben(models.Model):
    """
    Besonders schützenswerte Daten. Eigene Tabelle mit eigenem Zugriffsrecht:
    Lehrkräfte sehen sie standardmäßig NICHT, nur Verwaltung und Schulleitung.
    """

    schueler = models.OneToOneField(Schuelerprofil, on_delete=models.CASCADE, related_name="gesundheit", verbose_name=_("Schüler:in"))
    allergien = models.CharField(_("Allergien / Unverträglichkeiten"), max_length=200, blank=True)
    erkrankungen = models.CharField(_("Chronische Erkrankungen"), max_length=200, blank=True)
    medikamente = models.CharField(_("Medikamente in der Schule"), max_length=200, blank=True)
    notfallhinweise = models.TextField(_("Hinweise für Notfälle"), blank=True)
    arzt = models.CharField(_("Ärztin / Arzt (Name, Telefon)"), max_length=150, blank=True)
    krankenversicherung = models.CharField(_("Krankenversicherung"), max_length=120, blank=True)
    schwimmen_erlaubt = models.BooleanField(_("Teilnahme am Schwimmunterricht"), default=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Gesundheitsangaben"))

    class Meta:
        verbose_name = _("Gesundheitsangaben")
        verbose_name_plural = _("Gesundheitsangaben")
        permissions = [("view_gesundheit_klasse", _("Darf Gesundheitsangaben der eigenen Klasse sehen"))]

    def __str__(self):
        return gettext("Gesundheitsangaben %(schueler)s") % {"schueler": self.schueler}

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

    ZIELGRUPPEN = [("schueler", _("Schüler:innen")), ("personal", _("Personal")), ("eltern", _("Eltern / Kontaktpersonen"))]
    TYPEN = [
        ("text", _("Text (einzeilig)")),
        ("langtext", _("Text (mehrzeilig)")),
        ("zahl", _("Zahl")),
        ("datum", _("Datum")),
        ("janein", _("Ja / Nein")),
        ("auswahl", _("Auswahl (eine Option)")),
        ("mehrfach", _("Mehrfachauswahl")),
    ]
    SICHTBARKEIT = [
        ("alle", _("Alle mit Aktenzugriff")),
        ("verwaltung", _("Verwaltung, Leitung, HR, Finanzen")),
        ("hr", _("Nur HR und Leitung")),
    ]

    zielgruppe = models.CharField(_("Für"), max_length=10, choices=ZIELGRUPPEN)
    name = models.CharField(_("Bezeichnung"), max_length=80)
    name_en = models.CharField(_("Bezeichnung (Englisch)"), max_length=80, blank=True)
    schluessel = models.SlugField(
        _("Technischer Schlüssel"), max_length=50, blank=True,
        help_text=_("wird automatisch aus der Bezeichnung erzeugt und ist danach fest"),
    )
    typ = models.CharField(_("Feldtyp"), max_length=10, choices=TYPEN, default="text")
    optionen = models.TextField(_("Optionen"), blank=True, help_text=_("nur bei Auswahl / Mehrfachauswahl: eine Option pro Zeile"))
    optionen_en = models.TextField(
        _("Optionen (Englisch)"), blank=True,
        help_text=_("optional: englische Bezeichnungen in derselben Reihenfolge; gespeichert wird immer die deutsche Option"),
    )
    abschnitt = models.CharField(_("Abschnitt"), max_length=60, blank=True, help_text=_("Überschrift zur Gruppierung, z. B. Sport, Logistik"))
    abschnitt_en = models.CharField(_("Abschnitt (Englisch)"), max_length=60, blank=True)
    hilfetext = models.CharField(_("Hilfetext"), max_length=200, blank=True)
    hilfetext_en = models.CharField(_("Hilfetext (Englisch)"), max_length=200, blank=True)
    pflicht = models.BooleanField(_("Pflichtfeld"), default=False)
    sichtbarkeit = models.CharField(
        _("Sichtbar für"), max_length=10, choices=SICHTBARKEIT, default="verwaltung",
        help_text=_("„Alle mit Aktenzugriff“ schließt bei Schüler:innen die Klassenleitung ein; "
                  "„Nur HR und Leitung“ eignet sich für vertrauliche Personaldaten."),
    )
    in_liste = models.BooleanField(_("In Liste"), default=False, help_text=_("als Spalte in der Übersichtsliste zeigen"))
    reihenfolge = models.PositiveSmallIntegerField(_("Reihenfolge"), default=10)
    aktiv = models.BooleanField(_("Aktiv"), default=True, help_text=_("Deaktivieren statt löschen – gespeicherte Werte bleiben erhalten."))

    class Meta:
        verbose_name = _("Zusatzfeld")
        verbose_name_plural = _("Zusatzfelder (eigene Datenfelder)")
        ordering = ["zielgruppe", "abschnitt", "reihenfolge", "name"]
        constraints = [models.UniqueConstraint(fields=["zielgruppe", "schluessel"], name="zusatzfeld_schluessel_eindeutig")]

    def __str__(self):
        return f"{self.lokal_name} ({self.get_zielgruppe_display()})"

    @property
    def optionsliste(self):
        return [o.strip() for o in self.optionen.splitlines() if o.strip()]

    @property
    def optionen_anzeige(self):
        """[(gespeicherter Wert, Anzeige in der aktiven Sprache), ...]"""
        werte = self.optionsliste
        en = [o.strip() for o in self.optionen_en.splitlines() if o.strip()] if englisch_aktiv() else []
        return [(w, en[i] if i < len(en) else w) for i, w in enumerate(werte)]

    @property
    def lokal_name(self):
        return lokal(self, "name")

    @property
    def lokal_abschnitt(self):
        return lokal(self, "abschnitt")

    @property
    def lokal_hilfetext(self):
        return lokal(self, "hilfetext")

    @property
    def formularname(self):
        return f"zusatz__{self.schluessel}"

    def clean(self):
        if self.typ in {"auswahl", "mehrfach"} and not self.optionsliste:
            raise ValidationError({"optionen": _("Bitte mindestens eine Option angeben (eine pro Zeile).")})
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
            return datum(wert)
        if self.typ == "janein":
            return gettext("ja") if wert else gettext("nein")
        if self.typ in {"auswahl", "mehrfach"}:
            beschriftung = dict(self.optionen_anzeige)
            werte = wert if isinstance(wert, list) else [wert]
            return ", ".join(beschriftung.get(w, w) for w in werte)
        if self.typ == "zahl":
            from django.utils import formats

            return formats.number_format(wert.normalize())
        return str(wert)
