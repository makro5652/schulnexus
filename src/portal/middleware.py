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
