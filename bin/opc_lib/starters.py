"""起始材料引擎：机制之外、owner 可改的材料，按基线比对更新。

机制（`scripts/`、`tools/`、`LICENSE`）由指纹管理，本地改过就拒绝升级。
起始材料（根 `AGENTS.md`、`agents/`、`skills/` 与业务 seeds）装一次就归 owner：
升级只更新没被改过的文件，改过的保留并告警，删掉的不复活，模版新增的补入。

基线写在实例的 `.opc/starters.json`：每份起始材料记实例里的相对路径与
SHA-256；技能目录额外记该技能包含的文件集合，用于整目录冻结判断。

两类材料的更新口径不同：

- 角色与技能材料（`AGENTS.md`、`agents/`、`skills/`）：与基线一致就用模版
  版本刷新，owner 改过的保留并告警。
- 业务 seeds：只补不覆盖。实例里已经有就留着（业务事实归 owner），
  owner 删掉的不再补；模版新增的 seed 只在目标缺失时补入。
"""

import json
import os
from pathlib import Path

from . import manifest as manifest_mod
from . import safefile
from .errors import OpcError
from .hashutil import sha256_file

KIND_FILE = "file"
KIND_ROLE = "role"
KIND_SKILL = "skill"
KIND_SEED = "seed"

# 种子只补不覆盖：实例里的内容归 owner，模版改不动。
ADD_ONLY_KINDS = {KIND_SEED}

BASELINE_VERSION = 1


# ---------------------------------------------------------------- 基线读写


def baseline_path(instance):
    return Path(instance) / ".opc" / "starters.json"


def _read_json(path, default):
    path = Path(path)
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OpcError("不是合法 JSON：{}（{}）".format(path, exc))


def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def read_baseline(instance):
    """读实例的起始材料基线；没有就返回空基线。"""
    raw = _read_json(baseline_path(instance), None) or {}
    files = raw.get("files")
    files = dict(files) if isinstance(files, dict) else {}
    skills = raw.get("skills")
    if not isinstance(skills, dict):
        skills = {}
    return {
        "version": raw.get("version", BASELINE_VERSION),
        "files": files,
        "skills": {k: list(v) for k, v in skills.items() if isinstance(v, list)},
    }


def write_baseline(instance, baseline):
    """写基线：每份材料记路径、SHA-256 与类型；技能额外记它包含的文件。"""
    files = baseline.get("files") or {}
    skills = {}
    for rel, record in files.items():
        unit = (record or {}).get("unit")
        if not unit:
            continue
        skills.setdefault(unit, []).append(rel)
    data = {
        "version": BASELINE_VERSION,
        "files": files,
        "skills": {unit: sorted(rels) for unit, rels in skills.items()},
    }
    _write_json(baseline_path(instance), data)
    return data


# ---------------------------------------------------------------- 模版侧清单


def _entry(target, source, kind, unit=None, required=False):
    return {
        "target": target,
        "source": source,
        "kind": kind,
        "unit": unit,
        "required": required,
    }


def expand(payload, manifest):
    """模版侧的起始材料清单。

    每条含：实例里的目标路径、模版里的来源路径、材料类型、所属单元、
    是否必需。`skills/` 下的每个子目录是一个技能单元。
    """
    payload = Path(payload)
    entries = []
    starters = manifest.get("starters") or {}
    for spec in starters.get("files", []):
        entries.append(_entry(
            spec.get("target") or spec["source"], spec["source"], KIND_FILE,
            required=bool(spec.get("required"))))
    for spec in starters.get("dirs", []):
        source = spec["source"]
        target_root = spec.get("target") or source
        kind = KIND_SKILL if spec.get("type") == "skill" else KIND_ROLE
        src_dir = payload / source
        if not src_dir.is_dir():
            # 声明了但模版里还没有（如 `skills/`）：先不起作用，不算错。
            continue
        for path in sorted(src_dir.rglob("*")):
            if not path.is_file() or manifest_mod.should_ignore(path):
                continue
            rel = path.relative_to(src_dir).as_posix()
            unit = None
            if kind == KIND_SKILL:
                # 技能以目录为单元：目录里的文件一起冻结、一起更新。
                unit = "{}/{}".format(target_root, rel.split("/")[0] if "/" in rel else rel)
            entries.append(_entry(
                "{}/{}".format(target_root, rel),
                "{}/{}".format(source, rel),
                kind, unit=unit))
    for spec in manifest.get("seeds", []):
        entries.append(_entry(spec["target"], spec["source"], KIND_SEED))
    for entry in entries:
        _check_entry(entry)
        if not _inside(payload, payload / entry["source"]):
            raise OpcError("起始材料来源不在模版载荷内：{}".format(entry["source"]))
    return entries


def _record(files, entry, digest):
    record = {"sha256": digest, "kind": entry["kind"]}
    if entry.get("unit"):
        record["unit"] = entry["unit"]
    files[entry["target"]] = record


