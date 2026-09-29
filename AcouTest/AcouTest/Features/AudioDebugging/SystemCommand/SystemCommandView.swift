import SwiftUI

struct SystemCommandView: View {
    @StateObject private var viewModel: SystemCommandViewModel

    init(deviceManager: DeviceManager) {
        _viewModel = StateObject(wrappedValue: SystemCommandViewModel(deviceManager: deviceManager))
    }

    private let columns = [GridItem(.adaptive(minimum: 200), spacing: 10)]

    var body: some View {
        FeatureContainer(title: "系统指令") {
            Card(title: "预设指令") {
                Text("点击按钮获取设备信息；reboot 类直接下发不展示输出")
                    .font(.caption).foregroundStyle(.secondary)
                LazyVGrid(columns: columns, alignment: .leading, spacing: 10) {
                    ForEach(viewModel.presets) { preset in
                        Button {
                            Task { await viewModel.run(preset.command, silently: preset.runSilently) }
                        } label: {
                            Text(preset.label).frame(maxWidth: .infinity).lineLimit(1)
                        }
                        .buttonStyle(.secondaryAction)
                        .disabled(viewModel.isRunning)
                    }
                }
            }

            Card(title: "自定义指令") {
                HStack {
                    TextField("如：dumpsys media.audio", text: $viewModel.customCommand)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit { Task { await viewModel.run(viewModel.customCommand, silently: false) } }
                    Button("运行") { Task { await viewModel.run(viewModel.customCommand, silently: false) } }
                        .buttonStyle(.primaryAction).disabled(viewModel.isRunning)
                    Button("添加") { viewModel.addCustom() }.buttonStyle(.secondaryAction)
                }
                ForEach(viewModel.customList, id: \.self) { cmd in
                    HStack {
                        Text(cmd).font(.system(size: 12, design: .monospaced))
                        Spacer()
                        Button { Task { await viewModel.run(cmd, silently: false) } } label: { Image(systemName: "play.fill") }
                            .buttonStyle(.borderless)
                        Button { viewModel.deleteCustom(cmd) } label: { Image(systemName: "trash") }
                            .buttonStyle(.borderless)
                    }
                    .padding(.vertical, 2)
                }
            }

            StatusLine(text: viewModel.status)

            Card(title: "命令输出") {
                HStack {
                    Spacer()
                    Button("保存输出") { viewModel.saveOutput() }
                        .buttonStyle(.secondaryAction).disabled(viewModel.output.isEmpty)
                }
                MonospacedOutput(text: viewModel.output).frame(minHeight: 240)
            }
        }
    }
}
