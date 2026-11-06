#!/usr/bin/env bash
# 实例 ↔ 模版同步：把模版的机制更新拉进实例，把实例的诉求（提案）带回模版。
#
# 用法：
#   scripts/opc-sync.sh status                     实例摘要
#   scripts/opc-sync.sh check [--from <源>]        只读：这次的变更计划
#   scripts/opc-sync.sh pull [--from <源>]         落盘同步
#         [--dry-run] [--no-install] [--prune] [--force] [--accept-template <路径>]
#   scripts/opc-sync.sh seeds [--from <源>]        种子骨架的 diff
#         [--apply <目标>] [--merge <目标>]
#   scripts/opc-sync.sh mark <路径> [--unmark]     显式 pin：本地定制，模版此后不覆盖
#   scripts/opc-sync.sh baseline --from <源>        固化基线快照（不改任何业务文件）
#   scripts/opc-sync.sh adopt --from <模版路径>    老实例接入（不覆盖任何已有文件）
#   scripts/opc-sync.sh log [-n N]                 同步流水
#
# 退出码：0 成功/无差异；1 有差异或失败；2 用法/环境错；3 有冲突（业务文件未被改动）
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

ROOT="$(opc_root)"
STATE="$ROOT/.opc/sync-state.json"
BASE="$ROOT/.opc/sync-base"
CONFLICTS="$ROOT/.opc/sync-conflicts"
LOG="$ROOT/.opc/sync.log"
LOCK="$ROOT/template.lock.json"
INSTANCE_JSON="$ROOT/.opc/instance.json"
ACTIVE_SOURCE=""

usage() {
  sed -n '3,20p' "$0" | sed 's/^# \{0,1\}//'
}

# ---------------------------------------------------------------- 基础工具

opc_hash() {
  # 内容哈希，换行归一化（CRLF→LF），避免不同平台造成「本地改过」的误判
  python3 - "$1" <<'PY'
import hashlib, sys
try:
    data = open(sys.argv[1], 'rb').read()
except OSError:
    sys.exit(1)
sys.stdout.write(hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest())
PY
}

opc_hash_of() {
  [[ -f "$1" ]] || return 1
  opc_hash "$1"
}

path_is_under() {
  local base="$1" path="$2"
  python3 - "$base" "$path" <<'PY'
import os, sys
base = os.path.realpath(sys.argv[1])
path = os.path.realpath(sys.argv[2])
if path == base or path.startswith(base + os.sep):
    raise SystemExit(0)
raise SystemExit(1)
PY
}

opc_copy() {
  # 覆盖式拷贝，先写临时文件再改名，避免半截文件。
  # 在最终写入点再验一次边界，避免只在解析 policy 时检查而留下 TOCTOU 窗口。
  local src="$1" dst="$2"
  if ! path_is_under "$ROOT" "$dst"; then
    echo "拒绝写到实例根目录之外：$dst" >&2
    exit 2
  fi
  if ! path_is_under "$ROOT" "$src" && \
     { [[ -z "$ACTIVE_SOURCE" ]] || ! path_is_under "$ACTIVE_SOURCE" "$src"; }; then
    echo "拒绝读取实例或模版根目录之外：$src" >&2
    exit 2
  fi
  mkdir -p "$(dirname "$dst")"
  cp "$src" "$dst.tmp.$$"
  mv "$dst.tmp.$$" "$dst"
}

opc_now() { date -Iseconds; }

opc_rel() {
  # 绝对路径 → 相对仓库根（带换行，供 read 逐行读）
  printf '%s\n' "${1#"$2"/}"
}

# 同步脚本自我更新：上一轮把新版暂存在 .opc/sync-stage/scripts/opc-sync.sh。
# 启动时替换自身再重新执行——运行中的脚本被覆盖会读到乱码，所以不能本轮生效。
self_update() {
  local staged="$ROOT/.opc/sync-stage/scripts/opc-sync.sh"
  local cur="$ROOT/scripts/opc-sync.sh"
  [[ -f "$staged" ]] || return 0
  if [[ -f "$cur" ]] && cmp -s "$staged" "$cur"; then
    rm -f "$staged"
    return 0
  fi
  mkdir -p "$(dirname "$cur")"
  cp "$staged" "$cur.tmp.$$"
  mv "$cur.tmp.$$" "$cur"
  chmod +x "$cur"
  rm -f "$staged"
  echo "同步脚本已更新到新版本，重新执行…" >&2
  exec bash "$cur" "$@"
}

# ---------------------------------------------------------------- 模版来源

resolve_source() {
  local given="${1:-}"
  if [[ -n "$given" ]]; then printf '%s' "$given"; return; fi
  if [[ -n "${OPC_TEMPLATE_SOURCE:-}" ]]; then printf '%s' "$OPC_TEMPLATE_SOURCE"; return; fi
  if [[ -f "$INSTANCE_JSON" ]]; then
    jq -r '.template.source // empty' "$INSTANCE_JSON"
    return
  fi
  # 猜一个：仓库的同级目录里叫 opc-template 的
  local guess="$(dirname "$ROOT")/opc-template"
  [[ -d "$guess" ]] && printf '%s' "$guess"
}

