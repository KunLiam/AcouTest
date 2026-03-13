# 声测大师(AcouTest)

## 项目概述

声测大师(AcouTest)是一个专为音频系统测试设计的综合工具，支持多种音频测试功能，包括麦克风测试、多声道测试、扫频测试、HAL录音、日志监控、系统指令、遥控器与快捷应用、烧大象key等。该工具可帮助音频工程师和质量测试人员进行音频设备的测试、调试和问题排查。

**主界面结构**：顶部为设备选择与刷新；主区域为多标签页——**声学测试**（扫频等）、**硬件测试**（麦克风、雷达等）、**音频调试**（Loopback和Ref、HAL录音、Logcat日志、系统指令）、**常用功能**（本地播放、截图、遥控器）、**烧大象key**（u盘烧key、sn烧key）。

## 主要功能

### 硬件测试
- **麦克风测试**
  - 功能用途：检查麦克风录音链路是否正常，验证参数设置是否符合预期。
  - 可配置项：麦克风数量、PCM 设备号、设备 ID、采样率、保存路径。
  - 结果输出：生成录音文件；录制完成后可直接查看最近一次录音波形。
- **雷达检查**
  - 功能用途：监控雷达相关日志，辅助判断雷达传感器是否有响应。
  - 可配置项：监测关键词、监测开关、相关日志输出控制。
  - 结果输出：实时显示关键值变化和状态提示。
- **喇叭测试**
  - 功能用途：验证设备喇叭播放能力与基础音频输出链路。
  - 可配置项：默认测试音频（`audio/speaker/speaker_default.wav`）或自定义音频。
  - 结果输出：通过听感快速确认喇叭是否正常发声。
- **多声道测试**
  - 功能用途：验证多声道音频输出（如 7.1 / 2.1 / 2.0）是否正确。
  - 可配置项：声道预设、采样率、位深、播放设备 ID。
  - 结果输出：辅助判断各声道路由与播放结果是否正确。

### 声学测试
- **气密性测试**
  - 功能用途：对比堵mic与不堵mic两种状态，评估声学密封效果。
  - 测试流程：开始后先选择“堵mic/不堵mic”，按提示完成双阶段测试；文件自动区分命名保存。
  - 可配置项：录制时长、播放文件（可选，默认推荐 `sweep_speech_48k.wav`）、保存路径。
  - 对比分析：支持按通道频谱对比、按选段分析、平均 dB 对比；支持从波形窗口框选后自动回填选段。
  - 手动导入：支持手动指定堵mic与不堵mic录音文件，直接进行对比分析（无需先跑测试流程）。
- **震音测试**
  - 功能用途：执行震音播放测试并记录听感结果，便于人工评估异常。
  - 可配置项：播放控制与结果记录项。
  - 结果输出：保留测试结果，便于后续复核。
- **扫频测试**
  - 功能用途：执行扫频播放与录制，用于频响相关分析和回归测试。
  - 可配置项：扫频文件来源（大象/自定义）、录制设备参数、播放设备参数、录制时长、批量间隔、保存路径。
  - 结果输出：自动保存录音文件，并支持直接查看波形。

### 音频调试
- **Loopback和Ref测试**
  - 功能用途：进行回路与参考通道测试，排查音频链路问题。
  - 可配置项：录制设备、通道数、采样率、音频来源、保存路径。
  - 结果输出：录音文件自动保存，支持波形查看。
- **HAL录音**
  - 功能用途：进行 HAL 层录音与文件拉取，用于底层问题定位。
  - 可配置项：录音属性、录音目录、保存路径、自动停止策略。
  - 结果输出：按配置保存 HAL 录音数据与拉取结果。
- **Logcat日志**
  - 功能用途：抓取设备日志用于音频问题排查（支持开机等待抓取）。
  - 可配置项：日志过滤规则、保存路径、自动停止时间、属性开关。
  - 结果输出：日志文件落盘；支持日志查看器实时筛选查看。
- **唤醒监测**
  - 功能用途：监测唤醒关键词相关日志并统计命中次数；支持「100 条唤醒率测试」本地按序播放 100 条唤醒语并统计唤醒率。
  - 可配置项：关键词、监测时机、日志范围；唤醒后关闭方式（不关闭/force-stop 助手/返回键/Home 键）、关闭延迟。
  - 100 条测试：使用内置播放逻辑，只需在 exe 同目录或上一级目录放置 **wakeup_count** 文件夹，内含 **art_100.txt**（播放顺序列表）与 **selected_100** 文件夹（对应 wav 文件），无需提供任何 .py 脚本。
  - 结果输出：实时显示命中状态与计数；100 条测试时显示预期条数、当前唤醒次数与唤醒率。
