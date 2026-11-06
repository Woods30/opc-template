#!/usr/bin/env bash
# 升级（机制指纹 + 起始材料基线）的沙箱回归。
#
# 跑法：bash tests/test_opc_upgrade.sh
# 全程只动 mktemp 目录与沙箱 HOME/XDG 路径，不碰本机真实实例。
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
mkdir -p "$HOME" "$HERDR_APP_HOME" "$HERDR_CORE_HOME" "$OPC_BIN_DIR"

# 起始材料的基线检查：机制指纹不该再覆盖起始材料，基线要记全。
cat > "$WORK/starter_check.py" <<'PY'
import json
import sys

inst, what = sys.argv[1], sys.argv[2]
mech = json.load(open(inst + "/.opc/mechanism.json"))["files"]
base = json.load(open(inst + "/.opc/starters.json"))["files"]
if what == "mech-clean":
    ok = not any(k == "AGENTS.md" or k.startswith(("agents/", "skills/")) for k in mech)
elif what == "base-has":
    ok = all(p in base for p in sys.argv[3:])
elif what == "base-lacks":
    ok = all(p not in base for p in sys.argv[3:])
else:
    ok = False
sys.exit(0 if ok else 1)
PY
check_starter() {
  local inst="$1"; local d="$2"; shift 2
  if python3 "$WORK/starter_check.py" "$inst" "$@" >/dev/null 2>&1; then
    ok "$d"
  else
    bad "$d"
  fi
}

INST="$WORK/inst"
"$ROOT/bin/opc" install "$INST" t --template "$ROOT" --no-input --skip-smoke >/dev/null 2>&1
check "install 返回 0" "0" "$?"

say "升级场景"

# 1. 正常升级：dry-run 与正式执行都返回 0
"$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --dry-run >/dev/null 2>&1
check "upgrade --dry-run 返回 0" "0" "$?"
"$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --skip-smoke >/dev/null 2>&1
check "upgrade 返回 0" "0" "$?"

# 2. knowledge/ 永不被升级触碰
printf '# 业务事实\n' > "$INST/knowledge/business/custom.md"
before="$(shasum "$INST/knowledge/business/custom.md" | awk '{print $1}')"
"$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --skip-smoke >/dev/null 2>&1
after="$(shasum "$INST/knowledge/business/custom.md" | awk '{print $1}')"
check "升级不动 knowledge/" "$before" "$after"

# 无关脏文件不能被升级提交带上
printf '不相关\n' > "$INST/knowledge/business/unrelated.md"
"$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --skip-smoke >/dev/null 2>&1
if (cd "$INST" && git status --porcelain -- knowledge/business/unrelated.md | grep -q .); then
  ok "升级提交不含无关脏文件"
else
  bad "升级提交带上了无关脏文件"
fi

# 3. 机制文件被本地改过：拒绝并提示，--force-mechanism 覆盖
printf '\n# local tweak\n' >> "$INST/scripts/opc-up.sh"
out="$("$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --skip-smoke 2>&1)"
rc=$?
if [[ "$rc" != "0" ]] && grep -q "本地改过" <<< "$out"; then
  ok "本地改过的机制文件被拒绝"
else
  bad "本地改过的机制文件没有被拒绝（rc=${rc}）"
fi
if grep -q "local tweak" <<< "$out"; then
  ok "拒绝时打印了 diff"
else
  bad "拒绝时没有打印 diff"
fi
"$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --skip-smoke --force-mechanism >/dev/null 2>&1
check "--force-mechanism 覆盖成功" "0" "$?"
if grep -q "local tweak" "$INST/scripts/opc-up.sh"; then
  bad "机制文件没有被模版版本覆盖"
else
  ok "机制文件恢复成模版版本"
fi

# 4. 起始材料的分层：机制指纹不覆盖它，基线单独记
check_starter "$INST" "机制指纹不覆盖起始材料" mech-clean
check_starter "$INST" "基线记了根规约、角色文件与种子" base-has AGENTS.md agents/gm/AGENTS.md README.md