load_policy() {
  local src="$1"
  local file="$src/sync-policy.json"
  [[ -f "$file" ]] || file="$ROOT/.opc/policy.json"
  [[ -f "$file" ]] || { echo "找不到 sync-policy.json（在 $src 与实例缓存里都没有）" >&2; exit 2; }
  printf '%s' "$file"
}

# 策略里的每个路径都是「根目录内的相对路径」。三条硬约束：
#   不是绝对路径、不含 .. 成分、路径成分不是符号链接。
# 少了任何一条，拷贝就可能写到根目录之外。
validate_under_root() {
  local root="$1" rel="$2"
  [[ -n "$rel" ]] || return 1
  [[ "$rel" != /* && "$rel" != *'\\'* ]] || return 1
  local part
  local IFS='/'
  for part in $rel; do
    [[ "$part" != "." && "$part" != ".." ]] || return 1
  done
  # realpath 会解析途中已有的符号链接，也会规范化尚不存在的尾部。结果必须
  # 仍在 root 之内；字符串前缀判断要带路径分隔符，避免 /repo-evil 误通过。
  python3 - "$root" "$rel" <<'PY'
import os, sys
root = os.path.realpath(sys.argv[1])
candidate = os.path.realpath(os.path.join(root, sys.argv[2]))
if candidate == root or candidate.startswith(root + os.sep):
    raise SystemExit(0)
raise SystemExit(1)
PY
}

# 在任何拷贝动作之前把整个策略校验一遍。校验不过直接退出，不进同步。
validate_policy() {
  local policy="$1" src="$2" bad=0
  while IFS= read -r m; do
    [[ -n "$m" ]] || continue
    if ! validate_under_root "$src" "$m"; then
      echo "策略里的路径越界（rules）：$m" >&2
      bad=1
    fi
  done < <(jq -r '.rules[]?.match // empty' "$policy")
  while IFS=$'\t' read -r s t; do
    [[ -n "$s" ]] || continue
    if [[ "$s" != seeds/* ]] || ! validate_under_root "$src" "$s"; then
      echo "策略里的种子源越界或不在 seeds/ 下：$s" >&2; bad=1
    fi
    if ! validate_under_root "$ROOT" "$t"; then
      echo "策略里的种子目标越界：$t" >&2; bad=1
    fi
  done < <(jq -r '.seeds[]? | "\(.source)\t\(.target)"' "$policy")
  while IFS=$'\t' read -r s t; do
    [[ -n "$s" ]] || continue
    if ! validate_under_root "$src" "$s"; then
      echo "策略里的配置源越界：$s" >&2; bad=1
    fi
    if ! validate_under_root "$ROOT" "$t"; then
      echo "策略里的配置目标越界：$t" >&2; bad=1
    fi
  done < <(jq -r '.mergeConfigs[]? | "\(.source)\t\(.target)"' "$policy")
  while IFS= read -r k; do
    [[ -n "$k" ]] || continue
    if ! validate_under_root "$src" "$k"; then
      echo "策略里的种子规则越界：$k" >&2; bad=1
    fi
  done < <(jq -r '.seedRules | keys[]' "$policy")
  if [[ "$bad" != "0" ]]; then
    echo "策略校验不通过，同步中止。" >&2
    exit 2
  fi
}

policy_mode() {
  # 路径 → mode。最长前缀优先。
  jq -r --arg p "$2" '
    [ .rules[] | select(
        (if (.match | endswith("/")) then ($p | startswith(.match))
         else ($p == .match) end)
      ) ]
    | if length == 0 then "unclassified"
      else (sort_by(.match | length) | last | .mode) end
  ' "$1"
}

# 是否被 --accept-template 点名。accept 是一串路径，空格或逗号分隔；all 表示全部。
opc_accepted() {
  local rel="$1" accept="$2"
  [[ -n "$accept" ]] || return 1
  local a
  for a in ${accept//,/ }; do
    a="${a#/}"
    [[ "$a" == "$rel" || "$a" == "all" ]] && return 0
  done
  return 1
}

# ---------------------------------------------------------------- 变更计划

# 模版侧 managed 文件清单（相对路径，一行一个）
template_managed_files() {
  local src="$1" policy="$2"
  jq -r '.rules[] | select(.mode == "managed") | .match' "$policy" | while IFS= read -r m; do
    if [[ "$m" == */ ]]; then
      [[ -d "$src/$m" ]] || continue
      find "$src/$m" -type f -not -path '*/.git/*' \
        -not -name 'gpui-kit.d.ts' -not -name 'jsconfig.json' \
        -not -path '*/__pycache__/*' -not -name '*.pyc' | while IFS= read -r f; do
        opc_rel "$f" "$src"
      done
    else
      [[ -f "$src/$m" ]] && printf '%s\n' "$m"
    fi
  done | sort -u
}