- **系统指令**
  - 功能用途：执行常用系统指令（如 `dumpsys`、`tinymix`、`getprop`）与自定义命令。
  - 可配置项：预设指令、自定义 shell 指令。
  - 结果输出：弹窗显示执行结果，支持搜索、刷新、保存。

### 常用功能
- **遥控器**
  - 功能用途：进行遥控器配对、按键模拟、常用应用快速启动。
  - 可配置项：按键动作、快捷应用、自定义快捷方式。
  - 结果输出：设备端即时响应遥控操作。
- **截图功能**
  - 功能用途：抓取设备当前屏幕，便于留档和问题反馈。
  - 可配置项：截图保存路径。
  - 结果输出：按时间戳自动命名并保存图片。
- **OpenClaw**
  - 功能用途：通过本地 HTTP 接口让外部自动化系统控制工具执行操作。
  - 可配置项：接口地址、鉴权 token、动作参数。
  - 结果输出：显示连接状态、请求日志与触发的 ADB 操作日志。
- **账号登录**
  - 功能用途：提供账号密码输入辅助，降低重复输入成本。
  - 可配置项：账号信息维护与选择。
  - 结果输出：快速填充登录信息。

### 烧大象key
- **u盘烧key**
  - 功能用途：通过 U 盘授权流程执行 key 写入。
  - 可配置项：设备信息读取、烧录动作、覆盖确认、剩余数量检查。
  - 结果输出：写入结果与关键日志记录。
- **sn烧key**
  - 功能用途：通过 SN 流程读取并写入/替换 key。
  - 可配置项：SN 读取、写入策略、覆盖确认。
  - 结果输出：写入结果反馈与可追溯日志。

## 最近更新（V1.6）

- **OpenClaw HTTP 控制接口**
  - 新增本地 HTTP 接口服务，默认监听 `127.0.0.1:8765`，可供 OpenClaw 直接调用控制声测大师执行动作。
  - 默认鉴权 token：`acoutest-local-token`（可通过环境变量 `ACOUTEST_API_TOKEN` 覆盖）。
  - 支持动作：刷新设备、选择设备、开始/停止麦克风测试、开始/停止 logcat 抓取、开始/停止多声道测试、无弹窗截图。

- **录音波形查看增强**
  - 在 `Loopback和Ref测试` 与 `扫频测试` 页面新增“查看录音波形”按钮。
  - 录制成功并保存后自动记住最近录音文件，按钮自动可用，可直接查看最新一次 WAV 波形。

- **波形查看器（播放进度与时间轴对齐）**
  - 修复“红色播放进度线与真实音频时间不一致/看起来延迟”的问题：播放进度改为“高精度系统时钟实时驱动 + 播放器时间校准”，不再只依赖 `pygame.mixer.music.get_pos()`。
  - 进度刷新频率提升到约 30ms 一次，波形上的播放位置、点击光标位置与横轴秒数更稳定对应实际播放时间。

- **烧大象key**
  - u盘烧key 页面按钮顺序调整为：就绪 → 读SN → 烧大象Key → 剩余数量 → 检查key → 打开日志 → 打开目录。
  - 新增「剩余数量」按钮：可查看 U 盘中 key 剩余数量（需插 U 盘，调用 `elevoc_get_license_number()`）。
  - 烧录前二次确认：在 u盘烧key（烧大象Key）与 sn烧key（写入/替换 烧key）时，若检测到设备已有 key，会先弹窗「当前设备已有 key，是否确认覆盖烧录？」，避免误烧录。
- **Logcat 日志**
  - 抓取逻辑：先后台执行 `adb -s <设备> wait-for-device` 等待设备上线，再启动 `adb logcat -v threadtime` 写入文件；支持设备已断开时点“开始抓取”，自动等设备上线后抓取（可抓开机日志）。仅需已选/输入设备序列号，不要求设备当前在线。
  - 音频调试 → Logcat 日志页面：两行操作按钮（放开打印/停止打印、开始抓取/停止抓取/打开文件夹）使用 grid 布局上下对齐。
- **唤醒监测**
  - 与「开始抓取」为两套独立逻辑：唤醒监测单独起 `adb -s <设备> logcat` 进程，实时过滤含「Detected hotword」行并计数。此前过滤为 `native:I` `*:S`，若设备从 Java 层或其他 tag 输出该日志会收不到；已改为 `*:I`，在代码中仍只统计含「Detected hotword」的行，避免漏检。
