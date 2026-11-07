"""upgrade：机制指纹校验 + 起始材料按基线更新；本地改过机制文件则拒绝。"""

import difflib
import shutil
import sys
from pathlib import Path

from . import install as install_mod
from . import gitutil, manifest as manifest_mod, registry, role_migrate, safefile, starters, ui
from .errors import OpcError
from .hashutil import sha256_file

LEGACY_MARKERS = [
    "layouts",
    "mods",
    "seeds",
    "tools/tests",
    "sync-policy.json",
    "template.lock.json",
    ".opc/sync-base",
    ".opc/sync-state.json",
    ".opc/policy.json",
    ".opc/sync-stage",
    ".opc/sync-conflicts",
    "scripts/opc-sync.sh",
    "scripts/opc-new.sh",
]


def detect_legacy(instance):
    instance = Path(instance)
    return [rel for rel in LEGACY_MARKERS if (instance / rel).exists()]


def load_instance(instance):
    data = safefile.read_json(Path(instance) / ".opc" / "instance.json", None)
    if not data or data.get("kind") != "opc-instance":
        raise OpcError("不是 OPC 实例（缺 .opc/instance.json 或 kind 不对）：{}".format(instance))
    return data


def copy_mechanism_over(payload, manifest, target):
    """覆盖复制机制文件，但不删除目录里的其他文件（保留本地新增角色模板）。"""
    executables = set((manifest.get("mechanism") or {}).get("executables") or [])
    for rel in manifest_mod.mechanism_files(payload.parent, manifest):
        src = payload / rel
        dst = Path(target) / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".opc-tmp")
        shutil.copy2(src, tmp)
        tmp.replace(dst)
        if dst.suffix == ".sh" or rel in executables:
            try:
                dst.chmod(dst.stat().st_mode | 0o111)
            except OSError:
                pass


def merge_config(src, dst, spec):
    src, dst = Path(src), Path(dst)
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return [item.get(spec["key"]) for item in
                safefile.read_json(src, {}).get(spec["arrayPath"], [])]
    src_data = safefile.read_json(src, {})
    dst_data = safefile.read_json(dst, {})
    array_path = spec["arrayPath"]
    key = spec["key"]
    existing = {item.get(key) for item in dst_data.get(array_path, [])}
    added = []
    for item in src_data.get(array_path, []):
        if item.get(key) in existing:
            continue
        new = dict(item)
        if spec.get("onNew") == "append-disabled":
            new["enabled"] = False
        dst_data.setdefault(array_path, []).append(new)
        added.append(item.get(key))
    if added:
        safefile.write_json(dst, dst_data)
    return added


def verify(target, payload, manifest, old_files):
    """机制文件的本地改动检测。

    只看还是机制的文件：`AGENTS.md`、`agents/` 已经是起始材料，owner
    改它们不算机制被改，不会因此拒绝升级。
    """
    modified, deleted, collisions = [], [], []
    new_files = manifest_mod.mechanism_files(payload.parent, manifest)
    mechanism = set(new_files)
    for rel, digest in sorted(old_files.items()):
        if rel not in mechanism:
            continue
        path = Path(target) / rel
        if not path.exists():
            deleted.append(rel)
        elif sha256_file(path) != digest:
            modified.append(rel)
    for rel in new_files:
        if rel in old_files:
            continue
        path = Path(target) / rel
        if path.exists():
            src = payload / rel
            if not src.is_file() or sha256_file(path) != sha256_file(src):
                collisions.append(rel)
    return modified, deleted, collisions


def _diff(payload, target, rel):
    src = payload / rel
    dst = Path(target) / rel
    left = src.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) \
        if src.is_file() else []
    right = dst.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True) \
        if dst.is_file() else []
    return "".join(difflib.unified_diff(
        right, left, fromfile=str(dst), tofile=str(src)))


def apply_payload(target, template_root, manifest, upstream, data=None):
    """机制覆盖、配置合并、元数据重写。返回 (payload, added_config)。"""
    payload = manifest_mod.payload_root(template_root)
    prefix = (data or {}).get("prefix") or install_mod.slugify(Path(target).name)
    copy_mechanism_over(payload, manifest, target)
    added = {}
    for spec in manifest.get("config", []):
        added[spec["target"]] = merge_config(
            payload / spec["source"], Path(target) / spec["target"], spec)
    install_mod.write_instance_json(target, prefix, template_root, upstream)
    install_mod.write_mechanism_json(target, payload, manifest, template_root, upstream)
    return payload, added


def starter_plan(target, payload, manifest, old_files, entries=None):
    """起始材料的升级计划：读基线（老实例拿机制指纹当基线）并比对现状。"""
    if entries is None:
        entries = starters.expand(payload, manifest)
    baseline = starters.read_baseline(target)
    if not baseline.get("files"):
        baseline = starters.adopt_mechanism_baseline(baseline, old_files, entries)
    return starters.plan(payload, manifest, target, baseline, entries=entries)


