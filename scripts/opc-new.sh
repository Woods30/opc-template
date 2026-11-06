#!/usr/bin/env bash
# 用本模版开一个新 OPC 实例：复制骨架到目标目录，写实例元数据，初始化业务 git 仓库，安装模板。
#
# 用法：
#   scripts/opc-new.sh <目标目录> [前缀] [选项]
#
# 选项：
#   --source <模版路径>   模版来源，默认是本仓库
#   --prefix <前缀>       实例前缀，默认取目标目录名 slug 化
#   --git-init            在实例里 git init 并做首次提交（默认开）
#   --no-git-init         不初始化 git
#   --no-install          不自动跑安装
#   --interactive         安装时先选角色与 CLI（终端里默认就会问）
#   --no-input            安装时不提问
#   --dry-run             只打印将要做什么，不落盘
set -euo pipefail
source "$(cd "$(dirname "$0")" && pwd)/lib.sh"

SRC="$(opc_root)"
TARGET_ARG=""
PREFIX=""
SOURCE="$SRC"
DO_GIT=1
DO_INSTALL=1
DRY_RUN=0
INSTALL_INPUT=""

usage() {
  cat <<'EOF'
用法：
  scripts/opc-new.sh <目标目录> [前缀] [选项]

选项：
  --source <模版路径>   模版来源，默认是本仓库
  --prefix <前缀>       实例前缀，默认取目标目录名 slug 化
  --git-init            在实例里 git init 并做首次提交（默认开）
  --no-git-init         不初始化 git
  --no-install          不自动跑安装
  --interactive         安装时先选角色与 CLI（终端里默认就会问）
  --no-input            安装时不提问
  --dry-run             只打印将要做什么，不落盘
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) SOURCE="$2"; shift 2 ;;
    --prefix) PREFIX="$2"; shift 2 ;;
    --git-init) DO_GIT=1; shift ;;
    --no-git-init) DO_GIT=0; shift ;;
    --no-install) DO_INSTALL=0; shift ;;
    --interactive) INSTALL_INPUT="--interactive"; shift ;;
    --no-input) INSTALL_INPUT="--no-input"; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    --*) echo "未知选项：$1" >&2; usage >&2; exit 2 ;;
    *)
      if [[ -z "$TARGET_ARG" ]]; then TARGET_ARG="$1"
      elif [[ -z "$PREFIX" ]]; then PREFIX="$1"
      else echo "多余参数：$1" >&2; usage >&2; exit 2
      fi
      shift ;;
  esac
done

[[ -n "$TARGET_ARG" ]] || { usage >&2; exit 2; }

SOURCE="$(cd "$SOURCE" && pwd)"
[[ -d "$SOURCE" ]] || { echo "模版来源不存在：$SOURCE" >&2; exit 2; }
[[ -f "$SOURCE/.opc-template-repo" ]] || {
  echo "模版来源不是 OPC 模版仓库（缺 .opc-template-repo）：$SOURCE" >&2; exit 2; }

mkdir -p "$TARGET_ARG"
TARGET="$(cd "$TARGET_ARG" && pwd)"
[[ -n "$PREFIX" ]] || PREFIX="$(basename "$TARGET" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_-]/-/g')"

[[ "$TARGET" != "$SOURCE" ]] || { echo "目标就是模版自身，模版仓库不承载业务数据。" >&2; exit 1; }
case "$TARGET/" in
  "$SOURCE/"*) echo "目标不能放在模版目录内部：$TARGET" >&2; exit 1 ;;
esac
[[ -z "$(ls -A "$TARGET")" ]] || { echo "目标目录非空：$TARGET" >&2; exit 1; }

# 复制骨架。模版独占的东西不进实例：
#   .git          —— 实例自己开仓库
#   .opc          —— 本机运行态，实例自己生成
#   .opc-template-repo —— 标记「这是模版」，进了实例会让实例自认是模版
#   .github/ docs/     —— 模版侧档案（CI、提案存档、同步说明）
#   sync-policy.json   —— 同步策略，实例侧由 opc-sync.sh 缓存到 .opc/policy.json
#   /knowledge    —— 模版工作区的本地业务数据（sync-policy 里的 local）；
#                   实例的知识目录由安装器从 seeds/ 物化，不从模版复制
#   README.md     —— 模版视角的说明书，实例用 seeds/README.md 那一份
#                   （用 /README.md 锚定根目录，否则会连 seeds/ 下的同名文件一起排除）
#   template.lock.json —— 实例自己的同步状态（记着接的是哪个模版提交）。
#                   模版工作区里可能有一份旧的，复制过去新实例就会以为
#                   自己已经接上了那个提交，所以明确排除。
RSYNC_EXCLUDES=(
  --exclude '.git' --exclude '.opc' --exclude '.opc-template-repo'
  --exclude '.github' --exclude 'docs' --exclude 'sync-policy.json'
  --exclude '/knowledge' --exclude '/README.md'
  --exclude 'template.lock.json'
)