- **音频调试 → 系统指令**
  - 新增“系统指令”子标签：预设 dumpsys media、tinymix、getprop 等按钮，支持自定义指令输入与运行；结果弹窗支持 Ctrl+F 搜索、刷新、保存；提供设备解锁（Bootloader 解锁 + root/remount）入口。
- **遥控器**
  - 遥控器页面布局与功能完善：方向键、OK、音量、返回、配对遥控、系统设置按钮；快捷应用区域（YouTube、Netflix、Prime Video、HPlayer、Humming EQ 等）支持一键启动，可添加自定义快捷方式。
- **麦克风测试**
  - 新增「查看刚录音波形」按钮：录制结束并保存成功后，可在工具内直接查看最近一次 `.wav` 的多通道波形（不依赖第三方音频软件）。
 - **Loopback / 多声道播放设备选择**
  - Loopback 和 多声道测试新增「播放设备ID(-d)」参数，可手动指定 `tinyplay -d`。
  - 新增「读取alsaPORT播放设备」按钮：自动读取设备 `/proc/asound/pcm` 中的 playback 索引（优先 `alsaPORT-pcm`）并填充下拉选项，适配不同机型 `-d 0/-d 1/...` 差异。

## 使用方法

### 设备连接
1. 通过USB连接Android设备
2. 点击"刷新设备列表"按钮
3. 从下拉列表选择要测试的设备
4. 设备连接状态会在界面上显示

### OpenClaw 控制（HTTP API）
1. 启动 `声测大师` 后，程序会自动启动本地接口：`http://127.0.0.1:8765`（若端口占用会顺延到后续端口）。
2. 主界面 `常用功能` 下新增 `OpenClaw` 子页：可看到连接状态、接口地址、实时请求日志。
3. 主窗口底部状态栏会显示 `OpenClaw: 未连接 / 已连接`，并包含最近请求来源IP、时间和累计请求次数，便于确认是否已连通。
4. `OpenClaw` 子页日志会打印 OpenClaw 请求与其触发的相关 ADB 命令，便于排查自动化动作是否正确执行。
5. OpenClaw 调用时在请求头带上：`X-Api-Token: acoutest-local-token`（或你自定义的 token）。
6. 常用接口：
   - `GET /api/health`：健康检查（无需 token）
   - `GET /api/actions`：查看支持动作
   - `GET /api/devices`：获取设备列表和当前选择
   - `GET /api/status`：获取当前运行状态
   - `POST /api/action`：执行动作
7. `POST /api/action` 请求体示例：
   ```json
   {
     "action": "select_device",
     "params": { "device_id": "192.168.1.10:5555" }
   }
   ```
8. 可用动作（`action`）：
   - `refresh_devices`
   - `select_device`
   - `start_mic_test`
   - `stop_mic_test`
   - `start_logcat_capture`
   - `stop_logcat_capture`
   - `run_multichannel_test`
   - `stop_multichannel_test`
   - `take_screenshot`
9. 参数示例：
   - `start_mic_test`：`{"mic_count":4,"pcm_device":0,"device_id":3,"rate":16000,"save_path":"D:/output/mic_test"}`
   - `start_logcat_capture`：`{"save_path":"D:/output/logcat","filter":"*:V","auto_stop_seconds":60}`
   - `run_multichannel_test`：`{"rate":48000,"bit":16,"preset":"7.1","play_device":0}`
   - `take_screenshot`：`{"save_path":"D:/output/screenshots"}`

### 麦克风测试
1. 选择"麦克风测试"选项卡
2. 设置麦克风数量、PCM设备号、设备ID和采样率
   - 麦克风数量支持下拉选择，也支持手动输入（仅允许正整数）
3. 点击"开始录音"按钮开始测试
4. 点击"停止录音"按钮结束测试，录音文件会自动保存
   - 默认保存目录：`./mic_test`（保存后会自动打开所在文件夹）

### Loopback和Ref测试
1. 选择"Loopback和Ref测试"选项卡
2. 设置设备号、通道数和采样率
3. 选择使用默认测试音频或自定义音频
4. 点击"开始测试"按钮开始测试
5. 点击"停止测试"按钮结束测试，录音文件会自动保存

### 扫频测试
1. 选择"扫频测试"选项卡
2. 选择扫频文件类型和文件
3. 设置录音设备、通道数、采样率等参数
4. 点击"开始测试"按钮开始单次测试，或点击"开始批量测试"进行批量测试
5. 测试完成后，结果会自动保存到指定目录

