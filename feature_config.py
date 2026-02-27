# -*- coding: utf-8 -*-
"""
功能开关配置：控制哪些大类/子类在界面上显示。

使用方式：
- 发布给客户前：将不需要给客户的大类或子功能改为 False，然后执行 Packager.bat 打包。
- 自己使用时：将需要的项设为 True，或直接使用“全部开启”的配置。

True = 显示该功能
False = 不显示（相当于不编译进本次发布）
"""

# ========== 应用版本号（仅改此处，主窗口标题、软件信息弹窗、状态栏等会统一更新） ==========
APP_VERSION = "1.7.6"

# ========== 主标签页（五大类） ==========
# 设为 False 时，整个大类不会出现在界面上
MAIN_TABS = {
    "硬件测试": True,
    "声学测试": True,
    "音频调试": True,
    "常用功能": True,
    "烧大象key": True,   # 内部功能，给客户发布时可改为 False
}

# ========== 各大类下的子标签 ==========
# 只影响对应大类下的子页；若整类 MAIN_TABS 为 False，则不会用到这里的配置
SUB_TABS = {
    "硬件测试": {
        "麦克风测试": True,
        "雷达检查": True,
        "喇叭测试": True,
        "多声道测试": True,
    },
    "声学测试": {
        "扫频测试": True,
        "震音测试": True,
    },
    "音频调试": {
        "Loopback和Ref测试": True,
        "HAL录音": True,
        "Logcat日志": True,
        "唤醒监测": True,
        "系统指令": True,
    },
    "常用功能": {
        "遥控器": True,
        "本地播放": False,
        "截图功能": True,
        "账号登录": True,
    },
    "烧大象key": {
        "u盘烧key": True,
        "sn烧key": True,
    },
}


def is_main_tab_enabled(tab_name):
    """主标签是否启用"""
    return MAIN_TABS.get(tab_name, True)


def is_sub_tab_enabled(main_tab_name, sub_tab_name):
    """子标签是否启用（前提是主标签已启用）"""
    subs = SUB_TABS.get(main_tab_name, {})
    return subs.get(sub_tab_name, True)
