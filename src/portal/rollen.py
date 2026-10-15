"""
Rollen in Schulnexus (Django-Benutzergruppen) mit ihren Standardrechten.

Die Gruppennamen sind feste Schlüssel; die Anzeige erfolgt übersetzt. Rechte werden von
`manage.py grundeinrichtung` nur ergänzt, nie entfernt – Anpassungen in der Verwaltung bleiben
erhalten. `grundeinrichtung --rechte-zuruecksetzen` stellt die hier definierten Standards wieder her.

Neben den Modellrechten gibt es zeilenweise Regeln in portal/rechte.py, z. B. sieht die
Klassenleitung nur die eigene Klasse und die Stufenkoordination nur die eigene Stufe.
"""
from django.utils.translation import gettext_lazy as _

LEHRER = "Lehrer:in"
MITTELSTUFE = "Mittelstufenkoordination"
OBERSTUFE = "Oberstufenkoordination"
SCHULLEITUNG = "Schulleitung"
STELLVERTRETUNG = "Stellvertretende Schulleitung"
SEKRETARIAT = "Sekretariat"
VERWALTUNGSLEITUNG = "Verwaltungsleitung"
HR = "HR-Management"
FINANZEN = "Finanzen"
FOERDERKOORDINATION = "Förderkoordination"
SCHUELER = "Schüler:in"
ELTERN = "Eltern"
IT = "IT-Administration"

# Frühere Gruppennamen (bis Version 0.4.2.2) – werden per Migration umbenannt.
ALTE_NAMEN = {"Lehrkraft": LEHRER, "Verwaltung": SEKRETARIAT, "Personalverwaltung": HR}

ANZEIGE = {
    LEHRER: _("Lehrer:in"), MITTELSTUFE: _("Mittelstufenkoordination"), OBERSTUFE: _("Oberstufenkoordination"),
    SCHULLEITUNG: _("Schulleitung"), STELLVERTRETUNG: _("Stellvertretende Schulleitung"), SEKRETARIAT: _("Sekretariat"), VERWALTUNGSLEITUNG: _("Verwaltungsleitung"),
    HR: _("HR-Management"), FINANZEN: _("Finanzen"), FOERDERKOORDINATION: _("Förderkoordination"),
    SCHUELER: _("Schüler:in"), ELTERN: _("Eltern"), IT: _("IT-Administration"),
}

