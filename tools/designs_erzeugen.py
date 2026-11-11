"""
Zusätzliche Designs (ab 0.6.1): erzeugt die CSS-Abschnitte für portal.css, menueband.css, verwaltung.css und zeugnis.css.

    python tools/designs_erzeugen.py            schreibt die Abschnitte zwischen die Marken in den vier Dateien
    python tools/designs_erzeugen.py pruefen    prüft nur den Kontrast und ob die Dateien aktuell sind

Die drei ursprünglichen Designs (standard, latte, mocha) stehen von Hand in den CSS-Dateien und bleiben unberührt.
Jede Palette wird auf ausreichenden Kontrast geprüft (WCAG AA: 4,5 : 1 für Text). Neue Palette: hier eintragen,
in portal/models.py (DESIGNS, DESIGN_GRUPPEN) ergänzen, Skript ausführen.

Catppuccin (Frappé, Macchiato): https://catppuccin.com, MIT-Lizenz. Nord: https://www.nordtheme.com, MIT-Lizenz.
"""
import sys
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "src" / "static"
ANFANG = "/* >>> Weitere Designs – erzeugt von tools/designs_erzeugen.py, nicht von Hand ändern */"
ENDE = "/* <<< Weitere Designs */"

# auf_akzent: Schrift auf Akzentflächen (Knöpfe); titel/titel_text: Titelleiste des Menübands;
# akzent2: Akzent beim Überfahren; grau: neutrale Knöpfe der Verwaltungsoberfläche (mit auf_akzent beschriftet)
PALETTEN = {
    "hell": dict(
        dunkel=False, grund="#f6f5f1", flaeche="#ffffff", text="#1d2327", leise="#5b6670", linie="#dfe3e6", linie2="#c9cfd4",
        akzent="#1f5f5b", akzent2="#174845", akzent_hell="#e3efed", auf_akzent="#ffffff", titel="#1f5f5b", titel_text="#ffffff",
        hover="#eef3f2", warnung="#a04520", gefahr="#fbeae5", info="#e4ecf7", info_text="#2b4f80",
        hinweis="#fbf0d9", hinweis_text="#855a0c", notiz="#4a3608", lila="#ece6f6", lila_text="#563f8c", ok="#2f7a4f", ok_fl="#e1efe9",
        grau="#5b6670", papier=("#fbf3d3", "#e1efe9", "#e3ebf5", "#f6e4e4", "#ecebe7"), muster=("#ffffff", "#1f5f5b", "#e3efed")),
    "dunkel": dict(
        dunkel=True, grund="#15191c", flaeche="#1e2428", text="#e8eaec", leise="#9aa5ae", linie="#313a40", linie2="#424d55",
        akzent="#6fbfb6", akzent2="#9fdcd5", akzent_hell="#20332f", auf_akzent="#10201e", titel="#163f3c", titel_text="#ffffff",
        hover="#263034", warnung="#f0a07a", gefahr="#3a2620", info="#22324a", info_text="#a9c6ef",
        hinweis="#3a3020", hinweis_text="#f0cd85", notiz="#f0e0bd", lila="#2f2945", lila_text="#c9bdf2", ok="#7fd1a1", ok_fl="#233530",
        grau="#9aa5ae", papier=("#3a3522", "#233530", "#232f3d", "#3b2829", "#2c2f31"), muster=("#15191c", "#6fbfb6", "#1e2428")),
    "frappe": dict(
        dunkel=True, grund="#292c3c", flaeche="#303446", text="#c6d0f5", leise="#a5adce", linie="#414559", linie2="#51576d",
        akzent="#ca9ee6", akzent2="#babbf1", akzent_hell="#443f5c", auf_akzent="#232634", titel="#232634", titel_text="#c6d0f5",
        hover="#414559", warnung="#ea999c", gefahr="#43343f", info="#343b58", info_text="#8caaee",
        hinweis="#4a4650", hinweis_text="#e5c890", notiz="#e5c890", lila="#443f5c", lila_text="#ca9ee6", ok="#a6d189", ok_fl="#3a4a48",
        grau="#949cbb", papier=("#454250", "#3a4649", "#384060", "#463f58", "#3a3d50"), muster=("#303446", "#ca9ee6", "#8caaee")),
    "macchiato": dict(
        dunkel=True, grund="#1e2030", flaeche="#24273a", text="#cad3f5", leise="#a5adcb", linie="#363a4f", linie2="#494d64",
        akzent="#c6a0f6", akzent2="#b7bdf8", akzent_hell="#3b3555", auf_akzent="#181926", titel="#181926", titel_text="#cad3f5",
        hover="#363a4f", warnung="#ed8796", gefahr="#453246", info="#2f3858", info_text="#8aadf4",
        hinweis="#423e47", hinweis_text="#eed49f", notiz="#eed49f", lila="#3b3555", lila_text="#c6a0f6", ok="#a6da95", ok_fl="#2f403f",
        grau="#939ab7", papier=("#3c3944", "#2f3b40", "#2d3554", "#3c354f", "#2f3245"), muster=("#24273a", "#c6a0f6", "#8aadf4")),
    "nord": dict(
        dunkel=True, grund="#272c36", flaeche="#2e3440", text="#eceff4", leise="#b4bccb", linie="#434c5e", linie2="#4c566a",
        akzent="#88c0d0", akzent2="#8fbcbb", akzent_hell="#37475a", auf_akzent="#1f242d", titel="#1f242d", titel_text="#eceff4",
        hover="#3b4252", warnung="#f0a3aa", gefahr="#4a3540", info="#36465c", info_text="#a3c1e0",
        hinweis="#4a4538", hinweis_text="#ebcb8b", notiz="#ebcb8b", lila="#473f54", lila_text="#d0b3cb", ok="#a3be8c", ok_fl="#3a463f",
        grau="#a0aabc", papier=("#474436", "#3a463f", "#36465c", "#4a3b46", "#3b4252"), muster=("#2e3440", "#88c0d0", "#81a1c1")),
    "ozean": dict(
        dunkel=False, grund="#f1f5f9", flaeche="#ffffff", text="#0f172a", leise="#51607a", linie="#d8e0ea", linie2="#c2cddb",
        akzent="#1d4ed8", akzent2="#1e40af", akzent_hell="#e0e9fd", auf_akzent="#ffffff", titel="#1e3a8a", titel_text="#ffffff",
        hover="#eef3fb", warnung="#b42318", gefahr="#fdecea", info="#e0f0fb", info_text="#0b5a8a",
        hinweis="#fdf3d7", hinweis_text="#854d0e", notiz="#4a3608", lila="#ede9fe", lila_text="#5b21b6", ok="#15803d", ok_fl="#dcf3e4",
        grau="#51607a", papier=("#fdf3d7", "#dcf3e4", "#e0e9fd", "#fbe4e6", "#e8edf3"), muster=("#f1f5f9", "#1d4ed8", "#1e3a8a")),
    "sepia": dict(
        dunkel=False, grund="#f1e9d8", flaeche="#fbf6ea", text="#3b2f20", leise="#6b5a45", linie="#ddd0b8", linie2="#c9b99c",
        akzent="#8a4b14", akzent2="#6f3b0e", akzent_hell="#f1e1c8", auf_akzent="#fbf6ea", titel="#5c3a17", titel_text="#fbf6ea",
        hover="#f3ebda", warnung="#a8321c", gefahr="#f6ded4", info="#e0e6e2", info_text="#2f4f63",
        hinweis="#f3e3b8", hinweis_text="#7a5200", notiz="#4a3608", lila="#eadff0", lila_text="#5f3d7a", ok="#4d6b1f", ok_fl="#e3e9cf",
        grau="#6b5a45", papier=("#f3e6bd", "#dfe6cf", "#dde3e3", "#efd9d0", "#e6dcc8"), muster=("#fbf6ea", "#8a4b14", "#ddd0b8")),
    "kontrast": dict(
        dunkel=False, grund="#ffffff", flaeche="#ffffff", text="#000000", leise="#2b2b2b", linie="#5a5a5a", linie2="#000000",
        akzent="#0033a0", akzent2="#001f66", akzent_hell="#dfe8ff", auf_akzent="#ffffff", titel="#000000", titel_text="#ffffff",
        hover="#eaf0ff", warnung="#a30000", gefahr="#ffe3e0", info="#dfe8ff", info_text="#002a80",
        hinweis="#fff1b8", hinweis_text="#5c3d00", notiz="#2b1d00", lila="#ecdcff", lila_text="#3d0a80", ok="#005a1c", ok_fl="#d9f2df",
        grau="#2b2b2b", papier=("#fff1b8", "#d9f2df", "#dfe8ff", "#ffe3e0", "#ededed"), muster=("#ffffff", "#000000", "#0033a0")),
}

