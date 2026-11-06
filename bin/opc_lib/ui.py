"""全局 UI：一套 opc 布局与 mod，所有实例共用；按哈希记录本地改动。"""

import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from . import paths
from .errors import OpcError
from .hashutil import sha256_bytes

IGNORE_NAMES = {"gpui-kit.d.ts", "jsconfig.json", ".DS_Store"}
IGNORE_DIRS = {"__pycache__"}
IGNORE_SUFFIXES = {".pyc"}

RE_LEGACY_LAYOUT = re.compile(r".+-opc-(dashboard|focus|grid|monitor)\.json$")


def _now():
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _state():
    path = paths.ui_state_path()
    if not path.is_file():
        return {"version": 1, "files": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "files": {}}
    data.setdefault("version", 1)
    data.setdefault("files", {})
    return data


def _save_state(state):
    path = paths.ui_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _backup(dst):
    root = paths.backup_root() / _now() / "ui"
    target = root / dst.relative_to(paths.herdr_app_home())
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(dst, target)
    return target


def _write_atomic(dst, data):
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + ".opc-tmp")
    tmp.write_bytes(data)
    os.replace(tmp, dst)


def _iter_mod_files(mod_dir):
    for path in sorted(mod_dir.rglob("*")):
        if not path.is_file():
            continue
        if path.name in IGNORE_NAMES or path.suffix in IGNORE_SUFFIXES:
            continue
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        yield path.relative_to(mod_dir).as_posix(), path


def plan_files(payload, manifest):
    """返回 [(herdr 目录内的相对路径, 源文件)]。"""
    ui = manifest.get("ui") or {}
    files = []
    for spec in ui.get("layouts", []):
        files.append(("layouts/{}.json".format(spec["name"]), payload / spec["source"]))
        asset = spec.get("asset")
        if asset:
            src = payload / asset
            files.append(("layouts/{}{}".format(spec["name"], src.suffix), src))
    for name in ui.get("mods", []):
        mod_dir = payload / "mods" / name
        for rel, src in _iter_mod_files(mod_dir):
            files.append(("mods/{}/{}".format(name, rel), src))
    return files


def install(payload, manifest, force=False, dry_run=False):
    app_home = paths.herdr_app_home()
    state = _state()
    tracked = state["files"]
    conflicts = []
    actions = []

    for rel, src in plan_files(payload, manifest):
        dst = app_home / rel
        new = src.read_bytes()
        digest = sha256_bytes(new)
        current = dst.read_bytes() if dst.is_file() else None
        recorded = tracked.get(rel)
        if current is None:
            actions.append(("add", rel))
        elif current == new:
            tracked[rel] = digest
            continue
        elif recorded and sha256_bytes(current) != recorded:
            if not force:
                conflicts.append(rel)
                continue
            actions.append(("backup+update", rel))
        else:
            actions.append(("backup+update", rel) if current is not None else ("add", rel))
        if dry_run:
            continue
        if current is not None:
            _backup(dst)
        _write_atomic(dst, new)
        tracked[rel] = digest

    if conflicts:
        raise OpcError(
            "全局 UI 有本地修改，未覆盖：\n  "
            + "\n  ".join(conflicts)
            + "\n确认要覆盖请加 --force-ui（旧文件会先备份）。"
        )

    if not dry_run:
        _save_state(state)
    return actions


def cleanup_legacy(prefixes, dry_run=False):
    """清理旧版本按前缀安装的布局与 mod。返回被清理的路径。"""
    app_home = paths.herdr_app_home()
    layouts = app_home / "layouts"
    mods = app_home / "mods"
    victims = []

    if mods.is_dir():
        for path in mods.iterdir():
            name = path.name
            if name in {"opc-dashboard", "opc-tabs"}:
                continue
            if name.endswith("-opc-dashboard") or name.endswith("-opc-tabs"):
                victims.append(path)

    if layouts.is_dir():
        for path in layouts.iterdir():
            name = path.name
            if RE_LEGACY_LAYOUT.match(name):
                victims.append(path)
                continue
            stem = path.stem
            if stem in prefixes and path.suffix in {".json", ".svg"}:
                victims.append(path)

    if dry_run:
        return victims
    for path in victims:
        if not path.exists():
            continue
        target = paths.backup_root() / _now() / "legacy-ui" / path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir():
            shutil.copytree(path, target, dirs_exist_ok=True)
            shutil.rmtree(path)
        else:
            shutil.copy2(path, target)
            path.unlink()
    return victims