# ---------------------------------------------------------------- 安装


def install(payload, manifest, instance, entries=None):
    """把起始材料装到实例里（缺失才复制），并建立基线。

    已存在的文件不覆盖：owner 的东西装进去时就不该被模版改写。
    """
    payload = Path(payload)
    instance = Path(instance)
    if entries is None:
        entries = expand(payload, manifest)
    files = {}
    added = []
    for entry in entries:
        src = payload / entry["source"]
        dst = instance / entry["target"]
        if not src.is_file():
            continue
        if dst.is_symlink():
            # 目标是软链接：不顺着它写，否则会改到别处的文件。
            # 校验与拷贝之间仍有竞态；能往实例目录里写符号链接的人本来就能
            # 改这个实例，这里防的是「实例里已有的链接把改动带到实例外」。
            continue
        if _symlink_component(instance, dst) or not _resolves_inside(instance, dst):
            # 父目录是软链接或落点在实例外：一律不写。
            continue
        if not dst.exists():
            safefile.copy_from(payload, entry["source"], instance,
                               entry["target"])
            added.append(entry["target"])
        _record(files, entry, sha256_file(src))
    return {"version": BASELINE_VERSION, "files": files}, added


def adopt_mechanism_baseline(baseline, old_files, entries):
    """机制指纹转成起始材料基线。

    旧实例把 `AGENTS.md`、`agents/` 当机制文件记指纹。改成起始材料后，
    那份指纹正好是「装进来时的模版版本」，拿来当基线才能分清
    「owner 改过」与「只是模版更新了」。
    """
    files = baseline.setdefault("files", {})
    known = {entry["target"]: entry for entry in entries}
    for rel, digest in sorted((old_files or {}).items()):
        if rel in files:
            continue
        entry = known.get(rel)
        if not entry or entry["kind"] in ADD_ONLY_KINDS:
            continue
        _record(files, entry, digest)
    return baseline


# ---------------------------------------------------------------- 升级


def _frozen_units(instance, entries, files):
    """被冻结的技能单元。

    技能以目录为单位：任一已记录文件被改、或目录里出现 owner 新增的文件，
    整个技能都跳过更新——免得 `SKILL.md` 与脚本出现半新半旧的版本。
    """
    by_unit = {}
    for entry in entries:
        if entry["kind"] == KIND_SKILL and entry.get("unit"):
            by_unit.setdefault(entry["unit"], []).append(entry)
    frozen = set()
    for unit, unit_entries in by_unit.items():
        template_targets = {e["target"] for e in unit_entries}
        changed = False
        for target, record in files.items():
            if record.get("unit") != unit:
                continue
            path = Path(instance) / target
            if not path.is_file() or sha256_file(path) != record["sha256"]:
                changed = True
                break
        if not changed:
            unit_dir = Path(instance) / unit
            if unit_dir.is_dir():
                for path in sorted(unit_dir.rglob("*")):
                    if not path.is_file():
                        continue
                    rel = path.relative_to(Path(instance)).as_posix()
                    if rel in template_targets or rel in files:
                        continue
                    changed = True
                    break
        if changed:
            frozen.add(unit)
    return frozen


