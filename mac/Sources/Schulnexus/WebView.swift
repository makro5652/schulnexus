import AppKit
import SwiftUI
import WebKit

/// WKWebView mit Datei-Uploads (Anhänge), Downloads (Excel/PDF-Export) und JS-Dialogen.
struct WebView: NSViewRepresentable {
    let url: URL
    let reloadZaehler: Int

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeNSView(context: Context) -> WKWebView {
        let konfiguration = WKWebViewConfiguration()
        konfiguration.websiteDataStore = .default()
        let webView = WKWebView(frame: .zero, configuration: konfiguration)
        webView.navigationDelegate = context.coordinator
        webView.uiDelegate = context.coordinator
        context.coordinator.webView = webView
        webView.load(URLRequest(url: url))
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        if context.coordinator.zuletzt != reloadZaehler {
            context.coordinator.zuletzt = reloadZaehler
            webView.reload()
        }
    }

    final class Coordinator: NSObject, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
        weak var webView: WKWebView?
        var zuletzt = 0
        private var ziele: [ObjectIdentifier: URL] = [:]

        // MARK: Navigation

        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            // Fremde Links im Standardbrowser öffnen, die Schulnexus-Seite bleibt im Fenster.
            if action.navigationType == .linkActivated,
               let u = action.request.url, let host = u.host,
               !["127.0.0.1", "localhost"].contains(host),
               ["http", "https", "mailto"].contains(u.scheme ?? "") {
                NSWorkspace.shared.open(u)
                decisionHandler(.cancel)
                return
            }
            decisionHandler(.allow)
        }

        func webView(_ webView: WKWebView, decidePolicyFor response: WKNavigationResponse,
                     decisionHandler: @escaping (WKNavigationResponsePolicy) -> Void) {
            let anhang = (response.response as? HTTPURLResponse)?
                .value(forHTTPHeaderField: "Content-Disposition")?.lowercased().contains("attachment") ?? false
            decisionHandler(!response.canShowMIMEType || anhang ? .download : .allow)
        }

        func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
            download.delegate = self
        }

        func webView(_ webView: WKWebView, navigationResponse: WKNavigationResponse, didBecome download: WKDownload) {
            download.delegate = self
        }

        // MARK: Downloads

        func download(_ download: WKDownload, decideDestinationUsing response: URLResponse,
                      suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
            let ordner = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask)[0]
            let ziel = eindeutigerName(in: ordner, datei: suggestedFilename)
            ziele[ObjectIdentifier(download)] = ziel
            completionHandler(ziel)
        }

        func downloadDidFinish(_ download: WKDownload) {
            if let ziel = ziele.removeValue(forKey: ObjectIdentifier(download)) {
                NSWorkspace.shared.activateFileViewerSelecting([ziel])
            }
        }

        func download(_ download: WKDownload, didFailWithError error: Error, resumeData: Data?) {
            ziele.removeValue(forKey: ObjectIdentifier(download))
            zeigeMeldung("Der Download ist fehlgeschlagen: \(error.localizedDescription)")
        }

        private func eindeutigerName(in ordner: URL, datei: String) -> URL {
            let basis = (datei as NSString).deletingPathExtension
            let endung = (datei as NSString).pathExtension
            var kandidat = ordner.appendingPathComponent(datei)
            var n = 2
            while FileManager.default.fileExists(atPath: kandidat.path) {
                let neu = endung.isEmpty ? "\(basis) \(n)" : "\(basis) \(n).\(endung)"
                kandidat = ordner.appendingPathComponent(neu)
                n += 1
            }
            return kandidat
        }

        // MARK: Datei-Auswahl (Anhänge hochladen)

        func webView(_ webView: WKWebView, runOpenPanelWith parameters: WKOpenPanelParameters,
                     initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping ([URL]?) -> Void) {
            let panel = NSOpenPanel()
            panel.allowsMultipleSelection = parameters.allowsMultipleSelection
            panel.canChooseFiles = true
            panel.canChooseDirectories = false
            panel.message = "Datei auswählen"
            panel.begin { antwort in
                completionHandler(antwort == .OK ? panel.urls : nil)
            }
        }

        // MARK: JavaScript-Dialoge

        func webView(_ webView: WKWebView, runJavaScriptAlertPanelWithMessage message: String,
                     initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping () -> Void) {
            zeigeMeldung(message)
            completionHandler()
        }

        func webView(_ webView: WKWebView, runJavaScriptConfirmPanelWithMessage message: String,
                     initiatedByFrame frame: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
            let alert = NSAlert()
            alert.messageText = message
            alert.addButton(withTitle: "OK")
            alert.addButton(withTitle: "Abbrechen")
            completionHandler(alert.runModal() == .alertFirstButtonReturn)
        }

        private func zeigeMeldung(_ text: String) {
            let alert = NSAlert()
            alert.messageText = text
            alert.runModal()
        }
    }
}
