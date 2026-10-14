"""
Neuanmeldungen: Bewerbungsakte bis zur Aufnahme.

Eine Anmeldung sammelt die Angaben zum Kind, die Erziehungsberechtigten, hochgeladene Unterlagen
(Zeugnisse, Pass, Impfnachweis …), eine vorläufige Klasse und eine individuell zusammengestellte
Checkliste. Erst mit der Übernahme entstehen daraus reguläre Schüler- und Elterndaten (siehe uebernahme.py).
So bleiben Bewerbungen, die nicht zustande kommen, von den Stammdaten getrennt und können nach
Ablauf der Aufbewahrungsfrist vollständig gelöscht werden.
"""
import os
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from portal.krypto import VerschluesselterSpeicher
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from stammdaten.dokumente import groesse_lesbar, groesse_pruefen
from stammdaten.models import Beziehung, Bildungsgang, Dokument, Elternprofil, Gruppe, Person, Schuelerprofil, Schuljahr
from stammdaten.sprache import LokalerNameMixin, lokal

# Wer für einen Checklistenpunkt zuständig ist (nur zur Orientierung; abhaken darf jede berechtigte Rolle).
ZUSTAENDIG = [
    ("", "—"),
    ("sekretariat", _("Sekretariat")),
    ("finanzen", _("Finanzen")),
    ("koordination", _("Stufenkoordination")),
    ("schulleitung", _("Schulleitung")),
]


# ---------------------------------------------------------------- Ablage der Dateien

class AufnahmeSpeicher(VerschluesselterSpeicher):
    """Wie bei den Anhängen: außerhalb des Webpfads, Links nur über die rechtegeprüfte Download-Ansicht."""

    def url(self, name):
        return reverse("aufnahme_datei_pfad", args=[name])


def aufnahme_speicher():
    return AufnahmeSpeicher()


def aufnahme_pfad(instance, dateiname):
    endung = os.path.splitext(dateiname)[1].lower()[:10]
    return f"aufnahme/{timezone.now():%Y}/{uuid.uuid4().hex}{endung}"


def dateimetadaten(obj, datei):
    """Originalname, Größe und Typ einer frisch hochgeladenen Datei festhalten."""
    import mimetypes

    obj.originalname = os.path.basename(datei.name)[:200]
    obj.groesse = datei.size or 0
    obj.inhaltstyp = (getattr(getattr(datei, "file", None), "content_type", None)
                      or mimetypes.guess_type(datei.name)[0] or "application/octet-stream")[:100]


# ---------------------------------------------------------------- Checklisten-Vorlagen

class ChecklistenVorlage(LokalerNameMixin, models.Model):
    """Wiederverwendbare Zusammenstellung von Checklistenpunkten, z. B. „Standard“, „Oberstufe“, „Quereinstieg“."""

    name = models.CharField(_("Bezeichnung"), max_length=80, unique=True)
    name_en = models.CharField(_("Bezeichnung (Englisch)"), max_length=80, blank=True)
    beschreibung = models.CharField(_("Beschreibung"), max_length=200, blank=True)
    jahrgang_von = models.PositiveSmallIntegerField(_("ab Jahrgang"), null=True, blank=True,
                                                    help_text=_("Wird bei passendem Jahrgang vorgeschlagen."))
    jahrgang_bis = models.PositiveSmallIntegerField(_("bis Jahrgang"), null=True, blank=True)
    standard = models.BooleanField(_("Immer vorschlagen"), default=False,
                                   help_text=_("Wird bei jeder neuen Anmeldung vorausgewählt."))
    aktiv = models.BooleanField(_("Aktiv"), default=True)
    reihenfolge = models.PositiveSmallIntegerField(_("Reihenfolge"), default=10)

    class Meta:
        verbose_name = _("Checklisten-Vorlage")
        verbose_name_plural = _("Checklisten-Vorlagen")
        ordering = ["reihenfolge", "name"]

    def passt_zu(self, jahrgang):
        if self.standard:
            return True
        if jahrgang is None or (self.jahrgang_von is None and self.jahrgang_bis is None):
            return False
        return (self.jahrgang_von or 0) <= jahrgang <= (self.jahrgang_bis or 99)


