import Foundation
import Combine

/// 雷达检查（对应 ui_components.setup_radar_tab：TTY 检查 / Logcat 监控 / AIEQ 指南）
@MainActor
final class RadarCheckViewModel: ObservableObject {
    // 通用状态
    @Published var status = "就绪"

    // 方法一：TTY 设备检查
    @Published var ttyResult = ""
    @Published var isCheckingTTY = false

    // 方法二：Logcat 监控（默认关键词 updateGain）
    @Published var keyword = "updateGain"
    @Published var isMonitoring = false
    @Published var hitCount = 0
    @Published var monitorLines: [String] = []

    private let deviceManager: DeviceManager
    private let monitor = LogcatMonitor()

    init(deviceManager: DeviceManager) { self.deviceManager = deviceManager }

    // MARK: TTY 设备检查
    func checkTTY() {
        guard let serial = deviceManager.selectedOnlineDevice else { status = "请先选择已连接的设备"; return }
        isCheckingTTY = true
        status = "正在检查 TTY 设备…"
        ttyResult = "正在检查 TTY 设备…\n"
        Task {
            do {
                // 列出 /dev 全部节点再在本机过滤，避免通配符在设备端不展开
                let out = try await ADBService.shared.shellAsync("ls -la /dev/", deviceSerial: serial)
                let lines = out.split(separator: "\n").map(String.init)
                let ttyLines = lines.filter { $0.lowercased().contains("tty") }
                let acm = lines.filter { $0.contains("ttyACM") }
                var text = "TTY 设备列表:\n"
                text += ttyLines.isEmpty ? "（未发现 tty 节点）\n" : ttyLines.joined(separator: "\n") + "\n"
                if acm.isEmpty {
                    text += "\n未检测到 ttyACM 设备：可能没有雷达节点。\n"
                    status = "检查完成：未检测到雷达传感器"
                } else {
                    text += "\n检测到 ttyACM 设备:\n" + acm.joined(separator: "\n")
                    text += "\n\n✅ 雷达传感器已连接；是否正常工作还需打开 AIEQ 的 Sweet Spot 后再看 Logcat。\n"
                    status = "检查完成：已检测到雷达传感器"
                }
                ttyResult = text
            } catch {
                ttyResult = "检查失败：\(error.localizedDescription)\n\n提示：部分设备 /dev 访问需要 root，可先在系统指令里执行 adb root。"
                status = "检查失败"
            }
            isCheckingTTY = false
        }
    }

    // MARK: Logcat 监控
    func toggleMonitor() { isMonitoring ? stopMonitor() : startMonitor() }

    private func startMonitor() {
        guard let serial = deviceManager.selectedOnlineDevice else { status = "请先选择已连接的设备"; return }
        let kw = keyword.trimmingCharacters(in: .whitespaces)
        guard !kw.isEmpty else { status = "请填写监测关键词"; return }
        hitCount = 0
        monitorLines = ["请用手或物体靠近/远离雷达传感器区域，观察 \(kw) 值变化…"]
        let ok = monitor.start(serial: serial, keywords: [kw]) { [weak self] line, _ in
            Task { @MainActor in
                guard let self else { return }
                self.hitCount += 1
                self.monitorLines.insert(line, at: 0)
                if self.monitorLines.count > 80 { self.monitorLines.removeLast() }
            }
        }
        if ok {
            isMonitoring = true
            status = "正在监控雷达日志（关键词：\(kw)）…"
        } else {
            status = "启动 logcat 失败"
        }
    }

    private func stopMonitor() {
        monitor.stop()
        isMonitoring = false
        status = "已停止监控，共命中 \(hitCount) 次"
    }
}
