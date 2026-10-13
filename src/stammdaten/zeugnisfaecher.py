"""Vorschlag für Zeugnisrolle und Zeugnisspalte eines Fachs anhand seiner (deutschen) Bezeichnung."""

# (Wortbestandteile, Rolle, Spalte) – Spalte 1 = links (Sprachen, Gesellschaft, Religion), 2 = rechts (MINT, Künste, Sport)
REGELN = [
    (("mathematik",), "mathematik", 2),
    (("englisch", "französisch", "franzoesisch", "spanisch", "latein", "kiswahili", "swahili", "chinesisch", "italienisch",
      "portugiesisch", "russisch", "arabisch", "fremdsprache", "landessprache"), "fremdsprache", 1),
    (("deutsch",), "deutsch", 1),
    (("kunst", "musik", "sport", "darstellendes spiel", "theater"), "musisch", 2),
    (("religion", "ethik", "philosophie"), "religion", 1),
    (("biologie", "chemie", "physik", "informatik", "naturwissenschaft", "technik"), "sonstiges", 2),
    (("geschichte", "geographie", "erdkunde", "politik", "sozialkunde", "wirtschaft", "gesellschaft"), "sonstiges", 1),
]


def vorschlag(name):
    n = (name or "").lower()
    for woerter, rolle, spalte in REGELN:
        if any(w in n for w in woerter):
            # „Deutsch als Fremdsprache“ o. Ä. bleibt Fremdsprache; reines „Deutsch“ ist Deutsch
            if rolle == "deutsch" and n.strip() != "deutsch":
                continue
            return rolle, spalte
    return None


def faecher_einordnen(faecher):
    """Setzt Rolle und Spalte für Fächer, die noch auf der Voreinstellung stehen. Gibt die Anzahl zurück."""
    n = 0
    for f in faecher:
        if f.zeugnisrolle != "sonstiges" or f.zeugnisspalte != 1:
            continue
        v = vorschlag(f.name)
        if v and (v[0], v[1]) != ("sonstiges", 1):
            f.zeugnisrolle, f.zeugnisspalte = v
            f.save(update_fields=["zeugnisrolle", "zeugnisspalte"])
            n += 1
    return n
