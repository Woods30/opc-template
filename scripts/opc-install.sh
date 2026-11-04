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
# 路径会写进生成的启动器（单引号字符串），拒绝能逃出引号的字符
case "$ROOT" in
  *"'"*|*$'\n'*)
    echo "项目路径不能包含单引号或换行：$ROOT" >&2
    exit 1 ;;
esac

mkdir -p "$TEMPLATES" "$ROOT/.opc/run"
printf '%s' "$PREFIX" > "$ROOT/.opc/prefix"

roles="$(opc_roles)"
[[ -n "$roles" ]] || { echo "roles.json 里没有启用的角色" >&2; exit 1; }

# 1. 生成 hc 模板与启动器（模板名全局唯一，带前缀）
for role in $roles; do
  [[ "$role" =~ ^[a-z][a-z0-9_-]{0,19}$ ]] || {
    echo "角色名不合法：${role}（1-20 位 a-z 0-9 - _，以字母开头）" >&2
    exit 1
  }
  src="$ROOT/$(opc_role_template "$role")"
  [[ -f "$src" ]] || { echo "缺少角色简报：$src" >&2; exit 1; }

  # cli 是单个可执行文件名或路径，不接受参数——它会被写进启动器
  cli="$(opc_role_cli "$role")"
  [[ "$cli" =~ ^[A-Za-z0-9/._-]+$ ]] || {
    echo "角色 $role 的 cli 不合法：${cli}（只允许单个可执行文件名或路径，不含参数）" >&2
    exit 1
  }

  # 值走环境变量，shell 字符串是常量：配置内容不会被当成命令执行
  if [[ "$cli" == "claude" ]]; then
    mode="$(opc_role_field "$role" permissionMode)"
    mode="${mode:-default}"
    case "$mode" in
      default|manual|auto|acceptEdits|plan|dontAsk) ;;
      bypassPermissions)
        echo "角色 $role 的 permissionMode 不能是 bypassPermissions（会架空全部权限）" >&2
        exit 1 ;;
      *) echo "角色 $role 的 permissionMode 不合法：${mode}" >&2; exit 1 ;;
    esac
    cat > "$ROOT/.opc/run/$role.sh" <<EOF
#!/bin/sh
# 由 scripts/opc-install.sh 生成，勿手改。重新安装请重跑安装脚本。
OPC_ROOT='$ROOT'
OPC_SETTINGS='$ROOT/.opc/settings-$role.json'
export OPC_ROOT OPC_SETTINGS
exec /bin/zsh -lic 'cd "\$OPC_ROOT" && exec claude --settings "\$OPC_SETTINGS" --permission-mode $mode'
EOF
  else
    cat > "$ROOT/.opc/run/$role.sh" <<EOF
