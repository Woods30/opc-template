"""旧角色单文件迁移：`agents/opc-<角色>.md` → `agents/<角色>/AGENTS.md`。

角色目录化之前，角色简报是 `agents/` 下的单文件，职责描述写在文件自己的
frontmatter 里。角色目录化之后入口是 `agents/<角色>/AGENTS.md`（纯 Markdown），
描述搬进 `roles.json`。

迁移只搬 owner 的东西：正文原样保留（含 `{{PREFIX}}` 占位），frontmatter 的
description 写进 `roles.json`，旧文件连同原始 frontmatter 备份到
`.opc/backups/`。技能留空——迁移不该悄悄改变角色的行为。

旧实例把 `agents/` 当机制目录，所以 `.opc/mechanism.json` 里留着那些文件的
指纹。拿它当基线：指纹对得上说明 owner 没改过，迁出来的文件按普通起始材料
跟随模版更新；对不上说明 owner 改过，记成 pinned，之后升级不再覆盖它。
"""

import os
import re
import shutil
import tempfile
from pathlib import Path

from . import install as install_mod
from .errors import OpcError
from .hashutil import sha256_bytes, sha256_file

# 旧布局：agents/ 下的单文件角色简报。
OLD_TEMPLATE_RE = re.compile(r"^agents/[^/]+\.md$")

# 角色名要能当目录名用：只允许普通标识符，挡住路径穿越。
ROLE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# frontmatter 的字段行：key: value。纯 Markdown 正文里也可能出现分隔线，
# 只有整段都像字段才当 frontmatter。
FM_KEY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*:")

BACKUP_ROOT = ".opc/backups"

KIND_ROLE = "role"


def _inside(instance, path):
    """路径（含软链接落点）是否仍在实例内。"""
    try:
        resolved = Path(path).resolve()
        base = Path(instance).resolve()
    except OSError:
        return False
    return resolved == base or base in resolved.parents


def _symlink_component(instance, path):
    """路径的任一层（含自己）是不是软链接。

    只看最后一段不够：父目录是软链接时，写进去的文件照样落在实例外。
    """
    root = Path(instance)
    try:
        rel = Path(path).relative_to(root)
    except ValueError:
        return True
    cur = root
    for part in rel.parts:
        cur = cur / part
        try:
            if cur.is_symlink():
                return True
        except OSError:
            return True
    return False


