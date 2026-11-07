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

# 新收件箱的固定头部。install 与 role add 都走这里，避免新增角色拿到另一套
# 任务格式；只负责生成内容，调用方仍要守住「文件存在就不覆盖」。
opc_write_inbox() { # opc_write_inbox <角色> <目标文件>
  local role="$1"
  local target="$2"
  printf '# %s 收件箱\n\n派工写入本文件，结果回写原记录；一项任务始终只占一行，最新的在最下面。`knowledge/inbox/` 只有 gm 可写。\n\n派工格式：\n\n```\n- [YYYY-MM-DD HH:MM] 发起方：<角色> | 任务 ID：task-<稳定 ID> | 业务引用：<content_id / publication_id / -> | 任务：<做什么> | 验收：<怎么算完成>\n```\n\n完成后由执行角色先用 `hc send <前缀>-gm` 通知，gm 再把**原记录**改成：\n\n```\n- ✅ [YYYY-MM-DD HH:MM] 发起方：<角色> | 任务 ID：task-<稳定 ID> | 业务引用：<content_id / publication_id / -> | 任务：<做什么> | 验收：<怎么算完成> | 完成时间：YYYY-MM-DD HH:MM | 结果：<一句话结论与产出路径>\n```\n\n`结果` 必填；细节较长时只写一句话结论与产出路径。`hc send` 只负责通知，任务与结果事实都在本文件。派工后再用 `hc send <前缀>-%s` 通知收件人。\n\n**只执行行首既无 `✅` 也无 `⛔` 的条目。** 撤销时把原记录改成 `- ⛔ 已撤销：<原因> - [派工时间] ...`。详见 `AGENTS.md`「状态来源」一节。\n\n---\n\n## 当前队列\n\n（空）\n' \
    "$role" "$role" > "$target"
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

# 角色简报源路径，默认 agents/<角色名>/AGENTS.md
# 角色材料是目录：AGENTS.md 是入口，目录里还可以放角色专属参考文件。
opc_role_template() {
  local t
  t="$(opc_role_field "$1" template)"
  printf '%s' "${t:-agents/$1/AGENTS.md}"
}

# 角色的一句职责描述。roles.json 是唯一事实来源；旧实例还没迁移时，
# 退回旧角色文件 frontmatter 里的那一行，升级过程中也不至于把描述丢掉。
opc_role_description() {
  local role="$1" src="${2:-}" desc
  desc="$(opc_role_field "$role" description)"
  if [[ -z "$desc" && -n "$src" ]]; then
    desc="$(opc_frontmatter_value "$src" description)"
  fi
  printf '%s' "$desc"
}

# 角色在根级技能库里选中的技能（roles.json 的 skills）
opc_role_skills() {
  jq -r --arg n "$1" '.roles[] | select(.name==$n) | .skills[]? // empty' "$(opc_roles_file)"
}

# 路径安全：相对路径、不含 .. 、软链接展开后仍在实例内。
# 角色简报会被拼成这个角色的启动提示，等于交给终端执行；
# 路径一旦能读出实例外的文件，那内容就可能被当成指令。
opc_safe_rel_path() {
  local rel="$1" root="$2"
  [[ -n "$rel" ]] || return 1
  case "$rel" in
    /*) return 1 ;;
    ../*|*/../*|*/..) return 1 ;;
  esac
  local root_resolved
  root_resolved="$(cd "$root" 2>/dev/null && pwd -P)" || return 1
  local resolved
  resolved="$(opc_resolved_path "$root_resolved" "$rel")" || return 1
  case "$resolved" in
    "$root_resolved"/*) return 0 ;;
    *) return 1 ;;
  esac
}

# 逐段展开软链接，得到相对 root 的最终落点。
# 目标不存在时退到最深的存在祖先，剩余部分原样接在后面。
opc_resolved_path() {
  local root="$1" rel="$2" cur part rest depth=0
  cur="$root"
  rest="$rel"
  while [[ -n "$rest" ]]; do
    part="${rest%%/*}"
    if [[ "$part" == "$rest" ]]; then rest=""; else rest="${rest#*/}"; fi
    [[ -n "$part" ]] || continue
    cur="$cur/$part"
    while [[ -L "$cur" && $depth -lt 32 ]]; do
      depth=$((depth + 1))
      local target
      target="$(readlink "$cur")" || return 1
      case "$target" in
        /*) cur="$target" ;;
        *) cur="$(dirname "$cur")/$target" ;;
      esac
    done
  done
  local probe="$cur" tail=""
  while [[ ! -e "$probe" ]]; do
    tail="/$(basename "$probe")$tail"
    probe="$(dirname "$probe")"
    [[ "$probe" == "/" ]] && break
  done
  local real
  if [[ -d "$probe" ]]; then
    real="$(cd "$probe" 2>/dev/null && pwd -P)" || return 1
  else
    real="$(cd "$(dirname "$probe")" 2>/dev/null && pwd -P)/$(basename "$probe")" || return 1
  fi
  printf '%s%s' "$real" "$tail"
}

# 技能名：只允许普通标识符，挡住路径穿越。
opc_safe_skill_name() {
  local name="$1"
  [[ "$name" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || return 1
  [[ "$name" == *..* ]] && return 1
  return 0
}

# 技能 frontmatter 的原始 description 值（不做引号剥离）。
# 单独取一次是为了能看出「值是不是块标量」：块标量（| 或 >）说明描述跨了多行。
opc_skill_description_raw() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  awk '
    NR==1 { if ($0 !~ /^---[[:space:]]*$/) exit; next }
    /^---[[:space:]]*$/ { exit }
    {
      pat = "^description[[:space:]]*:[[:space:]]*"
      if ($0 ~ pat) { sub(pat, ""); print; exit }
    }
  ' "$file" 2>/dev/null
}

# 技能 frontmatter 校验：name 与目录名一致、description 非空且是单行。
# 通过返回 0；不通过返回 1，原因写在 OPC_SKILL_ERROR 里。
# 读技能的地方都用它，所以模版里的技能坏了，索引里不会出现一条坏条目。
opc_skill_frontmatter_error() {
  local file="$1" expected="${2:-}" name raw desc
  OPC_SKILL_ERROR=""
  [[ -f "$file" ]] || { OPC_SKILL_ERROR="技能文件不存在"; return 1; }
  head -n 1 "$file" 2>/dev/null | grep -q '^---[[:space:]]*$' || {
    OPC_SKILL_ERROR="缺少 frontmatter"; return 1; }
  name="$(opc_frontmatter_value "$file" name)"
  if [[ -z "$name" ]]; then
    OPC_SKILL_ERROR="frontmatter 缺少 name"; return 1
  fi
  if [[ -n "$expected" && "$name" != "$expected" ]]; then
    OPC_SKILL_ERROR="frontmatter 的 name 与目录名不一致（name=${name}，目录=${expected}）"
    return 1
  fi
  raw="$(opc_skill_description_raw "$file")"
  desc="$(opc_skill_description "$file")"
  if [[ -z "$raw" ]]; then
    OPC_SKILL_ERROR="frontmatter 缺少 description"; return 1
  fi
  case "$raw" in
    '|'*|'>'*) OPC_SKILL_ERROR="description 必须是单行，不能用块标量"; return 1 ;;
  esac
  if [[ -z "$desc" ]]; then
    OPC_SKILL_ERROR="frontmatter 的 description 是空的"; return 1
  fi
  return 0
}

# 技能文件的真实路径：解析软链接后必须仍落在实例根之下，否则不可用。
# 技能说明会被读进角色提示词，等于交给终端执行；实例里的 skills/ 或
# skills/<名字>/SKILL.md 本身可能就是指向实例外的软链接，读进来就是越权。
# 成功时把路径写进 OPC_SKILL_FILE 并返回 0；失败返回 1，原因写在 OPC_SKILL_ERROR 里。
# （用全局量而不是 stdout：命令替换会开子 shell，全局量就丢了。）
opc_safe_skill_file() {
  local root="$1" name="$2" root_resolved skills_resolved file_resolved
  OPC_SKILL_ERROR=""
  OPC_SKILL_FILE=""
  opc_safe_skill_name "$name" || { OPC_SKILL_ERROR="技能名不合法"; return 1; }
  root_resolved="$(cd "$root" 2>/dev/null && pwd -P)" || {
    OPC_SKILL_ERROR="实例根目录读不到"; return 1; }
  skills_resolved="$(opc_resolved_path "$root_resolved" "skills")" || {
    OPC_SKILL_ERROR="技能目录解析失败"; return 1; }
  case "$skills_resolved" in
    "$root_resolved"/*) ;;
    *) OPC_SKILL_ERROR="技能目录指向实例外"; return 1 ;;
  esac
  file_resolved="$(opc_resolved_path "$root_resolved" "skills/$name/SKILL.md")" || {
    OPC_SKILL_ERROR="技能文件解析失败"; return 1; }
  case "$file_resolved" in
    "$root_resolved"/*) ;;
    *) OPC_SKILL_ERROR="技能文件指向实例外"; return 1 ;;
  esac
  [[ -f "$file_resolved" ]] || { OPC_SKILL_ERROR="技能文件不存在"; return 1; }
  OPC_SKILL_FILE="$file_resolved"
  return 0
}

# frontmatter 里的一个字段值。只认文件开头那一段 --- ... ---，
# 且只取首行匹配，避免正文里的同名行被当成字段。
opc_frontmatter_value() {
  local file="$1" key="$2" line
  [[ -f "$file" ]] || return 0
  line="$(awk -v key="$key" '
    NR==1 { if ($0 !~ /^---[[:space:]]*$/) exit; next }
    /^---[[:space:]]*$/ { exit }
    {
      pat = "^" key ":[[:space:]]*"
      if ($0 ~ pat) { sub(pat, ""); print; exit }
    }
  ' "$file")"
  line="${line%$'\r'}"
  line="${line%\"}"; line="${line#\"}"
  printf '%s' "$line"
}

# 技能 frontmatter 里的一句话描述
opc_skill_description() {
  opc_frontmatter_value "$1" description
}

# 角色简报正文：旧版单文件把描述写在自己的 frontmatter 里，
# 新版正文是纯 Markdown。取正文时把那层 frontmatter 摘掉。
opc_role_body() {
  local file="$1"
  # 只有「开头有 ---、中间全是 key: value、后面有配对的 ---」才算 frontmatter。
  # 纯 Markdown 里也可能出现分隔线，误当成 frontmatter 会把正文吃掉。
  if head -n 1 "$file" 2>/dev/null | grep -q '^---[[:space:]]*$' \
     && awk '
          NR==1 { next }
          /^---[[:space:]]*$/ { closed=1; exit }
          /^[[:space:]]*$/ { next }
          /^[A-Za-z][A-Za-z0-9_-]*:/ { next }
          { bad=1; exit }
          END { exit !(closed && !bad) }
        ' "$file" 2>/dev/null; then
    awk '
      NR==1 { next }
      !inbody && /^---[[:space:]]*$/ { inbody=1; next }
      inbody { print }
    ' "$file"
  else
    cat "$file"
  fi
}

# 技能索引：缺失技能允许角色降级启动；非法名、越界路径与坏 frontmatter
# 必须阻断安装，否则会把未经校验的指令静默装进角色提示词。
opc_skill_index() {
  local role="$1" root="$2" name file desc
  local lines=()
  while IFS= read -r name; do
    [[ -n "$name" ]] || continue
    if ! opc_safe_skill_name "$name"; then
      echo "错误：角色 $role 的技能 $name 不合法：技能名不合法" >&2
      return 1
    fi
    if ! opc_safe_skill_file "$root" "$name"; then
      if [[ "${OPC_SKILL_ERROR:-}" == "技能文件不存在" ]]; then
        echo "警告：角色 $role 选中的技能已跳过：${name}（技能文件不存在）" >&2
        continue
      fi
      echo "错误：角色 $role 的技能 $name 不合法：${OPC_SKILL_ERROR:-不可用}" >&2
      return 1
    fi
    file="$OPC_SKILL_FILE"
    if ! opc_skill_frontmatter_error "$file" "$name"; then
      echo "错误：角色 $role 的技能 $name 不合法：${OPC_SKILL_ERROR:-frontmatter 不合法}" >&2
      return 1
    fi
    desc="$(opc_skill_description "$file")"
    # 索引每条必须是一行：描述里的换行会把它拆成两条。
    desc="$(printf '%s' "$desc" | tr '\n' ' ' | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    lines+=("- $name — $desc — \`skills/$name/SKILL.md\`")
  done < <(opc_role_skills "$role")
  [[ ${#lines[@]} -gt 0 ]] || return 0
  printf '\n## 技能索引\n\n'
  printf '%s\n' "${lines[@]}"
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

# OPC 认得的 CLI。装没装只看 PATH：没装的不该出现在选择清单里。
opc_known_clis() {
  printf '%s\n' claude codex opencode gemini
}

# 本机装了哪些 CLI，一行一个。roles.json 里已经用到的 CLI 也算认得，
# 自定义的 CLI 不会被漏掉。
# 末尾的 read 读到 EOF 会返回非零：调用方都在 set -e 下，这里兜住，
# 免得「没找到」被当成「函数失败」。
opc_detect_clis() {
  {
    opc_known_clis
    jq -r '.roles[]?.cli // empty' "$(opc_roles_file)" 2>/dev/null || true
  } | sort -u | while IFS= read -r cli; do
    [[ -n "$cli" ]] || continue
    command -v "$cli" >/dev/null 2>&1 && printf '%s\n' "$cli"
  done || true
}

opc_app_home()  { printf '%s' "${HERDR_APP_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/herdr-app}"; }
opc_core_home() { printf '%s' "${HERDR_CORE_HOME:-${XDG_CONFIG_HOME:-$HOME/.config}/herdr-core}"; }
opc_templates_dir() { printf '%s/templates' "$(opc_core_home)"; }
opc_layouts_dir()   { printf '%s/layouts'   "$(opc_app_home)"; }
opc_mods_dir()      { printf '%s/mods'      "$(opc_app_home)"; }

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
# 业务内容一律长在实例仓库里（见 docs/安装与升级.md）。
opc_is_template_repo() {
  local root="${1:-$(opc_root)}"
  [[ -f "$root/.opc-template-repo" ]]
}

# 在模版仓库里执行实例操作时的统一提示
opc_template_repo_refusal() {
  cat >&2 <<'EOF'
这是模版仓库，不承载业务数据。
请开一个实例再干活：

  bin/opc install <实例目录> [前缀]

实例是独立目录、独立 git 仓库，业务内容只落在那里。模版这边只改机制。
EOF
}

