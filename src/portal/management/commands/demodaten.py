"""
Demo-Datensatz mit ERFUNDENEN Personen zum Ausprobieren.
Niemals auf einem System mit echten Schülerdaten ausführen.
"""
import os
import random
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from fehlzeiten.models import Fehlzeit, Stunde
from nachmittag.models import AGAngebot, AGWahl
from nachmittag.zuteilung import lose_zuteilen
from noten.models import (
    Bewertungsordner,
    Gewichtungsvorlage,
    Leistungskategorie,
    Leistungsnachweis,
    Note,
    Notenschluessel,
    Notenskala,
    Schluesselschwelle,
    Unterricht,
)
from stammdaten.models import (
    Abschnitt,
    Beziehung,
    Einwilligung,
    Fach,
    Gruppe,
    Mitgliedschaft,
    Person,
    Personalprofil,
    Schuelerprofil,
    Schuljahr,
)

VORNAMEN = [
    "Amani", "Ben", "Clara", "David", "Elif", "Finn", "Grace", "Hannah", "Imani", "Jonas", "Kiara", "Leon",
    "Malia", "Noah", "Olivia", "Paul", "Rehema", "Samuel", "Tara", "Umar", "Valentina", "Wanjiru", "Yusuf", "Zoe",
    "Aiden", "Baraka", "Charlotte", "Daniel", "Emma", "Felix", "Jabari", "Lena", "Mia", "Nia", "Otieno", "Sophie",
]
NACHNAMEN = [
    "Achieng", "Bauer", "Chege", "Dietrich", "Engel", "Fischer", "Gitau", "Hoffmann", "Imbuga", "Jung",
    "Kamau", "Lehmann", "Mwangi", "Neumann", "Odhiambo", "Peters", "Ruto", "Schmidt", "Thiong'o", "Ullrich",
    "Vogel", "Wanjiku", "Zimmermann", "Becker", "Kariuki", "Meyer", "Njoroge", "Schulz", "Wagner", "Kiprop",
]
SCHLUESSEL = [
    ("1+", 95), ("1", 90), ("1-", 85), ("2+", 80), ("2", 75), ("2-", 70), ("3+", 65), ("3", 60), ("3-", 55),
    ("4+", 50), ("4", 45), ("4-", 40), ("5+", 33), ("5", 26), ("5-", 20), ("6", 0),
]