BESCHREIBUNG = {
    LEHRER: _("Eigener Unterricht mit Leistungsnachweisen, Noten und Zeugnisnoten; Zeugniskommentare der eigenen Schüler:innen "
              "lesen, abzeichnen und kommentieren. Als Klassenleitung: Zeugnisse und Kommentare der Klasse, Schülerakte, "
              "Fehlzeiten, Anhänge und Förderung der eigenen Klasse. Nachteilsausgleiche der eigenen Schüler:innen lesen."),
    MITTELSTUFE: _("Wie Lehrer:in, zusätzlich für alle Klassen der Mittelstufe: Schülerakten, Notenübersichten, Fehlzeiten, "
                   "Zeugnisse und Konferenzen (leiten, Zeugnisse freigeben), "
                   "Gesundheitshinweise, Förderpläne und Nachteilsausgleiche (bearbeiten), Schullaufbahn und Versetzungsvermerke, "
                   "Klassen und Lerngruppen der Stufe bilden und Schüler:innen zuordnen, Neuanmeldungen der Stufe bearbeiten."),
    OBERSTUFE: _("Wie Mittelstufenkoordination, bezogen auf die Jahrgänge der Oberstufe."),
    SCHULLEITUNG: _("Alle Rechte, einschließlich Genehmigung von Nachteilsausgleichen, HR-Daten und Benutzerverwaltung."),
    STELLVERTRETUNG: _("Wie Stufenkoordination für alle Jahrgänge; plant Elternsprechtage und Lern- und Entwicklungsgespräche "
                        "(Zeitraster, Teilnahme, Buchungszeitraum), pflegt Schulkalender und Räume."),
    SEKRETARIAT: _("Schüler- und Elternstammdaten, Klassen und Gruppen, Fehlzeiten, AGs, Einwilligungen, Anhänge, "
                   "Gesundheitsangaben, Neuanmeldungen einschließlich Übernahme, Zeugnisse vorbereiten und drucken. Noten, Unterrichtsverteilung, Kataloge und Personal nur lesend; keine Förderpläne, keine HR-Daten."),
    VERWALTUNGSLEITUNG: _("Wie Sekretariat, zusätzlich Schuljahre, Zeitraster, Fächer, Notenskalen, Unterrichtsverteilung, "
                          "eigene Datenfelder, Benutzerkonten und Rollen, Personal einschließlich HR-Daten, Dienstleister und Finanzen. "
                          "Keine Noteneingabe, keine Förderpläne."),
    HR: _("Personal aller Bereiche mit Dienstverhältnis, Nachweisen, Abwesenheiten, Fortbildungen und Notfallkontakten. "
          "Keine Noten, keine Gesundheits- oder Förderdaten von Schüler:innen."),
    FINANZEN: _("Rechnungsempfänger:innen und Elternstammdaten, Schülerstammdaten lesend, Dienstleister und Verträge, "
                "Anhänge der Kategorie Verwaltung, Neuanmeldungen lesen mit Checkliste, Kontakten und Unterlagen. Keine Noten, keine Förder- und Gesundheitsdaten. Ein Finanzmodul folgt später."),
    FOERDERKOORDINATION: _("Alle Förderpläne und Nachteilsausgleiche der Schule, Genehmigung, Kataloge, Schülerakten lesend."),
    SCHUELER: _("Vorbereitet für den späteren Stundenplan. Derzeit kein Zugang zum Portal."),
    ELTERN: _("Elternportal mit eigener Anmeldung (vorbereitet, standardmäßig abgeschaltet): eigene Nachrichten lesen, "
              "bestätigen und beantworten. Ohne Portal erhalten Eltern Nachrichten über persönliche Links."),
    IT: _("Administration mit Vollzugriff: alle Daten und Einstellungen, Benutzerkonten, Rollen und Einzelrechte "
          "(erteilen und entziehen), Sicherung, Wiederherstellung und PDF-Export."),
}

REIHENFOLGE = [LEHRER, MITTELSTUFE, OBERSTUFE, SCHULLEITUNG, STELLVERTRETUNG, SEKRETARIAT, VERWALTUNGSLEITUNG, HR, FINANZEN,
               FOERDERKOORDINATION, IT, SCHUELER, ELTERN]

ALLE = ("add", "change", "view", "delete")


def r(aktionen, *modelle):
    if isinstance(aktionen, str):
        aktionen = (aktionen,)
    return {f"{a}_{m}" for a in aktionen for m in modelle}


# Schulkalender, Räume, Sprechtage (App termine). Zeilenweise: Lehrkräfte nur eigene Verfügbarkeit und eigene Gespräche.
_TERMINE_LESEN = r("view", "termin", "raum", "raumbuchung", "sprechtag", "zeitfenster", "teilnahme", "gespraechstermin")
_TERMINE_LEHRER = _TERMINE_LESEN | r("add", "raumbuchung") | r("change", "teilnahme") | r(("add", "delete"), "gespraechstermin")
_TERMINE_KALENDER = r(("add", "change", "view"), "termin")
_TERMINE_VERWALTUNG = r(ALLE, "termin", "raum", "raumbuchung", "gespraechstermin") | _TERMINE_LESEN
_TERMINE_PLANUNG = r(ALLE, "termin", "raum", "raumbuchung", "sprechtag", "zeitfenster", "teilnahme", "gespraechstermin")

