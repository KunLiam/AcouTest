import SwiftUI

@main
struct AcouTestApp: App {
    @StateObject private var deviceManager = DeviceManager()

    var body: some Scene {
        WindowGroup {
            MainWindowView()
                .environmentObject(deviceManager)
                .frame(minWidth: 1000, minHeight: 680)
        }
        .windowStyle(.titleBar)
    }
}
