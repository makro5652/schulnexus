"""
Zeilenweise Rechte für Zeugnisse, Kommentare und Konferenzen.

- Zeugnisnoten setzt die Lehrkraft des Unterrichts (Schulleitung ebenfalls).
- Zeugnis bearbeiten (Bemerkungen, GeR, Fehltage, Datum): Klassenleitung, Stufenkoordination, Sekretariat/
  Verwaltungsleitung, Schulleitung. Den Kommentar schreiben Klassenleitung, Stufenkoordination und Schulleitung.
- Kommentar lesen und abzeichnen: alle Lehrkräfte, die die Schülerin / den Schüler im Halbjahr unterrichten.
- Freigabe: Schulleitung und Stufenkoordination (eigene Jahrgänge), sofern das Recht „Kann Zeugnisse freigeben“ besteht.
- Konferenz leiten (anlegen, Beschlüsse, abschließen): Schulleitung, Stufenkoordination; ansehen zusätzlich alle
  Lehrkräfte der Klasse und die Verwaltung.
"""
from noten.models import Unterricht

from portal.rechte import ist_schulleitung, ist_verwaltung, koordinierte_jahrgaenge, personal_von


def ist_klassenleitung(user, klasse):
    p = personal_von(user)
    return bool(p and klasse and klasse.leitung_id == p.pk)


def ist_stufe(user, jahrgang):
    return jahrgang is not None and jahrgang in koordinierte_jahrgaenge(user)


def lehrkraefte_ids(schueler, abschnitt):
    from .noten import unterrichte_fuer

    return set(unterrichte_fuer(schueler, abschnitt).values_list("lehrkraft_id", flat=True))


def unterrichtet(user, schueler, abschnitt):
    p = personal_von(user)
    return bool(p and p.pk in lehrkraefte_ids(schueler, abschnitt))


def _jahrgang(z):
    return z.jahrgang if z.jahrgang is not None else getattr(z.klasse, "jahrgang", None)


def darf_klasse_sehen(user, klasse):
    return (ist_verwaltung(user) or ist_schulleitung(user) or ist_klassenleitung(user, klasse)
            or ist_stufe(user, klasse.jahrgang)) and user.has_perm("zeugnisse.view_zeugnis")


def darf_zeugnis_sehen(user, z):
    if not user.has_perm("zeugnisse.view_zeugnis"):
        return False
    return (ist_verwaltung(user) or ist_klassenleitung(user, z.klasse) or ist_stufe(user, _jahrgang(z))
            or unterrichtet(user, z.schueler, z.abschnitt))


def darf_zeugnis_bearbeiten(user, z):
    if z.freigegeben or not user.has_perm("zeugnisse.change_zeugnis"):
        return False
    return ist_verwaltung(user) or ist_klassenleitung(user, z.klasse) or ist_stufe(user, _jahrgang(z))


def darf_kommentar_schreiben(user, z):
    if z.freigegeben or not user.has_perm("zeugnisse.change_zeugnis"):
        return False
    return ist_schulleitung(user) or ist_klassenleitung(user, z.klasse) or ist_stufe(user, _jahrgang(z))


def darf_abzeichnen(user, z):
    p = personal_von(user)
    return (bool(p) and user.has_perm("zeugnisse.add_abzeichnung") and not z.freigegeben and bool(z.kommentar.strip())
            and (p.pk in lehrkraefte_ids(z.schueler, z.abschnitt) or ist_klassenleitung(user, z.klasse)))


def darf_anmerken(user, z):
    return user.has_perm("zeugnisse.add_anmerkung") and not z.freigegeben and darf_zeugnis_sehen(user, z)


def darf_freigeben(user, z):
    if not user.has_perm("zeugnisse.freigeben_zeugnis"):
        return False
    return ist_schulleitung(user) or ist_stufe(user, _jahrgang(z))


def darf_zeugnisnote_setzen(user, unterricht: Unterricht):
    if not (user.has_perm("noten.add_zeugnisnote") and user.has_perm("noten.change_zeugnisnote")):
        return False
    p = personal_von(user)
    return ist_schulleitung(user) or bool(p and unterricht.lehrkraft_id == p.pk)


def darf_konferenz_leiten(user, klasse):
    return user.has_perm("zeugnisse.change_konferenz") and (ist_schulleitung(user) or ist_stufe(user, klasse.jahrgang))


def darf_konferenz_sehen(user, konferenz):
    if not user.has_perm("zeugnisse.view_konferenz"):
        return False
    klasse = konferenz.klasse
    if ist_verwaltung(user) or ist_klassenleitung(user, klasse) or ist_stufe(user, klasse.jahrgang):
        return True
    p = personal_von(user)
    return bool(p and (Unterricht.objects.filter(abschnitt=konferenz.abschnitt, gruppe=klasse, lehrkraft=p).exists()
                       or konferenz.teilnehmende.filter(pk=p.pk).exists()))
