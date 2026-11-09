#!/usr/bin/env bash
# 安装 OPC 实例：按 roles.json 生成 hc 模板、权限白名单、启动器与角色注册表。
#
# 用法：
#   scripts/opc-install.sh [前缀] [选项]
#
# 选项：
#   --interactive   先检测本机装了哪些 CLI，再逐个选角色、CLI 与模型
#   --no-input      不提问（脚本、测试、CI 用）
#   --skip-smoke    跳过主流程冒烟（工具链自检；默认要跑）
#   两个都不给时：终端里跑就问，重定向/管道里跑就不问。
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

ROOT="$(opc_root)"
PREFIX=""
INPUT_MODE=auto   # auto | yes | no
SKIP_SMOKE=0       # 1 = 跳过主流程冒烟
TEMPLATES="$(opc_templates_dir)"

usage() {
  cat <<'EOF'
用法：scripts/opc-install.sh [前缀] [选项]

选项：
  --interactive   先检测本机装了哪些 CLI，再逐个选角色、CLI 与模型
  --no-input      不提问（脚本、测试、CI 用）
  --skip-smoke    跳过主流程冒烟（工具链自检；默认要跑）
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --interactive) INPUT_MODE=yes; shift ;;
    --no-input) INPUT_MODE=no; shift ;;
    --skip-smoke) SKIP_SMOKE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    --*) echo "未知选项：$1" >&2; usage >&2; exit 2 ;;
    *)
      if [[ -n "$PREFIX" ]]; then echo "多余参数：$1" >&2; usage >&2; exit 2; fi
      PREFIX="$1"; shift ;;
  esac
done
[[ -n "$PREFIX" ]] || PREFIX="$(opc_prefix "$ROOT")"

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

# ---- 交互式选择：本机装了什么 CLI，就只让选什么 ----

# 提示写 stderr、答案走 stdout；读到 EOF 就中止，绝不半途改配置。
ask() {
  local prompt="$1" answer=""
  printf '%s' "$prompt" >&2
  if ! IFS= read -r answer; then
    printf '\n' >&2
    echo "输入结束，已中止（roles.json 未改动）" >&2
    exit 2
  fi
  printf '%s' "$answer"
}

# 可选的一问：读到 EOF 返回非零，不中止安装。
# 模型选择是第二轮的附加项，输入没了就按「用该 CLI 的默认模型」处理。
ask_optional() {
  local prompt="$1" answer=""
  printf '%s' "$prompt" >&2
  if ! IFS= read -r answer; then
    printf '\n' >&2
    return 1
  fi
  printf '%s' "$answer"
}