if [[ "$DRY_RUN" == "1" ]]; then
  echo "将创建实例：${TARGET}（前缀 ${PREFIX}）"
  echo "  模版来源：$SOURCE"
  echo "  复制内容：除 .git/.opc/.opc-template-repo/.github/docs/sync-policy.json/knowledge/template.lock.json 外的全部"
  [[ "$DO_GIT" == "1" ]] && echo "  git：init + 首次提交"
  echo "  基线：写 .opc/sync-base（建实例这一刻的模版内容）"
  if [[ "$DO_INSTALL" == "1" ]]; then
    if [[ -n "$INSTALL_INPUT" ]]; then
      echo "  安装：scripts/opc-install.sh $INSTALL_INPUT $PREFIX"
    else
      echo "  安装：scripts/opc-install.sh ${PREFIX}（终端里跑会先问角色与 CLI）"
    fi
  fi
  exit 0
fi

rsync -a "${RSYNC_EXCLUDES[@]}" "$SOURCE/" "$TARGET/"

# 实例元数据：模版来源、前缀、创建时间。放在 .opc/ 下，不进版本库。
mkdir -p "$TARGET/.opc"
TPL_COMMIT="$(git -C "$SOURCE" rev-parse --short HEAD 2>/dev/null || echo "unknown")"
cat > "$TARGET/.opc/instance.json" <<EOF
{
  "version": 1,
  "kind": "opc-instance",
  "prefix": "$PREFIX",
  "createdAt": "$(date -Iseconds)",
  "template": {
    "id": "opc-template",
    "source": "$SOURCE",
    "commit": "$TPL_COMMIT"
  }
}
EOF

if [[ "$DO_GIT" == "1" ]]; then
  git -C "$TARGET" init -q -b main
  git -C "$TARGET" add -A
  if git -C "$TARGET" -c user.name="$(git -C "$SOURCE" config user.name 2>/dev/null || echo "$USER")" \
                -c user.email="$(git -C "$SOURCE" config user.email 2>/dev/null || echo "$USER@localhost")" \
                commit -q -m "chore: 实例初始快照（模版骨架 + 配置）"; then
    echo "已初始化业务 git 仓库并完成首次提交"
  else
    echo "git 仓库已初始化，但首次提交失败（检查 git user.name/user.email 配置）" >&2
  fi
fi

# 基线快照：实例建立这一刻的模版内容。有基线，模版后续的机制更新才能被
# check 检出、被 pull 落地；没有基线，实例会永远停在建实例那天的版本上。
if [[ -x "$TARGET/scripts/opc-sync.sh" ]]; then
  if "$TARGET/scripts/opc-sync.sh" baseline --from "$SOURCE" >/dev/null 2>&1; then
    echo "已写入基线快照（.opc/sync-base）"
  else
    echo "提示：基线快照没建成，之后跑 scripts/opc-sync.sh baseline --from <模版> 补上" >&2
  fi
fi

if [[ "$DO_INSTALL" == "1" ]]; then
  case "$INSTALL_INPUT" in
    "") "$TARGET/scripts/opc-install.sh" "$PREFIX" ;;
    *)  "$TARGET/scripts/opc-install.sh" "$INSTALL_INPUT" "$PREFIX" ;;
  esac
fi

echo
echo "新实例已建好：$TARGET"
echo "  前缀：$PREFIX"
echo "  模版来源：$SOURCE"
if [[ "$DO_INSTALL" == "1" ]]; then
  echo "  下一步：cd \"$TARGET\" && scripts/opc-up.sh"
else
  echo "  下一步：cd \"$TARGET\" && scripts/opc-install.sh $PREFIX && scripts/opc-up.sh"
fi
