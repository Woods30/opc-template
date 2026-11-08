#!/usr/bin/env bash
# 查看 OPC 团队状态：角色是否启用、终端是否在跑、权限模式与放行规则。
# 收件箱已退休，不再统计待办：待办以任务卡为准（knowledge/tasks/），
# 那份口径由任务卡机制自己定，这里不另立一套。
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

ROOT="$(opc_root)"
PREFIX="$(opc_prefix "$ROOT")"

echo "实例：${ROOT}（前缀 ${PREFIX}）"
echo
# 表头用 ASCII：中文在 printf 的 %-Ns 里按字节补空格，列会错位
printf '%-10s %-4s %-6s %-10s %-13s %-9s %-6s %s\n' ROLE ON TERM STATE AGENT MODE ALLOW
printf '%-10s %-4s %-6s %-10s %-13s %-9s %-6s %s\n' ---- -- ---- ----- ----- ---- -----

terminals=$(hc ls --json 2>/dev/null || echo '{"terminals":[]}')

for role in $(opc_all_roles); do
  tname="$PREFIX-$role"
  if opc_role_enabled "$role"; then enabled="Y"; else enabled="N"; fi
  row=$(printf '%s' "$terminals" | jq -r --arg n "$tname" \
    '.terminals[] | select(.address==$n or .name==$n) | "\(.address)\t\(.state)\t\(.agent // "-")"' | head -1)
  if [[ -n "$row" ]]; then
    addr=$(printf '%s' "$row" | cut -f1)
    state=$(printf '%s' "$row" | cut -f2)
    agent=$(printf '%s' "$row" | cut -f3)
  else
    addr="-" ; state="未启动" ; agent="$(opc_role_cli "$role")"
  fi
  mode=$(opc_role_field "$role" permissionMode)
  mode="${mode:-$(opc_cli_default_permission_mode "$(opc_role_cli "$role")")}"
  settings="$ROOT/.opc/settings-$role.json"
  if [[ -f "$settings" ]]; then
    allowed=$(jq -r '.permissions.allow | length' "$settings" 2>/dev/null || true)
  else
    allowed="-"
  fi
  printf '%-10s %-4s %-6s %-10s %-13s %-9s %-6s %s\n' \
    "$role" "$enabled" "$addr" "$state" "$agent" "$mode" "${allowed:--}"
done

echo
echo "改角色：scripts/opc-role.sh list | enable <角色> | disable <角色> | add <角色>"
echo
echo "待办看任务卡目录：knowledge/tasks/"
echo
echo "权限模式：default/manual=常规审批；acceptEdits=编辑自动放行；auto=分类器代审；"
echo "          plan=只读；dontAsk=不弹窗、未放行一律拒绝；bypassPermissions=只剩 deny 与目录封锁"
echo
echo "CLI 能力差异（Skill 来源与权限模型）："
for role in $(opc_all_roles); do
  cli="$(opc_role_cli "$role")"
  printf '  %-10s %-8s %s\n' "$role" "$cli" "$(opc_cli_skill_source "$cli")"
  printf '  %-10s %-8s %s\n' "" "" "$(opc_cli_permission_model "$cli")"
done
