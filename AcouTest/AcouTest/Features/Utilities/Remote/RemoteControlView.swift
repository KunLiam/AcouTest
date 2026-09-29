import SwiftUI

struct RemoteControlView: View {
    @StateObject private var viewModel: RemoteControlViewModel

    init(deviceManager: DeviceManager) {
        _viewModel = StateObject(wrappedValue: RemoteControlViewModel(deviceManager: deviceManager))
    }

    var body: some View {
        FeatureContainer(title: "遥控器") {
            HStack(alignment: .top, spacing: 16) {
                Card(title: "方向 / 导航") { dpadSection }
                Card(title: "音量 / 电源") { volumeSection }
            }
            Card(title: "快捷应用") { quickAppsSection }
            Card(title: "自定义快捷") { customSection }
            StatusLine(text: viewModel.status)
        }
    }

    private func keyButton(_ title: String, _ keycode: String, width: CGFloat = 60) -> some View {
        Button(title) { viewModel.sendKey(keycode) }
            .buttonStyle(.secondaryAction)
            .frame(width: width)
    }

    private var dpadSection: some View {
        VStack(spacing: 10) {
            keyButton("↑", "DPAD_UP")
            HStack(spacing: 10) {
                keyButton("←", "DPAD_LEFT")
                Button("OK") { viewModel.sendKey("DPAD_CENTER") }
                    .buttonStyle(.primaryAction).frame(width: 60)
                keyButton("→", "DPAD_RIGHT")
            }
            keyButton("↓", "DPAD_DOWN")
            HStack(spacing: 10) {
                keyButton("返回", "BACK", width: 76)
                keyButton("主页", "HOME", width: 76)
                keyButton("菜单", "MENU", width: 76)
            }
        }
        .frame(maxWidth: .infinity)
    }

    private var volumeSection: some View {
        VStack(spacing: 10) {
            keyButton("音量 +", "VOLUME_UP", width: 100)
            keyButton("音量 -", "VOLUME_DOWN", width: 100)
            keyButton("静音", "VOLUME_MUTE", width: 100)
            keyButton("电源", "POWER", width: 100)
            Button("适配遥控器") { viewModel.adaptRemote() }
                .buttonStyle(.primaryAction)
        }
        .frame(maxWidth: .infinity)
    }

    private var quickAppsSection: some View {
        LazyVGrid(columns: [GridItem(.adaptive(minimum: 130), spacing: 10)], alignment: .leading, spacing: 10) {
            ForEach(viewModel.builtinApps) { app in
                Button(app.label) { viewModel.launch(app) }
                    .buttonStyle(.secondaryAction)
                    .frame(maxWidth: .infinity)
            }
        }
    }

    private var customSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                TextField("名称", text: $viewModel.customName)
                    .textFieldStyle(.roundedBorder).frame(maxWidth: 140)
                TextField("如 am start -n 包名/.Activity", text: $viewModel.customCmd)
                    .textFieldStyle(.roundedBorder)
                Button("添加") { viewModel.addCustom() }.buttonStyle(.secondaryAction)
            }
            ForEach(Array(viewModel.customApps.enumerated()), id: \.offset) { index, item in
                HStack {
                    Text(item.name).bold()
                    Text(item.cmd).font(.system(size: 11, design: .monospaced)).foregroundStyle(.secondary)
                    Spacer()
                    Button { viewModel.launchCustom(item.cmd) } label: { Image(systemName: "play.fill") }
                        .buttonStyle(.borderless)
                    Button { viewModel.deleteCustom(at: index) } label: { Image(systemName: "trash") }
                        .buttonStyle(.borderless)
                }
            }
        }
    }
}
