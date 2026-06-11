#!/usr/bin/env bash
# macOS 打包脚本（与 Packager.bat 逻辑对应）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-}"
FULL_RESYNC="${PACKAGER_FULL_RESYNC:-0}"
USE_ONEDIR="${PACKAGER_ONEDIR:-0}"

# macOS：优先 Homebrew Python + Tcl/Tk 9.x 打包，避免系统 Tcl/Tk 8.5 导致 ttk 空白窗
setup_packager_python() {
  if [[ -n "${PYTHON:-}" ]]; then
    return
  fi
  if [[ "$(uname -s)" != "Darwin" ]]; then
    PYTHON="python3"
    return
  fi

  local hb_py=""
  if [[ -x "/opt/homebrew/opt/python@3.12/bin/python3.12" ]]; then
    hb_py="/opt/homebrew/opt/python@3.12/bin/python3.12"
  elif command -v brew >/dev/null 2>&1; then
    if ! brew list python@3.12 >/dev/null 2>&1; then
      echo "[Packager] Installing Homebrew python@3.12 (fixes macOS blank Tk window)..."
      brew install python@3.12 || true
    fi
    if ! brew list python-tk@3.12 >/dev/null 2>&1; then
      echo "[Packager] Installing Homebrew python-tk@3.12..."
      brew install python-tk@3.12 || true
    fi
    hb_py="$(brew --prefix python@3.12 2>/dev/null)/bin/python3.12"
    if [[ ! -x "$hb_py" ]]; then
      hb_py=""
    fi
  fi

  if [[ -n "$hb_py" ]]; then
    local venv="$ROOT/.packager-venv"
    if [[ ! -x "$venv/bin/python" ]]; then
      echo "[Packager] Creating packager venv with Homebrew Python..."
      "$hb_py" -m venv "$venv"
      "$venv/bin/pip" install -U pip
      "$venv/bin/pip" install -r requirements.txt pyinstaller pillow pygame certifi
    fi
    PYTHON="$venv/bin/python"
    echo "[Packager] Using Homebrew Python venv: $PYTHON"
    return
  fi

  PYTHON="python3"
  echo "[Packager] WARN: Homebrew Python not found; using $PYTHON (may show blank window on macOS)."
}

setup_packager_python

echo "[Packager] Building standalone executable (macOS)..."

if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "[ERROR] Python not found. Install Python 3.8+ or set PYTHON=..."
  exit 1
fi

"$PYTHON" -c "import PyInstaller" 2>/dev/null || {
  echo "[Packager] Installing PyInstaller..."
  "$PYTHON" -m pip install pyinstaller
}

"$PYTHON" -c "import PIL" 2>/dev/null || "$PYTHON" -m pip install pillow
"$PYTHON" -c "import pygame" 2>/dev/null || "$PYTHON" -m pip install pygame
"$PYTHON" -c "import certifi" 2>/dev/null || "$PYTHON" -m pip install certifi

echo "[Packager] Installing app dependencies (requirements.txt)..."
"$PYTHON" -m pip install -r requirements.txt pyinstaller 2>/dev/null || "$PYTHON" -m pip install -r requirements.txt

VER="$("$PYTHON" -c "from feature_config import APP_VERSION; print(APP_VERSION)" 2>/dev/null || echo "1.0")"
APP_NAME="AcouTest.v${VER}"
SPEC_FILE="${APP_NAME}.spec"

# macOS 默认 onedir；若仍空白可试 PACKAGER_CONSOLE=1 生成带终端的诊断版
if [[ "$(uname -s)" == "Darwin" && "$USE_ONEDIR" != "1" ]]; then
  USE_ONEDIR=1
  echo "[Packager] macOS defaults to onedir mode (PACKAGER_ONEDIR=1)."
fi
USE_CONSOLE="${PACKAGER_CONSOLE:-0}"
PI_WINDOW=()
if [[ "$USE_CONSOLE" == "1" ]]; then
  PI_WINDOW=(--console)
  echo "[Packager] Mode: console (PACKAGER_CONSOLE=1)"
elif [[ "${PACKAGER_WINDOWED:-0}" == "1" ]]; then
  PI_WINDOW=(--windowed)
  echo "[Packager] Mode: windowed .app (PACKAGER_WINDOWED=1)"
else
  echo "[Packager] Mode: onedir binary (no .app bundle, avoids Tk blank window on macOS)"
fi

if [[ "$USE_ONEDIR" == "1" ]]; then
  PI_MODE=(--onedir)
  DIST_BIN="dist/${APP_NAME}/${APP_NAME}"
else
  PI_MODE=(--onefile)
  DIST_BIN="dist/${APP_NAME}"
fi