# ---------------------------------------------------------------- Bausteine
_LEHRER = (
    r("view", "person", "schuelerprofil", "gruppe", "mitgliedschaft", "fach", "beziehung", "unterricht", "notenskala",
      "notenstufe", "notenschluessel", "gewichtungsvorlage", "leistungskategorie", "laufbahnabschnitt", "abschluss",
      "sprachenfolge", "vorherigeschule", "elternprofil", "bildungsgang", "abschlussart", "einwilligung", "stunde",
      "agangebot", "agwahl", "agzuteilung", "foerderschwerpunkt", "ausgleichsmassnahme")
    | r(ALLE, "bewertungsordner", "leistungsnachweis") | r("view", "leistungsvorgabe")
    | r(("add", "change", "view"), "note", "zeugnisnote", "fehlzeit", "foerderplan", "foerdereintrag",
        "nachteilsausgleich", "aushaendigung")
    | r(ALLE, "foerderziel")
    | r(("add", "view"), "dokument")
    # Zeugnisse: Kommentar lesen/abzeichnen/anmerken; als Klassenleitung Zeugnis bearbeiten (zeilenweise geprüft)
    | r(("view", "change"), "zeugnis") | r(ALLE, "abzeichnung") | r(("add", "view", "change"), "anmerkung")
    | r("view", "konferenz", "beschluss", "zeugnisfachnote")
    # Elternkommunikation: an Eltern der eigenen Schüler:innen schreiben (zeilenweise geprüft, elternkontakt/rechte.py)
    | r(("add", "view"), "gespraech", "beitrag") | r("view", "empfaenger")
    | _TERMINE_LEHRER
)
# Benachrichtigungsregeln für Fehlzeiten: erweiterte Schulleitung (Koordinationen nur für ihre Jahrgänge)
_REGELN = r(ALLE, "benachrichtigungsregel") | r("view", "ausloesung")
_ELTERNKONTAKT_VERWALTUNG = r(ALLE, "gespraech", "beitrag", "empfaenger") | r("view", "benachrichtigungsregel", "ausloesung")

# Gesundheitshinweise der eigenen Stufe: zeilenweise über view_gesundheit_klasse (siehe portal/rechte.py)
_STUFE = (_LEHRER | r(("add", "change", "view"), "laufbahnabschnitt", "abschluss", "gruppe") | r(ALLE, "mitgliedschaft")
          | {"view_gesundheit_klasse", "freigeben_zeugnis"} | r(ALLE, "konferenz", "beschluss")
          | r(("view", "change"), "gespraech", "empfaenger") | _REGELN | _TERMINE_KALENDER
          # Leistungsvorgaben (Pflichtnoten mit Frist) für die koordinierten Jahrgänge, zeilenweise in noten/rechte.py
          | r(ALLE, "leistungsvorgabe"))

_SCHUELERDATEN = r(ALLE, "person", "schuelerprofil", "elternprofil", "beziehung", "gruppe", "mitgliedschaft", "einwilligung",
                   "dokument", "laufbahnabschnitt", "abschluss", "vorherigeschule", "sprachenfolge", "gesundheitsangaben",
                   "fehlzeit", "agangebot", "agwahl", "agzuteilung") | {"view_gesundheitsangaben"}
_KATALOGE = ("schuljahr", "abschnitt", "fach", "bildungsgang", "abschlussart", "stunde", "unterricht", "notenskala",
             "notenstufe", "notenschluessel", "gewichtungsvorlage", "leistungskategorie", "zusatzfeld", "personalbereich")
_NOTEN_LESEN = r("view", "leistungsnachweis", "note", "zeugnisnote", "bewertungsordner", "leistungsvorgabe")
_HR = r(ALLE, "personalprofil", "personalbereich", "dienstleister", "nachweisart", "nachweis", "personalabwesenheit",
        "fortbildung", "notfallkontakt", "dokument") | r(("add", "change", "view"), "person", "zusatzfeld") | {"view_hr_daten", "view_fach"}

