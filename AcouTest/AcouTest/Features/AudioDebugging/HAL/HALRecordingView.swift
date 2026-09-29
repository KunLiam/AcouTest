import SwiftUI

struct HALRecordingView: View {
    @StateObject private var viewModel: HALRecordingViewModel

    init(deviceManager: DeviceManager) {
        _viewModel = StateObject(wrappedValue: HALRecordingViewModel(deviceManager: deviceManager))
    }

    var body: some View {
        FeatureContainer(title: "HAL 录音") {
            Card(title: "录音设置") {
                LabeledRow(label: "设备录音目录") {
                    TextField("如 data/vendor/audiohal", text: $viewModel.remoteDir)
                        .textFieldStyle(.roundedBorder).disabled(viewModel.isRecording)
                }
                LabeledRow(label: "本地保存路径") {
                    TextField("保存路径", text: $viewModel.savePath)
                        .textFieldStyle(.roundedBorder).disabled(viewModel.isRecording)
                    Button("浏览…") { viewModel.chooseFolder() }.buttonStyle(.secondaryAction).disabled(viewModel.isRecording)
                }
            }

            Card(title: "录音属性") {
                HStack {
                    Spacer()
                    Button("全选") { viewModel.toggleAll(true) }.buttonStyle(.borderless)
                    Button("全不选") { viewModel.toggleAll(false) }.buttonStyle(.borderless)
                }
                ForEach($viewModel.props) { $prop in
                    Toggle(isOn: $prop.enabled) {
                        Text("\(prop.name) = \(prop.onValue)")
                            .font(.system(size: 12, design: .monospaced))
                    }
                    .disabled(viewModel.isRecording)
                }
            }

            ActionBar {
                Button { Task { await viewModel.startRecording() } } label: {
                    Label("开始录音", systemImage: "record.circle")
                }
                .buttonStyle(.primaryAction).disabled(viewModel.isRecording)
                Button { Task { await viewModel.stopRecording() } } label: {
                    Label("停止录音并拉取", systemImage: "stop.circle")
                }
                .buttonStyle(.secondaryAction).disabled(!viewModel.isRecording)
                Button { viewModel.openFolder() } label: { Label("打开目录", systemImage: "folder") }
                    .buttonStyle(.secondaryAction)
            }

            StatusLine(text: viewModel.status)

            Card(title: "操作日志") {
                MonospacedOutput(text: viewModel.log).frame(minHeight: 200)
            }
        }
    }
}
