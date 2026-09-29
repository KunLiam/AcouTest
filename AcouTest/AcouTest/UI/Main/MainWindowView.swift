import SwiftUI

/// 主窗口：顶部设备栏 + 大类标签 + 子标签（贴近原 Python 版 Notebook 布局）
struct MainWindowView: View {
    @EnvironmentObject private var deviceManager: DeviceManager

    @State private var selectedMainID: String = FeatureFlags.enabledMainTabs.first?.id ?? ""
    @State private var selectedSubID: String = ""

    private var currentMain: FeatureFlags.MainTab? {
        FeatureFlags.enabledMainTabs.first { $0.id == selectedMainID }
    }

    private var currentSubTabs: [FeatureFlags.SubTab] {
        currentMain?.subTabs.filter(\.enabled) ?? []
    }

    private var currentSub: FeatureFlags.SubTab? {
        currentSubTabs.first { $0.id == selectedSubID } ?? currentSubTabs.first
    }

    var body: some View {
        VStack(spacing: 0) {
            DeviceToolbarView(deviceManager: deviceManager)
            Divider()
            mainTabBar
                .background(Color(nsColor: .controlBackgroundColor))
            Divider()
            subTabBar
                .background(Color(nsColor: .controlBackgroundColor).opacity(0.6))
            Divider()
            contentArea
            Divider()
            bottomStatusBar
        }
        .task {
            await deviceManager.refresh()
            syncSubSelection()
        }
        .onChange(of: selectedMainID) { _, _ in
            syncSubSelection()
        }
    }

    // MARK: 底部状态栏
    private var bottomStatusBar: some View {
        HStack(spacing: 8) {
            Image(systemName: deviceManager.selectedOnlineDevice != nil ? "checkmark.circle.fill" : "exclamationmark.circle")
                .foregroundStyle(deviceManager.selectedOnlineDevice != nil ? .green : .secondary)
                .font(.system(size: 11))
            Text(deviceManager.statusMessage)
                .lineLimit(1)
            Spacer()
            Text("\(AppVersion.displayName) v\(AppVersion.current)")
        }
        .font(.system(size: 11))
        .foregroundStyle(.secondary)
        .padding(.horizontal, 14)
        .padding(.vertical, 6)
        .background(Color(nsColor: .windowBackgroundColor))
    }

    // MARK: 大类标签（顶部横向）
    private var mainTabBar: some View {
        HStack(spacing: 4) {
            ForEach(FeatureFlags.enabledMainTabs) { tab in
                Button {
                    selectedMainID = tab.id
                } label: {
                    Text(tab.title)
                        .font(.system(size: 14, weight: selectedMainID == tab.id ? .semibold : .regular))
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(
                            selectedMainID == tab.id
                                ? Color.accentColor.opacity(0.18)
                                : Color.clear
                        )
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                .buttonStyle(.plain)
                .foregroundStyle(selectedMainID == tab.id ? Color.accentColor : .primary)
            }
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
    }

    // MARK: 子标签（次级横向）
    private var subTabBar: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(currentSubTabs) { sub in
                    Button {
                        selectedSubID = sub.id
                    } label: {
                        Text(sub.title)
                            .font(.system(size: 12))
                            .padding(.horizontal, 12)
                            .padding(.vertical, 5)
                            .background(
                                (currentSub?.id == sub.id)
                                    ? Color.accentColor.opacity(0.9)
                                    : Color.gray.opacity(0.12)
                            )
                            .foregroundStyle((currentSub?.id == sub.id) ? Color.white : .primary)
                            .clipShape(Capsule())
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
        }
    }

    // MARK: 内容区
    @ViewBuilder
    private var contentArea: some View {
        if let sub = currentSub {
            FeatureRouter.view(for: sub.id, title: sub.title)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            Text("请选择功能")
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private func syncSubSelection() {
        if !currentSubTabs.contains(where: { $0.id == selectedSubID }) {
            selectedSubID = currentSubTabs.first?.id ?? ""
        }
    }
}