# 5. owner 改过的起始材料：保留并告警
printf '\n# owner 的补充\n' >> "$INST/AGENTS.md"
out="$("$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --skip-smoke 2>&1)"
rc=$?
check "改过的起始材料不阻断升级" "0" "$rc"
expect "改过的起始材料有告警" grep -q "已本地修改" <<< "$out"
expect "改过的起始材料被保留" grep -q "owner 的补充" "$INST/AGENTS.md"
(cd "$INST" && git checkout -- AGENTS.md)

# 6. owner 删掉的起始材料不再复活
rm -f "$INST/README.md"
"$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --skip-smoke >/dev/null 2>&1
check "删掉起始材料后升级仍成功" "0" "$?"
expect "删掉的起始材料不被补回" test ! -e "$INST/README.md"

# 6b. 业务种子：owner 删过就跳过，不补回，也不算错误
rm -f "$INST/knowledge/business/品牌口径.md"
"$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --skip-smoke >/dev/null 2>&1
check "删掉业务种子后升级仍成功" "0" "$?"
expect "删掉的业务种子不被补回" test ! -e "$INST/knowledge/business/品牌口径.md"

# 7. owner 自己加的文件永不被触碰
mkdir -p "$INST/agents/owner"
printf '# owner 自己加的\n' > "$INST/agents/owner/AGENTS.md"
"$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --skip-smoke >/dev/null 2>&1
expect "owner 新增的文件还在" test -f "$INST/agents/owner/AGENTS.md"
check "owner 新增的文件内容不变" "# owner 自己加的" "$(cat "$INST/agents/owner/AGENTS.md")"

# 8. 模版新增的起始材料补入
TPL2="$WORK/tpl2"
mkdir -p "$TPL2"
cp -R "$ROOT/template" "$TPL2/template"
mkdir -p "$TPL2/template/agents/new"
printf '# 新角色简报\n' > "$TPL2/template/agents/new/AGENTS.md"
"$ROOT/bin/opc" upgrade "$INST" --template "$TPL2" --skip-smoke >/dev/null 2>&1
check "带新起始材料的模版升级成功" "0" "$?"
expect "模版新增的起始材料被补入" test -f "$INST/agents/new/AGENTS.md"

# 9. 模版移除的起始材料只提示，不从实例删
out="$("$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --skip-smoke 2>&1)"
expect "模版移除的起始材料被提示" grep -q "模版已移除" <<< "$out"
expect "模版移除的起始材料没有从实例删除" test -f "$INST/agents/new/AGENTS.md"

# 10. 缺失根规约视为错误
mv "$INST/AGENTS.md" "$WORK/AGENTS.md.bak"
out="$("$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --skip-smoke 2>&1)"
rc=$?
if [[ "$rc" != "0" ]] && grep -q "起始材料缺失" <<< "$out"; then
  ok "缺失根规约时升级失败"
else
  bad "缺失根规约时升级没有失败（rc=${rc}）"
fi
mv "$WORK/AGENTS.md.bak" "$INST/AGENTS.md"

# 11. 启用角色缺入口文件视为错误
mv "$INST/agents/gm/AGENTS.md" "$WORK/gm.md.bak"
out="$("$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --skip-smoke 2>&1)"
rc=$?
if [[ "$rc" != "0" ]] && grep -q "agents/gm/AGENTS.md" <<< "$out"; then
  ok "启用角色缺入口文件时升级失败"
else
  bad "启用角色缺入口文件时升级没有失败（rc=${rc}）"
fi
mv "$WORK/gm.md.bak" "$INST/agents/gm/AGENTS.md"

# 12. 停用角色缺入口文件不阻断升级，也不补回
python3 - "$INST/roles.json" <<'PY'
import json
import sys

path = sys.argv[1]
data = json.load(open(path))
for role in data["roles"]:
    if role["name"] == "dev":
        role["enabled"] = False