# 基线内容 = 实例建立那一刻的模版内容。
# 找法按可靠度排序：
#   1. 实例 git 里这个文件**第一次被加入**的那次提交 —— 最准，就是建实例时的快照；
#   2. 实例记录的模版创建提交（老实例接入时用）；
#   3. 模版当前内容（实例没有 git、也没有记录时的兜底）。
# 文件在基线时刻还不存在 → 返回 1，基线里就不该有它（模版后加的文件算 add）。
baseline_copy() {
  local rel="$1" src="$2" created_commit="$3" dest="$4"
  local tmp c
  tmp="$(mktemp "${TMPDIR:-/tmp}/opc-baseline.XXXXXX")"
  c="$(git -C "$ROOT" log --diff-filter=A --reverse --format=%H -- "$rel" 2>/dev/null | head -n 1 || true)"
  if [[ -n "$c" ]] && git -C "$ROOT" show "$c:$rel" > "$tmp" 2>/dev/null; then
    mkdir -p "$(dirname "$dest")"
    cp "$tmp" "$dest"
    rm -f "$tmp"
    return 0
  fi
  if [[ -n "$created_commit" ]] && git -C "$src" cat-file -e "${created_commit}^{commit}" 2>/dev/null; then
    if git -C "$src" show "${created_commit}:$rel" > "$tmp" 2>/dev/null; then
      mkdir -p "$(dirname "$dest")"
      cp "$tmp" "$dest"
      rm -f "$tmp"
      return 0
    fi
    rm -f "$tmp"
    return 1
  fi
  rm -f "$tmp"
  [[ -f "$src/$rel" ]] || return 1
  mkdir -p "$(dirname "$dest")"
  cp "$src/$rel" "$dest"
}

# 输出变更计划：每行 "状态|路径|说明"
compute_plan() {
  local src="$1" policy="$2"
  local state="$3"
  local accept="${4:-}"

  # ---- managed：模版托管的机制文件
  while IFS= read -r rel; do
    [[ -n "$rel" ]] || continue
    local tpl="$src/$rel" inst="$ROOT/$rel"
    local basefile="$BASE/$rel"
    local pin="false"
    if [[ -f "$state" ]]; then
      pin="$(jq -r --arg p "$rel" '.files[$p].pinned // false' "$state")"
    fi
    [[ "$pin" == "true" ]] && { echo "pinned|$rel|已 pin：本地定制，模版不覆盖"; continue; }

    if [[ ! -f "$tpl" ]]; then continue; fi
    local tpl_hash inst_hash base_hash
    tpl_hash="$(opc_hash_of "$tpl")"
    inst_hash="$(opc_hash_of "$inst" || true)"
    base_hash="$(opc_hash_of "$basefile" || true)"

    if [[ "$rel" == "scripts/opc-sync.sh" ]]; then
      if [[ "$inst_hash" == "$tpl_hash" ]]; then
        echo "identical|$rel|已一致"
      else
        echo "deferred|$rel|同步脚本自身，本轮不覆盖（下轮生效）"
      fi
      continue
    fi
    if [[ -z "$inst_hash" ]]; then
      echo "add|$rel|模版新增"
      continue
    fi
    if [[ "$inst_hash" == "$tpl_hash" ]]; then
      echo "identical|$rel|已一致"
      continue
    fi
    if opc_accepted "$rel" "$accept"; then
      echo "update|$rel|已点名采用模版版本"
      continue
    fi
    if [[ -n "$base_hash" && "$inst_hash" == "$base_hash" ]]; then
      echo "update|$rel|模版已更新，直接覆盖"
      continue
    fi
    if [[ -z "$base_hash" ]]; then
      echo "unknown|$rel|没有基线，无法判断本地是否改过（跑 baseline 固化基线）"
      continue
    fi
    if [[ "$tpl_hash" == "$base_hash" ]]; then
      echo "local-modified|$rel|本地改过，模版没动（需要固化就跑 mark）"
      continue
    fi
    echo "conflict|$rel|本地与模版都改过"
  done < <(template_managed_files "$src" "$policy")

  # ---- seeds：占位骨架 → 实例业务文件
  jq -r '.seeds[] | "\(.source)\t\(.target)"' "$policy" | while IFS=$'\t' read -r srel trel; do
    [[ -n "$srel" ]] || continue
    local tpl="$src/$srel" snap="$ROOT/$srel" ours="$ROOT/$trel"
    [[ -f "$tpl" ]] || continue
    local tpl_hash ours_hash snap_hash
    tpl_hash="$(opc_hash_of "$tpl")"
    ours_hash="$(opc_hash_of "$ours" || true)"
    snap_hash="$(opc_hash_of "$snap" || true)"
    if [[ -z "$ours_hash" ]]; then
      echo "seed-add|$trel|业务文件还没有，用模版骨架物化"
      continue
    fi
    if [[ "$ours_hash" == "$tpl_hash" ]]; then
      echo "seed-identical|$trel|骨架一致"
      continue
    fi
    if [[ -z "$snap_hash" ]]; then
      echo "seed-unknown|$trel|没有基线快照，无法判断是否被业务改过"
      continue
    fi
    if [[ "$ours_hash" == "$snap_hash" ]]; then
      echo "seed-update|$trel|骨架有改进，业务没动过，直接升级"
      continue
    fi
    if [[ "$tpl_hash" == "$snap_hash" ]]; then
      echo "seed-diverged|$trel|业务已改，模版骨架未动（不用管）"
      continue
    fi
    echo "seed-diff|$trel|骨架有改进且业务已改，需要人工合并（seeds --merge）"
  done

  # ---- merge：结构化配置按 key 并集
  while IFS=$'\t' read -r srel trel arr key; do
    [[ -n "$srel" ]] || continue
    while IFS= read -r k; do
      [[ -n "$k" ]] || continue
      echo "config-add|$trel|模版新增条目 ${k}，将并入并默认停用"
    done < <(config_missing_keys "$policy" "$src" "$trel" "$arr" "$key")
  done < <(jq -r '.mergeConfigs[] | "\(.source)\t\(.target)\t\(.arrayPath)\t\(.key)"' "$policy")
}

