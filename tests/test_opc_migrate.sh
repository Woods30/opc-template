#!/usr/bin/env bash
# 旧实例一次性迁移的沙箱回归：删除实例内 UI/种子副本、改指纹模型、清理旧前缀 UI。
#
# 跑法：bash tests/test_opc_migrate.sh
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

say() { printf '%s\n' "$*"; }
ok()  { PASS=$((PASS + 1)); printf '  \033[32m通过\033[0m %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf '  \033[31m失败\033[0m %s\n' "$1"; }
check() { if [[ "$2" == "$3" ]]; then ok "$1"; else bad "$1（期望「$2」，实际「$3」）"; fi; }
expect() { local d="$1"; shift; if "$@" >/dev/null 2>&1; then ok "$d"; else bad "$d"; fi; }

export HOME="$WORK/home"
export XDG_CONFIG_HOME="$WORK/config"
export XDG_DATA_HOME="$WORK/data"
export HERDR_APP_HOME="$WORK/herdr-app"
export HERDR_CORE_HOME="$WORK/herdr-core"
export OPC_CONFIG_DIR="$WORK/config/opc"
export OPC_DATA_DIR="$WORK/data/opc"
export OPC_CACHE_DIR="$WORK/cache/opc"
export OPC_BIN_DIR="$WORK/bin"
export OPC_GIT_NAME="opc-test"
export OPC_GIT_EMAIL="opc-test@example.invalid"
mkdir -p "$HOME" "$HERDR_APP_HOME" "$HERDR_CORE_HOME" "$OPC_BIN_DIR"

INST="$WORK/inst"
"$ROOT/bin/opc" install "$INST" t --template "$ROOT" --no-input --skip-smoke >/dev/null 2>&1
check "install 返回 0" "0" "$?"

say "迁移场景"

# 造出旧结构的残留，并按旧实例的样子提交（干净工作区）
mkdir -p "$INST/layouts" "$INST/mods/t-opc-dashboard" "$INST/seeds/knowledge" \
         "$INST/tools/tests" "$INST/scripts" "$INST/.opc/sync-base/scripts"
printf '{"name":"t"}\n' > "$INST/layouts/t.json"
printf '{"name":"t-opc-dashboard"}\n' > "$INST/mods/t-opc-dashboard/mod.json"
printf '# old seed\n' > "$INST/seeds/knowledge/品牌口径.md"
printf '# old test\n' > "$INST/tools/tests/old.py"
printf '{"version":0}\n' > "$INST/sync-policy.json"
printf '#!/usr/bin/env bash\n' > "$INST/scripts/opc-sync.sh"
printf '#!/usr/bin/env bash\n' > "$INST/scripts/opc-new.sh"
cp "$INST/scripts/opc-up.sh" "$INST/.opc/sync-base/scripts/opc-up.sh"
printf '{"locked":true}\n' > "$INST/template.lock.json"
(
  cd "$INST" || exit 1
  git add -A
  git -c user.name="$OPC_GIT_NAME" -c user.email="$OPC_GIT_EMAIL" \
    commit -m "legacy fixture" >/dev/null 2>&1
)
check "旧结构已提交" "0" "$?"

# 旧前缀的全局 UI 残留
mkdir -p "$HERDR_APP_HOME/mods/t-opc-dashboard"
printf '{"name":"t"}\n' > "$HERDR_APP_HOME/layouts/t.json"
printf '{}\n' > "$HERDR_APP_HOME/mods/t-opc-dashboard/mod.json"

knowledge_before="$(find "$INST/knowledge" -type f -exec shasum {} + | sort | shasum | awk '{print $1}')"

# dry-run 不写任何东西
out="$("$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --dry-run 2>&1)"
rc=$?
check "迁移 --dry-run 返回 0" "0" "$rc"
expect "dry-run 打印实例内删除项" grep -q "实例内删除" <<< "$out"
expect "dry-run 不删除旧结构" test -d "$INST/layouts"
expect "dry-run 不动知识库" test -d "$INST/knowledge"

# 正式迁移
"$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --yes --skip-smoke >/dev/null 2>&1
check "迁移返回 0" "0" "$?"

expect "实例内 layouts/ 已删除" test ! -e "$INST/layouts"
expect "实例内 mods/ 已删除" test ! -e "$INST/mods"
expect "实例内 seeds/ 已删除" test ! -e "$INST/seeds"
expect "tools/tests 已删除" test ! -e "$INST/tools/tests"
expect "sync-policy.json 已删除" test ! -e "$INST/sync-policy.json"
expect "template.lock.json 已删除" test ! -e "$INST/template.lock.json"
expect "旧同步脚本已删除" test ! -e "$INST/scripts/opc-sync.sh"
expect "旧建实例脚本已删除" test ! -e "$INST/scripts/opc-new.sh"
expect "sync-base 已删除" test ! -e "$INST/.opc/sync-base"
expect "新指纹文件已写入" test -f "$INST/.opc/mechanism.json"
expect "旧前缀布局已清理" test ! -e "$HERDR_APP_HOME/layouts/t.json"
expect "旧前缀 mod 已清理" test ! -e "$HERDR_APP_HOME/mods/t-opc-dashboard"
expect "全局 opc 布局已安装" test -f "$HERDR_APP_HOME/layouts/opc.json"

knowledge_after="$(find "$INST/knowledge" -type f -exec shasum {} + | sort | shasum | awk '{print $1}')"
check "knowledge/ 哈希不变" "$knowledge_before" "$knowledge_after"

commits="$(cd "$INST" && git rev-list --count HEAD)"
check "迁移只产生一个提交（安装 + 旧结构 + 迁移）" "3" "$commits"

# 迁移后再次升级走普通指纹路径
"$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --skip-smoke >/dev/null 2>&1
check "迁移后再升级返回 0" "0" "$?"

say ""
say "汇总：通过 ${PASS} 项 / 失败 ${FAIL} 项"
[[ "$FAIL" -eq 0 ]]
