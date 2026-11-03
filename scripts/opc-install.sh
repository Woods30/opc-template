#!/usr/bin/env bash
# 安装 OPC 实例：按 roles.json 生成 hc 模板、权限白名单、启动器与团队名册。
# 用法：scripts/opc-install.sh [前缀]
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

ROOT="$(opc_root)"
PREFIX="${1:-$(opc_prefix "$ROOT")}"
TEMPLATES="$(opc_templates_dir)"
LAYOUTS="$(opc_layouts_dir)"

[[ -f "$(opc_roles_file)" ]] || { echo "缺少 roles.json" >&2; exit 1; }
command -v jq >/dev/null || { echo "缺少 jq" >&2; exit 1; }

[[ "$PREFIX" =~ ^[a-z0-9][a-z0-9_-]{0,30}$ ]] || {
  echo "前缀不合法：${PREFIX}（只允许 1-31 位 a-z 0-9 - _，且以字母数字开头）" >&2
  exit 1
}
[[ "$ROOT" != *" "* ]] || {
  echo "项目路径含空格：$ROOT —— hc 模板的 command 会被空格拆开，请把实例放到无空格路径。" >&2
  exit 1
}

mkdir -p "$TEMPLATES" "$ROOT/.opc/run"
printf '%s' "$PREFIX" > "$ROOT/.opc/prefix"

roles="$(opc_roles)"
[[ -n "$roles" ]] || { echo "roles.json 里没有启用的角色" >&2; exit 1; }

# 1. 生成 hc 模板与启动器（模板名全局唯一，带前缀）
for role in $roles; do
  src="$ROOT/$(opc_role_template "$role")"
  [[ -f "$src" ]] || { echo "缺少角色简报：$src" >&2; exit 1; }

  cli="$(opc_role_cli "$role")"
  if [[ "$cli" == "claude" ]]; then
    inner="exec claude --settings '$ROOT/.opc/settings-$role.json' --permission-mode default"
  else
    inner="exec $cli"
  fi
  cat > "$ROOT/.opc/run/$role.sh" <<EOF
#!/bin/sh
# 由 scripts/opc-install.sh 生成，勿手改。重新安装请重跑安装脚本。
exec /bin/zsh -lic "cd '$ROOT' && $inner"
EOF
  chmod +x "$ROOT/.opc/run/$role.sh"

  sed -e "s/{{PREFIX}}/$PREFIX/g" \
      -e "s#^command:.*#command: $ROOT/.opc/run/$role.sh#" \
      "$src" > "$TEMPLATES/$PREFIX-$role.md"
done

# 1b. 已停用的角色：删掉旧模板，否则 hc templates 里还看得见
for role in $(jq -r '.roles[] | select(.enabled | not) | .name' "$(opc_roles_file)"); do
  rm -f "$TEMPLATES/$PREFIX-$role.md"
done

# 2. 每角色一份权限白名单（只对 claude 角色有意义）
for role in $roles; do
  if [[ "$(opc_role_cli "$role")" != "claude" ]]; then
    rm -f "$ROOT/.opc/settings-$role.json"
    continue
  fi
  edit_rules='[]'
  for scope in $(opc_role_scope "$role"); do
    edit_rules=$(printf '%s' "$edit_rules" \
      | jq --arg p "./$scope/**" '. + ["Edit(" + $p + ")"]')
  done
  jq -n --argjson edit "$edit_rules" '{
    "$schema": "https://json.schemastore.org/claude-code-settings.json",
    "permissions": {
      "defaultMode": "default",
      "allow": ([
        "Bash(hc send:*)",
        "Bash(hc ls:*)",
        "Bash(hc read:*)",
        "Bash(hc templates:*)",
        "Bash(hc wait:*)"
      ] + $edit),
      "deny": [
        "Bash(git push:*)",
        "Bash(git reset --hard:*)",
        "Bash(rm -rf:*)"
      ]
    }
  }' > "$ROOT/.opc/settings-$role.json"
done

# 3. 团队名册（角色引用终端名时的唯一权威来源）
{
  echo "# 团队名册"
  echo
  echo "> 本文件由 \`scripts/opc-install.sh\` 生成，**不要手改**。"
  echo "> 改角色请编辑 \`roles.json\`，或跑 \`scripts/opc-role.sh\`。"
  echo
  echo "| 角色 | 终端名 | 模板名 | CLI | 负责的子树 |"
  echo "|---|---|---|---|---|"
  for role in $roles; do
    scope_md="$(opc_role_scope "$role" | sed 's#^#`#; s#$#/`#' | paste -sd ',' - | sed 's/,/、/g')"
    echo "| $role | \`$PREFIX-$role\` | \`$PREFIX-$role\` | $(opc_role_cli "$role") | $scope_md |"
  done
  echo
  echo "\`hc send <终端名> \"<消息>\"\` 用的是上表的终端名。查当前存活终端用 \`hc ls\`。"
  echo
  disabled="$(jq -r '.roles[] | select(.enabled | not) | .name' "$(opc_roles_file)" | paste -sd ', ' -)"
  [[ -z "$disabled" ]] || echo "已停用（不启动、不生成模板）：$disabled"
} > "$ROOT/knowledge/team.md"

# 4. 布局（可选，存在才装）
if [[ -f "$ROOT/layouts/opc.json" ]]; then
  mkdir -p "$LAYOUTS"
  cp "$ROOT/layouts/opc.json" "$LAYOUTS/$PREFIX.json"
  [[ -f "$ROOT/layouts/opc.svg" ]] && cp "$ROOT/layouts/opc.svg" "$LAYOUTS/$PREFIX.svg"
fi

echo "已安装 OPC 实例：前缀 $PREFIX"
echo "  角色：$(echo $roles | tr ' ' ', ')"
echo "  模板：$TEMPLATES/$PREFIX-<角色>.md"
echo "  权限：$ROOT/.opc/settings-<角色>.json（仅 claude 角色）"
echo "  名册：$ROOT/knowledge/team.md"
echo "下一步：scripts/opc-up.sh [角色...]"
