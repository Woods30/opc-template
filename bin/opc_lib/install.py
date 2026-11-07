"""install：创建实例、复制机制、装起始材料、装全局 UI。"""

import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from . import cache, gitutil, manifest as manifest_mod, paths, registry, safefile, starters, ui
from .errors import OpcError
from .hashutil import sha256_file

PREFIX_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,30}$")
CHANNEL_RE = re.compile(r"^[a-z][a-z0-9-]{0,19}$")


def slugify(name):
    value = str(name).lower()
    value = re.sub(r"[^a-z0-9_-]", "-", value)
    return value.strip("-") or "opc"


def now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def validate_prefix(prefix):
    if not PREFIX_RE.match(prefix):
        raise OpcError("前缀不合法：{}（只允许 1-31 位 a-z 0-9 - _，且以字母数字开头）".format(prefix))
    return prefix


def copy_mechanism(payload, manifest, target):
    """把机制目录与文件复制到空实例。"""
    target = Path(target)
    mechanism = manifest.get("mechanism") or {}
    executables = set(mechanism.get("executables") or [])
    for rel_dir in mechanism.get("dirs", []):
        src = payload / rel_dir
        dst = target / rel_dir
        if dst.exists():
            raise OpcError("实例里已有 {}，目标目录不是空的".format(rel_dir))
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", ".DS_Store"))
        for path in dst.rglob("*"):
            rel = path.relative_to(target).as_posix()
            if path.is_file() and (path.suffix == ".sh" or rel in executables):
                try:
                    path.chmod(path.stat().st_mode | 0o111)
                except OSError:
                    pass
    for rel_file in (manifest.get("mechanism") or {}).get("files", []):
        src = payload / rel_file
        dst = target / rel_file
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def copy_config(payload, manifest, target):
    for spec in manifest.get("config", []):
        src = payload / spec["source"]
        dst = target / spec["target"]
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def apply_answers(target, answers):
    """把 /opc-init 的问答结果写进 roles.json / channels.json。"""
    if not answers:
        return
    roles_path = Path(target) / "roles.json"
    roles_data = safefile.read_json(roles_path, {"roles": []})
    role_answers = answers.get("roles") or {}
    for role in roles_data.get("roles", []):
        patch = role_answers.get(role.get("name"))
        if not patch:
            continue
        if "enabled" in patch:
            role["enabled"] = bool(patch["enabled"])
        if patch.get("cli"):
            role["cli"] = str(patch["cli"])
        if patch.get("permissionMode"):
            role["permissionMode"] = str(patch["permissionMode"])
    safefile.write_json(roles_path, roles_data)

    channels = answers.get("channels")
    if isinstance(channels, list):
        cleaned = []
        for item in channels:
            if isinstance(item, str):
                item = {"id": item, "name": item, "enabled": True}
            cid = str(item.get("id", ""))
            if not CHANNEL_RE.match(cid):
                raise OpcError("频道 id 不合法：{}".format(cid))
            cleaned.append({
                "id": cid,
                "name": str(item.get("name") or cid),
                "enabled": bool(item.get("enabled", True)),
            })
        safefile.write_json(Path(target) / "channels.json", {"channels": cleaned})


def mechanism_hashes(payload, manifest):
    return {
        rel: sha256_file(payload / rel)
        for rel in manifest_mod.mechanism_files(payload.parent, manifest)
    }


def write_instance_json(target, prefix, template_root, upstream, created=False):
    path = Path(target) / ".opc" / "instance.json"
    data = safefile.read_json(path, {}) or {}
    data["version"] = 2
    data["kind"] = "opc-instance"
    data["prefix"] = prefix
    data.setdefault("createdAt", now())
    data["updatedAt"] = now()
    data["template"] = {
        "id": "opc-template",
        "source": str(Path(template_root).resolve()),
        "commit": gitutil.head_commit(template_root),
        "upstream": upstream,
    }
    safefile.write_json(path, data)
    return data


