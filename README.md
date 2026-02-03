# 声测大师(AcouTest)

## 项目概述

声测大师(AcouTest)是一个专为音频系统测试设计的综合工具，支持多种音频测试功能，包括麦克风测试、多声道测试、扫频测试、HAL录音、日志监控、系统指令、遥控器与快捷应用、烧大象key等。该工具可帮助音频工程师和质量测试人员进行音频设备的测试、调试和问题排查。

**主界面结构**：顶部为设备选择与刷新；主区域为多标签页——**声学测试**（扫频等）、**硬件测试**（麦克风、雷达等）、**音频调试**（Loopback和Ref、HAL录音、Logcat日志、系统指令）、**常用功能**（本地播放、截图、遥控器）、**烧大象key**（u盘烧key、sn烧key）。

## 主要功能

### 1. 麦克风测试
- 支持多麦克风录音测试
- 可设置PCM设备号、设备ID、采样率等参数
- 实时显示录音状态
- 自动保存录音文件

### 2. Loopback和Ref测试
- 支持回路测试和参考通道测试
- 可选择设备、通道数和采样率
- 支持自定义测试音频或使用默认测试音频
- 实时显示测试状态

### 3. 多声道测试
- 支持7.1声道音频播放测试
- 可设置采样率和位深
- 适用于多声道音频系统测试

### 4. 本地播放
- 支持播放本地音频文件
- 支持将音频推送到设备播放
- 支持音量调节
- 支持多种音频格式

### 5. 扫频测试
- 支持单次扫频测试和批量扫频测试
- 支持自定义扫频音频文件
- 可设置录音设备、通道数、采样率等参数
- 自动保存测试结果

### 6. HAL录音
- 支持多种HAL录音属性设置
- 可自定义录音目录
- 支持自动停止录音
- 可批量拉取录音文件

### 7. 自定义HAL录音
- 支持添加自定义录音属性
- 可自定义录音目录和保存路径
- 支持自动停止录音
- 可批量拉取录音文件

### 8. 屏幕截图
- 支持设备屏幕截图
- 可自定义保存路径
- 自动生成时间戳文件名

### 9. 喇叭测试
- 支持喇叭测试音频播放
- 支持默认测试音频或自定义音频

### 10. 日志监控（Logcat）
- **入口**：主界面 → 音频调试 → Logcat日志 子标签。
- **logcat 属性管理**：可勾选/添加系统属性（如 `vendor.avdebug.debug`、`log.tag.APM_AudioPolicyManager` 等），通过“放开打印”/“停止打印”在设备上开启或关闭对应日志输出。
- **日志抓取**：设置保存路径、自动停止时间（秒）、日志过滤（默认 `*:V`）后，点击“开始抓取”将设备 logcat 实时写入本地文件，点击“停止抓取”结束；支持“打开文件夹”打开日志目录。
- **日志过滤器语法**（`TAG:PRIORITY`）：
  - TAG：日志标签，如 AudioFlinger、AudioPolicyManager 等。
  - PRIORITY：V(详细)、D(调试)、I(信息)、W(警告)、E(错误)、F(严重)、S(静默)。
  - 示例：`*:V` 显示所有日志；`*:W` 仅警告及以上；`audio*:V *:S` 仅以 "audio" 开头的标签。
- **抓取实现说明（与 V1.5 一致）**：仅执行 `logcat -v threadtime` + 过滤，不指定 `-b`，使用设备默认 buffer；stdout 直接写入文件（无 PIPE、无读线程），避免停止时管道内数据丢失；adb 使用参数列表调用，避免 Windows 下 `*:V` 被 shell 展开。文件名：`audio_logcat_时间戳.txt`，默认目录：`logcat`。

### 11. 系统指令（音频调试）
- **入口**：主界面 → 音频调试 → 系统指令 子标签。
- **功能**：在已选设备上执行常用 ADB 系统命令，结果在弹窗中显示；弹窗支持 **Ctrl+F 搜索**、**刷新**、**保存** 到文件。
- **预设按钮**：`dumpsys media.audio_policy`、`dumpsys media.audio_flinger`、`dumpsys audio`、`tinymix`、`getprop`、`getprop ro.build.fingerprint`、`dumpsys input`。点击即执行对应命令并显示输出。
- **设备解锁**：提供“Bootloader 解锁 + root/remount”入口（会强提示，可能清数据，请谨慎使用）。
- **自定义指令**：在输入框中输入任意 adb shell 指令（如 `dumpsys media.audio`），点击“运行”执行并在弹窗中查看结果。

