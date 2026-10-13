"""
Rollen der Schulverwaltung (Django-Benutzergruppen) mit ihren Standardrechten.

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
SEKRETARIAT = "Sekretariat"
VERWALTUNGSLEITUNG = "Verwaltungsleitung"
HR = "HR-Management"
FINANZEN = "Finanzen"
FOERDERKOORDINATION = "Förderkoordination"
SCHUELER = "Schüler:in"
ELTERN = "Eltern"

# Frühere Gruppennamen (bis Version 0.4.2.2) – werden per Migration umbenannt.
ALTE_NAMEN = {"Lehrkraft": LEHRER, "Verwaltung": SEKRETARIAT, "Personalverwaltung": HR}

ANZEIGE = {
    LEHRER: _("Lehrer:in"), MITTELSTUFE: _("Mittelstufenkoordination"), OBERSTUFE: _("Oberstufenkoordination"),
    SCHULLEITUNG: _("Schulleitung"), SEKRETARIAT: _("Sekretariat"), VERWALTUNGSLEITUNG: _("Verwaltungsleitung"),
    HR: _("HR-Management"), FINANZEN: _("Finanzen"), FOERDERKOORDINATION: _("Förderkoordination"),
    SCHUELER: _("Schüler:in"), ELTERN: _("Eltern"),
}

BESCHREIBUNG = {
    LEHRER: _("Eigener Unterricht mit Leistungsnachweisen, Noten und Zeugnisnoten. Als Klassenleitung: Schülerakte, "
              "Fehlzeiten, Anhänge und Förderung der eigenen Klasse. Nachteilsausgleiche der eigenen Schüler:innen lesen."),
    MITTELSTUFE: _("Wie Lehrer:in, zusätzlich für alle Klassen der Mittelstufe: Schülerakten, Notenübersichten, Fehlzeiten, "
                   "Gesundheitshinweise, Förderpläne und Nachteilsausgleiche (bearbeiten), Schullaufbahn und Versetzungsvermerke, "
                   "Klassen und Lerngruppen der Stufe bilden und Schüler:innen zuordnen, Neuanmeldungen der Stufe bearbeiten."),
    OBERSTUFE: _("Wie Mittelstufenkoordination, bezogen auf die Jahrgänge der Oberstufe."),
    SCHULLEITUNG: _("Alle Rechte, einschließlich Genehmigung von Nachteilsausgleichen, HR-Daten und Benutzerverwaltung."),
    SEKRETARIAT: _("Schüler- und Elternstammdaten, Klassen und Gruppen, Fehlzeiten, AGs, Einwilligungen, Anhänge, "
                   "Gesundheitsangaben, Neuanmeldungen einschließlich Übernahme. Noten, Unterrichtsverteilung, Kataloge und Personal nur lesend; keine Förderpläne, keine HR-Daten."),
    VERWALTUNGSLEITUNG: _("Wie Sekretariat, zusätzlich Schuljahre, Zeitraster, Fächer, Notenskalen, Unterrichtsverteilung, "
                          "eigene Datenfelder, Benutzerkonten und Rollen, Personal einschließlich HR-Daten, Dienstleister und Finanzen. "
                          "Keine Noteneingabe, keine Förderpläne."),
    HR: _("Personal aller Bereiche mit Dienstverhältnis, Nachweisen, Abwesenheiten, Fortbildungen und Notfallkontakten. "
          "Keine Noten, keine Gesundheits- oder Förderdaten von Schüler:innen."),
    FINANZEN: _("Rechnungsempfänger:innen und Elternstammdaten, Schülerstammdaten lesend, Dienstleister und Verträge, "
                "Anhänge der Kategorie Verwaltung, Neuanmeldungen lesen mit Checkliste, Kontakten und Unterlagen. Keine Noten, keine Förder- und Gesundheitsdaten. Ein Finanzmodul folgt später."),
    FOERDERKOORDINATION: _("Alle Förderpläne und Nachteilsausgleiche der Schule, Genehmigung, Kataloge, Schülerakten lesend."),
    SCHUELER: _("Vorbereitet für den späteren Stundenplan. Derzeit kein Zugang zum Portal."),
    ELTERN: _("Vorbereitet für die spätere Elternkommunikation. Derzeit kein Zugang zum Portal."),
}

REIHENFOLGE = [LEHRER, MITTELSTUFE, OBERSTUFE, SCHULLEITUNG, SEKRETARIAT, VERWALTUNGSLEITUNG, HR, FINANZEN,
               FOERDERKOORDINATION, SCHUELER, ELTERN]

ALLE = ("add", "change", "view", "delete")


def r(aktionen, *modelle):
    if isinstance(aktionen, str):
        aktionen = (aktionen,)
    return {f"{a}_{m}" for a in aktionen for m in modelle}


# ---------------------------------------------------------------- Bausteine
_LEHRER = (
    r("view", "person", "schuelerprofil", "gruppe", "mitgliedschaft", "fach", "beziehung", "unterricht", "notenskala",
      "notenstufe", "notenschluessel", "gewichtungsvorlage", "leistungskategorie", "laufbahnabschnitt", "abschluss",
      "sprachenfolge", "vorherigeschule", "elternprofil", "bildungsgang", "abschlussart", "einwilligung", "stunde",
      "agangebot", "agwahl", "agzuteilung", "foerderschwerpunkt", "ausgleichsmassnahme")
    | r(ALLE, "bewertungsordner", "leistungsnachweis")
    | r(("add", "change", "view"), "note", "zeugnisnote", "fehlzeit", "foerderplan", "foerdereintrag",
        "nachteilsausgleich", "aushaendigung")
    | r(ALLE, "foerderziel")
    | r(("add", "view"), "dokument")
)
# Gesundheitshinweise der eigenen Stufe: zeilenweise über view_gesundheit_klasse (siehe portal/rechte.py)
_STUFE = (_LEHRER | r(("add", "change", "view"), "laufbahnabschnitt", "abschluss", "gruppe") | r(ALLE, "mitgliedschaft")
          | {"view_gesundheit_klasse"})

_SCHUELERDATEN = r(ALLE, "person", "schuelerprofil", "elternprofil", "beziehung", "gruppe", "mitgliedschaft", "einwilligung",
                   "dokument", "laufbahnabschnitt", "abschluss", "vorherigeschule", "sprachenfolge", "gesundheitsangaben",
                   "fehlzeit", "agangebot", "agwahl", "agzuteilung") | {"view_gesundheitsangaben"}
_KATALOGE = ("schuljahr", "abschnitt", "fach", "bildungsgang", "abschlussart", "stunde", "unterricht", "notenskala",
             "notenstufe", "notenschluessel", "gewichtungsvorlage", "leistungskategorie", "zusatzfeld", "personalbereich")
_NOTEN_LESEN = r("view", "leistungsnachweis", "note", "zeugnisnote", "bewertungsordner")
_HR = r(ALLE, "personalprofil", "personalbereich", "dienstleister", "nachweisart", "nachweis", "personalabwesenheit",
        "fortbildung", "notfallkontakt", "dokument") | r(("add", "change", "view"), "person", "zusatzfeld") | {"view_hr_daten", "view_fach"}

# Neuanmeldungen (App aufnahme). Zeilenweise: Stufenkoordination nur Anmeldungen ihrer Jahrgänge (aufnahme/rechte.py).
_AUFNAHME_MODELLE = ("anmeldung", "anmeldekontakt", "anmeldedatei", "anmeldepunkt")
_AUFNAHME_VOLL = r(ALLE, *_AUFNAHME_MODELLE, "checklistenvorlage", "vorlagenpunkt") | {"uebernehmen_anmeldung"}
_AUFNAHME_STUFE = (r(("add", "change", "view"), "anmeldung", "anmeldekontakt") | r(ALLE, "anmeldedatei", "anmeldepunkt")
                   | r("view", "checklistenvorlage", "vorlagenpunkt"))
_AUFNAHME_FINANZEN = (r("view", *_AUFNAHME_MODELLE, "checklistenvorlage", "vorlagenpunkt")
                      | r("change", "anmeldekontakt", "anmeldepunkt") | r("add", "anmeldedatei"))

_SEKRETARIAT = (_SCHUELERDATEN | _AUFNAHME_VOLL | r("view", *_KATALOGE) | _NOTEN_LESEN | r("view", "personalprofil", "dienstleister")
                | r("view", "nachteilsausgleich", "foerderschwerpunkt", "ausgleichsmassnahme"))

ROLLEN_RECHTE = {
    LEHRER: _LEHRER,
    MITTELSTUFE: _STUFE | _AUFNAHME_STUFE,
    OBERSTUFE: _STUFE | _AUFNAHME_STUFE,
    SCHULLEITUNG: "__alle__",
    SEKRETARIAT: _SEKRETARIAT,
    VERWALTUNGSLEITUNG: _SEKRETARIAT | r(ALLE, *_KATALOGE) | _HR | r(ALLE, "user", "group") | {"view_permission"},
    HR: _HR,
    FINANZEN: (r("view", "person", "schuelerprofil", "gruppe", "mitgliedschaft", "personalprofil", "personalbereich", "zusatzfeld")
               | r(("view", "change"), "beziehung", "elternprofil") | r(ALLE, "dienstleister") | r(("add", "view"), "dokument") | _AUFNAHME_FINANZEN),
    FOERDERKOORDINATION: "__foerderung__",
    SCHUELER: set(),
    ELTERN: set(),
}

FOERDERKOORDINATION_EXTRA = (r("view", "person", "schuelerprofil", "gruppe", "mitgliedschaft", "fach", "beziehung", "elternprofil",
                                "laufbahnabschnitt", "bildungsgang", "sprachenfolge", "personalprofil", "unterricht")
                             | r(ALLE, "dokument"))

# Apps, deren Rechte über Rollen vergeben werden
APPS = ["stammdaten", "noten", "fehlzeiten", "nachmittag", "foerderung", "aufnahme", "auth"]

# Rollen, die im Portal arbeiten (Beschäftigte). Schüler:innen und Eltern erhalten später eigene Oberflächen.
PORTAL_ROLLEN = {LEHRER, MITTELSTUFE, OBERSTUFE, SCHULLEITUNG, SEKRETARIAT, VERWALTUNGSLEITUNG, HR, FINANZEN, FOERDERKOORDINATION}


# ---------------------------------------------------------------- Übersicht (Seite „Rollen und Rechte“)
# Werte: "ja" · "lesen" · "eigene" (eigener Unterricht/eigene Klasse) · "stufe" (eigene Stufe) · "" (kein Zugriff)
BEREICHE = [
    ("noten", _("Noten und Zeugnisnoten")),
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
]

MATRIX = {
    LEHRER: {"aufnahme": "", "zuordnung": "", "noten": "eigene", "akten": "eigene", "gesundheit": "", "fehlzeiten": "eigene", "foerderung": "eigene",
             "nta": "eigene", "stammdaten": "lesen", "personal": "", "hr": "", "finanzen": "", "einstellungen": "lesen", "benutzer": ""},
    MITTELSTUFE: {"aufnahme": "stufe", "zuordnung": "stufe", "noten": "stufe", "akten": "stufe", "gesundheit": "stufe", "fehlzeiten": "stufe", "foerderung": "stufe",
                  "nta": "stufe", "stammdaten": "lesen", "personal": "", "hr": "", "finanzen": "", "einstellungen": "lesen", "benutzer": ""},
    SCHULLEITUNG: {k: "ja" for k, _n in BEREICHE},
    SEKRETARIAT: {"aufnahme": "ja", "zuordnung": "ja", "noten": "lesen", "akten": "ja", "gesundheit": "ja", "fehlzeiten": "ja", "foerderung": "", "nta": "lesen",
                  "stammdaten": "ja", "personal": "lesen", "hr": "", "finanzen": "", "einstellungen": "lesen", "benutzer": ""},
    VERWALTUNGSLEITUNG: {"aufnahme": "ja", "zuordnung": "ja", "noten": "lesen", "akten": "ja", "gesundheit": "ja", "fehlzeiten": "ja", "foerderung": "", "nta": "lesen",
                         "stammdaten": "ja", "personal": "ja", "hr": "ja", "finanzen": "ja", "einstellungen": "ja", "benutzer": "ja"},
    HR: {"aufnahme": "", "zuordnung": "", "noten": "", "akten": "", "gesundheit": "", "fehlzeiten": "", "foerderung": "", "nta": "", "stammdaten": "",
         "personal": "ja", "hr": "ja", "finanzen": "", "einstellungen": "", "benutzer": ""},
    FINANZEN: {"aufnahme": "teils", "zuordnung": "", "noten": "", "akten": "", "gesundheit": "", "fehlzeiten": "", "foerderung": "", "nta": "", "stammdaten": "lesen",
               "personal": "lesen", "hr": "", "finanzen": "ja", "einstellungen": "", "benutzer": ""},
    FOERDERKOORDINATION: {"aufnahme": "", "zuordnung": "", "noten": "", "akten": "lesen", "gesundheit": "", "fehlzeiten": "", "foerderung": "ja", "nta": "ja",
                          "stammdaten": "lesen", "personal": "", "hr": "", "finanzen": "", "einstellungen": "", "benutzer": ""},
    SCHUELER: {k: "" for k, _n in BEREICHE},
    ELTERN: {k: "" for k, _n in BEREICHE},
}
MATRIX[OBERSTUFE] = dict(MATRIX[MITTELSTUFE])

WERTE = {"ja": _("ja"), "teils": _("Checkliste"), "lesen": _("lesen"), "eigene": _("eigene"), "stufe": _("Stufe"), "": "–"}
