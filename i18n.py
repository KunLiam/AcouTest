# -*- coding: utf-8 -*-
"""
国际化（中文 / English）支持。

设计思路：
- 业务代码里的中文字符串保持不变；英文模式下在 Tk 层统一拦截「要显示出来的文字」
  （控件 text/label、Notebook 页签、窗口标题、弹窗、日志 Text、StringVar、下拉框 values 等），
  按中文片段查 i18n_en.EN 对照表替换成英文。
- 动态拼接的句子（如 f"已连接 {n} 台设备"）按片段分别翻译，数字/设备号等原样保留。
- 代码里如果读回控件文字做判断（cget / StringVar.get / Combobox.get），会自动还原成中文原文，
  因此业务逻辑不受影响。
- 中英文模式都会安装钩子；中文模式下钩子原样放行，显示与原版一致。
- 运行中切换语言（switch_language）：遍历所有窗口和控件，取回每段文字的中文原文，
  再按新语言重新设置一遍；已经打印出来的日志保持原语言。

对外接口：
    get_language() -> "zh" | "en"
    set_language(lang)            # 保存偏好（下次启动也用这个语言）
    is_english() -> bool
    tr(text) -> str               # 手动翻译一段文字（中文模式原样返回）
    install_tk_hooks()            # 在创建 tk.Tk() 之前调用
    switch_language(root, lang)   # 不重启，立即把整个界面切换成 lang
"""
import json
import os
import re
import sys
import time

SUPPORTED_LANGUAGES = ("zh", "en")

# ---------------------------------------------------------------------------
# 片段识别（i18n_extract.py 使用同一套规则，保证提取与运行时一致）
# ---------------------------------------------------------------------------
_CJK = "\u4e00-\u9fff"
# 中文标点（全角符号、中文引号、省略号、破折号、间隔号）
_CJK_PUNCT = "\u3000-\u303f\uff01-\uff0f\uff1a-\uff20\uff3b-\uff40\uff5b-\uff65\u2014\u2026\u201c\u201d\u2018\u2019\u00b7"
_CJK_CHUNK = f"[{_CJK}{_CJK_PUNCT}]+"
# 一个片段：中文块，中间允许夹少量英文/数字/空格（两侧都必须是中文块），例如「请先选择ADB设备」
_RUN_RE = re.compile(f"{_CJK_CHUNK}(?:[A-Za-z0-9 ._+\\-]{{1,24}}{_CJK_CHUNK})*")
_HAS_CJK_RE = re.compile(f"[{_CJK}]")
_EDGE_PUNCT_RE = re.compile(f"^([{_CJK_PUNCT}\\s]*)(.*?)([{_CJK_PUNCT}\\s]*)$", re.S)

_PUNCT_MAP = {
    "，": ", ", "。": ". ", "：": ": ", "；": "; ", "！": "! ", "？": "? ",
    "（": " (", "）": ") ", "【": "[", "】": "] ", "「": "\"", "」": "\"",
    "『": "\"", "』": "\"", "“": "\"", "”": "\"", "‘": "'", "’": "'",
    "、": ", ", "…": "...", "—": "-", "《": "\"", "》": "\"", "\u3000": " ",
    "～": "~", "·": "·", "／": "/", "％": "%", "＋": "+", "＝": "=", "＜": "<", "＞": ">",
    "［": "[", "］": "]", "｛": "{", "｝": "}", "｜": "|", "＃": "#", "＆": "&", "＊": "*",
    "＠": "@", "＿": "_", "－": "-", "＂": "\"", "＇": "'", "〔": "[", "〕": "]",
    "〈": "<", "〉": ">", "〜": "~",
}


def iter_cjk_segments(text):
    """从一段文字中取出所有需要翻译的中文片段（去掉首尾标点后的核心部分）。"""
    for m in _RUN_RE.finditer(text or ""):
        core = _EDGE_PUNCT_RE.match(m.group()).group(2)
        if core and _HAS_CJK_RE.search(core):
            yield core


# ---------------------------------------------------------------------------
# 语言偏好
# ---------------------------------------------------------------------------
def _build_default_language():
    """打包时的默认语言：英文包由 Packager 生成 i18n_build_default.py；否则读 feature_config。"""
    try:
        from i18n_build_default import DEFAULT_LANGUAGE as lang  # type: ignore
        if lang in SUPPORTED_LANGUAGES:
            return lang
    except Exception:
        pass
    try:
        from feature_config import DEFAULT_LANGUAGE as lang  # type: ignore
        if lang in SUPPORTED_LANGUAGES:
            return lang
    except Exception:
        pass
    return "zh"


