import Foundation

/// 测试输出目录（对应 output_paths.py）
enum OutputPaths {
    /// 测试数据根目录：~/AcouTest/output（GUI 应用工作目录为 /，不能用 cwd）
    static var root: URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("AcouTest", isDirectory: true)
            .appendingPathComponent("output", isDirectory: true)
    }

    enum Subdir: String {
        case logcat
        case screenshots
        case micTest = "mic_test"
        case sweepRecordings = "sweep_recordings"
        case airtightness
        case loopback
        case halDump = "hal_dump"
        case halCustom = "hal_custom"
        case wakeupKardome = "wakeup_kardome_hal"
    }

    static func url(for subdir: Subdir) -> URL {
        root.appendingPathComponent(subdir.rawValue, isDirectory: true)
    }

    static func ensure(_ subdir: Subdir) throws -> URL {
        let dir = url(for: subdir)
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }
}
