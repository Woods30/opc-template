#!/usr/bin/env bash
# 模版自检（薄包装）：核心规则在 tools/opc-lint（Python）。
# 用法：scripts/opc-lint.sh [--root DIR] [--private-words FILE] [--json] [--quiet] [--strict]
# 退出码：0 通过；1 有违规；2 用法/环境错
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

command -v python3 >/dev/null || { echo "缺少 python3" >&2; exit 2; }
[[ -f "$ROOT/tools/opc-lint" ]] || { echo "缺少 tools/opc-lint" >&2; exit 2; }

exec python3 "$ROOT/tools/opc-lint" --root "$ROOT" "$@"
