from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Benutzereinstellung(models.Model):
    """Persönliche Einstellungen je Benutzerkonto (derzeit: Sprache der Oberfläche)."""

    benutzer = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="einstellung", verbose_name=_("Benutzerkonto")
    )
    sprache = models.CharField(_("Sprache der Oberfläche"), max_length=8, choices=settings.LANGUAGES, default=settings.LANGUAGE_CODE)

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