### 气密性测试（堵mic / 不堵mic）
1. 选择"气密性测试"选项卡
2. 点击"开始气密性测试"后，在弹窗中选择本次模式（堵mic / 不堵mic）
3. 若选择堵mic，按提示先用橡皮泥堵住麦克风孔；若选择不堵mic，按提示确认已去掉橡皮泥
4. 测试脚本固定：播放文件使用 `sweep_speech_48k.wav`，录制/播放命令使用固定参数
5. 录音会保存到气密性专用目录，文件名自动带 `du_mic` 或 `open_mic` 标记，便于后续波形对比
6. 完成堵mic测试后，工具会提示继续进行不堵mic测试；可分别点击“查看堵mic波形 / 查看不堵mic波形 / 对比查看波形”

### HAL录音
1. 选择"HAL录音"选项卡
2. 选择需要启用的录音属性
3. 设置录音目录和保存路径
4. 点击"开始录音"按钮开始录音
5. 点击"停止录音"按钮结束录音，录音文件会自动保存

### 日志监控（Logcat）
1. 主界面选择“音频调试” → 子标签“Logcat日志”
2. 可选：在 logcat 属性管理中勾选需要启用的属性，点击“放开日志打印”在设备上开启对应日志
3. 设置保存路径、自动停止时间（秒）、日志过滤（默认 `*:V`）
4. 点击“开始抓取”开始抓取，点击“停止抓取”结束抓取；结束后可点击“打开文件夹”打开日志目录（文件名为 `audio_logcat_时间戳.txt`，默认目录为 `logcat`）

### 系统指令
1. 主界面选择“音频调试” → 子标签“系统指令”
2. 点击预设按钮（如 dumpsys media.audio_policy、tinymix、getprop 等）执行对应命令，结果在弹窗中显示
3. 弹窗中可使用 **Ctrl+F** 搜索内容，点击“刷新”重新执行命令，点击“保存”将结果保存为文件
4. 在“自定义指令”输入框中输入任意 adb shell 命令（如 `dumpsys media.audio`），点击“运行”执行
5. 设备解锁等敏感操作在“设备解锁”区域，使用前请注意提示（可能清数据）

### 遥控器
1. 主界面选择“常用功能” → 子标签“遥控器”
2. **配对**：点击“配对遥控”，按设备提示完成遥控器配对
3. **发送按键**：点击方向键（↑↓←→）、OK、音量+/-、返回等按钮，向设备发送对应 keycode
4. **打开设置**：点击“设置”在设备上打开系统设置；需要移除遥控器时，可通过设备上的蓝牙/遥控器设置操作
5. **快捷应用**：点击 YouTube、Netflix、Prime Video 等按钮，在设备上启动对应应用（需已安装）；可添加自定义快捷方式

## UI ↔ 底层代码对照表（按钮点了会调用哪里）

> **完整层级说明**：从**大类→小类**、**UI→业务→设备**的整条调用链已整理到 **[接口与调用关系.md](接口与调用关系.md)**，包含架构分层、各小类下「UI 操作 → 方法 → 文件」及典型调用链示例。
>
> 下表为快速对账：每个按钮/操作会调用哪个函数、在哪个文件、关键参数变量；若“点了没反应/报错”，可先查下表再结合 `接口与调用关系.md` 定位。

### 入口（从主界面进入）

| UI入口（窗口/标签） | UI创建函数（界面） | 说明 |
|---|---|---|
| 扫频测试 | `ui_components.py` → `open_sweep_window()` / `setup_sweep_tab()` | 打开“扫频测试”窗口 |
| 麦克风测试 | `ui_components.py` → `open_mic_window()` / `setup_mic_tab()` | 打开“麦克风测试”窗口 |
| 雷达检查 | `ui_components.py` → `open_radar_window()` / `setup_radar_tab()` | 打开“雷达检查”窗口 |
| 喇叭测试 | `ui_components.py` → `open_speaker_window()` / `setup_speaker_tab()` | 打开“喇叭测试”窗口 |
| 多声道测试 | `ui_components.py` → `open_multichannel_window()` / `setup_multichannel_tab()` | 打开“多声道测试”窗口 |
| Loopback和Ref测试 | `ui_components.py` → `open_loopback_window()` / `setup_loopback_tab()` | 打开“Loopback和Ref”窗口 |
| HAL录音 | `ui_components.py` → `open_hal_window()` / `setup_hal_recording_tab()` | 打开“HAL录音”窗口 |
| Logcat日志 | `ui_components.py` → `setup_logcat_tab()` | 主界面 → 音频调试 → Logcat日志 子标签 |
| 系统指令 | `ui_components.py` → `setup_system_cmd_tab()` / `_setup_system_cmd_panel()` | 主界面 → 音频调试 → 系统指令 子标签 |
| 本地播放 | `ui_components.py` → `open_playback_window()` / `setup_local_playback_tab()` | 打开“本地播放”窗口 |
| 截图功能 | `ui_components.py` → `open_screenshot_window()` / `setup_screenshot_tab()` | 打开“截图功能”窗口 |
| 遥控器 | `ui_components.py` → `open_remote_window()` / `setup_remote_tab()` | 打开“遥控器”窗口 |
| 烧大象key | 主界面标签“烧大象key” | u盘烧key / sn烧key 子标签（`ui_components.py` 内 `setup_ukey_burn_tab`、`setup_sn_key_burn_tab`） |