def _settings_path():
    """用户语言偏好文件路径；按包的默认语言分开存，中文包和英文包互不影响。"""
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/AcouTest")
    elif os.name == "nt":
        base = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "AcouTest")
    else:
        base = os.path.expanduser("~/.acoutest")
    return os.path.join(base, f"language_{_build_default_language()}.json")


_language = None


def get_language():
    """当前语言：环境变量 ACOUTEST_LANG > 用户偏好 > 包默认语言。"""
    global _language
    if _language:
        return _language
    lang = (os.environ.get("ACOUTEST_LANG") or "").strip().lower()
    if lang not in SUPPORTED_LANGUAGES:
        lang = ""
        try:
            with open(_settings_path(), "r", encoding="utf-8") as f:
                lang = str(json.load(f).get("language") or "").strip().lower()
        except Exception:
            pass
    if lang not in SUPPORTED_LANGUAGES:
        lang = _build_default_language()
    _language = lang
    return lang


def is_english():
    return get_language() == "en"


def set_language(lang):
    """保存语言偏好（下次启动时使用）。返回是否保存成功。"""
    if lang not in SUPPORTED_LANGUAGES:
        return False
    path = _settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"language": lang}, f)
        return True
    except Exception as e:
        print(f"[i18n] 保存语言偏好失败: {e}")
        return False


# ---------------------------------------------------------------------------
# 翻译
# ---------------------------------------------------------------------------
_EN = None
_EN_MAXLEN = 0
# 英文 -> 中文原文，用于读回控件文字时还原（只记录短文本，日志不记录）
_REVERSE = {}
_REVERSE_LIMIT = 20000
# 不翻译的固定文字（如语言切换按钮本身）
_NO_TRANSLATE = {"中文", "English", "中文 / English"}
# 拆分拼接时允许单独使用的单字（量词/连词）；其他单字含义依赖上下文，只在整段精确匹配时使用
_SAFE_SINGLE_CHARS = set("个秒次条台分帧行轮和或第共")


def _load_dict():
    global _EN, _EN_MAXLEN
    if _EN is None:
        try:
            from i18n_en import EN
            _EN = dict(EN)
        except Exception as e:
            print(f"[i18n] 加载英文对照表失败: {e}")
            _EN = {}
        _EN_MAXLEN = max((len(k) for k in _EN), default=0)
    return _EN


_SPACE_BEFORE_CLOSE_RE = re.compile(r" +([.,;:!?)\]])")


def _map_punct(s):
    out = "".join(_PUNCT_MAP.get(ch, ch) for ch in s)
    # 「）。」这类连续标点映射后会出现 ") ." ，去掉右侧标点前的空格
    return _SPACE_BEFORE_CLOSE_RE.sub(r"\1", out)


# 句首保持小写的技术词（命令、属性名等）
_LOWERCASE_TECH_WORDS = {
    "adb", "am", "logcat", "tinycap", "tinyplay", "tinymix", "dumpsys", "getprop", "setprop",
    "wav", "pcm", "ukey", "usid", "unifykeys", "elevockey", "key", "root", "su", "pull", "push",
    "mic", "apk", "ms", "dbfs", "e.g.", "vs",
}


def _capitalize_first(body):
    m = re.match(r"([a-z][A-Za-z.\-]*)", body)
    if not m or m.group(1).lower() in _LOWERCASE_TECH_WORDS:
        return body
    return body[0].upper() + body[1:]


def _translate_core(core, en):
    """翻译一个去掉首尾标点的片段；整段查不到时按最长匹配逐段拆分。"""
    hit = en.get(core)
    if hit is not None:
        return hit
    out = []
    i, n = 0, len(core)
    pending = []
    while i < n:
        found = None
        for j in range(min(n, i + _EN_MAXLEN), i, -1):
            piece = core[i:j]
            if len(piece) == 1 and piece not in _SAFE_SINGLE_CHARS:
                # 单字只有前后都不是汉字时才单独翻译（如「第 3 段」里的「段」）
                prev_c = core[i - 1:i]
                next_c = core[i + 1:i + 2]
                if _HAS_CJK_RE.match(prev_c) or _HAS_CJK_RE.match(next_c):
                    continue
            v = en.get(piece)
            if v is not None:
                found = (j, v)
                break
        if found:
            if pending:
                out.append(_map_punct("".join(pending)))
                pending = []
            out.append(found[1])
            i = found[0]
        else:
            pending.append(core[i])
            i += 1
    if pending:
        out.append(_map_punct("".join(pending)))
    return _join_words(out)


