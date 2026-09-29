import Foundation
import AppKit
import Combine
import UniformTypeIdentifiers

/// 喇叭测试（对应 test_operations.start_speaker_test）
/// 推送本地 wav 到 /sdcard/test.wav，再启动喇叭测试应用。
@MainActor
final class SpeakerTestViewModel: ObservableObject {
    enum AudioSource: String, CaseIterable, Identifiable {
        case `default` = "默认音频"
        case custom = "自定义音频"
        var id: String { rawValue }
    }

    @Published var source: AudioSource = .default
    @Published var defaultPath = AudioAssets.path(named: AudioAssets.speakerDefault) ?? ""
    @Published var customPath = ""
    @Published var status = "请选择音频后开始"
    @Published var isBusy = false

    private let deviceManager: DeviceManager
    private let launchComponent = "com.nes.sound/.component.activity.SoundLocateActivity"

    init(deviceManager: DeviceManager) { self.deviceManager = deviceManager }

    func chooseDefault() { pick { self.defaultPath = $0 } }
    func chooseCustom() { pick { self.customPath = $0 } }

    private func pick(_ assign: @escaping (String) -> Void) {
        let panel = NSOpenPanel()
        panel.canChooseFiles = true; panel.canChooseDirectories = false
        panel.allowedContentTypes = [.audio, .wav]
        if panel.runModal() == .OK, let url = panel.url { assign(url.path) }
    }

    func start() async {
        guard let serial = deviceManager.selectedOnlineDevice else { status = "请先选择已连接的设备"; return }
        let file = (source == .default ? defaultPath : customPath).trimmingCharacters(in: .whitespaces)
        guard !file.isEmpty, FileManager.default.fileExists(atPath: file) else {
            status = source == .default ? "默认测试音频文件不存在，请先选择有效文件" : "请选择有效的音频文件"
            return
        }
        isBusy = true; defer { isBusy = false }
        do {
            status = "正在推送音频…"
            _ = try await ADBService.shared.runAsync(["push", file, "/sdcard/test.wav"], deviceSerial: serial, timeout: 120)
            status = "正在启动喇叭测试应用…"
            _ = try await ADBService.shared.shellAsync("am start -n \(launchComponent)", deviceSerial: serial)
            status = "喇叭测试已启动"
        } catch {
            status = "失败：\(error.localizedDescription)"
        }
    }
}
