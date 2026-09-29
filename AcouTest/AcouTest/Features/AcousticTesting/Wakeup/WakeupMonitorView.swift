import SwiftUI

struct WakeupMonitorView: View {
    @StateObject private var viewModel: WakeupMonitorViewModel

    init(deviceManager: DeviceManager) {
        _viewModel = StateObject(wrappedValue: WakeupMonitorViewModel(deviceManager: deviceManager))
    }

    var body: some View {
        FeatureContainer(title: "唤醒监测") {
            Card(title: "唤醒次数") {
                HStack(spacing: 24) {
                    VStack(spacing: 2) {
                        Text("\(viewModel.wakeupCount)")
                            .font(.system(size: 40, weight: .bold))
                            .foregroundStyle(Color.accentColor)
                        Text("累计唤醒次数").font(.caption).foregroundStyle(.secondary)
                    }
                    VStack(spacing: 10) {
                        Button { viewModel.toggle() } label: {
                            Label(viewModel.isMonitoring ? "停止监测" : "开始监测",
                                  systemImage: viewModel.isMonitoring ? "stop.circle" : "waveform.badge.mic")
                        }
                        .buttonStyle(viewModel.isMonitoring ? AnyButtonStyle(.secondaryAction) : AnyButtonStyle(.primaryAction))
                        Button("重置") { viewModel.reset() }.buttonStyle(.secondaryAction)
                    }
                    Spacer()
                }
            }

            Card(title: "语料库与匹配规则") {
                LabeledRow(label: "唤醒语料库") {
                    Picker("", selection: $viewModel.corpus) {
                        ForEach(WakeupMonitorViewModel.Corpus.allCases) { Text($0.rawValue).tag($0) }
                    }.labelsHidden().frame(width: 160).disabled(viewModel.isMonitoring)
                }
                VStack(alignment: .leading, spacing: 3) {
                    Text("匹配规则（logcat 关键字）").font(.caption).foregroundStyle(.secondary)
                    ForEach(viewModel.currentKeywords, id: \.self) { kw in
                        Text("• \(kw)").font(.system(size: 11, design: .monospaced)).foregroundStyle(.secondary)
                    }
                }
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.gray.opacity(0.06))
                .clipShape(RoundedRectangle(cornerRadius: 8))
            }

            Card(title: "唤醒后操作") {
                LabeledRow(label: "唤醒后") {
                    Picker("", selection: $viewModel.afterAction) {
                        ForEach(WakeupMonitorViewModel.AfterAction.allCases) { Text($0.rawValue).tag($0) }
                    }.labelsHidden().frame(width: 160)
                }
                LabeledField("延迟(秒)", text: $viewModel.afterDelay)
            }

            StatusLine(text: viewModel.status)

            Card(title: "最近唤醒记录") {
                MonospacedOutput(text: viewModel.recentHits.joined(separator: "\n")).frame(minHeight: 200)
            }
        }
    }
}
