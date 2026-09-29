import SwiftUI

/// 功能占位页：尚未迁移的功能展示，标注对应 Python 实现
struct FeaturePlaceholderView: View {
    let subTab: String
    let pythonReference: String

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "hammer.fill")
                .font(.system(size: 44))
                .foregroundStyle(.secondary)
            Text(subTab)
                .font(.title2.bold())
            Text("Swift 迁移进行中")
                .foregroundStyle(.secondary)
            Text("Python 对照: \(pythonReference)")
                .font(.caption)
                .foregroundStyle(.tertiary)
                .multilineTextAlignment(.center)
                .padding(.horizontal)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// 子功能 → 视图路由；已迁移的接真实视图，其余用占位
enum FeatureRouter {
    @MainActor @ViewBuilder
    static func view(for subTabID: String, title: String) -> some View {
        InjectingFeatureView(subTabID: subTabID, title: title)
    }
}

/// 取出环境中的 DeviceManager 并分发到各功能视图
private struct InjectingFeatureView: View {
    let subTabID: String
    let title: String
    @EnvironmentObject private var deviceManager: DeviceManager

    var body: some View {
        switch subTabID {
        // —— 硬件测试 ——
        case "mic":
            MicTestView(deviceManager: deviceManager)
        case "radar":
            RadarCheckView(deviceManager: deviceManager)
        case "speaker":
            SpeakerTestView(deviceManager: deviceManager)
        case "multichannel":
            MultichannelTestView(deviceManager: deviceManager)

        // —— 声学测试 ——
        case "sweep":
            SweepTestView(deviceManager: deviceManager)

        // —— 音频调试 ——
        case "loopback":
            LoopbackTestView(deviceManager: deviceManager)
        case "hal":
            HALRecordingView(deviceManager: deviceManager)
        case "logcat":
            LogcatView(deviceManager: deviceManager)
        case "wakeup":
            WakeupMonitorView(deviceManager: deviceManager)
        case "syscmd":
            SystemCommandView(deviceManager: deviceManager)

        // —— 常用功能 ——
        case "remote":
            RemoteControlView(deviceManager: deviceManager)
        case "screenshot":
            ScreenshotView(deviceManager: deviceManager)
        case "account":
            AccountLoginView(deviceManager: deviceManager)

        // —— 烧大象 key ——
        case "snkey":
            SNKeyBurnView(deviceManager: deviceManager)

        // —— 暂未迁移（依赖音频分析/语料/Windows DLL，后续处理）——
        case "airtightness":
            FeaturePlaceholderView(subTab: title, pythonReference: "ui_components.start_airtightness_test（需波形分析）")
        case "jitter":
            FeaturePlaceholderView(subTab: title, pythonReference: "ui_components.start_jitter_test（需波形分析）")
        case "corpus":
            FeaturePlaceholderView(subTab: title, pythonReference: "generate_wake_word（依赖 edge-tts 语料生成）")
        case "playback":
            FeaturePlaceholderView(subTab: title, pythonReference: "ui_components.play_local_audio")
        case "openclaw":
            FeaturePlaceholderView(subTab: title, pythonReference: "control_api.AcouTestControlApi（HTTP 控制接口）")
        default:
            FeaturePlaceholderView(subTab: title, pythonReference: "unknown")
        }
    }
}
