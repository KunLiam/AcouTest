import Foundation
import Combine

/// 唤醒监测（对应 ui_components.setup_hotword_monitor_tab 监测核心）
/// 按「唤醒语料库」匹配 logcat 关键字统计唤醒次数，支持重置 + 唤醒后操作。
@MainActor
final class WakeupMonitorViewModel: ObservableObject {
    /// 语料库 → 唤醒计数关键词（对应 _hotword_keywords_for）
    enum Corpus: String, CaseIterable, Identifiable {
        case okGoogle = "ok_google"
        case okFreebox = "ok_freebox"
        case okHoma = "ok_homa"
        case magenta = "magenta"
        var id: String { rawValue }

        var keywords: [String] {
            switch self {
            case .okGoogle:
                return ["Detected hotword", "LIBAS_HOTWORD_DETECTION_RECEIVED"]
            case .okFreebox:
                return ["KardomeJni: Keyword recognized!",
                        "Report wakeup phrase by current_kws_type=1 -> ok_freebox",
                        "Received wake-up event: 1", "kws wakeup",
                        "VOICE_PREPROCESS_WAKEUP sent phrase=ok_freebox"]
            case .okHoma:
                return ["Received wake-up event: 1"]
            case .magenta:
                return ["[KS] Keyword recognized: magenta"]
            }
        }
    }

    /// 唤醒后操作（对应 hotword_after_key_var）
    enum AfterAction: String, CaseIterable, Identifiable {
        case none = "不关闭"
        case back = "返回键(BACK)"
        case home = "Home键(HOME)"
        var id: String { rawValue }
        var keycode: String? {
            switch self {
            case .none: return nil
            case .back: return "BACK"
            case .home: return "HOME"
            }
        }
    }

    @Published var corpus: Corpus = .okGoogle
    @Published var afterAction: AfterAction = .none
    @Published var afterDelay = "2"
    @Published var status = "就绪"
    @Published var wakeupCount = 0
    @Published var isMonitoring = false
    @Published var recentHits: [String] = []

    /// 当前语料库对应的匹配关键词（界面展示「匹配规则」）
    var currentKeywords: [String] { corpus.keywords }

    private let deviceManager: DeviceManager
    private let monitor = LogcatMonitor()
    private var lastHit = Date.distantPast
    private let debounce: TimeInterval = 1.5

    init(deviceManager: DeviceManager) { self.deviceManager = deviceManager }

    func toggle() { isMonitoring ? stop() : start() }

    func reset() {
        wakeupCount = 0
        recentHits = []
        status = "已重置计数"
    }

    private func start() {
        guard let serial = deviceManager.selectedOnlineDevice else { status = "请先选择已连接的设备"; return }
        wakeupCount = 0
        recentHits = []
        lastHit = .distantPast
        let keywords = corpus.keywords
        let ok = monitor.start(serial: serial, keywords: keywords) { [weak self] line, _ in
            Task { @MainActor in
                self?.handleHit(line: line, serial: serial)
            }
        }
        if ok {
            isMonitoring = true
            status = "正在监测唤醒（语料：\(corpus.rawValue)）…"
        } else {
            status = "启动 logcat 失败"
        }
    }

    private func handleHit(line: String, serial: String) {
        let now = Date()
        if now.timeIntervalSince(lastHit) < debounce { return }
        lastHit = now
        wakeupCount += 1
        recentHits.insert("[\(wakeupCount)] \(line)", at: 0)
        if recentHits.count > 50 { recentHits.removeLast() }

        // 唤醒后操作：延迟后发送按键
        if let keycode = afterAction.keycode {
            let delay = Double(afterDelay) ?? 2
            Task {
                try? await Task.sleep(nanoseconds: UInt64(delay * 1_000_000_000))
                _ = try? await ADBService.shared.shellAsync("input keyevent KEYCODE_\(keycode)", deviceSerial: serial)
            }
        }
    }

    private func stop() {
        monitor.stop()
        isMonitoring = false
        status = "已停止，共检测到 \(wakeupCount) 次唤醒"
    }
}