def _join_words(parts):
    """拼接英文片段，词与词之间补空格、去掉多余空格。"""
    res = ""
    for p in parts:
        if not p:
            continue
        if res and res[-1].isalnum() and p[0].isalnum():
            res += " "
        elif res.endswith(" ") and p.startswith(" "):
            p = p.lstrip(" ")
        res += p
    return res


def _is_ascii_path_char(ch):
    return bool(ch) and ord(ch) < 128 and (ch.isalnum() or ch in "_.-~:")


_PATH_BEFORE_RE = re.compile(r"(?:^|[\s\"'(=:])(?:[A-Za-z]:)?[~.]?[/\\](?:[\w.\-~\u4e00-\u9fff]*[/\\])*$")
_PATH_AFTER_RE = re.compile(r"^[/\\][A-Za-z0-9_\-~]*(?:[/\\.][A-Za-z0-9_\-~]*)*[/\\.][A-Za-z0-9_]")


def _is_path_part(text, start, end):
    """
    片段是否是路径/文件名的一部分（如 /Users/x/测试/a.wav、测试/a.wav、使用说明.txt）。
    「离线/未授权」「ADB/设备连接」这类用斜杠分隔的普通词不算路径。
    """
    run = text[start:end]
    if _HAS_CJK_RE.match(run[:1]) and start > 0 and text[start - 1] in "/\\":
        if _PATH_BEFORE_RE.search(text[max(0, start - 200):start]):
            return True
    if _HAS_CJK_RE.match(run[-1:]) and end < len(text):
        tail = text[end:end + 200]
        if tail[:1] in "/\\" and _PATH_AFTER_RE.match(tail):
            return True
        if re.match(r"\.[A-Za-z0-9]{1,6}\b", tail):
            return True
    return False


def _translate_run(match, text, en):
    start, end = match.start(), match.end()
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""
    # 路径里的中文文件夹/文件名保持原样（如 /Users/x/测试/a.wav）
    if _is_path_part(text, start, end):
        return match.group()
    lead, core, tail = _EDGE_PUNCT_RE.match(match.group()).groups()
    body = _map_punct(lead) + _translate_core(core, en) + _map_punct(tail)
    # 与原文前后的字母/数字之间补空格，去掉行首行尾因标点映射产生的多余空格
    if before and (before.isalnum() or before in ")]}") and body[:1].isalnum():
        body = " " + body
    if before in ("", "\n", " ", "\t", "(", "[", "{", "\"", "'") or before.isspace():
        body = body.lstrip(" ")
    if after and (after.isalnum() or after in "([{") and body[-1:].isalnum():
        body = body + " "
    if after in ("", "\n", " ", "\t", "\r", ")", "]", "}", ",", ".", ":", ";", "!", "?", "\"", "'"):
        body = body.rstrip(" ")
    # 英文双引号：根据前面引号个数判断是开引号还是闭引号，补上词与引号之间的空格
    if after == "\"" and text[:end].count("\"") % 2 == 0 and body[-1:].isalnum():
        body = body + " "
    if before == "\"" and text[:start - 1].count("\"") % 2 == 1 and body[:1].isalnum():
        body = " " + body
    # 「增加/删除」：斜杠后面的译文先打标记，整句翻完后再按前一个词的大小写调整
    if before == "/" and body[:1].isupper():
        body = _SLASH_MARK + body
    # 整段文字（或一行）以中文开头时，英文句首大写
    if before in ("", "\n"):
        body = _capitalize_first(body)
    return body


# 整词优先替换（在片段翻译之前执行）
_PHRASES = (
    ("声测大师(AcouTest)", "AcouTest"),
    ("声测大师（AcouTest）", "AcouTest"),
    ("声测大师", "AcouTest"),
)


_SLASH_MARK = "\x00"
_SLASH_CASE_RE = re.compile(r"([a-z])/\x00([A-Z])(?=[a-z])")


def _translate(text):
    en = _load_dict()
    for zh, eng in _PHRASES:
        if zh in text:
            text = text.replace(zh, eng)
    out = _RUN_RE.sub(lambda m: _translate_run(m, text, en), text)
    if _SLASH_MARK in out:
        out = _SLASH_CASE_RE.sub(lambda m: f"{m.group(1)}/{m.group(2).lower()}", out).replace(_SLASH_MARK, "")
    return out


def tr(text, remember=False):
    """
    把文字翻译成当前语言。中文模式或不含中文时原样返回。
    remember=True 时记录 英文->中文 映射，读回控件文字时可还原。
    """
    if not isinstance(text, str) or not text or get_language() != "en":
        return text
    if text in _NO_TRANSLATE or not _HAS_CJK_RE.search(text):
        return text
    try:
        out = _translate(text)
    except Exception as e:
        print(f"[i18n] 翻译失败: {e}")
        return text
    if remember and out != text and len(_REVERSE) < _REVERSE_LIMIT and len(text) < 400:
        _REVERSE[out] = text
    return out


