"""git 封装：限定 pathspec 的提交、脏文件检测、首次添加提交查找。"""

import os
import subprocess
from pathlib import Path

from .errors import OpcError


def _env():
    env = os.environ.copy()
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    return env


def run(repo, *args, check=True, capture=True):
    cmd = ["git", "-C", str(repo)] + [str(a) for a in args]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=capture,
            text=True,
            env=_env(),
        )
    except FileNotFoundError:
        raise OpcError("找不到 git 命令")
    if check and proc.returncode != 0:
        message = (proc.stderr or proc.stdout or "").strip()
        raise OpcError("git 失败：{}\n{}".format(" ".join(cmd), message))
    return proc


def is_repo(path):
    path = Path(path)
    if not (path / ".git").exists():
        return False
    proc = run(path, "rev-parse", "--is-inside-work-tree", check=False)
    return proc.returncode == 0


def head_commit(repo):
    proc = run(repo, "rev-parse", "HEAD", check=False)
    if proc.returncode != 0:
        return "unknown"
    return proc.stdout.strip()


def identity_args(template_repo=None):
    name = os.environ.get("OPC_GIT_NAME")
    email = os.environ.get("OPC_GIT_EMAIL")
    if template_repo:
        if not name:
            proc = run(template_repo, "config", "user.name", check=False)
            if proc.returncode == 0:
                name = proc.stdout.strip()
        if not email:
            proc = run(template_repo, "config", "user.email", check=False)
            if proc.returncode == 0:
                email = proc.stdout.strip()
    name = name or os.environ.get("USER") or "opc"
    email = email or "{}@localhost".format(name)
    return ["-c", "user.name={}".format(name), "-c", "user.email={}".format(email)]


def _path_exists_or_tracked(repo, path):
    repo = Path(repo)
    if (repo / path).exists():
        return True
    proc = run(repo, "ls-files", "--", path, check=False)
    return bool(proc.stdout.strip())


def commit_paths(repo, paths, message, template_repo=None):
    """只提交给定路径；无关的脏文件保持不动。返回是否产生提交。"""
    repo = Path(repo)
    if not is_repo(repo):
        return False
    valid = [p for p in paths if p and _path_exists_or_tracked(repo, p)]
    if not valid:
        return False
    run(repo, "add", "-A", "--", *valid)
    staged = run(repo, "diff", "--cached", "--name-only", "--", *valid, check=False)
    if not staged.stdout.strip():
        return False
    ident = identity_args(template_repo)
    run(repo, *ident, "commit", "-m", message, "--", *valid)
    return True


def dirty_paths(repo, paths):
    repo = Path(repo)
    if not is_repo(repo):
        return []
    existing = [p for p in paths if (repo / p).exists()]
    if not existing:
        return []
    proc = run(repo, "status", "--porcelain", "--", *existing, check=False)
    return [line for line in proc.stdout.splitlines() if line.strip()]


def first_add_commit(repo, rel):
    proc = run(repo, "log", "--diff-filter=A", "--format=%H", "--", rel, check=False)
    if proc.returncode != 0:
        return None
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    return lines[-1] if lines else None


def show_file(repo, commit, rel):
    proc = run(repo, "show", "{}:{}".format(commit, rel), check=False, capture=True)
    if proc.returncode != 0:
        return None
    return proc.stdout
