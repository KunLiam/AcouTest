import Foundation
import AppKit
import Combine
import UniformTypeIdentifiers

/// 多声道测试（对应 test_operations.run_multichannel_test / _multichannel_test_thread）
@MainActor
final class MultichannelTestViewModel: ObservableObject {
    @Published var preset = "7.1" {
        didSet { if useDefaultAudio { loadDefaultAudio() } }
    }
    @Published var sampleRate = "48000"
    @Published var bitDepth = "16"
    @Published var playDevice = "0"
    @Published var useDefaultAudio = true
    @Published var audioPath = ""   // 多声道 wav（7.1/2.1/2.0）
    @Published var status = "就绪（已加载默认片源）"
    @Published var isBusy = false

    let presets = ["7.1", "2.1", "2.0"]
    let playDeviceOptions = ["0", "1"]
    private let deviceManager: DeviceManager

    init(deviceManager: DeviceManager) {
        self.deviceManager = deviceManager
        loadDefaultAudio()
    }

    /// 按当前预设加载内置默认片源
    func loadDefaultAudio() {
        if let path = AudioAssets.multichannelPath(preset: preset) {
            audioPath = path
            status = "已加载默认片源：\((path as NSString).lastPathComponent)"
        } else {
            audioPath = ""
            status = "未找到 \(preset) 默认片源，请手动选择音频"
        }
    }

    func chooseAudio() {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true; panel.canChooseDirectories = false
        panel.allowedContentTypes = [.audio, .wav]
        if panel.runModal() == .OK, let url = panel.url {
            audioPath = url.path
            useDefaultAudio = false
        }
    }

    func start() async {
        guard let serial = deviceManager.selectedOnlineDevice else { status = "请先选择已连接的设备"; return }
        if useDefaultAudio { loadDefaultAudio() }
        let file = audioPath.trimmingCharacters(in: .whitespaces)
        guard !file.isEmpty, FileManager.default.fileExists(atPath: file) else {
            status = "多声道音频不存在，请手动选择 wav 文件"; return
        }
        let name = (file as NSString).lastPathComponent
        isBusy = true; defer { isBusy = false }
        do {
            status = "准备设备（root）…"
            _ = try? await ADBService.shared.runAsync(["root"], deviceSerial: serial)
            status = "推送音频…"
            _ = try await ADBService.shared.runAsync(["push", file, "/sdcard/\(name)"], deviceSerial: serial, timeout: 120)
            status = "重启 audioserver…"
            for _ in 0..<3 {
                _ = try? await ADBService.shared.shellAsync("killall audioserver", deviceSerial: serial)
            }
            status = "正在播放多声道音频（\(preset)）…"
            let play = "tinyplay /sdcard/\(name) -r \(sampleRate) -b \(bitDepth) -d \(playDevice)"
            _ = try await ADBService.shared.shellAsync(play, deviceSerial: serial, timeout: 120)
            status = "多声道播放已执行"
        } catch {
            status = "失败：\(error.localizedDescription)"
        }
    }
}
