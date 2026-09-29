import SwiftUI

struct MicTestView: View {
    @StateObject private var viewModel: MicTestViewModel

    init(deviceManager: DeviceManager) {
        _viewModel = StateObject(wrappedValue: MicTestViewModel(deviceManager: deviceManager))
    }

    var body: some View {
        FeatureContainer(title: "麦克风测试") {
            Card(title: "测试设置") {
                LabeledField("麦克风数量 (-c)", text: $viewModel.micCount, disabled: viewModel.isRecording)
                LabeledField("PCM 设备号 (-D)", text: $viewModel.pcmDevice, disabled: viewModel.isRecording)
                LabeledField("设备 / 卡号 (-d)", text: $viewModel.cardId, disabled: viewModel.isRecording)
                LabeledField("采样率 (-r)", text: $viewModel.sampleRate, disabled: viewModel.isRecording)
                LabeledRow(label: "保存路径") {
                    TextField("保存路径", text: $viewModel.savePath)
                        .textFieldStyle(.roundedBorder).disabled(viewModel.isRecording)
                    Button("浏览…") { viewModel.chooseFolder() }
                        .buttonStyle(.secondaryAction).disabled(viewModel.isRecording)
                }
            }

            ActionBar {
                Button { viewModel.start() } label: { Label("开始录制", systemImage: "record.circle") }
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