# 逐个角色问「启用吗」「用哪个 CLI」，答案写回 roles.json。
# 默认值取当前配置：现在的 CLI 装着就还是它，否则用检测到的第一个。
choose_roles() {
  local roles_file clis cli role answer enable chosen default_index
  local total i enabled_names sel current_cli
  local models model model_default no_more n m

  roles_file="$(opc_roles_file)"
  clis="$(opc_detect_clis | paste -sd ' ' -)"
  if [[ -z "$clis" ]]; then
    echo "没有检测到任何可用的 CLI，先装一个再来。OPC 认得：" >&2
    opc_known_clis | sed 's/^/  - /' >&2
    exit 1
  fi

  total=0
  echo "检测到的 CLI：" >&2
  for cli in $clis; do
    total=$((total + 1))
    printf '  %d) %s\n' "$total" "$cli" >&2
  done
  # roles.json 里写了但没装的 CLI 不会出现在选项里，说一声免得以为丢了配置
  for current_cli in $(jq -r '.roles[]?.cli // empty' "$roles_file" | sort -u); do
    case " $clis " in
      *" $current_cli "*) ;;
      *) echo "提示：roles.json 里的 ${current_cli} 没装，选项里没有它。" >&2 ;;
    esac
  done
  echo >&2

  enable=false
  enabled_names=""
  sel='[]'
  for role in $(opc_all_roles); do
    if [[ "$(opc_role_field "$role" enabled)" == "true" ]]; then
      answer="$(ask "启用角色 ${role}？[y] ")"
      [[ -n "$answer" ]] || answer="y"
    else
      answer="$(ask "启用角色 ${role}？[n] ")"
      [[ -n "$answer" ]] || answer="n"
    fi
    case "$answer" in
      y|Y|yes|是) enable=true ;;
      *) enable=false ;;
    esac

    chosen=""
    if [[ "$enable" == "true" ]]; then
      default_index=1
      i=0
      current_cli="$(opc_role_cli "$role")"
      for cli in $clis; do
        i=$((i + 1))
        [[ "$cli" == "$current_cli" ]] && default_index="$i"
      done
      while :; do
        answer="$(ask "  ${role} 用哪个 CLI？[${default_index}] ")"
        [[ -n "$answer" ]] || answer="$default_index"
        # 10# 前缀：避免「08」被当成八进制
        if [[ "$answer" =~ ^[0-9]+$ ]] && (( 10#$answer >= 1 && 10#$answer <= total )); then
          break
        fi
        echo "  请输入 1 到 ${total} 之间的编号。" >&2
      done
      i=0
      for cli in $clis; do
        i=$((i + 1))
        [[ "$i" == "$((10#$answer))" ]] && chosen="$cli"
      done
      enabled_names="${enabled_names} ${role}(${chosen})"
    fi

    sel="$(jq -c --arg n "$role" --argjson e "$enable" --arg c "$chosen" \
      '. + [{name: $n, enabled: $e, cli: $c}]' <<< "$sel")"
  done

  # 第二轮：逐角色选模型。清单由该 CLI 自己报告，模版不内置任何模型名；
  # 拿不到清单时允许手填模型名。留空表示用该 CLI 的默认模型。
  no_more=0
  for role in $(opc_all_roles); do
    chosen="$(jq -r --arg n "$role" '.[] | select(.name==$n) | if .enabled then .cli else "" end' <<< "$sel")"
    [[ -n "$chosen" ]] || continue
    model_default="$(opc_role_field "$role" model)"
    model="$model_default"
    if [[ $no_more -eq 0 ]]; then
      models="$(opc_cli_models "$chosen")"
      if [[ -n "$models" ]]; then
        echo "  ${role} 的模型清单（由 ${chosen} 自己报告）：" >&2
        n=0
        while IFS= read -r m; do
          [[ -n "$m" ]] || continue
          n=$((n + 1))
          printf '    %d) %s\n' "$n" "$m" >&2
        done <<< "$models"
      fi
      if ! answer="$(ask_optional "  ${role} 用哪个模型？[留空 = 该 CLI 的默认模型；可填编号或模型名] ")"; then
        no_more=1
        answer=""
      fi
      if [[ -n "$answer" ]]; then
        if [[ "$answer" =~ ^[0-9]+$ ]] && [[ -n "$models" ]]; then
          model="$(printf '%s\n' "$models" | sed -n "${answer}p")"
          if [[ -z "$model" ]]; then
            echo "  编号超出范围：${answer}" >&2
            exit 2
          fi
        else
          model="$answer"
        fi
        # 模型名会写进启动器并交给 CLI 解析：只放行干净的字符
        if ! [[ "$model" =~ ^[A-Za-z0-9._:/-]+$ ]]; then
          echo "  模型名不合法：${model}（只允许字母数字与 . _ : / -）" >&2
          exit 2
        fi
      fi
    fi
    sel="$(jq -c --arg n "$role" --arg m "$model" \
      'map(if .name == $n then . + {model: $m} else . end)' <<< "$sel")"
  done

  if [[ -z "$enabled_names" ]]; then
    echo "至少要启用一个角色，已中止（roles.json 未改动）。" >&2
    exit 1
  fi

  jq --argjson sel "$sel" '
    .roles |= map(. as $r |
      ($sel | map(select(.name == $r.name)) | .[0]) as $s |
      if $s == null then .
      elif $s.enabled then . + {enabled: true, cli: $s.cli, model: $s.model}
      else . + {enabled: false}
      end)
  ' "$roles_file" > "$roles_file.tmp" && mv "$roles_file.tmp" "$roles_file"

  # 问过一次就不再自动问：重装是常事（改白名单、换权限），每次都要按回车太烦。
  # 想再改就跑 scripts/opc-install.sh --interactive。
  mkdir -p "$ROOT/.opc"
  : > "$ROOT/.opc/roles-asked"

  echo "将启用：${enabled_names# }" >&2
  echo >&2
}

if [[ "$INPUT_MODE" == "yes" ]] \
   || { [[ "$INPUT_MODE" == "auto" ]] && [[ -t 0 ]] && [[ ! -f "$ROOT/.opc/roles-asked" ]]; }; then
  choose_roles
fi

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
  # 模板路径会被拼进 $ROOT：带 .. 就能读到实例外的文件，而那内容会变成这个
  # 角色的简报，被对应终端当成指令执行。和下面的 cli 一样，先拒绝再读。
  tpl="$(opc_role_template "$role")"
  opc_safe_rel_path "$tpl" "$ROOT" || {
    echo "角色 $role 的模板路径不合法：${tpl}（必须是实例内的相对路径）" >&2
    exit 1
  }
  src="$ROOT/$tpl"
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
  #   codex  —— --sandbox / --ask-for-approval / --approve-for-me
  #   其他   —— 不接管权限，按该 CLI 默认跑，装完提示 owner 自己确认语义
  mode="$(opc_role_field "$role" permissionMode)"
  mode="${mode:-$(opc_cli_default_permission_mode "$cli")}"
  valid_modes="$(opc_cli_permission_modes "$cli")"
  if [[ -n "$valid_modes" ]]; then
    case " $valid_modes " in
      *" $mode "*) ;;
      *) echo "角色 $role 的 permissionMode 不合法：${mode}" >&2; exit 1 ;;
    esac
  fi
  perm_args="$(opc_cli_permission_args "$cli" "$mode")"

  # 模型：留空表示用该 CLI 的默认模型，这时不加任何模型参数。
  # 写法按 CLI 分派（claude 用 --model，codex 用配置覆盖），口径在 lib.sh。
  model="$(opc_role_field "$role" model)"
  if [[ -n "$model" ]] && ! [[ "$model" =~ ^[A-Za-z0-9._:/-]+$ ]]; then
    echo "角色 $role 的 model 不合法：${model}（只允许字母数字与 . _ : / -）" >&2
    exit 1
  fi
  model_args="$(opc_cli_model_args "$cli" "$model")"
  # 必备开关：codex 少了 --no-daemon，命令会跑到 HC 的调度之外。
  required_args="$(opc_cli_required_args "$cli")"
  # 角色配置里没有自由参数字段：启动命令行只拼模版自己算出来的参数。
  # 实例里若留着手写的 args 字段，明确告诉 owner 它不生效，而不是静默忽略。
  if [[ -n "$(opc_role_list "$role" args)" ]]; then
    echo "提示：角色 $role 的 roles.json 里有 args 字段，已不生效——" >&2
    echo "      启动参数由模版按 CLI 与权限档算出，自由参数会变成往别人的" >&2
    echo "      启动命令行里塞开关的路。需要别的开关请改模版机制。" >&2
  fi

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
    sh) exec "\$_p" -lc 'cd "\$OPC_ROOT" && exec "\$OPC_CLI" $perm_args $model_args $required_args $extra_args' ;;
    *) exec "\$_p" -lic 'cd "\$OPC_ROOT" && exec "\$OPC_CLI" $perm_args $model_args $required_args $extra_args' ;;
  esac