### 12. 遥控器管理
- **入口**：主界面 → 常用功能 → 遥控器 子标签。
- **适配遥控器**：点击“配对遥控”或“开始适配遥控器”，通过 `adb shell am broadcast -a com.nes.intent.action.NES_RESET_LONGPRESS` 进入设备端遥控器配对流程；适配完成后可在设备上使用物理遥控器。
- **发送按键**：界面提供方向键（↑↓←→）、OK、音量+/-、返回等按钮，点击后通过 ADB 向设备发送对应 keycode（如 DPAD_UP、VOLUME_UP、BACK），用于远程模拟遥控器操作。
- **系统设置**：提供“设置”按钮，在设备上打开系统设置（`am start -n com.android.tv.settings/.MainSettings`），便于进入设置界面进行遥控器移除等操作。
- **移除已配对遥控器**：通过“打开遥控器设置”在设备上打开蓝牙/遥控器设置页面，在设备屏幕上选择要移除的遥控器并执行“移除”或“忘记”。
- **快捷应用**：下方“快捷应用”区域提供一键在设备上启动常用 App：
  - 内置：YouTube、Netflix、Prime Video、HPlayer、Humming EQ 等；通过 ADB 执行 `monkey -p <包名> -c android.intent.category.LAUNCHER 1` 或指定 Activity 启动，不依赖具体 Activity，兼容性更好。
  - 支持添加自定义快捷方式（名称 + 启动方式/包名），仅当前运行期有效。
  - 前提：设备已连接 ADB 且已授权；若应用未安装会提示启动失败。

### 13. 雷达检查功能
- 支持 Radar 相关 logcat 监控（如 updateGain）。
- 可检查设备是否存在 TTY 设备（如 ttyACM），用于判断雷达节点是否就绪。

### 14. 烧大象key
- **u盘烧key**：读取设备 UUID → 调用 soft_encryption.dll 生成 license → 写回 unifykeys(elevockey)。页面按钮顺序：就绪 → UUID → 烧Key → 检查 → 打开日志 → 打开目录。
- **sn烧key**：按 sn烧key 流程检查/写入 unifykeys elevockey，支持获取SN、检查支持、读取当前 key、写入/替换 elevockey。
- 说明：DLL 可能不支持中文路径，本工具会在临时英文目录运行所需文件。

## 最近更新（V1.6）

- **烧大象key**
  - u盘烧key 页面按钮顺序调整为：就绪 → UUID → 烧Key → 检查 → 打开日志 → 打开目录（“打开日志”“打开目录”置于“检查”之后）。
- **Logcat 日志**
  - 抓取逻辑与 V1.5 一致：仅 `logcat -v threadtime` + 过滤，不指定 `-b`，直接写入文件，参数列表调用 adb 避免 `*` 被 shell 展开；开始抓取前使用 `check_device_selected()` 检查设备。
  - 音频调试 → Logcat 日志页面：两行操作按钮（放开打印/停止打印、开始抓取/停止抓取/打开文件夹）使用 grid 布局上下对齐。
- **音频调试 → 系统指令**
  - 新增“系统指令”子标签：预设 dumpsys media、tinymix、getprop 等按钮，支持自定义指令输入与运行；结果弹窗支持 Ctrl+F 搜索、刷新、保存；提供设备解锁（Bootloader 解锁 + root/remount）入口。
- **遥控器**
  - 遥控器页面布局与功能完善：方向键、OK、音量、返回、配对遥控、系统设置按钮；快捷应用区域（YouTube、Netflix、Prime Video、HPlayer、Humming EQ 等）支持一键启动，可添加自定义快捷方式。

## 使用方法

### 设备连接
1. 通过USB连接Android设备
2. 点击"刷新设备列表"按钮
3. 从下拉列表选择要测试的设备
4. 设备连接状态会在界面上显示

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

> 这张表用于“对账”：你看到的每个按钮/操作，最终会调用哪个函数、在哪个文件里实现、用到哪些关键参数变量。
> 如果后续出现“UI看起来有，但点了没反应/报错”，优先用这张表定位问题。

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

## 测试数据目录（output）

所有测试生成的数据（日志、截图、录音等）默认统一放在项目根目录下的 **output** 文件夹中，按类型分子目录，便于查找和管理。配置见 `output_paths.py`。

| 子目录 | 用途 |
|--------|------|
| `output/logcat/` | Logcat 抓取文件（如 `audio_logcat_时间戳.txt`） |
| `output/screenshots/` | 设备截图（如 `screenshot_时间戳.png`） |
| `output/mic_test/` | 麦克风测试录音 |
| `output/sweep_recordings/` | 扫频测试录音 |
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

### 打包体积为什么会变大？（audio 文件夹很大）

结论先说：**文件夹可以存在**，但如果打包脚本把 `audio/` 作为“数据文件”一起加入，就会把里面的所有音频都塞进 exe，导致 exe 体积暴涨。

本项目现在的策略是：

- **exe 不再内置 `audio/` 的音频数据**：打包仅包含代码 + `logo/`。
- **默认测试音频不再自动生成**：如果你选择了“默认音频”但目录里没有对应文件，程序会提示你把文件放进 `audio/` 或改选“自定义音频”。
- **你仍然可以自己往 `audio/大象扫频文件`、`audio/自定义扫频文件20Hz-20KHz_0dB` 放文件**：程序会读取这些目录里的文件来做测试；这些文件不会因为存在于源码目录就自动进入 exe（除非你在打包命令里显式 `--add-data audio;audio`）。

## 联系与支持

如有问题或建议，请联系开发团队。

---

© 2025 声测大师(AcouTest) 保留所有权利 