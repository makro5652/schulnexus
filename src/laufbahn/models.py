"""
Schullaufbahn über Schuljahre hinweg: Aufnahme → Klasse → Versetzung → Schuljahreswechsel → Abgang → Archiv.

- Schuljahreswechsel: überträgt alle Schüler:innen eines Schuljahres in das folgende (versetzt, Wiederholung,
  Überspringen, Zurückstufung, Abschluss, Abgang). Jeder Schritt wird je Schüler:in als Wechselposten mit den
  Daten für die Rücknahme gespeichert; einzelne Posten und der ganze Wechsel lassen sich zurücknehmen.
- Laufbahnereignis: Änderungen im laufenden Schuljahr (Klassenwechsel, Hoch- oder Zurückstufung, Abgang), ebenfalls
  mit Rücknahme.
- Löschfrist / Löschvorgang: Aufbewahrungsfristen für Daten abgegangener Schüler:innen, Erinnerung der Schulleitung
  und Nachweis der Löschung (ohne Namen, nur mit Schülernummer).
"""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from stammdaten.models import Gruppe, Schuelerprofil, Schuljahr

# Entscheidung beim Schuljahreswechsel: (Schlüssel, Bezeichnung, Änderung des Jahrgangs oder None = verlässt die Schule)
ENTSCHEIDUNGEN = [
    ("versetzt", _("versetzt"), 1),
    ("nicht_versetzt", _("nicht versetzt – wiederholt"), 0),
    ("freiwillig", _("freiwillige Wiederholung"), 0),
    ("ueberspringen", _("überspringt eine Jahrgangsstufe"), 2),
    ("zurueckstufen", _("Zurückstufung"), -1),
    ("abschluss", _("Abschluss – verlässt die Schule"), None),
    ("abgang", _("Abgang – verlässt die Schule"), None),
]
JAHRGANG_PLUS = {k: d for k, _n, d in ENTSCHEIDUNGEN}
# Ergebnis im Laufbahnabschnitt des alten Schuljahres
ERGEBNIS_FUER = {"versetzt": "versetzt", "nicht_versetzt": "nicht_versetzt", "freiwillig": "freiwillig_wiederholt",
                 "ueberspringen": "uebersprungen", "zurueckstufen": "zurueckgestuft", "abschluss": "abschluss", "abgang": "abgang"}


