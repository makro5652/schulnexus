"""
Menüband (Ribbon) für Portal und Verwaltungsoberfläche.

Jede Registerkarte enthält Befehlsgruppen; jeder Befehl erscheint nur, wenn die angemeldete Person
die nötigen Rechte hat. Leere Gruppen und Karten werden ausgeblendet.
"""
from django.urls import NoReverseMatch, reverse
from django.utils.translation import gettext as _, pgettext

from .rechte import (
    ist_finanzen, ist_foerderkoordination, ist_personalverwaltung, ist_schulleitung, ist_systemverwaltung, ist_verwaltung,
    personal_von,
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
    gruppen = [g for g in gruppen if g.befehle]
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
        Gruppe(_("Persönlich"))
        .add(_("Notizen"), _url("start", query="#notizen"), "notiz")
        .add(_("Geburtstage"), _url("start", query="#geburtstage"), "kerze")
        .add(_("Mitteilung schreiben"), _url("start", query="#notizen"), "nadel", bedingung=verwaltung),
        Gruppe(_("Konto"))
        .add(_("Passwort ändern"), _url("admin:password_change"), "schluessel", bedingung=admin and user.has_usable_password()),
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

    stufen = Gruppe(_("Stufenkoordination"))
    for st in stufen_fuer(user):
        stufen.add(str(st["name"]), st["url"], "treppe", gross=True,
                   hinweis=_("%(name)s, Jahrgänge %(von)s bis %(bis)s") % {"name": st["name"], "von": st["von"], "bis": st["bis"]})
    schueler = _karte(
        "schueler", _("Schüler:innen"),
        meine_klassen,
        stufen,
        Gruppe(_("Schülerakten"))
        .add(_("Alle Schüler:innen"), _url("admin:stammdaten_schuelerprofil_changelist"), "personen", gross=True,
             bedingung=alle_sehen and p("stammdaten.view_schuelerprofil"))
        .add(_("Aufnehmen"), _url("admin:stammdaten_schuelerprofil_add"), "person_plus",
             bedingung=verwaltung and p("stammdaten.add_schuelerprofil"))
        .add(_("Eltern und Kontakte"), _url("admin:stammdaten_person_changelist", query="?rolle=eltern"), "personen",
             bedingung=verwaltung and p("stammdaten.view_person"))
        .add(_("Anhänge"), _url("admin:stammdaten_dokument_changelist"), "klammer", bedingung=p("stammdaten.view_dokument")),
        Gruppe(_("Klassen und Gruppen"))
        .add(_("Klassen und Gruppen"), _url("admin:stammdaten_gruppe_changelist"), "gruppen", gross=True,
             bedingung=verwaltung and p("stammdaten.view_gruppe"))
        .add(_("Mitgliedschaften"), _url("admin:stammdaten_mitgliedschaft_changelist"), "liste",
             bedingung=verwaltung and p("stammdaten.view_mitgliedschaft"))
        .add(_("Schullaufbahn"), _url("admin:stammdaten_laufbahnabschnitt_changelist"), "treppe",
             bedingung=verwaltung and p("stammdaten.view_laufbahnabschnitt")),
        Gruppe(_("Fehlzeiten"))
        .add(_("Fehlzeiten"), _url("admin:fehlzeiten_fehlzeit_changelist"), "uhr", gross=True, bedingung=p("fehlzeiten.view_fehlzeit"))
        .add(_("Offene Entschuldigungen"), _url("admin:fehlzeiten_fehlzeit_changelist", query="?status__exact=offen"), "warnung",
             bedingung=p("fehlzeiten.view_fehlzeit"))
        .add(_("Fehlzeit erfassen"), _url("admin:fehlzeiten_fehlzeit_add"), "plus", bedingung=p("fehlzeiten.add_fehlzeit")),
    )

    # ------------------------------------------------------------ Unterricht
    mein_unterricht = Gruppe(_("Mein Unterricht"))
    if personal and sj:
        kurse = list(Unterricht.objects.filter(lehrkraft=personal, abschnitt__schuljahr=sj)
                     .select_related("fach", "gruppe", "abschnitt").order_by("abschnitt__nummer", "gruppe__name", "fach__reihenfolge"))
        for u in kurse:
            mein_unterricht.add(f"{u.fach.kuerzel} {u.gruppe.name}", _url("notenuebersicht", u.pk), "buch", gross=len(kurse) <= 3,
                                hinweis=_("Notenübersicht %(fach)s %(gruppe)s, %(abschnitt)s") % {
                                    "fach": u.fach.lokal_name, "gruppe": u.gruppe.name, "abschnitt": u.abschnitt.lokal_name})
    unterricht = _karte(
        "unterricht", pgettext("Menüband", "Unterricht"),
        mein_unterricht,
        Gruppe(_("Bewertung"))
        .add(_("Leistungsnachweise"), _url("admin:noten_leistungsnachweis_changelist"), "stift", gross=True,
             bedingung=p("noten.view_leistungsnachweis"))
        .add(_("Neuer Leistungsnachweis"), _url("admin:noten_leistungsnachweis_add"), "plus", bedingung=p("noten.add_leistungsnachweis"))
        .add(_("Bewertungsordner"), _url("admin:noten_bewertungsordner_changelist"), "ordner", bedingung=p("noten.view_bewertungsordner"))
        .add(_("Einzelnoten"), _url("admin:noten_note_changelist"), "liste", bedingung=p("noten.view_note")),
        Gruppe(_("Zeugnis"))
        .add(_("Zeugnisnoten"), _url("admin:noten_zeugnisnote_changelist"), "zeugnis", gross=True, bedingung=p("noten.view_zeugnisnote")),
        Gruppe(_("Nachmittag"))
        .add(_("AG-Angebote"), _url("admin:nachmittag_agangebot_changelist"), "ball", gross=True, bedingung=p("nachmittag.view_agangebot"))
        .add(_("AG-Wünsche"), _url("admin:nachmittag_agwahl_changelist"), "liste", bedingung=p("nachmittag.view_agwahl"))
        .add(_("Zuteilungen"), _url("admin:nachmittag_agzuteilung_changelist"), "haken", bedingung=p("nachmittag.view_agzuteilung")),
        Gruppe(_("Einstellungen"))
        .add(_("Unterrichtsverteilung"), _url("admin:noten_unterricht_changelist"), "tafel", gross=True,
             bedingung=verwaltung and p("noten.view_unterricht"))
        .add(_("Fächer"), _url("admin:stammdaten_fach_changelist"), "buch", bedingung=verwaltung and p("stammdaten.view_fach"))
        .add(_("Notenskalen"), _url("admin:noten_notenskala_changelist"), "lineal", bedingung=verwaltung and p("noten.view_notenskala"))
        .add(_("Gewichtungsvorlagen"), _url("admin:noten_gewichtungsvorlage_changelist"), "regler",
             bedingung=verwaltung and p("noten.view_gewichtungsvorlage")),
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

    # ------------------------------------------------------------ Finanzen
    finanzen = ist_finanzen(user)
    finanzen_karte = _karte(
        "finanzen", _("Finanzen"),
        Gruppe(_("Schulgeld"))
        .add(_("Rechnungsempfänger"), _url("admin:stammdaten_beziehung_changelist", query="?rechnungsempfaenger__exact=1"),
             "personen", gross=True, bedingung=finanzen and p("stammdaten.view_beziehung"))
        .add(_("Elternprofile"), _url("admin:stammdaten_elternprofil_changelist"), "liste",
             bedingung=finanzen and p("stammdaten.view_elternprofil"))
        .add(_("Schüler:innen"), _url("admin:stammdaten_schuelerprofil_changelist"), "personen",
             bedingung=finanzen and not verwaltung and p("stammdaten.view_schuelerprofil")),
        Gruppe(_("Verträge"))
        .add(_("Dienstleister"), _url("admin:stammdaten_dienstleister_changelist"), "gebaeude", gross=True,
             bedingung=finanzen and p("stammdaten.view_dienstleister"))
        .add(_("Vertragsunterlagen"), _url("admin:stammdaten_dokument_changelist", query="?kategorie__exact=vertrag"), "klammer",
             bedingung=finanzen and p("stammdaten.view_dokument")),
    )

    # ------------------------------------------------------------ Verwaltung
    verwaltung_karte = _karte(
        "verwaltung", _("Verwaltung"),
        Gruppe(_("Übersicht"))
        .add(_("Alle Bereiche"), _url("admin:index"), "zahnrad", gross=True, bedingung=admin),
        Gruppe(_("Schuljahr"))
        .add(_("Schuljahre"), _url("admin:stammdaten_schuljahr_changelist"), "kalender", gross=True,
             bedingung=verwaltung and p("stammdaten.view_schuljahr"))
        .add(_("Zeitraster"), _url("admin:fehlzeiten_stunde_changelist"), "uhr", bedingung=verwaltung and p("fehlzeiten.view_stunde"))
        .add(_("Bildungsgänge"), _url("admin:stammdaten_bildungsgang_changelist"), "treppe", bedingung=verwaltung and p("stammdaten.view_bildungsgang"))
        .add(_("Abschlussarten"), _url("admin:stammdaten_abschlussart_changelist"), "zeugnis", bedingung=verwaltung and p("stammdaten.view_abschlussart")),
        Gruppe(_("Datenfelder"))
        .add(_("Eigene Felder"), _url("admin:stammdaten_zusatzfeld_changelist"), "regler", gross=True,
             bedingung=p("stammdaten.view_zusatzfeld"), hinweis=_("Zusatzfelder für Schüler:innen, Personal und Eltern")),
        Gruppe(_("Benutzer und Rechte"))
        .add(_("Benutzerkonten"), _url("admin:auth_user_changelist"), "schluessel", gross=True, bedingung=p("auth.view_user"))
        .add(_("Rollen"), _url("admin:auth_group_changelist"), "schild", bedingung=p("auth.view_group"))
        .add(_("Rollen und Rechte"), _url("rollen"), "liste", bedingung=ist_systemverwaltung(user),
             hinweis=_("Übersicht: welche Rolle was darf")),
    )

    karten = [k for k in (start, schueler, unterricht, foerderung, personal_karte, finanzen_karte, verwaltung_karte) if k]
    aktiv = _aktive_karte(request.path, karten)
    _aktiven_befehl_markieren(request.get_full_path(), karten)
    from . import rollen as R

    namen = set(user.groups.values_list("name", flat=True))
    rollen = [str(R.ANZEIGE[n]) for n in R.REIHENFOLGE if n in namen] + sorted(n for n in namen if n not in R.ANZEIGE)
    if user.is_superuser:
        rollen.insert(0, _("Vollzugriff"))
    return {"karten": karten, "aktiv": aktiv, "rollen": rollen}


PFAD_REGELN = [("/klassen/", "schueler"), ("/schueler/", "schueler"), ("/stufe/", "schueler"), ("/noten/", "unterricht"),
               ("/rollen/", "verwaltung"),
               ("/foerderung/", "foerderung"), ("/verwaltung/", "verwaltung")]


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
