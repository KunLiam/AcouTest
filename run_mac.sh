#!/usr/bin/env bash
# macOS 开发运行脚本
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 python3，请先安装 Python 3.8+（https://www.python.org/downloads/）"
  exit 1
fi

if ! command -v adb >/dev/null 2>&1; then
  echo "提示: 未在 PATH 中找到 adb。请安装 Android Platform Tools 并加入 PATH。"
  echo "  brew install --cask android-platform-tools"
fi

if [[ ! -d ".venv" ]]; then
  echo "创建虚拟环境 .venv ..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

pip install -q -r requirements.txt
exec python3 main.py
