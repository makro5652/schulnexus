"""Textvorlagen für automatische Nachrichten – werden beim Anzeigen in der Sprache der Leserin / des Lesers erzeugt."""
from django.utils.translation import gettext as _, ngettext

EINHEITEN = {
    "fehltage": lambda n: ngettext("Fehltag", "Fehltage", n),
    "fehlstunden": lambda n: ngettext("Fehlstunde", "Fehlstunden", n),
    "verspaetungen": lambda n: ngettext("Verspätung", "Verspätungen", n),
    "verspaetungsminuten": lambda n: ngettext("Minute Verspätung", "Minuten Verspätung", n),
}


def zeitraum_text(daten):
    from stammdaten.models import Abschnitt, Schuljahr

    if daten.get("zeitraum") == "halbjahr":
        a = Abschnitt.objects.filter(pk=daten.get("zeitraum_id")).select_related("schuljahr").first()
        return f"{a.lokal_name} {a.schuljahr}" if a else ""
    s = Schuljahr.objects.filter(pk=daten.get("zeitraum_id")).first()
    return _("Schuljahr %(sj)s") % {"sj": s} if s else ""


def zaehlung_text(zaehlung):
    return {"nicht_entschuldigt": _("Gezählt werden nicht entschuldigte Einträge (offen oder unentschuldigt)."),
            "unentschuldigt": _("Gezählt werden nur unentschuldigte Einträge.")}.get(zaehlung, "")


def betreff_aus_vorlage(vorlage, daten):
    if vorlage == "zeugnis":
        return _("Zeugnis %(zeitraum)s – bitte Erhalt bestätigen") % {"zeitraum": zeitraum_text(daten)}
    if vorlage == "fehlzeiten":
        if daten.get("merkmal", "").startswith("verspaetung"):
            return _("Verspätungen von %(vorname)s") % {"vorname": daten.get("vorname", "")}
        return _("Fehlzeiten von %(vorname)s") % {"vorname": daten.get("vorname", "")}
    return ""


def text_aus_vorlage(vorlage, daten):
    if vorlage == "zeugnis":
        art = _("Jahreszeugnis") if daten.get("zeugnis_art") == "jahr" else _("Halbjahreszeugnis")
        return _(
            "Sehr geehrte Eltern und Erziehungsberechtigte,\n\n"
            "%(vorname)s hat das %(art)s für %(zeitraum)s erhalten. Bitte bestätigen Sie mit dem Knopf unten, "
            "dass Ihnen das Zeugnis vorgelegt wurde.\n\n"
            "Bei Fragen können Sie direkt auf diese Nachricht antworten."
        ) % {"vorname": daten.get("vorname", ""), "art": art, "zeitraum": zeitraum_text(daten)}
    if vorlage == "fehlzeiten":
        merkmal = daten.get("merkmal", "")
        wert, schwelle = int(daten.get("wert", 0)), int(daten.get("schwelle", 0))
        einheit = EINHEITEN.get(merkmal, lambda n: "")
        teile = [
            _("Sehr geehrte Eltern und Erziehungsberechtigte,"),
            _("für %(vorname)s wurden bisher %(wert)s %(einheit)s erfasst (Zeitraum: %(zeitraum)s). Damit ist die Schwelle "
              "von %(schwelle)s %(einheit_schwelle)s erreicht, ab der die Schule die Eltern automatisch informiert.")
            % {"vorname": daten.get("vorname", ""), "zeitraum": zeitraum_text(daten), "wert": wert, "einheit": einheit(wert),
               "schwelle": schwelle, "einheit_schwelle": einheit(schwelle)},
        ]
        z = zaehlung_text(daten.get("zaehlung"))
        if z:
            teile[-1] += " " + z
        teile.append(_("Bitte sprechen Sie mit Ihrem Kind darüber. Bei Fragen wenden Sie sich an die Klassenleitung "
                       "oder antworten Sie direkt auf diese Nachricht."))
        if daten.get("zusatztext"):
            teile.append(daten["zusatztext"])
        return "\n\n".join(teile)
    return ""