### 按钮/操作 → 调用函数（核心对照）

| 功能页面 | UI操作（按钮/动作） | 最终调用函数 | 底层实现文件 | 关键参数来源（变量名） |
|---|---|---|---|---|
| 设备区（主界面） | 刷新设备 | `refresh_devices()` | `devices_operations.py` | `device_combobox`, `device_var`, `selected_device` |
| 设备区（主界面） | 选择设备 | `on_device_selected()` | `devices_operations.py` | `device_var` |
| 通用（多数功能） | 检查是否选择设备 | `check_device_selected()` | `devices_operations.py` | `device_combobox.get()`, `selected_device` |
| 通用（多数功能） | 组装 ADB 命令 | `get_adb_command(cmd)` | `devices_operations.py` | `selected_device` |
| 麦克风测试 | 开始麦克风测试 | `start_mic_test()` | `test_operations.py` | `mic_count_var`, `pcm_device_var`, `device_id_var`, `rate_var`, `mic_save_path_var` |
| 麦克风测试 | 停止录制 | `stop_mic_test()` | `test_operations.py` | `mic_process`, `mic_filename`, `mic_save_path_var` |
| Loopback和Ref | 开始测试 | `run_loopback_test()` | `ui_components.py` | `loopback_device_var`, `loopback_channel_var`, `loopback_rate_var`, `audio_source_var`, `selected_audio_file`, `loopback_save_path_var` |
| Loopback和Ref | 停止录制 | `stop_loopback_test()` | `ui_components.py` | `loopback_process`, `loopback_filename`, `loopback_save_path_var` |
| 多声道测试 | 开始测试 | `run_multichannel_test()` | `test_operations.py` | `multi_rate_var`, `multi_bit_var` |
| 多声道测试 | 停止测试 | `stop_multichannel_test()` | `test_operations.py` | `multichannel_process`（若存在） |
| 本地播放 | 选择文件 | `browse_local_audio_file()` | `test_operations.py` | `local_audio_file`（文件路径/对象），UI显示为 `local_file_path_var` |
| 本地播放 | 播放 | `play_local_audio()` | `ui_components.py` | `playback_mode_var`, `local_file_path_var`, `volume_var` |
| 本地播放 | 停止 | `stop_local_audio()` | `ui_components.py` | `pygame.mixer` |
| 本地播放 | 调整音量 | `update_volume()` | `test_operations.py` | `volume_var` |
| 扫频测试 | 开始单次/批量测试（同一个开始按钮） | `start_sweep_test(handler)` | `ui_components.py` | `sweep_type_var`, `sweep_file_var`, `record_device_var`, `record_card_var`, `record_channels_var`, `record_rate_var`, `play_device_var`, `play_card_var`, `sweep_duration_var`, `batch_test_var`, `batch_interval_var`, `sweep_save_path_var` |
| 扫频测试 | 停止测试 | `stop_sweep_test(handler)` | `ui_components.py` | `stop_requested`、播放/录制进程（若存在） |
| 扫频测试 | 批量测试线程执行 | `_run_batch_tests(...)` | `ui_components.py` | 同上（由 `start_sweep_test` 触发） |
| HAL录音 | 开始录音 | `start_hal_recording()` | `ui_components.py` | `hal_props`, `hal_duration_var`, `hal_start_time_var` 等 |
| HAL录音 | 停止录音 | `stop_hal_recording()` | `ui_components.py` | `hal_timer`, `hal_props` |
| Logcat日志 | 放开日志打印 | `enable_logcat_debug()` | `ui_components.py` | logcat 属性列表/开关（以页面变量为准） |
| Logcat日志 | 停止日志打印 | `disable_logcat_debug()` | `ui_components.py` | 同上 |
| Logcat日志 | 开始抓取 | `start_logcat_capture()` | `test_operations.py` | `logcat_save_path_var`、过滤条件等 |
| Logcat日志 | 停止抓取 | `stop_logcat_capture()` | `test_operations.py` | `logcat_process`（若存在） |
| 系统指令 | 预设按钮（dumpsys/tinymix/getprop 等） | `open_system_cmd_window(title, shell_cmd)` | `ui_components.py` | `device_var`、`check_device_selected()` |
| 系统指令 | 自定义指令 + 运行 | `open_system_cmd_window("custom", ...)` | `ui_components.py` | `_syscmd_custom_var` |
| 系统指令 | 设备解锁 | `open_device_unlock_window()` | `ui_components.py` | 设备 root/remount 等 |
| 截图功能 | 截图 | `take_screenshot()` | `ui_components.py` | `screenshot_save_path_var` |
| 截图功能 | 打开截图目录 | `open_screenshot_folder()` | `ui_components.py` | `screenshot_save_path_var` |
| 遥控器 | 适配/配对遥控器 | `adapt_remote_controller()` | `ui_components.py` / `test_operations.py` | `device_var`、广播 `NES_RESET_LONGPRESS` |
| 遥控器 | 发送按键（方向/OK/音量/返回） | `send_keycode(keycode)` | `ui_components.py` / `test_operations.py` | `keycode`（如 DPAD_UP、VOLUME_UP、BACK） |
| 遥控器 | 设置 / 移除遥控器 | `launch_quick_action("系统设置", ...)` / 打开设置界面 | `ui_components.py` / `test_operations.py` | 系统设置 Activity、蓝牙设置 |
| 遥控器 | 快捷应用（YouTube/Netflix 等） | `launch_quick_action(name, ...)` | `ui_components.py` | 包名或 shell 命令 |
| 烧大象key（u盘烧key） | 就绪 / UUID / 烧Key / 检查 / 打开日志 / 打开目录 | 见 `ui_components.py` 内 u盘烧key 区域 `do_get_uuid`、`do_burn`、`do_check`、`_open_folder`、`_open_log` 等 | `ui_components.py` | `device_var`、elevoc 工作目录与 DLL 路径 |