def plan(payload, manifest, instance, baseline, entries=None):
    """比对基线与实例现状，产出待执行的动作。不写盘。"""
    payload = Path(payload)
    instance = Path(instance)
    if entries is None:
        entries = expand(payload, manifest)
    files = dict((baseline.get("files") or {}))
    frozen = _frozen_units(instance, entries, files)

    result = {
        "copy": [],
        "added": [],
        "updated": [],
        "kept": [],
        "skipped": [],
        "retired": [],
        "frozen": sorted(frozen),
        "missing": [],
        "instance": str(instance),
        "payload": str(payload),
    }
    new_files = {}

    for entry in entries:
        rel = entry["target"]
        src = payload / entry["source"]
        dst = instance / rel
        record = files.get(rel)
        if not src.is_file():
            continue

        if entry["kind"] == KIND_SKILL and entry.get("unit") in frozen:
            # 整个技能冻结：一个文件都不动。
            if record:
                new_files[rel] = dict(record)
            continue

        if not _resolves_inside(instance, dst):
            # 目标（连同它的父目录）指向实例外：不写过去，保留并告警。
            result["kept"].append((rel, "指向实例外的软链接，已保留"))
            if record:
                new_files[rel] = dict(record)
            continue

        if dst.is_symlink():
            # 目标是软链接：不顺着它写，避免改到实例里别的文件。
            result["kept"].append((rel, "目标是软链接，已保留"))
            if record:
                new_files[rel] = dict(record)
            continue

        if _symlink_component(instance, dst):
            # 父目录是软链接：落点可能落在实例外，同样不写。
            result["kept"].append((rel, "父目录是软链接，已保留"))
            if record:
                new_files[rel] = dict(record)
            continue

        if entry["kind"] in ADD_ONLY_KINDS:
            # 种子只补不覆盖：实例里有就留着，owner 删掉的不再补。
            if dst.exists():
                new_files[rel] = dict(record) if record else {
                    "sha256": sha256_file(dst), "kind": entry["kind"]}
            elif record:
                result["skipped"].append(rel)
                new_files[rel] = dict(record)
            else:
                result["copy"].append((entry["source"], dst, rel))
                result["added"].append(rel)
                _record(new_files, entry, sha256_file(src))
            continue

        if not dst.exists():
            if record:
                if entry["required"]:
                    result["missing"].append(rel)
                else:
                    result["skipped"].append(rel)
                    new_files[rel] = dict(record)
            else:
                result["copy"].append((entry["source"], dst, rel))
                result["added"].append(rel)
                _record(new_files, entry, sha256_file(src))
            continue

        current = sha256_file(dst)
        if record is None:
            if current == sha256_file(src):
                # 与模版一致：收编进基线，之后就能正常跟随模版更新。
                _record(new_files, entry, current)
            else:
                result["kept"].append((rel, "与模版不同，已保留"))
                _record(new_files, entry, sha256_file(src))
                new_files[rel]["pinned"] = True
            continue
        if record.get("pinned"):
            # owner 自己放的文件：认下来，之后也不再动它。
            new_files[rel] = dict(record)
            continue
        if current != record["sha256"]:
            result["kept"].append((rel, "已本地修改，已保留"))
            new_files[rel] = dict(record)
            continue
        # 与基线一致：可以用模版版本刷新。
        if sha256_file(src) != record["sha256"]:
            result["copy"].append((entry["source"], dst, rel))
            result["updated"].append(rel)
            _record(new_files, entry, sha256_file(src))
        else:
            new_files[rel] = dict(record)

    template_targets = {e["target"] for e in entries}
    for rel, record in sorted(files.items()):
        if rel in template_targets:
            continue
        # 模版不再提供：只提示，实例里的文件不删。
        result["retired"].append(rel)
        retired = dict(record)
        retired["retired"] = True
        new_files[rel] = retired

    result["baseline"] = {"version": BASELINE_VERSION, "files": new_files}
    return result


def _safe_rel(rel):
    """相对路径安全性：拒绝绝对路径与 `..`。"""
    if not rel or not isinstance(rel, str):
        return False
    if rel.startswith("/") or os.path.isabs(rel):
        return False
    return ".." not in Path(rel).parts


def _inside(root, path):
    """路径（含软链接落点）是否仍在 root 之下。"""
    try:
        resolved = Path(path).resolve()
        base = Path(root).resolve()
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


def _check_entry(entry):
    """起始材料条目的路径合法性：相对、无 `..`、来源在载荷内。"""
    for key in ("source", "target"):
        if not _safe_rel(entry.get(key)):
            raise OpcError("起始材料路径不合法：{} = {}".format(key, entry.get(key)))


def _resolves_inside(instance, path):
    """软链接的落点是否仍在实例内。

    实例里的文件可能是指向实例外的软链接。顺着它写会把 owner 目录外的东西
    改掉——那既越界，也会把实例的改动写到别处去。
    """
    try:
        resolved = Path(path).resolve()
        root = Path(instance).resolve()
    except OSError:
        return False
    return resolved == root or root in resolved.parents


def instance_roles(instance):
    """实例里的角色清单（roles.json）；读不到就当没有角色。"""
    path = Path(instance) / "roles.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data.get("roles") or []


def missing_required_files(instance, entries, planned=()):
    """缺失的必需起始材料（清单里标了 required 的，比如根 `AGENTS.md`）。"""
    planned = set(planned)
    missing = []
    for entry in entries:
        if not entry.get("required"):
            continue
        rel = entry["target"]
        if (Path(instance) / rel).exists() or rel in planned:
            continue
        missing.append(rel)
    return missing


def missing_role_entries(instance, roles, planned=()):
    """启用角色缺入口文件时返回它们的路径。"""
    planned = set(planned)
    missing = []
    for role in roles or []:
        if not role.get("enabled"):
            continue
        template = role.get("template")
        if not template:
            continue
        if not _safe_rel(template):
            missing.append("角色 {}：模板路径不合法 {}".format(role.get("name"), template))
            continue
        if (Path(instance) / template).exists() or template in planned:
            continue
        missing.append("角色 {}：{}".format(role.get("name"), template))
    return missing


def apply(result):
    """执行计划里的拷贝。"""
    instance = result.get("instance")
    for src, dst, rel in result.get("copy") or []:
        dst = Path(dst)
        if dst.is_symlink():
            # 目标是软链接：replace 会替换链接本身，但这里直接跳过更清楚。
            continue
        if instance and (_symlink_component(instance, dst)
                         or not _resolves_inside(instance, dst)):
            continue
        safefile.copy_from(result.get("payload"), src, instance, rel)
    return result