#!/bin/sh
# 由 scripts/opc-install.sh 生成，勿手改。重新安装请重跑安装脚本。
OPC_ROOT='$ROOT'
OPC_CLI='$cli'
export OPC_ROOT OPC_CLI
exec /bin/zsh -lic 'cd "\$OPC_ROOT" && exec "\$OPC_CLI"'
EOF
  fi
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
  # 只读命令白名单：只放行「参数面内不能写文件、也不能执行外部程序」的命令，
  # 避免每个角色查文件都弹审批。
  # 不放行 cp/mv/tee/sed/awk 等可写命令——它们会绕过下面的 Edit 子树隔离。
  # 不放行 find/rg/sort/tree/echo/uniq/file：
  #   find -exec/-delete/-fprint*、rg --pre、sort -o/--compress-program、
  #   tree -o、echo 重定向、uniq 的可选输出文件参数、file -C 编译 magic，
  #   都能写文件或执行任意程序。
  # 不放行 shell 循环（for/while）：Claude Code 预检无法静态确认，加规则也放不过。
  readonly_rules='[
    "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)",
    "Bash(grep:*)", "Bash(stat:*)",
    "Bash(diff:*)", "Bash(pwd)",
    "Bash(basename:*)", "Bash(dirname:*)", "Bash(jq:*)",
    "Bash(cd:*)", "Bash(which:*)", "Bash(date:*)", "Bash(tr:*)",
    "Bash(./tools/preflight:*)", "Bash(tools/preflight:*)",
    "Bash(python3 tools/tests/test_preflight.py)"
  ]'
  edit_rules='[]'
  for scope in $(opc_role_scope "$role"); do
    # scope 必须是实例内的相对路径，不能借 .. 逃出去
    case "$scope" in
      /*|*..*|*"'"*|*'"'*|*" "*)
        echo "角色 ${role} 的 scope 不合法：$scope" >&2
        exit 1 ;;
    esac
    # 目录 → 整棵子树；明确列出的文件 → 精确路径（不拼 /**）
    case "$scope" in
      *.md|*.json|*.txt|*.png|*.svg|*.sh|*.py) pattern="./$scope" ;;
      *) pattern="./$scope/**" ;;
    esac
    edit_rules=$(printf '%s' "$edit_rules" \
      | jq --arg p "$pattern" '. + ["Edit(" + $p + ")"]')
  done
  jq -n --argjson edit "$edit_rules" --argjson readonly "$readonly_rules" --arg prefix "$PREFIX" --arg root "$ROOT" '{
    "$schema": "https://json.schemastore.org/claude-code-settings.json",
    "permissions": {
      "defaultMode": "default",
      "allow": ([
        "Bash(hc send \($prefix)-*)",
        "Bash(hc ls:*)",
        "Bash(hc read \($prefix)-*)",
        "Bash(hc get \($prefix)-*)",
        "Bash(hc templates:*)",
        "Bash(hc wait \($prefix)-*)",
        "Bash(hc --help)"
      ] + $readonly + $edit),
      "ask": [
        "Bash(hc kill:*)",
        "Bash(hc server stop:*)",
        "Bash(hc server restart:*)",
        "Bash(scripts/opc-down.sh:*)",
        "Bash(scripts/opc-up.sh:*)",
        "Bash(bash scripts/opc-down.sh:*)",
        "Bash(bash scripts/opc-up.sh:*)",
        "Bash(sh scripts/opc-down.sh:*)",
        "Bash(sh scripts/opc-up.sh:*)",
        "Bash(./scripts/opc-down.sh:*)",
        "Bash(./scripts/opc-up.sh:*)",
        "Bash(\($root)/scripts/opc-down.sh:*)",
        "Bash(\($root)/scripts/opc-up.sh:*)",
        "Bash(herdr-app do terminal.kill:*)",
        "Bash(script:*)",
        "Bash(expect:*)",
        "Bash(socat:*)",
        "Bash(unbuffer:*)"
      ],
      "deny": [
        "Bash(git:*)",
        "Bash(rm:*)",
        "Bash(sudo:*)",
        "Bash(hc keys:*)"
      ]
    }
  }' > "$ROOT/.opc/settings-$role.json"
done

# 2b. 每个启用角色的工作目录与经验教训文件（过程记录，进版本库）
for role in $roles; do
  mkdir -p "$ROOT/knowledge/work/$role"
  if [[ ! -f "$ROOT/knowledge/work/$role/LESSONS.md" ]]; then
    printf '# %s 的经验教训\n\n本角色的经验教训，只追加、不改别人的条目。gm 每周汇总到根目录 `LESSONS.md`。\n\n每条固定三行，带日期：\n\n```markdown\n## YYYY-MM-DD · %s\n- 教训：一句话说清踩了什么坑\n- 触发场景：什么情况下会再踩到\n- 以后怎么做：下次的具体动作\n```\n' \
      "$role" "$role" > "$ROOT/knowledge/work/$role/LESSONS.md"
  fi
done

# 2b-2. 固定目录、收件箱与目录型 scope（只建缺失的，不覆盖已有内容）
mkdir -p "$ROOT/knowledge/review" "$ROOT/knowledge/decisions" \
         "$ROOT/knowledge/daily" "$ROOT/knowledge/inbox"
for role in $roles; do
  inbox="$ROOT/knowledge/inbox/$role.md"
  if [[ ! -f "$inbox" ]]; then
    printf '# %s 收件箱\n\n派工与上报都追加到本文件末尾，一行一条，最新的在最下面。格式：\n\n```\n- [YYYY-MM-DD HH:MM] 发起方：<角色> | 任务：<做什么> | 验收：<怎么算完成>\n```\n\n派工后 `hc send <前缀>-%s` 通知。\n\n**只执行行首既无 `✅` 也无 `⛔` 的条目。** 发起方收到「完成」回报后在该条目行首加 `✅`；撤销时在行首加 `⛔ 已撤销：<原因>`。详见 `AGENTS.md`「状态来源」一节。\n\n---\n\n## 当前队列\n\n（空）\n' \
      "$role" "$role" > "$inbox"
  fi
  # 目录型 scope 一并建出来，避免角色第一次写文件时目录不存在
  while IFS= read -r scope; do
    [[ -n "$scope" ]] || continue
    case "$scope" in
      *.*) ;;
      *) mkdir -p "$ROOT/$scope" ;;
    esac
  done <<< "$(opc_role_scope "$role")"
done

# 2c. 频道目录（channels.json 驱动）：只建启用的频道；已存在的目录不删
CHANNELS_FILE="$ROOT/channels.json"
if [[ -f "$CHANNELS_FILE" ]]; then
  mkdir -p "$ROOT/knowledge/business"
  for cid in $(jq -r '.channels[] | select(.enabled) | .id' "$CHANNELS_FILE"); do
    [[ "$cid" =~ ^[a-z][a-z0-9-]{0,19}$ ]] || {
      echo "频道 id 不合法：${cid}（1-20 位 a-z 0-9 -，以字母开头）" >&2
      exit 1
    }
    mkdir -p "$ROOT/knowledge/business/$cid/assets"
    if [[ ! -f "$ROOT/knowledge/business/$cid/发布记录.md" ]]; then
      printf '# %s 发布记录\n\n| 日期 | 标题 | 版本 | 状态 | 链接 / 备注 |\n|---|---|---|---|---|\n' \
        "$cid" > "$ROOT/knowledge/business/$cid/发布记录.md"
    fi
  done
  # 索引按 channels.json 的数组顺序生成，不手改
  {
    echo "# 业务目录索引"
    echo
    echo "> 本文件由 \`scripts/opc-install.sh\` 生成，**不要手改**。频道清单见 \`channels.json\`。"
    echo
    echo "| 频道 | 目录 | 状态 |"
    echo "|---|---|---|"
    jq -r '.channels[] | "| \(.name) | `\(.id)/` | \(if .enabled then "启用" else "停用" end) |"' "$CHANNELS_FILE"
    echo
    echo "常驻文档：\`品牌口径.md\`、\`选题日历.md\`（content 维护）。"
    echo "业务线：\`growth/\`（增长）、\`product/\`（产品）。"
  } > "$ROOT/knowledge/business/README.md"
fi

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
    scope_md=""
    while IFS= read -r s; do
      [[ -n "$s" ]] || continue
      case "$s" in
        *.md|*.json|*.txt|*.png|*.svg|*.sh|*.py) item="\`$s\`" ;;
        *) item="\`$s/\`" ;;
      esac
      [[ -z "$scope_md" ]] && scope_md="$item" || scope_md="${scope_md}、$item"
    done <<< "$(opc_role_scope "$role")"
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
  # opc.json 装成 <前缀>.json（主布局）；其余 <名字>.json 装成 <前缀>-<名字>.json
  for f in "$ROOT"/layouts/*.json; do
    [[ -f "$f" ]] || continue
    name="$(basename "$f" .json)"
    if [[ "$name" == "opc" ]]; then
      target="$LAYOUTS/$PREFIX.json"
    else
      target="$LAYOUTS/$PREFIX-$name.json"
    fi
    cp "$f" "$target"
    [[ -f "$ROOT/layouts/$name.svg" ]] && cp "$ROOT/layouts/$name.svg" "${target%.json}.svg"
  done
fi

echo "已安装 OPC 实例：前缀 $PREFIX"
echo "  角色：$(echo $roles | tr ' ' ', ')"
echo "  模板：$TEMPLATES/$PREFIX-<角色>.md"
echo "  权限：$ROOT/.opc/settings-<角色>.json（仅 claude 角色）"
echo "  名册：$ROOT/knowledge/team.md"
echo "下一步：scripts/opc-up.sh [角色...]"
