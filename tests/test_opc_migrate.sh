#!/usr/bin/env bash
# 旧实例一次性迁移的沙箱回归：删除实例内 UI/种子副本、改指纹模型、清理旧前缀 UI。
#
# 跑法：bash tests/test_opc_migrate.sh
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

say() { printf '%s\n' "$*"; }
ok()  { PASS=$((PASS + 1)); printf '  \033[32m通过\033[0m %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf '  \033[31m失败\033[0m %s\n' "$1"; }
check() { if [[ "$2" == "$3" ]]; then ok "$1"; else bad "$1（期望「$2」，实际「$3」）"; fi; }
expect() { local d="$1"; shift; if "$@" >/dev/null 2>&1; then ok "$d"; else bad "$d"; fi; }

export HOME="$WORK/home"
export XDG_CONFIG_HOME="$WORK/config"
export XDG_DATA_HOME="$WORK/data"
export HERDR_APP_HOME="$WORK/herdr-app"
export HERDR_CORE_HOME="$WORK/herdr-core"
export OPC_CONFIG_DIR="$WORK/config/opc"
export OPC_DATA_DIR="$WORK/data/opc"
export OPC_CACHE_DIR="$WORK/cache/opc"
export OPC_BIN_DIR="$WORK/bin"
export OPC_GIT_NAME="opc-test"
export OPC_GIT_EMAIL="opc-test@example.invalid"
mkdir -p "$HOME" "$HERDR_APP_HOME" "$HERDR_CORE_HOME" "$OPC_BIN_DIR"

INST="$WORK/inst"
"$ROOT/bin/opc" install "$INST" t --template "$ROOT" --no-input --skip-smoke >/dev/null 2>&1
check "install 返回 0" "0" "$?"

say "迁移场景"

# 造出旧结构的残留，并按旧实例的样子提交（干净工作区）
mkdir -p "$INST/layouts" "$INST/mods/t-opc-dashboard" "$INST/seeds/knowledge" \
         "$INST/tools/tests" "$INST/scripts" "$INST/.opc/sync-base/scripts"
printf '{"name":"t"}\n' > "$INST/layouts/t.json"
printf '{"name":"t-opc-dashboard"}\n' > "$INST/mods/t-opc-dashboard/mod.json"
printf '# old seed\n' > "$INST/seeds/knowledge/品牌口径.md"
printf '# old test\n' > "$INST/tools/tests/old.py"
printf '{"version":0}\n' > "$INST/sync-policy.json"
printf '#!/usr/bin/env bash\n' > "$INST/scripts/opc-sync.sh"
printf '#!/usr/bin/env bash\n' > "$INST/scripts/opc-new.sh"
cp "$INST/scripts/opc-up.sh" "$INST/.opc/sync-base/scripts/opc-up.sh"
printf '{"locked":true}\n' > "$INST/template.lock.json"
(
  cd "$INST" || exit 1
  git add -A
  git -c user.name="$OPC_GIT_NAME" -c user.email="$OPC_GIT_EMAIL" \
    commit -m "legacy fixture" >/dev/null 2>&1
)
check "旧结构已提交" "0" "$?"

# 旧前缀的全局 UI 残留
mkdir -p "$HERDR_APP_HOME/mods/t-opc-dashboard"
printf '{"name":"t"}\n' > "$HERDR_APP_HOME/layouts/t.json"
printf '{}\n' > "$HERDR_APP_HOME/mods/t-opc-dashboard/mod.json"

knowledge_before="$(find "$INST/knowledge" -type f -exec shasum {} + | sort | shasum | awk '{print $1}')"

# dry-run 不写任何东西
out="$("$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --dry-run 2>&1)"
rc=$?
check "迁移 --dry-run 返回 0" "0" "$rc"
expect "dry-run 打印实例内删除项" grep -q "实例内删除" <<< "$out"
expect "dry-run 不删除旧结构" test -d "$INST/layouts"
expect "dry-run 不动知识库" test -d "$INST/knowledge"

# 正式迁移
"$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --yes --skip-smoke >/dev/null 2>&1
check "迁移返回 0" "0" "$?"

expect "实例内 layouts/ 已删除" test ! -e "$INST/layouts"
expect "实例内 mods/ 已删除" test ! -e "$INST/mods"
expect "实例内 seeds/ 已删除" test ! -e "$INST/seeds"
expect "tools/tests 已删除" test ! -e "$INST/tools/tests"
expect "sync-policy.json 已删除" test ! -e "$INST/sync-policy.json"
expect "template.lock.json 已删除" test ! -e "$INST/template.lock.json"
expect "旧同步脚本已删除" test ! -e "$INST/scripts/opc-sync.sh"
expect "旧建实例脚本已删除" test ! -e "$INST/scripts/opc-new.sh"
expect "sync-base 已删除" test ! -e "$INST/.opc/sync-base"
expect "新指纹文件已写入" test -f "$INST/.opc/mechanism.json"
expect "旧前缀布局已清理" test ! -e "$HERDR_APP_HOME/layouts/t.json"
expect "旧前缀 mod 已清理" test ! -e "$HERDR_APP_HOME/mods/t-opc-dashboard"
expect "全局 opc 布局已安装" test -f "$HERDR_APP_HOME/layouts/opc.json"

knowledge_after="$(find "$INST/knowledge" -type f -exec shasum {} + | sort | shasum | awk '{print $1}')"
check "knowledge/ 哈希不变" "$knowledge_before" "$knowledge_after"

commits="$(cd "$INST" && git rev-list --count HEAD)"
check "迁移只产生一个提交（安装 + 旧结构 + 迁移）" "3" "$commits"

# 迁移后再次升级走普通指纹路径
"$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --skip-smoke >/dev/null 2>&1
check "迁移后再升级返回 0" "0" "$?"

say "角色单文件迁移"

# 旧角色布局：roles.json 指向 agents/ 下的单文件简报，机制指纹里留着那些文件
INST2="$WORK/inst-roles"
"$ROOT/bin/opc" install "$INST2" t2 --template "$ROOT" --no-input --skip-smoke >/dev/null 2>&1
check "角色迁移用例的实例准备就绪" "0" "$?"

python3 - "$INST2" <<'PY'
import hashlib
import json
import pathlib
import shutil
import sys

inst = pathlib.Path(sys.argv[1])


def sha_text(text):
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


# 角色 -> (描述, 正文, owner 追加的段落)
OLD = {
    "gm": ("OPC 公司总经理。旧实例的描述。",
           "你现在是 **OPC 公司的总经理（gm）**。\n\n"
           "旧实例里的 gm 正文，通知走 {{PREFIX}}-gm。\n", ""),
    "content": ("OPC 内容经理。旧实例的描述。",
                "你现在是 **OPC 公司的内容经理（content）**。\n\n"
                "旧实例里的 content 正文。\n", "\nowner 的补充。\n"),
}

roles = json.loads((inst / "roles.json").read_text(encoding="utf-8"))
mech_path = inst / ".opc" / "mechanism.json"
mech = json.loads(mech_path.read_text(encoding="utf-8"))

for role in roles["roles"]:
    name = role["name"]
    if name not in OLD:
        continue
    desc, body, owner = OLD[name]
    brief = ("---\nname: {{PREFIX}}-%s\ndescription: %s\ncommand: zsh -lic claude\n---\n\n%s"
             % (name, desc, body))
    old_rel = "agents/opc-%s.md" % name
    (inst / old_rel).write_text(brief + owner, encoding="utf-8")
    shutil.rmtree(inst / "agents" / name)
    role["template"] = old_rel
    role.pop("description", None)
    role.pop("skills", None)
    # 旧指纹记的是装进来时那份的哈希：owner 改过的角色就对不上号了
    mech["files"][old_rel] = sha_text(brief)

(inst / "roles.json").write_text(
    json.dumps(roles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
mech_path.write_text(
    json.dumps(mech, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
(inst / ".opc" / "starters.json").unlink()
PY
check "旧角色布局造好" "0" "$?"

(
  cd "$INST2" || exit 1
  git add -A
  git -c user.name="$OPC_GIT_NAME" -c user.email="$OPC_GIT_EMAIL" \
    commit -m "旧角色布局" >/dev/null 2>&1
)
check "旧角色布局已提交" "0" "$?"

# dry-run 零写入
out="$("$ROOT/bin/opc" upgrade "$INST2" --template "$ROOT" --dry-run 2>&1)"
check "角色迁移 --dry-run 返回 0" "0" "$?"
expect "dry-run 打印角色迁移" grep -q "角色迁移" <<< "$out"
expect "dry-run 打印要建的角色目录" grep -q "agents/gm/AGENTS.md" <<< "$out"
expect "dry-run 打印备份位置" grep -q ".opc/backups/agents/opc-gm.md" <<< "$out"
expect "dry-run 不建角色目录" test ! -e "$INST2/agents/gm"
expect "dry-run 不动旧简报" test -f "$INST2/agents/opc-gm.md"
expect "dry-run 不写备份" test ! -e "$INST2/.opc/backups"
expect "dry-run 不写基线" test ! -e "$INST2/.opc/starters.json"
expect "dry-run 不改 roles.json" grep -q "agents/opc-gm.md" "$INST2/roles.json"
expect "dry-run 后工作区干净" test -z "$(git -C "$INST2" status --porcelain)"

knowledge_before="$(find "$INST2/knowledge" -type f -exec shasum {} + | sort | shasum | awk '{print $1}')"

# 正式升级
out="$("$ROOT/bin/opc" upgrade "$INST2" --template "$ROOT" --skip-smoke 2>&1)"
check "角色迁移升级返回 0" "0" "$?"
expect "升级打印了角色迁移" grep -q "角色迁移" <<< "$out"

expect "角色目录建出来了" test -f "$INST2/agents/gm/AGENTS.md"
expect "旧正文保留" grep -q "旧实例里的 gm 正文" "$INST2/agents/gm/AGENTS.md"
expect "占位符原样保留" grep -q "{{PREFIX}}-gm" "$INST2/agents/gm/AGENTS.md"
expect "frontmatter 已摘掉" bash -c "! head -n 1 '$INST2/agents/gm/AGENTS.md' | grep -q '^---$'"
expect "owner 改过的正文也保留" grep -q "owner 的补充" "$INST2/agents/content/AGENTS.md"

expect "旧简报已移除" test ! -e "$INST2/agents/opc-gm.md"
expect "旧简报已备份" test -f "$INST2/.opc/backups/agents/opc-gm.md"
expect "备份保留原始 frontmatter" grep -q "^description: OPC 公司总经理。旧实例的描述。$" \
  "$INST2/.opc/backups/agents/opc-gm.md"

check "描述迁进 roles.json" "OPC 公司总经理。旧实例的描述。" \
  "$(jq -r '.roles[]|select(.name=="gm")|.description' "$INST2/roles.json")"
check "模板路径指向角色目录" "agents/gm/AGENTS.md" \
  "$(jq -r '.roles[]|select(.name=="gm")|.template' "$INST2/roles.json")"
check "迁移后 skills 是空数组" "0" \
  "$(jq -r '.roles[]|select(.name=="gm")|.skills|length' "$INST2/roles.json")"
check "迁移后 skills 仍是数组" "array" \
  "$(jq -r '.roles[]|select(.name=="gm")|.skills|type' "$INST2/roles.json")"
check "别的角色没被套上默认技能" "knowledge-writing" \
  "$(jq -r '.roles[]|select(.name=="growth")|.skills[0]' "$INST2/roles.json")"

check "基线记了迁移出来的角色文件" "role" \
  "$(jq -r '.files["agents/gm/AGENTS.md"].kind' "$INST2/.opc/starters.json")"
check "owner 改过的角色被钉住" "true" \
  "$(jq -r '.files["agents/content/AGENTS.md"].pinned' "$INST2/.opc/starters.json")"
check "没改过的角色不钉住" "null" \
  "$(jq -r '.files["agents/gm/AGENTS.md"].pinned // "null"' "$INST2/.opc/starters.json")"

knowledge_after="$(find "$INST2/knowledge" -type f -exec shasum {} + | sort | shasum | awk '{print $1}')"
check "knowledge/ 哈希不变" "$knowledge_before" "$knowledge_after"

expect "hc 模板用上迁移后的描述" grep -q "OPC 公司总经理。旧实例的描述。" \
  "$HERDR_CORE_HOME/templates/t2-gm.md"
expect "hc 模板里没有技能索引" bash -c "! grep -q '技能索引' '$HERDR_CORE_HOME/templates/t2-gm.md'"

committed="$(git -C "$INST2" diff-tree --no-commit-id --name-only -r --no-renames HEAD \
  | sort | tr '\n' ' ')"
check "升级提交只含迁移相关文件" \
  "agents/content/AGENTS.md agents/gm/AGENTS.md agents/opc-content.md agents/opc-gm.md roles.json " \
  "$committed"

# 幂等：再升级一次不重做迁移
content_before="$(shasum "$INST2/agents/content/AGENTS.md" | awk '{print $1}')"
out="$("$ROOT/bin/opc" upgrade "$INST2" --template "$ROOT" --skip-smoke 2>&1)"
check "再次升级返回 0" "0" "$?"
if grep -q "角色迁移" <<< "$out"; then
  bad "再次升级不该再做角色迁移"
else
  ok "再次升级不再做角色迁移"
fi
check "再次升级不覆盖 owner 改过的角色" "$content_before" \
  "$(shasum "$INST2/agents/content/AGENTS.md" | awk '{print $1}')"
expect "再次升级不多备份" test "$(find "$INST2/.opc/backups" -type f | wc -l | tr -d ' ')" = "2"
expect "再次升级不重建角色目录" test -f "$INST2/agents/gm/AGENTS.md"

# 换模版升级：owner 改过的角色不被覆盖，没改过的跟随模版
TPL2="$WORK/tpl2"
mkdir -p "$TPL2"
cp -R "$ROOT/template" "$TPL2/template"
printf '\n模版侧的新版本。\n' >> "$TPL2/template/agents/gm/AGENTS.md"
printf '\n模版侧的新版本。\n' >> "$TPL2/template/agents/content/AGENTS.md"
"$ROOT/bin/opc" upgrade "$INST2" --template "$TPL2" --skip-smoke >/dev/null 2>&1
check "换模版升级成功" "0" "$?"
expect "owner 改过的角色不被模版覆盖" \
  bash -c "! grep -q '模版侧的新版本' '$INST2/agents/content/AGENTS.md'"
expect "owner 改过的角色内容还在" grep -q "owner 的补充" "$INST2/agents/content/AGENTS.md"
expect "没改过的角色跟随模版更新" grep -q "模版侧的新版本" "$INST2/agents/gm/AGENTS.md"

say "角色简报是软链接"

# 旧简报是指向实例外的软链接：迁移不能把实例外的内容抄进角色提示词
INST3="$WORK/inst-link"
"$ROOT/bin/opc" install "$INST3" t3 --template "$ROOT" --no-input --skip-smoke >/dev/null 2>&1
check "软链接用例的实例准备就绪" "0" "$?"
OUTSIDE="$WORK/outside-brief.md"
printf '实例外的机密内容。\n' > "$OUTSIDE"
rm -f "$INST3/agents/opc-gm.md"
ln -s "$OUTSIDE" "$INST3/agents/opc-gm.md"
python3 - "$INST3" <<'PY'
import json
import pathlib
import sys

inst = pathlib.Path(sys.argv[1])
roles = json.loads((inst / "roles.json").read_text(encoding="utf-8"))
for role in roles["roles"]:
    if role["name"] == "gm":
        role["template"] = "agents/opc-gm.md"
        role.pop("description", None)
(inst / "roles.json").write_text(
    json.dumps(roles, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
rm -f "$INST3/.opc/starters.json"
(
  cd "$INST3" || exit 1
  git add -A
  git -c user.name="$OPC_GIT_NAME" -c user.email="$OPC_GIT_EMAIL" \
    commit -m "旧简报是软链接" >/dev/null 2>&1
)

out="$("$ROOT/bin/opc" upgrade "$INST3" --template "$ROOT" --skip-smoke 2>&1)"
check "软链接旧简报的升级返回 0" "0" "$?"
expect "升级提示旧简报指向实例外" grep -q "指向实例外" <<< "$out"
expect "实例外的内容没进角色提示词" \
  bash -c "! grep -rq '实例外的机密内容' '$INST3/agents' 2>/dev/null"
expect "实例外的文件没有被改写" grep -q "实例外的机密内容" "$OUTSIDE"
expect "软链接本身没被删掉" test -L "$INST3/agents/opc-gm.md"

say ""
say "汇总：通过 ${PASS} 项 / 失败 ${FAIL} 项"
[[ "$FAIL" -eq 0 ]]