class Schuljahreswechsel(models.Model):
    VORBEREITET, DURCHGEFUEHRT = "vorbereitet", "durchgefuehrt"
    STATUS = [(VORBEREITET, _("in Vorbereitung")), (DURCHGEFUEHRT, _("durchgeführt"))]

    von = models.ForeignKey(Schuljahr, on_delete=models.PROTECT, related_name="wechsel_von", verbose_name=_("Von Schuljahr"))
    nach = models.ForeignKey(Schuljahr, on_delete=models.PROTECT, related_name="wechsel_nach", verbose_name=_("In Schuljahr"))
    status = models.CharField(_("Status"), max_length=14, choices=STATUS, default=VORBEREITET)
    aktiv_umgestellt = models.BooleanField(_("Aktuelles Schuljahr umgestellt"), default=False, editable=False)
    erstellt_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                     editable=False, verbose_name=_("Angelegt von"))
    erstellt_am = models.DateTimeField(_("Angelegt am"), auto_now_add=True)
    durchgefuehrt_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                          related_name="+", editable=False, verbose_name=_("Durchgeführt von"))
    durchgefuehrt_am = models.DateTimeField(_("Durchgeführt am"), null=True, blank=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Schuljahreswechsel"))

    class Meta:
        verbose_name = _("Schuljahreswechsel")
        verbose_name_plural = _("Schuljahreswechsel")
        ordering = ["-von__beginn"]
        constraints = [models.UniqueConstraint(fields=["von"], name="ein_wechsel_je_schuljahr")]

    def __str__(self):
        return f"{self.von} → {self.nach}"

    @property
    def durchgefuehrt(self):
        return self.status == self.DURCHGEFUEHRT


class Klassenplan(models.Model):
    """Welche Stammklasse des neuen Schuljahres auf eine Stammklasse des alten folgt (z. B. 9a → 10a)."""

    wechsel = models.ForeignKey(Schuljahreswechsel, on_delete=models.CASCADE, related_name="klassenplan", verbose_name=_("Wechsel"))
    alt = models.ForeignKey(Gruppe, on_delete=models.CASCADE, related_name="+", verbose_name=_("Bisherige Klasse"))
    neu = models.ForeignKey(Gruppe, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                            verbose_name=_("Nachfolgeklasse"))
    neu_angelegt = models.BooleanField(_("Vom Wechsel angelegt"), default=False)

    class Meta:
        verbose_name = _("Klassenplan")
        verbose_name_plural = _("Klassenplan")
        unique_together = [("wechsel", "alt")]
        ordering = ["alt__jahrgang", "alt__name"]

    def __str__(self):
        return f"{self.alt} → {self.neu or '–'}"


class Wechselposten(models.Model):
    OFFEN, DURCHGEFUEHRT = "offen", "durchgefuehrt"
    STATUS = [(OFFEN, _("offen")), (DURCHGEFUEHRT, _("durchgeführt"))]

    wechsel = models.ForeignKey(Schuljahreswechsel, on_delete=models.CASCADE, related_name="posten", verbose_name=_("Wechsel"))
    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="wechselposten", verbose_name=_("Schüler:in"))
    alte_klasse = models.ForeignKey(Gruppe, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                    verbose_name=_("Bisherige Klasse"))
    alter_jahrgang = models.PositiveSmallIntegerField(_("Bisheriger Jahrgang"), null=True, blank=True)
    entscheidung = models.CharField(_("Entscheidung"), max_length=16, choices=[(k, n) for k, n, _d in ENTSCHEIDUNGEN],
                                    default="versetzt")
    grundlage = models.CharField(_("Grundlage"), max_length=200, blank=True,
                                 help_text=_("z. B. Beschluss der Versetzungskonferenz"))
    neue_klasse = models.ForeignKey(Gruppe, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                    verbose_name=_("Neue Klasse"))
    status = models.CharField(_("Status"), max_length=14, choices=STATUS, default=OFFEN)
    rueckgaengig = models.JSONField(_("Daten für die Rücknahme"), default=dict, blank=True, editable=False)
    durchgefuehrt_am = models.DateTimeField(_("Durchgeführt am"), null=True, blank=True)
    zurueckgenommen_am = models.DateTimeField(_("Zuletzt zurückgenommen am"), null=True, blank=True)

    class Meta:
        verbose_name = _("Wechselposten")
        verbose_name_plural = _("Wechselposten")
        unique_together = [("wechsel", "schueler")]
        ordering = ["alte_klasse__name", "schueler__person__nachname", "schueler__person__vorname"]

    def __str__(self):
        return f"{self.schueler}: {self.get_entscheidung_display()}"

    @property
    def verlaesst_schule(self):
        return JAHRGANG_PLUS.get(self.entscheidung) is None

    @property
    def neuer_jahrgang(self):
        plus = JAHRGANG_PLUS.get(self.entscheidung)
        if plus is None or self.alter_jahrgang is None:
            return None
        return max(self.alter_jahrgang + plus, 1)


class Laufbahnereignis(models.Model):
    """Änderung der Schullaufbahn im laufenden Schuljahr – mit den Daten für die Rücknahme."""

    KLASSENWECHSEL, HOCHGESTUFT, ZURUECKGESTUFT, ABGANG = "klassenwechsel", "hochgestuft", "zurueckgestuft", "abgang"
    ARTEN = [(KLASSENWECHSEL, _("Klassenwechsel")), (HOCHGESTUFT, _("Höherstufung (Überspringen)")),
             (ZURUECKGESTUFT, _("Zurückstufung")), (ABGANG, _("Abgang"))]

    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="laufbahnereignisse",
                                 verbose_name=_("Schüler:in"))
    art = models.CharField(_("Art"), max_length=16, choices=ARTEN)
    datum = models.DateField(_("Wirksam ab"))
    text = models.CharField(_("Beschreibung"), max_length=250)
    bemerkung = models.CharField(_("Bemerkung"), max_length=250, blank=True)
    daten = models.JSONField(_("Daten für die Rücknahme"), default=dict, blank=True, editable=False)
    erstellt_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="+", editable=False, verbose_name=_("Erfasst von"))
    erstellt_am = models.DateTimeField(_("Erfasst am"), auto_now_add=True)
    zurueckgenommen_am = models.DateTimeField(_("Zurückgenommen am"), null=True, blank=True)

    class Meta:
        verbose_name = _("Laufbahnereignis")
        verbose_name_plural = _("Laufbahnereignisse")
        ordering = ["-erstellt_am"]

    def __str__(self):
        return f"{self.schueler}: {self.text}"


