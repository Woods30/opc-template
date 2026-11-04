#!/usr/bin/env bash
# OPC 脚本共享函数。由 opc-*.sh source，不单独执行。

# 项目根：scripts/ 的上一级
opc_root() {
  local here
  here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cd "$here/.." && pwd
}

# 项目前缀：OPC_PREFIX 环境变量 > .opc/prefix 文件 > 目录名 slug 化
opc_prefix() {
  local root="$1"
  if [[ -n "${OPC_PREFIX:-}" ]]; then
    printf '%s' "$OPC_PREFIX"
    return
  fi
  if [[ -f "$root/.opc/prefix" ]]; then
    cat "$root/.opc/prefix"
    return
  fi
  basename "$root" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]/-/g'
}

# ---- 角色注册表 roles.json ----

opc_roles_file() { printf '%s/roles.json' "$(opc_root)"; }

# 已启用的角色（按 roles.json 顺序）
opc_roles() {
  jq -r '.roles[] | select(.enabled) | .name' "$(opc_roles_file)"
}

# 全部角色（含停用）
opc_all_roles() {
  jq -r '.roles[].name' "$(opc_roles_file)"
}

opc_role_exists() {
  jq -e --arg n "$1" '.roles[] | select(.name==$n)' "$(opc_roles_file)" >/dev/null 2>&1
}

opc_role_enabled() {
  [[ "$(opc_role_field "$1" enabled)" == "true" ]]
}

opc_role_field() {
  jq -r --arg n "$1" --arg f "$2" \
    '.roles[] | select(.name==$n) | .[$f] // empty' "$(opc_roles_file)"
}

# 某角色可写的子树（相对项目根）
opc_role_scope() {
  jq -r --arg n "$1" '.roles[] | select(.name==$n) | .scope[]?' "$(opc_roles_file)"
}

# 角色模板源路径，默认 agents/opc-<name>.md
opc_role_template() {
  local t
  t="$(opc_role_field "$1" template)"
  printf '%s' "${t:-agents/opc-$1.md}"
}

# 角色级权限扩展：roles.json 里每个角色可带
#   "allow": [...]           追加的放行规则
#   "deny": [...]            追加的拒绝规则
#   "approvedSkills": [...]  逐个批准的技能名（生成精确的 Skill(名字) 规则）
# 三者都是实例主权：模版新增角色才并入，已有角色一个字段都不改。
opc_role_list() {
  jq -r --arg n "$1" --arg f "$2" \
    '.roles[] | select(.name==$n) | .[$f][]? // empty' "$(opc_roles_file)"
}

# 角色 CLI，默认 claude
opc_role_cli() {
  local c
  c="$(opc_role_field "$1" cli)"
  printf '%s' "${c:-claude}"
}

opc_templates_dir() { printf '%s/herdr-core/templates' "${XDG_CONFIG_HOME:-$HOME/.config}"; }
opc_layouts_dir()   { printf '%s/herdr-app/layouts'   "${XDG_CONFIG_HOME:-$HOME/.config}"; }

# ---- 各 CLI 的 Skill 与权限模型 ----
# 不同 CLI 的「技能在哪」和「谁来批」不是一回事，OPC 不能把 Claude 的规则
# 直接套给别的 CLI。这些函数是唯一的口径来源：安装器、名册、状态脚本共用。

opc_cli_skill_source() {
  case "$(basename "$1")" in
    claude)
      printf '%s' '.claude/skills/、~/.claude/skills/、插件 skills/（插件技能名为 plugin:skill）' ;;
    codex)
      printf '%s' '.agents/skills/、~/.agents/skills/、/etc/codex/skills/' ;;
    *)
      printf '%s' '由该 CLI 自行决定（OPC 不接管）' ;;
  esac
}

opc_cli_permission_model() {
  case "$(basename "$1")" in
    claude)
      printf '%s' 'settings.json 的 allow/ask/deny + permission-mode；Skill 调用需 permissions.allow 含 "Skill"' ;;
    codex)
      printf '%s' '--sandbox / --ask-for-approval / --approve-for-me / --dangerously-bypass-approvals-and-sandbox；没有 Skill 工具权限，Skill 由原生发现机制决定' ;;
    *)
      printf '%s' 'OPC 不接管该 CLI 的权限与审批，请自行确认其语义' ;;
  esac
}

# Claude 角色的权限由 OPC 生成并托管；其他 CLI 走各自原生机制。
opc_cli_managed_permissions() {
  [[ "$(basename "$1")" == "claude" ]]
}

# ---- 权限模式 → 各 CLI 自己的参数 ----
# permissionMode 是 OPC 的统一叫法，每个 CLI 表达「跳过审批」的方式不同。
# 这里是唯一的映射口径：安装器只认这张表，不把 Claude 的参数硬塞给别的 CLI。

# 该 CLI 支持哪些权限模式（空格分隔）；空串表示 OPC 不接管，按 CLI 默认跑。
opc_cli_permission_modes() {
  case "$(basename "$1")" in
    claude|codex)
      printf '%s' 'default manual auto acceptEdits plan dontAsk bypassPermissions' ;;
    *)
      printf '%s' '' ;;
  esac
}

# 模式 → 该 CLI 的启动参数（只含该 CLI 认识的开关，不含 CLI 本身）。
# 语义对齐：
#   default/manual   → 常规审批
#   acceptEdits      → 文件编辑自动放行
#   auto             → 自动评审代替人审批（codex: --approve-for-me）
#   plan             → 只读探查
#   dontAsk          → 不弹窗，需要审批的一律失败
#   bypassPermissions→ 跳过审批与沙箱（官方定位：只在隔离环境里用）
opc_cli_permission_args() {
  local cli="$1" mode="$2"
  case "$(basename "$cli")" in
    claude)
      printf '%s' "--permission-mode $mode" ;;
    codex)
      case "$mode" in
        default|manual|acceptEdits) printf '%s' '--sandbox workspace-write --ask-for-approval on-request' ;;
        auto)                         printf '%s' '--approve-for-me --sandbox workspace-write' ;;
        plan)                         printf '%s' '--sandbox read-only --ask-for-approval on-request' ;;
        dontAsk)                      printf '%s' '--sandbox workspace-write --ask-for-approval never' ;;
        bypassPermissions)            printf '%s' '--dangerously-bypass-approvals-and-sandbox' ;;
        *)                            printf '%s' '' ;;
      esac ;;
    *)
      printf '%s' '' ;;
  esac
}

# ---- 模版仓库守卫 ----

# 是否是模版仓库。模版仓库只装机制与占位骨架，不承载业务数据：
# 业务内容一律长在实例仓库里（见 scripts/opc-sync.sh 与 docs/同步机制.md）。
opc_is_template_repo() {
  local root="${1:-$(opc_root)}"
  [[ -f "$root/.opc-template-repo" ]]
}

# 在模版仓库里执行实例操作时的统一提示
opc_template_repo_refusal() {
  cat >&2 <<'EOF'
这是模版仓库，不承载业务数据。
请开一个实例再干活：

  scripts/opc-new.sh <实例目录> <前缀>

实例是独立目录、独立 git 仓库，业务内容只落在那里。模版这边只改机制。
EOF
}

