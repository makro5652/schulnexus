import SwiftUI

struct ContentView: View {
    @ObservedObject var server = ServerController.shared

    var body: some View {
        Group {
            switch server.phase {
            case .vorbereitung:
                VStack(spacing: 16) {
                    ProgressView()
                        .controlSize(.large)
                    Text("Schulnexus wird vorbereitet")
                        .font(.title2.weight(.semibold))
                    Text(server.status)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 480)
                }
                .padding(40)
                .frame(maxWidth: .infinity, maxHeight: .infinity)

            case .laeuft(let url):
                WebView(url: url, reloadZaehler: server.reloadZaehler)

            case .fehler(let text):
                VStack(spacing: 16) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 40))
                        .foregroundStyle(.orange)
                    Text("Schulnexus konnte nicht starten")
                        .font(.title2.weight(.semibold))
                    Text(text)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 520)
                    HStack {
                        Button("Erneut versuchen") {
                            Task { await server.starten() }
                        }
                        .keyboardShortcut(.defaultAction)
                        Button("Protokoll öffnen") {
                            NSWorkspace.shared.open(Pfade.einrichtungsProtokoll)
                        }
                    }
                }
                .padding(40)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .frame(minWidth: 960, minHeight: 640)
        .task {
            if case .vorbereitung = server.phase {
                await server.starten()
            }
        }
        .sheet(item: Binding(
            get: { server.neuerAdmin.map { AdminInfo(geheimnisse: $0) } },
            set: { _ in server.neuerAdmin = nil }
        )) { info in
            AdminSheet(info: info)
        }
    }
}

struct AdminInfo: Identifiable {
    let geheimnisse: Geheimnisse
    // Stabile Kennung, sonst würde das Sheet bei jedem Neuzeichnen neu erscheinen
    var id: String { geheimnisse.datenSchluessel }
}

struct AdminSheet: View {
    let info: AdminInfo
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Zugangsdaten für die Verwaltung")
                .font(.title3.weight(.semibold))
            Text("Diese Angaben werden nur einmal angezeigt. Sie stehen zusätzlich in der Datei geheimnisse.json im Ordner Application Support/Schulnexus (nur für dein Benutzerkonto lesbar).")
                .foregroundStyle(.secondary)
            Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 8) {
                GridRow {
                    Text("Benutzer:").bold()
                    Text(info.geheimnisse.adminBenutzer).textSelection(.enabled)
                }
                GridRow {
                    Text("Passwort:").bold()
                    Text(info.geheimnisse.adminPasswort).textSelection(.enabled).font(.body.monospaced())
                }
            }
            Text("Verschlüsselungsschlüssel (bitte sicher aufbewahren, ohne ihn sind Anhänge und Sicherungen unlesbar):")
                .foregroundStyle(.secondary)
            Text(info.geheimnisse.datenSchluessel)
                .font(.caption.monospaced())
                .textSelection(.enabled)
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(.quaternary, in: RoundedRectangle(cornerRadius: 6))
            HStack {
                Spacer()
                Button("Fertig") { dismiss() }
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(24)
        .frame(width: 560)
    }
}
