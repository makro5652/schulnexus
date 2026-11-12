"""Tests: Name Schulnexus (ab 0.4.9.1; zuvor „Schulverwaltung“, 0.4.9.0 „edunex“) – Name in Oberfläche, Verwaltung, Kalender, Sicherungen und Docker-Dateien."""
import io
import json
import zipfile
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from config.version import VERSION
from portal import krypto
from sicherung import archiv
from sicherung.tests import Grundlage

PROJEKT = Path(settings.BASE_DIR).parent


class NameOhneAnmeldungTest(TestCase):
    def test_anmeldeseite_traegt_den_namen(self):
        r = self.client.get(reverse("login"))
        self.assertContains(r, "<title>")
        self.assertContains(r, "Schulnexus")
        self.assertContains(r, f"Schulnexus · Open-Source-Schulverwaltung · Version {VERSION}")
        self.assertNotContains(r, "<title>Schulverwaltung")

    def test_verwaltungsoberflaeche(self):
        from django.contrib import admin

        self.assertEqual((admin.site.site_header, admin.site.site_title), ("Schulnexus", "Schulnexus"))

    def test_version(self):
        self.assertEqual(VERSION, "0.8.0")


class NameAngemeldetTest(Grundlage):
    def test_menueband_und_titel(self):
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("start"))
        self.assertContains(r, '<strong>Schulnexus</strong>')
        self.assertContains(r, '<span class="mb-zeichen" aria-hidden="true">S</span>')

    def test_englische_oberflaeche_behaelt_den_namen(self):
        self.anmelden("lehrkraft")
        r = self.client.get(reverse("start"), HTTP_ACCEPT_LANGUAGE="en")
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        r = self.client.get(reverse("start"))
        self.assertContains(r, '<strong>Schulnexus</strong>')
        self.assertContains(r, "Schulnexus · Open-source school administration")

    def test_verwaltungsoberflaeche_angemeldet(self):
        self.anmelden("it")
        r = self.client.get(reverse("admin:index"))
        self.assertContains(r, "<strong>Schulnexus</strong>")
        self.assertContains(r, "<title>")
        self.assertIn("| Schulnexus</title>", r.content.decode().replace("\n", ""))

    def test_kalenderdatei(self):
        self.anmelden("schulleitung")
        inhalt = self.client.get(reverse("kalender_ics")).content.decode()
        self.assertIn("PRODID:-//Schulnexus//Schulkalender//DE", inhalt)
        self.assertNotIn("schulverwaltung", inhalt.lower())
        self.assertNotIn("edunex", inhalt.lower())
        self.assertIn("@schulnexus", inhalt)

    def test_neue_sicherung_hat_neues_format(self):
        s = archiv.sicherung_erstellen(["fehlzeiten"], self.sl)
        with zipfile.ZipFile(io.BytesIO(krypto.ablage_lesen(s.pfad))) as zf:
            self.assertEqual(json.loads(zf.read("manifest.json"))["format"], "schulnexus-modulsicherung")

    def test_sicherung_unter_altem_namen_bleibt_lesbar(self):
        s = archiv.sicherung_erstellen(["fehlzeiten"], self.sl)
        puffer = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(krypto.ablage_lesen(s.pfad))) as alt, zipfile.ZipFile(puffer, "w") as neu:
            for n in alt.namelist():
                daten = alt.read(n)
                if n == "manifest.json":
                    m = json.loads(daten)
                    m["format"] = "schulverwaltung-modulsicherung"
                    daten = json.dumps(m).encode()
                neu.writestr(n, daten)
        s.pfad.write_bytes(puffer.getvalue())
        krypto.ablage_verschluesseln(s.pfad)
        zf, manifest = archiv.oeffnen(s.pfad)
        zf.close()
        self.assertEqual(manifest["format"], "schulverwaltung-modulsicherung")
        self.assertIn("edunex-modulsicherung", archiv.FORMATE_FRUEHER)
        # fremdes Format weiterhin abgelehnt
        m["format"] = "etwas-anderes"
        puffer = io.BytesIO()
        with zipfile.ZipFile(puffer, "w") as neu:
            neu.writestr("manifest.json", json.dumps(m))
        s.pfad.write_bytes(puffer.getvalue())
        with self.assertRaisesMessage(archiv.SicherungFehler, "keine gültige Sicherung von Schulnexus"):
            archiv.oeffnen(s.pfad)

    def test_schluesselableitung_unveraendert(self):
        # Der feste Salt-Wert stammt aus der Zeit vor der Umbenennung; ändert er sich, wären Dateien unlesbar.
        quelle = (Path(settings.BASE_DIR) / "portal" / "krypto.py").read_text()
        self.assertIn('salt=b"schulverwaltung"', quelle)


