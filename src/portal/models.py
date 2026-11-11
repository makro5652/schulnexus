from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


# Farbschemata der Oberfläche. „standard“ folgt der Hell-/Dunkel-Einstellung des Betriebssystems, alle anderen sind fest.
# Latte, Frappé, Macchiato und Mocha sind Paletten von Catppuccin (https://catppuccin.com, MIT-Lizenz), Nord stammt von
# https://www.nordtheme.com (MIT-Lizenz). Die Farben der Designs ab 0.6.1 erzeugt tools/designs_erzeugen.py.
DESIGN_COOKIE = "design"
DESIGNS = [
    ("standard", _("Standard (hell/dunkel nach System)")),
    ("hell", _("Schulnexus Hell")),
    ("ozean", _("Ozean (hell, blau)")),
    ("sepia", _("Sepia (hell, warm)")),
    ("latte", _("Catppuccin Latte (hell)")),
    ("kontrast", _("Hoher Kontrast (hell)")),
    ("dunkel", _("Schulnexus Dunkel")),
    ("nord", _("Nord (dunkel)")),
    ("frappe", _("Catppuccin Frappé (dunkel)")),
    ("macchiato", _("Catppuccin Macchiato (dunkel)")),
    ("mocha", _("Catppuccin Mocha (dunkel)")),
]
# Gliederung des Design-Menüs (ab 0.6.1)
DESIGN_GRUPPEN = [
    (_("Automatisch"), ["standard"]),
    (_("Hell"), ["hell", "ozean", "sepia", "latte", "kontrast"]),
    (_("Dunkel"), ["dunkel", "nord", "frappe", "macchiato", "mocha"]),
]


def design_gruppen():
    namen = dict(DESIGNS)
    return [(titel, [(code, namen[code]) for code in codes]) for titel, codes in DESIGN_GRUPPEN]


class Benutzereinstellung(models.Model):
    """Persönliche Einstellungen je Benutzerkonto: Sprache, Design der Oberfläche und entzogene Einzelrechte."""

    benutzer = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="einstellung", verbose_name=_("Benutzerkonto")
    )
    sprache = models.CharField(_("Sprache der Oberfläche"), max_length=8, choices=settings.LANGUAGES, default=settings.LANGUAGE_CODE)
    design = models.CharField(_("Design"), max_length=12, choices=DESIGNS, default="standard")
    entzogene_rechte = models.ManyToManyField(
        "auth.Permission", blank=True, related_name="+", verbose_name=_("Entzogene Rechte"),
        help_text=_("Rechte, die dieses Konto trotz seiner Rollen nicht hat (siehe Benutzer und Rechte)."))

    class Meta:
        verbose_name = _("Benutzereinstellung")
        verbose_name_plural = _("Benutzereinstellungen")

    def __str__(self):
        return f"{self.benutzer} ({self.sprache})"


class Notiz(models.Model):
    """Notizen auf der Startseite: privat für die eigene Person oder als Mitteilung an alle (Verwaltung/Leitung)."""

    PRIVAT, ALLE = "privat", "alle"
    SICHTBARKEIT = [(PRIVAT, _("Nur für mich")), (ALLE, _("Mitteilung an alle"))]
    FARBEN = [("gelb", _("Gelb")), ("gruen", _("Grün")), ("blau", _("Blau")), ("rosa", _("Rosa")), ("grau", _("Grau"))]

    besitzer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notizen",
                                 verbose_name=_("Verfasst von"))
    text = models.TextField(_("Notiz"), max_length=2000)
    farbe = models.CharField(_("Farbe"), max_length=6, choices=FARBEN, default="gelb")
    datum = models.DateField(
        _("Datum"), null=True, blank=True,
        help_text=_("Notiz: fällig am (wird ab diesem Tag hervorgehoben). Mitteilung: sichtbar bis einschließlich."),
    )
    sichtbarkeit = models.CharField(_("Sichtbar für"), max_length=6, choices=SICHTBARKEIT, default=PRIVAT)
    angeheftet = models.BooleanField(_("Angeheftet"), default=False)
    erledigt = models.BooleanField(_("Erledigt"), default=False)
    erstellt_am = models.DateTimeField(_("Erstellt am"), auto_now_add=True)
    geaendert_am = models.DateTimeField(_("Geändert am"), auto_now=True)

    class Meta:
        verbose_name = _("Notiz")
        verbose_name_plural = _("Notizen")
        ordering = ["erledigt", "-angeheftet", "-erstellt_am"]

    def __str__(self):
        return self.text[:50]

    @property
    def faellig(self):
        from django.utils import timezone

        return self.sichtbarkeit == self.PRIVAT and not self.erledigt and self.datum is not None and self.datum <= timezone.localdate()