class Command(BaseCommand):
    help = "Legt einen Demo-Datensatz mit erfundenen Personen an."

    def add_arguments(self, parser):
        parser.add_argument("--passwort", default=os.environ.get("DEMO_PASSWORT", "Schule-Demo-2026"))

    @transaction.atomic
    def handle(self, *args, **opts):
        if Schuljahr.objects.filter(name="2026/27").exists():
            self.stdout.write("Demo-Daten sind bereits vorhanden – nichts zu tun.")
            return

        call_command("grundeinrichtung", stdout=self.stdout)
        rng = random.Random(42)
        pw = opts["passwort"]

        sj = Schuljahr.objects.create(name="2026/27", beginn=date(2026, 8, 17), ende=date(2027, 6, 25), aktiv=True)
        hj1 = Abschnitt.objects.create(schuljahr=sj, name="1. Halbjahr", nummer=1, beginn=date(2026, 8, 17), ende=date(2027, 1, 29))
        Abschnitt.objects.create(schuljahr=sj, name="2. Halbjahr", nummer=2, beginn=date(2027, 2, 1), ende=date(2027, 6, 25))

        raster = [((7, 40), (8, 25)), ((8, 30), (9, 15)), ((9, 35), (10, 20)), ((10, 25), (11, 10)),
                  ((11, 30), (12, 15)), ((12, 20), (13, 5)), ((13, 45), (14, 30)), ((14, 35), (15, 20))]
        for i, (b, e) in enumerate(raster, start=1):
            Stunde.objects.create(schuljahr=sj, nummer=i, beginn=time(*b), ende=time(*e))

        faecher = {}
        for i, (k, n) in enumerate([("D", "Deutsch"), ("E", "Englisch"), ("M", "Mathematik"), ("CH", "Chemie"),
                                    ("BIO", "Biologie"), ("PH", "Physik"), ("ETH", "Ethik"), ("REL", "Religion"),
                                    ("SW", "Kiswahili")]):
            faecher[k], _ = Fach.objects.get_or_create(kuerzel=k, defaults={"name": n, "reihenfolge": (i + 1) * 10})

        # Personal mit Benutzerkonten
        def personal(kuerzel, vorname, nachname, funktion="lehrkraft", benutzername=None, rolle="Lehrkraft"):
            user = None
            if benutzername:
                user = User.objects.create_user(benutzername, password=pw, is_staff=True, first_name=vorname, last_name=nachname)
                user.groups.add(Group.objects.get(name=rolle))
            p = Person.objects.create(vorname=vorname, nachname=nachname, email=f"{kuerzel.lower()}@schule.example", benutzer=user)
            return Personalprofil.objects.create(person=p, kuerzel=kuerzel, funktion=funktion)

        kro = personal("KRA", "Martin", "Krause", benutzername="lehrkraft")
        mue = personal("MUE", "Sabine", "Müller")
        sch = personal("SCH", "Thomas", "Schwarz")
        oko = personal("OKO", "Grace", "Okoth")
        bra = personal("BRA", "Peter", "Brandt")
        personal("SEK", "Mercy", "Wambui", funktion="verwaltung", benutzername="verwaltung", rolle="Verwaltung")

        # Klassen und Schüler:innen
        klassen = {
            "8a": (8, mue, 10), "9a": (9, kro, 13), "9b": (9, sch, 12),
        }
        gruppen, nr = {}, 2026000
        namen_pool = [(v, n) for v in VORNAMEN for n in NACHNAMEN]
        rng.shuffle(namen_pool)
        for name, (jg, leitung, anzahl) in klassen.items():
            g = Gruppe.objects.create(schuljahr=sj, typ=Gruppe.STAMMKLASSE, name=name, kuerzel=name, jahrgang=jg, leitung=leitung)
            gruppen[name] = g
            for _ in range(anzahl):
                vorname, nachname = namen_pool.pop()
                nr += 1
                geb = date(2026 - jg - 6, rng.randint(1, 12), rng.randint(1, 28))
                p = Person.objects.create(vorname=vorname, nachname=nachname, geburtsdatum=geb, ort="Nairobi")
                s = Schuelerprofil.objects.create(person=p, schuelernummer=str(nr), eintrittsdatum=date(2022, 8, 15))
                Mitgliedschaft.objects.create(gruppe=g, schueler=s, von=sj.beginn)
                eltern = []
                for art, vn in [("mutter", rng.choice(VORNAMEN)), ("vater", rng.choice(VORNAMEN))][: rng.choice([1, 2, 2])]:
                    e = Person.objects.create(
                        vorname=vn, nachname=nachname, email=f"{vn.lower()}.{nachname.lower().replace(chr(39), '')}@eltern.example",
                        telefon=f"+254 7{rng.randint(10, 99)} {rng.randint(100, 999)} {rng.randint(100, 999)}", ort="Nairobi",
                        sprache=rng.choice(["de", "de", "en"]),
                    )
                    Beziehung.objects.create(schueler=s, person=e, art=art, notfallkontakt=not eltern)
                    eltern.append(e)
                if rng.random() < 0.8:
                    Einwilligung.objects.create(schueler=s, zweck="foto_intern", erteilt_durch=eltern[0], erteilt_am=date(2026, 8, 20))

        # Lerngruppen Ethik / Religion aus 9a + 9b
        ethik = Gruppe.objects.create(schuljahr=sj, typ=Gruppe.LERNGRUPPE, name="Ethik 9", jahrgang=9, leitung=oko)
        reli = Gruppe.objects.create(schuljahr=sj, typ=Gruppe.LERNGRUPPE, name="Religion 9", jahrgang=9, leitung=bra)
        for lg in (ethik, reli):
            lg.gebildet_aus.set([gruppen["9a"], gruppen["9b"]])
        for k in ("9a", "9b"):
            for s in gruppen[k].aktuelle_mitglieder(stichtag=sj.beginn):
                Mitgliedschaft.objects.create(gruppe=rng.choice([ethik, reli]), schueler=s, von=sj.beginn)

        # Noten-Grundlagen
        sek1 = Notenskala.objects.get(name__startswith="Sek I –")
        schluessel = Notenschluessel.objects.create(
            name="Beispielschlüssel Sek I (bitte durch DSN-Schlüssel ersetzen)", skala=sek1,
            beschreibung="Nur zu Demonstrationszwecken.",
        )
        stufen = {s.bezeichnung: s for s in sek1.stufen.all()}
        for b, ab in SCHLUESSEL:
            Schluesselschwelle.objects.create(schluessel=schluessel, min_prozent=Decimal(ab), stufe=stufen[b])

        nawi = Gewichtungsvorlage.objects.create(name="Naturwissenschaften Sek I", beschreibung="Beispiel: 50 % schriftlich, 50 % sonstige Leistungen")
        Leistungskategorie.objects.create(vorlage=nawi, name="Schriftlich", anteil=Decimal(50))
        Leistungskategorie.objects.create(vorlage=nawi, name="Sonstige Mitarbeit", anteil=Decimal(50))
        haupt = Gewichtungsvorlage.objects.create(name="Hauptfächer Sek I", beschreibung="Beispiel: 60 % schriftlich, 40 % sonstige")
        Leistungskategorie.objects.create(vorlage=haupt, name="Schriftlich", anteil=Decimal(60))
        Leistungskategorie.objects.create(vorlage=haupt, name="Sonstige Leistungen", anteil=Decimal(40))

        def unterricht(gruppe, fach, lehrkraft, vorlage=nawi):
            return Unterricht.objects.create(abschnitt=hj1, gruppe=gruppe, fach=faecher[fach], lehrkraft=lehrkraft, skala=sek1, gewichtung=vorlage)

        ch9a = unterricht(gruppen["9a"], "CH", kro)
        ch9b = unterricht(gruppen["9b"], "CH", kro)
        unterricht(gruppen["9a"], "BIO", kro)
        unterricht(gruppen["9a"], "M", mue, haupt)
        unterricht(gruppen["9a"], "D", sch, haupt)
        unterricht(ethik, "ETH", oko)
        unterricht(reli, "REL", bra)

        # Beispielnoten in Chemie 9a und 9b
        # Ordnerstruktur: Schriftlich (50) | Sonstige Mitarbeit (50) › Quartal 1 (1), Quartal 2 (1)
        for u in (ch9a, ch9b):
            schriftlich = u.bewertungsordner.get(name="Schriftlich", eltern=None)
            mitarbeit = u.bewertungsordner.get(name="Sonstige Mitarbeit", eltern=None)
            q1 = Bewertungsordner.objects.create(unterricht=u, eltern=mitarbeit, name="Quartal 1", gewicht=1, reihenfolge=10)
            Bewertungsordner.objects.create(unterricht=u, eltern=mitarbeit, name="Quartal 2", gewicht=1, reihenfolge=20)
            ka = Leistungsnachweis.objects.create(ordner=schriftlich, titel="1. Klassenarbeit", datum=date(2026, 9, 24), schluessel=schluessel, max_be=Decimal(40))
            test = Leistungsnachweis.objects.create(ordner=schriftlich, titel="Test Atombau", datum=date(2026, 10, 8), gewicht=Decimal("0.5"), schluessel=schluessel, max_be=Decimal(20))
            muendl = Leistungsnachweis.objects.create(ordner=q1, titel="Mitarbeit September", datum=date(2026, 9, 30))
            prot = Leistungsnachweis.objects.create(ordner=q1, titel="Protokoll Flammenfärbung", datum=date(2026, 10, 2), gewicht=Decimal("0.5"))
            muendlich_stufen = [s for s in sek1.stufen.all() if s.bezeichnung in {"1", "1-", "2+", "2", "2-", "3+", "3", "3-", "4", "4-", "5"}]
            for i, s in enumerate(u.schueler()):
                staerke = rng.gauss(0.68, 0.15) if i else 0.30  # erste Person: Gefährdungsbeispiel
                for ln in (ka, test):
                    if ln is ka and i == 3:
                        Note.objects.create(leistungsnachweis=ln, schueler=s, sonderstatus="entschuldigt", kommentar="Attest liegt vor")
                        continue
                    anteil = min(max(rng.gauss(staerke, 0.08), 0.05), 1)
                    Note.objects.create(leistungsnachweis=ln, schueler=s, erreichte_be=(ln.max_be * Decimal(str(round(anteil, 3)))).quantize(Decimal("0.5")))
                for ln in (muendl, prot):
                    idx = min(max(int(rng.gauss((1 - staerke) * len(muendlich_stufen), 1.5)), 0), len(muendlich_stufen) - 1)
                    Note.objects.create(leistungsnachweis=ln, schueler=s, stufe=muendlich_stufen[idx])

        # Fehlzeiten
        alle = list(Schuelerprofil.objects.all())
        sekretariat = User.objects.get(username="verwaltung")
        start_tag = date(2026, 9, 1)
        for _ in range(40):
            s = rng.choice(alle)
            tag = start_tag + timedelta(days=rng.randint(0, 40))
            while tag.weekday() >= 5:
                tag += timedelta(days=1)
            art = rng.choice([Fehlzeit.GANZTAEGIG, Fehlzeit.GANZTAEGIG, Fehlzeit.STUNDEN, Fehlzeit.VERSPAETUNG])
            fz = Fehlzeit(schueler=s, art=art, datum_von=tag, erfasst_von=sekretariat,
                          status=rng.choice(["entschuldigt", "entschuldigt", "unentschuldigt", "offen"]),
                          quelle=rng.choice(["lehrkraft", "eltern", "sekretariat"]))
            if art == Fehlzeit.GANZTAEGIG:
                fz.datum_bis = tag + timedelta(days=rng.choice([0, 0, 1, 2]))
                fz.grund = rng.choice(["Krankheit", "Arzttermin", "Familiäre Gründe", ""])
            elif art == Fehlzeit.STUNDEN:
                fz.stunde_von = rng.randint(1, 5)
                fz.stunde_bis = fz.stunde_von + rng.randint(0, 2)
                fz.grund = rng.choice(["Arzttermin", "Unwohlsein", ""])
            else:
                fz.minuten = rng.choice([5, 10, 15, 25])
                fz.grund = rng.choice(["Verkehr", "Bus verspätet", ""])
            fz.full_clean()
            fz.save()

        # Nachmittagsprogramm mit Wünschen und Losverfahren
        ags = [
            AGAngebot.objects.create(abschnitt=hj1, titel="Robotik", leitung=kro, wochentag=1, beginn=time(14, 45), ende=time(16, 15), raum="NW-Labor", kapazitaet=8, jahrgang_min=7, jahrgang_max=10),
            AGAngebot.objects.create(abschnitt=hj1, titel="Theater", leitung=sch, wochentag=2, beginn=time(14, 45), ende=time(16, 15), raum="Aula", kapazitaet=12),
            AGAngebot.objects.create(abschnitt=hj1, titel="Fußball", externe_leitung="Coach Otieno", wochentag=3, beginn=time(14, 45), ende=time(16, 15), raum="Sportplatz", kapazitaet=14),
            AGAngebot.objects.create(abschnitt=hj1, titel="Chor", leitung=bra, wochentag=0, beginn=time(14, 45), ende=time(15, 45), raum="Musikraum", kapazitaet=10),
        ]
        beliebtheit = [5, 2, 3, 1]
        for s in alle:
            wahl = []
            pool = list(ags)
            gewichte = list(beliebtheit)
            for prio in (1, 2, 3):
                a = rng.choices(pool, weights=gewichte)[0]
                i = pool.index(a)
                pool.pop(i)
                gewichte.pop(i)
                wahl.append(AGWahl(schueler=s, angebot=a, prioritaet=prio))
            AGWahl.objects.bulk_create(wahl)
        ergebnis = lose_zuteilen(hj1, seed=7)

        self.stdout.write(self.style.SUCCESS(
            f"Demo-Daten angelegt: {len(alle)} Schüler:innen, {Person.objects.count()} Personen, "
            f"{Fehlzeit.objects.count()} Fehlzeiten, AG-Zuteilung {ergebnis.zugeteilt} "
            f"({len(ergebnis.ohne_platz)} ohne Platz)."
        ))
        self.stdout.write(f"Demo-Konten: 'lehrkraft' (Klassenleitung 9a, Chemie) und 'verwaltung' – Passwort: {pw}")
