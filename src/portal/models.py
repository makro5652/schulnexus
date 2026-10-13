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
