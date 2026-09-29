import SwiftUI

struct DeviceToolbarView: View {
    @ObservedObject var deviceManager: DeviceManager
    @State private var showNetworkSheet = false
    @State private var showAboutSheet = false

    var body: some View {
        HStack(spacing: 12) {
            Image("AppLogo")
                .resizable()
                .frame(width: 22, height: 22)
            Text("\(AppVersion.displayName) v\(AppVersion.current)")
                .font(.system(size: 13, weight: .semibold))
            Divider().frame(height: 18)
            Text("设备")
            Picker("", selection: $deviceManager.selectedDeviceID) {
                if deviceManager.devices.isEmpty {
                    Text("无设备").tag("")
                }
                ForEach(deviceManager.devices) { device in
                    Text(deviceLabel(device)).tag(device.id)
                }
            }
            .labelsHidden()
            .frame(minWidth: 220)

            Button {
                Task { await deviceManager.refresh() }
            } label: {
                if deviceManager.isRefreshing {
                    ProgressView().controlSize(.small)
                } else {
                    Text("刷新")
                }
            }
            .disabled(deviceManager.isRefreshing)

            Button("网络连接") { showNetworkSheet = true }

            HStack(spacing: 6) {
                Circle()
                    .fill(statusColor)
                    .frame(width: 9, height: 9)
                Text(deviceManager.statusMessage)
                    .lineLimit(1)
                    .foregroundStyle(.secondary)
            }
            Spacer()

            Button {
                showAboutSheet = true
            } label: {
                Image(systemName: "questionmark.circle")
            }
            .buttonStyle(.borderless)
            .help("查看软件信息")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .sheet(isPresented: $showNetworkSheet) {
            NetworkConnectSheet(deviceManager: deviceManager)
        }
        .sheet(isPresented: $showAboutSheet) {
            AboutSheet()
        }
    }

    private func deviceLabel(_ device: ADBDevice) -> String {
        device.isOnline ? device.id : "\(device.id)（离线）"
    }

    private var statusColor: Color {
        if deviceManager.selectedOnlineDevice != nil { return .green }
        if !deviceManager.devices.isEmpty { return .orange }
        return .red
    }
}

/// 网络 ADB 连接弹窗
struct NetworkConnectSheet: View {
    @ObservedObject var deviceManager: DeviceManager
    @Environment(\.dismiss) private var dismiss
    @State private var address = ""
    @State private var status = ""
    @State private var isConnecting = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("网络 ADB 连接").font(.title3.bold())
            Text("请输入设备 IP 地址和端口，例如：192.168.10.41:5555")
                .font(.callout).foregroundStyle(.secondary)
            TextField("192.168.x.x:5555", text: $address)
                .textFieldStyle(.roundedBorder)
                .onSubmit { connect() }
            if !status.isEmpty {
                Text(status).font(.callout).foregroundStyle(.blue)
            }
            HStack {
                Spacer()
                Button("取消") { dismiss() }.buttonStyle(.secondaryAction)
                Button { connect() } label: {
                    if isConnecting { ProgressView().controlSize(.small) } else { Text("连接") }
                }
                .buttonStyle(.primaryAction).disabled(isConnecting)
            }
        }
        .padding(22)
        .frame(width: 440)
    }

    private func connect() {
        guard !isConnecting else { return }
        isConnecting = true
        status = "正在连接…"
        Task {
            let result = await deviceManager.connectNetwork(address: address)
            status = result
            isConnecting = false
            if result.hasPrefix("已连接") {
                try? await Task.sleep(nanoseconds: 1_200_000_000)
                dismiss()
            }
        }
    }
}

/// 软件信息弹窗
struct AboutSheet: View {
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                Image("AppLogo").resizable().frame(width: 44, height: 44)
                Text("软件信息").font(.title3.bold())
            }
            Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 6) {
                GridRow {
                    Text("版本号").foregroundStyle(.secondary)
                    Text("v\(AppVersion.current)").foregroundStyle(.blue)
                }
                GridRow {
                    Text("作者").foregroundStyle(.secondary)
                    Text("liangk").foregroundStyle(.blue)
                }
                GridRow {
                    Text("邮箱").foregroundStyle(.secondary)
                    Link("807946809@qq.com", destination: URL(string: "mailto:807946809@qq.com")!)
                }
            }
            Divider()
            Text("功能说明").font(.headline)
            ScrollView {
                Text(featureDescription)
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(height: 240)
            HStack {
                Spacer()
                Button("关闭") { dismiss() }.buttonStyle(.primaryAction)
            }
        }
        .padding(22)
        .frame(width: 500)
    }

    private var featureDescription: String {
        """
        声测大师(AcouTest) 面向 Android 设备的音频测试与远程控制，支持 ADB，便于设备管理与调试。

        【硬件测试】
        • 麦克风测试：多麦录音与参数配置
        • 雷达检查：TTY / Logcat / AIEQ 三种检查方法
        • 喇叭测试：默认/自定义音频播放验证
        • 多声道测试：7.1/2.1/2.0 音频播放验证

        【声学测试】
        • 扫频测试：扫频文件播放录制
        • 气密性测试 / 震音测试（迁移中）

        【音频调试】
        • Loopback 和 Ref 测试：回路与参考通道测试
        • HAL 录音：HAL 录音与拉取
        • Logcat 日志：属性管理 + 日志抓取
        • 唤醒监测：唤醒关键词监测与计数
        • 系统指令：常用 dumpsys/tinymix 及自定义 shell 指令

        【常用功能】
        • 遥控器：常用遥控器按键模拟
        • 截图功能：设备截图
        • 账号登录：账号密码输入辅助

        【烧大象 key】
        • sn烧key：ADB unifykeys 读写
        """
    }
}
