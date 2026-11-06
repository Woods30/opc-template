"""命令行入口。"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import cache, install as install_mod, manifest as manifest_mod, paths, registry, ui, upgrade
from .errors import OpcError


def _common(parser, template=True):
    if template:
        parser.add_argument("--template", help="模版路径（默认用全局缓存或 OPC_TEMPLATE）")
    parser.add_argument("--no-pull", action="store_true", help="不自动拉取最新模版")
    return parser


def build_parser():
    parser = argparse.ArgumentParser(prog="opc", description="OPC 模版：install 与 upgrade")
    parser.add_argument("--version", action="version", version="opc 1")
    sub = parser.add_subparsers(dest="command", required=True)

    p = _common(sub.add_parser("install", help="创建一个新实例"))
    p.add_argument("target", help="实例目录（必须为空）")
    p.add_argument("prefix", nargs="?", help="实例前缀")
    p.add_argument("--prefix", dest="prefix_opt")
    p.add_argument("--answers", help="问答结果 JSON（/opc-init 用）")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--interactive", action="store_true", help="安装时逐个选角色与 CLI")
    p.add_argument("--no-input", action="store_true", help="不提问（默认行为，保留兼容）")
    p.add_argument("--no-git", action="store_true")
    p.add_argument("--skip-smoke", action="store_true")
    p.add_argument("--force-ui", action="store_true", help="覆盖全局 UI 的本地修改")

    p = _common(sub.add_parser("upgrade", help="升级实例或全部实例"))
    p.add_argument("instance", nargs="?", help="实例目录（默认当前目录）")
    p.add_argument("--all", action="store_true", help="升级注册表里的全部实例")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force-mechanism", action="store_true", help="覆盖被本地修改的机制文件")
    p.add_argument("--force-ui", action="store_true")
    p.add_argument("--yes", action="store_true", help="迁移时不再询问")
    p.add_argument("--skip-smoke", action="store_true")

    sub.add_parser("ls", help="列出注册表中的实例")

    p = sub.add_parser("paths", help="打印全局路径（测试与排查用）")
    p.add_argument("--json", action="store_true")

    p = _common(sub.add_parser("lint", help="跑模版自检"), template=False)
    p.add_argument("--strict", action="store_true")
    p.add_argument("--json", action="store_true", help="输出 JSON")
    p.add_argument("--quiet", action="store_true", help="只输出失败项")
    p.add_argument("--private-words", default=None, help="私词表文件路径")
    p.add_argument("--root", default=None, help="仓库根，默认当前目录")

    sub.add_parser("version", help="打印模版版本")
    return parser


def _paths_dict():
    return {
        "config": str(paths.config_dir()),
        "data": str(paths.data_dir()),
        "cache": str(paths.cache_dir()),
        "bin": str(paths.bin_dir()),
        "herdr_app_home": str(paths.herdr_app_home()),
        "herdr_core_home": str(paths.herdr_core_home()),
        "registry": str(paths.registry_path()),
        "ui_state": str(paths.ui_state_path()),
    }


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "install" and getattr(args, "prefix_opt", None):
        args.prefix = args.prefix_opt
    try:
        if args.command == "install":
            template_root, upstream = cache.resolve(args)
            args.upstream = upstream
            manifest = manifest_mod.load(template_root)
            return install_mod.install(template_root, manifest, args)

        if args.command == "upgrade":
            template_root, upstream = cache.resolve(args)
            args.upstream = upstream
            manifest = manifest_mod.load(template_root)
            if args.all:
                return upgrade.upgrade_all(template_root, manifest, args)
            instance = args.instance or str(Path.cwd())
            return upgrade.upgrade_one(template_root, manifest, args, instance)

        if args.command == "ls":
            data = registry.load()
            if not data["instances"]:
                print("（注册表为空）")
                return 0
            for item in data["instances"]:
                mark = "" if Path(item["path"]).is_dir() else "  [目录不存在]"
                print("{}  {}  {}{}".format(
                    item.get("prefix", "?"), item.get("path", "?"),
                    (item.get("template") or {}).get("commit", "")[:12], mark))
            return 0

        if args.command == "paths":
            data = _paths_dict()
            if args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                for key, value in data.items():
                    print("{}: {}".format(key, value))
            return 0

        if args.command == "lint":
            root = Path(args.root).expanduser().resolve() if args.root else paths.repo_root_from_script()
            tool = manifest_mod.payload_root(root) / "tools" / "opc-lint"
            if not tool.is_file():
                raise OpcError("找不到 tools/opc-lint：{}".format(tool))
            cmd = [sys.executable, str(tool), "--root", str(root)]
            if args.strict:
                cmd.append("--strict")
            if args.json:
                cmd.append("--json")
            if args.quiet:
                cmd.append("--quiet")
            if args.private_words:
                cmd.extend(["--private-words", args.private_words])
            return subprocess.run(cmd, cwd=str(root)).returncode

        if args.command == "version":
            root = paths.repo_root_from_script()
            version = "1"
            path = manifest_mod.manifest_path(root)
            if path.is_file():
                version = str(manifest_mod.load(root).get("version", "1"))
            from . import gitutil
            print("opc {}  ({})".format(version, gitutil.head_commit(root)[:12]))
            return 0
    except OpcError as exc:
        print(exc.message, file=sys.stderr)
        return exc.code
    except KeyboardInterrupt:
        return 130
    return 0
