"""载荷清单：template/install-manifest.json 是唯一口径。"""

import json
from pathlib import Path

from . import safefile
from .errors import OpcError

IGNORE_DIRS = {"__pycache__", ".git"}
IGNORE_SUFFIXES = {".pyc"}
IGNORE_NAMES = {".DS_Store"}


def payload_root(template_root):
    return Path(template_root) / "template"


def manifest_path(template_root):
    return payload_root(template_root) / "install-manifest.json"


def load(template_root):
    path = manifest_path(template_root)
    if not path.is_file():
        raise OpcError("找不到载荷清单：{}".format(path))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OpcError("载荷清单不是合法 JSON：{}（{}）".format(path, exc))
    validate(template_root, data)
    return data


def safe_rel(rel):
    """清单路径校验的布尔接口；底层与实例文件操作共用同一实现。"""
    return safefile.safe_rel(rel)


def _check(root, rel, what):
    if not safe_rel(rel):
        raise OpcError("载荷清单里的{}路径不合法：{}".format(what, rel))
    if not safefile.inside(root, root / rel):
        raise OpcError("载荷清单里的{}路径不在载荷内：{}".format(what, rel))


def validate(template_root, manifest):
    root = payload_root(template_root)
    if manifest.get("version") != 1:
        raise OpcError("载荷清单版本不支持：{}".format(manifest.get("version")))
    mech = manifest.get("mechanism") or {}
    for rel in mech.get("dirs", []) + mech.get("files", []):
        _check(root, rel, "机制")
        if not (root / rel).exists():
            raise OpcError("载荷清单引用的机制路径不存在：{}".format(rel))
    mechanism_files_set = set(mechanism_files(template_root, manifest))
    for rel in mech.get("executables", []):
        _check(root, rel, "可执行文件")
        if rel not in mechanism_files_set:
            raise OpcError("可执行文件不属于机制载荷：{}".format(rel))
    for item in manifest.get("seeds", []):
        _check(root, item["source"], "种子来源")
        if not (root / item["source"]).is_file():
            raise OpcError("种子来源不存在：{}".format(item["source"]))
        if not item.get("target"):
            raise OpcError("种子缺少 target：{}".format(item["source"]))
        _check(root, item["target"], "种子目标")
    starters = manifest.get("starters") or {}
    for item in starters.get("files", []):
        _check(root, item["source"], "起始材料来源")
        if not (root / item["source"]).is_file():
            raise OpcError("起始材料来源不存在：{}".format(item["source"]))
        if not item.get("target"):
            raise OpcError("起始材料缺少 target：{}".format(item["source"]))
        _check(root, item["target"], "起始材料目标")
    for item in starters.get("dirs", []):
        _check(root, item["source"], "起始材料目录")
        path = root / item["source"]
        # 目录型起始材料可以先声明后落地（如 `skills/`）：目录不在就不起作用。
        if path.exists() and not path.is_dir():
            raise OpcError("起始材料来源不是目录：{}".format(item["source"]))
        if not item.get("target"):
            raise OpcError("起始材料目录缺少 target：{}".format(item["source"]))
        _check(root, item["target"], "起始材料目录目标")
    ui = manifest.get("ui") or {}
    for item in ui.get("layouts", []):
        _check(root, item["source"], "布局")
        if not (root / item["source"]).is_file():
            raise OpcError("布局来源不存在：{}".format(item["source"]))
        if item.get("asset"):
            _check(root, item["asset"], "布局资源")
            if not (root / item["asset"]).is_file():
                raise OpcError("布局资源不存在：{}".format(item["asset"]))
    for name in ui.get("mods", []):
        if not (root / "mods" / name).is_dir():
            raise OpcError("mod 目录不存在：mods/{}".format(name))


def mechanism_files(template_root, manifest):
    """机制文件清单（仓库内相对路径，正斜杠）。"""
    root = payload_root(template_root)
    mech = manifest.get("mechanism") or {}
    files = []
    for rel_dir in mech.get("dirs", []):
        base = root / rel_dir
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if should_ignore(path):
                continue
            files.append(rel)
    for rel_file in mech.get("files", []):
        path = root / rel_file
        if path.is_file():
            files.append(Path(rel_file).as_posix())
    return sorted(set(files))


def should_ignore(path):
    path = Path(path)
    if path.name in IGNORE_NAMES or path.suffix in IGNORE_SUFFIXES:
        return True
    return any(part in IGNORE_DIRS for part in path.parts)


def commit_paths(manifest, extra=None):
    """upgrade/migrate 需要提交的路径（相对实例根）。

    种子已是起始材料，只在本次真的动了的时候才提交，所以由调用方通过
    extra 传进来；这里只管机制目录、机制文件与配置文件。
    """
    mech = manifest.get("mechanism") or {}
    paths = list(mech.get("dirs", [])) + list(mech.get("files", []))
    paths += [spec["target"] for spec in manifest.get("config", [])]
    paths += list(extra or [])
    seen = []
    for path in paths:
        if path not in seen:
            seen.append(path)
    return seen