# 模版里有、实例里没有的 key，一行一个
config_missing_keys() {
  local policy="$1" src="$2" target="$3" arr="$4" key="$5"
  local tpl="$src/$target" inst="$ROOT/$target"
  [[ -f "$tpl" ]] || return 0
  [[ -f "$inst" ]] || { jq -r --arg arr "$arr" --arg key "$key" '.[$arr][]? | .[$key] // empty' "$tpl"; return 0; }
  while IFS= read -r k; do
    [[ -n "$k" ]] || continue
    if ! jq -e --arg arr "$arr" --arg key "$key" --arg k "$k" \
         '.[$arr][]? | select(.[$key] == $k)' "$inst" >/dev/null 2>&1; then
      printf '%s\n' "$k"
    fi
  done < <(jq -r --arg arr "$arr" --arg key "$key" '.[$arr][]? | .[$key] // empty' "$tpl")
}

# 把模版新增的条目并入实例：只增不改，新增的一律默认停用
merge_config_entry() {
  local policy="$1" src="$2" target="$3" arr="$4" key="$5" k="$6"
  local tpl="$src/$target" inst="$ROOT/$target"
  [[ -f "$tpl" ]] || return 0
  if [[ ! -f "$inst" ]]; then
    opc_copy "$tpl" "$inst"
    return 0
  fi
  local tmp="$inst.tmp.$$"
  jq --slurpfile tplfile "$tpl" --arg arr "$arr" --arg key "$key" --arg k "$k" '
    ($tplfile[0][$arr] // []) as $srcArr
    | ($srcArr[] | select(.[$key] == $k)) as $entry
    | .[$arr] = ((.[$arr] // []) + [$entry | .enabled = false])
  ' "$inst" > "$tmp" 2>/dev/null && mv "$tmp" "$inst"
}

# ---------------------------------------------------------------- 应用计划

apply_plan() {
  local src="$1" policy="$2" state="$3"
  local dry_run="${4:-0}" prune="${5:-0}" accept_template="${6:-}"
  local changed=0 conflicts=0
  while IFS='|' read -r status rel detail; do
    [[ -n "$status" ]] || continue
    case "$status" in
      add|update)
        if [[ "$dry_run" == "1" ]]; then echo "  [计划] $status $rel"; continue; fi
        opc_copy "$src/$rel" "$ROOT/$rel"
        opc_copy "$src/$rel" "$BASE/$rel"
        echo "  $status $rel"
        changed=$((changed + 1))
        ;;
      identical)
        if [[ "$dry_run" == "1" ]]; then continue; fi
        opc_copy "$src/$rel" "$BASE/$rel"
        ;;
      conflict)
        if [[ "$dry_run" == "1" ]]; then echo "  [计划] conflict $rel"; continue; fi
        local basefile="$BASE/$rel"
        if [[ -f "$basefile" ]]; then
          mkdir -p "$CONFLICTS/$(dirname "$rel")"
          if git merge-file -p "$ROOT/$rel" "$basefile" "$src/$rel" > "$CONFLICTS/$rel.merge" 2>/dev/null; then
            opc_copy "$CONFLICTS/$rel.merge" "$ROOT/$rel"
            opc_copy "$src/$rel" "$BASE/$rel"
            echo "  merged ${rel}（自动合并成功）"
            changed=$((changed + 1))
          else
            echo "  conflict $rel —— 未改动，合并结果见 .opc/sync-conflicts/$rel.merge"
            conflicts=$((conflicts + 1))
          fi
        else
          echo "  conflict $rel —— 没有基线，无法合并；未改动"
          conflicts=$((conflicts + 1))
        fi
        ;;
      local-modified|pinned|deferred|unknown)
        if [[ "$dry_run" == "1" ]]; then echo "  [计划] $status $rel"; continue; fi
        if [[ "$status" == "deferred" ]]; then
          # 正在被执行的脚本不能在本轮覆盖（bash 会读到乱码）。
          # 先把新版落到暂存区，下次运行启动时自我替换并重新执行。
          opc_copy "$src/$rel" "$ROOT/.opc/sync-stage/$rel"
          echo "  deferred $rel —— 新版已暂存，下次运行生效"
        else
          echo "  $status $rel —— $detail"
        fi
        ;;
      seed-add|seed-update)
        local srel trel
        srel="$(jq -r --arg t "$rel" '.seeds[] | select(.target == $t) | .source' "$policy")"
        trel="$rel"
        if [[ "$dry_run" == "1" ]]; then echo "  [计划] $status $trel"; continue; fi
        opc_copy "$src/$srel" "$ROOT/$trel"
        opc_copy "$src/$srel" "$ROOT/$srel"
        echo "  $status $trel"
        changed=$((changed + 1))
        ;;
      seed-identical)
        local srel
        srel="$(jq -r --arg t "$rel" '.seeds[] | select(.target == $t) | .source' "$policy")"
        [[ "$dry_run" == "1" ]] || opc_copy "$src/$srel" "$ROOT/$srel"
        ;;
      seed-diff|seed-unknown|seed-diverged)
        if [[ "$dry_run" == "1" ]]; then echo "  [计划] $status $rel"; continue; fi
        echo "  $status $rel —— $detail"
        ;;
      config-add)
        local arr mkey
        arr="$(jq -r --arg t "$rel" '.mergeConfigs[] | select(.target == $t) | .arrayPath' "$policy")"
        mkey="$(jq -r --arg t "$rel" '.mergeConfigs[] | select(.target == $t) | .key' "$policy")"
        if [[ "$dry_run" == "1" ]]; then echo "  [计划] config-add $rel"; continue; fi
        while IFS= read -r k; do
          [[ -n "$k" ]] || continue
          merge_config_entry "$policy" "$src" "$rel" "$arr" "$mkey" "$k"
          echo "  config-add ${rel} —— 并入 ${k}（默认停用）"
          changed=$((changed + 1))
        done < <(config_missing_keys "$policy" "$src" "$rel" "$arr" "$mkey")
        ;;
    esac
  done < <(printf '%s\n' "$PLAN")

  CHANGED="$changed"
  CONFLICTS="$conflicts"
}

