import AppKit
import SwiftUI

@main
struct SchulnexusApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate

    var body: some Scene {
        WindowGroup("Schulnexus") {
            ContentView()
        }
        .commands {
            CommandGroup(replacing: .newItem) {}
            CommandMenu("Schulnexus") {
                Button("Neu laden") { ServerController.shared.neuLaden() }
                    .keyboardShortcut("r", modifiers: .command)
                Divider()
                Button("Einstellungen öffnen …") {
                    NSWorkspace.shared.open(Pfade.einstellungen)
                }
                .keyboardShortcut(",", modifiers: .command)
                Button("Protokolle anzeigen") {
                    NSWorkspace.shared.open(Pfade.protokollordner)
                }
                Button("Datenordner anzeigen") {
                    NSWorkspace.shared.open(Pfade.support)
                }
            }
        }
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationWillTerminate(_ notification: Notification) {
        // Der Server-Prozess muss vor dem Beenden gestoppt werden, sonst läuft gunicorn weiter.
        if #available(macOS 14.0, *) {
            MainActor.assumeIsolated { ServerController.shared.stoppen() }
        } else {
            DispatchQueue.main.sync { ServerController.shared.stoppen() }
        }
    }

    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}
