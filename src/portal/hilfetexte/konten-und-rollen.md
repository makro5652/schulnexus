---
titel: Benutzerkonto anlegen und Rollen vergeben
art: anleitung
kurz: Konto anlegen, mit der Person verknüpfen, Rollen vergeben (auch für viele Konten), Einzelrechte, Passwort und Sperre
stichworte: Benutzer, Konto, Anmeldung, Rolle, Recht, Einzelrecht, Passwort zurücksetzen, sperren, entsperren, Sammelaktion, IT
reihenfolge: 13
pfade: /system/benutzer/, /verwaltung/auth/
---
Konten und Rechte verwaltet die **IT-Administration**. Alle Änderungen stehen im Protokoll.

## 1. Konto anlegen

1. **System › Benutzer und Rechte › Benutzerkonten** › „Benutzer hinzufügen“ (oder auf der Seite **Konten und Rechte** „Neues Konto anlegen“).
2. **Benutzername** und ein vorläufiges **Passwort** vergeben, speichern.
3. Im folgenden Formular Vor- und Nachname, E-Mail und die Verknüpfung mit der **Person** (Personalakte) eintragen. Ohne Personalakte und ohne Verwaltungszugang kann sich ein Konto nicht im Portal anmelden.

> Für neue Beschäftigte zuerst unter **Personal › Einstellen** die Personalakte anlegen, dann das Konto.

## 2. Rollen vergeben

**System › Benutzer und Rechte › Konten und Rechte** › Benutzername anklicken › **Rollen**: Rollen ankreuzen, „Konto aktiv“ prüfen, **Rollen speichern**. Unter jeder Rolle steht kurz, was sie darf; die Übersicht steht in [Rollen: Wer darf was?](hilfe:rollen).

- Die Rolle **IT-Administration** gibt Vollzugriff.
- Sie können sich die eigene IT-Rolle nicht entziehen und das eigene Konto nicht sperren.
- Es muss immer mindestens ein aktives Konto mit Vollzugriff bleiben.

## 3. Viele Konten auf einmal ändern

Auf der Seite **Konten und Rechte**:

1. Mit **Suche**, **Rolle**, **Status** und **Merkmal** filtern, zum Beispiel Rolle „Lehrer:in“.
2. Konten ankreuzen – einzeln, mit Umschalt+Klick als Bereich oder mit „alle angezeigten Konten auswählen“.
3. **Aktion für die Auswahl** wählen: Rolle hinzufügen, Rolle entziehen, Konten sperren, Konten entsperren, Zwei-Faktor-Anmeldung verpflichtend oder freiwillig machen. Bei Rollen-Aktionen die **Rolle** wählen.
4. **Anwenden** und bestätigen.

Andere Rollen der Konten bleiben erhalten. Konten, für die eine Schutzregel greift (zum Beispiel Ihr eigenes), werden übersprungen und genannt.

Nützliche Merkmale: „noch nie angemeldet“ (vergessene Konten), „ohne Rolle“, „Zwei-Faktor Pflicht, noch offen“.

## 4. Einzelrechte

Im Konto unter **Einzelrechte**: je Bereich (ansehen, anlegen, ändern, löschen, dazu Sonderrechte).

- „ja (Rolle)“ bzw. „nein“ ist der Stand aus den Rollen.
- **+ erteilen** gibt ein Recht zusätzlich, **− entziehen** nimmt es trotz Rolle weg.
- Suchfeld („Fehlzeiten“) und „nur Abweichungen von der Rolle“ helfen beim Finden.

> Sichtbarkeitsregeln nach Klasse und Stufe (zum Beispiel „Klassenleitung sieht die Akte ihrer Klasse“) hängen an der Rolle und bleiben von Einzelrechten unberührt. Für Konten mit Vollzugriff gelten Einzelrechte nicht.

## 5. Passwort vergessen, Konto sperren

- **Passwort zurücksetzen** im Konto erzeugt ein vorläufiges Passwort, das nur einmal angezeigt wird. Bitte persönlich übergeben; die Person ändert es nach der Anmeldung.
- **Zwei-Faktor zurücksetzen**, wenn das Telefon verloren ist; mit „verpflichtend“ muss die Person sie bei der nächsten Anmeldung neu einrichten.
- **Sperren** statt löschen, wenn jemand die Schule verlässt – so bleiben Protokolle und Verweise erhalten.

## Rechte einer Rolle ändern

**System › Rollen** ändert die Rechte einer Rolle für alle Konten mit dieser Rolle. Beim Neustart ergänzt Schulnexus nur fehlende Standardrechte; eigene Anpassungen bleiben. Auf die Standardrechte zurücksetzen kann die IT mit `manage.py grundeinrichtung --rechte-zuruecksetzen`.
