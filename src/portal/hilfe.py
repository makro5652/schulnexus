"""
Hilfe und Dokumentation (ab 0.7.0).

Die Hilfetexte liegen als einfache Textdateien in `portal/hilfetexte/*.md` – ohne Programmierkenntnisse änderbar.
Jede Datei beginnt mit einem Kopf zwischen zwei Zeilen `---`:

    ---
    titel: Schuljahreswechsel einleiten
    art: anleitung                 grundlagen | menue | anleitung
    kurz: Ein Satz für Listen und Suche
    karte: schulleitung            nur bei art=menue: Schlüssel der Registerkarte im Menüband
    pfade: /laufbahn/, /laufbahn/wechsel/*      Seiten, auf denen dieses Thema zuerst erscheint (* = beliebig, =/ = genau)
    stichworte: Versetzung, neues Schuljahr
    reihenfolge: 10
    ---

Danach folgt der Text in einer kleinen Auszeichnung:

    ## Überschrift              ### Unterüberschrift
    - Aufzählung                1. nummerierte Schritte
    > Hinweis                   | Tabelle | mit | Spalten |
    **fett**   `Eingabe`   [[Strg]]+[[K]] (Taste)
    [Text](/pfad/)              Verweis innerhalb von Schulnexus (nur Pfade, die mit / beginnen)
    [Text](hilfe:slug)          Verweis auf ein anderes Hilfethema (öffnet in der Hilfe-Einblendung)

Alles wird zuerst maskiert; HTML in den Dateien wird also nie ausgeführt.
"""
import re
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from functools import lru_cache
from html import escape
from pathlib import Path

from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _

ORDNER = Path(__file__).resolve().parent / "hilfetexte"
ARTEN = {"grundlagen": _("Grundlagen"), "menue": _("Menüs erklärt"), "anleitung": _("Anleitungen")}
ART_REIHENFOLGE = ["grundlagen", "anleitung", "menue"]
STANDARD = "bedienung"


@dataclass
class Thema:
    slug: str
    titel: str
    art: str
    kurz: str = ""
    karte: str = ""
    pfade: list = field(default_factory=list)
    stichworte: str = ""
    reihenfolge: int = 100
    html: str = ""
    text: str = ""
    abschnitte: list = field(default_factory=list)      # [(anker, Überschrift)] für das Inhaltsverzeichnis

    @property
    def art_name(self):
        return ARTEN.get(self.art, self.art)


# ---------------------------------------------------------------- Auszeichnung → HTML

_INLINE = [
    (re.compile(r"\[\[([^\]]{1,20})\]\]"), lambda m: f"<kbd>{m.group(1)}</kbd>"),
    (re.compile(r"`([^`]+)`"), lambda m: f"<code>{m.group(1)}</code>"),
    (re.compile(r"\*\*([^*]+)\*\*"), lambda m: f"<strong>{m.group(1)}</strong>"),
]
_VERWEIS = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _verweis(m):
    text, ziel = m.group(1), m.group(2)
    if ziel.startswith("hilfe:"):
        slug = ziel[6:]
        if re.fullmatch(r"[a-z0-9-]+", slug):
            return f'<a href="{reverse("hilfe_thema", args=[slug])}" data-hilfe="{slug}">{text}</a>'
        return text
    if ziel.startswith("/") and not ziel.startswith("//"):
        return f'<a href="{ziel}">{text}</a>'
    return text                      # fremde Adressen werden nicht verlinkt


def _zeile(text):
    """Inline-Auszeichnung; der Text ist bereits maskiert."""
    for muster, ersatz in _INLINE:
        text = muster.sub(ersatz, text)
    return _VERWEIS.sub(_verweis, text)


def _anker(titel, vergeben):
    basis = re.sub(r"[^a-z0-9äöüß]+", "-", titel.lower()).strip("-") or "abschnitt"
    anker, n = basis, 2
    while anker in vergeben:
        anker, n = f"{basis}-{n}", n + 1
    vergeben.add(anker)
    return anker