def untr(text):
    """把 tr(remember=True) 翻译过的英文还原成中文原文；未记录的原样返回。"""
    if isinstance(text, str) and _REVERSE:
        return _REVERSE.get(text, text)
    return text


def _tr_seq(values, remember=True):
    """翻译 list/tuple 中的字符串元素（下拉框 values、表格行等）。"""
    if isinstance(values, (list, tuple)):
        return type(values)(tr(v, remember) if isinstance(v, str) else v for v in values)
    if isinstance(values, str):
        return tr(values, remember)
    return values


def _untr_seq(values):
    if isinstance(values, (list, tuple)):
        return type(values)(untr(v) if isinstance(v, str) else v for v in values)
    return untr(values)


def _looks_like_path(s):
    """路径（含中文文件夹名）不翻译，避免显示的路径和实际路径不一致。"""
    if not isinstance(s, str) or "\n" in s:
        return False
    t = s.strip()
    return t.startswith(("/", "~", "\\\\")) or bool(re.match(r"^[A-Za-z]:[\\/]", t))


# ---------------------------------------------------------------------------
# Tk 钩子
# ---------------------------------------------------------------------------
_TEXT_KEYS = ("text", "label")
_hooks_installed = False


def _tr_options(opts, widget_name=None):
    """就地翻译一个 Tk 选项字典里的显示文字，返回新字典。"""
    if not isinstance(opts, dict) or not opts:
        return opts
    out = dict(opts)
    for k in _TEXT_KEYS:
        v = out.get(k)
        if isinstance(v, str):
            out[k] = tr(v, remember=True)
    if "values" in out:
        out["values"] = _tr_seq(out["values"])
    # 英文通常比中文长：按钮/标签按「字符宽度」写死时自动放宽，避免文字被截断
    w = out.get("width")
    t = out.get("text")
    if (
        _is_char_width_widget(widget_name)
        and isinstance(w, int)
        and w > 0
        and isinstance(t, str)
        and "image" not in out
        and t != opts.get("text")
    ):
        out["width"] = _fit_width(widget_name, w, t)
    return out


def _fit_width(widget_name, width, text):
    """
    英文按钮/标签的宽度：
    - ttk 控件：负数宽度表示「最少这么宽」，文字多长就按实际像素显示，不会像固定字符宽那样被截断或过度放大；
    - 经典 tk 控件不支持负宽度，按字符数放宽（英文字符比 "0" 窄，按 0.85 估算）。
    """
    need = int(max(len(line) for line in text.split("\n")) * 0.85) + 1
    if need <= width:
        return width
    base = (widget_name or "").lower()
    if base.startswith("ttk::") or (base.startswith("t") and base[1:] in _CHAR_WIDTH_KINDS):
        return -width
    return need


_CHAR_WIDTH_KINDS = ("button", "label", "checkbutton", "radiobutton", "menubutton")


def _is_char_width_widget(widget_name):
    """widget_name 可能是 'ttk::button'、'button' 或 winfo_class 的 'tbutton'。"""
    if not widget_name:
        return False
    base = widget_name.split("::")[-1].lower()
    if base.startswith("t") and base[1:] in _CHAR_WIDTH_KINDS:
        base = base[1:]
    return base in _CHAR_WIDTH_KINDS




# 英文说明文字比中文长很多：单行超过这个字符数的标签自动换行，宽度跟随所在区域
_WRAP_MIN_CHARS = 70
_WRAP_DEFAULT_PX = 640


# 被自动设置了换行的标签：路径 -> 原 wraplength（切回中文时恢复）；已绑定跟随宽度的标签（避免重复绑定）
_AUTO_WRAPPED = {}
_WRAP_BOUND = set()
# 英文模式下被自动放宽过的控件：路径 -> 原始宽度（切回中文时恢复）
_ORIG_WIDTH = {}
# 每个控件文字的中文原文：(路径, "text"/"tab") -> 中文。
# 不同中文可能译成同一个短英文（如「停止」「停止监控」都是 Stop），切回中文时优先用这里的原文。
_SRC = {}


def _remember_src(path, slot, text):
    if isinstance(text, str) and text and len(_SRC) < 50000:
        _SRC[(str(path), slot)] = text


def _en_of(text):
    """不论当前语言，给出 text 的英文译文。"""
    if not isinstance(text, str) or text in _NO_TRANSLATE or not _HAS_CJK_RE.search(text):
        return text
    try:
        return _translate(text)
    except Exception:
        return text


