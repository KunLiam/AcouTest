import SwiftUI

struct AccountLoginView: View {
    @StateObject private var viewModel: AccountLoginViewModel

    init(deviceManager: DeviceManager) {
        _viewModel = StateObject(wrappedValue: AccountLoginViewModel(deviceManager: deviceManager))
    }

    var body: some View {
        FeatureContainer(title: "账号登录") {
            Card(title: "操作步骤") {
                Text("在设备上聚焦账号输入框 → 点「输入账号」→ 设备上点 Next → 聚焦密码框 → 点「输入密码」")
                    .font(.callout).foregroundStyle(.secondary)
            }

            Card(title: "账号信息") {
                LabeledRow(label: "账号") {
                    TextField("邮箱 / 账号", text: $viewModel.email)
                        .textFieldStyle(.roundedBorder)
                }
                LabeledRow(label: "密码") {
                    SecureField("密码", text: $viewModel.password)
                        .textFieldStyle(.roundedBorder)
                }
            }

            ActionBar {
                Button { viewModel.inputEmail() } label: { Label("输入账号", systemImage: "person") }
                    .buttonStyle(.primaryAction)
                Button { viewModel.inputPassword() } label: { Label("输入密码", systemImage: "key") }
                    .buttonStyle(.secondaryAction)
            }

            StatusLine(text: viewModel.status)
        }
    }
}