def umwandeln(quelle):
    """Wandelt den Text eines Hilfethemas in HTML. Gibt (html, abschnitte) zurück."""
    aus, abschnitte, vergeben = [], [], set()
    liste = None                      # "ul" | "ol"
    innen = False                     # Unterliste (eingerückte „- “ in einem Listenpunkt) geöffnet
    absatz, tabelle = [], []

    def absatz_schliessen():
        if absatz:
            aus.append(f"<p>{_zeile(' '.join(absatz))}</p>")
            absatz.clear()

    def innen_schliessen():
        nonlocal innen
        if innen:
            aus.append("</li></ul>")
            innen = False

    def liste_schliessen():
        nonlocal liste
        innen_schliessen()
        if liste:
            aus.append(f"</li></{liste}>")
            liste = None

    def tabelle_schliessen():
        if not tabelle:
            return
        zeilen = [z for z in tabelle if not re.fullmatch(r"\|[\s:|-]+\|", z)]
        html = ['<div class="hp-tabelle"><table>']
        for i, z in enumerate(zeilen):
            zellen = [c.strip() for c in z.strip().strip("|").split("|")]
            tag = "th" if i == 0 else "td"
            html.append("<tr>" + "".join(f"<{tag}>{_zeile(c)}</{tag}>" for c in zellen) + "</tr>")
        html.append("</table></div>")
        aus.append("".join(html))
        tabelle.clear()

    def alles_schliessen():
        absatz_schliessen()
        liste_schliessen()
        tabelle_schliessen()

    for roh in quelle.splitlines():
        zeile = escape(roh.rstrip(), quote=False)
        inhalt = zeile.strip()
        if not inhalt:
            absatz_schliessen()
            tabelle_schliessen()
            continue
        if inhalt.startswith("|"):
            absatz_schliessen()
            liste_schliessen()
            tabelle.append(inhalt)
            continue
        tabelle_schliessen()
        m = re.match(r"(#{2,3}) (.+)", inhalt)
        if m:
            alles_schliessen()
            stufe, titel = len(m.group(1)), m.group(2)
            anker = _anker(titel, vergeben)
            if stufe == 2:
                abschnitte.append((anker, strip_tags(_zeile(titel))))
            aus.append(f'<h{stufe + 1} id="{anker}">{_zeile(titel)}</h{stufe + 1}>')
            continue
        if inhalt.startswith("&gt; "):
            alles_schliessen()
            aus.append(f'<p class="hp-hinweis">{_zeile(inhalt[5:])}</p>')
            continue
        m = re.match(r"(- |\d+\. )(.*)", inhalt)
        if m and liste and zeile.startswith("  ") and m.group(1) == "- ":    # Unterpunkt
            if not innen:
                aus.append("<ul><li>")
                innen = True
            else:
                aus.append("</li><li>")
            aus.append(_zeile(m.group(2)))
            continue
        if m and not zeile.startswith("  "):
            absatz_schliessen()
            art = "ul" if m.group(1) == "- " else "ol"
            if liste != art:
                liste_schliessen()
                aus.append(f"<{art}><li>")
                liste = art
            else:
                innen_schliessen()
                aus.append("</li><li>")
            aus.append(_zeile(m.group(2)))
            continue
        if liste and zeile.startswith("  "):          # Fortsetzung eines Listenpunkts
            aus.append(" " + _zeile(inhalt))
            continue
        liste_schliessen()
        absatz.append(inhalt)
    alles_schliessen()
    return "\n".join(aus), abschnitte


# ---------------------------------------------------------------- Dateien lesen

def _lesen(pfad):
    text = pfad.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{pfad.name}: Kopf mit --- fehlt")
    kopf_text, _trenner, inhalt = text[4:].partition("\n---\n")
    kopf = {}
    for zeile in kopf_text.splitlines():
        if ":" in zeile:
            k, v = zeile.split(":", 1)
            kopf[k.strip()] = v.strip()
    html, abschnitte = umwandeln(inhalt)
    return Thema(
        slug=pfad.stem, titel=kopf.get("titel", pfad.stem), art=kopf.get("art", "anleitung"), kurz=kopf.get("kurz", ""),
        karte=kopf.get("karte", ""), pfade=[p.strip() for p in kopf.get("pfade", "").split(",") if p.strip()],
        stichworte=kopf.get("stichworte", ""), reihenfolge=int(kopf.get("reihenfolge", "100") or 100),
        html=html, text=re.sub(r"\s+", " ", strip_tags(html)).strip(), abschnitte=abschnitte,
    )


@lru_cache(maxsize=1)
def alle():
    """Alle Themen als {slug: Thema}, sortiert nach Art, Reihenfolge, Titel. Wird einmal je Prozess gelesen."""
    themen = [_lesen(p) for p in sorted(ORDNER.glob("*.md"))]
    themen.sort(key=lambda t: (ART_REIHENFOLGE.index(t.art) if t.art in ART_REIHENFOLGE else 9, t.reihenfolge, t.titel.lower()))
    return {t.slug: t for t in themen}


def gruppiert():
    themen = alle().values()
    return [(art, ARTEN[art], [t for t in themen if t.art == art]) for art in ART_REIHENFOLGE]


def thema_fuer(pfad, karte=""):
    """Passendes Thema für eine Seite: das Thema mit dem genauesten passenden Pfad, sonst das Menü der aktiven Karte."""
    bester, laenge = None, -1
    for t in alle().values():
        for muster in t.pfade:
            if muster.startswith("="):                       # genau diese Seite, z. B. =/ für die Startseite
                passt = pfad == muster[1:]
            else:                                            # diese Seite und alle darunter; * steht für beliebigen Text
                passt = fnmatchcase(pfad, muster if muster.endswith("*") else muster + "*")
            if passt and len(muster) > laenge:
                bester, laenge = t.slug, len(muster)
    if bester:
        return bester
    for t in alle().values():
        if t.art == "menue" and t.karte == karte:
            return t.slug
    return STANDARD


# ---------------------------------------------------------------- Ansichten

def _teil(request):
    return request.GET.get("teil") == "1"


@login_required
def index(request):
    return render(request, "hilfe/index_teil.html" if _teil(request) else "hilfe/index.html", {"gruppen": gruppiert()})


@login_required
def thema(request, slug):
    t = alle().get(slug)
    if t is None:
        raise Http404
    kontext = {"t": t, "inhalt": mark_safe(t.html), "gruppen": gruppiert()}  # noqa: S308 – aus maskiertem Text erzeugt
    return render(request, "hilfe/thema_teil.html" if _teil(request) else "hilfe/thema.html", kontext)


@login_required
def suchindex(request):
    """Alle Themen mit Klartext für die Suche in der Hilfe-Einblendung (einmal geladen, im Browser durchsucht)."""
    return JsonResponse({"themen": [
        {"slug": t.slug, "titel": t.titel, "art": str(t.art_name), "kurz": t.kurz, "text": f"{t.stichworte} {t.text}"}
        for t in alle().values()]})