done
echo "OPC：找不到可用的 shell（zsh / bash / sh）" >&2
exit 127
EOF
  chmod +x "$ROOT/.opc/run/$role.sh"

  # hc 模板由三段拼成：frontmatter（来自 roles.json）、角色正文、技能索引。
  # frontmatter 的 description 只能有一行，且 hc 按行解析、不去引号，
  # 所以描述里的换行要压平、首尾引号要剥掉，否则会解析成带引号的字面量。
  desc="$(opc_role_description "$role" "$src")"
  desc="$(printf '%s' "$desc" | tr '\n' ' ' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
  desc="${desc#\"}"; desc="${desc%\"}"
  [[ -n "$desc" ]] || desc="OPC 角色 $role"

  # 先完整生成技能索引；校验失败时不能让重定向先截断已有 hc 模板。
  if ! skill_index="$(opc_skill_index "$role" "$ROOT")"; then
    exit 1
  fi

  # 角色正文：旧的单文件角色简报带 frontmatter，新版的 AGENTS.md 是纯
  # Markdown。两种都要只取正文，前缀占位符在这里替换。
  {
    printf -- '---\n'
    printf 'name: %s-%s\n' "$PREFIX" "$role"
    printf 'description: %s\n' "$desc"
    printf 'command: %s\n' "$ROOT/.opc/run/$role.sh"
    printf -- '---\n\n'
    opc_role_body "$src" | sed -e "s/{{PREFIX}}/$PREFIX/g"
    [[ -z "$skill_index" ]] || printf '%s\n' "$skill_index"
  } > "$TEMPLATES/$PREFIX-$role.md"
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
  # 模版自检（模版仓库的 tests/）不放行：那是模版仓库的事，实例里跑不通
  # （缺 .opc-template-repo 标记），留着只会让角色在实例里空跑。
  # 放行的是实例自己用得上的工具：preflight、opc-lint、opc-smoke。
  readonly_rules='[
    "Bash(ls:*)", "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)", "Bash(wc:*)",
    "Bash(grep:*)", "Bash(stat:*)",
    "Bash(diff:*)", "Bash(pwd)",
    "Bash(basename:*)", "Bash(dirname:*)", "Bash(jq:*)",
    "Bash(cd:*)", "Bash(which:*)", "Bash(date:*)", "Bash(tr:*)",
    "Bash(./tools/preflight:*)", "Bash(tools/preflight:*)",
    "Bash(./tools/opc-lint:*)",
    "Bash(./tools/opc-smoke:*)"
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
# tasks/ 是任务卡目录：委派时任务卡先落在这里，再交给承接角色。
# 收件箱已退休：不再建 knowledge/inbox/。既有实例里已有的目录不删。
mkdir -p "$ROOT/knowledge/content" "$ROOT/knowledge/decisions" \
         "$ROOT/knowledge/tasks"