def starter_lines(result):
    """起始材料动作的可读摘要。

    只有三种情况告警：owner 改过导致跳过更新、技能目录冻结、模版移除。
    其余（新增、更新、owner 删过不再补）只是过程信息。
    """
    lines = []
    if result.get("updated"):
        lines.append("  起始材料更新：{}".format("、".join(result["updated"])))
    if result.get("added"):
        lines.append("  起始材料新增：{}".format("、".join(result["added"])))
    if result.get("skipped"):
        lines.append("  起始材料跳过（owner 已删除，不再补）：{}".format(
            "、".join(result["skipped"])))
    for rel, reason in result.get("kept") or []:
        lines.append("  警告：{} {}".format(rel, reason))
    if result.get("frozen"):
        lines.append("  警告：技能冻结（整目录跳过更新）：{}".format(
            "、".join(result["frozen"])))
    if result.get("retired"):
        lines.append("  警告：模版已移除该起始材料（实例保留）：{}".format(
            "、".join(result["retired"])))
    return lines


def upgrade_one(template_root, manifest, args, instance, install_ui=True):
    instance = Path(instance).expanduser().resolve()
    if not instance.is_dir():
        raise OpcError("实例目录不存在：{}".format(instance))

    data = load_instance(instance)
    roles = starters.instance_roles(instance)
    starters.validate_skills(instance, roles)
    legacy = detect_legacy(instance)
    if legacy:
        from . import migrate
        return migrate.migrate(template_root, manifest, args, instance, legacy,
                               install_ui=install_ui)

    prefix = data.get("prefix") or install_mod.slugify(instance.name)
    mech_path = instance / ".opc" / "mechanism.json"
    if not mech_path.is_file():
        raise OpcError(
            "缺少 .opc/mechanism.json，无法判断机制文件是否被本地改过。\n"
            "确认没有本地改动后加 --force-mechanism 接管：{}".format(instance))
    old_files = (safefile.read_json(mech_path, {}) or {}).get("files", {})
    payload = manifest_mod.payload_root(template_root)
    modified, deleted, collisions = verify(instance, payload, manifest, old_files)

    problems = modified + deleted + collisions
    if problems and not args.force_mechanism:
        for rel in modified:
            print(_diff(payload, instance, rel))
        raise OpcError(
            "实例里的机制文件被本地改过：\n  {}\n"
            "先回退这些改动，或加 --force-mechanism 覆盖。".format("\n  ".join(problems))
        )

    new_files = set(manifest_mod.mechanism_files(payload.parent, manifest))
    entries = starters.expand(payload, manifest)
    starter_targets = {entry["target"] for entry in entries}
    # 不再是机制的旧文件里，属于起始材料的那部分不删：它归 owner 了。
    obsolete = sorted((set(old_files) - new_files) - starter_targets)

    # 角色单文件迁移：旧实例的 roles.json 还指向 agents/ 下的单文件简报。
    role_result = role_migrate.plan(instance, roles, old_files)

    plan = starter_plan(instance, payload, manifest, old_files, entries=entries)
    role_migrate.detach(plan, role_result)
    planned = [rel for _src, _dst, rel in plan["copy"]]
    planned.extend(role_migrate.written_targets(role_result))
    missing = list(plan.get("missing") or [])
    missing.extend(starters.missing_required_files(instance, entries, planned))
    missing.extend(starters.missing_role_entries(
        instance, role_migrate.effective_roles(roles, role_result), planned))
    if missing:
        raise OpcError("起始材料缺失：\n  " + "\n  ".join(missing))

    if args.dry_run:
        print("将升级实例：{}（前缀 {}）".format(instance, prefix))
        print("  覆盖机制文件：{} 个".format(len(new_files)))
        if obsolete:
            print("  删除机制文件：{}".format("、".join(obsolete)))
        for line in starter_lines(plan):
            print(line)
        for line in role_migrate.lines(role_result):
            print(line)
        print("  重跑实例安装器")
        return 0

    role_migrate.apply(instance, role_result)
    apply_payload(instance, template_root, manifest, args.upstream, data)
    starters.apply(plan)
    starters.write_baseline(instance, plan["baseline"])

    for rel in obsolete:
        path = instance / rel
        if path.exists():
            path.unlink()

    install_mod.run_installer(instance, prefix, "--no-input", args.skip_smoke)
    if install_ui:
        ui.install(payload, manifest, force=args.force_ui, dry_run=False)
    touched = list(plan["added"]) + list(plan["updated"])
    touched.extend(role_migrate.paths(role_result))
    gitutil.commit_paths(
        instance, manifest_mod.commit_paths(manifest, extra=touched),
        "chore: opc upgrade -> {}".format(gitutil.head_commit(template_root)[:12]),
        template_repo=template_root,
    )
    registry.upsert(instance, prefix, gitutil.head_commit(template_root), args.upstream)
    for line in starter_lines(plan):
        print(line)
    for line in role_migrate.lines(role_result):
        print(line)
    print("已升级：{}".format(instance))
    return 0


def upgrade_all(template_root, manifest, args):
    targets = registry.paths_list()
    if not targets:
        raise OpcError("注册表里没有实例；先运行 opc install。")
    failed = []
    for instance in targets:
        if not instance.is_dir():
            print("跳过（目录不存在）：{}".format(instance), file=sys.stderr)
            continue
        try:
            upgrade_one(template_root, manifest, args, instance, install_ui=False)
        except OpcError as exc:
            failed.append((instance, exc.message))
            print("升级失败：{}：{}".format(instance, exc.message), file=sys.stderr)
    ui.install(manifest_mod.payload_root(template_root), manifest,
               force=args.force_ui, dry_run=args.dry_run)
    if failed:
        raise OpcError("有 {} 个实例升级失败".format(len(failed)))
    return 0