with open(path, "w") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2)
PY
rm -f "$INST/agents/dev/AGENTS.md"
"$ROOT/bin/opc" upgrade "$INST" --template "$ROOT" --skip-smoke >/dev/null 2>&1
check "停用角色缺入口文件不阻断升级" "0" "$?"
expect "停用角色的入口文件不被补回" test ! -e "$INST/agents/dev/AGENTS.md"

# 13. 技能目录整体冻结：目录里任一文件被改，整个技能跳过更新
TPL3="$WORK/tpl3"
TPL4="$WORK/tpl4"
mkdir -p "$TPL3" "$TPL4"
cp -R "$ROOT/template" "$TPL3/template"
cp -R "$ROOT/template" "$TPL4/template"
mkdir -p "$TPL3/template/skills/demo" "$TPL4/template/skills/demo"
printf 'v1\n' > "$TPL3/template/skills/demo/SKILL.md"
printf 'v2\n' > "$TPL4/template/skills/demo/SKILL.md"
INST2="$WORK/inst2"
"$ROOT/bin/opc" install "$INST2" t2 --template "$TPL3" --no-input --skip-smoke >/dev/null 2>&1
check "带技能的模版安装成功" "0" "$?"
expect "技能装进了实例" test -f "$INST2/skills/demo/SKILL.md"
check_starter "$INST2" "基线记了技能文件" base-has skills/demo/SKILL.md
printf 'owner 改的\n' > "$INST2/skills/demo/SKILL.md"
out="$("$ROOT/bin/opc" upgrade "$INST2" --template "$TPL4" --skip-smoke 2>&1)"
rc=$?
check "技能冻结不阻断升级" "0" "$rc"
expect "技能冻结有提示" grep -q "技能冻结" <<< "$out"
check "整个技能目录保持不变" "owner 改的" "$(cat "$INST2/skills/demo/SKILL.md")"

# 14. 技能目录里出现 owner 新增的文件，同样冻结
INST3="$WORK/inst3"
"$ROOT/bin/opc" install "$INST3" t3 --template "$TPL3" --no-input --skip-smoke >/dev/null 2>&1
printf '# owner 加的\n' > "$INST3/skills/demo/owner.md"
out="$("$ROOT/bin/opc" upgrade "$INST3" --template "$TPL4" --skip-smoke 2>&1)"
expect "owner 在技能目录里加文件也会冻结" grep -q "技能冻结" <<< "$out"
check "技能目录保持原样" "v1" "$(cat "$INST3/skills/demo/SKILL.md")"

# 15. 老实例：没有起始材料基线，机制指纹就是基线
INST4="$WORK/inst4"
"$ROOT/bin/opc" install "$INST4" t4 --template "$ROOT" --no-input --skip-smoke >/dev/null 2>&1
check "老实例准备就绪" "0" "$?"
python3 - "$INST4" "$ROOT" <<'PY'
import hashlib
import json
import pathlib
import sys

inst, root = sys.argv[1], sys.argv[2]


def sha(path):
    data = pathlib.Path(path).read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


# 老实例把起始材料当机制记了指纹：回退成那个样子
mech_path = pathlib.Path(inst) / ".opc" / "mechanism.json"
mech = json.loads(mech_path.read_text(encoding="utf-8"))
for rel in ("AGENTS.md", "agents/gm/AGENTS.md"):
    mech["files"][rel] = sha(pathlib.Path(root) / "template" / rel)
mech_path.write_text(json.dumps(mech, ensure_ascii=False, indent=2), encoding="utf-8")
(pathlib.Path(inst) / ".opc" / "starters.json").unlink()
PY
printf '\n# 老实例里 owner 改的\n' >> "$INST4/AGENTS.md"
out="$("$ROOT/bin/opc" upgrade "$INST4" --template "$ROOT" --skip-smoke 2>&1)"
rc=$?
check "老实例升级不被机制指纹拦住" "0" "$rc"
expect "老实例改过的起始材料有告警" grep -q "已本地修改" <<< "$out"
expect "老实例改过的起始材料被保留" grep -q "老实例里 owner 改的" "$INST4/AGENTS.md"
expect "老实例的角色文件还在" test -f "$INST4/agents/gm/AGENTS.md"
expect "老实例升级后有了起始材料基线" test -f "$INST4/.opc/starters.json"

