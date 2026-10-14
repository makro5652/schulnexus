"""
Elternkommunikation: Nachrichten der Schule an Eltern, Antworten der Eltern, Lese- und Empfangsbestätigungen
(z. B. für Zeugnisse) sowie automatische Benachrichtigungen bei Fehlzeiten und Verspätungen.

Zustellung: E-Mail mit einem persönlichen, befristeten Link (ohne Elternkonto). Ein Elternportal mit eigener
Anmeldung ist vorbereitet und standardmäßig abgeschaltet (ELTERNPORTAL_AKTIV).
"""
import secrets

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords

from stammdaten.models import Person, Schuelerprofil


def neuer_schluessel():
    return secrets.token_urlsafe(18)


class Gespraech(models.Model):
    """Ein Nachrichtenverlauf zwischen Schule und den Eltern einer Schülerin / eines Schülers."""

    NACHRICHT = "nachricht"
    ZEUGNIS = "zeugnis"
    FEHLZEITEN = "fehlzeiten"
    ARTEN = [(NACHRICHT, _("Nachricht")), (ZEUGNIS, _("Zeugnisempfang")), (FEHLZEITEN, _("Fehlzeiten (automatisch)"))]

    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="elterngespraeche",
                                 verbose_name=_("Schüler:in"))
    art = models.CharField(_("Art"), max_length=12, choices=ARTEN, default=NACHRICHT)
    betreff = models.CharField(_("Betreff"), max_length=200, blank=True)
    # Automatische Nachrichten werden in der Sprache der Leserin / des Lesers aus einer Vorlage erzeugt.
    vorlage = models.CharField(_("Textvorlage"), max_length=20, blank=True, editable=False)
    daten = models.JSONField(_("Daten der Vorlage"), default=dict, blank=True, editable=False)
    bestaetigung_erbeten = models.BooleanField(_("Lese-/Empfangsbestätigung erbeten"), default=False)
    antworten_erlaubt = models.BooleanField(_("Eltern dürfen antworten"), default=True)
    abgeschlossen = models.BooleanField(_("Abgeschlossen"), default=False,
                                        help_text=_("Abgeschlossene Gespräche nehmen keine Antworten mehr an."))
    zeugnis = models.ForeignKey("zeugnisse.Zeugnis", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="empfangsanfragen", verbose_name=_("Zeugnis"))
    erstellt_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="+", verbose_name=_("Begonnen von"))
    erstellt_am = models.DateTimeField(_("Begonnen am"), auto_now_add=True)
    letzte_aktivitaet = models.DateTimeField(_("Letzte Aktivität"), default=timezone.now)
    eltern_antwort_am = models.DateTimeField(_("Letzte Elternantwort"), null=True, blank=True)
    schule_gelesen_am = models.DateTimeField(_("Von der Schule zuletzt gelesen"), null=True, blank=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Elterngespräch"))

    class Meta:
        verbose_name = _("Elternnachricht")
        verbose_name_plural = _("Elternnachrichten")
        ordering = ["-letzte_aktivitaet"]

    def __str__(self):
        return f"{self.titel()} – {self.schueler}"

    def titel(self):
        if self.vorlage:
            from .texte import betreff_aus_vorlage

            return betreff_aus_vorlage(self.vorlage, self.daten)
        return self.betreff

    @property
    def ungelesen(self):
        """Neue Elternantwort, die in der Schule noch niemand geöffnet hat."""
        return bool(self.eltern_antwort_am and (not self.schule_gelesen_am or self.eltern_antwort_am > self.schule_gelesen_am))

    @property
    def nimmt_antworten_an(self):
        return self.antworten_erlaubt and not self.abgeschlossen


class Empfaenger(models.Model):
    """Ein Elternteil / eine Kontaktperson als Empfänger:in eines Gesprächs – mit Zustell-, Lese- und Bestätigungsstatus."""

    WARTET = "wartet"
    VERSENDET = "versendet"
    FEHLER = "fehler"
    OHNE_EMAIL = "ohne_email"
    STATUS = [(WARTET, _("im Postausgang")), (VERSENDET, _("per E-Mail versendet")), (FEHLER, _("Versand fehlgeschlagen")),
              (OHNE_EMAIL, _("keine E-Mail-Adresse"))]
    WEGE = [("link", _("über den Link")), ("portal", _("im Elternportal")), ("schule", _("von der Schule vermerkt"))]

    gespraech = models.ForeignKey(Gespraech, on_delete=models.CASCADE, related_name="empfaenger", verbose_name=_("Gespräch"))
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="elternnachrichten", verbose_name=_("Empfänger:in"))
    beziehung = models.CharField(_("Beziehung"), max_length=20, blank=True)
    email = models.EmailField(_("E-Mail (beim Versand)"), blank=True)
    schluessel = models.CharField(_("Schlüssel des Links"), max_length=40, default=neuer_schluessel, editable=False)
    versand_status = models.CharField(_("Zustellung"), max_length=12, choices=STATUS, default=WARTET)
    versendet_am = models.DateTimeField(_("Zuletzt versendet"), null=True, blank=True)
    versand_fehler = models.CharField(_("Fehlermeldung"), max_length=300, blank=True)
    gelesen_am = models.DateTimeField(_("Geöffnet am"), null=True, blank=True)
    bestaetigt_am = models.DateTimeField(_("Bestätigt am"), null=True, blank=True)
    bestaetigt_ueber = models.CharField(_("Bestätigt"), max_length=8, choices=WEGE, blank=True)
    bestaetigung_vermerkt_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                                  related_name="+", verbose_name=_("Vermerkt von"))
    bestaetigung_notiz = models.CharField(_("Vermerk"), max_length=200, blank=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Empfänger:in"))

    class Meta:
        verbose_name = _("Empfänger:in")
        verbose_name_plural = _("Empfänger:innen")
        unique_together = [("gespraech", "person")]
        ordering = ["person__nachname", "person__vorname"]

    def __str__(self):
        return f"{self.person} · {self.gespraech_id}"

    def link_erneuern(self):
        """Macht alle bisherigen Links dieser Empfängerin / dieses Empfängers ungültig."""
        self.schluessel = neuer_schluessel()
        self.save(update_fields=["schluessel"])

    def bestaetigen(self, ueber, benutzer=None, notiz=""):
        if self.bestaetigt_am:
            return False
        self.bestaetigt_am = timezone.now()
        self.bestaetigt_ueber = ueber
        self.bestaetigung_vermerkt_von = benutzer
        self.bestaetigung_notiz = notiz[:200]
        if not self.gelesen_am and ueber != "schule":
            self.gelesen_am = self.bestaetigt_am
        self.save()
        return True


class Beitrag(models.Model):
    """Eine einzelne Nachricht im Verlauf – von der Schule, von Eltern oder automatisch."""

    WEGE = [("schule", _("Schule")), ("link", _("Eltern (Link)")), ("portal", _("Eltern (Portal)")), ("system", _("automatisch"))]

    gespraech = models.ForeignKey(Gespraech, on_delete=models.CASCADE, related_name="beitraege", verbose_name=_("Gespräch"))
    text = models.TextField(_("Text"), blank=True)
    vorlage = models.CharField(_("Textvorlage"), max_length=20, blank=True, editable=False)
    daten = models.JSONField(_("Daten der Vorlage"), default=dict, blank=True, editable=False)
    von_benutzer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="+", verbose_name=_("Von (Schule)"))
    von_person = models.ForeignKey(Person, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                   verbose_name=_("Von (Eltern)"))
    ueber = models.CharField(_("Weg"), max_length=8, choices=WEGE, default="schule")
    erstellt_am = models.DateTimeField(_("Geschrieben am"), default=timezone.now)

    class Meta:
        verbose_name = _("Beitrag")
        verbose_name_plural = _("Beiträge")
        ordering = ["erstellt_am", "pk"]

    def __str__(self):
        return (self.text or self.vorlage)[:60]

    @property
    def von_eltern(self):
        return self.ueber in ("link", "portal")

    def anzeigetext(self):
        """Text in der aktiven Sprache (Vorlagen werden übersetzt, freie Texte bleiben, wie sie geschrieben wurden)."""
        if self.vorlage:
            from .texte import text_aus_vorlage

            return text_aus_vorlage(self.vorlage, self.daten)
        return self.text

    def absender(self):
        if self.ueber == "system":
            from django.utils.translation import gettext

            return gettext("Schulverwaltung (automatisch)")
        if self.von_person_id:
            return self.von_person.anzeigename
        if self.von_benutzer_id:
            person = getattr(self.von_benutzer, "person", None)
            return person.anzeigename if person else self.von_benutzer.get_username()
        return ""


