#!/usr/bin/env bash
# 角色管理：列出、增加、启用、停用。改完会自动重跑安装脚本。
# 用法：
#   scripts/opc-role.sh list
#   scripts/opc-role.sh add <角色> [--cli claude] [--scope a,b] [--desc "一句话"] [--skills a,b]
#   scripts/opc-role.sh enable <角色>
#   scripts/opc-role.sh disable <角色>
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

ROOT="$(opc_root)"
REG="$(opc_roles_file)"
command -v jq >/dev/null || { echo "缺少 jq" >&2; exit 1; }

usage() { sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'; exit 1; }

reinstall() { "$ROOT/scripts/opc-install.sh" --no-input >/dev/null && echo "已重新安装（模板、权限、注册表已更新）"; }

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
    cli="claude"; scope="knowledge/work/$name"; desc="TODO：这个角色负责什么"; skills=""
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --cli)   cli="${2:?}"; shift 2 ;;
        --scope) scope="${2:?}"; shift 2 ;;
        --desc)  desc="${2:?}"; shift 2 ;;
        --skills) skills="${2:?}"; shift 2 ;;
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

    # 角色材料是目录：agents/<角色名>/AGENTS.md 是入口，目录里还可以放
    # 角色专属参考文件。入口是纯 Markdown，frontmatter 由安装器按
    # roles.json 生成，不写进角色材料。
    tpl="agents/$name/AGENTS.md"
    if [[ ! -f "$ROOT/$tpl" ]]; then
      mkdir -p "$ROOT/agents/$name"
      # 新角色的启动小节必须写明「等 gm 派工」（gm 自己先与 owner 对齐），
      # 否则角色一启动就自己开题——这正是 tools/opc-lint 的 L17 要拦的。
      if [[ "$name" == "gm" ]]; then
        startup='**然后先与 owner 对齐方向**，把结论写进 `knowledge/business/品牌口径.md`，再往其他角色派工。'
      else
        startup='**然后停下来等 gm 派工**：汇报当前状态与能承接的任务即可。'
      fi
      cat > "$ROOT/$tpl" <<EOF
你现在是 **OPC 公司的 $name**。

## 你的职责

- TODO：写清这个角色负责什么。

## 你的边界

- TODO：写清这个角色不做什么。

## 工作方式

- 动手前先读 \`knowledge/business/品牌口径.md\`、\`knowledge/work/$name/LESSONS.md\`，
  以及派给你的那张任务卡（\`knowledge/tasks/<task_id>.md\`）。
- 产出写进自己负责的子树，命名带日期。
- 完成后用 \`tools/opc-workflow complete-task <task_id> --result "<一句话结论与产出路径>"\`
  写完成态——完成态由工具写入任务卡，你不手工改卡；再用
  \`hc send {{PREFIX}}-gm "完成：<一句话结论> | 产出：<文件路径>"\` 通知下游或 gm。
- 拿不准时用 \`hc send {{PREFIX}}-gm\` 说明问题，请求裁决；**不要直接改别人的任务卡**。

## 启动

你现在在 OPC 项目根目录。**只读三件套**：品牌口径（\`knowledge/business/品牌口径.md\`）、
本角色的经验教训（\`knowledge/work/$name/LESSONS.md\`）、本次任务的详情（任务卡）。
其余一律不读：不读整个业务目录，不读已完成的条目，不读别人的任务卡。

$startup
EOF
      echo "已创建角色简报：${tpl}（请补全职责与边界）"
    fi
    [[ -f "$ROOT/agents/$name/CLAUDE.md" ]] || printf '%s\n' '@AGENTS.md' > "$ROOT/agents/$name/CLAUDE.md"
    [[ -f "$ROOT/agents/$name/GEMINI.md" ]] || printf '%s\n' '@./AGENTS.md' > "$ROOT/agents/$name/GEMINI.md"

    scope_json=$(printf '%s' "$scope" | tr ',' '\n' | sed '/^$/d' \
      | jq -R . | jq -s .)
    # 技能名要能安全地拼进 skills/<name>/SKILL.md，挡住路径穿越。
    skills_json="[]"
    if [[ -n "$skills" ]]; then
      skill_names=()
      for s in $(printf '%s' "$skills" | tr ',' '\n' | sed '/^$/d'); do
        opc_safe_skill_name "$s" || { echo "技能名不合法：$s" >&2; exit 1; }
        skill_names+=("$s")
      done
      skills_json=$(printf '%s\n' "${skill_names[@]}" | jq -R . | jq -s .)
    fi
    for s in $(printf '%s' "$scope" | tr ',' '\n' | sed '/^$/d'); do
      # scope 必须是实例内的相对路径
      case "$s" in
        /*|*..*|*"'"*|*'"'*|*" "*)
          echo "scope 不合法：$s" >&2; exit 1 ;;
      esac
      # 文件 scope 不建目录；目录 scope 才建
      case "$s" in
        *.md|*.json|*.txt|*.png|*.svg|*.sh|*.py) ;;
        *) mkdir -p "$ROOT/$s" ;;
      esac
    done

    tmp="$(mktemp)"
    jq --arg n "$name" --arg cli "$cli" --arg tpl "$tpl" --arg desc "$desc" \
       --argjson scope "$scope_json" --argjson skills "$skills_json" \
      '.roles += [{name:$n, enabled:true, cli:$cli, description:$desc, template:$tpl, skills:$skills, permissionMode:"bypassPermissions", scope:$scope, approvedSkills:[]}]' \
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