def _source_of(path, slot, raw):
    """取界面上 raw 这段文字的中文原文：优先用记录的原文（确认它确实对应 raw），否则查反向表。"""
    src = _SRC.get((str(path), slot))
    if src is not None and (raw == src or raw == _en_of(src)):
        return src
    return untr(raw)


def _auto_wrap_label(label, text):
    if get_language() != "en" or not isinstance(text, str) or not text:
        return
    if max(len(line) for line in text.split("\n")) <= _WRAP_MIN_CHARS:
        return
    try:
        path = str(label)
        if path not in _AUTO_WRAPPED:
            _AUTO_WRAPPED[path] = label.tk.call(path, "cget", "-wraplength")
        wrap = _WRAP_DEFAULT_PX
        try:
            if label.master.winfo_ismapped() and label.master.winfo_width() - 30 > 200:
                wrap = label.master.winfo_width() - 30
        except Exception:
            pass
        label.configure(wraplength=wrap, justify="left")
        if path in _WRAP_BOUND:
            return
        _WRAP_BOUND.add(path)

        def _on_resize(event, lbl=label, p=path):
            try:
                if p not in _AUTO_WRAPPED:
                    return
                width = int(event.width) - 30
                if width > 200 and lbl.winfo_exists():
                    lbl.configure(wraplength=width)
            except Exception:
                pass

        label.master.bind("<Configure>", _on_resize, add="+")
    except Exception:
        pass


def _remember_width(widget, before, after):
    """记录被自动放宽前的宽度。"""
    try:
        if isinstance(before, dict) and isinstance(after, dict):
            w0, w1 = before.get("width"), after.get("width")
            if isinstance(w0, int) and w0 != w1:
                _ORIG_WIDTH.setdefault(str(widget), w0)
    except Exception:
        pass