# ---------------------------------------------------------------- 状态与锁

write_state() {
  local src="$1" policy="$2" result="$3" commit="$4"
  mkdir -p "$ROOT/.opc"
  local files='{}'
  if [[ -f "$STATE" ]]; then files="$(jq '.files // {}' "$STATE")"; fi
  # 把这次同步到的 managed 文件记进状态（含哈希与 pin 标记）
  while IFS= read -r rel; do
    [[ -n "$rel" ]] || continue
    local hash pinned
    hash="$(opc_hash_of "$src/$rel" || echo "")"
    pinned="$(jq -r --arg p "$rel" '.files[$p].pinned // false' "$STATE" 2>/dev/null || echo false)"
    files="$(jq --arg p "$rel" --arg h "$hash" --argjson pinned "$pinned" \
      '. + {($p): {mode: "managed", hash: $h, pinned: $pinned}}' <<< "$files")"
  done < <(template_managed_files "$src" "$policy")
  jq -n --argjson files "$files" --argjson pv "$(jq '.version' "$policy")" \
        --arg at "$(opc_now)" --arg commit "$commit" --arg result "$result" \
    '{version: 1, policyVersion: $pv, lastSync: {at: $at, templateCommit: $commit, result: $result}, files: $files}' \
    > "$STATE"
}

write_lock() {
  local src="$1" commit="$2"
  jq -n --arg id "opc-template" --arg commit "$commit" --arg at "$(opc_now)" \
    '{template: {id: $id, commit: $commit}, syncedAt: $at}' > "$LOCK"
}

append_log() {
  mkdir -p "$(dirname "$LOG")"
  printf '%s %s\n' "$(opc_now)" "$*" >> "$LOG"
}

# ---------------------------------------------------------------- 子命令

cmd_status() {
  local from=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --from) from="$2"; shift 2 ;;
      *) echo "未知选项：$1" >&2; exit 2 ;;
    esac
  done
  local src commit
  src="$(resolve_source "${from:-}")"
  echo "实例：$ROOT"
  echo "  前缀：$(opc_prefix "$ROOT")"
  if [[ -n "$src" && -d "$src" ]]; then
    commit="$(git -C "$src" rev-parse --short HEAD 2>/dev/null || echo unknown)"
    echo "  模版来源：${src}（${commit}）"
  else
    echo "  模版来源：未找到（用 --from 指定）"
  fi
  if [[ -f "$STATE" ]]; then
    echo "  上次同步：$(jq -r '.lastSync.at // "无"' "$STATE")（$(jq -r '.lastSync.templateCommit // "-" // "-"' "$STATE")）"
    echo "  pinned：$(jq -r '[.files[]? | select(.pinned) ] | length' "$STATE") 个"
  else
    echo "  上次同步：无（还没接入，跑 adopt）"
  fi
  echo "  业务仓库远端：$(git -C "$ROOT" remote 2>/dev/null | tr '\n' ' ' || echo 无)"
}

cmd_check() {
  if opc_is_template_repo "$ROOT"; then
    opc_template_repo_refusal
    exit 2
  fi
  local from=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --from) from="$2"; shift 2 ;;
      *) echo "未知选项：$1" >&2; exit 2 ;;
    esac
  done
  local src policy
  src="$(resolve_source "${from:-}")"
  [[ -n "$src" && -d "$src" ]] || { echo "找不到模版来源，用 --from <路径> 指定" >&2; exit 2; }
  ACTIVE_SOURCE="$src"
  policy="$(load_policy "$src")"
  validate_policy "$policy" "$src"
  local plan actionable="" status rel detail
  plan="$(compute_plan "$src" "$policy" "$STATE" "")"
  # identical、seed-identical、seed-diverged（只有业务改了）以及本地 pin/定制
  # 都不需要同步处理。check 只报告模版侧真的有变化或缺基线/冲突的项，
  # 否则日常开工检查会永远退出 1。
  # unknown = 没有基线，判不出本地是否改过：这不是「没有差异」，必须报出来。
  while IFS='|' read -r status rel detail; do
    case "$status" in
      add|update|conflict|deferred|unknown|seed-add|seed-update|seed-diff|seed-unknown|config-add)
        actionable+="${status}|${rel}|${detail}"$'\n'
        ;;
    esac
  done <<< "$plan"
  actionable="${actionable%$'\n'}"
  if [[ -z "$actionable" ]]; then
    echo "没有待处理差异：模版托管文件已同步；业务自有改动保持不动"
    return 0
  fi
  printf '%-16s %-40s %s\n' "状态" "路径" "说明"
  while IFS='|' read -r status rel detail; do
    [[ -n "$status" ]] || continue
    printf '%-16s %-40s %s\n' "$status" "$rel" "$detail"
  done <<< "$actionable"
  return 1
}

