import Foundation
import AppKit
import Combine
import UniformTypeIdentifiers

/// 扫频测试（对应 test_operations.start_sweep_test）
/// 推送扫频音频 → tinycap 录音 + tinyplay 播放 → 到时停止并拉取录音。
@MainActor
final class SweepTestViewModel: ObservableObject {
    @Published var audioPath = ""
    @Published var recordingDevice = "0"
    @Published var channels = "2"
    @Published var sampleRate = "48000"
    @Published var bitDepth = "16"
    @Published var duration = "10"   // 秒
    @Published var savePath = OutputPaths.url(for: .sweepRecordings).path
    @Published var status = "请选择扫频音频后开始"
    @Published var isBusy = false

    private let deviceManager: DeviceManager
    private var recProcess: Process?
    private var playProcess: Process?

    init(deviceManager: DeviceManager) { self.deviceManager = deviceManager }

    func chooseAudio() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true; panel.canChooseDirectories = false
        panel.allowedContentTypes = [.audio, .wav]
        if panel.runModal() == .OK, let url = panel.url { audioPath = url.path }
    }

    func chooseFolder() {
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false
        if panel.runModal() == .OK, let url = panel.url { savePath = url.path }
    }

    func openFolder() {
        try? FileManager.default.createDirectory(atPath: savePath, withIntermediateDirectories: true)
        NSWorkspace.shared.open(URL(fileURLWithPath: savePath))
    }

    func start() async {
        guard !isBusy else { return }
        guard let serial = deviceManager.selectedOnlineDevice else { status = "请先选择已连接的设备"; return }
        let file = audioPath.trimmingCharacters(in: .whitespaces)
        guard !file.isEmpty, FileManager.default.fileExists(atPath: file) else {
            status = "请选择有效的扫频音频文件"; return
        }
        let name = (file as NSString).lastPathComponent
        let base = (name as NSString).deletingPathExtension
        let ts = MicTestViewModel.ts()
        let remoteAudio = "/sdcard/\(name)"
        let remoteRec = "/sdcard/\(base)_recording_\(ts).wav"
        let dur = Double(duration) ?? 10

        isBusy = true; defer { isBusy = false }
        do {
            status = "准备设备…"
            _ = try? await ADBService.shared.runAsync(["root"], deviceSerial: serial)
            for _ in 0..<3 { _ = try? await ADBService.shared.shellAsync("killall audioserver", deviceSerial: serial) }

            status = "推送扫频音频…"
            _ = try await ADBService.shared.runAsync(["push", file, remoteAudio], deviceSerial: serial, timeout: 120)

            status = "开始录制…"
            let recCmd = "tinycap \(remoteRec) -D 0 -d \(recordingDevice) -r \(sampleRate) -c \(channels) -p 256"
            let rec = ADBService.shared.makeProcess(["shell", recCmd], deviceSerial: serial)
            rec.standardOutput = Pipe(); rec.standardError = Pipe()
            try rec.run(); recProcess = rec
            try await Task.sleep(nanoseconds: 2_000_000_000)

            status = "正在播放扫频音频…"
            let playCmd = "tinyplay \(remoteAudio) -d 0 -D 0 -r \(sampleRate) -c \(channels) -b \(bitDepth)"
            let play = ADBService.shared.makeProcess(["shell", playCmd], deviceSerial: serial)
            play.standardOutput = Pipe(); play.standardError = Pipe()
            try play.run(); playProcess = play

            try await Task.sleep(nanoseconds: UInt64(dur * 1_000_000_000))

            status = "停止并拉取录音…"
            _ = try? await ADBService.shared.shellAsync("killall tinyplay", deviceSerial: serial)
            _ = try? await ADBService.shared.shellAsync("killall tinycap", deviceSerial: serial)
            if let p = playProcess, p.isRunning { p.terminate() }
            if let r = recProcess, r.isRunning { r.terminate() }
            playProcess = nil; recProcess = nil
            try? await Task.sleep(nanoseconds: 800_000_000)

            try FileManager.default.createDirectory(atPath: savePath, withIntermediateDirectories: true)
            let dest = (savePath as NSString).appendingPathComponent((remoteRec as NSString).lastPathComponent)
            _ = try await ADBService.shared.runAsync(["pull", remoteRec, dest], deviceSerial: serial, timeout: 120)
            status = "完成，录音已保存：\((dest as NSString).lastPathComponent)"
        } catch {
            status = "失败：\(error.localizedDescription)"
            _ = try? await ADBService.shared.shellAsync("killall tinyplay", deviceSerial: serial)
            _ = try? await ADBService.shared.shellAsync("killall tinycap", deviceSerial: serial)
        }
    }
}
