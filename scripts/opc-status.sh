#!/usr/bin/env bash
# 查看 OPC 团队状态：角色是否启用、终端是否在跑、各自 inbox 有多少条待处理。
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

ROOT="$(opc_root)"
PREFIX="$(opc_prefix "$ROOT")"

echo "实例：${ROOT}（前缀 ${PREFIX}）"
echo
printf '%-10s %-6s %-8s %-10s %-8s %s\n' 角色 启用 终端 状态 agent 待处理
printf '%-10s %-6s %-8s %-10s %-8s %s\n' ---- ---- ---- ---- ----- ------

terminals=$(hc ls --json 2>/dev/null || echo '{"terminals":[]}')

for role in $(opc_all_roles); do
  tname="$PREFIX-$role"
  if opc_role_enabled "$role"; then enabled="是"; else enabled="否"; fi
  row=$(printf '%s' "$terminals" | jq -r --arg n "$tname" \
    '.terminals[] | select(.address==$n or .name==$n) | "\(.address)\t\(.state)\t\(.agent // "-")"' | head -1)
  if [[ -n "$row" ]]; then
    addr=$(printf '%s' "$row" | cut -f1)
    state=$(printf '%s' "$row" | cut -f2)
    agent=$(printf '%s' "$row" | cut -f3)
  else
    addr="-" ; state="未启动" ; agent="$(opc_role_cli "$role")"
  fi
  # 只数真实条目（日期开头），不数格式示例
  pending=$(grep -cE '^- \[[0-9]{4}-[0-9]{2}-[0-9]{2}' "$ROOT/knowledge/inbox/$role.md" 2>/dev/null || true)
  printf '%-10s %-6s %-8s %-10s %-8s %s\n' "$role" "$enabled" "$addr" "$state" "$agent" "${pending:-0}"
done

echo
echo "改角色：scripts/opc-role.sh list | enable <角色> | disable <角色> | add <角色>"