cmd_pull() {
  local from="" dry=0 no_install=0 prune=0 force=0 accept=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --from) from="$2"; shift 2 ;;
      --dry-run) dry=1; shift ;;
      --no-install) no_install=1; shift ;;
      --prune) prune=1; shift ;;
      --force) force=1; shift ;;
      --accept-template) accept="${accept:+$accept,}$2"; shift 2 ;;
      *) echo "未知选项：$1" >&2; exit 2 ;;
    esac
  done

  if opc_is_template_repo "$ROOT"; then
    opc_template_repo_refusal
    exit 2
  fi
  local src policy
  src="$(resolve_source "$from")"
  [[ -n "$src" && -d "$src" ]] || { echo "找不到模版来源，用 --from <路径> 指定" >&2; exit 2; }
  ACTIVE_SOURCE="$src"
  policy="$(load_policy "$src")"
  validate_policy "$policy" "$src"
  mkdir -p "$ROOT/.opc"
  cp "$policy" "$ROOT/.opc/policy.json"

  local commit
  commit="$(git -C "$src" rev-parse --short HEAD 2>/dev/null || echo unknown)"

  echo "模版来源：${src}（${commit}）"
  echo "实例：$ROOT"

  # 护栏：只有「将被覆盖的路径」脏了才拒绝。业务文件没提交不该挡住同步。
  PLAN="$(compute_plan "$src" "$policy" "$STATE" "$accept")"
  if [[ "$force" == "0" ]] && git -C "$ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    local dirty_paths=() rel status
    while IFS='|' read -r status rel _; do
      case "$status" in
        add|update|conflict|seed-add|seed-update) dirty_paths+=("$rel") ;;
      esac
    done <<< "$PLAN"
    if [[ ${#dirty_paths[@]} -gt 0 ]]; then
      local dirty
      dirty="$(git -C "$ROOT" status --porcelain -- "${dirty_paths[@]}")"
      if [[ -n "$dirty" ]]; then
        echo "将被覆盖的路径有未提交改动，先提交或 stash（要强行同步用 --force）：" >&2
        printf '%s\n' "$dirty" >&2
        exit 1
      fi
    fi
  fi

  # 护栏：角色在跑时只提示
  if command -v hc >/dev/null 2>&1; then
    local prefix running
    prefix="$(opc_prefix "$ROOT")"
    running="$(hc ls --json 2>/dev/null | jq -r --arg p "$prefix-" '.. | objects | select(.name? | type == "string" and startswith($p)) | .name' 2>/dev/null | sort -u || true)"
    if [[ -n "$running" ]]; then
      echo "提示：本实例有角色在运行（$(echo "$running" | tr '\n' ' ')）。"
      echo "      提示词类改动（AGENTS.md、agents/）需重启才生效；重启会清空会话上下文，需要你确认。"
    fi
  fi

  apply_plan "$src" "$policy" "$STATE" "$dry" "$prune" "$accept"
  local changed conflicts
  changed="$CHANGED"
  conflicts="$CONFLICTS"

  if [[ "$dry" != "1" ]]; then
    write_state "$src" "$policy" "$([[ "$conflicts" -gt 0 ]] && echo conflict || echo ok)" "$commit"
    write_lock "$src" "$commit"
    append_log "sync from ${src} @ ${commit}：更新 ${changed} 个，冲突 ${conflicts} 个"
    if [[ "$no_install" != "1" ]]; then
      echo
      echo "重装模板与权限（脚本与角色简报变了才需要）…"
      "$ROOT/scripts/opc-install.sh" --no-input "$(opc_prefix "$ROOT")" || echo "安装失败：手动跑一次 scripts/opc-install.sh" >&2
    fi
  fi

  echo
  echo "同步完成：更新 $changed 个，冲突 $conflicts 个。"
  if [[ "$dry" != "1" && "$changed" -gt 0 ]]; then
    echo "提交（建议）："
    echo "  git add -A && git commit -m \"chore(sync): 模版 → $commit\""
  fi
  if [[ "$conflicts" -gt 0 ]]; then
    echo "冲突产物在 .opc/sync-conflicts/，业务文件未被改动。"
    exit 3
  fi
}

cmd_seeds() {
  local from="" apply_target="" merge_target=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --from) from="$2"; shift 2 ;;
      --apply) apply_target="$2"; shift 2 ;;
      --merge) merge_target="$2"; shift 2 ;;
      *) echo "未知选项：$1" >&2; exit 2 ;;
    esac
  done
  local src policy
  src="$(resolve_source "${from:-}")"
  [[ -n "$src" && -d "$src" ]] || { echo "找不到模版来源，用 --from <路径> 指定" >&2; exit 2; }
  ACTIVE_SOURCE="$src"
  policy="$(load_policy "$src")"
  validate_policy "$policy" "$src"

  if [[ -n "$apply_target" ]]; then
    local srel
    srel="$(jq -r --arg t "$apply_target" '.seeds[] | select(.target == $t) | .source' "$policy")"
    [[ -n "$srel" ]] || { echo "不是种子目标：$apply_target" >&2; exit 2; }
    opc_copy "$src/$srel" "$ROOT/$apply_target"
    opc_copy "$src/$srel" "$ROOT/$srel"
    echo "已用模版骨架覆盖 $apply_target"
    return 0
  fi

  if [[ -n "$merge_target" ]]; then
    local srel base ours theirs
    srel="$(jq -r --arg t "$merge_target" '.seeds[] | select(.target == $t) | .source' "$policy")"
    [[ -n "$srel" ]] || { echo "不是种子目标：$merge_target" >&2; exit 2; }
    base="$ROOT/$srel"; ours="$ROOT/$merge_target"; theirs="$src/$srel"
    [[ -f "$base" && -f "$ours" && -f "$theirs" ]] || { echo "三方合并需要基线、业务文件、模版骨架三份都在" >&2; exit 2; }
    mkdir -p "$CONFLICTS/$(dirname "$merge_target")"
    if git merge-file -p "$ours" "$base" "$theirs" > "$CONFLICTS/$merge_target.merge" 2>/dev/null; then
      opc_copy "$CONFLICTS/$merge_target.merge" "$ours"
      opc_copy "$theirs" "$base"
      echo "合并成功，已写回 $merge_target"
      return 0
    fi
    echo "有冲突：业务文件未改动。合并结果在 .opc/sync-conflicts/$merge_target.merge"
    return 3
  fi

  # 默认：打印每个种子的状态与 diff
  jq -r '.seeds[] | "\(.source)\t\(.target)"' "$policy" | while IFS=$'\t' read -r srel trel; do
    local tpl="$src/$srel" ours="$ROOT/$trel" snap="$ROOT/$srel"
    [[ -f "$tpl" ]] || continue
    if [[ ! -f "$ours" ]]; then
      echo "[待物化] ${trel}（模版有骨架，实例还没有）"
      continue
    fi
    if [[ "$(opc_hash_of "$ours")" == "$(opc_hash_of "$tpl")" ]]; then
      echo "[一致] $trel"
      continue
    fi
    if [[ -f "$snap" && "$(opc_hash_of "$ours")" == "$(opc_hash_of "$snap")" ]]; then
      echo "[可自动升级] ${trel}（业务没动过，模版骨架有改进）"
      diff -u "$ours" "$tpl" | sed 's/^/    /' || true
      continue
    fi
    if [[ -f "$snap" && "$(opc_hash_of "$tpl")" == "$(opc_hash_of "$snap")" ]]; then
      echo "[业务已改] ${trel}（模版骨架没动，无需处理）"
      continue
    fi
    echo "[需人工合并] ${trel}（业务已改，模版骨架也有改进）"
    diff -u "$ours" "$tpl" | sed 's/^/    /' || true
  done
}

