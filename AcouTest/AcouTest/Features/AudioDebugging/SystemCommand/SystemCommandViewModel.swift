import Foundation
import AppKit
import Combine

/// 系统指令（对应 ui_components.open_system_cmd_window / _syscmd_run_one / setup_system_cmd_tab）
@MainActor
final class SystemCommandViewModel: ObservableObject {
    struct Preset: Identifiable {
        let id = UUID()
        let label: String
        let command: String
        /// 直接执行不展示输出（如 reboot）
        let runSilently: Bool
    }

    @Published var output: String = ""
    @Published var status: String = "就绪"
    @Published var customCommand: String = ""
    @Published var customList: [String] = []
    @Published var isRunning = false

    private let deviceManager: DeviceManager

    /// 与原版 commands 预设一致
    let presets: [Preset] = [
        Preset(label: "dumpsys media.audio_policy", command: "dumpsys media.audio_policy", runSilently: false),
        Preset(label: "dumpsys media.audio_flinger", command: "dumpsys media.audio_flinger", runSilently: false),
        Preset(label: "dumpsys audio", command: "dumpsys audio", runSilently: false),
        Preset(label: "tinymix", command: "tinymix", runSilently: false),
        Preset(label: "getprop", command: "getprop", runSilently: false),
        Preset(label: "getprop ro.build.fingerprint", command: "getprop ro.build.fingerprint", runSilently: false),
        Preset(label: "reboot update", command: "reboot update", runSilently: true),
        Preset(label: "reboot", command: "reboot", runSilently: true),
        Preset(label: "dumpsys input", command: "dumpsys input", runSilently: false),
    ]

    init(deviceManager: DeviceManager) {
        self.deviceManager = deviceManager
    }

    func run(_ command: String, silently: Bool) async {
        let cmd = command.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cmd.isEmpty else { return }
        guard let serial = deviceManager.selectedOnlineDevice else {
            status = "请先选择已连接的设备"
            return
        }
        isRunning = true
        status = "正在执行：\(cmd)"
        if !silently { output = "" }
        defer { isRunning = false }

        do {
            let result = try await Task.detached(priority: .userInitiated) {
                try ADBService.shared.shell(cmd, deviceSerial: serial, timeout: 60)
            }.value
            if silently {
                status = "已下发：\(cmd)"
            } else {
                output = result
                status = "完成：\(cmd)"
            }
        } catch {
            status = "执行失败：\(error.localizedDescription)"
        }
    }

    func addCustom() {
        let cmd = customCommand.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cmd.isEmpty, !customList.contains(cmd) else { return }
        customList.append(cmd)
        customCommand = ""
    }

    func deleteCustom(_ cmd: String) {
        customList.removeAll { $0 == cmd }
    }

    func saveOutput() {
        guard !output.isEmpty else { return }
        let panel = NSSavePanel()
        panel.nameFieldStringValue = "syscmd_output.txt"
        if panel.runModal() == .OK, let url = panel.url {
            try? output.write(to: url, atomically: true, encoding: .utf8)
            status = "已保存：\(url.lastPathComponent)"
        }
    }
}
