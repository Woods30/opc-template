#!/usr/bin/env bash
# opc-sync 的场景回归测试。纯 bash，不依赖外部框架。
#
# 跑法：
#   bash tools/tests/test_opc_sync.sh
#
# 覆盖：模版更新覆盖 / 实例本地改动保留 / 双改冲突 / pin / 种子自动升级 /
#       种子需人工合并 / 配置按 key 并集 / 模版仓库守卫
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TEMPLATE="$ROOT"
PASS=0
FAIL=0

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

say()  { printf '%s\n' "$*"; }
ok()   { PASS=$((PASS + 1)); printf '  \033[32m通过\033[0m %s\n' "$1"; }
bad()  { FAIL=$((FAIL + 1)); printf '  \033[31m失败\033[0m %s\n' "$1"; }
check() { # check <描述> <期望> <实际>
  if [[ "$2" == "$3" ]]; then ok "$1"; else bad "$1（期望「$2」，实际「$3」）"; fi
}

# 造一个模版副本与一个实例
TPL="$WORK/tpl"
INST="$WORK/inst"
cp -R "$TEMPLATE" "$TPL"
rm -rf "$TPL/.git" "$TPL/.opc"
"$TPL/scripts/opc-new.sh" "$INST" --prefix t --source "$TPL" --no-install >/dev/null 2>&1
cd "$INST" || exit 1
scripts/opc-sync.sh pull --from "$TPL" --no-install >/dev/null 2>&1

say "opc-sync 场景测试"

# ---- 1. 模版更新 → 实例被覆盖 ----
printf '\n模版新增的一节。\n' >> "$TPL/AGENTS.md"
out="$(scripts/opc-sync.sh check --from "$TPL" 2>&1 | grep -c 'update.*AGENTS.md')"
check "模版改动被检出" "1" "$out"
scripts/opc-sync.sh pull --from "$TPL" --no-install >/dev/null 2>&1
grep -q "模版新增的一节" AGENTS.md && ok "拉取后实例拿到模版内容" || bad "拉取后实例没拿到模版内容"

# ---- 2. 实例本地改动 → 保留，不被覆盖 ----
printf '\n实例本地加的。\n' >> AGENTS.md
git -C "$INST" add -A >/dev/null 2>&1
git -C "$INST" commit -q -m "本地改动" >/dev/null 2>&1
scripts/opc-sync.sh pull --from "$TPL" --no-install >/dev/null 2>&1
grep -q "实例本地加的" AGENTS.md && ok "本地改动没有被覆盖" || bad "本地改动被覆盖了"

# ---- 3. 双改 → 冲突，业务文件不动 ----
printf '\n模版又加的。\n' >> "$TPL/AGENTS.md"
scripts/opc-sync.sh pull --from "$TPL" --no-install >/dev/null 2>&1
rc=$?
check "双改时报冲突（退出码 3）" "3" "$rc"
grep -q "实例本地加的" AGENTS.md && ok "冲突时业务文件未被改动" || bad "冲突时业务文件被改了"
[[ -f "$INST/.opc/sync-conflicts/AGENTS.md.merge" ]] && ok "冲突产物已生成" || bad "没有冲突产物"

# ---- 4. pin → 模版不再覆盖 ----
scripts/opc-sync.sh mark AGENTS.md >/dev/null 2>&1
scripts/opc-sync.sh pull --from "$TPL" --no-install >/dev/null 2>&1
grep -q "模版又加的" AGENTS.md && bad "pin 之后仍被覆盖" || ok "pin 之后不被覆盖"

# ---- 5. 种子：业务没动 → 自动升级 ----
printf '\n骨架改进：加一行说明。\n' >> "$TPL/seeds/knowledge/business/品牌口径.md"
scripts/opc-sync.sh pull --from "$TPL" --no-install >/dev/null 2>&1
grep -q "骨架改进" "$INST/knowledge/business/品牌口径.md" && ok "业务没动过时种子自动升级" || bad "种子没有自动升级"

# ---- 6. 种子：业务改过 → 不动，只提示 ----
printf '\n业务自己写的真实内容。\n' >> "$INST/knowledge/business/品牌口径.md"
git -C "$INST" add -A >/dev/null 2>&1
git -C "$INST" commit -q -m "业务定稿" >/dev/null 2>&1
printf '\n骨架再改进一次。\n' >> "$TPL/seeds/knowledge/business/品牌口径.md"
scripts/opc-sync.sh pull --from "$TPL" --no-install >/dev/null 2>&1
grep -q "业务自己写的真实内容" "$INST/knowledge/business/品牌口径.md" && ok "业务定稿没有被骨架覆盖" || bad "业务定稿被骨架覆盖了"
grep -q "骨架再改进一次" "$INST/knowledge/business/品牌口径.md" && bad "业务定稿被骨架改进污染了" || ok "骨架改进没有硬写进业务文件"

