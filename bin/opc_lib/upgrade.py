"""upgrade：指纹校验 + 整目录覆盖；本地改过机制文件则拒绝。"""

import difflib
import json
import shutil
from pathlib import Path

from . import install as install_mod
from . import gitutil, manifest as manifest_mod, registry, ui
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
    data = install_mod.load_json(Path(instance) / ".opc" / "instance.json", None)
    if not data or data.get("kind") != "opc-instance":
        raise OpcError("不是 OPC 实例（缺 .opc/instance.json 或 kind 不对）：{}".format(instance))
    return data


def copy_mechanism_over(payload, manifest, target):
    """覆盖复制机制文件，但不删除目录里的其他文件（保留本地新增角色模板）。"""
    for rel in manifest_mod.mechanism_files(payload.parent, manifest):
        src = payload / rel
        dst = Path(target) / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name(dst.name + ".opc-tmp")
        shutil.copy2(src, tmp)
        tmp.replace(dst)
        if dst.suffix == ".sh" or dst.name in {
                "opc-workflow", "opc-lint", "preflight", "opc-smoke"}:
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
                install_mod.load_json(src, {}).get(spec["arrayPath"], [])]
    src_data = install_mod.load_json(src, {})
    dst_data = install_mod.load_json(dst, {})
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
        install_mod.write_json(dst, dst_data)
    return added


def verify(target, payload, manifest, old_files):
    modified, deleted, collisions = [], [], []
    for rel, digest in sorted(old_files.items()):
        path = Path(target) / rel
        if not path.exists():
            deleted.append(rel)
        elif sha256_file(path) != digest:
            modified.append(rel)
    new_files = manifest_mod.mechanism_files(payload.parent, manifest)
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
    """机制覆盖、配置合并、种子物化、元数据重写。返回 (payload, added_config)。"""
    payload = manifest_mod.payload_root(template_root)
    prefix = (data or {}).get("prefix") or install_mod.slugify(Path(target).name)
    copy_mechanism_over(payload, manifest, target)
    added = {}
    for spec in manifest.get("config", []):
        added[spec["target"]] = merge_config(
            payload / spec["source"], Path(target) / spec["target"], spec)
    install_mod.materialize_seeds(payload, manifest, target)
    install_mod.write_instance_json(target, prefix, template_root, upstream)
    install_mod.write_mechanism_json(target, payload, manifest, template_root, upstream)
    return payload, added


def upgrade_one(template_root, manifest, args, instance, install_ui=True):
    instance = Path(instance).expanduser().resolve()
    if not instance.is_dir():
        raise OpcError("实例目录不存在：{}".format(instance))

    legacy = detect_legacy(instance)
    if legacy:
        from . import migrate
        return migrate.migrate(template_root, manifest, args, instance, legacy,
                               install_ui=install_ui)

    data = load_instance(instance)
    prefix = data.get("prefix") or install_mod.slugify(instance.name)
    mech_path = instance / ".opc" / "mechanism.json"
    if not mech_path.is_file():
        raise OpcError(
            "缺少 .opc/mechanism.json，无法判断机制文件是否被本地改过。\n"
            "确认没有本地改动后加 --force-mechanism 接管：{}".format(instance))
    old_files = (install_mod.load_json(mech_path, {}) or {}).get("files", {})
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
    obsolete = sorted(set(old_files) - new_files)

    if args.dry_run:
        print("将升级实例：{}（前缀 {}）".format(instance, prefix))
        print("  覆盖机制文件：{} 个".format(len(new_files)))
        if obsolete:
            print("  删除机制文件：{}".format("、".join(obsolete)))
        print("  种子：只补缺失")
        print("  重跑实例安装器")
        return 0

    apply_payload(instance, template_root, manifest, args.upstream, data)

    for rel in obsolete:
        path = instance / rel
        if path.exists():
            path.unlink()

    install_mod.run_installer(instance, prefix, "--no-input", args.skip_smoke)
    if install_ui:
        ui.install(payload, manifest, force=args.force_ui, dry_run=False)
    gitutil.commit_paths(
        instance, manifest_mod.commit_paths(manifest),
        "chore: opc upgrade -> {}".format(gitutil.head_commit(template_root)[:12]),
        template_repo=template_root,
    )
    registry.upsert(instance, prefix, gitutil.head_commit(template_root), args.upstream)
    print("已升级：{}".format(instance))
    return 0


def upgrade_all(template_root, manifest, args):
    targets = registry.paths_list()
    if not targets:
        raise OpcError("注册表里没有实例；先运行 opc install。")
    failed = []
    for instance in targets:
        if not instance.is_dir():
            print("跳过（目录不存在）：{}".format(instance), file=__import__("sys").stderr)
            continue
        try:
            upgrade_one(template_root, manifest, args, instance, install_ui=False)
        except OpcError as exc:
            failed.append((instance, exc.message))
            print("升级失败：{}：{}".format(instance, exc.message), file=__import__("sys").stderr)
    ui.install(manifest_mod.payload_root(template_root), manifest,
               force=args.force_ui, dry_run=args.dry_run)
    if failed:
        raise OpcError("有 {} 个实例升级失败".format(len(failed)))
    return 0
