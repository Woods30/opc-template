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
# Hosted runner 没有全局 git identity；后续场景要提交本地改动，测试仓库自己
# 提供固定身份，不依赖开发机 ~/.gitconfig 或 Git 对系统账号的猜测。
git -C "$INST" config user.name "OPC Sync Test"
git -C "$INST" config user.email "opc-sync-test@example.invalid"
git -C "$INST" config user.useConfigOnly true
cd "$INST" || exit 1
scripts/opc-sync.sh pull --from "$TPL" --no-install >/dev/null 2>&1

say "opc-sync 场景测试"

check "模版内所有 agent 默认 bypassPermissions" "bypassPermissions" \
  "$(jq -r '[.roles[] | select(.enabled) | .permissionMode] | unique | join(",")' "$INST/roles.json")"

# ---- 0. 技能只放行 owner 逐个批准的，不放行裸 Skill ----
# 技能 frontmatter 的 allowed-tools 会在调用那一轮临时预授权工具，
# 裸 Skill 等于把角色的工具面交给任意技能，所以只放行精确的 Skill(名字)。
jq '(.roles[] | select(.name == "gm") | .permissionMode) = "dontAsk"
  | (.roles[] | select(.name == "gm") | .approvedSkills) = ["humanizer-zh"]' \
  "$INST/roles.json" > "$INST/roles.json.tmp" && mv "$INST/roles.json.tmp" "$INST/roles.json"
XDG_CONFIG_HOME="$WORK/config" "$INST/scripts/opc-install.sh" t >/dev/null 2>&1
check "批准的技能生成精确规则" "Skill(humanizer-zh)" \
  "$(jq -r '.permissions.allow[] | select(. == "Skill(humanizer-zh)")' "$INST/.opc/settings-gm.json")"
if jq -e '.permissions.allow | index("Skill")' "$INST/.opc/settings-gm.json" >/dev/null; then
  bad "白名单里出现了裸 Skill 规则"
else
  ok "白名单里没有裸 Skill 规则"
fi

jq '.channels = [{"id":"wechat","name":"公众号","enabled":true}]' \
  "$INST/channels.json" > "$INST/channels.json.tmp" && mv "$INST/channels.json.tmp" "$INST/channels.json"
XDG_CONFIG_HOME="$WORK/config" "$INST/scripts/opc-install.sh" t >/dev/null 2>&1
if grep -q 'GENERATED FILE — READ ONLY' "$INST/knowledge/business/wechat/发布记录.md"; then
  ok "安装器创建的渠道发布记录可由 workflow 安全接管"
else
  bad "安装器仍创建手工维护格式的渠道发布记录"
fi
jq '.channels = []' "$INST/channels.json" > "$INST/channels.json.tmp" && \
  mv "$INST/channels.json.tmp" "$INST/channels.json"

# ---- 看板：mod 装进 herdr 配置目录，布局里的实例路径按实例替换 ----
# 看板是独立面板，不改现有布局的安装与切换行为。
if [[ -f "$WORK/config/herdr-app/mods/t-opc-dashboard/main.js" \
   && -f "$WORK/config/herdr-app/mods/t-opc-dashboard/model.js" \
   && -f "$WORK/config/herdr-app/mods/t-opc-dashboard/mod.json" ]]; then
  ok "看板 mod 装进 herdr 配置目录"
else
  bad "看板 mod 没有装进 herdr 配置目录"
fi
check "看板布局按实例替换实例目录" "$INST" \
  "$(jq -r '.children[] | select(.id=="dashboard") | .content.props.instance' \
     "$WORK/config/herdr-app/layouts/t-opc-dashboard.json" 2>/dev/null)"
check "看板布局指向本实例的 mod" "t-opc-dashboard" \
  "$(jq -r '.children[] | select(.id=="dashboard") | .content.mod' \
     "$WORK/config/herdr-app/layouts/t-opc-dashboard.json" 2>/dev/null)"
