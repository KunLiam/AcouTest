import Foundation

/// 功能开关（对应 feature_config.py MAIN_TABS / SUB_TABS）
struct FeatureFlags {
    struct MainTab: Hashable, Identifiable {
        let id: String
        let title: String
        let enabled: Bool
        let subTabs: [SubTab]
    }

    struct SubTab: Hashable, Identifiable {
        let id: String
        let title: String
        let enabled: Bool
    }

    static let mainTabs: [MainTab] = [
        MainTab(id: "hardware", title: "硬件测试", enabled: true, subTabs: [
            SubTab(id: "mic", title: "麦克风测试", enabled: true),
            SubTab(id: "radar", title: "雷达检查", enabled: true),
            SubTab(id: "speaker", title: "喇叭测试", enabled: true),
            SubTab(id: "multichannel", title: "多声道测试", enabled: true),
        ]),
        MainTab(id: "acoustic", title: "声学测试", enabled: true, subTabs: [
            SubTab(id: "sweep", title: "扫频测试", enabled: true),
            SubTab(id: "airtightness", title: "气密性测试", enabled: true),
            SubTab(id: "jitter", title: "震音测试", enabled: true),
        ]),
        MainTab(id: "debug", title: "音频调试", enabled: true, subTabs: [
            SubTab(id: "loopback", title: "Loopback和Ref测试", enabled: true),
            SubTab(id: "hal", title: "HAL录音", enabled: true),
            SubTab(id: "logcat", title: "Logcat日志", enabled: true),
            SubTab(id: "wakeup", title: "唤醒监测", enabled: true),
            SubTab(id: "corpus", title: "语料生成", enabled: true),
            SubTab(id: "syscmd", title: "系统指令", enabled: true),
        ]),
        MainTab(id: "utilities", title: "常用功能", enabled: true, subTabs: [
            SubTab(id: "remote", title: "遥控器", enabled: true),
            SubTab(id: "playback", title: "本地播放", enabled: false),
            SubTab(id: "screenshot", title: "截图功能", enabled: true),
            SubTab(id: "openclaw", title: "OpenClaw", enabled: true),
            SubTab(id: "account", title: "账号登录", enabled: true),
        ]),
        MainTab(id: "keyburn", title: "烧大象key", enabled: true, subTabs: [
            SubTab(id: "snkey", title: "sn烧key", enabled: true),
        ]),
    ]

    static var enabledMainTabs: [MainTab] {
        mainTabs.filter(\.enabled)
    }
}
