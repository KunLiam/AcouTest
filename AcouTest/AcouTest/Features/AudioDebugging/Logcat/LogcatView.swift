import SwiftUI

struct LogcatView: View {
    @StateObject private var viewModel: LogcatViewModel

    init(deviceManager: DeviceManager) {
        _viewModel = StateObject(wrappedValue: LogcatViewModel(deviceManager: deviceManager))
    }

    var body: some View {
        FeatureContainer(title: "Logcat 日志") {
            propsCard
            captureCard

            ActionBar {
                Button { viewModel.startCapture() } label: { Label("开始抓取", systemImage: "record.circle") }
                    .buttonStyle(.primaryAction).disabled(viewModel.isCapturing)
                Button { viewModel.stopCapture() } label: { Label("停止抓取", systemImage: "stop.circle") }
                    .buttonStyle(.secondaryAction).disabled(!viewModel.isCapturing)
                Button { viewModel.openFolder() } label: { Label("打开目录", systemImage: "folder") }
                    .buttonStyle(.secondaryAction)
            }

            StatusLine(text: viewModel.status)

            Card(title: "实时预览（仅末尾片段）") {
                MonospacedOutput(text: viewModel.tailPreview).frame(minHeight: 280)
            }
        }
    }

    // MARK: 属性管理
    private var propsCard: some View {
        Card(title: "logcat 属性管理") {
            Text("勾选要开启的调试属性，点「放开日志打印」会 adb root 后 setprop 写入；「停止」则恢复默认值。")
                .font(.caption).foregroundStyle(.secondary)

            HStack {
                TextField("添加属性，如 vendor.media.audiohal.debug 4096", text: $viewModel.newPropText)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { viewModel.addProp() }
                Button("添加") { viewModel.addProp() }.buttonStyle(.secondaryAction)
            }
            HStack {
                Button("全选") { viewModel.toggleAllProps(true) }.buttonStyle(.borderless)
                Button("取消全选") { viewModel.toggleAllProps(false) }.buttonStyle(.borderless)
                Spacer()
            }

            VStack(alignment: .leading, spacing: 4) {
                ForEach($viewModel.props) { $prop in
                    HStack {
                        Toggle(isOn: $prop.enabled) {
                            Text("\(prop.name) = \(prop.debugValue)")
                                .font(.system(size: 11.5, design: .monospaced))
                        }
                        .disabled(viewModel.isApplyingProps)
                        Spacer()
                        Button { viewModel.deleteProp(prop) } label: { Image(systemName: "trash") }
                            .buttonStyle(.borderless)
                    }
                }
            }
            .padding(10)
            .background(Color.gray.opacity(0.06))
            .clipShape(RoundedRectangle(cornerRadius: 8))

            HStack(spacing: 12) {
                Button { viewModel.enableDebug() } label: { Label("放开日志打印", systemImage: "lock.open") }
                    .buttonStyle(.primaryAction).disabled(viewModel.isApplyingProps)
                Button { viewModel.disableDebug() } label: { Label("停止日志打印", systemImage: "lock") }
                    .buttonStyle(.secondaryAction).disabled(viewModel.isApplyingProps)
            }
        }
    }

    // MARK: 抓取设置
    private var captureCard: some View {
        Card(title: "日志抓取") {
            LabeledRow(label: "过滤规则") {
                TextField("如 *:V 或 AudioHAL:D *:S", text: $viewModel.filterSpec)
                    .textFieldStyle(.roundedBorder).disabled(viewModel.isCapturing)
            }
            LabeledRow(label: "保存路径") {
                TextField("保存路径", text: $viewModel.savePath)
                    .textFieldStyle(.roundedBorder).disabled(viewModel.isCapturing)
                Button("浏览…") { viewModel.chooseFolder() }.buttonStyle(.secondaryAction).disabled(viewModel.isCapturing)
            }
        }
    }
}
