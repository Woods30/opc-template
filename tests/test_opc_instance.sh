#!/usr/bin/env bash
# 干净实例的端到端测试：安装结构 + 完整内容闭环 + generated 视图 + inbox task ID。
#
# 跑法：
#   bash tests/test_opc_instance.sh
#
# 所有动作都在 mktemp 目录里的副本实例上完成：不读取、不启动、不停止、也不修改
# 任何活动实例或 hc 终端。全程不调用 hc / opc-up。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

say() { printf '%s\n' "$*"; }
ok()  { PASS=$((PASS + 1)); printf '  \033[32m通过\033[0m %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf '  \033[31m失败\033[0m %s\n' "$1"; }
check() { # check <描述> <期望> <实际>
  if [[ "$2" == "$3" ]]; then ok "$1"; else bad "$1（期望「$2」，实际「$3」）"; fi
}
expect() { # expect <描述> <命令...>
  local desc="$1"
  shift
  if "$@" >/dev/null 2>&1; then ok "$desc"; else bad "$desc"; fi
}
reject() { # reject <描述> <命令...>
  local desc="$1"
  shift
  if "$@" >/dev/null 2>&1; then bad "$desc"; else ok "$desc"; fi
}

say "干净实例端到端测试"

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
check "opc install 建实例返回 0" "0" "$?"

jq '.channels = [{"id":"wechat","name":"公众号","enabled":true}]' \
  "$INST/channels.json" > "$INST/channels.json.tmp" && mv "$INST/channels.json.tmp" "$INST/channels.json"
"$INST/scripts/opc-install.sh" --no-input t >/dev/null 2>&1

INST2="$WORK/inst2"
"$ROOT/bin/opc" install "$INST2" t2 --template "$ROOT" --no-input --skip-smoke >/dev/null 2>&1
check "install 第二个实例返回 0" "0" "$?"
expect "第二个实例的目录结构已建好" test -f "$INST2/knowledge/team.md"
expect "第二个实例没有 review 与 daily 目录" test ! -e "$INST2/knowledge/review"

DRY_OUT="$("$ROOT/bin/opc" install "$WORK/inst3" t3 --template "$ROOT" --dry-run 2>&1)"
DRY_RC=$?
check "dry-run 返回 0" "0" "$DRY_RC"
expect "dry-run 不创建目录" test ! -e "$WORK/inst3"

# ---- 1. 安装结构：canonical 内容区、规则、生成视图入口、工具 ----
expect "新实例有 canonical 内容区" test -d "$INST/knowledge/content"
expect "新实例有业务规则种子" test -f "$INST/knowledge/business/品牌口径.md"
expect "新实例有生成的选题日历入口" grep -q "GENERATED FILE — READ ONLY" \
  "$INST/knowledge/business/选题日历.md"
expect "新实例有 workflow" test -x "$INST/tools/opc-workflow"
expect "新实例有 preflight" test -x "$INST/tools/preflight"
expect "新实例自带机制指纹" test -f "$INST/.opc/mechanism.json"
expect "新实例有 gm inbox" test -f "$INST/knowledge/inbox/gm.md"
expect "渠道目录只有发布记录" test -f "$INST/knowledge/business/wechat/发布记录.md"
expect "渠道发布记录标记 generated" grep -q "GENERATED FILE — READ ONLY" \
  "$INST/knowledge/business/wechat/发布记录.md"
check "渠道目录不带稿件或资产副本" "发布记录.md" \
  "$(ls -A "$INST/knowledge/business/wechat")"
reject "不再创建 review 目录" test -e "$INST/knowledge/review"
reject "不再创建 daily 目录" test -e "$INST/knowledge/daily"
reject "实例不再持有 layouts/" test -e "$INST/layouts"
reject "实例不再持有 mods/" test -e "$INST/mods"
reject "实例不再持有 seeds/" test -e "$INST/seeds"
reject "实例不再持有 sync-policy.json" test -e "$INST/sync-policy.json"
expect "全局布局只装一套" test -f "$HERDR_APP_HOME/layouts/opc.json"
expect "全局看板 mod 已安装" test -d "$HERDR_APP_HOME/mods/opc-dashboard"
expect "实例已登记到注册表" grep -q "$INST" "$OPC_CONFIG_DIR/instances.json"

# ---- 1b. 角色目录与 hc 模板 ----
only_ref() { # only_ref <文件>：入口文件只能是对 AGENTS.md 的引用，不能拷正文
  local body
  body="$(tr -d '[:space:]' < "$1")"
  [[ "$body" == "@AGENTS.md" || "$body" == "@./AGENTS.md" ]]
}
for role in gm content growth dev; do
  expect "角色 $role 有自己的目录" test -d "$INST/agents/$role"
  expect "角色 $role 的入口文件在" test -f "$INST/agents/$role/AGENTS.md"
  expect "角色 $role 有 Claude 的入口文件" test -f "$INST/agents/$role/CLAUDE.md"
  expect "角色 $role 有 Gemini 的入口文件" test -f "$INST/agents/$role/GEMINI.md"
  expect "角色 $role 的 Claude 入口文件只引用 AGENTS.md" \
    only_ref "$INST/agents/$role/CLAUDE.md"
  expect "角色 $role 的 Gemini 入口文件只引用 AGENTS.md" \
    only_ref "$INST/agents/$role/GEMINI.md"
  expect "角色 $role 的 hc 模板已生成" test -f "$HERDR_CORE_HOME/templates/t-$role.md"
done
expect "实例根有 Claude 的入口文件" test -f "$INST/CLAUDE.md"
expect "实例根有 Gemini 的入口文件" test -f "$INST/GEMINI.md"
expect "实例根的入口文件只引用 AGENTS.md" only_ref "$INST/GEMINI.md"
expect "角色正文不带 hc frontmatter" \
  bash -c "! head -n 1 '$INST/agents/gm/AGENTS.md' | grep -q '^---$'"
expect "hc 模板的 frontmatter 带前缀名" grep -q "^name: t-gm$" "$HERDR_CORE_HOME/templates/t-gm.md"
expect "hc 模板的 frontmatter 带描述" \
  grep -q "^description: [^ ]" "$HERDR_CORE_HOME/templates/t-gm.md"
expect "hc 模板的 frontmatter 带启动命令" \
  grep -q "^command: $INST/.opc/run/gm.sh$" "$HERDR_CORE_HOME/templates/t-gm.md"
expect "hc 模板带角色正文" grep -q "只在本实例目录内取材" "$HERDR_CORE_HOME/templates/t-gm.md"
expect "hc 模板里的占位符已替换" \
  bash -c "! grep -q '{{PREFIX}}' '$HERDR_CORE_HOME/templates/t-gm.md'"

# 实例里的角色正文改了，重跑安装器后 hc 模板跟着变，正文本身不被改写
printf '\n# owner 的补充说明\n' >> "$INST/agents/gm/AGENTS.md"
before="$(shasum "$INST/agents/gm/AGENTS.md" | awk '{print $1}')"
(cd "$INST" && scripts/opc-install.sh --no-input t >/dev/null 2>&1)
check "重跑安装器不改写实例的角色正文" "$before" \
  "$(shasum "$INST/agents/gm/AGENTS.md" | awk '{print $1}')"
expect "hc 模板反映改后的正文" \
  grep -q "owner 的补充说明" "$HERDR_CORE_HOME/templates/t-gm.md"

# ---- 1c. 收件箱文件头按角色分措辞 ----
# 上报只在会话里处理、不落盘。gm 的收件箱头若还写「上报」，下一个 gm 会以为该落盘；
# 其余角色的头保持原样。措辞类规则靠 review，这里守住的是「gm 那版不讲上报」。
expect "gm 收件箱头不讲上报" \
  bash -c "! grep -q '上报' '$INST/knowledge/inbox/gm.md'"
expect "gm 收件箱头讲清落盘的只有派工状态" \
  grep -q "落盘的只有派工状态" "$INST/knowledge/inbox/gm.md"
for role in content growth dev; do
  expect "收件箱 $role 保留派工与上报的原措辞" \
    grep -q "派工与上报都追加到本文件末尾" "$INST/knowledge/inbox/$role.md"
done
for role in gm content growth dev; do
  expect "收件箱 $role 保留当前队列小节" \
    grep -q "## 当前队列" "$INST/knowledge/inbox/$role.md"
  expect "收件箱 $role 保留空队列占位" \
    grep -q "（空）" "$INST/knowledge/inbox/$role.md"
done
# printf 没把 Markdown 打坏：占位符全部替换，反引号、完成/撤销标记、条目竖线原样输出
expect "收件箱头没留下未替换的占位符" \
  bash -c "! grep -q '%s' '$INST/knowledge/inbox/content.md'"
expect "收件箱头保留反引号" \
  grep -q '`knowledge/inbox/`' "$INST/knowledge/inbox/gm.md"
expect "收件箱头保留完成标记" \
  grep -q "✅" "$INST/knowledge/inbox/gm.md"
expect "收件箱头保留撤销标记" \
  grep -q "⛔ 已撤销" "$INST/knowledge/inbox/gm.md"
expect "收件箱头保留条目格式的竖线" \
  grep -q "| 任务 ID：task-" "$INST/knowledge/inbox/content.md"

# 收件箱只在文件缺失时创建：已有的头不被改写，由 gm 在会话内自行对齐
before_inbox="$(shasum "$INST/knowledge/inbox/gm.md" | awk '{print $1}')"
(cd "$INST" && scripts/opc-install.sh --no-input t >/dev/null 2>&1)
check "重跑安装器不改写已有收件箱" "$before_inbox" \
  "$(shasum "$INST/knowledge/inbox/gm.md" | awk '{print $1}')"

# ---- 2. 完整生命周期：proposed → ready → publication → published → metrics → reviewed → closed ----
cd "$INST" || exit 1
created="$(tools/opc-workflow create-content --title "集成测试内容" --target-date 2026-12-01 --actor content 2>&1)"
content_id="$(printf '%s' "$created" | sed -n 's/^已创建 \(content-[0-9a-z-]*\).*/\1/p')"
if [[ -n "$content_id" ]]; then ok "创建 proposed 内容"; else bad "创建 proposed 内容：$created"; fi

expect "内容进入 drafting" tools/opc-workflow transition "$content_id" --to drafting --actor content
expect "主稿固定在内容包" test -f "knowledge/content/$content_id/主稿.md"
reject "主稿不落到 work" test -e "knowledge/work/content/主稿.md"
printf '# 集成测试内容\n\n> **渠道**：公众号\n\n正文。\n\n关注公众号。\n' \
  > "knowledge/content/$content_id/主稿.md"
expect "主稿提交审核" tools/opc-workflow transition "$content_id" --to reviewing --actor content
expect "主稿审批通过" tools/opc-workflow transition "$content_id" --decision approved --actor gm

created_pub="$(tools/opc-workflow create-publication "$content_id" --channel wechat --required-window 48h --actor gm 2>&1)"
publication_id="$(printf '%s' "$created_pub" | sed -n 's/^已创建 \(publication-[0-9a-z-]*\).*/\1/p')"
if [[ -n "$publication_id" ]]; then ok "创建 publication"; else bad "创建 publication：$created_pub"; fi

printf '# 集成测试内容（公众号改写）\n\n> **渠道**：公众号\n\n正文。\n\n关注公众号。\n' \
  > "knowledge/content/$content_id/publications/$publication_id/渠道稿.md"
expect "渠道稿提交审核" tools/opc-workflow transition "$publication_id" --to reviewing --actor content
expect "渠道稿审批通过" tools/opc-workflow transition "$publication_id" --decision approved --actor gm
expect "publication 排期" tools/opc-workflow transition "$publication_id" --to scheduled \
  --planned-at 2026-12-05T09:00:00+08:00 --timezone Asia/Shanghai --actor gm

# 发布前自检：canonical 主稿与渠道稿都应通过硬性检查
expect "主稿 preflight 无硬性失败（退出码 0）" \
  tools/preflight "knowledge/content/$content_id/主稿.md"
expect "渠道稿 preflight 无硬性失败（退出码 0）" \
  tools/preflight --publication "$publication_id"

expect "记录实际发布" tools/opc-workflow transition "$publication_id" --to published \
  --actual-at 2026-12-05T09:10:00+08:00 --url https://example.com/posts/1 --actor gm

cat > knowledge/business/growth/指标.md <<'EOF'
---
{
  "schema_version": 1,
  "record_type": "metric_catalog",
  "metrics": [
    {
      "key": "views",
      "label": "阅读量",
      "unit": "count",
      "aggregation": "sum",
      "scope": "publication",
      "channels": ["wechat"]
    }
  ]
}
---

# 指标目录
EOF

expect "记录 48h 指标" tools/opc-workflow record-metrics "$publication_id" --window 48h \
  --observed-at 2026-12-07T09:10:00+08:00 --source "公众号后台" \
  --values '{"views": 1234}' --actor growth
expect "growth 完成复盘" tools/opc-workflow transition "$publication_id" --to reviewed \
  --conclusion continue --next-action "继续观察同类选题" --actor growth
expect "gm 关闭内容" tools/opc-workflow transition "$content_id" --to closed --actor gm

# ---- 3. inbox task ID 与业务引用 ----
printf '\n- [2026-12-07 10:00] 发起方：gm | 任务 ID：task-abc123 | 业务引用：%s | 任务：跟进复盘 | 验收：有结论\n' \
  "$publication_id" >> knowledge/inbox/gm.md

expect "validate 通过" tools/opc-workflow validate
expect "build 刷新生成视图" tools/opc-workflow build

expect "已关闭内容不进选题日历" bash -c "! grep -q '$content_id' knowledge/business/选题日历.md"
expect "发布记录展示复盘结论" grep -q "continue" knowledge/business/wechat/发布记录.md
expect "发布记录展示下一项行动" grep -q "继续观察同类选题" knowledge/business/wechat/发布记录.md
expect "看板 JSON 生成" test -f knowledge/business/dashboard.json
check "看板只把真实条目当任务" "1" \
  "$(jq -r '.tasks | length' knowledge/business/dashboard.json 2>/dev/null)"
check "看板记录 stable task ID" "task-abc123" \
  "$(jq -r '.tasks[0].task_id' knowledge/business/dashboard.json 2>/dev/null)"
check "看板记录业务引用" "$publication_id" \
  "$(jq -r '.tasks[0].reference' knowledge/business/dashboard.json 2>/dev/null)"
check "看板内容状态为 closed" "closed" \
  "$(jq -r --arg id "$content_id" '.contents[] | select(.content_id == $id) | .status' \
     knowledge/business/dashboard.json 2>/dev/null)"

# ---- 4. 没有 Herdr 时 workflow / build / preflight 仍可独立工作 ----
# 本测试全程只用 PATH 里的 python3/jq 等基础命令，从不调用 herdr-app 或 hc；
# 上面每一步都成功即证明这一点。
expect "生成视图无需 Herdr 即可读取" test -s knowledge/business/选题日历.md

# ---- 5. 新角色的简报也要守住「启动不自主开工」 ----
# opc-role.sh add 生成的简报如果只写「告诉我你打算先做什么」，
# 角色一启动就会自己开题——那正是 L17 要拦的。
(cd "$INST" && scripts/opc-role.sh add tester --scope knowledge/work/tester >/dev/null 2>&1) || true
expect "新角色的简报已生成" test -f "$INST/agents/tester/AGENTS.md"
expect "新角色的简报写明等 gm 派工" grep -q "等 gm 派工" "$INST/agents/tester/AGENTS.md"
expect "新角色的 roles.json 里有描述" \
  test -n "$(jq -r '.roles[] | select(.name=="tester") | .description' "$INST/roles.json")"
expect "新角色的 roles.json 里有技能列表" \
  test -n "$(jq -r '.roles[] | select(.name=="tester") | .skills | type' "$INST/roles.json")"
expect "新角色的 hc 模板已生成" test -f "$HERDR_CORE_HOME/templates/t-tester.md"
expect "新角色的 hc 模板带前缀名" grep -q "^name: t-tester$" "$HERDR_CORE_HOME/templates/t-tester.md"
expect "新角色的 hc 模板带启动命令" grep -q "^command: " "$HERDR_CORE_HOME/templates/t-tester.md"
expect "新角色的 hc 模板带角色正文" grep -q "等 gm 派工" "$HERDR_CORE_HOME/templates/t-tester.md"
expect "没有选中技能时不生成技能索引" \
  bash -c "! grep -q '技能索引' '$HERDR_CORE_HOME/templates/t-tester.md'"

lint_out="$(cd "$INST" && python3 tools/opc-lint --root . --quiet 2>&1)"
if grep -q "角色启动不自主开工" <<< "$lint_out"; then
  bad "新角色的简报没过 L17：$(grep -A 3 "角色启动不自主开工" <<< "$lint_out" | tr '\n' ' ')"
else
  ok "新角色的简报过了 L17"
fi

# ---- 6. 交互式安装：先看本机装了哪些 CLI，再选角色与 CLI ----
# 只放 claude 与 codex 两个假 CLI——检测只看 PATH，别的都不该出现。
FAKEBIN="$WORK/bin"
mkdir -p "$FAKEBIN"
for fake in claude codex; do
  printf '#!/bin/sh\nexit 0\n' > "$FAKEBIN/$fake"
  chmod +x "$FAKEBIN/$fake"
done
ln -sf "$(command -v jq)" "$FAKEBIN/jq"
# 答问顺序跟 roles.json 一致：gm(启用,第 2 个 CLI)、content(启用,第 1 个)、
# growth(停用)、dev(停用)、tester(第 5 节加的角色，停用)。
printf 'y\n2\ny\n1\nn\nn\nn\n' | PATH="$FAKEBIN:/usr/bin:/bin:/usr/sbin:/sbin" \
  XDG_CONFIG_HOME="$WORK/config" "$INST/scripts/opc-install.sh" --interactive i >/dev/null 2>&1
check "交互式安装按编号选中第 2 个 CLI" "codex" \
  "$(jq -r '.roles[] | select(.name=="gm") | .cli' "$INST/roles.json")"
check "交互式安装启用 content" "true" \
  "$(jq -r '.roles[] | select(.name=="content") | .enabled' "$INST/roles.json")"
check "交互式安装停用 growth" "false" \
  "$(jq -r '.roles[] | select(.name=="growth") | .enabled' "$INST/roles.json")"

# 一个 CLI 都没装时不猜，直接拒绝，别把角色配到不存在的命令上
out="$(PATH="/usr/bin:/bin:/usr/sbin:/sbin" XDG_CONFIG_HOME="$WORK/config" \
  "$INST/scripts/opc-install.sh" --interactive i 2>&1)"
rc=$?
if [[ "$rc" != "0" ]] && grep -q "没有检测到" <<< "$out"; then
  ok "没有可用的 CLI 时安装被拒绝"
else
  bad "没有可用的 CLI 时安装没有被拒绝（退出码 ${rc}）"
fi

# 非交互安装不读 stdin，也不改角色配置
before="$(jq -c . "$INST/roles.json")"
printf '' | PATH="$FAKEBIN:/usr/bin:/bin" XDG_CONFIG_HOME="$WORK/config" \
  "$INST/scripts/opc-install.sh" --no-input i >/dev/null 2>&1
check "非交互安装不改角色配置" "$before" "$(jq -c . "$INST/roles.json")"

# ---- 7. 技能索引：只列选中且存在的技能，缺失的只告警不失败 ----
mkdir -p "$INST/skills/demo"
printf -- '---\nname: demo\ndescription: 演示技能的一句话说明\n---\n\n正文。\n' \
  > "$INST/skills/demo/SKILL.md"
jq '.roles += [{name:"demoer", enabled:true, cli:"claude",
  description:"演示角色", template:"agents/demoer/AGENTS.md", skills:["demo","ghost"],
  permissionMode:"bypassPermissions", scope:["knowledge/work/demoer"], approvedSkills:[]}]' \
  "$INST/roles.json" > "$INST/roles.json.tmp" && mv "$INST/roles.json.tmp" "$INST/roles.json"
mkdir -p "$INST/agents/demoer"
printf '你是 demoer。\n\n## 启动\n\n等 gm 派工。\n' > "$INST/agents/demoer/AGENTS.md"
out="$( (cd "$INST" && scripts/opc-install.sh --no-input t) 2>&1 )"
rc=$?
check "选中技能缺失时安装仍成功" "0" "$rc"
expect "选中技能缺失时有告警" grep -q "ghost" <<< "$out"
expect "hc 模板里有技能索引" grep -q "## 技能索引" "$HERDR_CORE_HOME/templates/t-demoer.md"
expect "技能索引列出技能名" grep -q "demo" "$HERDR_CORE_HOME/templates/t-demoer.md"
expect "技能索引带技能描述" \
  grep -q "演示技能的一句话说明" "$HERDR_CORE_HOME/templates/t-demoer.md"
expect "技能索引带技能路径" \
  grep -q "skills/demo/SKILL.md" "$HERDR_CORE_HOME/templates/t-demoer.md"
expect "技能索引不含缺失的技能" \
  bash -c "! grep -q 'ghost' '$HERDR_CORE_HOME/templates/t-demoer.md'"

# 停用角色后旧的 hc 模板要清掉，否则全局模板目录里还留着失效入口
jq '(.roles[] | select(.name=="demoer") | .enabled) = false' \
  "$INST/roles.json" > "$INST/roles.json.tmp" && mv "$INST/roles.json.tmp" "$INST/roles.json"
(cd "$INST" && scripts/opc-install.sh --no-input t >/dev/null 2>&1)
expect "停用角色的 hc 模板被清理" test ! -e "$HERDR_CORE_HOME/templates/t-demoer.md"

# ---- 8. 统一技能库：默认映射、索引内容与越界防护 ----
# 第 6 节的交互式安装停用了 growth 与 dev，这里恢复全部角色再验默认映射。
jq '(.roles[] | select(.name=="growth" or .name=="dev") | .enabled) = true' \
  "$INST/roles.json" > "$INST/roles.json.tmp" && mv "$INST/roles.json.tmp" "$INST/roles.json"
(cd "$INST" && scripts/opc-install.sh --no-input t >/dev/null 2>&1)

for skill in opc-workflow knowledge-writing instance-ops; do
  expect "新实例含技能 $skill" test -f "$INST/skills/$skill/SKILL.md"
done

# 索引里列出的技能名，一行一个
index_skills() {
  sed -n '/^## 技能索引/,$p' "$HERDR_CORE_HOME/templates/t-$1.md" \
    | grep -o '^- [a-z0-9-]*' | sed 's/^- //'
}
check "gm 的索引列出三个技能" "opc-workflow knowledge-writing instance-ops" \
  "$(index_skills gm | paste -sd ' ' -)"
check "content 的索引列出两个技能" "knowledge-writing opc-workflow" \
  "$(index_skills content | paste -sd ' ' -)"
check "growth 的索引列出两个技能" "knowledge-writing opc-workflow" \
  "$(index_skills growth | paste -sd ' ' -)"
check "dev 的索引列出两个技能" "instance-ops knowledge-writing" \
  "$(index_skills dev | paste -sd ' ' -)"
expect "索引带技能路径" grep -q "skills/opc-workflow/SKILL.md" \
  "$HERDR_CORE_HOME/templates/t-gm.md"

# 改 roles.json 的技能选择，重跑安装器后索引跟着变
jq '(.roles[] | select(.name=="dev") | .skills) = ["instance-ops"]' \
  "$INST/roles.json" > "$INST/roles.json.tmp" && mv "$INST/roles.json.tmp" "$INST/roles.json"
(cd "$INST" && scripts/opc-install.sh --no-input t >/dev/null 2>&1)
check "改过技能选择后索引跟着变" "instance-ops" "$(index_skills dev | paste -sd ' ' -)"

# 实例里没有的技能：只告警并跳过，安装不失败
rm -rf "$INST/skills/instance-ops"
out="$( (cd "$INST" && scripts/opc-install.sh --no-input t) 2>&1 )"
rc=$?
check "选中技能缺失时安装仍成功" "0" "$rc"
expect "选中技能缺失时有告警" grep -q "instance-ops" <<< "$out"
expect "缺失的技能不进索引" \
  bash -c "! grep -q 'instance-ops' '$HERDR_CORE_HOME/templates/t-dev.md'"

# 技能文件是指向实例外的软链接：安装失败，外部内容不进提示词。
# 技能正文会被读进角色提示词，等于交给终端执行，所以越界读取要拦住。
printf -- '---\nname: instance-ops\ndescription: 外部机密\n---\n\n外部机密内容\n' \
  > "$WORK/outside.md"
mkdir -p "$INST/skills/instance-ops"
ln -s "$WORK/outside.md" "$INST/skills/instance-ops/SKILL.md"
cp "$HERDR_CORE_HOME/templates/t-dev.md" "$WORK/t-dev.before"
out="$( (cd "$INST" && scripts/opc-install.sh --no-input t) 2>&1 )"
rc=$?
check "技能指向实例外时安装失败" "1" "$rc"
expect "技能指向实例外时说明原因" grep -q "实例外" <<< "$out"
expect "失败后原有模板没被截断" \
  cmp -s "$WORK/t-dev.before" "$HERDR_CORE_HOME/templates/t-dev.md"
expect "外部文件内容不进提示词" \
  bash -c "! grep -q '外部机密内容' '$HERDR_CORE_HOME/templates/t-dev.md'"

# 整个技能库指向实例外：同样拦住
rm -rf "$INST/skills"
mkdir -p "$WORK/outside-skills"
ln -s "$WORK/outside-skills" "$INST/skills"
out="$( (cd "$INST" && scripts/opc-install.sh --no-input t) 2>&1 )"
rc=$?
check "技能库指向实例外时安装失败" "1" "$rc"
expect "技能库指向实例外时说明原因" grep -q "实例外" <<< "$out"
expect "技能库指向实例外时模板没被重写" \
  cmp -s "$WORK/t-dev.before" "$HERDR_CORE_HOME/templates/t-dev.md"

# ---- 9. 端到端验收：安装产物、起始材料升级、实例 lint ----
# 前 8 节把 $INST 改得面目全非（技能库被换成软链接、角色被停用），这里另开
# 一个干净实例走完整链路。
E2E="$WORK/e2e"
"$ROOT/bin/opc" install "$E2E" e2e --template "$ROOT" --no-input --skip-smoke >/dev/null 2>&1
check "端到端实例安装成功" "0" "$?"

# 9a. 角色目录：入口文件在目录里，目录本身就是角色的家
for role in gm content growth dev; do
  expect "角色 $role 有角色目录" test -d "$E2E/agents/$role"
  expect "角色 $role 的入口文件在目录里" test -f "$E2E/agents/$role/AGENTS.md"
done

# 9b. 技能库：模版带的技能整库复制到实例
for skill in opc-workflow knowledge-writing instance-ops; do
  expect "技能库整库复制到实例" test -f "$E2E/skills/$skill/SKILL.md"
done

# 9c. 起始材料基线：相对路径 + SHA-256 + 技能单元
expect "起始材料基线已生成" test -f "$E2E/.opc/starters.json"
cat > "$WORK/check_baseline.py" <<'PY'
import hashlib
import json
import pathlib
import sys

inst = pathlib.Path(sys.argv[1])
data = json.loads((inst / ".opc" / "starters.json").read_text(encoding="utf-8"))
files = data.get("files") or {}
skills = data.get("skills") or {}
problems = []
for rel in ("AGENTS.md", "agents/gm/AGENTS.md", "skills/opc-workflow/SKILL.md"):
    record = files.get(rel) or {}
    digest = record.get("sha256")
    if not digest:
        problems.append("基线缺 " + rel)
        continue
    actual = hashlib.sha256((inst / rel).read_bytes()).hexdigest()
    if actual != digest:
        problems.append("基线哈希与实际不符：" + rel)
for rel in files:
    parts = pathlib.PurePosixPath(rel).parts
    if rel.startswith("/") or ".." in parts:
        problems.append("基线里的路径不是相对路径：" + rel)
if "skills/opc-workflow" not in skills:
    problems.append("基线没记技能单元")
print("；".join(problems))
sys.exit(1 if problems else 0)
PY
if python3 "$WORK/check_baseline.py" "$E2E" >/dev/null 2>&1; then
  ok "起始材料基线记了相对路径与 SHA-256"
else
  bad "起始材料基线不对：$(python3 "$WORK/check_baseline.py" "$E2E" 2>&1)"
fi

# 9d. hc 模板的技能索引：与 roles.json 里该角色选中的技能完全一致
for role in gm content growth dev; do
  want="$(jq -r --arg n "$role" '.roles[] | select(.name==$n) | .skills | join(" ")' \
    "$E2E/roles.json")"
  got="$(sed -n '/^## 技能索引/,$p' "$HERDR_CORE_HOME/templates/e2e-$role.md" \
    | grep -o '^- [A-Za-z0-9._-]*' | sed 's/^- //' | paste -sd ' ' -)"
  check "角色 $role 的技能索引与 roles.json 完全一致" "$want" "$got"
done
expect "技能索引给出读取路径" \
  grep -q "skills/opc-workflow/SKILL.md" "$HERDR_CORE_HOME/templates/e2e-gm.md"

# 9e. 升级语义：owner 改过的保留、owner 删掉的不复活、模版新增的补入
TPL_A="$WORK/tpl-a"
TPL_B="$WORK/tpl-b"
mkdir -p "$TPL_A" "$TPL_B"
cp -R "$ROOT/template" "$TPL_A/template"
cp -R "$ROOT/template" "$TPL_B/template"
mkdir -p "$TPL_A/template/agents/extra" "$TPL_B/template/agents/extra"
printf '# 模版新增的角色材料\n' > "$TPL_A/template/agents/extra/AGENTS.md"
cp "$TPL_A/template/agents/extra/AGENTS.md" "$TPL_B/template/agents/extra/AGENTS.md"
mkdir -p "$TPL_B/template/skills/extra-skill"
printf -- '---\nname: extra-skill\ndescription: 模版新增的技能\n---\n\n正文。\n' \
  > "$TPL_B/template/skills/extra-skill/SKILL.md"
# 模版侧改了 dev 的角色材料：实例没动过它，升级应该刷新
printf '\n模版侧的新版本。\n' >> "$TPL_B/template/agents/dev/AGENTS.md"

UP="$WORK/up"
"$ROOT/bin/opc" install "$UP" up --template "$TPL_A" --no-input --skip-smoke >/dev/null 2>&1
check "升级场景的实例安装成功" "0" "$?"
expect "起始材料基线记了模版新增的角色材料" test -f "$UP/agents/extra/AGENTS.md"

# owner 改过一份起始材料，删掉另一份
printf '\n# owner 的补充\n' >> "$UP/agents/gm/AGENTS.md"
rm -f "$UP/agents/extra/AGENTS.md"

# dry-run 要把将要发生的动作讲清楚，但不能写盘
out="$("$ROOT/bin/opc" upgrade "$UP" --template "$TPL_B" --dry-run 2>&1)"
rc=$?
check "升级 --dry-run 返回 0" "0" "$rc"
expect "dry-run 打印起始材料更新" grep -q "起始材料更新" <<< "$out"
expect "dry-run 打印起始材料新增" grep -q "起始材料新增" <<< "$out"
expect "dry-run 打印 owner 删过的跳过" grep -q "owner 已删除" <<< "$out"
expect "dry-run 不补 owner 删掉的文件" test ! -e "$UP/agents/extra/AGENTS.md"
expect "dry-run 不补模版新增的技能" test ! -e "$UP/skills/extra-skill/SKILL.md"
expect "dry-run 不改 owner 改过的文件" bash -c \
  "! grep -q '模版侧的新版本' '$UP/agents/gm/AGENTS.md'"

out="$("$ROOT/bin/opc" upgrade "$UP" --template "$TPL_B" --skip-smoke 2>&1)"
rc=$?
check "升级成功" "0" "$rc"
expect "owner 改过的起始材料被保留" grep -q "owner 的补充" "$UP/agents/gm/AGENTS.md"
expect "owner 改过的起始材料有告警" grep -q "已本地修改" <<< "$out"
expect "owner 删掉的起始材料没有复活" test ! -e "$UP/agents/extra/AGENTS.md"
expect "模版新增的起始材料被补入" test -f "$UP/skills/extra-skill/SKILL.md"
expect "没改过的角色材料跟随模版更新" grep -q "模版侧的新版本" "$UP/agents/dev/AGENTS.md"

# 提交范围：只带本次动作涉及的文件，不带工作区里的无关脏文件
printf '不相关\n' > "$UP/knowledge/business/unrelated.md"
committed="$(git -C "$UP" diff-tree --no-commit-id --name-only -r --no-renames HEAD \
  | sort | tr '\n' ' ')"
expect "升级提交不含无关脏文件" bash -c \
  "! printf '%s' '$committed' | grep -q 'knowledge/business/unrelated.md'"
expect "升级提交含新增的技能" bash -c \
  "printf '%s' '$committed' | grep -q 'skills/extra-skill/SKILL.md'"

# 9f. 实例 lint：结构检查在干净实例上全绿
lint_out="$("$E2E/scripts/opc-lint.sh" 2>&1)"
rc=$?
check "干净实例的 lint 通过" "0" "$rc"
if grep -q "角色启动不自主开工" <<< "$lint_out"; then
  bad "实例 lint 不该查角色内容：$(grep -A 3 "角色启动不自主开工" <<< "$lint_out" | tr '\n' ' ')"
else
  ok "实例 lint 不查角色内容规则"
fi

# owner 改过角色简报也不该被实例 lint 拦：内容归 owner 管
lint_out="$("$UP/scripts/opc-lint.sh" 2>&1)"
rc=$?
check "owner 改过角色简报后实例 lint 仍通过" "0" "$rc"

say ""
say "汇总：通过 ${PASS} 项 / 失败 ${FAIL} 项"
[[ "$FAIL" -eq 0 ]]