# 主布局 layouts/opc.json 装成 <前缀>.json，其余装成 <前缀>-<名字>.json。
if [[ -f "$WORK/config/herdr-app/layouts/t.json" \
   && -f "$WORK/config/herdr-app/layouts/t-grid.json" ]]; then
  ok "既有布局的安装与切换行为没有被看板影响"
else
  bad "看板安装把既有布局弄丢了"
fi
if grep -qF '{{' "$WORK/config/herdr-app/layouts/t-opc-dashboard.json" 2>/dev/null; then
  bad "看板布局里还留着没替换的占位"
else
  ok "看板布局里没有没替换的占位"
fi

# 没装 Herdr 时安装器要说清楚，而不是失败或装出个坏面板。
mkdir -p "$WORK/bin"
for cmd in jq python3 git bash sed grep cp mkdir rm chmod cat basename dirname tr; do
  real="$(command -v "$cmd" 2>/dev/null || true)"
  [[ -n "$real" ]] && ln -sf "$real" "$WORK/bin/$cmd"
done
no_herdr_out="$(PATH="$WORK/bin:/usr/bin:/bin" XDG_CONFIG_HOME="$WORK/config" \
  "$INST/scripts/opc-install.sh" t 2>&1)"
no_herdr_code=$?
if [[ "$no_herdr_code" -eq 0 ]] && grep -q "没找到 herdr-app" <<< "$no_herdr_out"; then
  ok "没装 Herdr 时安装器给出清楚结果且不失败"
else
  bad "没装 Herdr 时安装器没说清楚或直接失败"
fi
if [[ -f "$INST/knowledge/business/选题日历.md" ]]; then
  ok "没装 Herdr 时第一阶段的种子与视图照常物化"
else
  bad "没装 Herdr 时第一阶段的种子与视图没了"
fi

# Codex 没有 Claude 的 Skill 工具权限；它原生发现 .agents/skills 与 ~/.agents/skills。
# 安装器要映射的是 approval/sandbox，不能把 Claude permissionMode 原样传给 Codex。
# 假 codex 把参数逐行落盘；测试自己用 shell 内建拼回去，不依赖 paste。
FAKE_CODEX="$WORK/bin/codex"
mkdir -p "$(dirname "$FAKE_CODEX")"
cat > "$FAKE_CODEX" <<EOF
#!/bin/sh
printf '%s\n' "\$@" > "$WORK/codex-args"
EOF
chmod +x "$FAKE_CODEX"

join_args() { # join_args <文件>：把每行一个的参数拼成一行
  local out="" line
  while IFS= read -r line; do out="${out:+$out }$line"; done < "$1"
  printf '%s' "$out"
}

jq --arg cli "$FAKE_CODEX" '
  (.roles[] | select(.name == "gm") | .cli) = $cli
  | (.roles[] | select(.name == "gm") | .permissionMode) = "dontAsk"
' "$INST/roles.json" > "$INST/roles.json.tmp" && mv "$INST/roles.json.tmp" "$INST/roles.json"
XDG_CONFIG_HOME="$WORK/config" "$INST/scripts/opc-install.sh" t >/dev/null 2>&1
"$INST/.opc/run/gm.sh" </dev/null
codex_args="$(join_args "$WORK/codex-args")"
check "Codex dontAsk 映射为 never + workspace-write" \
  "--sandbox workspace-write --ask-for-approval never" "$codex_args"
check "Codex 启动器导出业务归属角色" "OPC_ROLE='gm'" \
  "$(grep '^OPC_ROLE=' "$INST/.opc/run/gm.sh")"
if [[ -e "$INST/.codex/hooks.json" ]]; then
  bad "Codex 角色仍被生成实例级 hooks.json"
else
  ok "Codex 权限完全交给用户与原生 CLI，不生成 hooks.json"
fi
if compgen -G "$INST/.opc/hooks/scope-*.sh" >/dev/null; then
  bad "Codex 角色仍被生成 scope 守卫脚本"