def write_mechanism_json(target, payload, manifest, template_root, upstream):
    path = Path(target) / ".opc" / "mechanism.json"
    data = safefile.read_json(path, {}) or {}
    data["version"] = 1
    data.setdefault("installedAt", now())
    data["upgradedAt"] = now()
    data["template"] = {
        "id": "opc-template",
        "source": str(Path(template_root).resolve()),
        "commit": gitutil.head_commit(template_root),
        "upstream": upstream,
    }
    data["files"] = mechanism_hashes(payload, manifest)
    data["policy"] = {
        "proposalDir": manifest.get("proposalDir"),
        "proposalSections": manifest.get("proposalSections", []),
        "manifestVersion": manifest.get("version"),
    }
    safefile.write_json(path, data)
    return data


def run_installer(target, prefix, input_mode="--no-input", skip_smoke=False):
    script = Path(target) / "scripts" / "opc-install.sh"
    if not script.is_file():
        raise OpcError("实例里没有 scripts/opc-install.sh：{}".format(target))
    argv = ["bash", str(script), input_mode, prefix]
    if skip_smoke:
        argv.append("--skip-smoke")
    proc = subprocess.run(argv, cwd=str(target))
    if proc.returncode != 0:
        raise OpcError("实例安装器失败（退出码 {}）".format(proc.returncode))


def install(template_root, manifest, args):
    payload = manifest_mod.payload_root(template_root)
    entries = starters.expand(payload, manifest)
    target = Path(args.target).expanduser()
    prefix = args.prefix or slugify(target.name)
    validate_prefix(prefix)

    if paths.is_within(target, template_root):
        raise OpcError("目标不能放在模版目录内部：{}".format(target))
    if target.exists() and any(target.iterdir()):
        raise OpcError("目标目录非空：{}".format(target))
    if target.exists() and not target.is_dir():
        raise OpcError("目标不是目录：{}".format(target))

    if args.dry_run:
        print("将创建实例：{}（前缀 {}）".format(target, prefix))
        print("  机制：{}".format("、".join(
            (manifest.get("mechanism") or {}).get("dirs", [])
            + (manifest.get("mechanism") or {}).get("files", []))))
        print("  起始材料：{} 份（装一次就归 owner，升级只补不改）".format(len(entries)))
        print("  全局 UI：{}".format(paths.herdr_app_home()))
        print("  git：init + 首次提交")
        return 0

    target.mkdir(parents=True, exist_ok=True)
    target = target.resolve()
    copy_mechanism(payload, manifest, target)
    copy_config(payload, manifest, target)
    baseline, _added = starters.install(payload, manifest, target, entries=entries)
    starters.write_baseline(target, baseline)

    answers = safefile.read_json(args.answers) if args.answers else None
    if answers and answers.get("prefix"):
        prefix = validate_prefix(str(answers["prefix"]))
    apply_answers(target, answers)

    roles = starters.instance_roles(target)
    starters.validate_skills(target, roles)
    missing = starters.missing_required_files(target, entries)
    missing.extend(starters.missing_role_entries(target, starters.instance_roles(target)))
    if missing:
        raise OpcError("起始材料缺失：\n  " + "\n  ".join(missing))

    write_instance_json(target, prefix, template_root, args.upstream)
    write_mechanism_json(target, payload, manifest, template_root, args.upstream)

    if not args.no_git:
        if not gitutil.is_repo(target):
            gitutil.run(target.parent, "init", "-q", "-b", "main", str(target))
    input_mode = "--interactive" if args.interactive else "--no-input"
    run_installer(target, prefix, input_mode, args.skip_smoke)

    if not args.no_git and gitutil.is_repo(target):
        gitutil.commit_paths(
            target, ["."],
            "chore: 实例初始快照（模版机制 + 起始材料 + 配置）",
            template_repo=template_root,
        )

    ui.install(payload, manifest, force=args.force_ui, dry_run=False)
    registry.upsert(target, prefix, gitutil.head_commit(template_root), args.upstream)
    cache.ensure_global_command(template_root)

    print("已创建 OPC 实例：{}".format(target))
    print("  前缀：{}".format(prefix))
    print("  下一步：cd \"{}\" && scripts/opc-up.sh".format(target))
    return 0
