import SwiftUI

struct MultichannelTestView: View {
    @StateObject private var viewModel: MultichannelTestViewModel

    init(deviceManager: DeviceManager) {
        _viewModel = StateObject(wrappedValue: MultichannelTestViewModel(deviceManager: deviceManager))
    }

    var body: some View {
        FeatureContainer(title: "多声道测试") {
            Card(title: "音频片源") {
                LabeledRow(label: "声道预设") {
                    Picker("", selection: $viewModel.preset) {
                        ForEach(viewModel.presets, id: \.self) { Text($0).tag($0) }
                    }.pickerStyle(.segmented).labelsHidden().frame(maxWidth: 220)
                }
                Toggle("使用内置默认片源（7.1/2.1/2.0）", isOn: $viewModel.useDefaultAudio)
                    .onChange(of: viewModel.useDefaultAudio) { _, on in
                        if on { viewModel.loadDefaultAudio() }
                    }
                LabeledRow(label: "音频文件") {
                    TextField("音频路径", text: $viewModel.audioPath)
                        .textFieldStyle(.roundedBorder).disabled(viewModel.isBusy)
                    Button("浏览…") { viewModel.chooseAudio() }.buttonStyle(.secondaryAction)
                }
            }

            Card(title: "播放参数") {
                LabeledField("采样率 (-r)", text: $viewModel.sampleRate, disabled: viewModel.isBusy)
                LabeledField("位深 (-b)", text: $viewModel.bitDepth, disabled: viewModel.isBusy)
                LabeledRow(label: "播放设备 (-d)") {
                    Picker("", selection: $viewModel.playDevice) {
                        ForEach(viewModel.playDeviceOptions, id: \.self) { Text($0).tag($0) }
                    }.labelsHidden().frame(width: 100)
                }
            }

            ActionBar {
                Button { Task { await viewModel.start() } } label: {
                    Label("开始多声道测试", systemImage: "hifispeaker.2")
                }
                .buttonStyle(.primaryAction).disabled(viewModel.isBusy)
            }

            StatusLine(text: viewModel.status)
        }
    }
}
