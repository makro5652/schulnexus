#!/bin/sh
# Baut Schulnexus.app (macOS, Apple Silicon und Intel über den Swift-Compiler des Rechners).
# Ergebnis: mac/dist/Schulnexus.app – Programmcode des Django-Projekts liegt in Contents/Resources/app.
set -e
HIER="$(cd "$(dirname "$0")" && pwd)"
PROJEKT="$(cd "$HIER/.." && pwd)"
cd "$HIER"

swift build -c release
BIN="$(swift build -c release --show-bin-path)/Schulnexus"

VERSION="$(sed -n 's/^VERSION = "\(.*\)"/\1/p' "$PROJEKT/src/config/version.py")"
APP="dist/Schulnexus.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources/app"

cp "$BIN" "$APP/Contents/MacOS/Schulnexus"
rsync -a --exclude '__pycache__' --exclude '*.pyc' --exclude 'staticfiles' \
      --exclude 'media' --exclude 'modulsicherungen' \
      "$PROJEKT/src/" "$APP/Contents/Resources/app/"
cp "$HIER/bootstrap_admin.py" "$APP/Contents/Resources/app/"
cp "$PROJEKT/requirements.txt" "$APP/Contents/Resources/"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>Schulnexus</string>
    <key>CFBundleDisplayName</key><string>Schulnexus</string>
    <key>CFBundleIdentifier</key><string>de.schulnexus.desktop</string>
    <key>CFBundleExecutable</key><string>Schulnexus</string>
    <key>CFBundlePackageType</key><string>APPL</string>
    <key>CFBundleShortVersionString</key><string>$VERSION</string>
    <key>CFBundleVersion</key><string>$VERSION</string>
    <key>LSMinimumSystemVersion</key><string>13.0</string>
    <key>NSHighResolutionCapable</key><true/>
    <key>NSPrincipalClass</key><string>NSApplication</string>
</dict>
</plist>
PLIST

codesign --force --deep --sign - "$APP"
echo "Fertig: $HIER/$APP (Version $VERSION)"
