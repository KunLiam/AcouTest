import SwiftUI

struct LoopbackTestView: View {
    @StateObject private var viewModel: LoopbackTestViewModel

    init(deviceManager: DeviceManager) {
        _viewModel = StateObject(wrappedValue: LoopbackTestViewModel(deviceManager: deviceManager))
    }

    var body: some View {
        FeatureContainer(title: "Loopback 和 Ref 测试") {
            Card(title: "测试设置") {
                LabeledField("录制设备 (-d)", text: $viewModel.recordDevice, disabled: viewModel.isRecording)
                LabeledField("通道数 (-c)", text: $viewModel.channels, disabled: viewModel.isRecording)
                LabeledField("采样率 (-r)", text: $viewModel.sampleRate, disabled: viewModel.isRecording)
                LabeledRow(label: "保存路径") {
                    TextField("保存路径", text: $viewModel.savePath)
                        .textFieldStyle(.roundedBorder).disabled(viewModel.isRecording)
                    Button("浏览…") { viewModel.chooseFolder() }.buttonStyle(.secondaryAction).disabled(viewModel.isRecording)
                }
            }

            ActionBar {
                Button { viewModel.start() } label: { Label("开始测试", systemImage: "record.circle") }
                    .buttonStyle(.primaryAction).disabled(viewModel.isRecording)
                Button { Task { await viewModel.stop() } } label: { Label("停止并拉取", systemImage: "stop.circle") }
                    .buttonStyle(.secondaryAction).disabled(!viewModel.isRecording)
                Button { viewModel.openFolder() } label: { Label("打开目录", systemImage: "folder") }
                    .buttonStyle(.secondaryAction)
            }

            StatusLine(text: viewModel.status)
        }
    }
}
