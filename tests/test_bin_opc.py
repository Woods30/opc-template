#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bin/opc 入口的沙箱测试：路径、版本、lint 与 install 的基本行为。

跑法：python3 tests/test_bin_opc.py
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPC = ROOT / "bin" / "opc"


class BinOpcTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="bin-opc-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = os.environ.copy()
        self.env.update({
            "HOME": str(self.tmp / "home"),
            "XDG_CONFIG_HOME": str(self.tmp / "config"),
            "XDG_DATA_HOME": str(self.tmp / "data"),
            "HERDR_APP_HOME": str(self.tmp / "herdr-app"),
            "HERDR_CORE_HOME": str(self.tmp / "herdr-core"),
            "OPC_CONFIG_DIR": str(self.tmp / "config" / "opc"),
            "OPC_DATA_DIR": str(self.tmp / "data" / "opc"),
            "OPC_CACHE_DIR": str(self.tmp / "cache" / "opc"),
            "OPC_BIN_DIR": str(self.tmp / "bin"),
            "OPC_GIT_NAME": "opc-test",
            "OPC_GIT_EMAIL": "opc-test@example.invalid",
        })
        for key in ("HOME", "HERDR_APP_HOME", "HERDR_CORE_HOME", "OPC_BIN_DIR"):
            Path(self.env[key]).mkdir(parents=True, exist_ok=True)

    def run_opc(self, *args, check=False):
        return subprocess.run(
            [sys.executable, str(OPC), *args],
            cwd=str(ROOT),
            env=self.env,
            capture_output=True,
            text=True,
            check=check,
        )

    def test_version(self):
        proc = self.run_opc("version")
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertTrue(proc.stdout.startswith("opc 1"))

    def test_paths_stay_in_sandbox(self):
        proc = self.run_opc("paths", "--json")
        self.assertEqual(0, proc.returncode, proc.stderr)
        data = json.loads(proc.stdout)
        sandbox = str(self.tmp.resolve())
        for key, value in data.items():
            self.assertTrue(
                str(Path(value).resolve()).startswith(sandbox),
                "{} 跑出沙箱：{}".format(key, value),
            )

    def test_lint_delegates(self):
        proc = self.run_opc("lint", "--quiet")
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)

    def test_install_dry_run_writes_nothing(self):
        target = self.tmp / "instance"
        proc = self.run_opc(
            "install", str(target), "t", "--template", str(ROOT), "--dry-run")
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertFalse(target.exists())

    def test_install_creates_registry_and_ui(self):
        target = self.tmp / "instance"
        proc = self.run_opc(
            "install", str(target), "t", "--template", str(ROOT),
            "--no-input", "--skip-smoke")
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertTrue((target / ".opc" / "instance.json").is_file())
        self.assertTrue((target / ".opc" / "mechanism.json").is_file())
        self.assertFalse((target / "layouts").exists())
        self.assertTrue((Path(self.env["HERDR_APP_HOME"]) / "layouts" / "opc.json").is_file())
        registry = Path(self.env["OPC_CONFIG_DIR"]) / "instances.json"
        self.assertTrue(registry.is_file())
        data = json.loads(registry.read_text(encoding="utf-8"))
        self.assertEqual(1, len(data["instances"]))
        self.assertEqual("t", data["instances"][0]["prefix"])

    def test_install_splits_mechanism_and_starters(self):
        target = self.tmp / "instance"
        proc = self.run_opc(
            "install", str(target), "t", "--template", str(ROOT),
            "--no-input", "--skip-smoke")
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        mech = json.loads(
            (target / ".opc" / "mechanism.json").read_text(encoding="utf-8"))["files"]
        starters = json.loads(
            (target / ".opc" / "starters.json").read_text(encoding="utf-8"))["files"]
        # 机制指纹只覆盖机制文件
        self.assertNotIn("AGENTS.md", mech)
        self.assertFalse([k for k in mech if k.startswith(("agents/", "skills/"))])
        # 起始材料单独记基线：路径 + SHA-256
        for rel in ("AGENTS.md", "agents/gm/AGENTS.md", "README.md"):
            self.assertIn(rel, starters)
            self.assertEqual(64, len(starters[rel]["sha256"]))
        self.assertTrue((target / "AGENTS.md").is_file())
        self.assertTrue((target / "agents" / "gm" / "AGENTS.md").is_file())

    def test_install_uses_manifest_executable_list(self):
        tpl = self.tmp / "tpl"
        shutil.copytree(str(ROOT / "template"), str(tpl / "template"))
        executables = json.loads(
            (tpl / "template" / "install-manifest.json").read_text(encoding="utf-8")
        )["mechanism"]["executables"]
        for rel in executables:
            (tpl / "template" / rel).chmod(0o644)
        target = self.tmp / "instance"

        proc = self.run_opc(
            "install", str(target), "t", "--template", str(tpl),
            "--no-input", "--skip-smoke")

        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        for rel in executables:
            self.assertTrue(os.access(target / rel, os.X_OK), rel)

    def test_install_refuses_non_empty_target(self):
        target = self.tmp / "instance"
        target.mkdir()
        (target / "keep.txt").write_text("x", encoding="utf-8")
        proc = self.run_opc(
            "install", str(target), "t", "--template", str(ROOT), "--no-input")
        self.assertNotEqual(0, proc.returncode)

    def test_install_rejects_manifest_path_escape(self):
        # 清单里的路径能读出载荷外的文件：绝对路径与 `..` 都要被拒。
        tpl = self.tmp / "tpl"
        shutil.copytree(str(ROOT / "template"), str(tpl / "template"))
        manifest_path = tpl / "template" / "install-manifest.json"
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        data["starters"]["files"].append({
            "source": "../../../etc/passwd", "target": "leak.txt"})
        manifest_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        target = self.tmp / "instance"
        proc = self.run_opc(
            "install", str(target), "t", "--template", str(tpl),
            "--no-input", "--skip-smoke")
        self.assertNotEqual(0, proc.returncode)
        self.assertIn("路径不合法", proc.stdout + proc.stderr)
        self.assertFalse((target / "leak.txt").exists())

    def test_upgrade_does_not_write_through_symlink(self):
        # 实例里的起始材料是软链接且指向实例外：升级不能顺着它改写外部文件。
        target = self.tmp / "instance"
        proc = self.run_opc(
            "install", str(target), "t", "--template", str(ROOT),
            "--no-input", "--skip-smoke")
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        outside = self.tmp / "outside.md"
        outside.write_text("原来的内容\n", encoding="utf-8")
        role_file = target / "agents" / "gm" / "AGENTS.md"
        role_file.unlink()
        role_file.symlink_to(outside)
        self.run_opc("upgrade", str(target), "--template", str(ROOT), "--skip-smoke")
        self.assertEqual("原来的内容\n", outside.read_text(encoding="utf-8"))

    def test_upgrade_does_not_write_through_symlinked_parent(self):
        # 父目录是软链接时，写进去的文件会落在实例外：一律不写。
        target = self.tmp / "instance"
        proc = self.run_opc(
            "install", str(target), "t", "--template", str(ROOT),
            "--no-input", "--skip-smoke")
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        outside = self.tmp / "outside-dir"
        outside.mkdir()
        shutil.rmtree(str(target / "agents"))
        (target / "agents").symlink_to(outside)
        self.run_opc("upgrade", str(target), "--template", str(ROOT), "--skip-smoke")
        self.assertEqual([], sorted(p.name for p in outside.iterdir()))


    # ---- 每角色 CLI 与模型 + 名册注册表 ----

    def install_instance(self, answers=None):
        """装一个实例；answers 非空时走 --answers 路径。"""
        target = self.tmp / "instance"
        argv = ["install", str(target), "t", "--template", str(ROOT),
                "--no-input", "--skip-smoke"]
        if answers is not None:
            path = self.tmp / "answers.json"
            path.write_text(
                json.dumps(answers, ensure_ascii=False), encoding="utf-8")
            argv += ["--answers", str(path)]
        proc = self.run_opc(*argv)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        return target

    def roles_of(self, target):
        data = json.loads((target / "roles.json").read_text(encoding="utf-8"))
        return {r["name"]: r for r in data["roles"]}

    def launcher_of(self, target, role):
        path = target / ".opc" / "run" / (role + ".sh")
        self.assertTrue(path.is_file(), path)
        return path.read_text(encoding="utf-8")

    def test_template_roles_leave_model_empty(self):
        # 模版只定机制，不定模型：每个角色的 model 留空表示用该 CLI 的默认模型。
        data = json.loads(
            (ROOT / "template" / "roles.json").read_text(encoding="utf-8"))
        for role in data["roles"]:
            self.assertIn("model", role, role["name"])
            self.assertEqual("", role["model"], role["name"])

    def test_template_has_no_literal_model_name(self):
        # 模版里不能写死任何具体模型名：模型参数只能是变量。
        pattern = re.compile(r"--model\s+[A-Za-z0-9]|(?<![a-zA-Z])model=\\\\?\"[A-Za-z0-9]")
        for path in (ROOT / "template").rglob("*"):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            hit = pattern.search(text)
            self.assertIsNone(
                hit, "{} 里写死了模型名：{}".format(path, hit.group(0) if hit else ""))

    def test_answers_write_model_into_instance_roles(self):
        target = self.install_instance({
            "roles": {
                "content": {
                    "enabled": True,
                    "cli": "claude",
                    "model": "spec-model-alpha",
                    "permissionMode": "dontAsk",
                }
            }
        })
        roles = self.roles_of(target)
        self.assertEqual("spec-model-alpha", roles["content"]["model"])
        self.assertEqual("dontAsk", roles["content"]["permissionMode"])
        # 没选的角色留空 = 该 CLI 的默认模型
        self.assertEqual("", roles["gm"]["model"])

    def test_answers_with_free_args_are_rejected(self):
        # 自由参数等于给实例内容开一条往启动命令行里塞任意开关的路：不接。
        answers = self.tmp / "answers-args.json"
        answers.write_text(json.dumps({
            "roles": {"content": {"args": ["--dangerously-skip-permissions"]}}
        }, ensure_ascii=False), encoding="utf-8")
        proc = self.run_opc(
            "install", str(self.tmp / "instance"), "t", "--template", str(ROOT),
            "--no-input", "--skip-smoke", "--answers", str(answers))
        self.assertNotEqual(0, proc.returncode)
        self.assertIn("args", proc.stdout + proc.stderr)

    def test_hand_written_role_args_never_reach_the_launcher(self):
        # 实例里手写的 args 字段不生效：启动参数只由模版算出。
        target = self.install_instance()
        path = target / "roles.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for role in data["roles"]:
            if role["name"] == "content":
                role["args"] = ["--dangerously-skip-permissions"]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        proc = subprocess.run(
            ["bash", str(target / "scripts" / "opc-install.sh"),
             "--no-input", "t", "--skip-smoke"],
            cwd=str(target), env=self.env, capture_output=True, text=True)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertNotIn("--dangerously-skip-permissions",
                         self.launcher_of(target, "content"))
        self.assertIn("args", proc.stderr)

    def test_launcher_composes_model_args_per_cli(self):
        target = self.install_instance({
            "roles": {
                "content": {
                    "enabled": True,
                    "cli": "claude",
                    "model": "spec-model-alpha",
                    "permissionMode": "dontAsk",
                },
                "growth": {
                    "enabled": True,
                    "cli": "codex",
                    "model": "spec-model-beta",
                    "permissionMode": "dontAsk",
                },
            }
        })
        claude_launcher = self.launcher_of(target, "content")
        self.assertIn("--model spec-model-alpha", claude_launcher)
        self.assertIn("--permission-mode dontAsk", claude_launcher)

        codex_launcher = self.launcher_of(target, "growth")
        # Codex 用配置覆盖写模型，并且必须带独立运行开关
        self.assertIn("-c model=", codex_launcher)
        self.assertIn("spec-model-beta", codex_launcher)
        self.assertIn("--no-daemon", codex_launcher)

    def test_install_without_model_uses_cli_default(self):
        target = self.install_instance()
        for role in ("gm", "content", "growth", "dev"):
            launcher = self.launcher_of(target, role)
            self.assertNotIn("--model ", launcher, role)
            self.assertNotIn("-c model=", launcher, role)
        self.assertEqual("", self.roles_of(target)["gm"]["model"])

    def test_upgrade_keeps_model_and_tolerates_missing_model(self):
        target = self.install_instance({
            "roles": {"content": {"enabled": True, "cli": "claude",
                                 "model": "spec-model-alpha"}}
        })
        proc = self.run_opc("upgrade", str(target), "--template", str(ROOT),
                            "--skip-smoke")
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertEqual("spec-model-alpha", self.roles_of(target)["content"]["model"])
        self.assertIn("--model spec-model-alpha", self.launcher_of(target, "content"))

        # 旧实例的角色配置没有 model 字段：照样能升级，按默认模型跑。
        path = target / "roles.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for role in data["roles"]:
            role.pop("model", None)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        proc = self.run_opc("upgrade", str(target), "--template", str(ROOT),
                            "--skip-smoke")
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertNotIn("--model ", self.launcher_of(target, "content"))
        self.assertNotIn("-c model=", self.launcher_of(target, "content"))

    def test_lib_dispatches_model_args_per_cli(self):
        lib = ROOT / "template" / "scripts" / "lib.sh"
        def call(expr):
            proc = subprocess.run(
                ["bash", "-c", '. "%s" >/dev/null 2>&1; %s' % (lib, expr)],
                capture_output=True, text=True, check=False)
            self.assertEqual(0, proc.returncode, proc.stderr)
            return proc.stdout.strip()
        self.assertEqual("--model spec-model-alpha",
                         call("opc_cli_model_args claude spec-model-alpha"))
        self.assertIn("-c model=", call("opc_cli_model_args codex spec-model-alpha"))
        self.assertEqual("", call("opc_cli_model_args claude ''"))
        self.assertEqual("--no-daemon", call("opc_cli_required_args codex"))
        self.assertEqual("", call("opc_cli_required_args claude"))
        # Codex 角色的默认权限档是「不弹窗、保留沙箱」：不审批，但不掉沙箱。
        self.assertEqual("dontAsk",
                         call("opc_cli_default_permission_mode codex"))
        # 任何档位都不许把 codex 的沙箱整个关掉：那个开关只在外部已沙箱化
        # 的环境里成立，OPC 实例不是。
        for mode in call("opc_cli_permission_modes codex").split():
            args = call("opc_cli_permission_args codex %s" % mode)
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", args)
        self.assertIn("--ask-for-approval never",
                      call("opc_cli_permission_args codex bypassPermissions"))

    def test_interactive_install_asks_cli_and_model(self):
        # 交互式安装要能逐角色选 CLI 与模型：模型清单拿不到时允许手填模型名。
        bindir = self.tmp / "bin"
        bindir.mkdir(parents=True, exist_ok=True)
        for name in ("claude", "codex"):
            stub = bindir / name
            stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            stub.chmod(0o755)
        env = dict(self.env)
        env["PATH"] = "{}:{}".format(bindir, env.get("PATH", ""))

        target = self.tmp / "instance"
        proc = subprocess.run(
            [sys.executable, str(OPC), "install", str(target), "t",
             "--template", str(ROOT), "--interactive", "--skip-smoke"],
            cwd=str(ROOT), env=env, capture_output=True, text=True, check=False,
            # 逐角色：启用？→ 用哪个 CLI？；最后再逐个问模型。
            input="y\n1\ny\n1\nn\nn\nspec-model-alpha\nspec-model-beta\n")
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        roles = self.roles_of(target)
        self.assertEqual("spec-model-alpha", roles["gm"]["model"])
        self.assertEqual("spec-model-beta", roles["content"]["model"])
        self.assertIn("--model spec-model-alpha", self.launcher_of(target, "gm"))

    def test_team_md_is_registry(self):
        target = self.install_instance({
            "roles": {"content": {"enabled": True, "cli": "claude",
                                 "model": "spec-model-alpha"}}
        })
        text = (target / "knowledge" / "team.md").read_text(encoding="utf-8")
        for column in ("角色", "终端名", "启动器", "HC 模板名", "所在 tab",
                       "CLI", "模型", "权限模式", "负责的子树"):
            self.assertIn(column, text)
        # 模型为空写「默认模型」，不留空字段
        self.assertIn("默认模型", text)
        self.assertIn("spec-model-alpha", text)
        # 委派由编排者按注册表发起；旧的「按名册终端名发通知」退休
        self.assertIn("委派", text)
        self.assertIn("编排者", text)
        self.assertNotIn("hc send <终端名>", text)
        # 边界与读屏约定保留
        self.assertIn("只有名册里的角色终端才属于本实例", text)
        self.assertIn("不用地址形式", text)
        # 每个角色一行，列出 CLI、模型与权限模式
        for role in ("gm", "content", "growth", "dev"):
            self.assertIn(role, text)

    def test_install_creates_task_dir(self):
        target = self.install_instance()
        self.assertTrue((target / "knowledge" / "tasks").is_dir())


if __name__ == "__main__":
    unittest.main()
