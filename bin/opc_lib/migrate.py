"""旧实例一次性迁移：移除实例内的 UI/种子副本，改指纹模型。"""

import shutil
import sys
from pathlib import Path

from . import install as install_mod
from . import gitutil, manifest as manifest_mod, registry, role_migrate, safefile, starters, ui
from .errors import OpcError
from .hashutil import sha256_bytes, sha256_file
from .upgrade import apply_payload, load_instance, starter_lines

DELETIONS = [
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
    ".claude/commands/opc-init.md",
]

OPTIONAL_DELETIONS = {".claude/commands/opc-init.md"}


def _baseline_bytes(instance, rel):
    baseline = Path(instance) / ".opc" / "sync-base" / rel
    if baseline.is_file():
        return baseline.read_bytes()
    commit = gitutil.first_add_commit(instance, rel)
    if commit:
        text = gitutil.show_file(instance, commit, rel)
        if text is not None:
            return text.encode("utf-8")
    return None


def _modified_mechanisms(instance, payload, manifest):
    modified = []
    for rel in manifest_mod.mechanism_files(payload.parent, manifest):
        target = Path(instance) / rel
        source = payload / rel
        if not target.is_file() or not source.is_file():
            continue
        baseline = _baseline_bytes(instance, rel)
        if baseline is None:
            continue
        if sha256_bytes(baseline) != sha256_file(target):
            modified.append(rel)
    return modified


def _to_delete(instance):
    result = []
    for rel in DELETIONS:
        if (Path(instance) / rel).exists():
            result.append(rel)
    return result


def _backup(instance, rels):
    stamp = install_mod.now().replace(":", "").replace("+", "-")
    root = Path(instance).parent / (".opc-backup-" + stamp)
    for rel in rels:
        src = Path(instance) / rel
        if not src.exists():
            continue
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)
    return root


def _legacy_starter_baseline(instance, payload, manifest):
    """老实例的起始材料基线：拿 git 里首次提交的那份当基线。

    首次提交里那份就是「装进来时的模版版本」：owner 之后没改过的，
    升级时会刷新到模版最新版；改过的会因哈希不同被保留并告警。
    """
    files = {}
    for entry in starters.expand(payload, manifest):
        rel = entry["target"]
        if not (Path(instance) / rel).is_file():
            continue
        commit = gitutil.first_add_commit(instance, rel)
        if not commit:
            continue
        text = gitutil.show_file(instance, commit, rel)
        if text is None:
            continue
        record = {"sha256": sha256_bytes(text.encode("utf-8")), "kind": entry["kind"]}
        if entry.get("unit"):
            record["unit"] = entry["unit"]
        files[rel] = record
    return {"version": 1, "files": files}


def _legacy_role_fingerprint(instance, roles, fingerprint):
    """从 git 首次提交补出旧角色指纹；现存 mechanism 记录优先。"""
    reconstructed = {}
    for role in role_migrate.detect(roles):
        rel = role.get("template") or ""
        commit = gitutil.first_add_commit(instance, rel)
        if not commit:
            continue
        text = gitutil.show_file(instance, commit, rel)
        if text is not None:
            reconstructed[rel] = sha256_bytes(text.encode("utf-8"))
    reconstructed.update(fingerprint or {})
    return reconstructed


def migrate(template_root, manifest, args, instance, legacy, install_ui=True):
    instance = Path(instance).resolve()
    data = load_instance(instance)
    prefix = data.get("prefix") or install_mod.slugify(instance.name)
    payload = manifest_mod.payload_root(template_root)

    modified = _modified_mechanisms(instance, payload, manifest)
    if modified and not args.force_mechanism:
        raise OpcError(
            "实例里的机制文件被本地改过，先回退或加 --force-mechanism：\n  "
            + "\n  ".join(modified))

    deletions = _to_delete(instance)
    dirty = gitutil.dirty_paths(instance, deletions)
    if dirty and not args.force_mechanism:
        raise OpcError(
            "要删除的路径有未提交改动，先提交或 stash：\n  "
            + "\n  ".join(line.strip() for line in dirty))

    # 角色单文件迁移：旧指纹优先；没有 mechanism.json 的更老实例从
    # git 首次提交重建，避免把每个未改角色都误判为 owner 修改。
    fingerprint = (safefile.read_json(
        instance / ".opc" / "mechanism.json", {}) or {}).get("files", {})
    roles = starters.instance_roles(instance)
    fingerprint = _legacy_role_fingerprint(instance, roles, fingerprint)
    role_result = role_migrate.plan(instance, roles, fingerprint)
    role_lines = role_migrate.lines(role_result)

    # 起始材料计划必须在 dry-run 返回前完成，才能完整展示更新与技能冻结；
    # 这里只读，不会写基线或实例文件。
    entries = starters.expand(payload, manifest)
    baseline = starters.read_baseline(instance)
    if not baseline.get("files"):
        baseline = _legacy_starter_baseline(instance, payload, manifest)
    plan = starters.plan(payload, manifest, instance, baseline, entries=entries)
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
        print("将迁移旧实例：{}（前缀 {}）".format(instance, prefix))
        print("  检测到旧结构：" + "、".join(legacy))
        if modified:
            print("  机制文件本地改动（--force-mechanism 会覆盖）：" + "、".join(modified))
        print("  实例内删除：")
        for rel in deletions:
            print("    - {}".format(rel))
        print("  全局清理：~/.config/herdr-app 下 {} 前缀的旧布局与 mod".format(prefix))
        for line in starter_lines(plan):
            print(line)
        for line in role_lines:
            print(line)
        print("  然后：复制新机制、合并配置、补起始材料、单个提交、重跑安装器")
        return 0

    if not args.yes:
        if not sys.stdin.isatty():
            raise OpcError("迁移需要确认；非交互环境请加 --yes")
        answer = input("确认迁移 {}？[y/N] ".format(instance))
        if answer.strip().lower() not in {"y", "yes", "是"}:
            raise OpcError("已取消")

    backup = _backup(instance, deletions)
    for rel in deletions:
        path = instance / rel
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()

    role_migrate.apply(instance, role_result)
    apply_payload(instance, template_root, manifest, args.upstream, data)

    starters.apply(plan)
    starters.write_baseline(instance, plan["baseline"])

    touched = list(plan["added"]) + list(plan["updated"])
    touched.extend(role_migrate.paths(role_result))
    commit_list = list(deletions) + manifest_mod.commit_paths(manifest, extra=touched)
    gitutil.commit_paths(
        instance, commit_list,
        "chore: 迁移到 opc 新结构（移除实例内的 UI/种子副本）",
        template_repo=template_root,
    )

    ui.cleanup_legacy([prefix], manifest)
    if install_ui:
        ui.install(payload, manifest, force=args.force_ui, dry_run=False)
    install_mod.run_installer(instance, prefix, "--no-input", args.skip_smoke)
    registry.upsert(instance, prefix, gitutil.head_commit(template_root), args.upstream)

    print("已迁移：{}".format(instance))
    for line in starter_lines(plan):
        print(line)
    for line in role_lines:
        print(line)
    if backup.exists():
        print("  旧文件备份：{}".format(backup))
    print("  下一步：重启 herdr-app，然后 cd \"{}\" && scripts/opc-up.sh".format(instance))
    return 0
