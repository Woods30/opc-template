#!/usr/bin/env bash
# 停止 OPC 团队：结束角色终端，保留 Herdr space 与 tab 结构。
# 用法：scripts/opc-down.sh [--yes] [--dry-run] [角色...]   # 不带参数 = 停掉 roles.json 里的全部角色（含停用的）
#   --yes = 已知会清空所有角色的会话上下文，owner 明确同意后才可加；非 TTY 调用必须带
#   --dry-run = 只打印门槛判定与将要停止的角色，不执行任何 hc kill
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

ROOT="$(opc_root)"
PREFIX="$(opc_prefix "$ROOT")"

# 护栏：同 opc-up.sh——停止团队同样会清空所有角色的上下文，需要 owner 明确同意。
assume_yes=0
dry_run=0
roles=()
for arg in "$@"; do
  case "$arg" in
    --yes) assume_yes=1 ;;
    --dry-run) dry_run=1 ;;
    *) roles+=("$arg") ;;
  esac
done

# 判定调用来源：owner 手动在自己的终端执行 = tty；agent / 管道 / CI 调用 = non-tty
if [[ -t 0 && -t 1 ]]; then tty_flag=tty; else tty_flag=non-tty; fi

# 本次要停哪些角色（只读解析，dry-run 也要打印）
if [[ ${#roles[@]} -eq 0 ]]; then
  roles=($(opc_all_roles))
fi

# --dry-run：无副作用（只打印，不执行任何 hc kill），不受门槛限制
if [[ $dry_run -eq 1 ]]; then
  echo "dry-run：门槛判定 tty_flag=${tty_flag}，--yes=${assume_yes}。"
  if [[ $assume_yes -eq 0 && $tty_flag == non-tty ]]; then
    echo "dry-run：去掉 --dry-run，本命令会被门槛拒绝（非 TTY 且未带 --yes）。"
  else
    echo "dry-run：去掉 --dry-run，本命令会被放行。"
  fi
  echo "dry-run：本次不执行任何停止动作。"
  echo "将要停止：${roles[*]}"
  printf '%s\tscript=%s\tresult=dry-run\ttty=%s\t--yes=%s\tsession=%s\tcwd=%s\n' \
    "$(date '+%Y-%m-%d %H:%M:%S')" "opc-down" "$tty_flag" "$assume_yes" \
    "${CLAUDE_CODE_SESSION_ID:-owner-terminal}" "$PWD" >> "$ROOT/.opc/restart.log"
  exit 0
fi

# 护栏：同 opc-up.sh——停止团队同样会清空所有角色的上下文，需要 owner 明确同意。
if [[ $assume_yes -eq 0 && $tty_flag == non-tty ]]; then
  echo "拒绝执行：停止 OPC 团队会清空所有角色的会话上下文，需要 owner 明确同意。" >&2
  echo "当前调用没有 TTY（agent / 脚本 / 管道调用，tty_flag=${tty_flag}）。两种方式：" >&2
  echo "  1) owner 在自己的终端手动执行本命令；" >&2
  echo "  2) owner 明确同意后，在命令上显式加 --yes。" >&2
  echo "依据：knowledge/decisions/2026-11-04-团队重启须owner确认.md" >&2
  printf '%s\tscript=%s\tresult=blocked\ttty=%s\t--yes=%s\tsession=%s\tcwd=%s\n' \
    "$(date '+%Y-%m-%d %H:%M:%S')" "opc-down" "$tty_flag" "$assume_yes" \
    "${CLAUDE_CODE_SESSION_ID:-owner-terminal}" "$PWD" >> "$ROOT/.opc/restart.log"
  exit 2
fi

# 审计日志：真正执行停止时留痕（只记元数据，不记会话内容）
printf '%s\tscript=%s\tresult=executed\ttty=%s\t--yes=%s\tsession=%s\tcwd=%s\n' \
  "$(date '+%Y-%m-%d %H:%M:%S')" "opc-down" "$tty_flag" "$assume_yes" \
  "${CLAUDE_CODE_SESSION_ID:-owner-terminal}" "$PWD" >> "$ROOT/.opc/restart.log"

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
