import Foundation
import AppKit
import Combine

/// Loopback 和 Ref 测试（对应 test_operations.run_loopback_test / stop_loopback_test）
@MainActor
final class LoopbackTestViewModel: ObservableObject {
    @Published var recordDevice = "0"   // tinycap -d
    @Published var channels = "2"        // -c
    @Published var sampleRate = "48000"  // -r
    @Published var savePath = OutputPaths.url(for: .loopback).path
    @Published var status = "就绪"
    @Published var isRecording = false

    private let deviceManager: DeviceManager
    private var remoteFile = "/sdcard/loopback.wav"
    private var process: Process?

    init(deviceManager: DeviceManager) { self.deviceManager = deviceManager }

    func start() {
        guard !isRecording else { return }
        guard let serial = deviceManager.selectedOnlineDevice else { status = "请先选择已连接的设备"; return }
        remoteFile = "/sdcard/loopback_\(MicTestViewModel.ts()).wav"
        let cmd = "tinycap \(remoteFile) -d \(recordDevice) -c \(channels) -r \(sampleRate) -p 480"
        let proc = ADBService.shared.makeProcess(["shell", cmd], deviceSerial: serial)
        proc.standardOutput = Pipe(); proc.standardError = Pipe()
        do { try proc.run() } catch { status = "启动录制失败：\(error.localizedDescription)"; return }
        process = proc
        isRecording = true
        status = "正在录制通道音频…"
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
            let dest = (savePath as NSString).appendingPathComponent((remoteFile as NSString).lastPathComponent)
            _ = try await ADBService.shared.runAsync(["pull", remoteFile, dest], deviceSerial: serial, timeout: 120)
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
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false
        if panel.runModal() == .OK, let url = panel.url { savePath = url.path }
    }
}
