"""
Menüband (Ribbon) für Portal und Verwaltungsoberfläche.

Jede Registerkarte enthält Befehlsgruppen; jeder Befehl erscheint nur, wenn die angemeldete Person
die nötigen Rechte hat. Leere Gruppen und Karten werden ausgeblendet.
"""
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _, pgettext

from elternkontakt.rechte import darf_regeln
from laufbahn.rechte import darf_archiv, darf_fristen_sehen, darf_schuljahre
from noten import rechte as noten_rechte

from .rechte import (
    darf_sichern, ist_finanzen, ist_foerderkoordination, ist_it, ist_personalverwaltung, ist_schulleitung, ist_systemverwaltung,
    ist_verwaltung, personal_von,
)


def _url(name, *args, query=""):
    try:
        return reverse(name, args=args) + query
    except NoReverseMatch:
        return None


class Gruppe:
    def __init__(self, titel):
        self.titel = titel
        self.befehle = []
        self.auswahl = None          # Auswahlliste statt Befehlen, z. B. „Mein Unterricht“ (noten/kurswahl.py)

    def add(self, titel, url, symbol, gross=False, bedingung=True, hinweis=""):
        if bedingung and url:
            self.befehle.append({"titel": titel, "url": url, "symbol": symbol, "gross": gross, "hinweis": hinweis or titel})
        return self

    @property
    def grosse(self):
        return [b for b in self.befehle if b["gross"]]

    @property
    def kleine(self):
        return [b for b in self.befehle if not b["gross"]]


def _karte(schluessel, titel, *gruppen):
    gruppen = [g for g in gruppen if g.befehle or g.auswahl]
    return {"schluessel": schluessel, "titel": titel, "gruppen": gruppen} if gruppen else None


