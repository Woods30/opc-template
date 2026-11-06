#!/usr/bin/env bash
# 模版自检（薄包装）：核心规则在 tools/opc-lint（Python）。
# 用法：scripts/opc-lint.sh [--root DIR] [--private-words FILE] [--json] [--quiet] [--strict]
# 退出码：0 通过；1 有违规；2 用法/环境错
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"

# 在模版仓库里跑 template/scripts/opc-lint.sh 时，仓库根是 payload 的上一级；
# 在实例里跑时，实例根就是本目录。
if [[ "$(basename "$ROOT")" == "template" && -f "$ROOT/install-manifest.json" ]]; then
  TOOL="$ROOT/tools/opc-lint"
  ROOT="$(cd "$ROOT/.." && pwd)"
else
  TOOL="$ROOT/tools/opc-lint"
fi

command -v python3 >/dev/null || { echo "缺少 python3" >&2; exit 2; }
[[ -f "$TOOL" ]] || { echo "缺少 tools/opc-lint" >&2; exit 2; }

exec python3 "$TOOL" --root "$ROOT" "$@"