### 备注：为什么要“对账”

- `ui_components.py` 负责“画界面 + 绑定按钮回调”，`test_operations.py` 负责“真正执行测试/ADB命令”，`devices_operations.py` 负责“设备选择与ADB命令拼接”。
- 如果你看到“点按钮没反应/跑错设备/参数不生效”，通常是 **变量取错**（比如把 ADB 序列号当成 tinycap 的 `-d`）或 **回调绑错**（按钮调用了同名但不对的函数）。

## 交付给客户：打包哪个文件夹

**给客户发版本时，只需打包「dist 目录」里的内容**（或把整个 dist 打成 zip 发给客户）。

- **必须包含**：`声测大师(AcouTest) v<版本号>.exe`（如 `声测大师(AcouTest) v1.7.1.exe`，版本号来自 `feature_config.py` 的 `APP_VERSION`）、`logo/`、`启动测试工具.bat`；若客户需要烧大象 key，还需带上 `elevoc_ukey/`（含 `soft_encryption.dll` 等）。
- **可选**：`README.md`、`audio/`（若希望客户自带扫频/测试音频，可把你在本机用的 audio 子目录一并拷贝到 dist 里再打包）。
- **不需要给客户**：源码（.py）、build/、output/、.git 等。客户运行 exe 后，程序会在**客户自己的安装目录下**自动创建 `output/` 存放测试数据。