# Neuanmeldungen (App aufnahme). Zeilenweise: Stufenkoordination nur Anmeldungen ihrer Jahrgänge (aufnahme/rechte.py).
_AUFNAHME_MODELLE = ("anmeldung", "anmeldekontakt", "anmeldedatei", "anmeldepunkt")
_AUFNAHME_VOLL = r(ALLE, *_AUFNAHME_MODELLE, "checklistenvorlage", "vorlagenpunkt") | {"uebernehmen_anmeldung"}
_AUFNAHME_STUFE = (r(("add", "change", "view"), "anmeldung", "anmeldekontakt") | r(ALLE, "anmeldedatei", "anmeldepunkt")
                   | r("view", "checklistenvorlage", "vorlagenpunkt"))
_AUFNAHME_FINANZEN = (r("view", *_AUFNAHME_MODELLE, "checklistenvorlage", "vorlagenpunkt")
                      | r("change", "anmeldekontakt", "anmeldepunkt") | r("add", "anmeldedatei"))

_ZEUGNIS_VERWALTUNG = r(("view", "change"), "zeugnis") | r("view", "zeugnisfachnote", "abzeichnung", "anmerkung", "konferenz", "beschluss")

# Abgänge, Klassenwechsel und Archiv (App laufbahn). Den Schuljahreswechsel macht die Schulleitung
# (akademische Verwaltung), Löschfristen ändern nur Schulleitung und IT.
_LAUFBAHN = r(ALLE, "laufbahnereignis") | r("view", "schuljahreswechsel", "wechselposten")

_SEKRETARIAT = (_SCHUELERDATEN | _LAUFBAHN | _TERMINE_VERWALTUNG | _AUFNAHME_VOLL | _ZEUGNIS_VERWALTUNG | _ELTERNKONTAKT_VERWALTUNG | r("view", *_KATALOGE) | _NOTEN_LESEN | r("view", "personalprofil", "dienstleister")
                | r("view", "nachteilsausgleich", "foerderschwerpunkt", "ausgleichsmassnahme"))

ROLLEN_RECHTE = {
    LEHRER: _LEHRER,
    MITTELSTUFE: _STUFE | _AUFNAHME_STUFE,
    OBERSTUFE: _STUFE | _AUFNAHME_STUFE,
    SCHULLEITUNG: "__alle__",
    STELLVERTRETUNG: _STUFE | _AUFNAHME_STUFE | _TERMINE_PLANUNG | r("view", "laufbahnereignis", "schuljahreswechsel", "wechselposten"),
    IT: "__alle__",
    SEKRETARIAT: _SEKRETARIAT,
    VERWALTUNGSLEITUNG: _SEKRETARIAT | _REGELN | r("view", "loeschfrist", "loeschvorgang") | r(ALLE, *_KATALOGE) | _HR | r(ALLE, "user", "group") | {"view_permission"},
    HR: _HR | _TERMINE_LESEN | r("add", "raumbuchung"),
    FINANZEN: _TERMINE_LESEN | r("add", "raumbuchung") | (r("view", "person", "schuelerprofil", "gruppe", "mitgliedschaft", "personalprofil", "personalbereich", "zusatzfeld")
               | r(("view", "change"), "beziehung", "elternprofil") | r(ALLE, "dienstleister") | r(("add", "view"), "dokument") | _AUFNAHME_FINANZEN),
    FOERDERKOORDINATION: "__foerderung__",
    SCHUELER: set(),
    ELTERN: set(),
}

FOERDERKOORDINATION_EXTRA = _TERMINE_LESEN | r("add", "raumbuchung") | (r("view", "person", "schuelerprofil", "gruppe", "mitgliedschaft", "fach", "beziehung", "elternprofil",
                                "laufbahnabschnitt", "bildungsgang", "sprachenfolge", "personalprofil", "unterricht")
                             | r(ALLE, "dokument"))

# Apps, deren Rechte über Rollen vergeben werden
APPS = ["stammdaten", "noten", "fehlzeiten", "nachmittag", "foerderung", "aufnahme", "zeugnisse", "elternkontakt", "sicherung",
        "laufbahn", "termine", "auth"]

# Rollen, die im Portal arbeiten (Beschäftigte). Schüler:innen und Eltern erhalten später eigene Oberflächen.
PORTAL_ROLLEN = {LEHRER, MITTELSTUFE, OBERSTUFE, SCHULLEITUNG, STELLVERTRETUNG, SEKRETARIAT, VERWALTUNGSLEITUNG, HR, FINANZEN, FOERDERKOORDINATION, IT}


