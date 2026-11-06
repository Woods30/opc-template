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