客户使用方式：解压你给的 zip，双击 `声测大师(AcouTest) v<版本号>.exe` 或 `启动测试工具.bat` 即可；测试产生的 logcat、截图、录音等会出现在**该解压目录下的 output/** 里。

### 功能开关：发布时隐藏部分功能

若希望**给客户的版本**只包含部分功能（例如不暴露烧大象 key、唤醒监测等内部功能），可在**打包前**修改项目根目录下的 **`feature_config.py`**：

- **主标签页（大类）**：`MAIN_TABS` 中把不需要给客户的大类设为 `False`，例如 `"烧大象key": False`，则该大类不会出现在界面上。
- **子标签页（小类）**：`SUB_TABS` 中按大类名和子标签名控制，例如 `"音频调试"` 下的 `"唤醒监测": False`，则「唤醒监测」子页不会显示。

修改并保存后，再执行 **Packager.bat** 打包，生成的 exe 即只包含你开启的功能；客户看不到被关闭的大类或子页。自己使用时，把对应项改回 `True` 再打包即可得到完整版。若删除或未找到 `feature_config.py`，程序会默认显示全部功能。

---

## 测试数据目录（output）与「为什么 output 不在 dist 里」

程序里用「当前工作目录（cwd）」+ `output` 作为测试数据根目录（见 `output_paths.py` 中的 `os.getcwd()`），所以 **output 永远出现在「你运行程序时所在的那个目录」下**，而不是固定在源码根或 dist 里：

| 运行方式 | 当前工作目录（cwd） | output 实际位置 |
|----------|---------------------|-----------------|
| 开发时用源码运行（如 `python main.py`） | 项目根目录 | **项目根/output/** |
| 开发时双击 dist 里的 exe 测试 | dist 目录 | **dist/output/** |
| 客户解压后双击 exe | 客户解压目录（如 `D:\声测大师`） | **D:\声测大师\output/** |

因此：
- **开发阶段**：你在项目根或 dist 里跑，看到的是项目根或 dist 下的 output，这是正常的。
- **交付阶段**：不需要把 output 打进给客户的包；客户运行 exe 后，程序会在**客户自己的文件夹**下新建 output，所有测试数据都在那里，和 exe 同目录，方便客户查找。

把 output 设计成「跟着运行目录走」，是为了：无论从源码、从 dist 还是客户本机运行，测试数据都落在**当前运行目录**下，不会混在一起，也不需要为「是否在 dist 里」单独写两套路径。

---

以下为 output 子目录说明。所有测试生成的数据（日志、截图、录音等）默认统一放在**当前运行目录下的 output** 中，按类型分子目录。配置见 `output_paths.py`。

| 子目录 | 用途 |
|--------|------|
| `output/logcat/` | Logcat 抓取文件（如 `audio_logcat_时间戳.txt`） |
| `output/screenshots/` | 设备截图（如 `screenshot_时间戳.png`） |
| `output/mic_test/` | 麦克风测试录音 |
| `output/sweep_recordings/` | 扫频测试录音 |
| `output/airtightness/` | 气密性测试录音（堵mic/不堵mic） |
| `output/loopback/` | Loopback/Ref 测试录音 |
| `output/hal_dump/` | HAL 录音拉取文件（含时间戳子目录） |
| `output/hal_custom/` | 自定义 HAL 录音拉取 |

- 各功能界面中的“保存路径”可修改，未填写时使用上表对应默认子目录。
- “打开文件夹”类按钮会打开当前功能使用的目录；若某处提供“打开测试数据根目录”，则打开 `output` 根目录。
- `.gitignore` 已忽略 `output/`，避免将测试数据提交到版本库。

**若项目根目录或 dist 目录下仍存在旧的分散目录**（`logcat/`、`screenshots/`、`mic_test/`、`sweep_recordings/`、`hal_dump/`、`test/`），可手动删除以保持整洁；如需保留其中文件，请先复制到 `output/` 下对应子目录。

## 技术要求

- 操作系统：Windows 7/10/11
- Python 3.6 或更高版本
- 依赖库：tkinter, pygame, subprocess, threading
- ADB工具（Android Debug Bridge）

## 安装方法

1. 安装Python 3.6或更高版本
2. 安装必要的依赖库：
   ```
   pip install pygame
   ```
3. 确保ADB工具已安装并添加到系统PATH
4. 下载本工具的源代码
5. 运行main.py启动工具

## 常见问题

### 设备连接问题
- 确保USB调试已开启
- 尝试重新连接设备
- 检查ADB驱动是否正确安装

### 录音问题
- 确保设备麦克风未被其他应用占用
- 检查录音参数设置是否正确
- 尝试使用不同的PCM设备号

### 扫频/录制失败：Permission denied（Unable to open PCM device）
- 报错示例：`Unable to open PCM device (cannot open device X for card 0: Permission denied)`  
  说明设备上的 **tinycap** 没有权限打开该 PCM 设备。
- **建议**：  
  1) 在电脑上执行 **`adb root`** 获取 root 权限后，再在工具里进行扫频测试（部分设备需已解锁并支持 root）。  
  2) 检查扫频「录制设置」里的**设备、卡号**是否为当前设备实际可用的 PCM 编号（如 0、1、2 等），不同机型可用编号不同，可向设备方确认或尝试 0/1/2。

### 播放问题
- 确保音频文件格式正确
- 检查设备扬声器是否正常工作
- 尝试使用不同的播放方式

### 打包后启动报错（pygame/numpy）

如果你运行打包后的 exe，在启动阶段看到类似报错：

- `RuntimeError: CPU dispatcher tracer already initlized`

这是因为 **pygame 导入时会尝试导入 numpy**（来自 `pygame.sndarray`），而 numpy 在部分 CPU/打包环境下可能在导入阶段崩溃。

本项目的处理方式是：

- **pygame 改为按需导入**：只有使用“本地播放”时才会加载；即使失败也不会影响其它功能启动。
- **PyInstaller 打包时排除 numpy**：见 `声测大师(AcouTest).spec` 中的 `excludes=['numpy']`，这样 pygame 就不会导入 numpy，从而避免该崩溃。

### audio 目录结构（扫频与喇叭测试用）

程序只认以下**英文目录名**，避免重复放两套内容：

| 目录 | 用途 | 说明 |
|------|------|------|
| `audio/elephant/` | 大象扫频文件 | 界面选「大象扫频文件」时从这里加载 .wav |
| `audio/custom/` | 自定义扫频文件 | 界面选「自定义扫频文件」时从这里加载；支持「添加文件」拷贝进来 |
| `audio/speaker/speaker_default.wav` | 喇叭测试默认音频 | 界面选「默认音频」时用此文件做喇叭测试 |

- **只需保留一套**：若你之前有 `大象扫频文件`、`自定义扫频文件20Hz-20KHz_0dB` 等中文目录，内容与 `elephant`、`custom` 相同，可只保留 `elephant` 和 `custom`，删除中文目录或不再拷贝到 dist，避免重复。
- **喇叭默认音频**：请把默认用的 wav 放在 `audio/speaker/speaker_default.wav`。

### 打包体积为什么会变大？（audio 文件夹很大）

结论先说：**文件夹可以存在**，但如果打包脚本把 `audio/` 作为“数据文件”一起加入，就会把里面的所有音频都塞进 exe，导致 exe 体积暴涨。

本项目现在的策略是：

- **exe 不再内置 `audio/` 的音频数据**：打包仅包含代码 + `logo/`。
- **默认测试音频不再自动生成**：如果你选择了“默认音频”但目录里没有对应文件，程序会提示你把文件放进 `audio/speaker/speaker_default.wav` 或改选“自定义音频”。
- **扫频与喇叭用**：请把文件放在 `audio/elephant/`、`audio/custom/`、`audio/speaker/speaker_default.wav`；这些文件不会因为存在于源码目录就自动进入 exe（除非你在打包命令里显式 `--add-data audio;audio`）。

### 启动自动更新（推荐）

你可以让用户在启动旧版本时自动弹出“发现新版本”窗口，并一键更新到当前安装目录，不需要你每次手工发新包。

#### 1) 准备更新清单（manifest）

- 使用项目根目录的 `update_manifest.json` 作为更新清单模板，按同样字段维护线上 JSON 文件。
- 必填字段：
  - `latest_version`：最新版本号（例如 `1.8.2`）
  - `download_url`：新版本安装包地址（支持 zip 或 exe）
  - `notes`：更新说明（字符串或字符串数组）

#### 2) 配置清单地址（任选其一）

- 方式 A：在 `feature_config.py` 填 `UPDATE_MANIFEST_URL`（单地址）或 `UPDATE_MANIFEST_URLS`（多地址）
- 方式 B：设置环境变量 `ACOUTEST_UPDATE_MANIFEST_URL`（支持多个地址，逗号分隔）
- 方式 C：在安装目录放 `update_config.json`，内容示例（主地址失败自动尝试备用地址）：

```json
{
  "manifest_urls": [
    "https://cdn.jsdelivr.net/gh/your-org/acoutest-release@main/update_manifest.json",
    "https://raw.githubusercontent.com/your-org/acoutest-release/main/update_manifest.json"
  ]
}
```

如果你希望不改代码，也可以在安装目录放 `update_config.json`，直接写你的更新地址。

#### 3) 用户侧体验

- 启动程序后自动后台检查更新（可用 `UPDATE_AUTO_CHECK=False` 关闭）。
- 顶部工具栏支持“检查更新”按钮，用户可随时手动检查，不用重启程序。
- 发现新版本会弹窗显示版本号与更新说明。
- 用户点击“立即更新”后：
  - 自动下载更新包
  - 将新版本文件保存到当前安装目录
  - 提示用户关闭当前程序后，手动启动新的 exe 生效

## 联系与支持

如有问题或建议，请联系开发者，邮箱：807946809@qq.com。

---

© 2026 声测大师(AcouTest) 保留所有权利 