def split_frontmatter(text):
    """拆出 frontmatter 与正文。

    只有「开头是 ---、中间全是 key: value 或空行、后面有配对的 ---」才算
    frontmatter。误判会把正文吃掉，所以判不出来就当没有 frontmatter。
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = None
    for index in range(1, len(lines)):
        line = lines[index].strip()
        if line == "---":
            end = index
            break
        if not line or FM_KEY_RE.match(line):
            continue
        return {}, text
    if end is None:
        return {}, text
    meta = {}
    for line in lines[1:end]:
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key in meta:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        meta[key] = value
    return meta, "".join(lines[end + 1:])


def detect(roles):
    """旧布局的角色条目：template 指向 `agents/` 下的单文件。"""
    result = []
    for role in roles or []:
        template = role.get("template") or ""
        if OLD_TEMPLATE_RE.match(template):
            result.append(role)
    return result


def fallback_description(name):
    """没有描述时的占位：从角色名生成。"""
    return "OPC 角色 {}".format(name)


def plan(instance, roles, fingerprint=None):
    """规划角色迁移。只读，不写盘。

    `fingerprint` 是旧实例的机制指纹（rel → sha256），用来判断旧简报被
    owner 改过没有：改过的迁出来之后就不再跟随模版更新。
    """
    instance = Path(instance)
    fingerprint = fingerprint or {}
    items = []
    for role in detect(roles):
        name = role.get("name") or ""
        old_rel = role.get("template") or ""
        if not ROLE_NAME_RE.match(name) or ".." in name:
            # 角色名要当目录名用：名字不干净就别碰它。
            continue
        item = {
            "role": name,
            "old": old_rel,
            "target": "agents/{}/AGENTS.md".format(name),
            "backup": "{}/{}".format(BACKUP_ROOT, old_rel),
            "write": False,
            "modified": False,
            "skipped": False,
            "description": role.get("description") or "",
            "warnings": [],
        }
        target_path = instance / item["target"]
        if not _inside(instance, target_path.parent):
            # 角色目录指向实例外：不写过去，也不改这个角色条目。
            item["skipped"] = True
            item["warnings"].append("角色目录指向实例外，跳过 {}".format(name))
            items.append(item)
            continue
        old_path = instance / old_rel
        have_body = False
        if not old_path.is_file():
            item["warnings"].append("旧角色文件 {} 不存在，只改元数据".format(old_rel))
        elif old_path.is_symlink() or not _inside(instance, old_path):
            # 旧简报是软链接或指向实例外：读它等于把实例外的文件抄进角色
            # 提示词，所以不读，只改元数据。
            item["warnings"].append(
                "旧角色文件 {} 指向实例外，不读取内容".format(old_rel))
        else:
            text = old_path.read_text(encoding="utf-8", errors="replace")
            meta, body = split_frontmatter(text)
            item["body"] = body.lstrip("\n")
            have_body = True
            description = meta.get("description") or ""
            if description:
                item["description"] = description
            recorded = fingerprint.get(old_rel)
            if recorded is None:
                item["modified"] = True
                item["warnings"].append(
                    "旧指纹里没有 {} 的记录，按 owner 改过处理".format(old_rel))
            elif recorded != sha256_file(old_path):
                item["modified"] = True
        if not item["description"]:
            item["description"] = fallback_description(name)
            item["warnings"].append("旧简报没有 description，用占位描述代替")
        if target_path.is_symlink():
            # 目标是软链接：不顺着它写。
            item["record"] = None
        elif target_path.exists():
            # 已经有角色目录了：不覆盖，只把它认成 owner 的内容。
            item["write"] = False
            item["record"] = {
                "sha256": sha256_file(target_path), "kind": KIND_ROLE, "pinned": True}
        elif have_body:
            item["write"] = True
            record = {"sha256": sha256_bytes(item["body"].encode("utf-8")),
                      "kind": KIND_ROLE}
            if item["modified"]:
                record["pinned"] = True
            item["record"] = record
        else:
            item["record"] = None
        items.append(item)
    return {"roles": items}


def effective_roles(roles, result):
    """迁移之后的角色条目：模板路径改了，描述与技能也按迁移结果算。"""
    by_name = {item["role"]: item for item in result["roles"] if not item.get("skipped")}
    effective = []
    for role in roles or []:
        item = by_name.get(role.get("name"))
        if not item:
            effective.append(role)
            continue
        patched = dict(role)
        patched["template"] = item["target"]
        patched["description"] = item["description"]
        patched["skills"] = []
        effective.append(patched)
    return effective


def written_targets(result):
    """迁移当次会写出来的角色入口路径。"""
    return [item["target"] for item in result["roles"] if item["write"]]


def records(result):
    """迁移写出的文件对应的起始材料基线条目。"""
    out = {}
    for item in result["roles"]:
        if item.get("record"):
            out[item["target"]] = dict(item["record"])
    return out


def detach(starter_result, result):
    """把迁移要写的文件从起始材料计划里摘出来。

    迁移当次由迁移自己写这些文件：起始材料引擎不要拿模版版本盖掉刚迁出来的
    正文。基线里记迁移的结果，下次升级再按普通起始材料更新。
    """
    files = starter_result.setdefault("baseline", {}).setdefault("files", {})
    for rel, record in records(result).items():
        if not any(item["target"] == rel and item["write"] for item in result["roles"]):
            continue
        starter_result["copy"] = [row for row in starter_result.get("copy") or []
                                  if row[2] != rel]
        starter_result["added"] = [x for x in starter_result.get("added") or []
                                   if x != rel]
        starter_result["updated"] = [x for x in starter_result.get("updated") or []
                                     if x != rel]
        files[rel] = record
    return starter_result


def lines(result):
    """迁移动作的可读摘要（dry-run 与执行后共用）。"""
    out = []
    items = [item for item in (result.get("roles") or []) if not item.get("skipped")]
    skipped = [item for item in (result.get("roles") or []) if item.get("skipped")]
    if items:
        out.append("  角色迁移（单文件 → 角色目录）：")
    for item in items:
        out.append("    - {}：创建 {}（正文来自 {}）".format(
            item["role"], item["target"], item["old"]))
        out.append("    - {}：roles.json 写入 description、template 指向 {}、skills 置空".format(
            item["role"], item["target"]))
        out.append("    - {}：旧简报备份到 {}".format(item["role"], item["backup"]))
        out.append("    - {}：旧简报 {} 已移除".format(item["role"], item["old"]))
    for item in items:
        if item["modified"]:
            out.append("    警告：{} 的旧简报被 owner 改过，迁移后不再跟随模版更新".format(
                item["role"]))
    for item in items + skipped:
        for warning in item["warnings"]:
            out.append("    警告：{}：{}".format(item["role"], warning))
    return out


def paths(result):
    """迁移动过的实例内路径（新文件 + 旧文件），供提交限定 pathspec。"""
    out = []
    for item in result.get("roles") or []:
        if item.get("skipped"):
            continue
        if item["write"]:
            out.append(item["target"])
        out.append(item["old"])
    return out


def _copy_file(src, dst):
    """复制文件：先写临时文件再 replace，replace 不会顺着软链接写。"""
    dst = Path(dst)
    fd, tmp_name = tempfile.mkstemp(dir=str(dst.parent), prefix=".opc-tmp-")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        shutil.copy2(str(src), str(tmp))
        os.replace(str(tmp), str(dst))
    finally:
        if tmp.exists():
            tmp.unlink()


def apply(instance, result):
    """执行迁移：写角色目录、改 roles.json、备份并移除旧简报。

    幂等：已经存在的角色文件不覆盖，旧简报备份过一次就不再重备。
    """
    instance = Path(instance)
    for item in result.get("roles") or []:
        if item.get("skipped"):
            continue
        old_path = instance / item["old"]
        if item["write"]:
            target = instance / item["target"]
            if not target.exists() and not _symlink_component(instance, target):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(item["body"], encoding="utf-8")
        if old_path.is_file() and not old_path.is_symlink() and _inside(instance, old_path):
            backup = instance / item["backup"]
            if not backup.exists() and not _symlink_component(instance, backup):
                backup.parent.mkdir(parents=True, exist_ok=True)
                _copy_file(old_path, backup)
            old_path.unlink()
    _apply_roles(instance, result)
    return result


def _apply_roles(instance, result):
    """把迁移结果写进 roles.json：描述、模板路径与技能选择。"""
    path = Path(instance) / "roles.json"
    if not path.is_file():
        return
    data = install_mod.load_json(path, None)
    if not isinstance(data, dict):
        raise OpcError("roles.json 不是合法 JSON：{}".format(path))
    by_name = {item["role"]: item for item in (result.get("roles") or [])
               if not item.get("skipped")}
    changed = False
    for role in data.get("roles") or []:
        item = by_name.get(role.get("name"))
        if not item:
            continue
        role["description"] = item["description"]
        role["template"] = item["target"]
        # 迁移不套模版的默认技能：升级不该悄悄改变角色的行为。
        role["skills"] = []
        changed = True
    if changed:
        install_mod.write_json(path, data)
