import Foundation
import Combine

/// 账号登录（对应 ui_components._do_account_login_email_only / _password_only）
/// 通过 `adb shell input text` 向设备当前焦点输入框输入账号/密码。
@MainActor
final class AccountLoginViewModel: ObservableObject {
    @Published var email = ""
    @Published var password = ""
    @Published var status = "在设备上聚焦输入框后，点击下方按钮输入"

    private let deviceManager: DeviceManager

    init(deviceManager: DeviceManager) { self.deviceManager = deviceManager }

    func inputEmail() { inputText(email, label: "账号") }
    func inputPassword() { inputText(password, label: "密码") }

    private func inputText(_ raw: String, label: String) {
        let text = raw.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { status = "请先填写\(label)"; return }
        guard let serial = deviceManager.selectedOnlineDevice else { status = "请先选择已连接的设备"; return }
        // Android `input text` 用 %s 表示空格
        let escaped = text.replacingOccurrences(of: " ", with: "%s")
        status = "正在输入\(label)…"
        Task {
            do {
                _ = try await ADBService.shared.shellAsync("input text \(escaped)", deviceSerial: serial)
                status = "已输入\(label)，请在设备上继续操作（点 Next / 登录）"
            } catch {
                status = "输入\(label)失败：\(error.localizedDescription)"
            }
        }
    }
}
