#!/usr/bin/env bash
# PyInstaller 产物：Developer ID 签名 + 苹果公证 + 装订
#
# 用法 1（App 专用密码，appleid.apple.com 生成）：
#   export APPLE_ID="xxx@company.com"
#   export APPLE_APP_PASSWORD="abcd-efgh-ijkl-mnop"
#   export APPLE_TEAM_ID="48JD48NR6W"
#   ./macos_sign_notarize.sh dist/AcouTest.v2.1.5.app
#
# 用法 2（App Store Connect API Key，无需 App 专用密码）：
#   export NOTARY_API_KEY_PATH="$HOME/AuthKey_XXXX.p8"
#   export NOTARY_API_KEY_ID="XXXX"
#   export NOTARY_API_ISSUER="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
#   ./macos_sign_notarize.sh
#
# APPLE_DEVELOPER_ID 可省略，脚本会自动从钥匙串读取 Developer ID Application 证书。

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "[notarize] 仅支持 macOS。"
  exit 1
fi

detect_developer_id() {
  if [[ -n "${APPLE_DEVELOPER_ID:-}" ]]; then
    echo "$APPLE_DEVELOPER_ID"
    return
  fi
  security find-identity -v -p codesigning 2>/dev/null \
    | awk -F'"' '/Developer ID Application:/{print $2; exit}'
}

resolve_app_path() {
  local arg="${1:-}"
  if [[ -n "$arg" ]]; then
    echo "$arg"
    return
  fi
  local latest=""
  local d
  for d in dist/AcouTest.v*.app; do
    [[ -d "$d" ]] || continue
    latest="$d"
  done
  echo "$latest"
}

APP_PATH="$(resolve_app_path "${1:-}")"
if [[ -z "$APP_PATH" || ! -d "$APP_PATH" ]]; then
  echo "[notarize] 未找到 .app，请先 ./Packager.sh"
  exit 1
fi

APPLE_DEVELOPER_ID="$(detect_developer_id)"
if [[ -z "$APPLE_DEVELOPER_ID" ]]; then
  echo "[notarize] 未找到 Developer ID Application 证书。请在 Xcode → Settings → Accounts 创建。"
  exit 1
fi

HAS_APP_PW=0
HAS_API_KEY=0
[[ -n "${APPLE_APP_PASSWORD:-}" && -n "${APPLE_ID:-}" && -n "${APPLE_TEAM_ID:-}" ]] && HAS_APP_PW=1
[[ -n "${NOTARY_API_KEY_PATH:-}" && -n "${NOTARY_API_KEY_ID:-}" && -n "${NOTARY_API_ISSUER:-}" ]] && HAS_API_KEY=1
if [[ "$HAS_APP_PW" -eq 0 && "$HAS_API_KEY" -eq 0 ]]; then
  echo "[notarize] 请设置公证凭据："
  echo "  App 专用密码: APPLE_ID + APPLE_APP_PASSWORD + APPLE_TEAM_ID"
  echo "  或 API Key: NOTARY_API_KEY_PATH + NOTARY_API_KEY_ID + NOTARY_API_ISSUER"
  exit 1
fi

APP_PATH="$(cd "$(dirname "$APP_PATH")" && pwd)/$(basename "$APP_PATH")"
APP_NAME="$(basename "$APP_PATH")"
ZIP_PATH="${TMPDIR:-/tmp}/${APP_NAME%.app}_notarize.zip"

echo "[notarize] App: $APP_PATH"
echo "[notarize] Sign: $APPLE_DEVELOPER_ID"
echo "[notarize] 1/4 签名..."

sign_file() {
  codesign --force --options runtime --timestamp --sign "$APPLE_DEVELOPER_ID" "$1"
}

if [[ -d "$APP_PATH/Contents/Frameworks" ]]; then
  while IFS= read -r -d '' f; do
    sign_file "$f" 2>/dev/null || true
  done < <(find "$APP_PATH/Contents/Frameworks" -type f \( -name '*.dylib' -o -name '*.so' -o -perm -111 \) -print0 2>/dev/null || true)
fi
if [[ -d "$APP_PATH/Contents/MacOS" ]]; then
  while IFS= read -r -d '' f; do
    [[ -f "$f" && -x "$f" ]] && sign_file "$f"
  done < <(find "$APP_PATH/Contents/MacOS" -type f -print0)
fi
sign_file "$APP_PATH"

codesign --verify --deep --strict --verbose=2 "$APP_PATH"

echo "[notarize] 2/4 打包 zip..."
rm -f "$ZIP_PATH"
ditto -c -k --keepParent "$APP_PATH" "$ZIP_PATH"

echo "[notarize] 3/4 提交公证（可能需数分钟）..."
if [[ "$HAS_API_KEY" -eq 1 ]]; then
  xcrun notarytool submit "$ZIP_PATH" \
    --key "$NOTARY_API_KEY_PATH" \
    --key-id "$NOTARY_API_KEY_ID" \
    --issuer "$NOTARY_API_ISSUER" \
    --wait
else
  xcrun notarytool submit "$ZIP_PATH" \
    --apple-id "$APPLE_ID" \
    --password "$APPLE_APP_PASSWORD" \
    --team-id "$APPLE_TEAM_ID" \
    --wait
fi

echo "[notarize] 4/4 装订票据..."
xcrun stapler staple "$APP_PATH"
xcrun stapler validate "$APP_PATH"

rm -f "$ZIP_PATH"
echo "[notarize] 完成: $APP_NAME（可 zip dist 目录发给用户）"
