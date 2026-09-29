import Foundation
import AppKit
import Combine

/// HAL 录音（对应 test_operations.start_hal_recording / stop_hal_recording + 自动拉取）
@MainActor
final class HALRecordingViewModel: ObservableObject {
    struct HALProp: Identifiable {
        let id = UUID()
        let name: String
        let onValue: String
        var enabled: Bool
    }

    @Published var props: [HALProp]
    @Published var remoteDir: String = "data/vendor/audiohal"
    @Published var savePath: String = OutputPaths.url(for: .halDump).path
    @Published var status: String = "就绪"
    @Published var isRecording = false
    @Published var log: String = ""

    private let deviceManager: DeviceManager

    init(deviceManager: DeviceManager) {
        self.deviceManager = deviceManager
        // 与原版 default_props 一致的常用子集
        self.props = [
            HALProp(name: "vendor.media.audiohal.vpp.dump", onValue: "1", enabled: true),
            HALProp(name: "vendor.media.audiohal.speech.dump", onValue: "1", enabled: true),
            HALProp(name: "vendor.media.audiohal.indump", onValue: "1", enabled: true),
            HALProp(name: "vendor.media.audiohal.outdump", onValue: "1", enabled: true),
            HALProp(name: "vendor.media.audiohal.loopback", onValue: "1", enabled: false),
            HALProp(name: "vendor.media.audiohal.alsadump", onValue: "1", enabled: false),
            HALProp(name: "vendor.media.audiohal.in.dump", onValue: "1", enabled: false),
            HALProp(name: "vendor.media.audiohal.out.dump", onValue: "1", enabled: false),
            HALProp(name: "vendor.media.audiohal.ms12.dump", onValue: "0xffff", enabled: false),
            HALProp(name: "vendor.media.audiohal.btpcm", onValue: "1", enabled: false),
        ]
    }

    func toggleAll(_ on: Bool) {
        for i in props.indices { props[i].enabled = on }
    }

    func startRecording() async {
        guard let serial = deviceManager.selectedOnlineDevice else {
            status = "请先选择已连接的设备"
            return
        }
        let selected = props.filter(\.enabled)
        guard !selected.isEmpty else {
            status = "请至少选择一个录音属性"
            return
        }
        isRecording = true
        status = "正在开启录音属性…"
        appendLog("=== 开始 HAL 录音 ===")
        do {
            for prop in selected {
                _ = try await ADBService.shared.shellAsync("setprop \(prop.name) \(prop.onValue)", deviceSerial: serial)
                appendLog("已开启: \(prop.name)=\(prop.onValue)")
            }
            status = "录音中…（停止后自动拉取到本地）"
        } catch {
            status = "开启属性失败：\(error.localizedDescription)"
            isRecording = false
        }
    }

    func stopRecording() async {
        guard let serial = deviceManager.selectedOnlineDevice else {
            status = "请先选择已连接的设备"
            return
        }
        status = "正在关闭录音属性…"
        appendLog("=== 停止 HAL 录音 ===")
        for prop in props where prop.enabled {
            _ = try? await ADBService.shared.shellAsync("setprop \(prop.name) 0", deviceSerial: serial)
            appendLog("已关闭: \(prop.name)=0")
        }
        // 等待落盘
        try? await Task.sleep(nanoseconds: 1_000_000_000)
        await pullFiles(serial: serial)
        isRecording = false
    }

    private func pullFiles(serial: String) async {
        let dir = savePath.isEmpty ? OutputPaths.url(for: .halDump).path : savePath
        let timestamp = Self.timestamp()
        let destDir = (dir as NSString).appendingPathComponent("hal_\(timestamp)")
        do {
            try FileManager.default.createDirectory(atPath: destDir, withIntermediateDirectories: true)
            status = "正在拉取录音文件…"
            let remote = remoteDir.hasPrefix("/") ? remoteDir : "/\(remoteDir)"
            let result = try await Task.detached(priority: .userInitiated) {
                try ADBService.shared.pull(remote: remote, localDir: destDir, deviceSerial: serial)
            }.value
            appendLog(result)
            status = "已拉取到：\(destDir)"
        } catch {
            status = "拉取失败：\(error.localizedDescription)"
            appendLog("拉取失败：\(error.localizedDescription)")
        }
    }

    func openFolder() {
        let dir = savePath.isEmpty ? OutputPaths.url(for: .halDump).path : savePath
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        NSWorkspace.shared.open(URL(fileURLWithPath: dir))
    }

    func chooseFolder() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        if panel.runModal() == .OK, let url = panel.url {
            savePath = url.path
        }
    }

    private func appendLog(_ line: String) {
        log += line + "\n"
        if log.count > 8000 { log = String(log.suffix(8000)) }
    }

    private static func timestamp() -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyyMMdd_HHmmss"
        return f.string(from: Date())
    }
}
