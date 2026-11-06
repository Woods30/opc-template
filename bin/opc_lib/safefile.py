"""实例内的文件操作：按目录描述符逐段打开，不跟随软链接。

按路径名校验之后再按路径名打开，中间留了竞态窗口：能在实例目录里换符号
链接的人本来就能改这个实例，但既然要关，就用 `O_NOFOLLOW` 与 `dir_fd`
逐段打开，把窗口关上。

所有路径都是相对实例根的相对路径；每一段都不能是 `..`，也不能是软链接。
"""

import os

O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)

TMP_PREFIX = ".opc-tmp-"


class UnsafePath(Exception):
    """路径不合法，或落点不在实例内。"""


def split_rel(rel):
    """把相对路径拆成段；绝对路径与 `..` 一律拒绝。"""
    if not rel or not isinstance(rel, str):
        raise UnsafePath("路径不合法：{}".format(rel))
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        raise UnsafePath("路径不合法：{}".format(rel))
    return parts


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


def copy_from(root, src_path, rel, mode=None):
    """把实例外的文件复制进实例。

    来源按普通路径读（模版侧可信），落点在实例内按目录描述符写。
    """
    parts = split_rel(rel)
    parent = _open_dir(root, parts[:-1], create=True)
    tmp = _tmp_name()
    try:
        with open(str(src_path), "rb") as source:
            data = source.read()
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | O_NOFOLLOW,
                     0o600, dir_fd=parent)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        if mode is None:
            try:
                mode = os.stat(str(src_path)).st_mode & 0o777
            except OSError:
                mode = 0o644
        os.chmod(tmp, mode, dir_fd=parent)
        os.replace(tmp, parts[-1], src_dir_fd=parent, dst_dir_fd=parent)
    except BaseException:
        _unlink_quiet(parent, tmp)
        raise
    finally:
        os.close(parent)


def copy_file(root, src_rel, dst_rel):
    """把实例内的文件复制到实例内的另一个路径。"""
    src = split_rel(src_rel)
    dst = split_rel(dst_rel)
    src_parent = _open_dir(root, src[:-1])
    try:
        sfd = os.open(src[-1], os.O_RDONLY | O_NOFOLLOW, dir_fd=src_parent)
    finally:
        os.close(src_parent)
    with os.fdopen(sfd, "rb") as source:
        data = source.read()
    parent = _open_dir(root, dst[:-1], create=True)
    tmp = _tmp_name()
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | O_NOFOLLOW,
                     0o600, dir_fd=parent)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(tmp, 0o644, dir_fd=parent)
        os.replace(tmp, dst[-1], src_dir_fd=parent, dst_dir_fd=parent)
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
