import Foundation
import Combine

/// sn烧key（对应 ui_components.setup_sn_key_burn_tab：ADB 读写 unifykeys/elevockey）
/// 注意：license 由 SN 生成需 Windows 端 soft_encryption.dll，Mac 端支持读 SN、读/写 elevockey。
@MainActor
final class SNKeyBurnViewModel: ObservableObject {
    @Published var snValue = ""
    @Published var currentKey = ""
    @Published var licenseHex = ""
    @Published var log = ""
    @Published var isBusy = false

    private let deviceManager: DeviceManager

    init(deviceManager: DeviceManager) { self.deviceManager = deviceManager }

    func readSN() {
        run(desc: "读取 SN") { serial in
            try await ADBService.shared.runAsync(["root"], deviceSerial: serial)
            let out = try await ADBService.shared.shellAsync(
                "echo usid > /sys/class/unifykeys/name && cat /sys/class/unifykeys/read", deviceSerial: serial)
            let sn = out.trimmingCharacters(in: .whitespacesAndNewlines)
            await MainActor.run { self.snValue = sn }
            return "SN(usid): \(sn) | 长度: \(sn.count)"
        }
    }

    func readCurrentKey() {
        run(desc: "读取当前 elevockey") { serial in
            try await ADBService.shared.runAsync(["root"], deviceSerial: serial)
            let out = try await ADBService.shared.shellAsync(
                "echo elevockey > /sys/class/unifykeys/name && cat /sys/class/unifykeys/read", deviceSerial: serial)
            let key = out.trimmingCharacters(in: .whitespacesAndNewlines)
            await MainActor.run { self.currentKey = key }
            return key.isEmpty ? "当前未烧录 elevockey" : "当前 elevockey: \(key)"
        }
    }

    func writeKey() {
        let hex = licenseHex.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !hex.isEmpty else { appendLog("请先填写 license（hex）"); return }
        run(desc: "写入 elevockey") { serial in
            try await ADBService.shared.runAsync(["root"], deviceSerial: serial)
            _ = try await ADBService.shared.shellAsync(
                "echo elevockey > /sys/class/unifykeys/name && echo \(hex) > /sys/class/unifykeys/write",
                deviceSerial: serial)
            let verify = try await ADBService.shared.shellAsync(
                "echo elevockey > /sys/class/unifykeys/name && cat /sys/class/unifykeys/read", deviceSerial: serial)
            let got = verify.trimmingCharacters(in: .whitespacesAndNewlines)
            await MainActor.run { self.currentKey = got }
            return "写入完成，回读: \(got)"
        }
    }

    func listKeys() {
        run(desc: "列出 unifykeys") { serial in
            try await ADBService.shared.runAsync(["root"], deviceSerial: serial)
            let out = try await ADBService.shared.shellAsync("cat /sys/class/unifykeys/list", deviceSerial: serial)
            return "unifykeys/list:\n\(out)"
        }
    }

    private func run(desc: String, _ work: @escaping (String) async throws -> String) {
        guard let serial = deviceManager.selectedOnlineDevice else { appendLog("请先选择已连接的设备"); return }
        isBusy = true
        appendLog("=== \(desc) ===")
        Task {
            do {
                let result = try await work(serial)
                appendLog(result)
            } catch {
                appendLog("\(desc) 失败：\(error.localizedDescription)")
            }
            isBusy = false
        }
    }

    private func appendLog(_ s: String) {
        log += (log.isEmpty ? "" : "\n") + s
    }
}
