import Foundation
import Combine

/// 遥控器（对应 ui_components.send_keycode / launch_quick_action / adapt_remote_controller）
@MainActor
final class RemoteControlViewModel: ObservableObject {
    struct QuickApp: Identifiable {
        let id = UUID()
        let label: String
        let kind: Kind
        enum Kind {
            case packages([String])     // monkey 启动
            case activity(String)        // am start -n
            case shell(String)           // 直接 shell
        }
    }

    @Published var status = "就绪"
    @Published var customApps: [(name: String, cmd: String)] = []
    @Published var customName = ""
    @Published var customCmd = ""

    private let deviceManager: DeviceManager

    let builtinApps: [QuickApp] = [
        QuickApp(label: "系统设置", kind: .shell("am start -n com.android.tv.settings/.MainSettings")),
        QuickApp(label: "YouTube", kind: .packages(["com.google.android.youtube.tv", "com.google.android.youtube"])),
        QuickApp(label: "Netflix", kind: .packages(["com.netflix.ninja", "com.netflix.mediaclient"])),
        QuickApp(label: "Prime Video", kind: .activity("com.amazon.amazonvideo.livingroom/com.amazon.ignition.IgnitionActivity")),
    ]

    init(deviceManager: DeviceManager) {
        self.deviceManager = deviceManager
    }

    func sendKey(_ keycode: String) {
        runOnDevice(desc: "按键 \(keycode)") { serial in
            try await ADBService.shared.shellAsync("input keyevent KEYCODE_\(keycode)", deviceSerial: serial)
        }
    }

    func adaptRemote() {
        runOnDevice(desc: "适配遥控器") { serial in
            try await ADBService.shared.shellAsync(
                "am broadcast -a com.nes.intent.action.NES_RESET_LONGPRESS", deviceSerial: serial)
        }
    }

    func launch(_ app: QuickApp) {
        runOnDevice(desc: app.label) { serial in
            switch app.kind {
            case .packages(let pkgs):
                for pkg in pkgs {
                    let out = try? await ADBService.shared.shellAsync(
                        "monkey -p \(pkg) -c android.intent.category.LAUNCHER 1", deviceSerial: serial)
                    if let out, !out.contains("No activities found") { return out }
                }
                return "已尝试启动"
            case .activity(let comp):
                return try await ADBService.shared.shellAsync("am start -n \(comp)", deviceSerial: serial)
            case .shell(let cmd):
                return try await ADBService.shared.shellAsync(cmd, deviceSerial: serial)
            }
        }
    }

    func launchCustom(_ cmd: String) {
        runOnDevice(desc: "自定义启动") { serial in
            let normalized = cmd.hasPrefix("am ") || cmd.hasPrefix("monkey") ? cmd : cmd
            return try await ADBService.shared.shellAsync(normalized, deviceSerial: serial)
        }
    }

    func addCustom() {
        let name = customName.trimmingCharacters(in: .whitespaces)
        let cmd = customCmd.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty, !cmd.isEmpty else { return }
        customApps.append((name, cmd))
        customName = ""
        customCmd = ""
    }

    func deleteCustom(at index: Int) {
        guard customApps.indices.contains(index) else { return }
        customApps.remove(at: index)
    }

    private func runOnDevice(desc: String, _ work: @escaping (String) async throws -> String) {
        guard let serial = deviceManager.selectedOnlineDevice else {
            status = "请先选择已连接的设备"
            return
        }
        status = "正在执行：\(desc)…"
        Task {
            do {
                _ = try await work(serial)
                status = "已执行：\(desc)"
            } catch {
                status = "\(desc) 失败：\(error.localizedDescription)"
            }
        }
    }
}
