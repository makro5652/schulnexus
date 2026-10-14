from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .context import darf_portal_nutzen


class AnmeldeFormular(AuthenticationForm):
    """Anmeldung für Beschäftigte – und für Eltern nur, wenn das Elternportal eingeschaltet ist (ELTERNPORTAL_AKTIV)."""

    def confirm_login_allowed(self, user):
        from .middleware import NurPersonalMiddleware

        super().confirm_login_allowed(user)
        if not darf_portal_nutzen(user) and not NurPersonalMiddleware.elternkonto(user):
            raise ValidationError(_("Dieses Portal ist nur für Beschäftigte der Schule zugänglich."), code="kein_personal")
