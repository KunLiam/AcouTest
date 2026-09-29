import Foundation

/// 行缓冲（在后台读取线程使用，不触碰 MainActor 状态）
private final class LineBuffer: @unchecked Sendable {
    private var buffer = ""
    private let lock = NSLock()
    let keywords: [String]
    let onMatch: (_ line: String, _ keyword: String) -> Void

    init(keywords: [String], onMatch: @escaping (_ line: String, _ keyword: String) -> Void) {
        self.keywords = keywords
        self.onMatch = onMatch
    }

    func feed(_ chunk: String) {
        lock.lock(); defer { lock.unlock() }
        buffer += chunk
        while let nl = buffer.firstIndex(of: "\n") {
            let line = String(buffer[..<nl])
            buffer = String(buffer[buffer.index(after: nl)...])
            for kw in keywords where !kw.isEmpty && line.contains(kw) {
                onMatch(line, kw)
                break
            }
        }
    }
}

/// 通用 logcat 关键词监测（雷达检查、唤醒监测共用）
/// 启动 `adb logcat`，对每行匹配关键词，命中时回调（回调在后台线程，调用方需切回主线程）。
@MainActor
final class LogcatMonitor {
    private var process: Process?

    func start(serial: String?, keywords: [String], onMatch: @escaping @Sendable (_ line: String, _ keyword: String) -> Void) -> Bool {
        stop()
        let proc = ADBService.shared.makeProcess(["logcat", "-v", "time"], deviceSerial: serial)
        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = pipe
        let lineBuffer = LineBuffer(keywords: keywords, onMatch: onMatch)
        pipe.fileHandleForReading.readabilityHandler = { fh in
            let data = fh.availableData
            guard !data.isEmpty, let chunk = String(data: data, encoding: .utf8) else { return }
            lineBuffer.feed(chunk)
        }
        do {
            try proc.run()
        } catch {
            return false
        }
        process = proc
        return true
    }

    func stop() {
        if let proc = process {
            (proc.standardOutput as? Pipe)?.fileHandleForReading.readabilityHandler = nil
            if proc.isRunning { proc.terminate() }
        }
        process = nil
    }

    var isRunning: Bool { process?.isRunning ?? false }
}
