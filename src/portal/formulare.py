from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .context import darf_portal_nutzen


class AnmeldeFormular(AuthenticationForm):
    """Anmeldung nur für Beschäftigte (Verwaltung und Lehrkräfte)."""

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not darf_portal_nutzen(user):
            raise ValidationError(_("Dieses Portal ist nur für Beschäftigte der Schule zugänglich."), code="kein_personal")
