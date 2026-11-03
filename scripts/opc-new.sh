#!/usr/bin/env bash
# 用本模版开一个新 OPC 实例：复制骨架到目标目录，安装模板并写入前缀。
# 用法：scripts/opc-new.sh <目标目录> [前缀]
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

SRC="$(opc_root)"
TARGET_ARG="${1:-}"
[[ -n "$TARGET_ARG" ]] || { echo "用法：scripts/opc-new.sh <目标目录> [前缀]" >&2; exit 1; }

mkdir -p "$TARGET_ARG"
TARGET="$(cd "$TARGET_ARG" && pwd)"
PREFIX="${2:-$(basename "$TARGET" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]/-/g')}"

[[ "$TARGET" != "$SRC" ]] || { echo "目标就是模版自身，直接跑 opc-install.sh 即可。" >&2; exit 1; }
case "$TARGET/" in
  "$SRC/"*) echo "目标不能放在模版目录内部：$TARGET" >&2; exit 1 ;;
esac
[[ -z "$(ls -A "$TARGET")" ]] || { echo "目标目录非空：$TARGET" >&2; exit 1; }

rsync -a --exclude '.git' --exclude '.opc' "$SRC/" "$TARGET/"
"$TARGET/scripts/opc-install.sh" "$PREFIX"

echo
echo "新实例已建好：$TARGET"
echo "  cd \"$TARGET\" && scripts/opc-up.sh"
