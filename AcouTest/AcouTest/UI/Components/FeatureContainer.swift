import SwiftUI

// MARK: - 设计常量

enum UITheme {
    static let cardCorner: CGFloat = 10
    static let contentMaxWidth: CGFloat = 760
    static let cardBackground = Color(nsColor: .controlBackgroundColor)
    static let pageBackground = Color(nsColor: .windowBackgroundColor)
    static let hairline = Color.gray.opacity(0.22)
}

// MARK: - 功能页容器

/// 统一的功能页容器：居中标题 + 居中内容（限制最大宽度，带柔和背景与滚动）
struct FeatureContainer<Content: View>: View {
    let title: String
    @ViewBuilder var content: Content

    var body: some View {
        ScrollView {
            VStack(spacing: 18) {
                Text(title)
                    .font(.title2.weight(.semibold))
                    .frame(maxWidth: .infinity, alignment: .center)
                    .padding(.top, 18)

                content
                    .frame(maxWidth: UITheme.contentMaxWidth)
            }
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 24)
            .padding(.bottom, 28)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(UITheme.pageBackground)
    }
}

// MARK: - 卡片分组框

/// 带边框/标题的分组卡片（对应原版 LabelFrame「测试设置」）
struct Card<Content: View>: View {
    var title: String? = nil
    @ViewBuilder var content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let title {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(.primary)
            }
            content
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: UITheme.cardCorner)
                .fill(UITheme.cardBackground)
        )
        .overlay(
            RoundedRectangle(cornerRadius: UITheme.cardCorner)
                .stroke(UITheme.hairline, lineWidth: 1)
        )
        .shadow(color: .black.opacity(0.04), radius: 3, y: 1)
    }
}

// MARK: - 操作按钮区

/// 居中排列的按钮行（对应原版底部按钮区）
struct ActionBar<Content: View>: View {
    @ViewBuilder var content: Content
    var body: some View {
        HStack(spacing: 14) {
            content
        }
        .frame(maxWidth: .infinity, alignment: .center)
        .padding(.vertical, 4)
    }
}

// MARK: - 状态面板

/// 居中状态区（对应原版「状态 / 准备就绪」）
struct StatusLine: View {
    let text: String
    var body: some View {
        VStack(spacing: 4) {
            Text("状态")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(text)
                .font(.system(size: 13))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .textSelection(.enabled)
        }
        .frame(maxWidth: .infinity, alignment: .center)
        .padding(.top, 4)
    }
}

// MARK: - 输入行

/// 通用「标签 + 输入框」行（标签右对齐，输入框统一宽度）
struct LabeledField: View {
    let label: String
    @Binding var text: String
    var disabled: Bool = false
    var placeholder: String? = nil

    init(_ label: String, text: Binding<String>, disabled: Bool = false, placeholder: String? = nil) {
        self.label = label
        self._text = text
        self.disabled = disabled
        self.placeholder = placeholder
    }

    var body: some View {
        HStack(spacing: 12) {
            Text(label)
                .frame(width: 130, alignment: .trailing)
                .foregroundStyle(.secondary)
            TextField(placeholder ?? label, text: $text)
                .textFieldStyle(.roundedBorder)
                .frame(maxWidth: 300)
                .disabled(disabled)
            Spacer(minLength: 0)
        }
    }
}

/// 「标签 + 任意控件」行
struct LabeledRow<Content: View>: View {
    let label: String
    @ViewBuilder var content: Content
    var body: some View {
        HStack(spacing: 12) {
            Text(label)
                .frame(width: 130, alignment: .trailing)
                .foregroundStyle(.secondary)
            content
            Spacer(minLength: 0)
        }
    }
}

// MARK: - 等宽日志/输出

struct MonospacedOutput: View {
    let text: String
    var body: some View {
        ScrollView {
            Text(text.isEmpty ? "（暂无输出）" : text)
                .font(.system(size: 11.5, design: .monospaced))
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(10)
        }
        .background(Color(nsColor: .textBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).stroke(UITheme.hairline))
    }
}

// MARK: - 按钮样式

/// 主操作按钮：醒目、统一尺寸
struct PrimaryActionButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .medium))
            .padding(.horizontal, 18)
            .padding(.vertical, 8)
            .frame(minWidth: 120)
            .background(Color.accentColor.opacity(configuration.isPressed ? 0.8 : 1))
            .foregroundStyle(.white)
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .opacity(configuration.isPressed ? 0.9 : 1)
    }
}

/// 次操作按钮：描边
struct SecondaryActionButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13))
            .padding(.horizontal, 18)
            .padding(.vertical, 8)
            .frame(minWidth: 120)
            .background(
                RoundedRectangle(cornerRadius: 8).fill(Color.gray.opacity(0.10))
            )
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(UITheme.hairline))
            .foregroundStyle(.primary)
            .opacity(configuration.isPressed ? 0.7 : 1)
    }
}

extension ButtonStyle where Self == PrimaryActionButtonStyle {
    static var primaryAction: PrimaryActionButtonStyle { .init() }
}
extension ButtonStyle where Self == SecondaryActionButtonStyle {
    static var secondaryAction: SecondaryActionButtonStyle { .init() }
}