# 16. 实例里删掉的技能不再复活
INST5="$WORK/inst5"
"$ROOT/bin/opc" install "$INST5" t5 --template "$ROOT" --no-input --skip-smoke >/dev/null 2>&1
check "带技能库的实例准备就绪" "0" "$?"
rm -rf "$INST5/skills/instance-ops"
"$ROOT/bin/opc" upgrade "$INST5" --template "$ROOT" --skip-smoke >/dev/null 2>&1
check "删掉技能后升级仍成功" "0" "$?"
expect "删掉的技能不被补回" test ! -e "$INST5/skills/instance-ops/SKILL.md"
expect "没删的技能还在" test -f "$INST5/skills/knowledge-writing/SKILL.md"

# 17. 改过技能里的任一文件，整个技能冻结；没改的技能照常更新
TPL5="$WORK/tpl5"
mkdir -p "$TPL5"
cp -R "$ROOT/template" "$TPL5/template"
printf '\n模版侧的新版本。\n' >> "$TPL5/template/skills/opc-workflow/SKILL.md"
printf '\n模版侧的新版本。\n' >> "$TPL5/template/skills/knowledge-writing/SKILL.md"
INST6="$WORK/inst6"
"$ROOT/bin/opc" install "$INST6" t6 --template "$ROOT" --no-input --skip-smoke >/dev/null 2>&1
printf '\nowner 改的。\n' >> "$INST6/skills/opc-workflow/SKILL.md"
out="$("$ROOT/bin/opc" upgrade "$INST6" --template "$TPL5" --skip-smoke 2>&1)"
rc=$?
check "技能冻结不阻断升级" "0" "$rc"
expect "技能冻结有提示" grep -q "技能冻结" <<< "$out"
expect "被冻结的技能保持 owner 的版本" grep -q "owner 改的" "$INST6/skills/opc-workflow/SKILL.md"
expect "被冻结的技能不更新到模版版本" \
  bash -c "! grep -q '模版侧的新版本' '$INST6/skills/opc-workflow/SKILL.md'"
expect "没被改的技能照常更新" \
  grep -q "模版侧的新版本" "$INST6/skills/knowledge-writing/SKILL.md"

# 18. 起始材料是指向实例外的软链接：升级不顺着它写到实例外
INST7="$WORK/inst7"
"$ROOT/bin/opc" install "$INST7" t7 --template "$ROOT" --no-input --skip-smoke >/dev/null 2>&1
printf 'owner 的内容\n' > "$WORK/outside.md"
rm -f "$INST7/skills/knowledge-writing/SKILL.md"
ln -s "$WORK/outside.md" "$INST7/skills/knowledge-writing/SKILL.md"
printf 'owner 的规约\n' > "$WORK/outside-agents.md"
rm -f "$INST7/AGENTS.md"
ln -s "$WORK/outside-agents.md" "$INST7/AGENTS.md"
out="$("$ROOT/bin/opc" upgrade "$INST7" --template "$TPL5" --skip-smoke 2>&1)"
rc=$?
check "起始材料软链接指向实例外时升级仍成功" "0" "$rc"
check "实例外的文件没有被改写" "owner 的内容" "$(cat "$WORK/outside.md")"
check "实例外的规约文件没有被改写" "owner 的规约" "$(cat "$WORK/outside-agents.md")"
expect "指向实例外的软链接有告警" grep -q "指向实例外" <<< "$out"

# 19. 注册表记录实例
expect "注册表包含实例" grep -q "$INST" "$OPC_CONFIG_DIR/instances.json"
check "opc ls 列出实例" "1" "$("$ROOT/bin/opc" ls 2>/dev/null | grep -c "^t  ")"

say ""
say "汇总：通过 ${PASS} 项 / 失败 ${FAIL} 项"
[[ "$FAIL" -eq 0 ]]