# ---------------------------------------------------------------- Übersicht (Seite „Rollen und Rechte“)
# Werte: "ja" · "lesen" · "eigene" (eigener Unterricht/eigene Klasse) · "stufe" (eigene Stufe) · "" (kein Zugriff)
BEREICHE = [
    ("noten", _("Noten und Zeugnisnoten")),
    ("zeugnisse", _("Zeugnisse, Kommentare, Konferenzen")),
    ("elternkontakt", _("Elternkommunikation")),
    ("regeln", _("Benachrichtigungsregeln (Fehlzeiten)")),
    ("akten", _("Schülerakten")),
    ("gesundheit", _("Gesundheitsangaben")),
    ("fehlzeiten", _("Fehlzeiten")),
    ("foerderung", _("Förderpläne")),
    ("nta", _("Nachteilsausgleiche")),
    ("stammdaten", _("Schüler- und Elternstammdaten")),
    ("zuordnung", _("Klassen und Gruppen zuordnen")),
    ("aufnahme", _("Neuanmeldungen")),
    ("personal", _("Personal")),
    ("hr", _("HR-Daten")),
    ("finanzen", _("Finanzen / Rechnungsempfänger")),
    ("einstellungen", _("Schuljahre, Fächer, Notenskalen")),
    ("benutzer", _("Benutzerkonten und Rollen")),
    ("einzelrechte", _("Einzelrechte erteilen und entziehen")),
    ("sicherung", _("Sicherung, Wiederherstellung, PDF-Export")),
    ("laufbahn", _("Schuljahreswechsel")),
    ("abgang", _("Abgänge, Klassenwechsel, Archiv")),
    ("loeschfristen", _("Löschfristen und Löschung")),
    ("kalender", _("Schulkalender und Termine eintragen")),
    ("raeume", _("Räume buchen")),
    ("sprechtage", _("Elternsprechtage und LEG planen")),
    ("sprechzeiten", _("Eigene Sprechzeiten und Gesprächstermine")),
]

