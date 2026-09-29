import SwiftUI

struct SNKeyBurnView: View {
    @StateObject private var viewModel: SNKeyBurnViewModel

    init(deviceManager: DeviceManager) {
        _viewModel = StateObject(wrappedValue: SNKeyBurnViewModel(deviceManager: deviceManager))
    }

    var body: some View {
        FeatureContainer(title: "sn烧key") {
            Card {
                Text("通过 ADB 读写设备 unifykeys/elevockey。license 由 SN 生成需 Windows 端 DLL，Mac 端可读 SN、读/写 elevockey。")
                    .font(.callout).foregroundStyle(.secondary)
            }

            Card(title: "读写操作") {
                LabeledRow(label: "SN(usid)") {
                    TextField("点击读取 SN", text: $viewModel.snValue).textFieldStyle(.roundedBorder)
                    Button("读取 SN") { viewModel.readSN() }.buttonStyle(.secondaryAction).disabled(viewModel.isBusy)
                }
                LabeledRow(label: "当前 key") {
                    TextField("点击读取当前 elevockey", text: $viewModel.currentKey).textFieldStyle(.roundedBorder)
                    Button("读取 key") { viewModel.readCurrentKey() }.buttonStyle(.secondaryAction).disabled(viewModel.isBusy)
                }
                LabeledRow(label: "license") {
                    TextField("待写入的 license（hex）", text: $viewModel.licenseHex).textFieldStyle(.roundedBorder)
                    Button("写入 key") { viewModel.writeKey() }.buttonStyle(.primaryAction).disabled(viewModel.isBusy)
                }
            }

            ActionBar {
                Button("列出 unifykeys") { viewModel.listKeys() }.buttonStyle(.secondaryAction).disabled(viewModel.isBusy)
            }

            Card(title: "操作日志") {
                MonospacedOutput(text: viewModel.log).frame(minHeight: 200)
            }
        }
    }
}