# Farbpaare (Schrift, Grund), die mindestens 4,5 : 1 erreichen müssen
PAARE = [("text", "flaeche"), ("text", "grund"), ("leise", "flaeche"), ("leise", "grund"), ("akzent", "flaeche"), ("akzent", "grund"),
         ("auf_akzent", "akzent"), ("titel_text", "titel"), ("warnung", "flaeche"), ("warnung", "gefahr"), ("info_text", "info"),
         ("hinweis_text", "hinweis"), ("lila_text", "lila"), ("ok", "flaeche"), ("text", "akzent_hell"), ("akzent", "akzent_hell"),
         ("text", "hover"), ("auf_akzent", "grau"), ("notiz", "hinweis")]


def _leuchtdichte(farbe):
    werte = [int(farbe[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    r, g, b = (w / 12.92 if w <= 0.04045 else ((w + 0.055) / 1.055) ** 2.4 for w in werte)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def kontrast(a, b):
    hell, dunkel = sorted((_leuchtdichte(a), _leuchtdichte(b)), reverse=True)
    return (hell + 0.05) / (dunkel + 0.05)


def kontrast_maengel():
    maengel = []
    for name, p in PALETTEN.items():
        for vorn, hinten in PAARE:
            k = kontrast(p[vorn], p[hinten])
            if k < 4.5:
                maengel.append(f"{name}: {vorn} {p[vorn]} auf {hinten} {p[hinten]} nur {k:.2f} : 1")
        for i, papier in enumerate(p["papier"]):
            k = kontrast(p["text"], papier)
            if k < 4.5:
                maengel.append(f"{name}: text auf papier[{i}] {papier} nur {k:.2f} : 1")
    return maengel


def portal():
    zeilen = []
    for name, p in PALETTEN.items():
        g, gr, b, r, n = p["papier"]
        zeilen.append(
            f':root[data-design="{name}"] {{\n'
            f'  color-scheme: {"dark" if p["dunkel"] else "light"};\n'
            f'  --grund: {p["grund"]}; --flaeche: {p["flaeche"]}; --text: {p["text"]}; --leise: {p["leise"]}; --linie: {p["linie"]};\n'
            f'  --akzent: {p["akzent"]}; --akzent-hell: {p["akzent_hell"]}; --warnung: {p["warnung"]}; --gefahr-flaeche: {p["gefahr"]};\n'
            f'  --info-flaeche: {p["info"]}; --info-text: {p["info_text"]}; --hinweis-flaeche: {p["hinweis"]}; '
            f'--hinweis-text: {p["hinweis_text"]}; --notiz-text: {p["notiz"]};\n'
            f'  --lila-flaeche: {p["lila"]}; --lila-text: {p["lila_text"]}; --ok: {p["ok"]};\n'
            f'  --papier-gelb: {g}; --papier-gruen: {gr}; --papier-blau: {b}; --papier-rosa: {r}; --papier-grau: {n};\n'
            f'}}')
        if p["dunkel"]:
            zeilen.append(f':root[data-design="{name}"] .nv-stand.in_arbeit {{ background: {p["hinweis"]}; color: {p["hinweis_text"]}; }}')
        if name == "kontrast":
            zeilen.append(':root[data-design="kontrast"] a { text-decoration-thickness: 2px; }\n'
                          ':root[data-design="kontrast"] :focus-visible { outline: 3px solid #0033a0; outline-offset: 2px; }')
    return "\n".join(zeilen)


def menueband():
    zeilen = []
    for name, p in PALETTEN.items():
        schatten = "rgba(0, 0, 0, .4)" if p["dunkel"] else "rgba(16, 24, 32, .1)"
        zeilen.append(
            f'html[data-design="{name}"] .mb {{\n'
            f'  --mb-titel: {p["titel"]}; --mb-titel-text: {p["titel_text"]}; --mb-flaeche: {p["flaeche"]}; --mb-text: {p["text"]}; '
            f'--mb-leise: {p["leise"]}; --mb-linie: {p["linie"]};\n'
            f'  --mb-akzent: {p["akzent"]}; --mb-akzent-hell: {p["akzent_hell"]}; --mb-hover: {p["hover"]}; --mb-schatten: {schatten};\n'
            f'}}')
        if p["dunkel"]:
            zeilen.append(f'html[data-design="{name}"] .mb-zeichen {{ background: var(--mb-akzent); color: {p["auf_akzent"]}; }}')
        a, b, c = p["muster"]
        zeilen.append(f'.design-muster-{name} i:nth-child(1) {{ background: {a}; }} .design-muster-{name} i:nth-child(2) {{ background: {b}; }} '
                      f'.design-muster-{name} i:nth-child(3) {{ background: {c}; }}')
    return "\n".join(zeilen)


def verwaltung():
    zeilen = []
    for name, p in PALETTEN.items():
        zeilen.append(
            f'html[data-design="{name}"]:root {{\n'
            f'  color-scheme: {"dark" if p["dunkel"] else "light"};\n'
            f'  --primary: {p["akzent"]}; --secondary: {p["akzent"]}; --accent: {p["akzent_hell"]}; --primary-fg: {p["auf_akzent"]};\n'
            f'  --body-fg: {p["text"]}; --body-bg: {p["flaeche"]}; --body-quiet-color: {p["leise"]}; --body-medium-color: {p["text"]}; '
            f'--body-loud-color: {p["text"]};\n'
            f'  --header-color: {p["titel_text"]}; --header-branding-color: {p["titel_text"]}; --header-bg: {p["titel"]}; '
            f'--header-link-color: {p["titel_text"]};\n'
            f'  --breadcrumbs-fg: {p["leise"]}; --breadcrumbs-link-fg: {p["akzent"]}; --breadcrumbs-bg: {p["grund"]};\n'
            f'  --link-fg: {p["akzent"]}; --link-hover-color: {p["akzent2"]}; --link-selected-fg: {p["akzent"]};\n'
            f'  --hairline-color: {p["linie"]}; --border-color: {p["linie2"]};\n'
            f'  --error-fg: {p["warnung"]}; --message-success-bg: {p["ok_fl"]}; --message-warning-bg: {p["hinweis"]}; '
            f'--message-error-bg: {p["gefahr"]};\n'
            f'  --darkened-bg: {p["grund"]}; --selected-bg: {p["linie"]}; --selected-row: {p["akzent_hell"]};\n'
            f'  --button-fg: {p["auf_akzent"]}; --button-bg: {p["akzent"]}; --button-hover-bg: {p["akzent2"]}; '
            f'--default-button-bg: {p["akzent2"]}; --default-button-hover-bg: {p["akzent"]};\n'
            f'  --close-button-bg: {p["grau"]}; --close-button-hover-bg: {p["leise"]}; --delete-button-bg: {p["warnung"]}; '
            f'--delete-button-hover-bg: {p["warnung"]};\n'
            f'  --object-tools-fg: {p["auf_akzent"]}; --object-tools-bg: {p["grau"]}; --object-tools-hover-bg: {p["akzent"]};\n'
            f'}}')
    return "\n".join(zeilen)


def zeugnis():
    zeilen = ["@media screen {"]
    for name, p in PALETTEN.items():
        zeilen.append(f'  html[data-design="{name}"] body {{ background: {p["grund"]}; }}')
        zeilen.append(f'  html[data-design="{name}"] .werkzeug {{ background: {p["titel"]}; color: {p["titel_text"]}; }}')
        if p["dunkel"]:
            zeilen.append(f'  html[data-design="{name}"] .werkzeug a {{ color: {p["akzent"]}; }}')
            zeilen.append(f'  html[data-design="{name}"] .werkzeug button {{ background: {p["akzent"]}; color: {p["auf_akzent"]}; }}')
        else:
            zeilen.append(f'  html[data-design="{name}"] .werkzeug button {{ color: {p["titel"]}; }}')
    zeilen.append("}")
    return "\n".join(zeilen)


DATEIEN = {"portal.css": portal, "menueband.css": menueband, "verwaltung.css": verwaltung, "zeugnis.css": zeugnis}


def neuer_inhalt(text, abschnitt):
    block = f"{ANFANG}\n{abschnitt}\n{ENDE}"
    if ANFANG in text and ENDE in text:
        return text[:text.index(ANFANG)] + block + text[text.index(ENDE) + len(ENDE):]
    return text.rstrip("\n") + "\n\n" + block + "\n"


if __name__ == "__main__":
    maengel = kontrast_maengel()
    for m in maengel:
        print("KONTRAST:", m)
    veraltet = []
    for datei, erzeuger in DATEIEN.items():
        pfad = STATIC / datei
        alt = pfad.read_text(encoding="utf-8")
        neu = neuer_inhalt(alt, erzeuger())
        if neu != alt:
            veraltet.append(datei)
            if "pruefen" not in sys.argv[1:] and not maengel:
                pfad.write_text(neu, encoding="utf-8")
                print(f"{datei} geschrieben.")
    if "pruefen" in sys.argv[1:]:
        for d in veraltet:
            print(f"VERALTET: {d} – bitte tools/designs_erzeugen.py ausführen")
        print(f"{len(PALETTEN)} Designs geprüft.")
        sys.exit(1 if (maengel or veraltet) else 0)
    sys.exit(1 if maengel else 0)
