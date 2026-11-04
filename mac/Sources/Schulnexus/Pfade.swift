import Foundation

/// Alle Pfade der Desktop-App. Code, Python-Umgebung und Daten sind getrennt,
/// damit ein Update den Code ersetzt, ohne Daten anzufassen.
enum Pfade {
    static let fileManager = FileManager.default

    /// ~/Library/Application Support/Schulnexus
    static let support: URL = {
        let basis = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        return basis.appendingPathComponent("Schulnexus", isDirectory: true)
    }()

    /// Kopie des Django-Projekts (wird bei jedem Start aus dem App-Bundle erneuert)
    static var code: URL { support.appendingPathComponent("app", isDirectory: true) }
    static var venv: URL { support.appendingPathComponent("venv", isDirectory: true) }
    static var daten: URL { support.appendingPathComponent("daten", isDirectory: true) }
    static var dokumente: URL { daten.appendingPathComponent("dokumente", isDirectory: true) }
    static var modulsicherungen: URL { daten.appendingPathComponent("modulsicherungen", isDirectory: true) }
    static var datenbank: URL { daten.appendingPathComponent("schulnexus.sqlite3") }
    static var geheimnisse: URL { support.appendingPathComponent("geheimnisse.json") }
    static var einstellungen: URL { support.appendingPathComponent("einstellungen.env") }
    static var serverPID: URL { support.appendingPathComponent("server.pid") }
    static var stempel: URL { venv.appendingPathComponent(".schulnexus-stempel") }

    static var protokollordner: URL {
        fileManager.homeDirectoryForCurrentUser.appendingPathComponent("Library/Logs/Schulnexus", isDirectory: true)
    }
    static var serverProtokoll: URL { protokollordner.appendingPathComponent("server.log") }
    static var einrichtungsProtokoll: URL { protokollordner.appendingPathComponent("einrichtung.log") }

    /// Im App-Bundle: Resources/app (Django-Projekt), Resources/requirements.txt
    static var gebuendelt: URL? { Bundle.main.resourceURL }

    static func legeOrdnerAn() throws {
        for ordner in [support, daten, dokumente, modulsicherungen, protokollordner] {
            try fileManager.createDirectory(at: ordner, withIntermediateDirectories: true)
        }
    }
}
