import Foundation
import AppKit
import Combine

/// logcat 调试属性（对应 ui_components.logcat_props / enable_logcat_debug / disable_logcat_debug）
struct LogcatProp: Identifiable {
    let id = UUID()
    let name: String
    let debugValue: String   // 放开日志时写入的值
    var enabled: Bool
    /// 停止日志时恢复的值：APM 日志恢复为 D，其余为 0
    var normalValue: String { name == "log.tag.APM_AudioPolicyManager" ? "D" : "0" }
}

/// Logcat 抓取（对应 test_operations.start_logcat_capture / stop_logcat_capture）
@MainActor
final class LogcatViewModel: ObservableObject {
    @Published var status: String = "就绪"
    @Published var savePath: String = OutputPaths.url(for: .logcat).path
    @Published var filterSpec: String = "*:V"
    @Published var isCapturing = false
    @Published var currentFile: String?
    @Published var tailPreview: String = ""

    // 属性管理
    @Published var props: [LogcatProp] = LogcatViewModel.defaultProps
    @Published var newPropText = ""
    @Published var debugEnabled = false
    @Published var isApplyingProps = false

    private let deviceManager: DeviceManager
    private var process: Process?
    private var fileHandle: FileHandle?

    init(deviceManager: DeviceManager) {
        self.deviceManager = deviceManager
    }

    static let defaultProps: [LogcatProp] = [
        ("vendor.avdebug.debug", "1"),
        ("vendor.avdebug.dspc-debug", "1"),
        ("sys.droidlogic.audio.debug", "1"),
        ("vendor.media.audio.hal.debug", "4096"),
        ("media.audio.hal.debug", "4096"),
        ("vendor.media.audiohal.debug", "4096"),
        ("vendor.media.audiohal.hwsync", "1"),
        ("vendor.media.c2.audio.decoder.debug", "1"),
        ("vendor.media.omx.audio.dump", "1"),
        ("vendor.media.droidaudio.debug", "1"),
        ("log.tag.APM_AudioPolicyManager", "V"),
    ].map { LogcatProp(name: $0.0, debugValue: $0.1, enabled: true) }

    // MARK: 属性管理
    func toggleAllProps(_ on: Bool) {
        for i in props.indices { props[i].enabled = on }
    }

    func addProp() {
        let text = newPropText.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return }
        let parts = text.split(separator: " ", maxSplits: 1).map(String.init)
        let name = parts[0]
        let value = parts.count >= 2 ? parts[1] : "1"
        guard !props.contains(where: { $0.name == name }) else {
            status = "属性已存在：\(name)"; return
        }
        props.append(LogcatProp(name: name, debugValue: value, enabled: true))
        newPropText = ""
        status = "已添加属性：\(name)=\(value)"
    }

    func deleteProp(_ prop: LogcatProp) {
        props.removeAll { $0.id == prop.id }
    }

    /// 放开日志打印：adb root 后 setprop 选中的属性为调试值
    func enableDebug() {
        applyProps(enable: true)
    }

    /// 停止日志打印：恢复属性为正常值
    func disableDebug() {
        applyProps(enable: false)
    }

    private func applyProps(enable: Bool) {
        guard let serial = deviceManager.selectedOnlineDevice else { status = "请先选择已连接的设备"; return }
        let selected = props.filter(\.enabled)
        guard !selected.isEmpty else { status = "请先勾选要设置的属性"; return }
        isApplyingProps = true
        status = enable ? "正在放开日志打印…" : "正在停止日志打印…"
        Task {
            _ = try? await ADBService.shared.runAsync(["root"], deviceSerial: serial)
            try? await Task.sleep(nanoseconds: 800_000_000)
            var failed: [String] = []
            for prop in selected {
                let value = enable ? prop.debugValue : prop.normalValue
                do {
                    _ = try await ADBService.shared.shellAsync("setprop \(prop.name) \(value)", deviceSerial: serial)
                } catch {
                    failed.append(prop.name)
                }
            }
            debugEnabled = enable
            if failed.isEmpty {
                status = enable ? "日志打印已放开（已设置 \(selected.count) 项）" : "日志打印已停止（已恢复 \(selected.count) 项）"
            } else {
                status = "部分属性设置失败：\(failed.joined(separator: ", "))"
            }
            isApplyingProps = false
        }
    }

    func startCapture() {
        guard !isCapturing else { return }
        let serial = deviceManager.selectedDeviceID

        let dir = savePath.isEmpty ? OutputPaths.url(for: .logcat).path : savePath
        do {
            try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        } catch {
            status = "创建目录失败：\(error.localizedDescription)"
            return
        }

        let timestamp = Self.timestamp()
        let filename = "audio_logcat_\(timestamp).txt"
        let filePath = (dir as NSString).appendingPathComponent(filename)
        FileManager.default.createFile(atPath: filePath, contents: nil)

        guard let handle = FileHandle(forWritingAtPath: filePath) else {
            status = "无法写入日志文件"
            return
        }
        fileHandle = handle
        currentFile = filePath
        tailPreview = ""

        let filter = filterSpec.trimmingCharacters(in: .whitespaces).isEmpty ? "*:V" : filterSpec
        // adb [-s serial] logcat -v threadtime <filter>
        var args = ["logcat", "-v", "threadtime"]
        args += filter.split(separator: " ").map(String.init)

        let proc = ADBService.shared.makeProcess(args, deviceSerial: serial.isEmpty ? nil : serial)
        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = pipe

        pipe.fileHandleForReading.readabilityHandler = { [weak self] fh in
            let data = fh.availableData
            guard !data.isEmpty else { return }
            try? handle.write(contentsOf: data)
            if let chunk = String(data: data, encoding: .utf8) {
                Task { @MainActor in
                    self?.appendPreview(chunk)
                }
            }
        }

        do {
            try proc.run()
        } catch {
            status = "启动 logcat 失败：\(error.localizedDescription)"
            cleanup()
            return
        }
        process = proc
        isCapturing = true
        status = "正在抓取日志 → \(filename)"
    }

    func stopCapture() {
        guard isCapturing else { return }
        status = "正在停止抓取…"
        if let proc = process, proc.isRunning {
            (proc.standardOutput as? Pipe)?.fileHandleForReading.readabilityHandler = nil
            proc.terminate()
        }
        cleanup()
        isCapturing = false
        status = "已停止。文件：\(currentFile.map { ($0 as NSString).lastPathComponent } ?? "-")"
    }

    func openFolder() {
        let dir = savePath.isEmpty ? OutputPaths.url(for: .logcat).path : savePath
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

    private func appendPreview(_ chunk: String) {
        tailPreview += chunk
        // 仅保留末尾 ~8000 字符，避免界面卡顿
        if tailPreview.count > 8000 {
            tailPreview = String(tailPreview.suffix(8000))
        }
    }

    private func cleanup() {
        try? fileHandle?.close()
        fileHandle = nil
        process = nil
    }

    private static func timestamp() -> String {
        let f = DateFormatter()
        f.dateFormat = "yyyyMMdd_HHmmss"
        return f.string(from: Date())
    }
}
