import SwiftUI

struct SpeakerTestView: View {
    @StateObject private var viewModel: SpeakerTestViewModel

    init(deviceManager: DeviceManager) {
        _viewModel = StateObject(wrappedValue: SpeakerTestViewModel(deviceManager: deviceManager))
    }

    var body: some View {
        FeatureContainer(title: "喇叭测试") {
            Card(title: "测试设置") {
                Text("将选定音频推送到设备 /sdcard/test.wav，并启动系统喇叭测试应用。")
                    .font(.caption).foregroundStyle(.secondary)

                Picker("音频来源", selection: $viewModel.source) {
                    ForEach(SpeakerTestViewModel.AudioSource.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
                .labelsHidden()
                .disabled(viewModel.isBusy)

                if viewModel.source == .default {
                    LabeledRow(label: "默认音频") {
                        TextField("默认测试音频路径", text: $viewModel.defaultPath)
                            .textFieldStyle(.roundedBorder).disabled(viewModel.isBusy)
                        Button("浏览…") { viewModel.chooseDefault() }.buttonStyle(.secondaryAction)
                    }
                } else {
                    LabeledRow(label: "自定义音频") {
                        TextField("选择 wav 文件", text: $viewModel.customPath)
                            .textFieldStyle(.roundedBorder).disabled(viewModel.isBusy)
                        Button("浏览…") { viewModel.chooseCustom() }.buttonStyle(.secondaryAction)
                    }
                }
            }

            ActionBar {
                Button { Task { await viewModel.start() } } label: {
                    Label("启动喇叭测试", systemImage: "speaker.wave.3")
                }
                .buttonStyle(.primaryAction).disabled(viewModel.isBusy)
            }

            StatusLine(text: viewModel.status)
        }
    }
}
