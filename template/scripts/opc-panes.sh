#!/usr/bin/env bash
# 把团队角色铺成一屏多 pane：scripts/opc-panes.sh [角色...]
#
#   不带参数    gm content growth dev（当前启用的角色，最多 4 个）
#   1-4 个角色  按参数顺序铺开
#
# 做法：新开一个 tab，第一格 attach 第一个角色，其余用 pane.split + `hc attach`
# 铺成 2 / 3 / 4 宫格。每个 pane 里跑的是 `hc attach <角色终端>`，只是看它的画面；
# 按 ctrl+\ 脱离后回到普通 shell。
#
# 配合全局布局用：`opc-grid`（无侧栏、无面板）留给 pane 最大空间；
# 用 ctrl-shift-l 或 `herdr-app do layout.switch '{"name":"opc-grid"}'` 切换。
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

ROOT="$(opc_root)"
PREFIX="$(opc_prefix "$ROOT")"

command -v herdr-app >/dev/null || { echo "找不到 herdr-app" >&2; exit 1; }
command -v jq        >/dev/null || { echo "找不到 jq" >&2; exit 1; }

if (( $# > 0 )); then
  roles=("$@")
else
  roles=()
  for r in $(opc_all_roles); do
    opc_role_enabled "$r" && roles+=("$r")
  done
fi

n=${#roles[@]}
if (( n < 1 || n > 4 )); then
  echo "用法：scripts/opc-panes.sh [角色...]（1-4 个，不给参数则用全部启用角色）" >&2
  exit 2
fi

for r in "${roles[@]}"; do
  opc_role_exists "$r" || { echo "没有这个角色：$r" >&2; exit 2; }
done

# 在指定 pane 里拆一格，并 attach 某个角色
split() { # split <right|down> <pane> <role>
  herdr-app do pane.split "$(jq -nc \
    --arg d "$1" --arg p "$2" --arg c "hc attach $PREFIX-$3" \
    '{direction: $d, pane: $p, argv: ["zsh", "-lic", $c]}')"
}

# tab.new 只返回 space/tab/terminal，pane id 要自己查
pane_of() { # pane_of <terminal>
  herdr-app ls | jq -r --arg t "$1" \
    '[.spaces[].tabs[].terminals[] | select(.terminal == $t) | .pane] | first // empty'
}

case "$n" in
  1) label="单格" ;;
  2) label="左右两格" ;;
  3) label="三格" ;;
  4) label="四宫格" ;;
esac

first=$(herdr-app do tab.new "$(jq -nc \
  --arg name "团队 ${label}" --arg c "hc attach $PREFIX-${roles[0]}" \
  '{name: $name, argv: ["zsh", "-lic", $c]}')")
first_term=$(printf '%s' "$first" | jq -r '.terminal')
p1=$(pane_of "$first_term")
[[ -n "$p1" ]] || { echo "没拿到新 tab 的 pane（terminal=${first_term}）" >&2; exit 1; }

case "$n" in
  2)
    split right "$p1" "${roles[1]}" >/dev/null
    ;;
  3)
    p2=$(split right "$p1" "${roles[1]}" | jq -r '.pane')
    split down "$p2" "${roles[2]}" >/dev/null
    ;;
  4)
    p2=$(split right "$p1" "${roles[1]}" | jq -r '.pane')
    split down "$p2" "${roles[2]}" >/dev/null
    split down "$p1" "${roles[3]}" >/dev/null
    ;;
esac

echo "已开「团队 ${label}」：${roles[*]}"
echo "切到紧凑布局：herdr-app do layout.switch '{\"name\":\"opc-grid\"}'"