def install_tk_hooks():
    """给 tkinter 打补丁；必须在创建 tk.Tk() 之前调用。中文模式下钩子原样放行。"""
    global _hooks_installed
    if _hooks_installed:
        return
    _hooks_installed = True
    _load_dict()

    import tkinter as tk
    from tkinter import ttk
    import tkinter.commondialog as commondialog

    # 1) 所有控件构造参数（tk 与 ttk 都走 BaseWidget.__init__）
    _orig_base_init = tk.BaseWidget.__init__

    def _base_init(self, master, widgetName, cnf={}, kw={}, extra=()):
        cnf0, kw0 = cnf, kw
        cnf = _tr_options(cnf, widgetName)
        kw = _tr_options(kw, widgetName)
        _orig_base_init(self, master, widgetName, cnf, kw, extra)
        _remember_width(self, cnf0, cnf)
        _remember_width(self, kw0, kw)
        for d in (cnf0, kw0):
            if isinstance(d, dict) and isinstance(d.get("text"), str):
                _remember_src(self, "text", d["text"])
        opts = {}
        for d in (cnf, kw):
            if isinstance(d, dict):
                opts.update(d)
        if widgetName in ("label", "ttk::label") and not opts.get("wraplength"):
            _auto_wrap_label(self, opts.get("text"))

    tk.BaseWidget.__init__ = _base_init

    # 2) configure / config / widget["text"] = ...
    _orig_configure = tk.Misc._configure

    def _configure(self, cmd, cnf, kw):
        name = None
        try:
            name = self.winfo_class().lower()
        except Exception:
            pass
        for d in (cnf, kw):
            if isinstance(d, dict) and isinstance(d.get("text"), str):
                _remember_src(self, "text", d["text"])
        if isinstance(cnf, dict):
            cnf0 = cnf
            cnf = _tr_options(cnf, name)
            _remember_width(self, cnf0, cnf)
        if isinstance(kw, dict):
            kw0 = kw
            kw = _tr_options(kw, name)
            _remember_width(self, kw0, kw)
            # 只改文字没改宽度时，按当前宽度判断是否需要放宽
            t = kw.get("text")
            if isinstance(t, str) and "width" not in kw and _is_char_width_widget(name) and get_language() == "en":
                try:
                    w = int(_orig_cget(self, "width") or 0)
                    if w > 0:
                        new_w = _fit_width(name, w, t)
                        if new_w != w:
                            kw["width"] = new_w
                            _ORIG_WIDTH.setdefault(str(self), w)
                except Exception:
                    pass
        result = _orig_configure(self, cmd, cnf, kw)
        if isinstance(kw, dict) and isinstance(kw.get("text"), str) and name in ("label", "tlabel"):
            try:
                if not int(str(_orig_cget(self, "wraplength") or 0).split(".")[0] or 0):
                    _auto_wrap_label(self, kw["text"])
            except Exception:
                pass
        return result

    tk.Misc._configure = _configure

    # 3) cget / widget["text"] 读回时还原中文，保证业务判断不受影响
    _orig_cget = tk.Misc.cget

    def _cget(self, key):
        v = _orig_cget(self, key)
        if key in _TEXT_KEYS:
            return untr(v)
        if key == "values":
            try:
                return _untr_seq(self.tk.splitlist(v)) if isinstance(v, str) else _untr_seq(v)
            except Exception:
                return v
        return v

    tk.Misc.cget = _cget
    tk.Misc.__getitem__ = _cget

    # 4) 窗口标题
    _orig_wm_title = tk.Wm.wm_title

    def _wm_title(self, string=None):
        if string is None:
            return untr(_orig_wm_title(self))
        return _orig_wm_title(self, tr(string, remember=True))

    tk.Wm.wm_title = _wm_title
    tk.Wm.title = _wm_title

    # 5) 菜单
    _orig_menu_add = tk.Menu.add
    _orig_menu_insert = tk.Menu.insert
    _orig_menu_entryconfigure = tk.Menu.entryconfigure
    _orig_menu_entrycget = tk.Menu.entrycget

    def _menu_add(self, itemType, cnf={}, **kw):
        return _orig_menu_add(self, itemType, _tr_options(cnf), **_tr_options(kw))

    def _menu_insert(self, index, itemType, cnf={}, **kw):
        return _orig_menu_insert(self, index, itemType, _tr_options(cnf), **_tr_options(kw))

    def _menu_entryconfigure(self, index, cnf=None, **kw):
        return _orig_menu_entryconfigure(self, index, _tr_options(cnf) if cnf else cnf, **_tr_options(kw))

    def _menu_entrycget(self, index, option):
        v = _orig_menu_entrycget(self, index, option)
        return untr(v) if option in _TEXT_KEYS else v

    tk.Menu.add = _menu_add
    tk.Menu.insert = _menu_insert
    tk.Menu.entryconfigure = _menu_entryconfigure
    tk.Menu.entryconfig = _menu_entryconfigure
    tk.Menu.entrycget = _menu_entrycget

    # 6) Notebook 页签
    _orig_nb_add = ttk.Notebook.add
    _orig_nb_insert = ttk.Notebook.insert
    _orig_nb_tab = ttk.Notebook.tab

    def _nb_add(self, child, **kw):
        _remember_src(child, "tab", kw.get("text"))
        return _orig_nb_add(self, child, **_tr_options(kw))

    def _nb_insert(self, pos, child, **kw):
        _remember_src(child, "tab", kw.get("text"))
        return _orig_nb_insert(self, pos, child, **_tr_options(kw))

    def _nb_tab(self, tab_id, option=None, **kw):
        if isinstance(kw.get("text"), str):
            try:
                _remember_src(self.tabs()[self.index(tab_id)], "tab", kw["text"])
            except Exception:
                pass
        v = _orig_nb_tab(self, tab_id, option, **_tr_options(kw))
        if option in _TEXT_KEYS:
            return untr(v)
        if option is None and isinstance(v, dict) and isinstance(v.get("text"), str):
            v = dict(v)
            v["text"] = untr(v["text"])
        return v

    ttk.Notebook.add = _nb_add
    ttk.Notebook.insert = _nb_insert
    ttk.Notebook.tab = _nb_tab

    # 7) Treeview 表头 / 行
    _orig_tv_heading = ttk.Treeview.heading
    _orig_tv_insert = ttk.Treeview.insert
    _orig_tv_item = ttk.Treeview.item

    def _tv_heading(self, column, option=None, **kw):
        v = _orig_tv_heading(self, column, option, **_tr_options(kw))
        return untr(v) if option == "text" else v

    def _tv_insert(self, parent, index, iid=None, **kw):
        return _orig_tv_insert(self, parent, index, iid, **_tr_options(kw))

    def _tv_item(self, item, option=None, **kw):
        v = _orig_tv_item(self, item, option, **_tr_options(kw))
        if option == "text":
            return untr(v)
        if option == "values":
            return _untr_seq(v)
        if option is None and isinstance(v, dict):
            v = dict(v)
            if isinstance(v.get("text"), str):
                v["text"] = untr(v["text"])
            if "values" in v:
                v["values"] = _untr_seq(v["values"])
        return v

    ttk.Treeview.heading = _tv_heading
    ttk.Treeview.insert = _tv_insert
    ttk.Treeview.item = _tv_item

    # 8) Canvas 上的文字
    _orig_canvas_create = tk.Canvas._create

    def _canvas_create(self, itemType, args, kw):
        if itemType == "text":
            if isinstance(kw, dict):
                kw = _tr_options(kw)
            if args and isinstance(args[-1], dict):
                args = tuple(args[:-1]) + (_tr_options(args[-1]),)
        return _orig_canvas_create(self, itemType, args, kw)

    tk.Canvas._create = _canvas_create

    # 9) Text（运行日志等）/ Listbox
    _orig_text_insert = tk.Text.insert

    def _text_insert(self, index, chars, *args):
        if isinstance(chars, str):
            chars = tr(chars)
        return _orig_text_insert(self, index, chars, *args)

    tk.Text.insert = _text_insert

    _orig_lb_insert = tk.Listbox.insert
    _orig_lb_get = tk.Listbox.get

    def _lb_insert(self, index, *elements):
        return _orig_lb_insert(self, index, *[tr(e, remember=True) if isinstance(e, str) else e for e in elements])

    def _lb_get(self, first, last=None):
        return _untr_seq(_orig_lb_get(self, first, last))

    tk.Listbox.insert = _lb_insert
    tk.Listbox.get = _lb_get

    # 10) StringVar：设置时翻译、读取时还原（状态栏、提示文字、绑定的下拉框等）
    _orig_var_set = tk.Variable.set

    def _var_set(self, value):
        if isinstance(self, tk.StringVar) and isinstance(value, str) and not _looks_like_path(value):
            _remember_src(self._name, "var", value)
            value = tr(value, remember=True)
        return _orig_var_set(self, value)

    tk.Variable.set = _var_set
    tk.Variable.initialize = _var_set

    _orig_sv_get = tk.StringVar.get

    def _sv_get(self):
        return untr(_orig_sv_get(self))

    tk.StringVar.get = _sv_get

    # 11) Combobox.set / Entry.get（含 Combobox）读回时还原
    _orig_cb_set = ttk.Combobox.set

    def _cb_set(self, value):
        return _orig_cb_set(self, tr(value, remember=True) if isinstance(value, str) else value)

    _orig_entry_get = tk.Entry.get

    def _entry_get(self):
        return untr(_orig_entry_get(self))

    tk.Entry.get = _entry_get
    ttk.Combobox.set = _cb_set
    ttk.Combobox.get = _entry_get

    # 12) messagebox / filedialog / colorchooser（都走 commondialog.Dialog.show）
    _orig_dialog_show = commondialog.Dialog.show

    def _dialog_show(self, **options):
        for k, v in options.items():
            self.options[k] = v
        for k in ("title", "message", "detail"):
            v = self.options.get(k)
            if isinstance(v, str):
                self.options[k] = tr(v)
        ft = self.options.get("filetypes")
        if isinstance(ft, (list, tuple)):
            new_ft = []
            for item in ft:
                if isinstance(item, (list, tuple)) and item and isinstance(item[0], str):
                    new_ft.append((tr(item[0]),) + tuple(item[1:]))
                else:
                    new_ft.append(item)
            self.options["filetypes"] = tuple(new_ft)
        return _orig_dialog_show(self)

    commondialog.Dialog.show = _dialog_show