else
  ok "Codex 权限完全交给用户与原生 CLI，不生成 scope 守卫"
fi

# 迁移老实例：只清掉 OPC 旧版生成的 hook，用户自己的项目 hook 必须保留。
mkdir -p "$INST/.codex" "$INST/.opc/hooks"
jq -n --arg cmd "/bin/sh '$INST/.opc/hooks/scope-gm.sh'" \
  '{hooks:{PreToolUse:[{matcher:"Bash",hooks:[{type:"command",command:$cmd,timeout:10}]}]}}' \
  > "$INST/.codex/hooks.json"
printf '%s\n' '#!/bin/sh' 'exit 0' > "$INST/.opc/hooks/scope-gm.sh"
chmod +x "$INST/.opc/hooks/scope-gm.sh"
XDG_CONFIG_HOME="$WORK/config" "$INST/scripts/opc-install.sh" t >/dev/null 2>&1
if [[ -e "$INST/.codex/hooks.json" || -e "$INST/.opc/hooks/scope-gm.sh" ]]; then
  bad "安装器没有清理 OPC 旧版生成的 codex hook"
else
  ok "安装器清理 OPC 旧版生成的 codex hook"
fi

custom_hooks='{"hooks":{"PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"my-user-hook"}]}]}}'
printf '%s\n' "$custom_hooks" > "$INST/.codex/hooks.json"
XDG_CONFIG_HOME="$WORK/config" "$INST/scripts/opc-install.sh" t >/dev/null 2>&1
check "安装器保留用户自己的 codex hook" "$custom_hooks" \
  "$(jq -c . "$INST/.codex/hooks.json")"

# 启动器不能写死 /bin/zsh：发行版不一定装 zsh，角色会直接起不来。
launcher="$(cat "$INST/.opc/run/gm.sh")"
case "$launcher" in
  */bin/zsh*) bad "启动器写死了 /bin/zsh" ;;
  *) ok "启动器不写死 /bin/zsh" ;;
esac

# PATH 里只有 bash 时（模拟没装 zsh 的机器），启动器仍要能跑起来。
mkdir -p "$WORK/onlybash"
ln -s "$(command -v bash)" "$WORK/onlybash/bash"
PATH="$WORK/onlybash" "$INST/.opc/run/gm.sh" </dev/null
codex_args="$(join_args "$WORK/codex-args")"
check "没有 zsh 时回退到 bash 仍能启动" \
  "--sandbox workspace-write --ask-for-approval never" "$codex_args"

jq '(.roles[] | select(.name == "gm") | .permissionMode) = "default"' \
  "$INST/roles.json" > "$INST/roles.json.tmp" && mv "$INST/roles.json.tmp" "$INST/roles.json"
XDG_CONFIG_HOME="$WORK/config" "$INST/scripts/opc-install.sh" t >/dev/null 2>&1
"$INST/.opc/run/gm.sh" </dev/null
codex_args="$(join_args "$WORK/codex-args")"
check "Codex default 映射为 on-request + workspace-write" \
  "--sandbox workspace-write --ask-for-approval on-request" "$codex_args"

jq '
  (.roles[] | select(.name == "gm") | .cli) = "claude"
  | (.roles[] | select(.name == "gm") | .permissionMode) = "default"
' "$INST/roles.json" > "$INST/roles.json.tmp" && mv "$INST/roles.json.tmp" "$INST/roles.json"

# ---- 0b. bypassPermissions：零弹窗，但 deny 与目录封锁仍然生效 ----
# bypassPermissions 下 allow 规则失效、deny 规则照旧生效，文件工具还额外被
# 锁在工作目录内。注意：deny 清单不是 OS 沙箱，shell 子进程仍可能绕过命令名规则；
# 这里只验证模版承诺的两层确实生成，不把它们冒充完整隔离。
jq '(.roles[] | select(.name == "gm") | .permissionMode) = "bypassPermissions"' \
  "$INST/roles.json" > "$INST/roles.json.tmp" && mv "$INST/roles.json.tmp" "$INST/roles.json"
