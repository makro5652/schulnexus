from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver


@receiver(user_logged_in)
def sprache_beim_anmelden_merken(sender, request, user, **kwargs):
    """Wer noch keine Einstellungen gespeichert hat, behält Sprache und Design, mit denen er sich angemeldet hat."""
    from .models import DESIGN_COOKIE, DESIGNS, Benutzereinstellung

    if request is None:
        return
    vorgaben = {}
    sprache = getattr(request, "LANGUAGE_CODE", None)
    if sprache:
        vorgaben["sprache"] = sprache
    design = request.COOKIES.get(DESIGN_COOKIE)
    if design in dict(DESIGNS):
        vorgaben["design"] = design
    if vorgaben:
        Benutzereinstellung.objects.get_or_create(benutzer=user, defaults=vorgaben)
