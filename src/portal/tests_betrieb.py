"""Betrieb hinter Tailscale (Unraid): Hostnamen und CSRF-Prüfung bei Aufruf über Tailnet-Adressen."""
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings

from config.settings import env_list


class TailnetZugriffTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("verw", password="Test-Passwort-123", is_staff=True)

    def anmelden(self, host, origin):
        c = Client(enforce_csrf_checks=True, HTTP_HOST=host)
        r = c.get("/anmelden/")
        self.assertEqual(r.status_code, 200)
        token = r.cookies["csrftoken"].value
        return c.post("/anmelden/", {"username": "verw", "password": "Test-Passwort-123", "csrfmiddlewaretoken": token},
                      HTTP_ORIGIN=origin)

    @override_settings(ALLOWED_HOSTS=["*"], CSRF_TRUSTED_ORIGINS=[])
    def test_http_ueber_tailscale_name_und_ip(self):
        for host in ("tower:8010", "tower.tail1234.ts.net:8010", "100.101.102.103:8010", "192.168.1.20:8010"):
            r = self.anmelden(host, f"http://{host}")
            self.assertEqual(r.status_code, 302, host)

    @override_settings(ALLOWED_HOSTS=["*"], CSRF_TRUSTED_ORIGINS=[])
    def test_fremde_herkunft_wird_abgewiesen(self):
        self.assertEqual(self.anmelden("tower:8010", "http://boese.example").status_code, 403)

    @override_settings(ALLOWED_HOSTS=["*"], CSRF_TRUSTED_ORIGINS=["https://*.ts.net:8443"])
    def test_https_ueber_tailscale_serve(self):
        r = self.anmelden("tower.tail1234.ts.net:8443", "https://tower.tail1234.ts.net:8443")
        self.assertEqual(r.status_code, 302)

    def test_leere_liste(self):
        import os
        os.environ["TEST_LEER"] = ""
        self.assertEqual(env_list("TEST_LEER", "a,b"), [])
