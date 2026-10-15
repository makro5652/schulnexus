from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.utils.translation import gettext, gettext_lazy as _

from .context import darf_portal_nutzen


def sperrmeldung():
    return gettext("Zu viele fehlgeschlagene Anmeldeversuche. Bitte warten Sie %(min)s Minuten und versuchen Sie es dann "
             "erneut.") % {"min": settings.ANMELDUNG_SPERRE_MINUTEN}


class AnmeldeFormular(AuthenticationForm):
    """Anmeldung für Beschäftigte – und für Eltern nur, wenn das Elternportal eingeschaltet ist (ELTERNPORTAL_AKTIV).
    Nach zu vielen Fehlversuchen ist die Anmeldung vorübergehend gesperrt (portal/anmeldeschutz.py)."""

    def clean(self):
        from . import anmeldeschutz as A

        name = self.cleaned_data.get("username")
        ip = A.client_ip(self.request) if self.request is not None else None
        if name is not None and A.gesperrt(name, ip):
            raise ValidationError(sperrmeldung(), code="gesperrt")
        try:
            return super().clean()
        except ValidationError as fehler:
            if any(getattr(e, "code", None) == "invalid_login" for e in fehler.error_list):
                A.fehlversuch(name, ip)
            raise

    def confirm_login_allowed(self, user):
        from .middleware import NurPersonalMiddleware

        super().confirm_login_allowed(user)
        if not darf_portal_nutzen(user) and not NurPersonalMiddleware.elternkonto(user):
            raise ValidationError(_("Dieses Portal ist nur für Beschäftigte der Schule zugänglich."), code="kein_personal")
