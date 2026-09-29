# AcouTest Swift 重构方案

## 一、必须先知道的现实

| 项目 | 现状 |
|------|------|
| Python 核心代码 | `ui_components.py` **16,925 行** + `test_operations.py` **4,339 行** + 其它 |
| 功能子模块 | **20+** 个独立测试/调试功能 |
| 预估 Swift 重写工作量 | **3～6 人月**（熟悉 macOS + ADB + 音频的开发者） |
| 本机环境 | 当前仅 Command Line Tools，**需从 App Store 安装完整 Xcode** 才能编译 SwiftUI |
| Windows 客户端 | Swift 原生 **无法替代** 现有 Windows `.exe`；若全量迁移则 Windows 需继续维护 Python 版 |

**结论**：不可能「一次对话全部重写且功能一个不落」。正确做法是 **分阶段迁移**，Python 版继续服务用户，Swift 版逐模块替换。

---

## 二、推荐策略（比全量重写更划算）

1. **短期（现在）**：继续用 Python + `Packager.sh` + `macos_sign_notarize.sh` 公证分发 → 用户双击即用。
2. **中期**：新建 `AcouTestMac/`（本目录），先实现 **设备连接 + 2～3 个常用功能** 验证架构。
3. **长期**：按下方 Phase 表逐个迁移；每完成一模块在 `FeatureFlags` 标记为 `swiftNative`。

---

## 三、Swift 分层架构（对应 Python 三层）

```
┌─────────────────────────────────────────────────────────────┐
│  App/          AcouTestApp, 依赖注入, 生命周期               │
├─────────────────────────────────────────────────────────────┤
│  UI/           SwiftUI Views（按 Features 分子目录）          │
├─────────────────────────────────────────────────────────────┤
│  Features/     各功能 ViewModel + 用例（业务编排）            │
├─────────────────────────────────────────────────────────────┤
│  Services/     ADB、音频、HTTP(OpenClaw)、更新、语料 TTS     │
├─────────────────────────────────────────────────────────────┤
│  Core/         Config、Models、Paths、Extensions             │
└─────────────────────────────────────────────────────────────┘
         Features → Services → Core（单向依赖，禁止反向）
```

### Python → Swift 文件对照

| Python | Swift 目录 |
|--------|------------|
| `main.py` + `audio_test_tool.py` | `App/AcouTestApp.swift` |
| `feature_config.py` | `Core/Config/FeatureFlags.swift` |
| `output_paths.py` | `Core/Paths/OutputPaths.swift` |
| `devices_operations.py` | `Services/ADB/DeviceManager.swift` |
| `test_operations.py` | `Features/*/…ViewModel.swift` + `Services/*/` |
| `ui_components.py` | `UI/` + `Features/*/…View.swift` |
| `control_api.py` | `Services/HTTP/OpenClawServer.swift` |
| `updater_http.py` | `Services/Update/UpdateService.swift` |
| `generate_wake_word.py` | `Services/Corpus/CorpusGeneratorService.swift` |

---

## 四、文件夹结构

```
AcouTestMac/
├── App/
├── Core/
│   ├── Config/          FeatureFlags, AppVersion, ReleaseChannel
│   ├── Models/          Device, TestSession, WakeupCorpus…
│   └── Paths/           OutputPaths
├── Services/
│   ├── ADB/             ADBService, DeviceManager, ShellRunner
│   ├── Audio/           LocalPlayback, WaveformAnalysis
│   ├── HTTP/            OpenClawServer
│   ├── Update/          UpdateService
│   └── Corpus/          EdgeTTS / 语料生成
├── Features/
│   ├── HardwareTesting/     麦克风、雷达、喇叭、多声道
│   ├── AcousticTesting/     扫频、气密、震音
│   ├── AudioDebugging/      Loopback、HAL、Logcat、唤醒、语料、系统指令
│   ├── Utilities/           遥控器、截图、OpenClaw、账号
│   └── KeyBurning/          sn烧key（Mac）；u盘烧key 仅 Windows
├── UI/
│   ├── Main/            MainWindow, DeviceToolbar, TabRouter
│   └── Components/      共用控件
└── Docs/
    └── SWIFT_MIGRATION.md
```

---

## 五、功能迁移清单（一个都不能漏）

### 硬件测试
- [ ] 麦克风测试 — `MicTestViewModel` ← `start_mic_test`
- [ ] 雷达检查 — `RadarCheckViewModel`
- [ ] 喇叭测试 — `SpeakerTestViewModel`
- [ ] 多声道测试 — `MultichannelTestViewModel`

