"""Anmeldung mit zweitem Faktor und Seite „Sicherheit“ des eigenen Kontos (ab 0.4.6.0)."""
import time

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, redirect_to_login
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext, gettext_lazy as _, ngettext
from django.views.decorators.cache import never_cache

from . import anmeldeschutz, zweifaktor as Z
from .formulare import AnmeldeFormular, sperrmeldung

SITZUNG = "zweifaktor_anmeldung"
GUELTIG_SEKUNDEN = 300
VERSUCHE = 5


class CodeForm(forms.Form):
    code = forms.CharField(label=_("Code aus der App oder Ersatzcode"), max_length=20,
                           widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric",
                                                         "autofocus": True, "size": 12}))


class Anmelden(LoginView):
    """Erster Schritt: Benutzername und Passwort. Mit eingerichteter Zwei-Faktor-Anmeldung folgt der Code."""

    template_name = "portal/login.html"
    authentication_form = AnmeldeFormular

    def form_valid(self, form):
        user = form.get_user()
        if Z.ist_aktiv(user):
            self.request.session.cycle_key()
            self.request.session[SITZUNG] = {"pk": user.pk, "backend": getattr(user, "backend", ""), "zeit": time.time(),
                                              "weiter": self.get_success_url(), "versuche": 0}
            return redirect("anmelden_code")
        return super().form_valid(form)


@never_cache
def anmelden_code(request):
    daten = request.session.get(SITZUNG)
    if not daten or time.time() - daten.get("zeit", 0) > GUELTIG_SEKUNDEN:
        request.session.pop(SITZUNG, None)
        messages.error(request, gettext("Bitte melden Sie sich erneut an."))
        return redirect("login")
    user = get_user_model().objects.filter(pk=daten["pk"], is_active=True).first()
    if user is None:
        request.session.pop(SITZUNG, None)
        return redirect("login")
    form = CodeForm()
    if request.method == "POST":
        ip = anmeldeschutz.client_ip(request)
        if anmeldeschutz.gesperrt(user.get_username(), ip):
            request.session.pop(SITZUNG, None)
            messages.error(request, sperrmeldung())
            return redirect("login")
        form = CodeForm(request.POST)
        if form.is_valid():
            art = Z.code_pruefen(Z.eintrag(user), form.cleaned_data["code"])
            if art:
                weiter = daten.get("weiter") or reverse("start")
                request.session.pop(SITZUNG, None)
                login(request, user, backend=daten.get("backend") or None)
                if art == "ersatz":
                    rest = len(Z.eintrag(user).ersatzcodes)
                    messages.warning(request, ngettext(
                        "Ersatzcode verwendet – es bleibt %(n)s Ersatzcode. Neue Codes erzeugen Sie unter „Sicherheit“.",
                        "Ersatzcode verwendet – es bleiben %(n)s Ersatzcodes. Neue Codes erzeugen Sie unter „Sicherheit“.", rest) % {"n": rest})
                if not url_has_allowed_host_and_scheme(weiter, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
                    weiter = reverse("start")
                return redirect(weiter)
            anmeldeschutz.fehlversuch(user.get_username(), ip)
            daten["versuche"] = daten.get("versuche", 0) + 1
            if daten["versuche"] >= VERSUCHE:
                request.session.pop(SITZUNG, None)
                messages.error(request, gettext("Zu viele falsche Codes. Bitte melden Sie sich erneut an."))
                return redirect("login")
            request.session[SITZUNG] = daten
            form.add_error("code", gettext("Der Code stimmt nicht. Bitte den aktuellen Code der App eingeben."))
    return render(request, "portal/login_code.html", {"form": form, "benutzer": user})


def admin_anmeldung(request, extra_context=None):
    """Die Anmeldeseite der Verwaltungsoberfläche führt immer über die eigene Anmeldung (mit zweitem Faktor)."""
    if request.user.is_authenticated:
        return redirect(request.GET.get("next") or "admin:index")
    return redirect_to_login(request.GET.get("next") or reverse("admin:index"))


# ---------------------------------------------------------------- Seite „Sicherheit“

@login_required
@never_cache
def sicherheit(request):
    user = request.user
    z = Z.eintrag(user)
    neue_codes, geheimnis, qr = None, None, None
    form = CodeForm()
    if request.method == "POST":
        aktion = request.POST.get("aktion")
        if aktion == "beginnen":
            geheimnis = Z.einrichten_beginnen(z)
        elif aktion == "bestaetigen":
            form = CodeForm(request.POST)
            if form.is_valid():
                neue_codes = Z.einrichten_bestaetigen(z, form.cleaned_data["code"])
                if neue_codes:
                    form = CodeForm()
                    _protokoll(user, gettext("Zwei-Faktor-Anmeldung eingerichtet"))
                    messages.success(request, gettext("Die Zwei-Faktor-Anmeldung ist eingerichtet."))
                else:
                    form.add_error("code", gettext("Der Code stimmt nicht. Bitte die Uhrzeit des Telefons prüfen."))
                    geheimnis = Z.geheimnis_von(z)
        elif aktion in ("ersatzcodes", "abschalten"):
            form = CodeForm(request.POST)
            if form.is_valid() and Z.code_pruefen(z, form.cleaned_data["code"]):
                if aktion == "ersatzcodes":
                    neue_codes = Z.ersatzcodes_erzeugen(z)
                    form = CodeForm()
                    messages.success(request, gettext("Neue Ersatzcodes erzeugt; die bisherigen gelten nicht mehr."))
                elif z.pflicht:
                    messages.error(request, gettext("Die Zwei-Faktor-Anmeldung ist für Ihr Konto verpflichtend."))
                else:
                    Z.abschalten(z)
                    _protokoll(user, gettext("Zwei-Faktor-Anmeldung abgeschaltet"))
                    messages.success(request, gettext("Die Zwei-Faktor-Anmeldung ist abgeschaltet."))
                    return redirect("sicherheit")
            else:
                form.add_error("code", gettext("Der Code stimmt nicht."))
        else:
            return redirect("sicherheit")
        z.refresh_from_db()
    if geheimnis:
        qr = Z.qr_svg(Z.uri(geheimnis, user))
    return render(request, "portal/sicherheit.html", {
        "z": z, "form": form, "geheimnis": geheimnis, "geheimnis_gruppen": " ".join(geheimnis[i:i + 4] for i in range(0, len(geheimnis), 4)) if geheimnis else "",
        "qr": qr, "neue_codes": neue_codes, "pflicht_offen": z.pflicht and not z.aktiv, "ersatz_rest": len(z.ersatzcodes or []),
    })


def _protokoll(user, text):
    from sicherung.models import Protokoll

    Protokoll.schreiben(user, "zweifaktor", f"{user.get_username()}: {text}")


class ZweifaktorPflichtMiddleware:
    """Konten mit angeordneter Zwei-Faktor-Anmeldung dürfen erst nach der Einrichtung weiterarbeiten."""

    FREI = ("/konto/sicherheit/", "/abmelden/", "/anmelden/", "/static/", "/sprache/", "/design/", "/gesundheit/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and not request.path.startswith(self.FREI) and Z.muss_einrichten(user):
            messages.info(request, gettext("Für Ihr Konto ist die Zwei-Faktor-Anmeldung vorgeschrieben. Bitte richten Sie sie jetzt ein."))
            return redirect("sicherheit")
        return self.get_response(request)