class Benachrichtigungsregel(models.Model):
    """Ab einer Schwelle an Fehlzeiten oder Verspätungen werden die Eltern automatisch benachrichtigt."""

    MERKMALE = [
        ("fehltage", _("Fehltage (ganztägig)")),
        ("fehlstunden", _("Fehlstunden (einschließlich ganzer Tage)")),
        ("verspaetungen", _("Verspätungen (Anzahl)")),
        ("verspaetungsminuten", _("Verspätungen (Minuten insgesamt)")),
    ]
    ZAEHLUNGEN = [
        ("alle", _("alle")),
        ("nicht_entschuldigt", _("nicht entschuldigte (offen oder unentschuldigt)")),
        ("unentschuldigt", _("nur unentschuldigte")),
    ]
    ZEITRAEUME = [("halbjahr", _("je Halbjahr")), ("schuljahr", _("je Schuljahr"))]

    name = models.CharField(_("Bezeichnung"), max_length=120)
    merkmal = models.CharField(_("Was wird gezählt?"), max_length=20, choices=MERKMALE)
    zaehlung = models.CharField(_("Welche Einträge?"), max_length=20, choices=ZAEHLUNGEN, default="alle")
    schwelle = models.PositiveSmallIntegerField(_("Ab (Schwelle)"), validators=[MinValueValidator(1)])
    zeitraum = models.CharField(_("Zeitraum"), max_length=10, choices=ZEITRAEUME, default="halbjahr")
    jahrgang_von = models.PositiveSmallIntegerField(_("Jahrgang von"), null=True, blank=True)
    jahrgang_bis = models.PositiveSmallIntegerField(_("Jahrgang bis"), null=True, blank=True)
    wiederholen = models.BooleanField(
        _("Bei jedem weiteren Vielfachen erneut benachrichtigen"), default=False,
        help_text=_("z. B. Schwelle 5: Nachricht bei 5, 10, 15 … – sonst nur einmal je Zeitraum."))
    bestaetigung_erbeten = models.BooleanField(_("Kenntnisnahme durch die Eltern erbitten"), default=True)
    zusatztext = models.TextField(_("Ergänzender Text der Schule"), blank=True,
                                  help_text=_("Wird unter die automatische Nachricht gesetzt, z. B. Hinweis auf die Schulordnung."))
    aktiv = models.BooleanField(_("Aktiv"), default=True)
    erstellt_von = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                     related_name="+", verbose_name=_("Angelegt von"))
    geaendert_am = models.DateTimeField(_("Geändert am"), auto_now=True)
    history = HistoricalRecords(verbose_name=_("Änderungsprotokoll Benachrichtigungsregel"))

    class Meta:
        verbose_name = _("Benachrichtigungsregel")
        verbose_name_plural = _("Benachrichtigungsregeln (Fehlzeiten)")
        ordering = ["-aktiv", "jahrgang_von", "merkmal", "schwelle"]

    def __str__(self):
        return self.name

    def gilt_fuer(self, jahrgang):
        if self.jahrgang_von is None and self.jahrgang_bis is None:
            return True
        if jahrgang is None:
            return False
        return (self.jahrgang_von or 0) <= jahrgang <= (self.jahrgang_bis or 99)

    def jahrgaenge(self):
        """Menge der Jahrgänge oder None (= alle)."""
        if self.jahrgang_von is None and self.jahrgang_bis is None:
            return None
        return set(range(self.jahrgang_von or 1, (self.jahrgang_bis or 13) + 1))

    def jahrgangstext(self):
        from django.utils.translation import gettext

        if self.jahrgang_von is None and self.jahrgang_bis is None:
            return gettext("alle Jahrgänge")
        if self.jahrgang_von == self.jahrgang_bis:
            return gettext("Jahrgang %(j)s") % {"j": self.jahrgang_von}
        return gettext("Jahrgänge %(von)s–%(bis)s") % {"von": self.jahrgang_von or 1, "bis": self.jahrgang_bis or 13}


