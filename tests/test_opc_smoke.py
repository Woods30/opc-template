#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""template/tools/opc-smoke 的测试。标准库 unittest，不依赖外部包。

跑法：
    python3 tests/test_opc_smoke.py
    python3 -m unittest discover -s tests -t . -v
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
SMOKE = ROOT / "template" / "tools" / "opc-smoke"


def run_smoke(cwd, *args):
    # 跑实例里那一份：工具的根目录由脚本位置决定，跑仓库那份等于在测模版。
    tool = Path(cwd) / "tools" / "opc-smoke"
    return subprocess.run(
        [sys.executable, str(tool), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )


class SmokeTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="opc-smoke-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.instance = Path(self.tmp) / "instance"
        (self.instance / "tools").mkdir(parents=True)
        (self.instance / ".opc").mkdir(parents=True)
        (self.instance / ".opc" / "instance.json").write_text(
            json.dumps({"kind": "opc-instance", "version": 1}), encoding="utf-8")
        shutil.copy2(SMOKE, self.instance / "tools" / "opc-smoke")
        (self.instance / "tools" / "opc-smoke").chmod(0o755)

    def install_workflow(self, text=None):
        target = self.instance / "tools" / "opc-workflow"
        if text is None:
            shutil.copy2(ROOT / "template" / "tools" / "opc-workflow", target)
        else:
            target.write_text(text, encoding="utf-8")
        target.chmod(0o755)
        return target

    # ---- 正常路径 ----

    def test_smoke_passes_with_a_healthy_toolchain(self):
        self.install_workflow()
        result = run_smoke(self.instance)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("通过", result.stdout)

    def test_smoke_json_output_is_machine_readable(self):
        self.install_workflow()
        result = run_smoke(self.instance, "--json")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertGreater(payload["steps"], 0)

    def test_smoke_does_not_write_into_the_instance(self):
        # 冒烟只读实例的工具，业务数据一律落在临时目录里。
        self.install_workflow()
        before = sorted(p.name for p in (self.instance / "knowledge").glob("*")) \
            if (self.instance / "knowledge").exists() else []
        result = run_smoke(self.instance)
        self.assertEqual(0, result.returncode, result.stderr)
        after = sorted(p.name for p in (self.instance / "knowledge").glob("*")) \
            if (self.instance / "knowledge").exists() else []
        self.assertEqual(before, after)

    def test_smoke_leaves_no_temporary_directory_behind(self):
        self.install_workflow()
        result = run_smoke(self.instance)
        self.assertEqual(0, result.returncode, result.stderr)
        leftovers = [p.name for p in Path(tempfile.gettempdir()).glob("opc-smoke-*")
                     if not p.name.startswith("opc-smoke-test-")]
        self.assertEqual([], leftovers)

    # ---- 角色环境 ----

    def test_smoke_passes_when_the_parent_process_carries_a_role(self):
        # 角色终端里 OPC_ROLE 由启动器导出，冒烟必须能在这种环境下跑通：
        # 脚本用多个 actor 连调工作流，继承下来的角色会污染每一步。
        self.install_workflow()
        env = dict(os.environ)
        env["OPC_ROLE"] = "gm"
        tool = self.instance / "tools" / "opc-smoke"
        result = subprocess.run(
            [sys.executable, str(tool)],
            cwd=str(self.instance),
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("通过", result.stdout)

    def test_smoke_keeps_other_environment_variables(self):
        # 只隔离角色变量，其余环境变量照常继承——别的工具靠它们定位实例。
        self.install_workflow()
        env = dict(os.environ)
        env["OPC_ROLE"] = "gm"
        env["OPC_TEST_MARKER"] = "kept"
        tool = self.instance / "tools" / "opc-smoke"
        result = subprocess.run(
            [sys.executable, str(tool), "--json"],
            cwd=str(self.instance),
            capture_output=True,
            text=True,
            env=env,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_keep_really_keeps_the_temporary_directory(self):
        self.install_workflow()
        result = run_smoke(self.instance, "--keep", "--json")
        self.assertEqual(0, result.returncode, result.stderr)
        kept = json.loads(result.stdout).get("kept_dir")
        self.assertTrue(kept, "冒烟没报告保留的临时目录")
        self.assertTrue(Path(kept).is_dir(), "保留的临时目录不存在")
        self.addCleanup(shutil.rmtree, kept, True)

    def test_smoke_finds_the_instance_root_from_another_directory(self):
        # 脚本不在 <实例>/tools/ 下时也要能定位实例根（提案目录里评审用）。
        self.install_workflow()
        elsewhere = self.instance / "knowledge" / "work" / "dev" / "tools"
        elsewhere.mkdir(parents=True, exist_ok=True)
        tool = elsewhere / "opc-smoke"
        shutil.copy2(self.instance / "tools" / "opc-smoke", tool)
        tool.chmod(0o755)
        result = subprocess.run(
            [sys.executable, str(tool)],
            cwd=str(self.instance),
            capture_output=True,
            text=True,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("通过", result.stdout)

    # ---- 失败路径 ----

    def test_missing_workflow_is_reported_not_crashed(self):
        result = run_smoke(self.instance)
        self.assertEqual(1, result.returncode)
        self.assertIn("冒烟失败", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_broken_workflow_is_reported_not_crashed(self):
        # 工具坏了也要说人话：不能甩 traceback 给人看。
        self.install_workflow(text="#!/usr/bin/env python3\nraise SystemExit(3)\n")
        result = run_smoke(self.instance)
        self.assertEqual(1, result.returncode)
        self.assertIn("冒烟失败", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_broken_workflow_json_output_still_parses(self):
        self.install_workflow(text="#!/usr/bin/env python3\nraise SystemExit(3)\n")
        result = run_smoke(self.instance, "--json")
        self.assertEqual(1, result.returncode)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["error"])


if __name__ == "__main__":
    unittest.main()