XDG_CONFIG_HOME="$WORK/config" "$INST/scripts/opc-install.sh" t >/dev/null 2>&1
launcher="$(cat "$INST/.opc/run/gm.sh")"
case "$launcher" in
  *"--permission-mode bypassPermissions"*) ok "bypassPermissions 传给 claude" ;;
  *) bad "bypassPermissions 没传给 claude（启动器：${launcher}）" ;;
esac
for d in "Bash(git:*)" "Bash(rm:*)" "Bash(sudo:*)" "Bash(hc keys:*)"; do
  if jq -e --arg d "$d" '.permissions.deny | index($d)' "$INST/.opc/settings-gm.json" >/dev/null; then
    ok "bypass 模式仍保留 deny：$d"
  else
    bad "bypass 模式丢了 deny：$d"
  fi
done
check "写操作被锁在实例目录内" "true" \
  "$(jq -r '.permissions.blockWritesOutsideWorkingDirectories' "$INST/.opc/settings-gm.json")"

# 角色级扩展：roles.json 里可以给某个角色单独加 deny / allow
jq '(.roles[] | select(.name == "gm") | .deny) = ["Bash(curl:*)"]' \
  "$INST/roles.json" > "$INST/roles.json.tmp" && mv "$INST/roles.json.tmp" "$INST/roles.json"
XDG_CONFIG_HOME="$WORK/config" "$INST/scripts/opc-install.sh" t >/dev/null 2>&1
if jq -e '.permissions.deny | index("Bash(curl:*)")' "$INST/.opc/settings-gm.json" >/dev/null; then
  ok "角色级 deny 扩展生效"
else
  bad "角色级 deny 扩展没生效"
fi

# Codex 的 bypass 等价物：跳过审批与沙箱
jq --arg cli "$FAKE_CODEX" '
  (.roles[] | select(.name == "gm") | .cli) = $cli
  | (.roles[] | select(.name == "gm") | .permissionMode) = "bypassPermissions"
' "$INST/roles.json" > "$INST/roles.json.tmp" && mv "$INST/roles.json.tmp" "$INST/roles.json"
XDG_CONFIG_HOME="$WORK/config" "$INST/scripts/opc-install.sh" t >/dev/null 2>&1
"$INST/.opc/run/gm.sh" </dev/null
codex_args="$(join_args "$WORK/codex-args")"
check "Codex bypass 映射为 dangerously-bypass-approvals-and-sandbox" \
  "--dangerously-bypass-approvals-and-sandbox" "$codex_args"

# Codex 的 auto 等价物：--approve-for-me
jq '(.roles[] | select(.name == "gm") | .permissionMode) = "auto"' \
  "$INST/roles.json" > "$INST/roles.json.tmp" && mv "$INST/roles.json.tmp" "$INST/roles.json"
XDG_CONFIG_HOME="$WORK/config" "$INST/scripts/opc-install.sh" t >/dev/null 2>&1
"$INST/.opc/run/gm.sh" </dev/null
codex_args="$(join_args "$WORK/codex-args")"
check "Codex auto 映射为 approve-for-me" \
  "--approve-for-me --sandbox workspace-write" "$codex_args"

# cli 路径里带相对跳转的也要拒绝：它会被写进启动器并被执行
jq --arg cli "../evil" '(.roles[] | select(.name == "gm") | .cli) = $cli' \
  "$INST/roles.json" > "$INST/roles.json.tmp" && mv "$INST/roles.json.tmp" "$INST/roles.json"
if XDG_CONFIG_HOME="$WORK/config" "$INST/scripts/opc-install.sh" t >/dev/null 2>&1; then
  bad "带 .. 的 cli 路径被放行了"
else
  ok "带 .. 的 cli 路径被拒绝"
