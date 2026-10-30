"""
Zeugnisse und Konferenzen.

Grundlage: Ordnung für den Abschluss der Sekundarstufe I an Deutschen Schulen im Ausland (Sek I-PO,
KMK 16.03.2017, Zeugnismuster Anlage 11) und Richtlinie zur Gestaltung von Bildungsgängen und Abschlüssen
in der Sekundarstufe I an DAS (Beschluss vom 18.03.2026).

- Zeugnis: je Schüler:in und Halbjahr (1. Halbjahr = Halbjahreszeugnis, 2. Halbjahr = Jahreszeugnis).
  Die Fachnoten kommen aus den Zeugnisnoten des Notenmoduls; bei der Freigabe werden sie festgeschrieben.
- Zeugniskommentar: individueller Text der Klassenleitung; alle unterrichtenden Lehrkräfte zeichnen ab
  und können Anmerkungen hinterlassen. Ändert sich der Text, gelten frühere Abzeichnungen als veraltet.
- Konferenz: Halbjahreskonferenz (Gefährdungen) bzw. Klassenkonferenz als Versetzungskonferenz mit
  Beschluss je Schüler:in und Protokoll.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from stammdaten.models import Abschnitt, Bildungsgang, Fach, Gruppe, Personalprofil, Schuelerprofil

VERSETZUNG = [
    ("", "—"),
    ("versetzt", _("Versetzt")),
    ("nicht_versetzt", _("Nicht versetzt")),
    ("qp_ja", _("Berechtigung zum Übergang in die Qualifikationsphase erhalten")),
    ("qp_nein", _("Berechtigung zum Übergang in die Qualifikationsphase nicht erhalten")),
    ("wiederholung", _("Freiwillige Wiederholung")),
]


class Zeugnis(models.Model):
    HALBJAHR, JAHR, ABGANG = "halbjahr", "jahr", "abgang"
    ARTEN = [(HALBJAHR, _("Halbjahreszeugnis")), (JAHR, _("Jahreszeugnis")), (ABGANG, _("Abgangszeugnis"))]
    ENTWURF, FREIGEGEBEN = "entwurf", "freigegeben"
    STATUS = [(ENTWURF, _("Entwurf")), (FREIGEGEBEN, _("Freigegeben"))]
    # GeR-Tabelle wie im Muster (Anlage 11)
    GER_ZEILEN = [
        ("fs1", _("1. Fremdsprache / Landessprache als Fremdsprache")),
        ("landessprache", _("Landessprache auf Erstsprachenniveau")),
        ("fs2", _("2. Fremdsprache")),
        ("neu", _("Neu beginnende Fremdsprache")),
    ]

    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="zeugnisse", verbose_name=_("Schüler:in"))
    abschnitt = models.ForeignKey(Abschnitt, on_delete=models.PROTECT, related_name="zeugnisse", verbose_name=_("Halbjahr"))
    art = models.CharField(_("Art"), max_length=10, choices=ARTEN, default=HALBJAHR)
    klasse = models.ForeignKey(Gruppe, on_delete=models.SET_NULL, null=True, blank=True, related_name="zeugnisse",
                               verbose_name=_("Klasse"))
    jahrgang = models.PositiveSmallIntegerField(_("Jahrgangsstufe"), null=True, blank=True)
    bildungsgang = models.ForeignKey(Bildungsgang, on_delete=models.SET_NULL, null=True, blank=True, verbose_name=_("Bildungsgang"))

    bemerkungen = models.TextField(_("Bemerkungen"), blank=True,
                                   help_text=_("z. B. Teilnahme an Arbeitsgemeinschaft, Wahlfach, Betriebspraktikum, Wettbewerb; "
                                               "Mitarbeit in schulischen Gremien"))
    ger = models.JSONField(_("GeR-Niveaustufen"), default=dict, blank=True)
    versetzung = models.CharField(_("Versetzungs- bzw. Berechtigungsvermerk"), max_length=14, choices=VERSETZUNG, blank=True)
    fehltage_entschuldigt = models.PositiveSmallIntegerField(_("Fehltage entschuldigt"), null=True, blank=True)
    fehltage_unentschuldigt = models.PositiveSmallIntegerField(_("Fehltage unentschuldigt"), null=True, blank=True)
    zeugnisdatum = models.DateField(_("Datum des Zeugnisses"), null=True, blank=True)
    abgangsvermerk = models.TextField(_("Abgangsvermerk"), blank=True,
                                      help_text=_("Nur beim Abgangszeugnis, z. B. „Grund: Umzug der Familie nach Mombasa.“"))
    ort = models.CharField(_("Ort"), max_length=60, blank=True)

    kommentar = models.TextField(_("Zeugniskommentar"), blank=True)
    kommentar_geaendert = models.DateTimeField(_("Kommentar zuletzt geändert"), null=True, blank=True, editable=False)
    kommentar_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                      editable=False, related_name="+", verbose_name=_("Kommentar zuletzt geändert von"))
    kommentar_drucken = models.BooleanField(_("Kommentar als Beiblatt drucken"), default=True)

    status = models.CharField(_("Status"), max_length=12, choices=STATUS, default=ENTWURF)
    freigegeben_am = models.DateTimeField(_("Freigegeben am"), null=True, blank=True, editable=False)
    freigegeben_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                        editable=False, related_name="+", verbose_name=_("Freigegeben von"))
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Zeugnis"))

    class Meta:
        verbose_name = _("Zeugnis")
        verbose_name_plural = _("Zeugnisse")
        unique_together = [("schueler", "abschnitt")]
        ordering = ["abschnitt", "schueler__person__nachname", "schueler__person__vorname"]
        permissions = [("freigeben_zeugnis", _("Kann Zeugnisse freigeben"))]

    def __str__(self):
        return f"{self.get_art_display()} {self.abschnitt} – {self.schueler}"

    @property
    def freigegeben(self):
        return self.status == self.FREIGEGEBEN

    def kommentar_setzen(self, text, user):
        """Speichert den Kommentar; nur eine echte Änderung macht frühere Abzeichnungen ungültig."""
        text = (text or "").strip()
        if text == (self.kommentar or "").strip():
            return False
        self.kommentar = text
        self.kommentar_geaendert = timezone.now()
        self.kommentar_von = user
        return True

    def ger_zeilen(self):
        zeilen = []
        for schluessel, name in self.GER_ZEILEN:
            werte = (self.ger or {}).get(schluessel) or {}
            zeilen.append({"schluessel": schluessel, "name": name, "sprache": werte.get("sprache", ""),
                           "von": werte.get("von", ""), "bis": werte.get("bis", ""), "niveau": werte.get("niveau", "")})
        return zeilen

    @property
    def ger_ausgefuellt(self):
        return any(any(v for v in (w or {}).values()) for w in (self.ger or {}).values())


class ZeugnisFachnote(models.Model):
    """Bei der Freigabe festgeschriebene Fachnote – das gedruckte Zeugnis ändert sich danach nicht mehr."""

    zeugnis = models.ForeignKey(Zeugnis, on_delete=models.CASCADE, related_name="fachnoten", verbose_name=_("Zeugnis"))
    fach = models.ForeignKey(Fach, on_delete=models.PROTECT, verbose_name=_("Fach"))
    fachname = models.CharField(_("Fachbezeichnung"), max_length=80)
    note = models.PositiveSmallIntegerField(_("Note"), null=True, blank=True)
    punkte = models.BooleanField(_("Punkte statt Note"), default=False)
    vermerk = models.CharField(_("Vermerk"), max_length=8, blank=True)
    hinweis = models.CharField(_("Hinweis"), max_length=60, blank=True, help_text=_("z. B. 1. Halbjahr bei epochalem Unterricht"))
    spalte = models.PositiveSmallIntegerField(_("Spalte"), default=1)
    reihenfolge = models.PositiveSmallIntegerField(_("Reihenfolge"), default=100)

    class Meta:
        verbose_name = _("Fachnote (Zeugnis)")
        verbose_name_plural = _("Fachnoten (Zeugnis)")
        ordering = ["zeugnis", "spalte", "reihenfolge"]

    def __str__(self):
        return f"{self.fachname}: {self.vermerk or (self.note if self.note is not None else '–')}"


class Abzeichnung(models.Model):
    """Digitale Kenntnisnahme des Zeugniskommentars durch eine unterrichtende Lehrkraft."""

    zeugnis = models.ForeignKey(Zeugnis, on_delete=models.CASCADE, related_name="abzeichnungen", verbose_name=_("Zeugnis"))
    lehrkraft = models.ForeignKey(Personalprofil, on_delete=models.CASCADE, related_name="abzeichnungen", verbose_name=_("Lehrkraft"))
    am = models.DateTimeField(_("Abgezeichnet am"), default=timezone.now)
    stand = models.DateTimeField(_("Stand des Kommentars"), null=True, blank=True)

    class Meta:
        verbose_name = _("Abzeichnung")
        verbose_name_plural = _("Abzeichnungen")
        unique_together = [("zeugnis", "lehrkraft")]

    def __str__(self):
        return f"{self.lehrkraft} · {self.zeugnis}"

    @property
    def aktuell(self):
        return self.zeugnis.kommentar_geaendert is None or (self.stand is not None and self.stand >= self.zeugnis.kommentar_geaendert)


class Anmerkung(models.Model):
    """Anmerkung einer Lehrkraft zum Zeugniskommentar (z. B. Ergänzungs- oder Änderungsvorschlag)."""

    zeugnis = models.ForeignKey(Zeugnis, on_delete=models.CASCADE, related_name="anmerkungen", verbose_name=_("Zeugnis"))
    autor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+", verbose_name=_("Von"))
    text = models.TextField(_("Anmerkung"))
    erstellt = models.DateTimeField(_("Erstellt"), auto_now_add=True)
    erledigt = models.BooleanField(_("Erledigt"), default=False)

    class Meta:
        verbose_name = _("Anmerkung zum Kommentar")
        verbose_name_plural = _("Anmerkungen zum Kommentar")
        ordering = ["zeugnis", "erstellt"]

    def __str__(self):
        return self.text[:60]


class Konferenz(models.Model):
    HALBJAHR, VERSETZUNG = "halbjahr", "versetzung"
    ARTEN = [(HALBJAHR, _("Halbjahreskonferenz (Zeugniskonferenz)")),
             (VERSETZUNG, _("Klassenkonferenz als Versetzungskonferenz"))]
    GEPLANT, DURCHGEFUEHRT, ABGESCHLOSSEN = "geplant", "durchgefuehrt", "abgeschlossen"
    STATUS = [(GEPLANT, _("Geplant")), (DURCHGEFUEHRT, _("Durchgeführt")), (ABGESCHLOSSEN, _("Abgeschlossen"))]

    klasse = models.ForeignKey(Gruppe, on_delete=models.CASCADE, related_name="konferenzen", verbose_name=_("Klasse"))
    abschnitt = models.ForeignKey(Abschnitt, on_delete=models.PROTECT, related_name="konferenzen", verbose_name=_("Halbjahr"))
    art = models.CharField(_("Art"), max_length=12, choices=ARTEN, default=HALBJAHR)
    datum = models.DateField(_("Datum"), null=True, blank=True)
    beginn = models.TimeField(_("Beginn"), null=True, blank=True)
    ende = models.TimeField(_("Ende"), null=True, blank=True)
    ort = models.CharField(_("Ort / Raum"), max_length=60, blank=True)
    vorsitz = models.ForeignKey(Personalprofil, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                verbose_name=_("Vorsitz"))
    protokoll = models.ForeignKey(Personalprofil, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                  verbose_name=_("Protokoll"))
    teilnehmende = models.ManyToManyField(Personalprofil, blank=True, related_name="konferenzen", verbose_name=_("Anwesend"))
    notizen = models.TextField(_("Allgemeine Beratungspunkte"), blank=True)
    status = models.CharField(_("Status"), max_length=14, choices=STATUS, default=GEPLANT)
    erstellt_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     editable=False, related_name="+")
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Konferenz"))

    class Meta:
        verbose_name = _("Konferenz")
        verbose_name_plural = _("Konferenzen")
        unique_together = [("klasse", "abschnitt")]
        ordering = ["-abschnitt__beginn", "klasse__name"]

    def __str__(self):
        return f"{self.get_art_display()} {self.klasse} – {self.abschnitt}"

    @property
    def abgeschlossen(self):
        return self.status == self.ABGESCHLOSSEN


class Beschluss(models.Model):
    ENTSCHEIDUNGEN = [
        ("", _("— offen —")),
        ("keine", _("Keine Entscheidung (Halbjahr)")),
        ("versetzt", _("Versetzt")),
        ("versetzt_ausgleich", _("Versetzt mit Notenausgleich")),
        ("nachpruefung", _("Nicht versetzt – Nachprüfung möglich")),
        ("nicht_versetzt", _("Nicht versetzt")),
        ("qp_ja", _("Berechtigung Qualifikationsphase erteilt")),
        ("qp_nein", _("Berechtigung Qualifikationsphase nicht erteilt")),
        ("wiederholung", _("Freiwillige Wiederholung")),
    ]
    # Übertrag auf das Zeugnis
    ZEUGNISVERMERK = {"versetzt": "versetzt", "versetzt_ausgleich": "versetzt", "nachpruefung": "nicht_versetzt",
                      "nicht_versetzt": "nicht_versetzt", "qp_ja": "qp_ja", "qp_nein": "qp_nein", "wiederholung": "wiederholung"}

    konferenz = models.ForeignKey(Konferenz, on_delete=models.CASCADE, related_name="beschluesse", verbose_name=_("Konferenz"))
    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="konferenzbeschluesse", verbose_name=_("Schüler:in"))
    vorschlag = models.CharField(_("Vorschlag des Systems"), max_length=250, blank=True)
    entscheidung = models.CharField(_("Entscheidung"), max_length=20, choices=ENTSCHEIDUNGEN, blank=True)
    ausgleich = models.CharField(_("Notenausgleich durch"), max_length=200, blank=True)
    gefaehrdung = models.CharField(_("Versetzung gefährdet in"), max_length=200, blank=True)
    gefaehrdung_mitgeteilt = models.DateField(_("Gefährdung schriftlich mitgeteilt am"), null=True, blank=True)
    stimmen_ja = models.PositiveSmallIntegerField(_("Stimmen dafür"), null=True, blank=True)
    stimmen_nein = models.PositiveSmallIntegerField(_("Stimmen dagegen"), null=True, blank=True)
    begruendung = models.TextField(_("Begründung / Bemerkung für das Protokoll"), blank=True)
    nicht_mitwirkend = models.CharField(_("Nicht mitwirkend (Verwandtschaft, häusliche Gemeinschaft)"), max_length=200, blank=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Konferenzbeschluss"))

    class Meta:
        verbose_name = _("Konferenzbeschluss")
        verbose_name_plural = _("Konferenzbeschlüsse")
        unique_together = [("konferenz", "schueler")]

    def __str__(self):
        return f"{self.schueler}: {self.get_entscheidung_display()}"


class Textbaustein(models.Model):
    """Textbaustein für Zeugniskommentare (ab 0.4.16.0); {vorname} wird beim Einfügen durch den Rufnamen ersetzt."""

    titel = models.CharField(_("Titel"), max_length=80, help_text=_("kurz, z. B. „Arbeitsverhalten sehr gut“"))
    kategorie = models.CharField(_("Kategorie"), max_length=60, blank=True, help_text=_("z. B. Arbeitsverhalten, Sozialverhalten"))
    text = models.TextField(_("Text"), help_text=_("{vorname} wird durch den Rufnamen ersetzt, {sie_er} durch „sie“ bzw. „er“."))
    jahrgang_von = models.PositiveSmallIntegerField(_("ab Jahrgang"), null=True, blank=True)
    jahrgang_bis = models.PositiveSmallIntegerField(_("bis Jahrgang"), null=True, blank=True)
    aktiv = models.BooleanField(_("Aktiv"), default=True)
    reihenfolge = models.PositiveSmallIntegerField(_("Reihenfolge"), default=10)

    class Meta:
        verbose_name = _("Textbaustein")
        verbose_name_plural = _("Textbausteine für Zeugniskommentare")
        ordering = ["kategorie", "reihenfolge", "titel"]

    def __str__(self):
        return f"{self.kategorie} – {self.titel}" if self.kategorie else self.titel

    @classmethod
    def fuer(cls, jahrgang):
        qs = cls.objects.filter(aktiv=True)
        if jahrgang:
            qs = qs.filter(models.Q(jahrgang_von__isnull=True) | models.Q(jahrgang_von__lte=jahrgang)).filter(
                models.Q(jahrgang_bis__isnull=True) | models.Q(jahrgang_bis__gte=jahrgang))
        return qs

    def fuer_schueler(self, person):
        sie_er = {"w": "sie", "m": "er"}.get(person.geschlecht, (person.rufname or person.vorname))
        return self.text.replace("{vorname}", person.rufname or person.vorname).replace("{sie_er}", sie_er)


class Unterzeichner(models.Model):
    """Wer das Zeugnis für die Schulleitung unterschreibt (ab 0.4.16.0), je Jahrgangsbereich – Name steht unter der Linie."""

    person = models.ForeignKey("stammdaten.Personalprofil", on_delete=models.CASCADE, related_name="+", verbose_name=_("Person"))
    funktion = models.CharField(_("Funktion"), max_length=80, help_text=_("wie unter der Unterschrift, z. B. Schulleiter, Leiterin der Grundschule"))
    jahrgang_von = models.PositiveSmallIntegerField(_("ab Jahrgang"))
    jahrgang_bis = models.PositiveSmallIntegerField(_("bis Jahrgang"))

    class Meta:
        verbose_name = _("Unterzeichner:in")
        verbose_name_plural = _("Unterzeichnung der Zeugnisse")
        ordering = ["jahrgang_von"]

    def __str__(self):
        return f"{self.funktion}: {self.person} (Jg. {self.jahrgang_von}–{self.jahrgang_bis})"

    @classmethod
    def fuer(cls, jahrgang):
        if not jahrgang:
            return None
        return cls.objects.filter(jahrgang_von__lte=jahrgang, jahrgang_bis__gte=jahrgang).select_related("person__person").first()