class Zweifaktor(models.Model):
    """
    Zwei-Faktor-Anmeldung mit Einmalcodes (TOTP, RFC 6238) aus einer Authenticator-App.
    Freiwillig; die IT kann sie je Konto verpflichtend machen. Das Geheimnis wird verschlüsselt gespeichert.
    """

    benutzer = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="zweifaktor",
                                    verbose_name=_("Benutzerkonto"))
    geheimnis = models.TextField(_("Geheimnis (verschlüsselt)"), blank=True, editable=False)
    aktiv = models.BooleanField(_("Eingerichtet"), default=False)
    pflicht = models.BooleanField(_("Verpflichtend"), default=False,
                                  help_text=_("Von der IT angeordnet: Anmeldung erst nach Einrichtung möglich."))
    eingerichtet_am = models.DateTimeField(_("Eingerichtet am"), null=True, blank=True)
    letzter_schritt = models.BigIntegerField(_("Zuletzt verwendeter Zeitschritt"), default=0, editable=False)
    ersatzcodes = models.JSONField(_("Ersatzcodes (Prüfwerte)"), default=list, blank=True, editable=False)
    zuletzt_verwendet = models.DateTimeField(_("Zuletzt verwendet"), null=True, blank=True)

    class Meta:
        verbose_name = _("Zwei-Faktor-Anmeldung")
        verbose_name_plural = _("Zwei-Faktor-Anmeldungen")

    def __str__(self):
        return str(self.benutzer)


class Anmeldeversuch(models.Model):
    """Fehlgeschlagene Anmeldung (Passwort oder zweiter Faktor) – Grundlage der vorübergehenden Sperre (ab 0.4.9.2).
    Einträge werden nach einem Tag gelöscht und nach erfolgreicher Anmeldung des Kontos entfernt."""

    benutzername = models.CharField(_("Benutzername"), max_length=150, db_index=True)
    ip = models.GenericIPAddressField(_("IP-Adresse"), null=True, blank=True, db_index=True)
    zeit = models.DateTimeField(_("Zeitpunkt"), auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = _("Fehlgeschlagene Anmeldung")
        verbose_name_plural = _("Fehlgeschlagene Anmeldungen")
        ordering = ["-zeit"]

    def __str__(self):
        return f"{self.benutzername} · {self.ip or '–'} · {self.zeit:%Y-%m-%d %H:%M}"


class OfficeKachel(models.Model):
    """
    Kachel auf der Seite „Office“: Verknüpfung zu einer Microsoft-365-Anwendung (öffnet in neuem Tab).
    Microsoft verbietet das Einbetten von Outlook & Co. in fremde Seiten (X-Frame-Options), daher keine Einbettung.
    """

    SYMBOLE = [
        ("brief", _("Brief (E-Mail)")), ("kalender", _("Kalender")), ("personen", _("Personen (Teams)")),
        ("ordner", _("Ordner (Dateien)")), ("stift", _("Stift (Text)")), ("liste", _("Liste (Tabelle)")),
        ("tafel", _("Tafel (Präsentation)")), ("buch", _("Buch (Notizbuch)")), ("haken", _("Haken (Formulare)")),
        ("gebaeude", _("Gebäude (Intranet)")), ("haus", _("Haus (Startseite)")), ("klammer", _("Klammer (Sonstiges)")),
    ]

    titel = models.CharField(_("Titel"), max_length=60)
    titel_en = models.CharField(_("Titel (englisch)"), max_length=60, blank=True,
                                help_text=_("Leer lassen, wenn der Titel in beiden Sprachen gleich ist."))
    beschreibung = models.CharField(_("Kurzbeschreibung"), max_length=120, blank=True)
    beschreibung_en = models.CharField(_("Kurzbeschreibung (englisch)"), max_length=120, blank=True)
    url = models.CharField(_("Adresse"), max_length=300,
                           help_text=_("Vollständige https-Adresse. Der Platzhalter {mandant} wird durch OFFICE_MANDANT aus der .env ersetzt, "
                                       "z. B. https://{mandant}.sharepoint.com; ohne OFFICE_MANDANT wird eine solche Kachel ausgeblendet."))
    symbol = models.CharField(_("Symbol"), max_length=20, choices=SYMBOLE, default="klammer")
    farbe = models.CharField(_("Farbe"), max_length=7, default="#0f6cbd", help_text=_("Hex-Farbwert, z. B. #0f6cbd."))
    reihenfolge = models.PositiveSmallIntegerField(_("Reihenfolge"), default=100)
    aktiv = models.BooleanField(_("Angezeigt"), default=True)

    class Meta:
        verbose_name = _("Office-Kachel")
        verbose_name_plural = _("Office-Kacheln")
        ordering = ["reihenfolge", "titel"]

    def __str__(self):
        return self.titel

    def clean(self):
        import re

        from django.core.exceptions import ValidationError

        if not self.url.startswith("https://"):
            raise ValidationError({"url": _("Die Adresse muss mit https:// beginnen.")})
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", self.farbe or ""):
            raise ValidationError({"farbe": _("Bitte einen Hex-Farbwert wie #0f6cbd angeben.")})

    def anzeige_titel(self, sprache):
        return self.titel_en if sprache.startswith("en") and self.titel_en else self.titel

    def anzeige_beschreibung(self, sprache):
        return self.beschreibung_en if sprache.startswith("en") and self.beschreibung_en else self.beschreibung

    def adresse(self, mandant=""):
        if "{mandant}" in self.url:
            return self.url.replace("{mandant}", mandant) if mandant else None
        return self.url
