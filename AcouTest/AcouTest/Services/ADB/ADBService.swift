import Foundation

struct ADBDevice: Identifiable, Hashable {
    let id: String
    let isOnline: Bool
}

enum ADBError: LocalizedError {
    case adbNotFound
    case commandFailed(String)
    case timeout

    var errorDescription: String? {
        switch self {
        case .adbNotFound: return "未找到 adb，请安装 Android Platform Tools 并加入 PATH"
        case .commandFailed(let msg): return msg
        case .timeout: return "ADB 命令超时"
        }
    }
}

/// 底层 ADB 进程调用（对应 devices_operations.get_adb_command）
final class ADBService {
    static let shared = ADBService()

    private init() {}

    /// 常见 adb 安装位置；优先使用存在的绝对路径，否则回退到 PATH 中的 adb
    var adbPath: String {
        let candidates = [
            "/opt/homebrew/bin/adb",
            "/usr/local/bin/adb",
            "\(NSHomeDirectory())/Library/Android/sdk/platform-tools/adb",
        ]
        for path in candidates where FileManager.default.isExecutableFile(atPath: path) {
            return path
        }
        return "adb"
    }

    /// 构造一个 adb 进程（含可选设备序列号），调用方负责 run / terminate
    func makeProcess(_ args: [String], deviceSerial: String? = nil) -> Process {
        var fullArgs: [String] = []
        if let serial = deviceSerial, !serial.isEmpty {
            fullArgs += ["-s", serial]
        }
        fullArgs += args

        let process = Process()
        let path = adbPath
        if path.contains("/") {
            process.executableURL = URL(fileURLWithPath: path)
            process.arguments = fullArgs
        } else {
            process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
            process.arguments = [path] + fullArgs
        }
        // 让子进程能在常见路径找到 adb 依赖
        var env = ProcessInfo.processInfo.environment
        let extraPaths = "/opt/homebrew/bin:/usr/local/bin:\(NSHomeDirectory())/Library/Android/sdk/platform-tools"
        env["PATH"] = (env["PATH"].map { "\($0):\(extraPaths)" }) ?? extraPaths
        process.environment = env
        return process
    }

    private func execute(_ args: [String], deviceSerial: String?, timeout: TimeInterval) throws -> (Data, String, Int32) {
        let process = makeProcess(args, deviceSerial: deviceSerial)
        let outPipe = Pipe()
        let errPipe = Pipe()
        process.standardOutput = outPipe
        process.standardError = errPipe

        do {
            try process.run()
        } catch {
            throw ADBError.adbNotFound
        }

        // 边读边收集，避免管道缓冲区写满导致死锁
        let outData = outPipe.fileHandleForReading.readDataToEndOfFile()
        let errData = errPipe.fileHandleForReading.readDataToEndOfFile()

        let deadline = Date().addingTimeInterval(timeout)
        while process.isRunning && Date() < deadline {
            Thread.sleep(forTimeInterval: 0.02)
        }
        if process.isRunning {
            process.terminate()
            throw ADBError.timeout
        }

        let stderr = String(data: errData, encoding: .utf8) ?? ""
        return (outData, stderr, process.terminationStatus)
    }

    @discardableResult
    func run(_ args: [String], deviceSerial: String? = nil, timeout: TimeInterval = 30) throws -> String {
        let (outData, stderr, status) = try execute(args, deviceSerial: deviceSerial, timeout: timeout)
        let stdout = String(data: outData, encoding: .utf8) ?? ""
        guard status == 0 else {
            throw ADBError.commandFailed(stderr.isEmpty ? stdout : stderr)
        }
        return stdout
    }

    /// 二进制输出（截图 screencap -p）
    func runData(_ args: [String], deviceSerial: String? = nil, timeout: TimeInterval = 30) throws -> Data {
        let (outData, stderr, status) = try execute(args, deviceSerial: deviceSerial, timeout: timeout)
        guard status == 0 else {
            throw ADBError.commandFailed(stderr)
        }
        return outData
    }

    func shell(_ command: String, deviceSerial: String? = nil, timeout: TimeInterval = 30) throws -> String {
        try run(["shell", command], deviceSerial: deviceSerial, timeout: timeout)
    }

    func pull(remote: String, localDir: String, deviceSerial: String? = nil, timeout: TimeInterval = 120) throws -> String {
        try run(["pull", remote, localDir], deviceSerial: deviceSerial, timeout: timeout)
    }

    func startServer() {
        _ = try? run(["start-server"])
    }

    func listDevices() throws -> [ADBDevice] {
        var devices = parseDevices(try run(["devices"]))
        if devices.isEmpty {
            startServer()
            Thread.sleep(forTimeInterval: 0.4)
            devices = parseDevices(try run(["devices"]))
        }
        return devices
    }

    private func parseDevices(_ output: String) -> [ADBDevice] {
        output.split(separator: "\n").dropFirst().compactMap { line in
            let parts = line.split(separator: "\t")
            guard parts.count >= 2 else { return nil }
            return ADBDevice(id: String(parts[0]), isOnline: String(parts[1]) == "device")
        }
    }
}

extension ADBService {
    func runAsync(_ args: [String], deviceSerial: String? = nil, timeout: TimeInterval = 30) async throws -> String {
        try await Task.detached(priority: .userInitiated) {
            try self.run(args, deviceSerial: deviceSerial, timeout: timeout)
        }.value
    }

    func shellAsync(_ command: String, deviceSerial: String? = nil, timeout: TimeInterval = 30) async throws -> String {
        try await Task.detached(priority: .userInitiated) {
            try self.shell(command, deviceSerial: deviceSerial, timeout: timeout)
        }.value
    }
}
