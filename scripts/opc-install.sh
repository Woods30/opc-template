#!/usr/bin/env bash
# 安装 OPC 实例：按 roles.json 生成 hc 模板、权限白名单、启动器与团队名册。
# 用法：scripts/opc-install.sh [前缀]
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

ROOT="$(opc_root)"
PREFIX="${1:-$(opc_prefix "$ROOT")}"
TEMPLATES="$(opc_templates_dir)"
LAYOUTS="$(opc_layouts_dir)"

# 模版仓库不承载业务数据：在这里装实例等于把业务写进模版，直接拒绝
if opc_is_template_repo "$ROOT"; then
  opc_template_repo_refusal
  exit 2
fi

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

# 旧版曾为 codex 生成项目级 scope hook；它依赖调用方可控的 OPC_ROLE，不能作为
# 权限边界。新版把权限完全交给 roles.json → CLI 原生参数。只删除结构完全匹配
# 旧生成物的 hooks.json，用户自己的项目 hook 原样保留。
legacy_codex_hooks="$ROOT/.codex/hooks.json"
if [[ -f "$legacy_codex_hooks" ]] && jq -e --arg root "$ROOT" '
  (keys == ["hooks"]) and
  (.hooks | keys == ["PreToolUse"]) and
  (.hooks.PreToolUse | type == "array" and length > 0) and
  all(.hooks.PreToolUse[];
    ((.matcher == "Bash") or (.matcher == "apply_patch")) and
    (.hooks | type == "array" and length == 1) and
    (.hooks[0].type == "command") and
    (.hooks[0].command | type == "string") and
    (.hooks[0].command | startswith("/bin/sh ") and contains($root + "/.opc/hooks/scope-"))
  )
' "$legacy_codex_hooks" >/dev/null 2>&1; then
  rm -f "$legacy_codex_hooks"
