#!/usr/bin/env bash
# 启动 OPC 团队：一个 Herdr space，每个角色一个 tab，每个 tab 一个 agent 终端。
# 用法：scripts/opc-up.sh [--install] [角色...]
#   不带角色 = 启动 roles.json 里所有已启用角色
#   --install = 模板或启动器缺失时先跑安装脚本（默认不自动执行）
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

ROOT="$(opc_root)"
PREFIX="$(opc_prefix "$ROOT")"
SPACE_NAME="$PREFIX 团队"

command -v herdr-app >/dev/null || { echo "找不到 herdr-app" >&2; exit 1; }
command -v hc        >/dev/null || { echo "找不到 hc" >&2; exit 1; }

# 解析参数：--install 是显式选择，默认绝不自动执行安装脚本
install_first=0
requested=()
for arg in "$@"; do
  case "$arg" in
    --install) install_first=1 ;;
    -*) echo "未知参数：$arg" >&2; exit 1 ;;
    *) requested+=("$arg") ;;
  esac
done

# 本次启动哪些角色
if [[ ${#requested[@]} -eq 0 ]]; then
  roles=($(opc_roles))
else
  roles=()
  for r in "${requested[@]}"; do
    opc_role_exists "$r" || { echo "未知角色：${r}（见 roles.json）" >&2; exit 1; }
    opc_role_enabled "$r" || { echo "角色已停用：${r}（用 scripts/opc-role.sh enable $r 启用）" >&2; exit 1; }
    roles+=("$r")
  done
fi
[[ ${#roles[@]} -gt 0 ]] || { echo "没有可启动的角色" >&2; exit 1; }

# 模板或启动器缺失：默认 fail-closed，只有显式 --install 才执行安装脚本
need_install=0
for role in "${roles[@]}"; do
  if [[ ! -f "$(opc_templates_dir)/$PREFIX-$role.md" || ! -x "$ROOT/.opc/run/$role.sh" ]]; then
    need_install=1
  fi
done
if [[ $need_install -eq 1 ]]; then
  if [[ $install_first -eq 1 ]]; then
    echo "模板或启动器缺失，按 --install 执行安装"
    "$ROOT/scripts/opc-install.sh" || { echo "安装失败" >&2; exit 1; }
  else
    echo "模板或启动器缺失。先跑 scripts/opc-install.sh，或 opc-up.sh --install" >&2
    exit 1
  fi
fi

# 1. 找到或新建 space
space_id=$(herdr-app ls | jq -r --arg n "$SPACE_NAME" '.spaces[] | select(.name==$n) | .id' | head -1)
first_tab="" ; first_term=""
if [[ -z "$space_id" ]]; then
  created=$(herdr-app do space.new --name "$SPACE_NAME" --folder "$ROOT")
  space_id=$(printf '%s' "$created" | jq -r '.space')
  first_tab=$(printf '%s' "$created" | jq -r '.tab // empty')
  first_term=$(printf '%s' "$created" | jq -r '.terminal // empty')
  echo "新建 space：${SPACE_NAME}（${space_id}）"
else
  echo "复用 space：${SPACE_NAME}（${space_id}）"
fi

# 2. 逐角色建 tab 并启动 agent
for role in "${roles[@]}"; do
  tname="$PREFIX-$role"

  # 已有同名 tab 就直接用，否则新建
  tab_id=$(herdr-app ls | jq -r --arg s "$space_id" --arg n "$role" \
    '.spaces[] | select(.id==$s) | .tabs[] | select(.name==$n) | .id' | head -1)
  placeholder=""
  if [[ -z "$tab_id" && -n "$first_tab" && "$role" == "gm" ]]; then
    tab_id="$first_tab"; placeholder="$first_term"; first_tab=""
    herdr-app do tab.rename --id "$tab_id" --name "$role" >/dev/null
  elif [[ -z "$tab_id" ]]; then
    t=$(herdr-app do tab.new --name "$role" --space "$space_id" --folder "$ROOT")
    tab_id=$(printf '%s' "$t" | jq -r '.tab')
    placeholder=$(printf '%s' "$t" | jq -r '.terminal // empty')
  fi

  # 该角色是否已在跑（herdr 的终端 name 字段）
  if herdr-app ls | jq -e --arg t "$tab_id" --arg n "$tname" \
      '.spaces[].tabs[] | select(.id==$t) | .terminals[] | select(.name==$n)' >/dev/null 2>&1; then
    echo "  跳过 ${tname}（已在运行）"
    [[ -n "$placeholder" ]] && herdr-app do terminal.kill --terminal "$placeholder" >/dev/null 2>&1 || true
    continue
  fi

  hc run --bg --name "$tname" --cwd "$ROOT" --no-parent \
    --label "herdr.space=$space_id" --label "herdr.tab=$tab_id" -- "$tname" \
    || { echo "  启动 $tname 失败" >&2; continue; }

  # 等 agent 落进 tab，再关掉 tab 自带的占位 shell
  for _ in $(seq 1 20); do
    herdr-app ls | jq -e --arg t "$tab_id" --arg n "$tname" \
      '.spaces[].tabs[] | select(.id==$t) | .terminals[] | select(.name==$n)' >/dev/null 2>&1 && break
    sleep 0.25
  done
  [[ -n "$placeholder" ]] && herdr-app do terminal.kill --terminal "$placeholder" >/dev/null 2>&1 || true
  echo "  启动 $tname"
done

# 3. 信任对话框是安全闸门，脚本不代按
echo
echo "若某个 tab 停在「Do you trust this folder?」，请在该 tab 里手动确认"
echo "（或 hc keys <终端名> down enter）。脚本不会替你按。"

echo
echo "已启动：$(echo "${roles[@]}" | tr ' ' ', ')"
echo "Herdr 里看「${SPACE_NAME}」，或 hc ls 查看终端。状态：scripts/opc-status.sh"