### 硬件测试
- [x] 麦克风测试 — `MicTestViewModel`（tinycap 录音 + pkill + pull）
- [x] 雷达检查 — `RadarCheckViewModel`（logcat 关键词监测/计数）
- [x] 喇叭测试 — `SpeakerTestViewModel`（push wav + 启动喇叭应用）
- [x] 多声道测试 — `MultichannelTestViewModel`（root + push + tinyplay）

### 声学测试
- [x] 扫频测试 — `SweepTestViewModel`（push + tinycap 录 + tinyplay 放 + 定时停止拉取）
- [ ] 气密性测试 — `AirtightnessTestViewModel`（**需波形/频谱 DSP 分析，暂占位**）
- [ ] 震音测试 — `JitterTestViewModel`（**需波形分析，暂占位**）

### 音频调试
- [x] Loopback和Ref — `LoopbackTestViewModel`（tinycap -p 480 + pull）
- [x] HAL录音 — `HALRecordingViewModel`（属性勾选 + setprop + 停止自动 pull）
- [x] Logcat — `LogcatViewModel`（后台进程流式写文件 + 实时预览）
- [x] 唤醒监测 — `WakeupMonitorViewModel`（logcat 关键词计数 + 去重）
- [ ] 语料生成 — `CorpusGeneratorViewModel`（**依赖 edge-tts 在线 TTS，暂占位**）
- [x] 系统指令 — `SystemCommandViewModel`（预设按钮 + 自定义 + 输出保存）

### 常用功能
- [x] 遥控器 — `RemoteControlViewModel`（方向/音量/电源键 + 快捷应用 + 自定义）
- [ ] 本地播放 — `LocalPlaybackViewModel`（原版默认关闭，暂占位）
- [x] 截图 — `ScreenshotViewModel`（exec-out screencap + 预览 + 打开目录）
- [ ] OpenClaw — `OpenClawViewModel`（**HTTP 控制服务，暂占位**）
- [x] 账号登录 — `AccountLoginViewModel`（input text 输入账号/密码）

### 烧大象 key
- [x] sn烧key — `SNKeyBurnViewModel`（ADB unifykeys：读 SN / 读写 elevockey）
- [ ] u盘烧key — **仅 Windows**（依赖 `soft_encryption.dll`，Mac 无法运行）

### 基础设施
- [x] 设备列表 / ADB 命令 — Phase 1 骨架
- [ ] 自动更新双通道
- [ ] 波形查看 / 频谱对比
- [ ] AudioPlayer.apk 联动

---

## 六、分阶段计划

| 阶段 | 内容 | 状态 |
|------|------|------|
| **Phase 1** | App 壳 + 设备栏 + FeatureFlags + ADB | ✅ 完成 |
| **Phase 2** | 截图、系统指令、Logcat、HAL（常用调试） | ✅ 完成 |
| **Phase 3** | 麦克风、喇叭、多声道、雷达、遥控器 | ✅ 完成 |
| **Phase 4** | 扫频、Loopback、唤醒监测、账号登录、sn烧key | ✅ 完成 |
| **Phase 5（剩余）** | 气密、震音（需波形 DSP）、语料（edge-tts）、OpenClaw（HTTP）、本地播放 | ⏳ 待做 |
| **平台限制** | u盘烧key 依赖 Windows DLL，Mac 无法实现 | ⛔ 不可行 |

### 界面布局
已改为贴近原版的 **顶部设备栏 + 大类横向标签 + 子标签 + 内容区**（`MainWindowView`），
不再使用左侧 NavigationSplitView 边栏。

### 运行要点
- 已在工程关闭 **App Sandbox**（`ENABLE_APP_SANDBOX = NO`），否则无法调用外部 `adb`、写入 `~/AcouTest/output`。
- `adb` 自动探测 `/opt/homebrew/bin`、`/usr/local/bin`、`~/Library/Android/sdk/platform-tools`，找不到时回退 PATH。
- 测试输出目录：`~/AcouTest/output/<子目录>`。

---

## 七、在 Xcode 中打开（首次）

1. App Store 安装 **Xcode**（非仅 Command Line Tools）
2. Xcode → File → New → Project → **macOS → App**
3. Product Name: `AcouTestMac`，Interface: **SwiftUI**，Language: **Swift**
4. 保存到本仓库，将 `AcouTestMac/` 下除 `Docs/` 外文件夹 **拖入工程**
5. Signing：Team 选 **Digital Beat PTE. LTD.**
6. 运行 ▶︎

---

## 八、为何不建议现在删掉 Python 版

- 已有 Windows 客户与完整功能
- 公证流程已就绪（`macos_sign_notarize.sh`）
- Swift 版未完工前无交付能力
- 唤醒监测等逻辑高度耦合 Python UI，迁移风险大

**Python 与 Swift 可长期并存**，共用 `audio/`、`wakeup_count/`、`output/` 资源目录。
