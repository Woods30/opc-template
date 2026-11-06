#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bin/opc 入口的沙箱测试：路径、版本、lint 与 install 的基本行为。

跑法：python3 tests/test_bin_opc.py
"""

import json
import os
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

    def test_install_refuses_non_empty_target(self):
        target = self.tmp / "instance"
        target.mkdir()
        (target / "keep.txt").write_text("x", encoding="utf-8")
        proc = self.run_opc(
            "install", str(target), "t", "--template", str(ROOT), "--no-input")
        self.assertNotEqual(0, proc.returncode)


if __name__ == "__main__":
    unittest.main()
