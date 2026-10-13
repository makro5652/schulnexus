from django.utils import translation


class BenutzerspracheMiddleware:
    """
    Aktiviert für angemeldete Personen die gespeicherte Sprache – unabhängig von Browser oder Gerät.
    Nicht angemeldete Personen (Anmeldeseite) erhalten die Sprache aus Cookie bzw. Browser.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            einstellung = getattr(user, "einstellung", None)
            if einstellung and einstellung.sprache != getattr(request, "LANGUAGE_CODE", None):
                translation.activate(einstellung.sprache)
                request.LANGUAGE_CODE = einstellung.sprache
        return self.get_response(request)


class NurPersonalMiddleware:
    """
    Das Portal ist ausschließlich für Beschäftigte (Verwaltung und Lehrkräfte).
    Andere angemeldete Konten – etwa spätere Eltern- oder Schülerkonten – werden abgemeldet.
    """

    FREI = ("/anmelden/", "/abmelden/", "/sprache/", "/design/", "/gesundheit/", "/static/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.contrib import messages
        from django.contrib.auth import logout
        from django.shortcuts import redirect
        from django.utils.translation import gettext

        from .context import darf_portal_nutzen

        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and not darf_portal_nutzen(user) \
                and not request.path.startswith(self.FREI):
            logout(request)
            messages.error(request, gettext("Dieses Portal ist nur für Beschäftigte der Schule zugänglich."))
            return redirect("login")
        return self.get_response(request)