class Loeschfrist(models.Model):
    """Aufbewahrungsfrist je Datenkategorie, gerechnet ab dem Austritt der Schülerin / des Schülers."""

    KATEGORIEN = [
        ("fehlzeiten", _("Fehlzeiten, Entschuldigungen und AG-Teilnahme")),
        ("elternkontakt", _("Elternnachrichten, Gesprächstermine und automatische Benachrichtigungen")),
        ("gesundheit", _("Gesundheitsangaben")),
        ("foerderung", _("Förderpläne, Förderverlauf und Nachteilsausgleiche")),
        ("noten", _("Einzelnoten und Zeugnisnoten des Notenmoduls")),
        ("dokumente", _("Anhänge (hochgeladene Dokumente)")),
        ("aufnahme", _("Anmeldeunterlagen der Neuanmeldung")),
        ("zeugnisse", _("Halbjahres- und Jahreszeugnisse, Konferenzbeschlüsse")),
        ("kontakte", _("Kontaktdaten, Elternverknüpfungen und Benutzerkonto")),
        ("akte", _("Gesamte Schülerakte einschließlich Abgangs- und Abschlusszeugnis")),
    ]
    # Vorschlagswerte (Jahre) – bewusst vorsichtig; die Schulleitung legt die verbindlichen Fristen fest.
    VORSCHLAG = {"fehlzeiten": 2, "elternkontakt": 2, "gesundheit": 1, "foerderung": 5, "noten": 5, "dokumente": 5,
                 "aufnahme": 5, "zeugnisse": 5, "kontakte": 5, "akte": 50}
    BEZUG = [("jahresende", _("Ende des Kalenderjahres des Austritts")), ("austritt", _("Austrittsdatum"))]
    LOESCHEN, ERINNERN = "loeschen", "erinnern"
    AKTIONEN = [(LOESCHEN, _("Erinnern und nach Bestätigung löschen")), (ERINNERN, _("Nur erinnern (Löschung von Hand)"))]

    kategorie = models.CharField(_("Daten"), max_length=16, choices=KATEGORIEN, unique=True)
    jahre = models.PositiveSmallIntegerField(_("Aufbewahrung (Jahre)"))
    bezug = models.CharField(_("Frist beginnt mit"), max_length=12, choices=BEZUG, default="jahresende")
    aktion = models.CharField(_("Bei Fristablauf"), max_length=10, choices=AKTIONEN, default=LOESCHEN)
    aktiv = models.BooleanField(_("Aktiv"), default=True)
    hinweis = models.CharField(_("Grundlage / Hinweis"), max_length=250, blank=True)
    geaendert_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name="+", editable=False, verbose_name=_("Geändert von"))
    geaendert_am = models.DateTimeField(_("Geändert am"), auto_now=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Löschfrist"))

    class Meta:
        verbose_name = _("Löschfrist")
        verbose_name_plural = _("Löschfristen")
        permissions = [("loeschen_archiv", _("Kann Daten aus dem Archiv endgültig löschen"))]

    def __str__(self):
        return f"{self.get_kategorie_display()}: {self.jahre}"

    @property
    def reihenfolge(self):
        return [k for k, _n in self.KATEGORIEN].index(self.kategorie)


class Loeschvorgang(models.Model):
    """Nachweis einer Löschung oder eines Aufschubs. Bewusst ohne Namen – nur Schülernummer und Kategorie."""

    ERLEDIGT, AUFGESCHOBEN, LEER = "erledigt", "aufgeschoben", "leer"
    STATUS = [(ERLEDIGT, _("gelöscht")), (AUFGESCHOBEN, _("aufgeschoben")), (LEER, _("keine Daten vorhanden"))]

    schuelernummer = models.CharField(_("Schülernummer"), max_length=20)
    kategorie = models.CharField(_("Daten"), max_length=16, choices=Loeschfrist.KATEGORIEN)
    status = models.CharField(_("Status"), max_length=14, choices=STATUS)
    anzahl = models.PositiveIntegerField(_("Gelöschte Einträge"), default=0)
    bis = models.DateField(_("Aufgeschoben bis"), null=True, blank=True)
    grund = models.CharField(_("Grund"), max_length=250, blank=True)
    von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                            verbose_name=_("Von"))
    am = models.DateTimeField(_("Am"), auto_now=True)

    class Meta:
        verbose_name = _("Löschvorgang")
        verbose_name_plural = _("Löschvorgänge")
        unique_together = [("schuelernummer", "kategorie")]
        ordering = ["-am"]

    def __str__(self):
        return f"{self.schuelernummer} · {self.get_kategorie_display()} · {self.get_status_display()}"
