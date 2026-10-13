from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver


@receiver(user_logged_in)
def sprache_beim_anmelden_merken(sender, request, user, **kwargs):
    """Wer noch keine Sprache gespeichert hat, behält die Sprache, in der er sich angemeldet hat."""
    from .models import Benutzereinstellung

    sprache = getattr(request, "LANGUAGE_CODE", None)
    if sprache:
        Benutzereinstellung.objects.get_or_create(benutzer=user, defaults={"sprache": sprache})
