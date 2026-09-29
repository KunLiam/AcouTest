import Foundation
import AppKit
import Combine

/// 麦克风测试（对应 test_operations.start_mic_test / stop_mic_test）
@MainActor
final class MicTestViewModel: ObservableObject {
    @Published var micCount = "2"
    @Published var pcmDevice = "0"   // tinycap -D
    @Published var cardId = "0"      // tinycap -d
    @Published var sampleRate = "48000"
    @Published var savePath = OutputPaths.url(for: .micTest).path
    @Published var status = "就绪"
    @Published var isRecording = false

    private let deviceManager: DeviceManager
    private let remotePath = "/sdcard/mic_test.wav"
    private var process: Process?

    init(deviceManager: DeviceManager) {
        self.deviceManager = deviceManager
    }

    func start() {
        guard !isRecording else { return }
        guard let serial = deviceManager.selectedOnlineDevice else {
            status = "请先选择已连接的设备"; return
        }
        let cmd = "tinycap \(remotePath) -D \(pcmDevice) -d \(cardId) -c \(micCount) -r \(sampleRate)"
        let proc = ADBService.shared.makeProcess(["shell", cmd], deviceSerial: serial)
        proc.standardOutput = Pipe()
        proc.standardError = Pipe()
        do {
            try proc.run()
        } catch {
            status = "启动录制失败：\(error.localizedDescription)"; return
        }
        process = proc
        isRecording = true
        status = "正在录制…（命令：\(cmd)）"
    }

    func stop() async {
        guard isRecording else { return }
        guard let serial = deviceManager.selectedOnlineDevice else { return }
        status = "正在停止并拉取…"
        _ = try? await ADBService.shared.shellAsync("pkill -f tinycap", deviceSerial: serial)
        if let proc = process, proc.isRunning { proc.terminate() }
        process = nil
        try? await Task.sleep(nanoseconds: 800_000_000)

        do {
            try FileManager.default.createDirectory(atPath: savePath, withIntermediateDirectories: true)
            let dest = (savePath as NSString).appendingPathComponent("mic_\(Self.ts()).wav")
            _ = try await ADBService.shared.runAsync(["pull", remotePath, dest], deviceSerial: serial, timeout: 120)
            status = "录音已保存：\((dest as NSString).lastPathComponent)"
        } catch {
            status = "拉取失败：\(error.localizedDescription)"
        }
        isRecording = false
    }

    func openFolder() {
        try? FileManager.default.createDirectory(atPath: savePath, withIntermediateDirectories: true)
        NSWorkspace.shared.open(URL(fileURLWithPath: savePath))
    }

    func chooseFolder() {
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true; panel.canChooseFiles = false
        if panel.runModal() == .OK, let url = panel.url { savePath = url.path }
    }

    static func ts() -> String {
        let f = DateFormatter(); f.dateFormat = "yyyyMMdd_HHmmss"; return f.string(from: Date())
    }
}
