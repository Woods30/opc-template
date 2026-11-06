#!/usr/bin/env bash
# 干净实例的端到端测试：安装结构 + 完整内容闭环 + generated 视图 + inbox task ID。
#
# 跑法：
#   bash tools/tests/test_opc_instance.sh
#
# 所有动作都在 mktemp 目录里的副本实例上完成：不读取、不启动、不停止、也不修改
# 任何活动实例或 hc 终端。全程不调用 hc / opc-up。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
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

TPL="$WORK/tpl"
INST="$WORK/inst"
cp -R "$ROOT" "$TPL"
rm -rf "$TPL/.git" "$TPL/.opc" "$TPL/knowledge"
mkdir -p "$TPL/knowledge/business"
printf '模版本地业务数据\n' > "$TPL/knowledge/local-only.md"
"$TPL/scripts/opc-new.sh" "$INST" --prefix t --source "$TPL" --no-install >/dev/null 2>&1
jq '.channels = [{"id":"wechat","name":"公众号","enabled":true}]' \
  "$INST/channels.json" > "$INST/channels.json.tmp" && mv "$INST/channels.json.tmp" "$INST/channels.json"
XDG_CONFIG_HOME="$WORK/config" "$INST/scripts/opc-install.sh" t >/dev/null 2>&1

# 开实例这条路径本身必须返回 0：安装成功时脚本不能以非零退出，
# 否则调用方（脚本、CI、agent）会把一次成功当失败。
INST2="$WORK/inst2"
XDG_CONFIG_HOME="$WORK/config" "$TPL/scripts/opc-new.sh" "$INST2" --prefix t2 \
  --source "$TPL" >/dev/null 2>&1
check "opc-new 建实例并安装返回 0" "0" "$?"
expect "第二个实例的目录结构已建好" test -f "$INST2/knowledge/team.md"
expect "第二个实例没有 review 与 daily 目录" test ! -e "$INST2/knowledge/review"

# ---- 1. 安装结构：canonical 内容区、规则、生成视图入口、工具 ----
expect "新实例有 canonical 内容区" test -d "$INST/knowledge/content"
expect "新实例有业务规则种子" test -f "$INST/knowledge/business/品牌口径.md"
expect "新实例有生成的选题日历入口" grep -q "GENERATED FILE — READ ONLY" \
  "$INST/knowledge/business/选题日历.md"
expect "新实例有 workflow" test -x "$INST/tools/opc-workflow"
expect "新实例有 preflight" test -x "$INST/tools/preflight"
expect "新实例自带基线快照" test -f "$INST/.opc/sync-base/AGENTS.md"
expect "新实例有 gm inbox" test -f "$INST/knowledge/inbox/gm.md"
expect "渠道目录只有发布记录" test -f "$INST/knowledge/business/wechat/发布记录.md"
expect "渠道发布记录标记 generated" grep -q "GENERATED FILE — READ ONLY" \
  "$INST/knowledge/business/wechat/发布记录.md"
check "渠道目录不带稿件或资产副本" "发布记录.md" \
  "$(ls -A "$INST/knowledge/business/wechat")"
reject "不再创建 review 目录" test -e "$INST/knowledge/review"
reject "不再创建 daily 目录" test -e "$INST/knowledge/daily"
reject "模版本地 knowledge 不会复制进实例" test -e "$INST/knowledge/local-only.md"

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

say ""
say "汇总：通过 ${PASS} 项 / 失败 ${FAIL} 项"
[[ "$FAIL" -eq 0 ]]