fi

jq '
  (.roles[] | select(.name == "gm") | .cli) = "claude"
  | (.roles[] | select(.name == "gm") | .permissionMode) = "default"
  | del(.roles[] | select(.name == "gm") | .deny)
' "$INST/roles.json" > "$INST/roles.json.tmp" && mv "$INST/roles.json.tmp" "$INST/roles.json"

if scripts/opc-sync.sh check --from "$TPL" >/dev/null 2>&1; then
  ok "完全同步后 check 退出 0，不把 identical 当差异"
else
  bad "完全同步后 check 仍报告差异"
fi

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

# ---- 13. 老实例 adopt：补齐种子快照但不覆盖业务 ----
OLD="$WORK/old"
mkdir -p "$OLD/scripts" "$OLD/knowledge/business"
cp "$TPL/scripts/lib.sh" "$OLD/scripts/lib.sh"
cp "$TEMPLATE/scripts/opc-sync.sh" "$OLD/scripts/opc-sync.sh"
printf '老实例真实业务。\n' > "$OLD/knowledge/business/品牌口径.md"
(
  cd "$OLD" || exit 1
  git init -q -b main
  git add -A >/dev/null 2>&1
  git -c user.name=test -c user.email=test@example.invalid commit -q -m old
  scripts/opc-sync.sh adopt --from "$TPL" >/dev/null 2>&1
)
grep -q "老实例真实业务" "$OLD/knowledge/business/品牌口径.md" && ok "adopt 不覆盖老实例业务" || bad "adopt 覆盖了老实例业务"
[[ -f "$OLD/seeds/knowledge/business/品牌口径.md" ]] && ok "adopt 补齐老实例的种子快照" || bad "adopt 没补种子快照"
status="$(cd "$OLD" && scripts/opc-sync.sh seeds --from "$TPL" 2>&1 || true)"
echo "$status" | grep -q "业务已改.*knowledge/business/品牌口径.md" && ok "老实例业务改动被正确识别" || bad "老实例业务被误报成无基线或双改"

# ---- 14. 同步脚本自身：本轮暂存，下次运行生效 ----
printf '\n# 模版对同步脚本的改动\n' >> "$TPL/scripts/opc-sync.sh"
out="$(scripts/opc-sync.sh pull --from "$TPL" --no-install 2>&1)"
echo "$out" | grep -q "deferred scripts/opc-sync.sh" && ok "同步脚本本轮不覆盖，改为暂存" || bad "同步脚本没有被识别为 deferred"
[[ -f "$INST/.opc/sync-stage/scripts/opc-sync.sh" ]] && ok "新版已落到暂存区" || bad "暂存区没有新版"
scripts/opc-sync.sh status --from "$TPL" >/dev/null 2>&1
grep -q "模版对同步脚本的改动" scripts/opc-sync.sh && ok "下次运行自动替换为新版" || bad "下次运行没有替换"
[[ -f "$INST/.opc/sync-stage/scripts/opc-sync.sh" ]] && bad "暂存区没有清理" || ok "暂存区已清理"

# ---- 15. 新实例自带基线：模版后续更新能被 check 检出并 pull 落地 ----
# 没有基线时，模版改了机制文件，check 会因为「无法判断本地是否改过」而静默，
# 实例就永远停在旧版本上。新建实例必须自带基线快照。
FRESH="$WORK/fresh"
FRESH_TPL="$WORK/fresh-tpl"
cp -R "$TEMPLATE" "$FRESH_TPL"
rm -rf "$FRESH_TPL/.git" "$FRESH_TPL/.opc"
"$FRESH_TPL/scripts/opc-new.sh" "$FRESH" --prefix f --source "$FRESH_TPL" --no-install >/dev/null 2>&1
printf '\n建好实例之后模版才加的一节。\n' >> "$FRESH_TPL/AGENTS.md"
mkdir -p "$FRESH_TPL/tools/__pycache__"
printf 'x' > "$FRESH_TPL/tools/__pycache__/fake.pyc"
out="$(cd "$FRESH" && scripts/opc-sync.sh check --from "$FRESH_TPL" 2>&1)"
rc=$?
if [[ "$rc" == "1" ]] && grep -q "update.*AGENTS.md" <<< "$out"; then
  ok "新建实例能检出模版后续更新"