def menueband(request):
    user = request.user
    from noten.models import Unterricht
    from stammdaten.models import Gruppe as Lerngruppe, Schuljahr

    sj = Schuljahr.aktuelles()
    personal = personal_von(user)
    verwaltung, leitung = ist_verwaltung(user), ist_schulleitung(user)
    hr, foerder = ist_personalverwaltung(user), ist_foerderkoordination(user)
    p = user.has_perm
    admin = user.is_staff

    # ------------------------------------------------------------ Start
    start = _karte(
        "start", _("Start"),
        Gruppe(_("Übersicht"))
        .add(_("Startseite"), _url("start"), "haus", gross=True)
        .add(_("Person suchen"), _url("suche"), "lupe", gross=True),
        Gruppe(_("Microsoft 365"))
        .add(_("Office"), _url("office"), "brief", gross=True, hinweis=_("Outlook, Teams, Word, Excel und weitere Anwendungen")),
        Gruppe(_("Persönlich"))
        .add(_("Notizen"), _url("start", query="#notizen"), "notiz")
        .add(_("Geburtstage"), _url("start", query="#geburtstage"), "kerze")
        .add(_("Mitteilung schreiben"), _url("start", query="#notizen"), "nadel", bedingung=verwaltung),
        Gruppe(_("Konto"))
        .add(_("Passwort ändern"), _url("admin:password_change"), "schluessel", bedingung=admin and user.has_usable_password())
        .add(_("Sicherheit"), _url("sicherheit"), "schild", hinweis=_("Zwei-Faktor-Anmeldung einrichten")),
    )

    # ------------------------------------------------------------ Termine
    from termine import rechte as TR

    termine_karte = _karte(
        "termine", _("Termine"),
        Gruppe(_("Kalender"))
        .add(_("Schulkalender"), _url("kalender"), "kalender", gross=True, bedingung=TR.darf_kalender_sehen(user))
        .add(_("Neuer Termin"), _url("termin_neu"), "plus", bedingung=TR.darf_kalender_bearbeiten(user))
        .add(_("Kalender abonnieren"), _url("kalender_ics"), "liste", bedingung=TR.darf_kalender_sehen(user),
             hinweis=_("Termine als iCalendar-Datei, z. B. für Outlook")),
        Gruppe(_("Räume"))
        .add(_("Raumplan"), _url("raumplan"), "gebaeude", gross=True, bedingung=TR.darf_raum_buchen(user) or TR.darf_raeume_verwalten(user),
             hinweis=_("Belegung ansehen und Räume buchen"))
        .add(_("Räume verwalten"), _url("admin:termine_raum_changelist"), "regler", bedingung=TR.darf_raeume_verwalten(user)),
        Gruppe(_("Sprechtage"))
        .add(_("Sprechtage"), _url("sprechtage"), "personen", gross=True, bedingung=TR.ist_beschaeftigt(user)
             and p("termine.view_sprechtag"), hinweis=_("Elternsprechtage und Lern- und Entwicklungsgespräche")),
    )

    # ------------------------------------------------------------ Schüler:innen
    meine_klassen = Gruppe(_("Meine Klassen"))
    if personal and sj:
        for g in Lerngruppe.objects.filter(leitung=personal, schuljahr=sj).order_by("typ", "name"):
            meine_klassen.add(g.name, _url("klassenliste", g.pk), "tafel" if g.typ == Lerngruppe.STAMMKLASSE else "gruppen",
                              gross=g.typ == Lerngruppe.STAMMKLASSE,
                              hinweis=_("Klassenliste %(name)s") % {"name": g.name})
    alle_sehen = verwaltung or foerder
    from .startseite import stufen_fuer
    from .zuordnung import darf_zuordnen

    stufen = Gruppe(_("Stufenkoordination"))
    for st in stufen_fuer(user):
        stufen.add(str(st["name"]), st["url"], "treppe", gross=True,
                   hinweis=_("%(name)s, Jahrgänge %(von)s bis %(bis)s") % {"name": st["name"], "von": st["von"], "bis": st["bis"]})
    from aufnahme.rechte import darf_aufnahme

    aufnahme = darf_aufnahme(user)
    neuanmeldung = (
        Gruppe(_("Neuanmeldung"))
        .add(_("Neuanmeldungen"), _url("anmeldungen"), "tuer", gross=True, bedingung=aufnahme,
             hinweis=_("Bewerbungen mit Unterlagen, Checkliste und vorläufiger Klasse"))
        .add(_("Neue Anmeldung"), _url("anmeldung_neu"), "plus", bedingung=aufnahme and p("aufnahme.add_anmeldung"))
        .add(_("Zugesagt"), _url("anmeldungen", query="?status=zugesagt"), "haken", bedingung=aufnahme,
             hinweis=_("Zugesagte Anmeldungen, Übernahme offen"))
        .add(_("Checklisten-Vorlagen"), _url("admin:aufnahme_checklistenvorlage_changelist"), "liste",
             bedingung=aufnahme and admin and p("aufnahme.change_checklistenvorlage"))
    )
    schueler = _karte(
        "schueler", _("Schüler:innen"),
        meine_klassen,
        stufen,
        neuanmeldung,
        Gruppe(_("Schülerakten"))
        .add(_("Alle Schüler:innen"), _url("admin:stammdaten_schuelerprofil_changelist", query="?status__exact=aktiv"), "personen", gross=True,
             bedingung=alle_sehen and p("stammdaten.view_schuelerprofil"))
        .add(_("Anhänge"), _url("admin:stammdaten_dokument_changelist"), "klammer", bedingung=p("stammdaten.view_dokument")),
        Gruppe(_("Eltern"))
        .add(_("Elternnachrichten"), _url("elternkontakt"), "brief", gross=True, bedingung=p("elternkontakt.view_gespraech"),
             hinweis=_("Nachrichten an Eltern, Antworten und Bestätigungen"))
        .add(_("Neue Nachricht"), _url("elternnachricht_neu"), "plus", bedingung=p("elternkontakt.add_gespraech"))
        .add(_("Benachrichtigungsregeln"), _url("elternkontakt_regeln"), "glocke", bedingung=darf_regeln(user),
             hinweis=_("Automatische Benachrichtigung bei Fehlzeiten und Verspätungen")),
        Gruppe(_("Klassen und Gruppen"))
        .add(_("Klassen und Gruppen"), _url("zuordnung"), "person_plus", gross=True, bedingung=darf_zuordnen(user),
             hinweis=_("Klassen anlegen, Schüler:innen zuordnen und abmelden, Fächer und Lehrkräfte festlegen")),
        Gruppe(_("Fehlzeiten"))
        .add(_("Fehlzeiten"), _url("admin:fehlzeiten_fehlzeit_changelist"), "uhr", gross=True, bedingung=p("fehlzeiten.view_fehlzeit"))
        .add(_("Offene Entschuldigungen"), _url("admin:fehlzeiten_fehlzeit_changelist", query="?status__exact=offen"), "warnung",
             bedingung=p("fehlzeiten.view_fehlzeit"))
        .add(_("Fehlzeit erfassen"), _url("admin:fehlzeiten_fehlzeit_add"), "plus", bedingung=p("fehlzeiten.add_fehlzeit")),
    )

    # ------------------------------------------------------------ Unterricht
    mein_unterricht = Gruppe(_("Mein Unterricht"))
    if personal and sj:
        from noten import kurswahl

        rm = getattr(request, "resolver_match", None)
        aktuell = None
        if rm is not None and rm.url_name in kurswahl.URLNAME_ZU_ZIEL and rm.kwargs.get("pk"):
            aktuell = Unterricht(pk=rm.kwargs["pk"])
        mein_unterricht.auswahl = kurswahl.auswahl(request, aktuell)
    unterricht = _karte(
        "unterricht", pgettext("Menüband", "Unterricht"),
        mein_unterricht,
        Gruppe(_("Bewertung"))
        .add(_("Noten nach Klasse"), _url("noten_klassen"), "tafel", gross=True, bedingung=p("noten.view_note"),
             hinweis=_("Klasse und Kurs wählen, Noten in der Tabelle eintragen, Excel-Tabelle laden"))
        .add(_("Leistungsvorgaben"), _url("leistungsvorgaben"), "haken", gross=True, bedingung=p("noten.view_leistungsvorgabe"),
             hinweis=_("Pflichtnoten mit Frist"))
        .add(_("Leistungsnachweise"), _url("admin:noten_leistungsnachweis_changelist"), "stift",
             bedingung=p("noten.view_leistungsnachweis"))
        .add(_("Neuer Leistungsnachweis"), _url("admin:noten_leistungsnachweis_add"), "plus", bedingung=p("noten.add_leistungsnachweis"))
        .add(_("Bewertungsordner"), _url("admin:noten_bewertungsordner_changelist"), "ordner", bedingung=p("noten.view_bewertungsordner"))
        .add(_("Einzelnoten"), _url("admin:noten_note_changelist"), "liste", bedingung=p("noten.view_note")),
        Gruppe(_("Zeugnis"))
        .add(_("Zeugnisse"), _url("zeugnisse"), "zeugnis", gross=True, bedingung=p("zeugnisse.view_zeugnis"),
             hinweis=_("Zeugnisnoten, Kommentare, Zeugnisse und Konferenzen"))
        .add(_("Notenliste"), _url("notenliste"), "liste", bedingung=p("zeugnisse.view_zeugnis"),
             hinweis=_("Alle Zeugnisnoten einer Klasse wie in der Konferenz – auch vergangene Halbjahre"))
        .add(_("Konferenzen"), _url("admin:zeugnisse_konferenz_changelist"), "gruppen",
             bedingung=admin and p("zeugnisse.change_konferenz"))
        .add(_("Notensperre"), _url("notensperre"), "schild",
             bedingung=noten_rechte.darf_noten_sperren(user, None) or noten_rechte.ist_koordination(user),
             hinweis=_("Noten einer Klasse nach Zeugnisfreigabe bzw. Konferenz sperren oder wieder freigeben")),
    )

    # ------------------------------------------------------------ Förderung
    foerderung = _karte(
        "foerderung", _("Förderung"),
        Gruppe(_("Förderpläne"))
        .add(_("Förderpläne"), _url("admin:foerderung_foerderplan_changelist"), "pflanze", gross=True,
             bedingung=p("foerderung.view_foerderplan"))
        .add(_("Neuer Förderplan"), _url("admin:foerderung_foerderplan_add"), "plus", bedingung=p("foerderung.add_foerderplan"))
        .add(_("Verlaufsdokumentation"), _url("admin:foerderung_foerdereintrag_changelist"), "liste",
             bedingung=p("foerderung.view_foerdereintrag")),
        Gruppe(_("Nachteilsausgleiche"))
        .add(_("Gültige"), _url("admin:foerderung_nachteilsausgleich_changelist", query="?gueltig=aktiv"), "waage", gross=True,
             bedingung=p("foerderung.view_nachteilsausgleich"), hinweis=_("Gültige Nachteilsausgleiche"))
        .add(_("Beantragt"), _url("admin:foerderung_nachteilsausgleich_changelist", query="?status__exact=beantragt"), "warnung",
             bedingung=p("foerderung.view_nachteilsausgleich") and (foerder or personal is not None))
        .add(_("Erfassen"), _url("admin:foerderung_nachteilsausgleich_add"), "plus",
             bedingung=p("foerderung.add_nachteilsausgleich"), hinweis=_("Nachteilsausgleich erfassen")),
        Gruppe(_("Eltern"))
        .add(_("Erhalt offen"), _url("admin:foerderung_aushaendigung_changelist", query="?bestaetigt_am__isempty=1"), "haken",
             gross=True, bedingung=p("foerderung.view_aushaendigung"), hinweis=_("Elternbestätigung offen")),
        Gruppe(_("Kataloge"))
        .add(_("Förderschwerpunkte"), _url("admin:foerderung_foerderschwerpunkt_changelist"), "kategorie",
             bedingung=foerder and p("foerderung.change_foerderschwerpunkt"))
        .add(_("Ausgleichsmaßnahmen"), _url("admin:foerderung_ausgleichsmassnahme_changelist"), "kategorie",
             bedingung=foerder and p("foerderung.change_ausgleichsmassnahme")),
    )

    # ------------------------------------------------------------ Personal
    personal_karte = _karte(
        "personal", _("Personal"),
        Gruppe(_("Beschäftigte"))
        .add(_("Personalliste"), _url("admin:stammdaten_personalprofil_changelist"), "ausweis", gross=True,
             bedingung=(hr or verwaltung) and p("stammdaten.view_personalprofil"))
        .add(_("Einstellen"), _url("admin:stammdaten_personalprofil_add"), "person_plus",
             bedingung=(hr or verwaltung) and p("stammdaten.add_personalprofil"), hinweis=_("Neue Mitarbeiterin / neuen Mitarbeiter anlegen"))
        .add(_("Nachweise offen"), _url("admin:stammdaten_personalprofil_changelist", query="?nachweise=offen"), "warnung",
             bedingung=hr),
        Gruppe(_("Abwesenheiten"))
        .add(_("Abwesenheiten"), _url("admin:stammdaten_personalabwesenheit_changelist"), "kalender", gross=True,
             bedingung=p("stammdaten.view_personalabwesenheit"))
        .add(_("Offene Anträge"), _url("admin:stammdaten_personalabwesenheit_changelist", query="?status__exact=beantragt"),
             "warnung", bedingung=p("stammdaten.view_personalabwesenheit")),
        Gruppe(_("Einstellungen"))
        .add(_("Personalbereiche"), _url("admin:stammdaten_personalbereich_changelist"), "gruppen", bedingung=hr and p("stammdaten.view_personalbereich"))
        .add(_("Nachweisarten"), _url("admin:stammdaten_nachweisart_changelist"), "haken", bedingung=hr and p("stammdaten.view_nachweisart"))
        .add(_("Dienstleister"), _url("admin:stammdaten_dienstleister_changelist"), "gebaeude", bedingung=hr and p("stammdaten.view_dienstleister")),
    )

    # ------------------------------------------------------------ Schulleitung (akademische Verwaltung)
    schulleitung_karte = _karte(
        "schulleitung", _("Schulleitung"),
        Gruppe(_("Schuljahr"))
        .add(_("Schuljahreswechsel"), _url("schuljahre"), "kalender", gross=True, bedingung=darf_schuljahre(user),
             hinweis=_("Schuljahre anlegen, Schüler:innen versetzen, Wechsel zurücknehmen"))
        .add(_("Schuljahre"), _url("admin:stammdaten_schuljahr_changelist"), "liste", bedingung=leitung and p("stammdaten.view_schuljahr"))
        .add(_("Zeitraster"), _url("admin:fehlzeiten_stunde_changelist"), "uhr", bedingung=leitung and p("fehlzeiten.view_stunde"))
        .add(_("Bildungsgänge"), _url("admin:stammdaten_bildungsgang_changelist"), "treppe", bedingung=leitung and p("stammdaten.view_bildungsgang"))
        .add(_("Abschlussarten"), _url("admin:stammdaten_abschlussart_changelist"), "zeugnis", bedingung=leitung and p("stammdaten.view_abschlussart")),
        Gruppe(_("Unterrichtsorganisation"))
        .add(_("Unterrichtsverteilung"), _url("admin:noten_unterricht_changelist"), "tafel", gross=True,
             bedingung=leitung and p("noten.view_unterricht"))
        .add(_("Fächer"), _url("admin:stammdaten_fach_changelist"), "buch", bedingung=leitung and p("stammdaten.view_fach"))
        .add(_("Notenskalen"), _url("admin:noten_notenskala_changelist"), "lineal", bedingung=leitung and p("noten.view_notenskala"))
        .add(_("Gewichtungsvorlagen"), _url("admin:noten_gewichtungsvorlage_changelist"), "regler",
             bedingung=leitung and p("noten.view_gewichtungsvorlage"))
        .add(_("Notenregeln"), _url("klausurregeln"), "stift", bedingung=noten_rechte.darf_klausurregeln(user),
             hinweis=_("Klausuren je Fach (z. B. 50 / 50) und Freigabe: Zeugnisnote ohne Einzelnoten")),
        Gruppe(_("Archiv"))
        .add(_("Archiv"), _url("archiv"), "archiv", gross=True, bedingung=leitung and darf_archiv(user),
             hinweis=_("Abgegangene Schüler:innen, Abgangszeugnisse, Löschfristen"))
        .add(_("Löschfristen"), _url("loeschfristen"), "glocke", bedingung=leitung and darf_fristen_sehen(user),
             hinweis=_("Aufbewahrungsfristen für das Archiv und fällige Löschungen")),
    )

    # ------------------------------------------------------------ Verwaltung (Administration)
    finanzen = ist_finanzen(user)
    verwaltung_karte = _karte(
        "verwaltung", _("Verwaltung"),
        Gruppe(_("Übersicht"))
        .add(_("Alle Bereiche"), _url("admin:index"), "zahnrad", gross=True,
             bedingung=admin and (verwaltung or finanzen or hr or ist_it(user))),
        Gruppe(_("Sekretariat"))
        .add(_("Schüler:in anlegen"), _url("admin:stammdaten_schuelerprofil_add"), "plus", gross=True,
             bedingung=verwaltung and p("stammdaten.add_schuelerprofil"),
             hinweis=_("Schüler:in ohne Anmeldeverfahren direkt anlegen"))
        .add(_("Eltern und Kontakte"), _url("admin:stammdaten_person_changelist", query="?rolle=eltern"), "personen",
             bedingung=verwaltung and p("stammdaten.view_person"))
        .add(_("Klassen und Gruppen"), _url("admin:stammdaten_gruppe_changelist"), "gruppen",
             bedingung=verwaltung and p("stammdaten.view_gruppe"))
        .add(_("Mitgliedschaften"), _url("admin:stammdaten_mitgliedschaft_changelist"), "liste",
             bedingung=verwaltung and p("stammdaten.view_mitgliedschaft"))
        .add(_("Schullaufbahn"), _url("admin:stammdaten_laufbahnabschnitt_changelist"), "treppe",
             bedingung=verwaltung and p("stammdaten.view_laufbahnabschnitt"))
        .add(_("Archiv"), _url("archiv"), "archiv", bedingung=darf_archiv(user) and not leitung,
             hinweis=_("Abgegangene Schüler:innen, Abgangszeugnisse, Löschfristen")),
        Gruppe(_("Nachmittag"))
        .add(_("AG-Angebote"), _url("admin:nachmittag_agangebot_changelist"), "ball", gross=True,
             bedingung=p("nachmittag.change_agangebot"))
        .add(_("AG-Wünsche"), _url("admin:nachmittag_agwahl_changelist"), "liste", bedingung=p("nachmittag.change_agwahl"))
        .add(_("Zuteilungen"), _url("admin:nachmittag_agzuteilung_changelist"), "haken", bedingung=p("nachmittag.change_agzuteilung")),
        Gruppe(_("Finanzen"))
        .add(_("Rechnungsempfänger"), _url("admin:stammdaten_beziehung_changelist", query="?rechnungsempfaenger__exact=1"),
             "personen", gross=True, bedingung=finanzen and p("stammdaten.view_beziehung"))
        .add(_("Elternprofile"), _url("admin:stammdaten_elternprofil_changelist"), "liste",
             bedingung=finanzen and p("stammdaten.view_elternprofil"))
        .add(_("Schüler:innen"), _url("admin:stammdaten_schuelerprofil_changelist"), "personen",
             bedingung=finanzen and not verwaltung and p("stammdaten.view_schuelerprofil"))
        .add(_("Dienstleister"), _url("admin:stammdaten_dienstleister_changelist"), "gebaeude",
             bedingung=finanzen and p("stammdaten.view_dienstleister"))
        .add(_("Vertragsunterlagen"), _url("admin:stammdaten_dokument_changelist", query="?kategorie__exact=vertrag"), "klammer",
             bedingung=finanzen and p("stammdaten.view_dokument")),
    )

    # ------------------------------------------------------------ System (IT)
    system_karte = _karte(
        "system", _("System"),
        Gruppe(_("Benutzer und Rechte"))
        .add(_("Benutzerkonten"), _url("admin:auth_user_changelist"), "schluessel", gross=True, bedingung=p("auth.view_user"))
        .add(_("Rollen"), _url("admin:auth_group_changelist"), "schild", bedingung=p("auth.view_group"))
        .add(_("Rollen und Rechte"), _url("rollen"), "liste", bedingung=ist_systemverwaltung(user),
             hinweis=_("Übersicht: welche Rolle was darf"))
        .add(_("Einzelrechte"), _url("benutzerverwaltung"), "person_plus", bedingung=ist_it(user),
             hinweis=_("Rollen und Einzelrechte je Konto erteilen oder entziehen")),
        Gruppe(_("Datenfelder"))
        .add(_("Eigene Felder"), _url("admin:stammdaten_zusatzfeld_changelist"), "regler", gross=True,
             bedingung=p("stammdaten.change_zusatzfeld"), hinweis=_("Zusatzfelder für Schüler:innen, Personal und Eltern")),
        Gruppe(_("Sicherung"))
        .add(_("Sicherung"), _url("sicherungen"), "archiv", gross=True, bedingung=darf_sichern(user),
             hinweis=_("Module sichern und wiederherstellen"))
        .add(_("PDF-Export"), _url("pdf_export"), "pdf", bedingung=darf_sichern(user), hinweis=_("Daten eines Zeitraums als PDF"))
        .add(pgettext("System", "Protokoll"), _url("systemprotokoll"), "liste", bedingung=darf_sichern(user) or ist_it(user)),
    )

    karten = [k for k in (start, termine_karte, schueler, unterricht, foerderung, schulleitung_karte, verwaltung_karte, personal_karte, system_karte) if k]
    aktiv = _aktive_karte(request.path, karten)
    _aktiven_befehl_markieren(request.get_full_path(), karten)
    from . import rollen as R

    namen = set(user.groups.values_list("name", flat=True))
    rollen = [str(R.ANZEIGE[n]) for n in R.REIHENFOLGE if n in namen] + sorted(n for n in namen if n not in R.ANZEIGE)
    if user.is_superuser:
        rollen.insert(0, _("Vollzugriff"))
    return {"karten": karten, "aktiv": aktiv, "rollen": rollen}


