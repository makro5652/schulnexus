// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "Schulnexus",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(name: "Schulnexus", path: "Sources/Schulnexus")
    ]
)