else
  bad "新建实例检不出模版后续更新（退出码 ${rc}）"
fi
grep -q "__pycache__" <<< "$out" && bad "字节码被当成模版托管文件" || ok "字节码不进同步清单"
(cd "$FRESH" && scripts/opc-sync.sh pull --from "$FRESH_TPL" --no-install >/dev/null 2>&1)
grep -q "建好实例之后模版才加的一节" "$FRESH/AGENTS.md" \
  && ok "新建实例能拉取模版后续更新" || bad "新建实例拉不到模版后续更新"

# ---- 16. 没有基线的实例：check 必须报「无法判断」，不能说「没有待处理差异」 ----
LEGACY="$WORK/legacy"
cp -R "$INST" "$LEGACY"
rm -rf "$LEGACY/.opc/sync-base" "$LEGACY/.opc/sync-state.json"
printf '\n老实例没有基线时模版又加的一节。\n' >> "$TPL/AGENTS.md"
out="$(cd "$LEGACY" && scripts/opc-sync.sh check --from "$TPL" 2>&1)"
rc=$?
if [[ "$rc" == "1" ]] && grep -q "unknown" <<< "$out"; then
  ok "没有基线的实例把「无法判断」报出来"
else
  bad "没有基线的实例被当成「没有待处理差异」（退出码 ${rc}）"
fi

# ---- 17. baseline 按实例首次提交还原基线，让模版更新重新可检出 ----
RECOVER="$WORK/recover"
RECOVER_TPL="$WORK/recover-tpl"
cp -R "$TEMPLATE" "$RECOVER_TPL"
rm -rf "$RECOVER_TPL/.opc" "$RECOVER_TPL/.git"
git -C "$RECOVER_TPL" init -q -b main
git -C "$RECOVER_TPL" add -A >/dev/null 2>&1
git -C "$RECOVER_TPL" -c user.name=test -c user.email=test@example.invalid \
  commit -q -m "模版初始" >/dev/null 2>&1
"$RECOVER_TPL/scripts/opc-new.sh" "$RECOVER" --prefix r --source "$RECOVER_TPL" --no-install >/dev/null 2>&1
rm -rf "$RECOVER/.opc/sync-base" "$RECOVER/.opc/sync-state.json"
printf '\n恢复路径要带回来的改动。\n' >> "$RECOVER_TPL/AGENTS.md"
git -C "$RECOVER_TPL" add -A >/dev/null 2>&1
git -C "$RECOVER_TPL" -c user.name=test -c user.email=test@example.invalid \
  commit -q -m "模版更新" >/dev/null 2>&1
(cd "$RECOVER" && scripts/opc-sync.sh baseline --from "$RECOVER_TPL" >/dev/null 2>&1)
out="$(cd "$RECOVER" && scripts/opc-sync.sh check --from "$RECOVER_TPL" 2>&1)"
if grep -q "update.*AGENTS.md" <<< "$out"; then
  ok "baseline 还原后模版更新重新可检出"
else
  bad "baseline 还原后模版更新仍检不出"
fi
(cd "$RECOVER" && scripts/opc-sync.sh pull --from "$RECOVER_TPL" --no-install >/dev/null 2>&1)
grep -q "恢复路径要带回来的改动" "$RECOVER/AGENTS.md" \
  && ok "baseline 之后能拉回模版更新" || bad "baseline 之后拉不回模版更新"

say ""
say "通过 $PASS 项 / 失败 $FAIL 项"
[[ "$FAIL" == "0" ]] || exit 1