MATRIX = {
    LEHRER: {"elternkontakt": "eigene", "regeln": "", "zeugnisse": "eigene", "aufnahme": "", "zuordnung": "", "noten": "eigene", "akten": "eigene", "gesundheit": "", "fehlzeiten": "eigene", "foerderung": "eigene",
             "nta": "eigene", "stammdaten": "lesen", "personal": "", "hr": "", "finanzen": "", "einstellungen": "lesen", "benutzer": ""},
    MITTELSTUFE: {"elternkontakt": "stufe", "regeln": "stufe", "zeugnisse": "stufe", "aufnahme": "stufe", "zuordnung": "stufe", "noten": "stufe", "akten": "stufe", "gesundheit": "stufe", "fehlzeiten": "stufe", "foerderung": "stufe",
                  "nta": "stufe", "stammdaten": "lesen", "personal": "", "hr": "", "finanzen": "", "einstellungen": "lesen", "benutzer": ""},
    SCHULLEITUNG: {k: "ja" for k, _n in BEREICHE},
    SEKRETARIAT: {"elternkontakt": "teils_ek", "regeln": "lesen", "zeugnisse": "ja", "aufnahme": "ja", "zuordnung": "ja", "noten": "lesen", "akten": "ja", "gesundheit": "ja", "fehlzeiten": "ja", "foerderung": "", "nta": "lesen",
                  "stammdaten": "ja", "personal": "lesen", "hr": "", "finanzen": "", "einstellungen": "lesen", "benutzer": ""},
    VERWALTUNGSLEITUNG: {"elternkontakt": "teils_ek", "regeln": "ja", "zeugnisse": "ja", "aufnahme": "ja", "zuordnung": "ja", "noten": "lesen", "akten": "ja", "gesundheit": "ja", "fehlzeiten": "ja", "foerderung": "", "nta": "lesen",
                         "stammdaten": "ja", "personal": "ja", "hr": "ja", "finanzen": "ja", "einstellungen": "ja", "benutzer": "ja"},
    HR: {"elternkontakt": "", "regeln": "", "zeugnisse": "", "aufnahme": "", "zuordnung": "", "noten": "", "akten": "", "gesundheit": "", "fehlzeiten": "", "foerderung": "", "nta": "", "stammdaten": "",
         "personal": "ja", "hr": "ja", "finanzen": "", "einstellungen": "", "benutzer": ""},
    FINANZEN: {"elternkontakt": "", "regeln": "", "zeugnisse": "", "aufnahme": "teils", "zuordnung": "", "noten": "", "akten": "", "gesundheit": "", "fehlzeiten": "", "foerderung": "", "nta": "", "stammdaten": "lesen",
               "personal": "lesen", "hr": "", "finanzen": "ja", "einstellungen": "", "benutzer": ""},
    FOERDERKOORDINATION: {"elternkontakt": "", "regeln": "", "zeugnisse": "", "aufnahme": "", "zuordnung": "", "noten": "", "akten": "lesen", "gesundheit": "", "fehlzeiten": "", "foerderung": "ja", "nta": "ja",
                          "stammdaten": "lesen", "personal": "", "hr": "", "finanzen": "", "einstellungen": "", "benutzer": ""},
    SCHUELER: {k: "" for k, _n in BEREICHE},
    ELTERN: {k: "" for k, _n in BEREICHE},
}
MATRIX[IT] = {k: "ja" for k, _n in BEREICHE}
for _rolle, _werte in MATRIX.items():          # neue Bereiche: nur Schulleitung (Sicherung) und IT
    _werte.setdefault("einzelrechte", "ja" if _rolle == IT else "")
    _werte.setdefault("sicherung", "ja" if _rolle in (SCHULLEITUNG, IT) else "")
    _werte.setdefault("laufbahn", "ja" if _rolle in (SCHULLEITUNG, IT) else "")
    _werte.setdefault("abgang", "ja" if _rolle in (SCHULLEITUNG, IT, SEKRETARIAT, VERWALTUNGSLEITUNG) else "")
    _werte.setdefault("loeschfristen", "ja" if _rolle in (SCHULLEITUNG, IT) else "lesen" if _rolle == VERWALTUNGSLEITUNG else "")
    _werte.setdefault("kalender", "ja" if _rolle in (SCHULLEITUNG, IT, SEKRETARIAT, VERWALTUNGSLEITUNG, MITTELSTUFE)
                      else "lesen" if _rolle not in (SCHUELER, ELTERN) else "")
    _werte.setdefault("raeume", "" if _rolle in (SCHUELER, ELTERN) else "ja")
    _werte.setdefault("sprechtage", "ja" if _rolle in (SCHULLEITUNG, IT) else "lesen" if _rolle in (SEKRETARIAT, VERWALTUNGSLEITUNG) else "")
    _werte.setdefault("sprechzeiten", "eigene" if _rolle in (LEHRER, MITTELSTUFE) else "ja" if _rolle in (SCHULLEITUNG, IT, SEKRETARIAT, VERWALTUNGSLEITUNG) else "")
MATRIX[OBERSTUFE] = dict(MATRIX[MITTELSTUFE])
MATRIX[STELLVERTRETUNG] = dict(MATRIX[MITTELSTUFE], sprechtage="ja", sprechzeiten="ja", kalender="ja", raeume="ja",
                               laufbahn="", abgang="lesen", akten="ja", zeugnisse="ja", noten="ja", gesundheit="ja",
                               foerderung="ja", nta="ja", fehlzeiten="ja", aufnahme="ja", zuordnung="ja", regeln="ja",
                               elternkontakt="ja")

WERTE = {"ja": _("ja"), "teils": _("Checkliste"), "teils_ek": _("Zeugnis/Fehlzeiten"), "lesen": _("lesen"), "eigene": _("eigene"), "stufe": _("Stufe"), "": "–"}