class Ausloesung(models.Model):
    """Protokoll: Regel hat für eine Schülerin / einen Schüler in einem Zeitraum ausgelöst (verhindert Doppelversand)."""

    regel = models.ForeignKey(Benachrichtigungsregel, on_delete=models.CASCADE, related_name="ausloesungen", verbose_name=_("Regel"))
    schueler = models.ForeignKey(Schuelerprofil, on_delete=models.CASCADE, related_name="fehlzeiten_ausloesungen",
                                 verbose_name=_("Schüler:in"))
    zeitraum = models.CharField(_("Zeitraum"), max_length=30)
    stufe = models.PositiveSmallIntegerField(_("Stufe"), default=1, help_text=_("1 = Schwelle erreicht, 2 = doppelte Schwelle …"))
    wert = models.PositiveIntegerField(_("Wert beim Auslösen"))
    ausgeloest_am = models.DateTimeField(_("Ausgelöst am"), auto_now_add=True)
    still = models.BooleanField(_("Ohne Nachricht"), default=False,
                                help_text=_("Schwelle war beim Anlegen der Regel bereits überschritten; es wurde nichts versendet."))
    gespraech = models.ForeignKey(Gespraech, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
                                  verbose_name=_("Nachricht"))

    class Meta:
        verbose_name = _("Auslösung")
        verbose_name_plural = _("Auslösungen")
        unique_together = [("regel", "schueler", "zeitraum", "stufe")]
        ordering = ["-ausgeloest_am"]

    def __str__(self):
        return f"{self.regel} · {self.schueler} · {self.wert}"