fi
rm -f "$ROOT/.opc/hooks"/scope-*.sh

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
  # cli 会被写进启动器并执行：只允许干净的绝对路径或 PATH 里的裸名字。
  # 相对跳转（../）会让启动器指向别处，- 开头会被当成选项。
  [[ "$cli" != -* ]] || {
    echo "角色 $role 的 cli 不能以 - 开头：${cli}" >&2
    exit 1
  }
  case "/$cli/" in
    */../*) echo "角色 $role 的 cli 路径不能包含 ..：${cli}" >&2; exit 1 ;;
  esac

  # 权限模式统一翻成各 CLI 自己的语义：OPC 不把 claude 的参数硬塞给别的 CLI。
  # 口径在 lib.sh（opc_cli_permission_modes / opc_cli_permission_args），这里只调用。
  #   claude —— --permission-mode <mode>，另有 settings-<角色>.json 托管规则
  #   codex  —— --sandbox / --ask-for-approval / --approve-for-me /
  #             --dangerously-bypass-approvals-and-sandbox
  #   其他   —— 不接管权限，按该 CLI 默认跑，装完提示 owner 自己确认语义
  mode="$(opc_role_field "$role" permissionMode)"
  mode="${mode:-default}"
  valid_modes="$(opc_cli_permission_modes "$cli")"
  if [[ -n "$valid_modes" ]]; then
    case " $valid_modes " in
      *" $mode "*) ;;
      *) echo "角色 $role 的 permissionMode 不合法：${mode}" >&2; exit 1 ;;
    esac
  fi
  perm_args="$(opc_cli_permission_args "$cli" "$mode")"

  cli_base="$(basename "$cli")"
  # 只有 claude 走 settings-<角色>.json；别的 CLI 用各自的原生参数
  if [[ "$cli_base" == "claude" ]]; then
    extra_args='--settings "$OPC_SETTINGS"'
  else
    extra_args=''
  fi
  cat > "$ROOT/.opc/run/$role.sh" <<EOF
#!/bin/sh
# 由 scripts/opc-install.sh 生成，勿手改。重新安装请重跑安装脚本。
OPC_ROOT='$ROOT'
OPC_SETTINGS='$ROOT/.opc/settings-$role.json'
OPC_CLI='$cli'
# 仅供 workflow 记录业务 actor，不参与权限判断；权限由各 CLI 原生机制决定。
OPC_ROLE='$role'
export OPC_ROOT OPC_SETTINGS OPC_CLI OPC_ROLE
# 用登录 shell 启动：CLI 常由 npm 或版本管理器装，只有交互登录环境的 PATH 里可见。
# zsh → bash → sh 依次回退——不是所有发行版都装了 zsh，写死它的绝对路径会让角色起不来。
for _sh in zsh bash sh; do
  _p="\$(command -v "\$_sh" 2>/dev/null)" || continue
  case "\$_sh" in
    sh) exec "\$_p" -lc 'cd "\$OPC_ROOT" && exec "\$OPC_CLI" $perm_args $extra_args' ;;
    *) exec "\$_p" -lic 'cd "\$OPC_ROOT" && exec "\$OPC_CLI" $perm_args $extra_args' ;;
  esac
done
echo "OPC：找不到可用的 shell（zsh / bash / sh）" >&2
exit 127
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
    "Bash(python3 tools/tests/test_preflight.py)",
    "Bash(python3 tools/tests/test_opc_lint.py)"
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
  # 技能：只放行 owner 逐个批准的技能，生成精确的 Skill(名字) 规则。
  # 不放行裸 Skill——技能 frontmatter 里的 allowed-tools 会在调用那一轮临时
  # 预授权工具，裸 Skill 等于把角色的工具面交给任意技能。
  skill_rules='[]'
  while IFS= read -r s; do
    [[ -n "$s" ]] || continue
    [[ "$s" =~ ^[A-Za-z0-9][A-Za-z0-9._:-]*$ ]] || {
      echo "角色 $role 的 approvedSkills 名字不合法：${s}" >&2
      exit 1
    }
    skill_rules="$(printf '%s' "$skill_rules" | jq --arg n "$s" '. + ["Skill(" + $n + ")"]')"
  done < <(opc_role_list "$role" approvedSkills)

  # 角色级扩展：roles.json 里 per-role 的 allow / deny
  extra_allow='[]'
  while IFS= read -r r; do
    [[ -n "$r" ]] || continue
    extra_allow="$(printf '%s' "$extra_allow" | jq --arg r "$r" '. + [$r]')"
  done < <(opc_role_list "$role" allow)
  extra_deny='[]'
  while IFS= read -r r; do
    [[ -n "$r" ]] || continue
    extra_deny="$(printf '%s' "$extra_deny" | jq --arg r "$r" '. + [$r]')"
  done < <(opc_role_list "$role" deny)

  jq -n --argjson edit "$edit_rules" --argjson readonly "$readonly_rules" \
        --argjson skills "$skill_rules" --argjson extra_allow "$extra_allow" \
        --argjson extra_deny "$extra_deny" \
        --arg prefix "$PREFIX" --arg root "$ROOT" '{
    "$schema": "https://json.schemastore.org/claude-code-settings.json",
    "permissions": {
      "defaultMode": "default",
      # 文件工具在任何权限模式下都拒绝写工作目录之外的路径（含 bypassPermissions）。
      # 角色的「只能在实例里操作」由这条兜底，不靠 allow 规则——bypass 下 allow 无效。
      "blockWritesOutsideWorkingDirectories": true,
      "allow": ([
        "Bash(hc send \($prefix)-*)",
        "Bash(hc ls:*)",
        "Bash(hc read \($prefix)-*)",
        "Bash(hc get \($prefix)-*)",
        "Bash(hc templates:*)",
        "Bash(hc wait \($prefix)-*)",
        "Bash(hc --help)"
      ] + $skills + $readonly + $edit + $extra_allow),
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
      # deny 规则在所有权限模式下都生效，bypassPermissions 也不例外——
      # 这几道闸门是 bypass 模式下唯一还在拦的东西。
      "deny": ([
        "Bash(git:*)",
        "Bash(rm:*)",
        "Bash(sudo:*)",
        "Bash(hc keys:*)",
        "Read(~/.ssh/**)",
        "Read(~/.aws/**)",
        "Read(~/.gnupg/**)",
        "Read(~/.config/gh/**)",
        "Read(~/.netrc)",
        "Read(~/.npmrc)"
      ] + $extra_deny)
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
# canonical 内容区与 workflow 的事实入口；review/ 与 daily/ 是旧操作模型，不再创建。
mkdir -p "$ROOT/knowledge/content" "$ROOT/knowledge/decisions" \
         "$ROOT/knowledge/inbox"
for role in $roles; do
  inbox="$ROOT/knowledge/inbox/$role.md"
  if [[ ! -f "$inbox" ]]; then
    printf '# %s 收件箱\n\n派工与上报都追加到本文件末尾，一行一条，最新的在最下面。`knowledge/inbox/` 只有 gm 能写。格式：\n\n```\n- [YYYY-MM-DD HH:MM] 发起方：<角色> | 任务 ID：task-<稳定 ID> | 业务引用：<content_id / publication_id / -> | 任务：<做什么> | 验收：<怎么算完成>\n```\n\n派工后 `hc send <前缀>-%s` 通知。\n\n**只执行行首既无 `✅` 也无 `⛔` 的条目。** 发起方收到「完成」回报后在该条目行首加 `✅`；撤销时在行首加 `⛔ 已撤销：<原因>`。详见 `AGENTS.md`「状态来源」一节。\n\n---\n\n## 当前队列\n\n（空）\n' \
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

# 2c. 种子物化：模版的占位骨架 → 实例的知识目录
# 映射规则：seeds/<路径> → <路径>（去掉 seeds/ 前缀）。
# 只在目标缺失时写，绝不覆盖实例已有内容（那里可能已经是真实业务定稿）。
if [[ -d "$ROOT/seeds" ]]; then
  while IFS= read -r -d '' seed_file; do
    rel="${seed_file#"$ROOT/seeds/"}"
    target="$ROOT/$rel"
    [[ -f "$target" ]] && continue
    mkdir -p "$(dirname "$target")"
    cp "$seed_file" "$target"
    echo "  已物化种子：$rel"
  done < <(find "$ROOT/seeds" -type f -not -path '*/.git/*' -print0)
fi

# 2d. 频道目录（channels.json 驱动）：只建启用的频道；已存在的目录不删
CHANNELS_FILE="$ROOT/channels.json"
if [[ -f "$CHANNELS_FILE" ]]; then
  mkdir -p "$ROOT/knowledge/business"
  for cid in $(jq -r '.channels[] | select(.enabled) | .id' "$CHANNELS_FILE"); do
    [[ "$cid" =~ ^[a-z][a-z0-9-]{0,19}$ ]] || {
      echo "频道 id 不合法：${cid}（1-20 位小写字母数字 -，以字母开头）" >&2
      exit 1
    }
    # 频道目录只放 generated 发布记录；稿件在 canonical 内容包，资产不进频道目录。
    mkdir -p "$ROOT/knowledge/business/$cid"
    if [[ ! -f "$ROOT/knowledge/business/$cid/发布记录.md" ]]; then
      printf '# %s 发布记录\n\n> **GENERATED FILE — READ ONLY**\n> 由 `tools/opc-workflow build` 从 canonical publication cards 生成。请勿手工编辑。\n\n当前没有该渠道的 publication。\n' \
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
    # 常驻文档清单从已物化的种子推导，不写死文件名
    seed_docs=""
    if [[ -d "$ROOT/seeds/business" ]]; then
      while IFS= read -r -d '' f; do
        name="$(basename "$f")"
        [[ -f "$ROOT/knowledge/business/$name" ]] || continue
        seed_docs="${seed_docs:+$seed_docs}"'、'"`$name`"
      done < <(find "$ROOT/seeds/business" -maxdepth 1 -type f -name '*.md' -print0)
    fi
    [[ -n "$seed_docs" ]] && echo "常驻文档：${seed_docs}。"
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
  echo "## CLI 能力差异"
  echo
  echo "Skill 的发现路径与权限模型因 CLI 而异，OPC 只对 claude 生成权限白名单。"
  echo
  echo "| 角色 | CLI | 技能来源 | 权限模型 |"
  echo "|---|---|---|---|"
  for role in $roles; do
    cli="$(opc_role_cli "$role")"
    echo "| $role | \`$cli\` | $(opc_cli_skill_source "$cli") | $(opc_cli_permission_model "$cli") |"
  done
  echo
  echo "非 claude 角色没有 \`.opc/settings-<角色>.json\`：它们的权限由各自 CLI 的"
  echo "沙箱与审批策略决定，OPC 不代为生成。"
  echo
  disabled="$(jq -r '.roles[] | select(.enabled | not) | .name' "$(opc_roles_file)" | paste -sd ', ' -)"
  [[ -z "$disabled" ]] || echo "已停用（不启动、不生成模板）：$disabled"
} > "$ROOT/knowledge/team.md"

# 4. 布局（可选，存在才装）
DASHBOARD_MOD="$PREFIX-opc-dashboard"
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
    # 带占位的布局（看板）要按实例替换：实例目录与 mod 名都是实例主权
    if grep -qF '{{' "$f"; then
      jq --arg instance "$ROOT" --arg mod "${DASHBOARD_MOD}" '
        walk(if type == "string"
             then gsub("\\{\\{INSTANCE\\}\\}"; $instance) | gsub("\\{\\{MOD\\}\\}"; $mod)
             else . end)' "$f" > "$target"
    else
      cp "$f" "$target"
    fi
    [[ -f "$ROOT/layouts/$name.svg" ]] && cp "$ROOT/layouts/$name.svg" "${target%.json}.svg"
  done
fi

# 5. 看板 mod（只读面板；没有 Herdr 也不影响第一阶段工具）
dashboard_note="看板 mod：模版里没有 mods/opc-dashboard，跳过"
if [[ -d "$ROOT/mods/opc-dashboard" ]]; then
  mkdir -p "$(opc_mods_dir)/${DASHBOARD_MOD}"
  cp "$ROOT/mods/opc-dashboard/main.js" "$ROOT/mods/opc-dashboard/model.js" \
     "$ROOT/mods/opc-dashboard/mod.json" "$(opc_mods_dir)/${DASHBOARD_MOD}/"
  if command -v herdr-app >/dev/null 2>&1; then
    dashboard_note="看板 mod：$(opc_mods_dir)/${DASHBOARD_MOD}（布局 $(opc_layouts_dir)/$PREFIX-opc-dashboard.json）"
  else
    dashboard_note="看板 mod：已写入 $(opc_mods_dir)/${DASHBOARD_MOD}，但没找到 herdr-app 命令；装好 Herdr 后自动生效"
  fi
fi

echo "已安装 OPC 实例：前缀 $PREFIX"
echo "  角色：$(echo $roles | tr ' ' ', ')"
echo "  模板：$TEMPLATES/$PREFIX-<角色>.md"
echo "  权限：$ROOT/.opc/settings-<角色>.json（仅 claude 角色）"
echo "  名册：$ROOT/knowledge/team.md"
echo "  $dashboard_note"
# 非 claude 的 CLI 不托管权限，要说清楚，否则 owner 会以为白名单覆盖了它们
unmanaged=""
for role in $roles; do
  cli="$(opc_role_cli "$role")"
  opc_cli_managed_permissions "$cli" || unmanaged="${unmanaged:+$unmanaged, }$role($cli)"
done
if [[ -n "$unmanaged" ]]; then
  echo
  echo "提示：以下角色的权限不由 OPC 托管：${unmanaged}"
  echo "      技能来源与审批语义见 knowledge/team.md「CLI 能力差异」。"
fi
# bypass 模式没有弹窗，也没有 allow 规则兜底：把还在拦的东西说清楚
bypass_roles=""
for role in $roles; do
  mode="$(opc_role_field "$role" permissionMode)"
  [[ "${mode:-default}" == "bypassPermissions" ]] && bypass_roles="${bypass_roles:+$bypass_roles, }$role"
done
if [[ -n "$bypass_roles" ]]; then
  echo
  echo "提示：以下角色跑在 bypassPermissions：${bypass_roles}"
  echo "      该模式下 allow 规则不生效，仍然拦得住的只有：deny 规则、"
  echo "      工作目录写入封锁、Claude Code 自己的保护路径。"
  echo "      首次启动会弹一次风险确认——由 owner 本人在终端确认。"
fi
echo "下一步：scripts/opc-up.sh [角色...]"