# ---------------------------------------------------------------------------
# 运行中切换语言
# ---------------------------------------------------------------------------
def _relabel(text):
    """把界面上当前显示的文字换成新语言：先还原中文原文，再按当前语言翻译。"""
    if not isinstance(text, str) or not text:
        return text
    return tr(untr(text), remember=True)


def _needs_relabel(raw):
    return isinstance(raw, str) and bool(raw) and (raw in _REVERSE or bool(_HAS_CJK_RE.search(raw)))


def _relabel_widget(w, tkapp, var_names):
    """切换单个控件上的文字（不含日志 Text 的内容）。"""
    path = w._w
    call = tkapp.call
    cls = w.winfo_class()

    # 普通 text 选项（按钮、标签、复选框、分组框……）
    try:
        raw = call(path, "cget", "-text")
    except Exception:
        raw = None
    if isinstance(raw, str) and raw and (_needs_relabel(raw) or (path, "text") in _SRC):
        src = _source_of(path, "text", raw)
        if tr(src) != raw:
            w.configure(text=src)  # 走 configure 钩子：翻译 + 英文时自动放宽宽度
    # 切回中文：恢复被放宽的宽度和原来的换行设置
    if get_language() != "en":
        orig_w = _ORIG_WIDTH.pop(path, None)
        if orig_w is not None:
            try:
                call(path, "configure", "-width", orig_w)
            except Exception:
                pass
        if path in _AUTO_WRAPPED:
            try:
                call(path, "configure", "-wraplength", _AUTO_WRAPPED.pop(path))
            except Exception:
                pass

    # 绑定的变量（状态栏、下拉框当前值等）
    try:
        var = str(call(path, "cget", "-textvariable"))
        if var:
            var_names.add(var)
    except Exception:
        pass

    if cls == "TNotebook":
        for t in tkapp.splitlist(call(path, "tabs")):
            raw = str(call(path, "tab", t, "-text"))
            if raw and (_needs_relabel(raw) or (str(t), "tab") in _SRC):
                new = tr(_source_of(t, "tab", raw), remember=True)
                if new != raw:
                    call(path, "tab", t, "-text", new)
    elif cls == "TCombobox":
        vals = tkapp.splitlist(call(path, "cget", "-values"))
        if any(_needs_relabel(v) for v in vals):
            call(path, "configure", "-values", tuple(_relabel(v) for v in vals))
        if not str(call(path, "cget", "-textvariable")):
            cur = call(path, "get")
            if _needs_relabel(cur):
                call(path, "set", _relabel(cur))
    elif cls == "Treeview":
        cols = ["#0"] + list(tkapp.splitlist(call(path, "cget", "-columns")))
        for c in cols:
            try:
                raw = call(path, "heading", c, "-text")
                if _needs_relabel(raw):
                    call(path, "heading", c, "-text", _relabel(raw))
            except Exception:
                pass
        stack = list(tkapp.splitlist(call(path, "children", "")))
        while stack:
            iid = stack.pop()
            raw = call(path, "item", iid, "-text")
            if _needs_relabel(raw):
                call(path, "item", iid, "-text", _relabel(raw))
            vals = tkapp.splitlist(call(path, "item", iid, "-values"))
            if any(_needs_relabel(v) for v in vals):
                call(path, "item", iid, "-values", tuple(_relabel(v) for v in vals))
            stack.extend(tkapp.splitlist(call(path, "children", iid)))
    elif cls == "Listbox":
        items = tkapp.splitlist(call(path, "get", 0, "end"))
        if any(_needs_relabel(v) for v in items):
            sel = tkapp.splitlist(call(path, "curselection"))
            top = call(path, "yview")
            call(path, "delete", 0, "end")
            if items:
                call(path, "insert", "end", *[_relabel(v) for v in items])
            for i in sel:
                call(path, "selection", "set", i)
            try:
                call(path, "yview", "moveto", tkapp.splitlist(top)[0])
            except Exception:
                pass
    elif cls == "Menu":
        last = call(path, "index", "end")
        if str(last) != "none":
            for i in range(int(last) + 1):
                if str(call(path, "type", i)) in ("command", "cascade", "checkbutton", "radiobutton"):
                    raw = call(path, "entrycget", i, "-label")
                    if _needs_relabel(raw):
                        call(path, "entryconfigure", i, "-label", _relabel(raw))
    elif cls == "Canvas":
        for item in tkapp.splitlist(call(path, "find", "all")):
            if str(call(path, "type", item)) == "text":
                raw = call(path, "itemcget", item, "-text")
                if _needs_relabel(raw):
                    call(path, "itemconfigure", item, "-text", _relabel(raw))

    if str(call("winfo", "toplevel", path)) == path:
        raw = call("wm", "title", path)
        if _needs_relabel(raw):
            call("wm", "title", path, _relabel(raw))