class DockerDateienTest(TestCase):
    def test_projektname_und_vorgaben(self):
        if not (PROJEKT / "docker-compose.yml").exists():
            self.skipTest("Docker-Dateien liegen nicht neben src/")
        haupt = (PROJEKT / "docker-compose.yml").read_text()
        self.assertIn("\nname: schulnexus\n", haupt)
        self.assertIn("${DB_NAME:-schulnexus}", haupt)
        self.assertIn("\nname: schulnexus\n", (PROJEKT / "unraid" / "docker-compose.yml").read_text())
        for datei in (".env.example", "unraid/.env.example", "docker-compose.yml", "unraid/docker-compose.yml",
                      "start.sh", "unraid/einrichten.sh", "docker/sicherung.sh", "Dockerfile"):
            inhalt = (PROJEKT / datei).read_text().lower()
            self.assertNotIn("schulverwaltung", inhalt, datei)
            self.assertNotIn("edunex", inhalt, datei)

    def test_vps_dateien(self):
        if not (PROJEKT / "vps").exists():
            self.skipTest("Docker-Dateien liegen nicht neben src/")
        traefik = (PROJEKT / "vps" / "traefik.yml").read_text()
        for teil in ("traefik.enable=true", "Host(`${DOMAIN", "loadbalancer.server.port=8000", "external: true"):
            self.assertIn(teil, traefik)
        skript = (PROJEKT / "vps" / "einrichten.sh").read_text()
        for teil in ("HINTER_PROXY 1", "HTTPS 1", 'PORT "127.0.0.1:', "CSRF_TRUSTED_ORIGINS", "vps/traefik.yml"):
            self.assertIn(teil, skript)
        beispiel = (PROJEKT / ".env.example").read_text()
        for n in ("DOMAIN=", "TRAEFIK_NETZWERK=", "TRAEFIK_ENTRYPOINT=", "TRAEFIK_RESOLVER="):
            self.assertIn("\n" + n, beispiel)

    def test_traefik_im_host_netzwerk(self):
        """Traefik im Host-Netzwerk (Hostinger-Docker-Manager, ab 0.4.9.5): kein Beitritt zum Netzwerk „host“."""
        if not (PROJEKT / "vps").exists():
            self.skipTest("Docker-Dateien liegen nicht neben src/")
        host = (PROJEKT / "vps" / "traefik-host.yml").read_text()
        self.assertIn("loadbalancer.server.port=8000", host)
        self.assertNotIn("networks:", host)
        self.assertNotIn("traefik.docker.network", host)
        skript = (PROJEKT / "vps" / "einrichten.sh").read_text()
        for teil in ("{{.HostConfig.NetworkMode}}", "vps/traefik-host.yml", "COMPOSE_FILE"):
            self.assertIn(teil, skript)

    def test_vps_ohne_traefik(self):
        """Betrieb ohne vorhandenen Traefik (ab 0.4.9.4): mitgelieferter Caddy holt das Zertifikat selbst."""
        if not (PROJEKT / "vps").exists():
            self.skipTest("Docker-Dateien liegen nicht neben src/")
        caddy = (PROJEKT / "vps" / "caddy.yml").read_text()
        for teil in ("image: caddy:2", '"80:80"', '"443:443"', "./vps/Caddyfile:/etc/caddy/Caddyfile:ro", "caddy_daten:/data"):
            self.assertIn(teil, caddy)
        self.assertNotIn("traefik", caddy.lower().split("services:")[1])
        datei = (PROJEKT / "vps" / "Caddyfile").read_text()
        self.assertIn("{$DOMAIN}", datei)
        self.assertIn("reverse_proxy web:8000", datei)
        # Uploads bis zur Höchstgröße der Sicherungen dürfen nicht am Proxy scheitern
        self.assertGreaterEqual(int(datei.split("max_size")[1].split("MB")[0]), settings.SICHERUNG_UPLOAD_MAX_MB)
        skript = (PROJEKT / "vps" / "einrichten-caddy.sh").read_text()
        for teil in ("HINTER_PROXY 1", "HTTPS 1", 'PORT "127.0.0.1:8000"', "CSRF_TRUSTED_ORIGINS", "vps/caddy.yml",
                     "chmod 600 .env", "DATEN_SCHLUESSEL", "bereits belegt"):
            self.assertIn(teil, skript)
        self.assertNotIn("traefik.yml", skript)


