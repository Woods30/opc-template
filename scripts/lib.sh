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

# 角色 CLI，默认 claude
opc_role_cli() {
  local c
  c="$(opc_role_field "$1" cli)"
  printf '%s' "${c:-claude}"
}

opc_templates_dir() { printf '%s/herdr-core/templates' "${XDG_CONFIG_HOME:-$HOME/.config}"; }
opc_layouts_dir()   { printf '%s/herdr-app/layouts'   "${XDG_CONFIG_HOME:-$HOME/.config}"; }