cmd_mark() {
  local path="" unmark=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --unmark) unmark=1; shift ;;
      --*) echo "未知选项：$1" >&2; exit 2 ;;
      *) path="$1"; shift ;;
    esac
  done
  [[ -n "$path" ]] || { echo "用法：scripts/opc-sync.sh mark <路径> [--unmark]" >&2; exit 2; }
  [[ -f "$STATE" ]] || echo '{"version":1,"files":{}}' > "$STATE"
  local pin
  [[ "$unmark" == "1" ]] && pin=false || pin=true
  jq --arg p "$path" --argjson pin "$pin" \
    '.files[$p] = ((.files[$p] // {mode: "managed", hash: ""}) | .pinned = $pin)' \
    "$STATE" > "$STATE.tmp" && mv "$STATE.tmp" "$STATE"
  if [[ "$unmark" == "1" ]]; then
    echo "已解除 pin：$path"
  else
    echo "已 pin：${path}（模版此后不再覆盖它）"
  fi
}

cmd_adopt() {
  # 这两个命令会往当前目录写实例状态（.opc/ 与 template.lock.json）。
  # 在模版仓库里跑，模版就自己变成了半个实例。
  if opc_is_template_repo "$ROOT"; then
    opc_template_repo_refusal
    exit 2
  fi
  local from=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --from) from="$2"; shift 2 ;;
      *) echo "未知选项：$1" >&2; exit 2 ;;
    esac
  done
  [[ -n "$from" ]] || { echo "用法：scripts/opc-sync.sh adopt --from <模版路径>" >&2; exit 2; }
  [[ -d "$from" ]] || { echo "模版路径不存在：$from" >&2; exit 2; }
  ACTIVE_SOURCE="$from"
  local policy commit
  policy="$(load_policy "$from")"
  validate_policy "$policy" "$from"
  commit="$(git -C "$from" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  mkdir -p "$ROOT/.opc"
  cp "$policy" "$ROOT/.opc/policy.json"
  jq -n --arg prefix "$(opc_prefix "$ROOT")" --arg src "$from" --arg commit "$commit" --arg at "$(opc_now)" \
    '{version: 1, kind: "opc-instance", prefix: $prefix, createdAt: $at,
      template: {id: "opc-template", source: $src, commit: $commit}}' > "$INSTANCE_JSON"

  # 基线快照 = 模版当前内容。已有文件一律不覆盖。
  while IFS= read -r rel; do
    [[ -n "$rel" ]] || continue
    opc_copy "$from/$rel" "$BASE/$rel"
  done < <(template_managed_files "$from" "$policy")
  while IFS= read -r rel; do
    [[ -n "$rel" ]] || continue
    if [[ -f "$from/$rel" ]]; then
      opc_copy "$from/$rel" "$BASE/$rel"
      # 老实例通常还没有 seeds/ 快照。只补缺失项，不覆盖已有快照；
      # 后续 seed 判定才能区分「只有业务改了」与「骨架和业务都改了」。
      [[ -f "$ROOT/$rel" ]] || opc_copy "$from/$rel" "$ROOT/$rel"
    fi
  done < <(jq -r '.seeds[].source' "$policy")

  write_state "$from" "$policy" "adopted" "$commit"
  write_lock "$from" "$commit"
  append_log "adopt：模版来源 ${from} @ ${commit}（未改动任何已有文件）"
  echo "已接入模版：${from}（${commit}）"
  echo "  写入了 .opc/instance.json、.opc/policy.json、基线快照与 template.lock.json"
  echo "  补齐了缺失的 seeds/ 快照，没有覆盖任何已有文件。接着跑 scripts/opc-sync.sh check 看差异。"
}

