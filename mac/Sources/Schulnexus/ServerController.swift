import Foundation
import SwiftUI

enum SchulnexusFehler: LocalizedError {
    case keinPython
    case schritt(String, Int32)
    case startFehlgeschlagen(String)
    case zeitueberschreitung

    var errorDescription: String? {
        switch self {
        case .keinPython:
            return "Kein Python 3.12 oder neuer gefunden. Bitte installieren, z. B. mit „brew install python@3.13“ oder von python.org."
        case .schritt(let name, let code):
            return "Schritt „\(name)“ ist fehlgeschlagen (Code \(code)). Protokoll: \(Pfade.einrichtungsProtokoll.path)"
        case .startFehlgeschlagen(let text):
            return "Der Server konnte nicht starten. \(text) Protokoll: \(Pfade.serverProtokoll.path)"
        case .zeitueberschreitung:
            return "Der Server antwortet nicht. Protokoll: \(Pfade.serverProtokoll.path)"
        }
    }
}

/// Richtet Python-Umgebung und Daten ein, startet gunicorn lokal und beendet ihn beim Beenden der App.
@MainActor
final class ServerController: ObservableObject {
    static let shared = ServerController()

    enum Phase {
        case vorbereitung
        case laeuft(URL)
        case fehler(String)
    }

    @Published var phase: Phase = .vorbereitung
    @Published var status: String = "Starte …"
    @Published var neuerAdmin: Geheimnisse?
    @Published var reloadZaehler = 0

    private var serverProzess: Process?
    private var port: Int = 0

    // MARK: - Ablauf

    func starten() async {
        phase = .vorbereitung
        do {
            try Pfade.legeOrdnerAn()
            let (geheimnisse, neu) = try GeheimnisSpeicher.ladenOderErzeugen()
            if neu { neuerAdmin = geheimnisse }
            try legeEinstellungsdateiAn()

            status = "Prüfe Python …"
            let python = try findePython()

            status = "Übernehme Programmcode …"
            try codeAktualisieren()

            status = "Richte Python-Umgebung ein (beim ersten Start einige Minuten) …"
            try await venvEinrichten(python: python)

            port = try freierPort()
            let umgebung = baueUmgebung(geheimnisse: geheimnisse)

            status = "Richte Datenbank ein …"
            try await verwaltungsbefehl(["migrate", "--noinput"], umgebung: umgebung)
            try await verwaltungsbefehl(["collectstatic", "--noinput"], umgebung: umgebung)
            try await verwaltungsbefehl(["grundeinrichtung"], umgebung: umgebung)
            try await verwaltungsbefehl(["zeugnisnoten_automatisch"], umgebung: umgebung)
            if !geheimnisse.datenSchluessel.isEmpty {
                try await verwaltungsbefehl(["dateien_verschluesseln"], umgebung: umgebung)
            }
            try await pythonSkript("bootstrap_admin.py", umgebung: umgebung)

            status = "Starte Server …"
            try serverStarten(umgebung: umgebung)
            let adresse = URL(string: "http://127.0.0.1:\(port)/")!
            try await aufBereitschaftWarten(adresse)
            phase = .laeuft(adresse)
        } catch {
            phase = .fehler(error.localizedDescription)
        }
    }

    func neuLaden() {
        if case .laeuft = phase { reloadZaehler += 1 } else {
            Task { await starten() }
        }
    }

    func stoppen() {
        serverProzess?.terminate()
        serverProzess = nil
        try? Pfade.fileManager.removeItem(at: Pfade.serverPID)
    }

    /// Beendet einen Server aus einem früheren Lauf, der nach hartem Beenden der App übrig geblieben ist.
    private func verwaisteServerBeenden() {
        guard let text = try? String(contentsOf: Pfade.serverPID, encoding: .utf8),
              let pid = Int32(text.trimmingCharacters(in: .whitespacesAndNewlines)) else { return }
        if kill(pid, 0) == 0 {
            kill(pid, SIGTERM)
            usleep(1_500_000)
        }
        try? Pfade.fileManager.removeItem(at: Pfade.serverPID)
    }

    // MARK: - Python

    private func findePython() throws -> URL {
        var kandidaten = [
            "/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3",
        ]
        for version in [15, 14, 13, 12] {
            kandidaten.append("/opt/homebrew/bin/python3.\(version)")
            kandidaten.append("/usr/local/bin/python3.\(version)")
            kandidaten.append("/Library/Frameworks/Python.framework/Versions/3.\(version)/bin/python3")
        }
        for pfad in kandidaten where Pfade.fileManager.isExecutableFile(atPath: pfad) {
            if let v = pythonVersion(pfad), v >= 312 {
                return URL(fileURLWithPath: pfad)
            }
        }
        throw SchulnexusFehler.keinPython
    }