class VorlagenPunkt(models.Model):
    vorlage = models.ForeignKey(ChecklistenVorlage, on_delete=models.CASCADE, related_name="punkte", verbose_name=_("Vorlage"))
    text = models.CharField(_("Punkt"), max_length=160)
    text_en = models.CharField(_("Punkt (Englisch)"), max_length=160, blank=True)
    zustaendig = models.CharField(_("Zuständig"), max_length=14, choices=ZUSTAENDIG, blank=True)
    pflicht = models.BooleanField(_("Pflicht vor Übernahme"), default=True)
    reihenfolge = models.PositiveSmallIntegerField(_("Reihenfolge"), default=10)

    class Meta:
        verbose_name = _("Checklistenpunkt (Vorlage)")
        verbose_name_plural = _("Checklistenpunkte (Vorlage)")
        ordering = ["vorlage", "reihenfolge", "pk"]

    def __str__(self):
        return lokal(self, "text")


# ---------------------------------------------------------------- Anmeldung

class Anmeldung(models.Model):
    EINGEGANGEN, PRUEFUNG, WARTELISTE, ZUGESAGT = "eingegangen", "pruefung", "warteliste", "zugesagt"
    ABGELEHNT, ZURUECKGEZOGEN, UEBERNOMMEN = "abgelehnt", "zurueckgezogen", "uebernommen"
    STATUS = [
        (EINGEGANGEN, _("Eingegangen")),
        (PRUEFUNG, _("In Prüfung")),
        (WARTELISTE, _("Warteliste")),
        (ZUGESAGT, _("Zugesagt")),
        (ABGELEHNT, _("Abgelehnt")),
        (ZURUECKGEZOGEN, _("Zurückgezogen")),
        (UEBERNOMMEN, _("Übernommen")),
    ]
    OFFEN = (EINGEGANGEN, PRUEFUNG, WARTELISTE, ZUGESAGT)
    BEENDET = (ABGELEHNT, ZURUECKGEZOGEN, UEBERNOMMEN)

    nummer = models.CharField(_("Anmeldenummer"), max_length=20, unique=True, editable=False)
    status = models.CharField(_("Status"), max_length=14, choices=STATUS, default=EINGEGANGEN)
    eingang = models.DateField(_("Eingang"), default=timezone.localdate)

    # Gewünschte Aufnahme
    schuljahr = models.ForeignKey(Schuljahr, on_delete=models.PROTECT, related_name="anmeldungen", verbose_name=_("Aufnahme zum Schuljahr"))
    jahrgang = models.PositiveSmallIntegerField(_("Jahrgang"), null=True, blank=True)
    bildungsgang = models.ForeignKey(Bildungsgang, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Bildungsgang"))
    eintrittsdatum = models.DateField(_("Gewünschter Eintritt"), null=True, blank=True,
                                      help_text=_("leer = Beginn des Schuljahres"))
    vorlaeufige_klasse = models.ForeignKey(
        Gruppe, on_delete=models.SET_NULL, null=True, blank=True, related_name="vorlaeufige_anmeldungen",
        limit_choices_to={"typ": Gruppe.STAMMKLASSE}, verbose_name=_("Vorläufige Klasse"),
    )

    # Kind
    vorname = models.CharField(_("Vorname(n)"), max_length=80)
    nachname = models.CharField(_("Nachname"), max_length=80)
    rufname = models.CharField(_("Rufname"), max_length=80, blank=True)
    geschlecht = models.CharField(_("Geschlecht"), max_length=1, choices=Person.GESCHLECHT, blank=True)
    geburtsdatum = models.DateField(_("Geburtsdatum"), null=True, blank=True)
    geburtsort = models.CharField(_("Geburtsort"), max_length=80, blank=True)
    geburtsland = models.CharField(_("Geburtsland"), max_length=60, blank=True)
    staatsangehoerigkeiten = models.CharField(_("Staatsangehörigkeit(en)"), max_length=120, blank=True)
    muttersprache = models.CharField(_("Erstsprache(n)"), max_length=80, blank=True)
    familiensprache = models.CharField(_("Familiensprache(n)"), max_length=80, blank=True)
    deutschkenntnisse = models.CharField(_("Deutschkenntnisse"), max_length=80, blank=True,
                                         help_text=_("z. B. keine, A2, B1, muttersprachlich"))
    daz = models.BooleanField(_("DaZ-/DaF-Förderung voraussichtlich nötig"), default=False)
    religionsunterricht = models.CharField(_("Religion / Ethik"), max_length=10, choices=Schuelerprofil.RELIGIONSUNTERRICHT, blank=True)
    strasse = models.CharField(_("Straße / Hausnummer / Estate"), max_length=120, blank=True)
    postfach = models.CharField(_("Postfach (P.O. Box)"), max_length=40, blank=True)
    plz = models.CharField(_("PLZ / Postal Code"), max_length=12, blank=True)
    ort = models.CharField(_("Ort"), max_length=80, blank=True)
    land = models.CharField(_("Land"), max_length=60, blank=True, default="Kenia")

    # Bisherige Schule
    vorherige_schule = models.CharField(_("Bisherige Schule"), max_length=150, blank=True)
    vorherige_schule_ort = models.CharField(_("Ort der bisherigen Schule"), max_length=80, blank=True)
    vorherige_schule_land = models.CharField(_("Land der bisherigen Schule"), max_length=60, blank=True)
    vorherige_schulform = models.CharField(_("Schulform / System"), max_length=80, blank=True,
                                           help_text=_("z. B. Gymnasium (DE), CBC (KE), IGCSE"))
    letzter_jahrgang = models.CharField(_("Zuletzt besuchte Klasse"), max_length=20, blank=True)

    geschwister = models.CharField(_("Geschwister an der Schule"), max_length=200, blank=True)
    bemerkungen = models.TextField(_("Bemerkungen"), blank=True)

    # Übernahme
    schueler = models.OneToOneField(Schuelerprofil, on_delete=models.SET_NULL, null=True, blank=True, editable=False,
                                    related_name="anmeldung", verbose_name=_("Übernommen als"))
    uebernommen_am = models.DateTimeField(_("Übernommen am"), null=True, blank=True, editable=False)
    uebernommen_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                        editable=False, related_name="+", verbose_name=_("Übernommen von"))

    status_seit = models.DateField(_("Status seit"), default=timezone.localdate, editable=False)
    erstellt = models.DateTimeField(auto_now_add=True)
    erstellt_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     editable=False, related_name="+", verbose_name=_("Erfasst von"))
    geaendert = models.DateTimeField(auto_now=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Anmeldung"))

    class Meta:
        verbose_name = _("Anmeldung")
        verbose_name_plural = _("Anmeldungen")
        ordering = ["-eingang", "-pk"]
        permissions = [("uebernehmen_anmeldung", _("Kann Anmeldungen in die Schülerdaten übernehmen"))]

    def __str__(self):
        return f"{self.nummer} · {self.nachname}, {self.rufname or self.vorname}"

    @property
    def anzeigename(self):
        return f"{self.rufname or self.vorname} {self.nachname}"

    @property
    def offen(self):
        return self.status in self.OFFEN

    @property
    def abgeschlossen(self):
        return self.status == self.UEBERNOMMEN

    @property
    def eintritt(self):
        """Tatsächlicher Eintrittstag (leer = Schuljahresbeginn)."""
        return self.eintrittsdatum or self.schuljahr.beginn

    def clean(self):
        if self.vorlaeufige_klasse_id and self.schuljahr_id and self.vorlaeufige_klasse.schuljahr_id != self.schuljahr_id:
            raise ValidationError({"vorlaeufige_klasse": _("Die Klasse gehört zu einem anderen Schuljahr.")})
        if self.eintrittsdatum and self.schuljahr_id and not (self.schuljahr.beginn <= self.eintrittsdatum <= self.schuljahr.ende):
            raise ValidationError({"eintrittsdatum": _("Der Eintritt muss im gewählten Schuljahr liegen.")})

    def save(self, *args, **kwargs):
        if not self.nummer:
            jahr = (self.eingang or timezone.localdate()).year
            praefix = f"A{jahr}-"
            vorhandene = Anmeldung.objects.filter(nummer__startswith=praefix).values_list("nummer", flat=True)
            n = max([int(x[len(praefix):]) for x in vorhandene if x[len(praefix):].isdigit()] or [0]) + 1
            self.nummer = f"{praefix}{n:03d}"
        super().save(*args, **kwargs)

    # Checkliste
    def fortschritt(self):
        punkte = list(self.punkte.all())
        erledigt = sum(1 for p in punkte if p.erledigt)
        offen_pflicht = [p for p in punkte if p.pflicht and not p.erledigt]
        return {"gesamt": len(punkte), "erledigt": erledigt, "offen_pflicht": offen_pflicht,
                "prozent": round(100 * erledigt / len(punkte)) if punkte else 0}

    def punkte_aus_vorlage(self, vorlage):
        """Fügt die Punkte einer Vorlage hinzu; bereits vorhandene (gleicher Text) werden übersprungen."""
        vorhanden = {p.text.strip().lower() for p in self.punkte.all()}
        start = (self.punkte.aggregate(m=models.Max("reihenfolge"))["m"] or 0)
        neu = []
        for vp in vorlage.punkte.all():
            if vp.text.strip().lower() in vorhanden:
                continue
            start += 10
            neu.append(AnmeldePunkt(anmeldung=self, text=vp.text, text_en=vp.text_en, zustaendig=vp.zustaendig,
                                    pflicht=vp.pflicht, reihenfolge=start))
            vorhanden.add(vp.text.strip().lower())
        AnmeldePunkt.objects.bulk_create(neu)
        return len(neu)


class AnmeldeKontakt(models.Model):
    """Erziehungsberechtigte bzw. Kontaktperson – wird bei der Übernahme zu Person + Elternprofil + Beziehung."""

    anmeldung = models.ForeignKey(Anmeldung, on_delete=models.CASCADE, related_name="kontakte", verbose_name=_("Anmeldung"))
    art = models.CharField(_("Beziehung zum Kind"), max_length=12, choices=Beziehung.ARTEN, default="mutter")
    anrede = models.CharField(_("Anrede"), max_length=20, blank=True)
    titel = models.CharField(_("Titel"), max_length=30, blank=True)
    vorname = models.CharField(_("Vorname"), max_length=80)
    nachname = models.CharField(_("Nachname"), max_length=80)
    email = models.EmailField(_("E-Mail"), blank=True)
    telefon = models.CharField(_("Telefon (privat)"), max_length=40, blank=True)
    mobil = models.CharField(_("Mobil"), max_length=40, blank=True)
    adresse_wie_kind = models.BooleanField(_("Adresse wie Kind"), default=True)
    strasse = models.CharField(_("Straße / Hausnummer / Estate"), max_length=120, blank=True)
    postfach = models.CharField(_("Postfach (P.O. Box)"), max_length=40, blank=True)
    plz = models.CharField(_("PLZ / Postal Code"), max_length=12, blank=True)
    ort = models.CharField(_("Ort"), max_length=80, blank=True)
    land = models.CharField(_("Land"), max_length=60, blank=True)
    sprache = models.CharField(_("Bevorzugte Sprache"), max_length=2, choices=[("de", _("Deutsch")), ("en", _("Englisch"))], default="de")
    korrespondenzweg = models.CharField(_("Bevorzugter Kommunikationsweg"), max_length=10, choices=Elternprofil.KORRESPONDENZ, default="email")
    beruf = models.CharField(_("Beruf"), max_length=100, blank=True)
    arbeitgeber = models.CharField(_("Arbeitgeber / Organisation"), max_length=120, blank=True)
    sorgerecht = models.BooleanField(_("Sorgerecht"), default=True)
    abholberechtigt = models.BooleanField(_("Abholberechtigt"), default=True)
    notfallkontakt = models.BooleanField(_("Notfallkontakt"), default=False)
    rechnungsempfaenger = models.BooleanField(_("Rechnungsempfänger:in"), default=False)
    reihenfolge = models.PositiveSmallIntegerField(_("Reihenfolge"), default=1)
    person = models.ForeignKey(Person, on_delete=models.SET_NULL, null=True, blank=True, editable=False, related_name="+",
                               verbose_name=_("Übernommen als Person"))
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Kontakt (Anmeldung)"))

    class Meta:
        verbose_name = _("Kontakt (Anmeldung)")
        verbose_name_plural = _("Kontakte (Anmeldung)")
        ordering = ["anmeldung", "reihenfolge", "pk"]

    def __str__(self):
        return f"{self.vorname} {self.nachname} ({self.get_art_display()})"

    @property
    def anzeigename(self):
        return f"{self.vorname} {self.nachname}"


class AnmeldeDatei(models.Model):
    """Zeugnisse und weitere Unterlagen der Bewerbung – sortiert nach Upload-Datum."""

    # Voreinstellung der Sichtbarkeit nach der Übernahme in die Schülerakte
    STUFE_NACH_KATEGORIE = {"zeugnis": "akte", "ausweis": "verwaltung", "vertrag": "verwaltung", "diagnostik": "foerderung",
                            "attest": "verwaltung", "foerderung": "foerderung"}

    anmeldung = models.ForeignKey(Anmeldung, on_delete=models.CASCADE, related_name="dateien", verbose_name=_("Anmeldung"))
    kategorie = models.CharField(_("Kategorie"), max_length=15, choices=Dokument.KATEGORIEN, default="zeugnis")
    titel = models.CharField(_("Titel"), max_length=120)
    datei = models.FileField(_("Datei"), upload_to=aufnahme_pfad, storage=aufnahme_speicher, max_length=200,
                             validators=[groesse_pruefen])
    originalname = models.CharField(_("Dateiname"), max_length=200, blank=True, editable=False)
    groesse = models.PositiveBigIntegerField(_("Größe (Byte)"), default=0, editable=False)
    inhaltstyp = models.CharField(_("Dateityp"), max_length=100, blank=True, editable=False)
    notiz = models.CharField(_("Notiz"), max_length=200, blank=True)
    zugriffsstufe = models.CharField(_("Sichtbar nach Übernahme für"), max_length=12, choices=Dokument.STUFEN, default="akte")
    uebernehmen = models.BooleanField(_("In die Schülerakte übernehmen"), default=True)
    hochgeladen_am = models.DateTimeField(_("Hochgeladen am"), auto_now_add=True)
    hochgeladen_von = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                        related_name="+", verbose_name=_("Hochgeladen von"))
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Datei (Anmeldung)"))

    class Meta:
        verbose_name = _("Datei (Anmeldung)")
        verbose_name_plural = _("Dateien (Anmeldung)")
        ordering = ["-hochgeladen_am", "-pk"]

    def __str__(self):
        return self.titel

    def save(self, *args, **kwargs):
        if self.datei and not getattr(self.datei, "_committed", True):
            dateimetadaten(self, self.datei)
        super().save(*args, **kwargs)

    @property
    def groesse_lesbar(self):
        return groesse_lesbar(self.groesse)

    @property
    def dateiendung(self):
        return os.path.splitext(self.originalname or self.datei.name or "")[1].lstrip(".").upper()