# ---- 7. 配置按 key 并集：模版新增角色 → 实例并入且默认停用 ----
jq '.roles += [{"name":"researcher","enabled":true,"cli":"claude","template":"agents/opc-researcher.md","permissionMode":"default","scope":["knowledge/work/researcher"]}]' \
  "$TPL/roles.json" > "$TPL/roles.json.tmp" && mv "$TPL/roles.json.tmp" "$TPL/roles.json"
scripts/opc-sync.sh pull --from "$TPL" --no-install >/dev/null 2>&1
merged="$(jq -r '[.roles[] | select(.name=="researcher") | .enabled] | if length == 0 then "absent" else (.[0] | tostring) end' "$INST/roles.json")"
check "模版新增角色并入实例" "false" "$merged"

# ---- 8. 实例自有配置不被改 ----
jq '.roles[0].permissionMode = "dontAsk"' "$INST/roles.json" > "$INST/roles.json.tmp" && mv "$INST/roles.json.tmp" "$INST/roles.json"
scripts/opc-sync.sh pull --from "$TPL" --no-install >/dev/null 2>&1
mode="$(jq -r '.roles[0].permissionMode' "$INST/roles.json")"
check "实例的 permissionMode 不被模版改掉" "dontAsk" "$mode"

# ---- 9. 模版仓库守卫：在模版里跑同步会被拒 ----
out="$(cd "$TPL" && scripts/opc-sync.sh check 2>&1)"
rc=$?
if [[ "$rc" == "2" ]] && echo "$out" | grep -q "模版仓库"; then
  ok "在模版仓库里跑同步被拒绝"
else
  bad "在模版仓库里跑同步没有被拒绝（退出码 ${rc}）"
fi

# ---- 10. 实例业务数据不被同步触碰 ----
mkdir -p "$INST/knowledge/business/private"
printf '私房话。\n' > "$INST/knowledge/business/private/秘密.md"
scripts/opc-sync.sh pull --from "$TPL" --no-install >/dev/null 2>&1
[[ -f "$INST/knowledge/business/private/秘密.md" ]] && ok "实例自有业务文件不受影响" || bad "实例业务文件被动了"

# ---- 11. --accept-template：本地改过的文件按点名采用模版版本 ----
scripts/opc-sync.sh mark AGENTS.md --unmark >/dev/null 2>&1
printf '\n实例还想保留的一句。\n' >> AGENTS.md
git -C "$INST" add -A >/dev/null 2>&1
git -C "$INST" commit -q -m "本地又改" >/dev/null 2>&1
scripts/opc-sync.sh pull --from "$TPL" --no-install >/dev/null 2>&1
grep -q "实例还想保留的一句" AGENTS.md && ok "默认不覆盖本地改动" || bad "默认覆盖了本地改动"
scripts/opc-sync.sh pull --from "$TPL" --no-install --accept-template AGENTS.md >/dev/null 2>&1
grep -q "实例还想保留的一句" AGENTS.md && bad "--accept-template 没有采用模版版本" || ok "--accept-template 采用模版版本"

# ---- 12. 策略里的路径越界 → 拒绝同步 ----
cp "$TPL/sync-policy.json" "$WORK/policy.bak"
jq '.seeds += [{"source":"seeds/../../escape.md","target":"../escape.md"}]' \
  "$TPL/sync-policy.json" > "$TPL/sync-policy.json.tmp" && mv "$TPL/sync-policy.json.tmp" "$TPL/sync-policy.json"
out="$(scripts/opc-sync.sh check --from "$TPL" 2>&1)"
rc=$?
if [[ "$rc" == "2" ]] && echo "$out" | grep -q "越界"; then
  ok "策略里的路径越界被拒绝"
else
  bad "策略里的路径越界没有被拒绝（退出码 ${rc}）"
fi
cp "$WORK/policy.bak" "$TPL/sync-policy.json"

# ---- 13. 同步脚本自身：本轮暂存，下次运行生效 ----
printf '\n# 模版对同步脚本的改动\n' >> "$TPL/scripts/opc-sync.sh"
out="$(scripts/opc-sync.sh pull --from "$TPL" --no-install 2>&1)"
echo "$out" | grep -q "deferred scripts/opc-sync.sh" && ok "同步脚本本轮不覆盖，改为暂存" || bad "同步脚本没有被识别为 deferred"
[[ -f "$INST/.opc/sync-stage/scripts/opc-sync.sh" ]] && ok "新版已落到暂存区" || bad "暂存区没有新版"
scripts/opc-sync.sh status --from "$TPL" >/dev/null 2>&1
grep -q "模版对同步脚本的改动" scripts/opc-sync.sh && ok "下次运行自动替换为新版" || bad "下次运行没有替换"
[[ -f "$INST/.opc/sync-stage/scripts/opc-sync.sh" ]] && bad "暂存区没有清理" || ok "暂存区已清理"

say ""
say "通过 $PASS 项 / 失败 $FAIL 项"
[[ "$FAIL" == "0" ]] || exit 1