for role in $roles; do
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
    # 常驻文档清单从 business 根目录的实际文件推导，不写死文件名
    docs=""
    for f in "$ROOT"/knowledge/business/*.md; do
      [[ -f "$f" ]] || continue
      name="$(basename "$f")"
      [[ "$name" == "README.md" || "$name" == "选题日历.md" ]] && continue
      docs="${docs:+${docs}、}\`$name\`"
    done
    [[ -n "$docs" ]] && echo "常驻文档：${docs}。"
    echo "业务线：\`growth/\`（增长）、\`product/\`（产品）。"
  } > "$ROOT/knowledge/business/README.md"
fi

# 3. 团队名册（角色注册表）：角色怎么起、用什么 CLI 与模型、权限如何、归哪棵子树
{
  echo "# 团队名册"
  echo
  echo "> 本文件由 \`scripts/opc-install.sh\` 生成，**不要手改**。"
  echo "> 改角色请编辑 \`roles.json\`，或跑 \`scripts/opc-role.sh\`。"
  echo
  echo "## 角色注册表"
  echo
  echo "每个角色一行的注册表：会话怎么起、用哪个 CLI 与模型、权限如何、归哪棵子树。"
  echo "编排者按这张表委派。"
  echo
  echo "| 角色 | 终端名 | 启动器 | HC 模板名 | 所在 tab | CLI | 模型 | 权限模式 | 负责的子树 |"
  echo "|---|---|---|---|---|---|---|---|---|"
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
    cli="$(opc_role_cli "$role")"
    # 模型留空表示用该 CLI 的默认模型：写清楚，不留空字段
    model="$(opc_role_field "$role" model)"
    [[ -n "$model" ]] || model="默认模型"
    mode="$(opc_role_field "$role" permissionMode)"
    mode="${mode:-$(opc_cli_default_permission_mode "$cli")}"
    echo "| $role | \`$PREFIX-$role\` | \`.opc/run/$role.sh\` | \`$PREFIX-$role\` | \`$role\` | \`$cli\` | $model | \`$mode\` | $scope_md |"
  done
  echo
  echo "## 约定"
  echo
  echo "- **只有注册表里的角色终端才属于本实例**；注册表之外的终端与本实例无关，也不要顺着它们的 cwd 取材。"
  echo "- **跨终端读屏按注册表里的终端名，不用地址形式**：读别的角色的屏幕用上表的终端名，不要用 \`hc ls\` 里的地址。"
  echo "- **委派一律由编排者按本注册表发起**：编排者是唯一发起方，按上表的终端名与启动器路径把任务卡交给承接角色。旧的「按名册终端名发通知」约定退休，不再作为委派方式。"
  echo "- 查当前存活终端用 \`hc ls\`；启动某个角色用上表的启动器路径。"
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

# 4. 全局 UI（布局与看板 mod）由模版级 bin/opc 安装，实例不再持有副本。
#    这里只留下提示，避免安装器与模版命令两边各装一套。
ui_note="全局 UI：由 bin/opc install/upgrade 统一安装（布局 opc，mod opc-tabs / opc-dashboard）"

# 5. 主流程冒烟：工具链不通就别宣布装完。
#    冒烟在临时目录里跑，不碰实例的业务数据，也不依赖实例缺了哪些目录。
if [[ $SKIP_SMOKE -eq 1 ]]; then
  smoke_note="主流程冒烟：已按 --skip-smoke 跳过"
elif [[ -x "$ROOT/tools/opc-smoke" ]]; then
  if python3 "$ROOT/tools/opc-smoke"; then
    smoke_note="主流程冒烟：通过"
  else
    echo "安装失败：主流程冒烟没过——上面的输出就是失败原因。" >&2
    echo "        修好工具链后重跑安装，或先用 --skip-smoke 跳过冒烟。" >&2
    exit 1
  fi
else
  smoke_note="主流程冒烟：实例里没有 tools/opc-smoke，跳过"
fi

# 7. 生成一次看板与选题日历：装完就有数据，看板不会是空的。
#    build 只写 generated 视图，不改业务事实；失败也不阻断安装——
#    多半是某张内容卡写坏了，那是业务问题，owner 自己看得见。
build_note="看板视图：实例里没有 tools/opc-workflow，跳过"
if [[ -f "$ROOT/tools/opc-workflow" ]]; then
  if python3 "$ROOT/tools/opc-workflow" build >/dev/null; then
    build_note="看板视图：已生成 knowledge/business/dashboard.json"
  else
    build_note="看板视图：build 没成功，看板暂时是空的（多半是某张内容卡写坏了）"
  fi
fi

echo "已安装 OPC 实例：前缀 $PREFIX"
echo "  角色：$(echo $roles | tr ' ' ', ')"
echo "  模板：$TEMPLATES/$PREFIX-<角色>.md"
echo "  权限：$ROOT/.opc/settings-<角色>.json（仅 claude 角色）"
echo "  注册表：$ROOT/knowledge/team.md"
echo "  $smoke_note"
echo "  $build_note"
echo "  $ui_note"
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
