import Foundation
import Security

/// Schlüssel und Zugangsdaten. Gespeichert als JSON mit Rechten 0600 im Application-Support-Ordner.
/// WICHTIG: Der daten_schluessel entschlüsselt Anhänge und Sicherungen. Verlust = Datenverlust.
struct Geheimnisse: Codable {
    var secretKey: String
    var datenSchluessel: String
    var adminBenutzer: String
    var adminPasswort: String
    var erstelltAm: Date
}

enum GeheimnisSpeicher {
    static func laden() throws -> Geheimnisse? {
        guard FileManager.default.fileExists(atPath: Pfade.geheimnisse.path) else { return nil }
        let daten = try Data(contentsOf: Pfade.geheimnisse)
        return try JSONDecoder().decode(Geheimnisse.self, from: daten)
    }

    /// Lädt vorhandene Geheimnisse oder erzeugt sie beim ersten Start.
    static func ladenOderErzeugen() throws -> (Geheimnisse, neu: Bool) {
        if let vorhanden = try laden() { return (vorhanden, false) }
        let neu = Geheimnisse(
            secretKey: zufallText(laenge: 50),
            datenSchluessel: zufallSchluessel(),
            adminBenutzer: "admin",
            adminPasswort: zufallText(laenge: 16),
            erstelltAm: Date()
        )
        try speichern(neu)
        return (neu, true)
    }

    static func speichern(_ g: Geheimnisse) throws {
        let kodiert = try JSONEncoder().encode(g)
        try kodiert.write(to: Pfade.geheimnisse, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: Pfade.geheimnisse.path)
    }

    static func zufallBytes(_ n: Int) -> [UInt8] {
        var bytes = [UInt8](repeating: 0, count: n)
        _ = SecRandomCopyBytes(kSecRandomDefault, n, &bytes)
        return bytes
    }

    /// 32 Zufallsbytes als URL-sicheres Base64 (wie start.sh/schluessel())
    static func zufallSchluessel() -> String {
        Data(zufallBytes(32)).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    static func zufallText(laenge: Int) -> String {
        let zeichen = Array("ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789")
        return String(zufallBytes(laenge).map { zeichen[Int($0) % zeichen.count] })
    }
}
