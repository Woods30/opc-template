#!/usr/bin/env bash
# 角色管理：列出、增加、启用、停用。改完会自动重跑安装脚本。
# 用法：
#   scripts/opc-role.sh list
#   scripts/opc-role.sh add <角色> [--cli claude] [--scope a,b] [--desc "一句话"]
#   scripts/opc-role.sh enable <角色>
#   scripts/opc-role.sh disable <角色>
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

ROOT="$(opc_root)"
REG="$(opc_roles_file)"
command -v jq >/dev/null || { echo "缺少 jq" >&2; exit 1; }

usage() { sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

reinstall() { "$ROOT/scripts/opc-install.sh" >/dev/null && echo "已重新安装（模板、权限、名册已更新）"; }

cmd="${1:-}"; shift || true

case "$cmd" in
  list)
    printf '%-12s %-6s %-8s %s\n' 角色 启用 CLI 可写子树
    printf '%-12s %-6s %-8s %s\n' ---- ---- --- --------
    for r in $(opc_all_roles); do
      if opc_role_enabled "$r"; then e="是"; else e="否"; fi
      printf '%-12s %-6s %-8s %s\n' "$r" "$e" "$(opc_role_cli "$r")" \
        "$(opc_role_scope "$r" | paste -sd ',' - | sed 's/,/, /g')"
    done
    ;;

  add)
    name="${1:-}"; [[ -n "$name" ]] || usage; shift || true
    cli="claude"; scope="knowledge/$name"; desc="TODO：这个角色负责什么"
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --cli)   cli="${2:?}"; shift 2 ;;
        --scope) scope="${2:?}"; shift 2 ;;
        --desc)  desc="${2:?}"; shift 2 ;;
        *) echo "未知参数：$1" >&2; exit 1 ;;
      esac
    done

    [[ "$name" =~ ^[a-z][a-z0-9_-]{0,19}$ ]] || {
      echo "角色名不合法：${name}（1-20 位 a-z 0-9 - _，以字母开头）" >&2; exit 1; }
    [[ "$cli" =~ ^[A-Za-z0-9/._-]+$ ]] || {
      echo "cli 不合法：${cli}（单个可执行文件名或路径，不含参数）" >&2; exit 1; }
    case "$desc" in
      *$'\n'*) echo "desc 不能包含换行" >&2; exit 1 ;;
    esac
    opc_role_exists "$name" && { echo "角色已存在：$name" >&2; exit 1; }

    tpl="agents/opc-$name.md"
    if [[ ! -f "$ROOT/$tpl" ]]; then
      cat > "$ROOT/$tpl" <<EOF
---
name: {{PREFIX}}-$name
description: $desc
command: zsh -lic claude
---

你现在是 **OPC 公司的 $name**。

## 你的职责

- TODO：写清这个角色负责什么。

## 你的边界

- TODO：写清这个角色不做什么。

## 工作方式

- 动手前先读 \`AGENTS.md\` 与 \`knowledge/team.md\`。
- 产出写进自己负责的子树，命名带日期。
- 完成后 \`hc send {{PREFIX}}-gm "完成：<文件路径>"\`。
- 拿不准时写 \`knowledge/inbox/gm.md\` 并 \`hc send {{PREFIX}}-gm\`。

## 启动

你现在在 OPC 项目根目录。先读 \`AGENTS.md\` 了解共享规约，再读 \`knowledge/team.md\`
确认其他角色的终端名，然后读 \`knowledge/\` 下的已有内容，最后告诉我你打算先做什么。
EOF
      echo "已创建角色简报：${tpl}（请补全职责与边界）"
    fi

    inbox="$ROOT/knowledge/inbox/$name.md"
    if [[ ! -f "$inbox" ]]; then
      printf '# %s 收件箱\n\n派工与上报都追加到本文件末尾，一行一条，最新的在最下面。格式：\n\n```\n- [YYYY-MM-DD HH:MM] 发起方：<角色> | 任务：<做什么> | 验收：<怎么算完成>\n```\n\n派工后 `hc send <前缀>-%s` 通知。\n\n---\n' \
        "$name" "$name" > "$inbox"
      echo "已创建收件箱：knowledge/inbox/$name.md"
    fi

    scope_json=$(printf '%s' "$scope" | tr ',' '\n' | sed '/^$/d' \
      | jq -R . | jq -s .)
    for s in $(printf '%s' "$scope" | tr ',' '\n' | sed '/^$/d'); do
      # scope 必须是实例内的相对路径
      case "$s" in
        /*|*..*|*"'"*|*'"'*|*" "*)
          echo "scope 不合法：$s" >&2; exit 1 ;;
      esac
      mkdir -p "$ROOT/$s"
    done

    tmp="$(mktemp)"
    jq --arg n "$name" --arg cli "$cli" --arg tpl "$tpl" --argjson scope "$scope_json" \
      '.roles += [{name:$n, enabled:true, cli:$cli, template:$tpl, scope:$scope}]' \
      "$REG" > "$tmp" && mv "$tmp" "$REG"
    echo "已加入 roles.json：${name}（CLI ${cli}）"
    reinstall
    ;;

  enable|disable)
    name="${1:-}"; [[ -n "$name" ]] || usage
    opc_role_exists "$name" || { echo "角色不存在：$name" >&2; exit 1; }
    if [[ "$cmd" == "enable" ]]; then val=true; else val=false; fi
    tmp="$(mktemp)"
    jq --arg n "$name" --argjson v "$val" \
      '(.roles[] | select(.name==$n) | .enabled) = $v' "$REG" > "$tmp" && mv "$tmp" "$REG"
    echo "已$([[ "$cmd" == "enable" ]] && echo 启用 || echo 停用)：$name"
    reinstall
    ;;

  *) usage ;;
esac
