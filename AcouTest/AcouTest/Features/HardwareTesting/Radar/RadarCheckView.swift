import SwiftUI

struct RadarCheckView: View {
    @StateObject private var viewModel: RadarCheckViewModel
    @State private var method = 0

    init(deviceManager: DeviceManager) {
        _viewModel = StateObject(wrappedValue: RadarCheckViewModel(deviceManager: deviceManager))
    }

    var body: some View {
        FeatureContainer(title: "雷达检查") {
            Picker("", selection: $method) {
                Text("TTY 设备检查").tag(0)
                Text("Logcat 监控").tag(1)
                Text("AIEQ 操作指南").tag(2)
            }
            .pickerStyle(.segmented)
            .labelsHidden()

            switch method {
            case 0: ttySection
            case 1: logcatSection
            default: aieqSection
            }

            StatusLine(text: viewModel.status)
        }
    }

    // MARK: TTY
    private var ttySection: some View {
        VStack(spacing: 16) {
            Card {
                Text("检查设备中是否存在 ttyACM 设备，存在则表明有雷达节点（是否正常工作还需进一步检查）。")
                    .font(.callout).foregroundStyle(.secondary)
            }
            ActionBar {
                Button { viewModel.checkTTY() } label: { Label("检查 TTY 设备", systemImage: "cable.connector") }
                    .buttonStyle(.primaryAction).disabled(viewModel.isCheckingTTY)
            }
            Card(title: "检查结果") {
                MonospacedOutput(text: viewModel.ttyResult).frame(minHeight: 240)
            }
        }
    }

    // MARK: Logcat
    private var logcatSection: some View {
        VStack(spacing: 16) {
            Card(title: "测试步骤") {
                Text("1. 点「开始监控」启动日志监控\n2. 用手或物体靠近/远离雷达传感器区域\n3. 观察下方日志，如关键词相关值有变化则表明雷达正常\n4. 完成后点「停止监控」")
                    .font(.callout).foregroundStyle(.secondary)
                LabeledRow(label: "关键词") {
                    TextField("如 updateGain", text: $viewModel.keyword)
                        .textFieldStyle(.roundedBorder).frame(maxWidth: 220).disabled(viewModel.isMonitoring)
                    Text("命中：\(viewModel.hitCount)").bold().foregroundStyle(Color.accentColor)
                }
            }
            ActionBar {
                Button { viewModel.toggleMonitor() } label: {
                    Label(viewModel.isMonitoring ? "停止监控" : "开始监控",
                          systemImage: viewModel.isMonitoring ? "stop.circle" : "dot.radiowaves.left.and.right")
                }
                .buttonStyle(viewModel.isMonitoring ? AnyButtonStyle(.secondaryAction) : AnyButtonStyle(.primaryAction))
            }
            Card(title: "监控结果") {
                MonospacedOutput(text: viewModel.monitorLines.joined(separator: "\n")).frame(minHeight: 240)
            }
        }
    }

    // MARK: AIEQ 指南
    private var aieqSection: some View {
        Card(title: "AIEQ 操作指南") {
            Text("""
            通过 AIEQ 界面的 Sweet Spot 功能测试雷达传感器：

            1. 在设备上长按遥控器的静音键，打开 AIEQ 界面
            2. 在 AIEQ 界面中找到并点击 "Sweet Spot" 按钮
            3. Sweet Spot 会根据雷达传感器检测用户位置并调整音效
            4. 测试方法：
               • 在 Sweet Spot 模式下播放音乐
               • 移动位置或用手遮挡雷达传感器区域
               • 观察声音效果是否有变化
               • 如有变化，则表明雷达传感器工作正常

            注意：此方法需要设备支持 AIEQ 功能和 Sweet Spot 特性。
            """)
            .font(.callout)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }
}

/// 用于在两种 ButtonStyle 间切换
struct AnyButtonStyle: ButtonStyle {
    private let makeBodyClosure: (Configuration) -> AnyView
    init<S: ButtonStyle>(_ style: S) {
        makeBodyClosure = { config in AnyView(style.makeBody(configuration: config)) }
    }
    func makeBody(configuration: Configuration) -> some View {
        makeBodyClosure(configuration)
    }
}
