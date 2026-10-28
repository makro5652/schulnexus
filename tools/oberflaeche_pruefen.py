"""
Oberflächenprüfung (ab 0.4.9.3), läuft automatisch auf GitHub gegen den gestarteten Docker-Container.

Meldet sich mit mehreren Demo-Rollen an, folgt den Links ab der Startseite (je Seitentyp eine Seite, Verwaltungs-
oberfläche und Downloads ausgenommen) und prüft jede Seite am Telefon (390 px) und am Desktop (1440 px):
  - Antwort ohne Serverfehler (Status < 500),
  - keine JavaScript-Fehler,
  - am Telefon kein seitliches Überlaufen der Seite (Tabellen dürfen in ihrem eigenen Rahmen scrollen).
Bildschirmfotos landen im Ausgabeordner. Rückgabewert 1 bei Fehlern.

Aufruf:  python tools/oberflaeche_pruefen.py http://localhost:8000 ausgabe/ [Passwort]
"""
import re
import sys
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

BASIS = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"
AUSGABE = Path(sys.argv[2] if len(sys.argv) > 2 else "oberflaeche")
PASSWORT = sys.argv[3] if len(sys.argv) > 3 else "Schule-Demo-2026"
ROLLEN = ["lehrkraft", "mittelstufe", "schulleitung", "verwaltung", "foerderung", "it"]
JE_ROLLE = 40
AUSLASSEN = re.compile(r"^/(verwaltung|abmelden|static|media|sprache|design)/|/(druck|excel|notenbogen|pdf|herunterladen|datei|vorlage)/|"
                       r"\.(ics|pdf|xlsx|zip|csv)$|/loeschen/")


def muster(pfad):
    return re.sub(r"\d+", "#", pfad)


def anmelden(seite, name):
    seite.goto(BASIS + "/anmelden/")
    seite.fill("input[name=username]", name)
    seite.fill("input[name=password]", PASSWORT)
    seite.click("form:has(input[name=username]) button.knopf, form:has(input[name=username]) button[type=submit]:not([name=sprache])")
    seite.wait_for_load_state("networkidle")
    return "/anmelden/" not in seite.url


def main():
    AUSGABE.mkdir(parents=True, exist_ok=True)
    fehler, geprueft = [], 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for rolle in ROLLEN:
            telefon = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True).new_page()
            desktop = browser.new_context(viewport={"width": 1440, "height": 950}).new_page()
            js = []
            for s in (telefon, desktop):
                s.on("pageerror", lambda e, js=js: js.append(str(e)))
            if not (anmelden(telefon, rolle) and anmelden(desktop, rolle)):
                fehler.append(f"{rolle}: Anmeldung fehlgeschlagen")
                continue
            gesehen, q, n = set(), deque(["/"]), 0
            while q and n < JE_ROLLE:
                pfad = q.popleft()
                if muster(pfad) in gesehen:
                    continue
                gesehen.add(muster(pfad))
                n += 1
                for s, art in ((telefon, "telefon"), (desktop, "desktop")):
                    js.clear()
                    antwort = s.goto(BASIS + pfad)
                    s.wait_for_load_state("networkidle")
                    status = antwort.status if antwort else 0
                    if status >= 500:
                        fehler.append(f"{rolle} {art} {pfad}: Status {status}")
                    if js:
                        fehler.append(f"{rolle} {art} {pfad}: JavaScript-Fehler {js[:2]}")
                    if art == "telefon":
                        breite = s.evaluate("document.documentElement.scrollWidth")
                        if breite > 392:
                            fehler.append(f"{rolle} telefon {pfad}: Seite {breite} px breit (seitliches Überlaufen)")
                    geprueft += 1
                if n <= 8:
                    name = re.sub(r"[^a-z0-9]+", "_", pfad.strip("/")) or "start"
                    telefon.screenshot(path=str(AUSGABE / f"{rolle}_{name}_390.png"), full_page=True)
                for href in desktop.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))"):
                    ziel = urlparse(urljoin(BASIS + pfad, href))
                    if ziel.netloc != urlparse(BASIS).netloc or AUSLASSEN.search(ziel.path):
                        continue
                    if muster(ziel.path) not in gesehen:
                        q.append(ziel.path)
            print(f"{rolle}: {n} Seiten geprüft", flush=True)
        browser.close()
    print(f"\n{geprueft} Seitenaufrufe, {len(fehler)} Befund(e)")
    for f in fehler:
        print("  -", f)
    (AUSGABE / "befunde.txt").write_text("\n".join(fehler) + "\n", encoding="utf-8")
    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
