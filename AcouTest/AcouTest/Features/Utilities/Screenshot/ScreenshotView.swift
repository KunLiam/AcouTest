import SwiftUI

struct ScreenshotView: View {
    @StateObject private var viewModel: ScreenshotViewModel

    init(deviceManager: DeviceManager) {
        _viewModel = StateObject(wrappedValue: ScreenshotViewModel(deviceManager: deviceManager))
    }

    var body: some View {
        FeatureContainer(title: "截图功能") {
            Card(title: "截图设置") {
                LabeledRow(label: "保存路径") {
                    TextField("保存路径", text: $viewModel.savePath)
                        .textFieldStyle(.roundedBorder)
                    Button("浏览…") { viewModel.chooseFolder() }.buttonStyle(.secondaryAction)
                }
            }

            ActionBar {
                Button { Task { await viewModel.takeScreenshot() } } label: {
                    Label("截图", systemImage: "camera")
                }
                .buttonStyle(.primaryAction).disabled(viewModel.isBusy)
                Button { viewModel.openFolder() } label: { Label("打开目录", systemImage: "folder") }
                    .buttonStyle(.secondaryAction)
            }

            StatusLine(text: viewModel.status)
            previewArea
        }
    }

    @ViewBuilder
    private var previewArea: some View {
        if let path = viewModel.lastImagePath, let image = NSImage(contentsOfFile: path) {
            Card(title: "最近一次截图预览") {
                Image(nsImage: image)
                    .resizable()
                    .scaledToFit()
                    .frame(maxWidth: .infinity)
                    .frame(maxHeight: 360)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                    .overlay(RoundedRectangle(cornerRadius: 8).stroke(UITheme.hairline))
            }
        }
    }
}
