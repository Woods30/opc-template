"""实例内的文件操作：按目录描述符逐段打开，不跟随软链接。

按路径名校验之后再按路径名打开，中间留了竞态窗口：能在实例目录里换符号
链接的人本来就能改这个实例，但既然要关，就用 `O_NOFOLLOW` 与 `dir_fd`
逐段打开，把窗口关上。

所有路径都是相对实例根的相对路径；每一段都不能是 `..`，也不能是软链接。
"""

import json
import os
from pathlib import Path

from .errors import OpcError

O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)

TMP_PREFIX = ".opc-tmp-"


class UnsafePath(Exception):
    """路径不合法，或落点不在实例内。"""


def split_rel(rel):
    """把相对路径拆成段；绝对路径与 `..` 一律拒绝。"""
    if not rel or not isinstance(rel, str) or os.path.isabs(rel):
        raise UnsafePath("路径不合法：{}".format(rel))
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise UnsafePath("路径不合法：{}".format(rel))
    return parts


def safe_rel(rel):
    """相对路径是否合法；供只需要布尔结果的清单校验复用。"""
    try:
        split_rel(rel)
    except UnsafePath:
        return False
    return True


def inside(root, path):
    """路径（含软链接落点）是否仍在 root 之下。"""
    try:
        resolved = Path(path).resolve()
        base = Path(root).resolve()
    except OSError:
        return False
    return resolved == base or base in resolved.parents


def symlink_component(root, path):
    """路径的任一层（含自己）是不是软链接。"""
    root = Path(root)
    try:
        rel = Path(path).relative_to(root)
    except ValueError:
        return True
    current = root
    for part in rel.parts:
        current = current / part
        try:
            if current.is_symlink():
                return True
        except OSError:
            return True
    return False


def read_json(path, default=None):
    """读取 JSON；文件不存在时返回 default，格式错误时给统一诊断。"""
    path = Path(path)
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise OpcError("不是合法 JSON：{}（{}）".format(path, exc))


def write_json(path, data):
    """原子写入 JSON。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _open_dir(root, parts, create=False):
    """逐段打开目录；`create` 为真时缺哪段建哪段。"""
    fd = os.open(str(root), os.O_RDONLY | O_DIRECTORY)
    try:
        for part in parts:
            try:
                nfd = os.open(part, os.O_RDONLY | O_DIRECTORY | O_NOFOLLOW,
                              dir_fd=fd)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, 0o755, dir_fd=fd)
                nfd = os.open(part, os.O_RDONLY | O_DIRECTORY | O_NOFOLLOW,
                              dir_fd=fd)
            os.close(fd)
            fd = nfd
    except BaseException:
        os.close(fd)
        raise
    return fd


def _tmp_name():
    return "{}{}".format(TMP_PREFIX, os.getpid())


def read_text(root, rel):
    """读实例内的文本文件；目标是软链接时报错，不顺着读。"""
    parts = split_rel(rel)
    parent = _open_dir(root, parts[:-1])
    try:
        fd = os.open(parts[-1], os.O_RDONLY | O_NOFOLLOW, dir_fd=parent)
    finally:
        os.close(parent)
    with os.fdopen(fd, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def write_text(root, rel, text, mode=0o644):
    """原子写入：先写同目录临时文件，再 replace 过去。"""
    parts = split_rel(rel)
    parent = _open_dir(root, parts[:-1], create=True)
    tmp = _tmp_name()
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | O_NOFOLLOW,
                     0o600, dir_fd=parent)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(tmp, mode, dir_fd=parent)
        os.replace(tmp, parts[-1], src_dir_fd=parent, dst_dir_fd=parent)
    except BaseException:
        _unlink_quiet(parent, tmp)
        raise
    finally:
        os.close(parent)


def copy_from(src_root, src_rel, dst_root, dst_rel, mode=None):
    """在两个受限目录之间复制文件，来源与落点都不跟随软链接。"""
    sparts = split_rel(src_rel)
    dparts = split_rel(dst_rel)
    src_parent = _open_dir(src_root, sparts[:-1])
    try:
        sfd = os.open(sparts[-1], os.O_RDONLY | O_NOFOLLOW, dir_fd=src_parent)
    finally:
        os.close(src_parent)
    with os.fdopen(sfd, "rb") as source:
        data = source.read()
        source_mode = os.fstat(source.fileno()).st_mode & 0o777
    parent = _open_dir(dst_root, dparts[:-1], create=True)
    tmp = _tmp_name()
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | O_NOFOLLOW,
                     0o600, dir_fd=parent)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(tmp, mode if mode is not None else (source_mode or 0o644), dir_fd=parent)
        os.replace(tmp, dparts[-1], src_dir_fd=parent, dst_dir_fd=parent)
    except BaseException:
        _unlink_quiet(parent, tmp)
        raise
    finally:
        os.close(parent)


def unlink(root, rel):
    """删掉实例里的一个文件（不跟随软链接）。"""
    parts = split_rel(rel)
    parent = _open_dir(root, parts[:-1])
    try:
        os.unlink(parts[-1], dir_fd=parent)
    finally:
        os.close(parent)


def exists(root, rel):
    """实例里有没有这个路径（软链接本身算存在，不跟随）。"""
    try:
        parts = split_rel(rel)
    except UnsafePath:
        return False
    try:
        parent = _open_dir(root, parts[:-1])
    except OSError:
        return False
    try:
        os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        return True
    except OSError:
        return False
    finally:
        os.close(parent)


def _unlink_quiet(parent, name):
    try:
        os.unlink(name, dir_fd=parent)
    except OSError:
        pass
