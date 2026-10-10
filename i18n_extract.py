# -*- coding: utf-8 -*-
"""
i18n 维护工具：扫描项目 .py 中的中文字符串片段，检查英文对照表 i18n_en.py 是否缺翻译。

用法：
    python3 i18n_extract.py                 # 打印缺翻译的片段数量和前 50 条
    python3 i18n_extract.py --dump out.json # 导出缺翻译片段 {片段: 示例原句}，便于补译
    python3 i18n_extract.py --all --dump out.json  # 导出全部片段（不管是否已翻译）
    python3 i18n_extract.py --simulate      # 模拟英文模式运行时翻译，列出仍残留中文的片段
    python3 i18n_extract.py --merge new.json # 把补译好的 {片段: English} 合并进 i18n_en.py

片段规则与运行时 i18n.tr() 一致：连续的中文字符 + 中文标点为一个片段，去掉首尾标点。
"""
import ast
import glob
import json
import os
import sys

import re

from i18n import iter_cjk_segments

_HAS_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_HAS_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")

# 不参与界面显示的脚本
SKIP_FILES = {
    "i18n.py",
    "i18n_en.py",
    "i18n_extract.py",
    "convert_icon.py",
    "generate_high_quality_logo.py",
}


def _docstring_nodes(tree):
    """返回所有 docstring 节点 id（docstring 不显示在界面上，跳过）。"""
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            if body and isinstance(body[0], ast.Expr):
                val = body[0].value
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    ids.add(id(val))
    return ids


def _literal_text(node):
    """字符串常量返回原文；f-string 返回把 {表达式} 替换成 {} 后的模板。"""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            else:
                parts.append("{}")
        return "".join(parts)
    return None


def collect_segments(root_dir):
    """扫描 root_dir 下的 .py，返回 {片段: 示例原句}。"""
    found = {}
    for text in collect_literals(root_dir):
        for seg in iter_cjk_segments(text):
            found.setdefault(seg, text[:200])
    return found


def collect_literals(root_dir):
    """扫描 root_dir 下的 .py，返回所有含中文的字符串常量/f-string 模板（不含 docstring）。"""
    found = []
    for path in sorted(glob.glob(os.path.join(root_dir, "*.py"))):
        name = os.path.basename(path)
        if name in SKIP_FILES:
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=name)
        except Exception as e:
            print(f"[i18n_extract] 跳过 {name}: {e}", file=sys.stderr)
            continue
        doc_ids = _docstring_nodes(tree)
        inner_consts = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                for v in node.values:
                    inner_consts.add(id(v))
        for node in ast.walk(tree):
            if id(node) in doc_ids or id(node) in inner_consts:
                continue
            text = _literal_text(node)
            if text and _HAS_CJK_RE.search(text):
                found.append(text)
    return found


def simulate(root_dir):
    """模拟运行时翻译：把占位符换成示例值后翻译，返回 {仍残留的中文片段: 示例原句}。"""
    import i18n

    i18n._language = "en"
    residual = {}
    for text in collect_literals(root_dir):
        sample = text.replace("{}", "X1").replace("%s", "X1").replace("%d", "1")
        out = i18n.tr(sample)
        for m in _HAS_CJK_RUN_RE.finditer(out):
            residual.setdefault(m.group(), text[:200])
    return residual


def merge_translations(root_dir, json_path):
    """把 {中文片段: English} 的 JSON 合并进 i18n_en.py（已有的同名片段会被覆盖）。"""
    from i18n_en import EN

    with open(json_path, "r", encoding="utf-8") as f:
        extra = json.load(f)
    merged = dict(EN)
    for k, v in extra.items():
        k, v = str(k).strip(), str(v).strip()
        if k and v and not _HAS_CJK_RE.search(v):
            merged[k] = v
    path = os.path.join(root_dir, "i18n_en.py")
    with open(path, "r", encoding="utf-8") as f:
        header = f.read().split("EN = {")[0]
    body = [
        f"    {json.dumps(k, ensure_ascii=False)}: {json.dumps(merged[k], ensure_ascii=False)},"
        for k in sorted(merged, key=lambda s: (len(s), s))
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + "EN = {\n" + "\n".join(body) + "\n}\n")
    print(f"[i18n_extract] 已合并 {len(extra)} 条，对照表共 {len(merged)} 条")


def main(argv):
    root_dir = os.path.dirname(os.path.abspath(__file__))
    if "--merge" in argv:
        merge_translations(root_dir, argv[argv.index("--merge") + 1])
        return 0
    segs = collect_segments(root_dir)
    try:
        from i18n_en import EN
    except Exception:
        EN = {}
    want_all = "--all" in argv
    todo = segs if want_all else {k: v for k, v in segs.items() if k not in EN}
    if "--simulate" in argv:
        todo = simulate(root_dir)
        print(f"[i18n_extract] 模拟翻译后仍残留中文的片段 {len(todo)} 个")
    print(f"[i18n_extract] 片段总数 {len(segs)}，已翻译 {len(segs) - len([k for k in segs if k not in EN])}，缺翻译 {len([k for k in segs if k not in EN])}")
    if "--dump" in argv:
        out = argv[argv.index("--dump") + 1]
        with open(out, "w", encoding="utf-8") as f:
            json.dump(todo, f, ensure_ascii=False, indent=1)
        print(f"[i18n_extract] 已导出 {len(todo)} 条到 {out}")
    else:
        for k in list(todo)[:50]:
            print(f"  {k}    <- {todo[k]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