PFAD_REGELN = [("/termine/", "termine"), ("/laufbahn/archiv/", "schulleitung"), ("/laufbahn/archiv/", "verwaltung"), ("/laufbahn/schueler/", "schueler"),
               ("/klassen/", "schueler"), ("/schueler/", "schueler"), ("/stufe/", "schueler"), ("/zuordnung/", "schueler"),
               ("/aufnahme/", "schueler"), ("/elternkontakt/", "schueler"),
               ("/noten/", "unterricht"), ("/zeugnisse/", "unterricht"),
               ("/laufbahn/", "schulleitung"), ("/rollen/", "system"), ("/system/", "system"),
               ("/foerderung/", "foerderung"), ("/verwaltung/", "verwaltung"), ("/verwaltung/", "system")]


def _aktive_karte(pfad, karten):
    """Karte des am besten passenden Befehls; sonst nach Pfadregeln; sonst Start."""
    beste, laenge = None, 0
    for k in karten:
        for g in k["gruppen"]:
            for b in g.befehle:
                basis = b["url"].split("?")[0].split("#")[0]
                if basis in ("/", "/verwaltung/"):
                    continue
                if pfad.startswith(basis) and len(basis) > laenge:
                    beste, laenge = k["schluessel"], len(basis)
    if beste:
        return beste
    vorhanden = {k["schluessel"] for k in karten}
    for praefix, schluessel in PFAD_REGELN:
        if pfad.startswith(praefix) and schluessel in vorhanden:
            return schluessel
    return "start"


def _aktiven_befehl_markieren(voller_pfad, karten):
    beste, laenge = None, 0
    pfad = voller_pfad.split("#")[0]
    for k in karten:
        for g in k["gruppen"]:
            for b in g.befehle:
                b["aktiv"] = False
                url = b["url"].split("#")[0]
                if "#" in b["url"]:
                    continue
                if pfad == url or (pfad.split("?")[0].startswith(url.split("?")[0]) and "?" not in url and url not in ("/", "/verwaltung/")):
                    if len(url) > laenge:
                        beste, laenge = b, len(url)
    if beste:
        beste["aktiv"] = True
