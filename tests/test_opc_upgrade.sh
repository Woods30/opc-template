#!/usr/bin/env bash
# 升级（指纹校验 + 整目录覆盖）的沙箱回归。
#
# 跑法：bash tests/test_opc_upgrade.sh
# 全程只动 mktemp 目录与沙箱 HOME/XDG 路径，不碰本机真实实例。
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
mkdir -p "$HOME" "$HERDR_APP_HOME" "$HERDR_CORE_HOME" "$OPC_BIN_DIR"

INST="$WORK/inst"
"$ROOT/bin/opc" install "$INST" t --template "$ROOT" --no-input --skip-smoke >/dev/null 2>&1
check "install 返回 0" "0" "$?"

say "升级场景"

# 1. 正常升级：dry-run 与正式执行都返回 0
"$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --dry-run >/dev/null 2>&1
check "upgrade --dry-run 返回 0" "0" "$?"
"$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --skip-smoke >/dev/null 2>&1
check "upgrade 返回 0" "0" "$?"

# 2. knowledge/ 永不被升级触碰
printf '# 业务事实\n' > "$INST/knowledge/business/custom.md"
before="$(shasum "$INST/knowledge/business/custom.md" | awk '{print $1}')"
"$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --skip-smoke >/dev/null 2>&1
after="$(shasum "$INST/knowledge/business/custom.md" | awk '{print $1}')"
check "升级不动 knowledge/" "$before" "$after"

# 无关脏文件不能被升级提交带上
printf '不相关\n' > "$INST/knowledge/business/unrelated.md"
"$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --skip-smoke >/dev/null 2>&1
if (cd "$INST" && git status --porcelain -- knowledge/business/unrelated.md | grep -q .); then
  ok "升级提交不含无关脏文件"
else
  bad "升级提交带上了无关脏文件"
fi

# 3. 机制文件被本地改过：拒绝并提示，--force-mechanism 覆盖
printf '\n# local tweak\n' >> "$INST/scripts/opc-up.sh"
out="$("$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --skip-smoke 2>&1)"
rc=$?
if [[ "$rc" != "0" ]] && grep -q "本地改过" <<< "$out"; then
  ok "本地改过的机制文件被拒绝"
else
  bad "本地改过的机制文件没有被拒绝（rc=${rc}）"
fi
if grep -q "local tweak" <<< "$out"; then
  ok "拒绝时打印了 diff"
else
  bad "拒绝时没有打印 diff"
fi
"$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --skip-smoke --force-mechanism >/dev/null 2>&1
check "--force-mechanism 覆盖成功" "0" "$?"
if grep -q "local tweak" "$INST/scripts/opc-up.sh"; then
  bad "机制文件没有被模版版本覆盖"
else
  ok "机制文件恢复成模版版本"
fi

# 4. 缺失的骨架会在升级时复活；已有的骨架不被覆盖
rm -f "$INST/README.md"
printf '# 自己写的 README\n' > "$INST/INSTANCE.md"
"$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --skip-smoke >/dev/null 2>&1
expect "缺失的骨架重新物化" test -f "$INST/README.md"
check "已有骨架不被覆盖" "# 自己写的 README" "$(cat "$INST/INSTANCE.md")"

# 5. 注册表记录实例
expect "注册表包含实例" grep -q "$INST" "$OPC_CONFIG_DIR/instances.json"
check "opc ls 列出实例" "1" "$("$ROOT/bin/opc" ls 2>/dev/null | grep -c "^t  ")"

say ""
say "汇总：通过 ${PASS} 项 / 失败 ${FAIL} 项"
[[ "$FAIL" -eq 0 ]]