def switch_language(root, lang):
    """
    不重启，立即把整个界面切换成 lang（"zh" / "en"），并保存为下次启动的语言。
    返回 (成功控件数, 失败控件数)。已经输出到日志框的内容保持原语言。
    """
    global _language
    if lang not in SUPPORTED_LANGUAGES:
        return 0, 0
    set_language(lang)
    _language = lang
    if lang == "en":
        _load_dict()

    started = time.time()
    tkapp = root.tk
    ok = failed = 0
    var_names = set()
    stack = [root]
    while stack:
        w = stack.pop()
        try:
            _relabel_widget(w, tkapp, var_names)
            ok += 1
        except Exception as e:
            failed += 1
            if failed <= 5:
                print(f"[i18n] 切换语言时控件 {w} 处理失败: {e}")
        try:
            stack.extend(w.winfo_children())
        except Exception:
            pass

    for name in var_names:
        try:
            raw = tkapp.globalgetvar(name)
            if not isinstance(raw, str) or not raw or _looks_like_path(raw):
                continue
            if _needs_relabel(raw) or (name, "var") in _SRC:
                new = tr(_source_of(name, "var", raw), remember=True)
                if new != raw:
                    tkapp.globalsetvar(name, new)
        except Exception:
            pass

    try:
        root.update_idletasks()
    except Exception:
        pass
    print(f"[i18n] 已切换为 {lang}：{ok} 个控件，失败 {failed}，耗时 {time.time() - started:.2f}s")
    return ok, failed
