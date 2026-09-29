import SwiftUI

struct SweepTestView: View {
    @StateObject private var viewModel: SweepTestViewModel

    init(deviceManager: DeviceManager) {
        _viewModel = StateObject(wrappedValue: SweepTestViewModel(deviceManager: deviceManager))
    }

    var body: some View {
        FeatureContainer(title: "扫频测试") {
            Card(title: "测试设置") {
                LabeledRow(label: "扫频音频") {
                    TextField("选择 wav 文件", text: $viewModel.audioPath)
                        .textFieldStyle(.roundedBorder)
                    Button("浏览…") { viewModel.chooseAudio() }.buttonStyle(.secondaryAction)
                }
                LabeledField("录制设备 (-d)", text: $viewModel.recordingDevice, disabled: viewModel.isBusy)
                LabeledField("通道数 (-c)", text: $viewModel.channels, disabled: viewModel.isBusy)
                LabeledField("采样率 (-r)", text: $viewModel.sampleRate, disabled: viewModel.isBusy)
                LabeledField("位深 (-b)", text: $viewModel.bitDepth, disabled: viewModel.isBusy)
                LabeledField("录制时长(秒)", text: $viewModel.duration, disabled: viewModel.isBusy)
                LabeledRow(label: "保存路径") {
                    TextField("保存路径", text: $viewModel.savePath)
                        .textFieldStyle(.roundedBorder).disabled(viewModel.isBusy)
                    Button("浏览…") { viewModel.chooseFolder() }.buttonStyle(.secondaryAction).disabled(viewModel.isBusy)
                }
            }

            ActionBar {
                Button { Task { await viewModel.start() } } label: {
                    Label("开始扫频测试", systemImage: "waveform.path")
                }
                .buttonStyle(.primaryAction).disabled(viewModel.isBusy)
                Button { viewModel.openFolder() } label: { Label("打开目录", systemImage: "folder") }
                    .buttonStyle(.secondaryAction)
            }

            StatusLine(text: viewModel.status)
        }
    }
}