echo "[Packager] Version: ${VER}  Output: ${APP_NAME}"
if [[ "$USE_ONEDIR" == "1" ]]; then
  echo "[Packager] Mode: onedir"
else
  echo "[Packager] Mode: onefile"
fi

echo "[Packager] Stopping running app instances if any..."
pkill -f "${APP_NAME}" 2>/dev/null || true

echo "[Packager] Cleaning old build artifacts..."
rm -f "dist/${APP_NAME}" "dist/${APP_NAME}.app" 2>/dev/null || true
rm -rf "dist/${APP_NAME}" "dist/${APP_NAME}.app" build "${SPEC_FILE}" 2>/dev/null || true
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find . -name '*.pyc' -delete 2>/dev/null || true

echo "[Packager] Generating logo + macOS rounded icon..."
"$PYTHON" -c "from generate_high_quality_logo import create_high_quality_logo; create_high_quality_logo()"

# generate_high_quality_logo 内部已调用 convert_icon；此处再执行一次确保 .icns 最新
echo "[Packager] Converting icon..."
"$PYTHON" convert_icon.py

ICON_ARG=()
if [[ "$(uname -s)" == "Darwin" ]]; then
  if [[ -f "logo/AcouTest.icns" ]]; then
    ICON_ARG=(--icon="logo/AcouTest.icns")
    echo "[Packager] Using macOS icon: logo/AcouTest.icns"
  else
    echo "[Packager] WARN: logo/AcouTest.icns missing; Dock icon may look square."
  fi
elif [[ -f "logo/AcouTest.ico" ]]; then
  ICON_ARG=(--icon="logo/AcouTest.ico")
fi

mkdir -p dist

echo "[Packager] Running PyInstaller..."
PI_EXCLUDE=$("$PYTHON" "$ROOT/pack_pyinstaller_excludes.py")
PI_HIDDEN=(
  --hidden-import certifi
  --hidden-import updater_http
  --hidden-import generate_wake_word
  --hidden-import platform_utils
  --hidden-import PIL.ImageTk
  --hidden-import edge_tts
  --hidden-import edge_tts.exceptions
  --hidden-import asyncio
  --hidden-import aiohttp
)
# Windows / 开发机若打包进 imageio_ffmpeg，语料生成无需系统 ffmpeg
if [[ "$(uname -s)" != "Darwin" ]]; then
  PI_HIDDEN+=(--hidden-import imageio_ffmpeg)
fi
"$PYTHON" -m PyInstaller --clean --noupx ${PI_WINDOW[@]+"${PI_WINDOW[@]}"} "${PI_MODE[@]}" ${ICON_ARG[@]+"${ICON_ARG[@]}"} \
  --add-data "logo:logo" \
  "${PI_HIDDEN[@]}" \
  $PI_EXCLUDE \
  --name "${APP_NAME}" \
  main.py

# PyInstaller 产物：优先 onedir 可执行文件（macOS 避免 .app 空白窗）
if [[ -f "dist/${APP_NAME}/${APP_NAME}" ]]; then
  DIST_BIN="dist/${APP_NAME}/${APP_NAME}"
elif [[ -d "dist/${APP_NAME}.app" ]]; then
  DIST_BIN="dist/${APP_NAME}.app"
elif [[ -f "dist/${APP_NAME}" ]]; then
  DIST_BIN="dist/${APP_NAME}"
fi

if [[ ! -e "$DIST_BIN" ]]; then
  echo "[ERROR] Build failed. Expected output not found: ${DIST_BIN}"
  ls -la dist/ 2>/dev/null || true
  exit 1
fi

echo "[Packager] Build OK: ${DIST_BIN}"
echo "[Packager] Syncing dist resources..."

sync_dir() {
  local src="$1"
  local dst="$2"
  if [[ ! -d "$src" ]]; then
    echo "[WARN] ${src} folder not found."
    return
  fi
  echo "[Packager] Sync ${src}..."
  mkdir -p "$dst"
  if [[ "$FULL_RESYNC" == "1" ]]; then
    rsync -a --delete "${src}/" "${dst}/"
  else
    rsync -a "${src}/" "${dst}/"
  fi
}

sync_dir logo dist/logo
sync_dir audio dist/audio

mkdir -p dist/output/{logcat,screenshots,mic_test,sweep_recordings,airtightness,loopback,hal_dump,hal_custom}
"$PYTHON" pack_dist_client_files.py || true

sync_dir elevoc_ukey dist/elevoc_ukey
sync_dir wakeup_count dist/wakeup_count

echo "[Packager] Done. dist is ready to zip for delivery."
echo "[Packager] macOS: program is inside dist/${APP_NAME}.app (double-click to run)"
echo "[Packager] Also zip audio/, output/, etc. next to the .app for full features."
echo "[Packager] Or: ./dist/启动测试工具.command"