cmd_baseline() {
  # 同 adopt：基线快照是实例状态，不该落在模版仓库里。
  if opc_is_template_repo "$ROOT"; then
    opc_template_repo_refusal
    exit 2
  fi
  local from=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --from) from="$2"; shift 2 ;;
      *) echo "未知选项：$1" >&2; exit 2 ;;
    esac
  done
  local src policy
  src="$(resolve_source "${from:-}")"
  [[ -n "$src" && -d "$src" ]] || { echo "找不到模版来源，用 --from <路径> 指定" >&2; exit 2; }
  ACTIVE_SOURCE="$src"
  policy="$(load_policy "$src")"
  validate_policy "$policy" "$src"
  mkdir -p "$ROOT/.opc"
  cp "$policy" "$ROOT/.opc/policy.json"

  # 基线 = 实例建立那一刻的模版内容。有基线才谈得上「模版更新了」，
  # 没有基线时 check 只能报「无法判断」，模版更新也就永远传不进实例。
  local created_commit=""
  if [[ -f "$INSTANCE_JSON" ]]; then
    created_commit="$(jq -r '.template.commit // ""' "$INSTANCE_JSON" 2>/dev/null || true)"
  fi

  local filled=0 kept=0
  while IFS= read -r rel; do
    [[ -n "$rel" ]] || continue
    if [[ -f "$BASE/$rel" ]]; then
      kept=$((kept + 1))
      continue
    fi
    if baseline_copy "$rel" "$src" "$created_commit" "$BASE/$rel"; then
      filled=$((filled + 1))
    fi
  done < <(template_managed_files "$src" "$policy")

  # seeds 快照：老实例可能没有，缺了就补，判种子差异才有基线可比。
  while IFS= read -r rel; do
    [[ -n "$rel" ]] || continue
    if [[ -f "$ROOT/$rel" ]]; then
      continue
    fi
    if baseline_copy "$rel" "$src" "$created_commit" "$ROOT/$rel"; then
      filled=$((filled + 1))
    fi
  done < <(jq -r '.seeds[].source' "$policy")

  local commit
  commit="$(git -C "$src" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  write_state "$src" "$policy" "baseline" "$commit"
  write_lock "$src" "$commit"
  append_log "baseline：模版来源 ${src} @ ${commit}（补齐 ${filled} 个基线，保留 ${kept} 个已有基线）"
  echo "已固化基线：新增 $filled 个，保留已有 $kept 个。"
  echo "  基线快照在 .opc/sync-base/；已有基线不会被覆盖，要重新固化就先删掉那个目录。"
  echo "  接着跑 scripts/opc-sync.sh check 看这次模版有什么变化。"
}

cmd_log() {
  local n=20
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -n) n="$2"; shift 2 ;;
      *) echo "未知选项：$1" >&2; exit 2 ;;
    esac
  done
  [[ -f "$LOG" ]] || { echo "还没有同步记录"; exit 0; }
  tail -n "$n" "$LOG"
}

# ---------------------------------------------------------------- 入口

[[ $# -ge 1 ]] || { usage >&2; exit 2; }
ALL_ARGS=("$@")
SUB="$1"; shift
self_update "${ALL_ARGS[@]}"
case "$SUB" in
  status) cmd_status "$@" ;;
  check) cmd_check "$@" ;;
  pull) cmd_pull "$@" ;;
  seeds) cmd_seeds "$@" ;;
  mark) cmd_mark "$@" ;;
  adopt) cmd_adopt "$@" ;;
  baseline) cmd_baseline "$@" ;;
  log) cmd_log "$@" ;;
  -h|--help|help) usage ;;
  *) echo "未知子命令：$SUB" >&2; usage >&2; exit 2 ;;
esac