class LeereUmgebungswerteTest(TestCase):
    """Leere Angaben in der .env („HSTS_SEKUNDEN=“) dürfen den Start nicht verhindern (Fehler 0.4.9.5, behoben 0.4.9.6)."""

    def test_einstellungen_mit_leeren_werten(self):
        import os
        import re
        import subprocess
        import sys

        quelle = (PROJEKT / ".env.example")
        if not quelle.exists():
            self.skipTest(".env.example liegt nicht neben src/")
        umgebung = {k: v for k, v in os.environ.items() if k not in ("DJANGO_SETTINGS_MODULE",)}
        for zeile in quelle.read_text().splitlines():
            m = re.match(r"^([A-Z][A-Z0-9_]*)=(.*)$", zeile)
            if m:
                umgebung[m.group(1)] = m.group(2)
        # zusätzlich jede Ganzzahl-Einstellung leer
        for n in re.findall(r'env_int\("([A-Z0-9_]+)"', (Path(settings.BASE_DIR) / "config" / "settings.py").read_text()):
            umgebung[n] = ""
        umgebung.update({"HTTPS": "1", "HINTER_PROXY": "1", "DEBUG": "0", "SECRET_KEY": "pruefung"})
        ergebnis = subprocess.run([sys.executable, "-c", "import django;from django.conf import settings;settings.DATABASES;print(settings.SECURE_HSTS_SECONDS)"],
                                  cwd=settings.BASE_DIR, env={**umgebung, "DJANGO_SETTINGS_MODULE": "config.settings"},
                                  capture_output=True, text=True, timeout=60)
        self.assertEqual(ergebnis.returncode, 0, ergebnis.stderr[-600:])
        self.assertEqual(ergebnis.stdout.strip(), "31536000")


class GitHubPruefungenTest(TestCase):
    """Die Workflow-Dateien für die automatische Prüfung (ab 0.4.9.3) sind vorhanden und vollständig."""

    def test_workflow_und_dependabot(self):
        if not (PROJEKT / ".github").exists():
            self.skipTest("Repository-Dateien liegen nicht neben src/")
        wf = (PROJEKT / ".github" / "workflows" / "pruefung.yml").read_text()
        for teil in ("manage.py test --parallel", "makemigrations --check", "ruff check", "sprachdateien.py pruefen",
                     "shellcheck", "pip-audit", "bandit", "oberflaeche_pruefen.py", "postgres:16", "docker compose up --build"):
            self.assertIn(teil, wf)
        self.assertNotIn("secrets.", wf)          # keine Geheimnisse des Betriebs nötig
        self.assertIn("pip", (PROJEKT / ".github" / "dependabot.yml").read_text())
        self.assertTrue((PROJEKT / "ruff.toml").exists())
        self.assertTrue((PROJEKT / "tools" / "oberflaeche_pruefen.py").exists())