class AnmeldePunkt(models.Model):
    """Ein Punkt der Checkliste einer Anmeldung – aus einer Vorlage übernommen oder frei ergänzt."""

    anmeldung = models.ForeignKey(Anmeldung, on_delete=models.CASCADE, related_name="punkte", verbose_name=_("Anmeldung"))
    text = models.CharField(_("Punkt"), max_length=160)
    text_en = models.CharField(_("Punkt (Englisch)"), max_length=160, blank=True)
    zustaendig = models.CharField(_("Zuständig"), max_length=14, choices=ZUSTAENDIG, blank=True)
    pflicht = models.BooleanField(_("Pflicht vor Übernahme"), default=True)
    reihenfolge = models.PositiveSmallIntegerField(_("Reihenfolge"), default=10)
    erledigt = models.BooleanField(_("Erledigt"), default=False)
    erledigt_am = models.DateTimeField(_("Erledigt am"), null=True, blank=True)
    erledigt_von = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                     related_name="+", verbose_name=_("Erledigt von"))
    bemerkung = models.CharField(_("Bemerkung"), max_length=200, blank=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Checklistenpunkt"))

    class Meta:
        verbose_name = _("Checklistenpunkt")
        verbose_name_plural = _("Checklistenpunkte")
        ordering = ["anmeldung", "reihenfolge", "pk"]

    def __str__(self):
        return self.lokal_text

    @property
    def lokal_text(self):
        return lokal(self, "text")

    def abhaken(self, user, erledigt=True):
        self.erledigt = erledigt
        self.erledigt_am = timezone.now() if erledigt else None
        self.erledigt_von = user if erledigt else None
        self.save(update_fields=["erledigt", "erledigt_am", "erledigt_von"])

