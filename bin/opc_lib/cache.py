"""模版来源：显式路径、开发副本或全局缓存；缓存负责自动拉取最新。"""

import os
import shutil
import sys
from pathlib import Path

from . import gitutil, paths
from .errors import OpcError

FALLBACK_REMOTE = "https://github.com/Woods30/opc-template.git"


def _valid_template(root):
    return (Path(root) / "template" / "install-manifest.json").is_file()


def remote_url(repo_root):
    explicit = os.environ.get("OPC_TEMPLATE_REMOTE")
    if explicit:
        return explicit.strip()
    marker = Path(repo_root) / ".opc-template-remote"
    if marker.is_file():
        value = marker.read_text(encoding="utf-8").strip()
        if value:
            return value
    if (Path(repo_root) / ".git").exists():
        proc = gitutil.run(repo_root, "remote", "get-url", "origin", check=False)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    return FALLBACK_REMOTE


def resolve(args):
    """返回 (模版仓库根, 上游地址)。可能 re-exec 到缓存里的新版本。"""
    explicit = getattr(args, "template", None) or os.environ.get("OPC_TEMPLATE")
    if explicit:
        root = paths.as_path(explicit)
        if not _valid_template(root):
            raise OpcError("模版路径无效（缺 template/install-manifest.json）：{}".format(root))
        return root, remote_url(root)

    cache = paths.cache_dir()
    entry = cache / "bin" / "opc"
    fallback = paths.repo_root_from_script()

    if not entry.is_file():
        if not _clone(cache, remote_url(fallback)):
            if _valid_template(fallback):
                print("提示：拉取模版缓存失败，改用当前副本：{}".format(fallback), file=sys.stderr)
                return fallback, remote_url(fallback)
            raise OpcError("拉取模版缓存失败：{}".format(cache))

    if not _valid_template(cache):
        if _valid_template(fallback) and fallback.resolve() != cache.resolve():
            print("提示：模版缓存不完整，改用当前副本：{}".format(fallback), file=sys.stderr)
            return fallback, remote_url(fallback)
        raise OpcError("模版缓存损坏：{}（可删除后重跑）".format(cache))

    if getattr(args, "no_pull", False):
        return cache, remote_url(cache)

    if os.environ.get("OPC_CACHE_READY") != "1":
        _refresh(cache)
        current = fallback.resolve()
        try:
            running_from_cache = current == cache.resolve()
        except OSError:
            running_from_cache = False
        if not running_from_cache and entry.is_file():
            env = os.environ.copy()
            env["OPC_CACHE_READY"] = "1"
            os.execve(sys.executable, [sys.executable, str(entry.resolve())] + sys.argv[1:], env)

    return cache, remote_url(cache)


def _clone(cache, remote):
    cache = Path(cache)
    cache.parent.mkdir(parents=True, exist_ok=True)
    if cache.exists() and any(cache.iterdir()):
        return False
    proc = gitutil.run(cache.parent, "clone", "--quiet", remote, str(cache), check=False)
    return proc.returncode == 0 and _valid_template(cache)


def _refresh(cache):
    if not gitutil.is_repo(cache):
        raise OpcError("模版缓存不是 git 仓库：{}".format(cache))
    fetched = gitutil.run(cache, "fetch", "--quiet", "origin", check=False)
    if fetched.returncode != 0:
        print("提示：模版拉取失败，继续使用缓存版本。（{}）".format(
            (fetched.stderr or "").strip().splitlines()[-1:] or ""), file=sys.stderr)
        return False
    for ref in ("origin/main", "origin/HEAD"):
        verify = gitutil.run(cache, "rev-parse", "--verify", "--quiet", ref, check=False)
        if verify.returncode == 0:
            merged = gitutil.run(cache, "merge", "--ff-only", "--quiet", ref, check=False)
            if merged.returncode != 0:
                raise OpcError(
                    "模版缓存无法快进到 {}，可能被本地改动过：{}\n"
                    "删除缓存后重跑：{}".format(
                        ref, (merged.stderr or merged.stdout or "").strip(), cache))
            return True
    print("提示：缓存找不到 origin/main，继续使用当前版本。", file=sys.stderr)
    return False


def ensure_global_command(template_root):
    """把 bin/opc 链到 ~/.local/bin/opc；不覆盖用户自己的同名文件。"""
    template_root = Path(template_root)
    # 全局命令优先指向缓存副本：开发副本可能随时被删除或改动。
    cached = paths.cache_dir() / "bin" / "opc"
    if cached.is_file() and _valid_template(paths.cache_dir()):
        source = cached.resolve()
    else:
        source = (template_root / "bin" / "opc").resolve()
    if not source.is_file():
        return None
    target = paths.bin_dir() / "opc"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        try:
            if target.resolve() == source:
                return target
        except OSError:
            pass
        if not target.is_symlink():
            print("提示：{} 已存在且不是符号链接，未覆盖。".format(target), file=sys.stderr)
            return target
    tmp = target.with_name(target.name + ".tmp")
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    tmp.symlink_to(source)
    os.replace(tmp, target)
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    if str(paths.bin_dir()) not in path_dirs:
        print("提示：{} 不在 PATH 里，把下面这行加进 shell 配置：\n"
              "  export PATH=\"{}:$PATH\"".format(paths.bin_dir(), paths.bin_dir()),
              file=sys.stderr)
    return target


def discard_cache_warning(cache):
    if shutil.which("git") is None:
        print("提示：没有 git，模版缓存不会自动更新。", file=sys.stderr)
