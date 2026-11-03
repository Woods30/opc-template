#!/usr/bin/env bash
# 停止 OPC 团队：结束角色终端，保留 Herdr space 与 tab 结构。
# 用法：scripts/opc-down.sh [角色...]   # 不带参数 = 停掉 roles.json 里的全部角色（含停用的）
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

ROOT="$(opc_root)"
PREFIX="$(opc_prefix "$ROOT")"

if [[ $# -eq 0 ]]; then
  roles=($(opc_all_roles))
else
  roles=("$@")
fi

# hc kill 一次只收一个目标，必须逐个调用
for role in "${roles[@]}"; do
  tname="$PREFIX-$role"
  if hc kill "$tname" >/dev/null 2>&1; then
    echo "  已停止 $tname"
  else
    echo "  $tname 不在运行"
  fi
done

echo "团队已停止。space「$PREFIX 团队」保留，重新启动用 scripts/opc-up.sh。"