    /// Gibt z. B. 313 für Python 3.13 zurück, nil bei Fehler.
    private func pythonVersion(_ pfad: String) -> Int? {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: pfad)
        p.arguments = ["-c", "import sys; print(sys.version_info[0]*100+sys.version_info[1])"]
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = Pipe()
        do { try p.run() } catch { return nil }
        p.waitUntilExit()
        guard p.terminationStatus == 0 else { return nil }
        let text = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
        return Int(text.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    // MARK: - Code und Umgebung

    private func codeAktualisieren() throws {
        guard let quelle = Pfade.gebuendelt?.appendingPathComponent("app", isDirectory: true),
              Pfade.fileManager.fileExists(atPath: quelle.path) else {
            throw SchulnexusFehler.startFehlgeschlagen("Das App-Paket enthält keinen Programmcode.")
        }
        if Pfade.fileManager.fileExists(atPath: Pfade.code.path) {
            try Pfade.fileManager.removeItem(at: Pfade.code)
        }
        try Pfade.fileManager.copyItem(at: quelle, to: Pfade.code)
    }

    private func legeEinstellungsdateiAn() throws {
        guard !Pfade.fileManager.fileExists(atPath: Pfade.einstellungen.path) else { return }
        let vorlage = """
        # Schulnexus – Einstellungen der Desktop-App (Änderungen wirken beim nächsten Start).
        # Eine Zeile je Einstellung: NAME=WERT

        SCHULNAME=Meine Schule
        SCHULORT=Ort
        TIME_ZONE=Europe/Berlin

        # Elternkontakt und E-Mail sind in der Desktop-App aus.
        ELTERN_EMAIL_VERSAND=0
        ZEUGNIS_FEHLZEITEN=0
        DOKUMENT_MAX_MB=25

        """
        try vorlage.write(to: Pfade.einstellungen, atomically: true, encoding: .utf8)
    }

    private func liesEinstellungen() -> [String: String] {
        guard let text = try? String(contentsOf: Pfade.einstellungen, encoding: .utf8) else { return [:] }
        var ergebnis: [String: String] = [:]
        for zeile in text.split(whereSeparator: \.isNewline) {
            let s = zeile.trimmingCharacters(in: .whitespaces)
            guard !s.isEmpty, !s.hasPrefix("#"), let gleich = s.firstIndex(of: "=") else { continue }
            let name = s[..<gleich].trimmingCharacters(in: .whitespaces)
            let wert = s[s.index(after: gleich)...].trimmingCharacters(in: .whitespaces)
            ergebnis[name] = wert
        }
        return ergebnis
    }

    private func baueUmgebung(geheimnisse g: Geheimnisse) -> [String: String] {
        var env: [String: String] = [
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "HOME": Pfade.fileManager.homeDirectoryForCurrentUser.path,
            "LANG": "de_DE.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "DATABASE_URL": "sqlite:///" + Pfade.datenbank.path,
            "SECRET_KEY": g.secretKey,
            "DATEN_SCHLUESSEL": g.datenSchluessel,
            "MEDIA_ROOT": Pfade.dokumente.path,
            "MODUL_SICHERUNGEN": Pfade.modulsicherungen.path,
            "ADMIN_BENUTZER": g.adminBenutzer,
            "ADMIN_PASSWORT": g.adminPasswort,
            "DEBUG": "0",
            "HTTPS": "0",
            "ALLOWED_HOSTS": "127.0.0.1,localhost",
            "CSRF_TRUSTED_ORIGINS": "http://127.0.0.1:\(port),http://localhost:\(port)",
            "ELTERN_LINK_BASIS": "http://127.0.0.1:\(port)",
            "TIME_ZONE": TimeZone.current.identifier,
        ]
        // Benutzer-Einstellungen überschreiben die Vorgaben
        for (name, wert) in liesEinstellungen() { env[name] = wert }
        return env
    }

    private func venvEinrichten(python: URL) async throws {
        let anforderungen = try String(contentsOf: Pfade.gebuendelt!.appendingPathComponent("requirements.txt"), encoding: .utf8)
        let stempelSoll = "\(python.path)\n\(anforderungen)"
        let stempelIst = try? String(contentsOf: Pfade.stempel, encoding: .utf8)
        let venvPython = Pfade.venv.appendingPathComponent("bin/python")
        if stempelIst == stempelSoll, Pfade.fileManager.isExecutableFile(atPath: venvPython.path) { return }

        if Pfade.fileManager.fileExists(atPath: Pfade.venv.path) {
            try Pfade.fileManager.removeItem(at: Pfade.venv)
        }
        let anf = Pfade.support.appendingPathComponent("requirements.txt")
        try anforderungen.write(to: anf, atomically: true, encoding: .utf8)

        try await kommando(python, ["-m", "venv", Pfade.venv.path], cwd: Pfade.support, env: [:], schritt: "Python-Umgebung anlegen")
        try await kommando(venvPython, ["-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", anf.path],
                           cwd: Pfade.support, env: [:], schritt: "Abhängigkeiten installieren")
        try stempelSoll.write(to: Pfade.stempel, atomically: true, encoding: .utf8)
    }

    private func verwaltungsbefehl(_ args: [String], umgebung: [String: String]) async throws {
        let python = Pfade.venv.appendingPathComponent("bin/python")
        try await kommando(python, ["manage.py"] + args, cwd: Pfade.code, env: umgebung, schritt: args[0])
    }

    private func pythonSkript(_ name: String, umgebung: [String: String]) async throws {
        let python = Pfade.venv.appendingPathComponent("bin/python")
        try await kommando(python, [name], cwd: Pfade.code, env: umgebung, schritt: name)
    }

    // MARK: - Server

    private func serverStarten(umgebung: [String: String]) throws {
        verwaisteServerBeenden()
        let gunicorn = Pfade.venv.appendingPathComponent("bin/python")
        let p = Process()
        p.executableURL = gunicorn
        p.arguments = ["-m", "gunicorn", "config.wsgi:application",
                       "--bind", "127.0.0.1:\(port)", "--workers", "2", "--timeout", "120",
                       "--access-logfile", "-", "--error-logfile", "-"]
        p.currentDirectoryURL = Pfade.code
        p.environment = umgebung
        let protokoll = try protokollHandle(Pfade.serverProtokoll)
        p.standardOutput = protokoll
        p.standardError = protokoll
        p.terminationHandler = { [weak self] beendet in
            Task { @MainActor in
                guard let self, self.serverProzess === beendet else { return }
                self.serverProzess = nil
                if case .laeuft = self.phase {
                    self.phase = .fehler("Der Server wurde unerwartet beendet (Code \(beendet.terminationStatus)).")
                }
            }
        }
        try p.run()
        serverProzess = p
        try "\(p.processIdentifier)".write(to: Pfade.serverPID, atomically: true, encoding: .utf8)
    }

    private func aufBereitschaftWarten(_ adresse: URL) async throws {
        let gesundheit = adresse.appendingPathComponent("gesundheit/")
        for _ in 0..<240 {
            if serverProzess == nil { throw SchulnexusFehler.startFehlgeschlagen("Der Prozess ist beendet.") }
            var anfrage = URLRequest(url: gesundheit)
            anfrage.timeoutInterval = 2
            if let (_, antwort) = try? await URLSession.shared.data(for: anfrage),
               (antwort as? HTTPURLResponse)?.statusCode == 200 {
                return
            }
            try await Task.sleep(nanoseconds: 500_000_000)
        }
        throw SchulnexusFehler.zeitueberschreitung
    }

    // MARK: - Hilfsfunktionen

    private func freierPort() throws -> Int {
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { throw SchulnexusFehler.startFehlgeschlagen("Kein Socket verfügbar.") }
        defer { close(fd) }
        var adresse = sockaddr_in()
        adresse.sin_family = sa_family_t(AF_INET)
        adresse.sin_addr.s_addr = inet_addr("127.0.0.1")
        adresse.sin_port = 0
        let gebunden = withUnsafePointer(to: &adresse) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        guard gebunden == 0 else { throw SchulnexusFehler.startFehlgeschlagen("Kein freier Port.") }
        var laenge = socklen_t(MemoryLayout<sockaddr_in>.size)
        _ = withUnsafeMutablePointer(to: &adresse) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                getsockname(fd, $0, &laenge)
            }
        }
        return Int(UInt16(bigEndian: adresse.sin_port))
    }

    private func protokollHandle(_ url: URL) throws -> FileHandle {
        if !Pfade.fileManager.fileExists(atPath: url.path) {
            Pfade.fileManager.createFile(atPath: url.path, contents: nil)
        }
        let handle = try FileHandle(forWritingTo: url)
        try handle.seekToEnd()
        return handle
    }

    /// Führt ein Programm aus und protokolliert die Ausgabe. Wirft bei Fehlercode.
    private func kommando(_ exe: URL, _ args: [String], cwd: URL, env: [String: String], schritt: String) async throws {
        let p = Process()
        p.executableURL = exe
        p.arguments = args
        p.currentDirectoryURL = cwd
        if env.isEmpty {
            p.environment = ["PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                             "HOME": Pfade.fileManager.homeDirectoryForCurrentUser.path,
                             "LANG": "de_DE.UTF-8"]
        } else {
            p.environment = env
        }
        let protokoll = try protokollHandle(Pfade.einrichtungsProtokoll)
        p.standardOutput = protokoll
        p.standardError = protokoll
        let code: Int32 = try await withCheckedThrowingContinuation { fortsetzung in
            p.terminationHandler = { beendet in fortsetzung.resume(returning: beendet.terminationStatus) }
            do { try p.run() } catch { fortsetzung.resume(throwing: error) }
        }
        try? protokoll.close()
        guard code == 0 else { throw SchulnexusFehler.schritt(schritt, code) }
    }
}
