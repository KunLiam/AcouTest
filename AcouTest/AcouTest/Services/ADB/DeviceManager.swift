import Foundation
import Combine

/// 设备列表与选中状态（对应 DeviceOperations）
@MainActor
final class DeviceManager: ObservableObject {
    @Published private(set) var devices: [ADBDevice] = []
    @Published var selectedDeviceID: String = ""
    @Published private(set) var statusMessage: String = "未连接设备"
    @Published private(set) var isRefreshing = false

    var selectedOnlineDevice: String? {
        guard devices.contains(where: { $0.id == selectedDeviceID && $0.isOnline }) else { return nil }
        return selectedDeviceID
    }

    var onlineDevices: [ADBDevice] {
        devices.filter(\.isOnline)
    }

    func refresh() async {
        isRefreshing = true
        defer { isRefreshing = false }
        do {
            let list = try await Task.detached { try ADBService.shared.listDevices() }.value
            devices = list
            if let first = onlineDevices.first?.id {
                if !onlineDevices.contains(where: { $0.id == selectedDeviceID }) {
                    selectedDeviceID = first
                }
                statusMessage = "已连接: \(selectedDeviceID)"
            } else if let first = devices.first {
                selectedDeviceID = first.id
                statusMessage = "设备 \(first.id) 离线/未授权"
            } else {
                selectedDeviceID = ""
                statusMessage = "未检测到设备（请插 USB 并点刷新）"
            }
        } catch {
            devices = []
            selectedDeviceID = ""
            statusMessage = error.localizedDescription
        }
    }

    func requireDevice() throws -> String {
        guard let serial = selectedOnlineDevice else {
            throw ADBError.commandFailed("请先选择已连接的设备")
        }
        return serial
    }

    /// 网络 ADB 连接（对应 devices_operations.show_network_connect_dialog）
    /// 返回结果文案；成功后自动刷新设备列表。
    func connectNetwork(address: String) async -> String {
        let addr = address.trimmingCharacters(in: .whitespaces)
        guard !addr.isEmpty else { return "请输入设备地址" }
        do {
            let out = try await ADBService.shared.runAsync(["connect", addr], timeout: 20)
            let lower = out.lowercased()
            if lower.contains("connected") {
                await refresh()
                return "已连接到 \(addr)"
            }
            return "连接失败：\(out.trimmingCharacters(in: .whitespacesAndNewlines))"
        } catch {
            return "连接错误：\(error.localizedDescription)"
        }
    }
}
