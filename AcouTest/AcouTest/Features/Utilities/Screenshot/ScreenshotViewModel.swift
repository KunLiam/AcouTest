import Foundation
import AppKit
import Combine

/// 截图功能（对应 test_operations.take_screenshot / open_screenshot_folder）
@MainActor
final class ScreenshotViewModel: ObservableObject {
    @Published var status: String = "就绪"
    @Published var savePath: String = OutputPaths.url(for: .screenshots).path
    @Published var lastImagePath: String?
    @Published var isBusy = false

    private let deviceManager: DeviceManager

    init(deviceManager: DeviceManager) {
        self.deviceManager = deviceManager
    }

    func takeScreenshot() async {
        guard let serial = deviceManager.selectedOnlineDevice else {
            status = "请先选择已连接的设备"
            return
        }
        isBusy = true
        status = "正在截取屏幕…"
        defer { isBusy = false }

        do {
            let dir = savePath.isEmpty ? OutputPaths.url(for: .screenshots).path : savePath
            try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)

            let timestamp = Self.timestamp()
            let filename = "screenshot_\(timestamp).png"
            let localPath = (dir as NSString).appendingPathComponent(filename)

            // 对应 adb exec-out screencap -p
            let data = try await Task.detached(priority: .userInitiated) {
                try ADBService.shared.runData(["exec-out", "screencap", "-p"], deviceSerial: serial)
            }.value

            guard !data.isEmpty else {
                status = "截图失败：未获取到图像数据"
                return
            }
            try data.write(to: URL(fileURLWithPath: localPath))
            lastImagePath = localPath
            status = "截图成功：\(filename)"
        } catch {
            status = "截图失败：\(error.localizedDescription)"
        }
    }

    func openFolder() {
        let dir = savePath.isEmpty ? OutputPaths.url(for: .screenshots).path : savePath
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        NSWorkspace.shared.open(URL(fileURLWithPath: dir))
    }

    func chooseFolder() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        if panel.runModal() == .OK, let url = panel.url {
            savePath = url.path
        }
    }

    private static func timestamp() -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyyMMdd_HHmmss"
        return f.string(from: Date())
    }
}
