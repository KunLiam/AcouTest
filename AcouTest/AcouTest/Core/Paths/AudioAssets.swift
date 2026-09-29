import Foundation

/// 内置音频资源定位（多声道/喇叭/扫频默认片源已打包进 App Bundle）
enum AudioAssets {
    /// 多声道预设 → 默认音频文件名（对应 audio/channel/）
    static let multichannelByPreset: [String: String] = [
        "7.1": "Nums_7dot1_16_48000",
        "2.1": "Nums_2dot1_16_48000",
        "2.0": "Nums_2dot0_16_48000",
    ]

    /// 喇叭默认音频（对应 audio/speaker/speaker_default.wav）
    static let speakerDefault = "speaker_default"

    /// 扫频内置片源（对应 audio/elephant/）
    static let sweepFiles = [
        "1KHZ_TEST",
        "20_20KHZ_0dBFS_48K_16bit",
        "20_20KHZ_0dB_SWEEP",
        "20_20KHZ_SWEEP_48K_16BIT",
        "20_20kHZ_61point_0dbfs",
        "sweep_speech_48k",
        "08_Let_the_Beat_Go_On",
    ]

    /// 按文件名（不含扩展名）查找打包的 wav 路径
    static func url(named name: String) -> URL? {
        Bundle.main.url(forResource: name, withExtension: "wav")
    }

    static func path(named name: String) -> String? {
        url(named: name)?.path
    }

    static func multichannelPath(preset: String) -> String? {
        guard let name = multichannelByPreset[preset] else { return nil }
        return path(named: name)
    }
}
