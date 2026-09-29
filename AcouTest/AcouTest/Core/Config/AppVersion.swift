import Foundation

/// 应用版本与更新通道（对应 feature_config.py）
enum AppVersion {
    static let current = "2.1.6"
    static let displayName = "声测大师(AcouTest)"
}

enum ReleaseChannel: String {
    case `public`
    case `internal`
}

enum AppConfig {
    static let releaseChannel: ReleaseChannel = .internal
    static let updateAutoCheck = true
}
