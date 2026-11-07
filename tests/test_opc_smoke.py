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
WORKFLOW = ROOT / "template" / "tools" / "opc-workflow"

# 记录每次调用看到的环境，再把真正的工作流跑起来。测试用它看清「每一步
# 各自构造环境」到底长什么样——只看退出码看不出角色变量有没有被换掉。
RECORDING_WORKFLOW = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试替身：记下本次调用看到的环境，再执行真正的工作流。"""
import json
import os
import sys

log = os.environ.get("OPC_SMOKE_TEST_LOG")
if log:
    record = {
        "args": sys.argv[1:],
        "has_role": "OPC_ROLE" in os.environ,
        "role": os.environ.get("OPC_ROLE"),
        "marker": os.environ.get("OPC_TEST_MARKER"),
    }
    with open(log, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\\n")

real = os.environ["OPC_SMOKE_TEST_REAL_WORKFLOW"]
with open(real, encoding="utf-8") as handle:
    source = handle.read()
# __file__ 保持替身自己的位置：工作流靠它推导根目录。
exec(compile(source, real, "exec"), {"__name__": "__main__", "__file__": __file__})
'''


def run_smoke(cwd, *args, env=None):
    # 跑实例里那一份：工具的根目录由脚本位置决定，跑仓库那份等于在测模版。
    tool = Path(cwd) / "tools" / "opc-smoke"
    return subprocess.run(
        [sys.executable, str(tool), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
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
            shutil.copy2(WORKFLOW, target)
        else:
            target.write_text(text, encoding="utf-8")
        target.chmod(0o755)
        return target

    def install_recording_workflow(self):
        """装一份会记下环境的工作流替身，用来看清每一步各自的环境。"""
        return self.install_workflow(text=RECORDING_WORKFLOW)

    def recording_env(self, log, **extra):
        env = dict(os.environ)
        env["OPC_SMOKE_TEST_LOG"] = str(log)
        env["OPC_SMOKE_TEST_REAL_WORKFLOW"] = str(WORKFLOW)
        env.update(extra)
        return env

    def read_log(self, log):
        if not log.exists():
            return []
        return [json.loads(line) for line in
                log.read_text(encoding="utf-8").splitlines() if line.strip()]

    def kept_dir_from(self, text):
        """从输出里取出保留的临时目录路径；没打印就是没报。"""
        if "保留临时目录：" not in text:
            return None
        return text.split("保留临时目录：", 1)[1].strip()

    def keep_env(self):
        """把保留的临时目录放到用例自己的沙箱里，清理不牵连共享目录。"""
        sandbox = Path(self.tmp) / "kept"
        sandbox.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        env["TMPDIR"] = str(sandbox)
        return env

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
        temp = Path(tempfile.gettempdir())
        before = set(temp.glob("opc-smoke-*"))
        result = run_smoke(self.instance)
        self.assertEqual(0, result.returncode, result.stderr)
        # 比「跑之前」多出来的目录：别的用例留下的残留不算冒烟的锅。
        leftovers = sorted(path.name for path in set(temp.glob("opc-smoke-*")) - before)
        self.assertEqual([], leftovers)

    # ---- 角色环境 ----

    def test_smoke_passes_when_the_parent_process_carries_a_role(self):
        # 角色终端里 OPC_ROLE 由启动器导出，冒烟必须能在这种环境下跑通：
        # 脚本用多个 actor 连调工作流，继承下来的角色会污染每一步。
        self.install_workflow()
        env = dict(os.environ)
        env["OPC_ROLE"] = "gm"
        result = run_smoke(self.instance, env=env)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("通过", result.stdout)

    def test_smoke_keeps_other_environment_variables(self):
        # 只隔离角色变量，其余环境变量照常继承——别的工具靠它们定位实例。
        self.install_workflow()
        env = dict(os.environ)
        env["OPC_ROLE"] = "gm"
        env["OPC_TEST_MARKER"] = "kept"
        result = run_smoke(self.instance, "--json", env=env)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])

    def test_every_step_runs_under_its_own_actor(self):
        # 每一步都写入本步自己的 actor：工作流那道「不得冒充其他角色」的防线
        # 得真的被走到，而不是靠把角色变量删掉绕过去。
        self.install_recording_workflow()
        log = Path(self.tmp) / "calls.jsonl"
        env = self.recording_env(log, OPC_ROLE="gm", OPC_TEST_MARKER="kept")
        result = run_smoke(self.instance, env=env)
        self.assertEqual(0, result.returncode, result.stderr)
        records = self.read_log(log)
        self.assertTrue(records, "工作流一次都没被调用")
        for record in records:
            args = record["args"]
            if "--actor" in args:
                actor = args[args.index("--actor") + 1]
                self.assertTrue(record["has_role"], "带 actor 的步骤没设 OPC_ROLE")
                self.assertEqual(actor, record["role"],
                                 "步骤的 OPC_ROLE 不是本步自己的 actor")
            else:
                self.assertFalse(record["has_role"],
                                 "不带 actor 的步骤不该设 OPC_ROLE")
            self.assertEqual("kept", record["marker"], "其余环境变量没被继承")

    def test_keep_really_keeps_the_temporary_directory(self):
        self.install_workflow()
        result = run_smoke(self.instance, "--keep", "--json", env=self.keep_env())
        self.assertEqual(0, result.returncode, result.stderr)
        kept = json.loads(result.stdout).get("kept_dir")
        self.assertTrue(kept, "冒烟没报告保留的临时目录")
        self.assertTrue(Path(kept).is_dir(), "保留的临时目录不存在")

    def test_keep_prints_the_kept_directory_in_plain_output(self):
        self.install_workflow()
        result = run_smoke(self.instance, "--keep", env=self.keep_env())
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("保留临时目录", result.stdout)
        kept = self.kept_dir_from(result.stdout)
        self.assertTrue(kept, "输出里没打印保留的临时目录")
        self.assertTrue(Path(kept).is_dir(), "打印的临时目录不存在")

    def test_keep_keeps_and_reports_the_scene_when_the_smoke_fails(self):
        # 保留参数最要紧的用处是排查失败：目录得留着，路径也得说出来。
        self.install_workflow(text="#!/usr/bin/env python3\nraise SystemExit(3)\n")
        result = run_smoke(self.instance, "--keep", env=self.keep_env())
        self.assertEqual(1, result.returncode)
        self.assertIn("冒烟失败", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        kept = self.kept_dir_from(result.stderr)
        self.assertTrue(kept, "失败时没打印保留的临时目录")
        self.assertTrue(Path(kept).is_dir(), "失败后保留的临时目录不存在")

    def test_keep_reports_the_kept_directory_in_json_on_failure(self):
        self.install_workflow(text="#!/usr/bin/env python3\nraise SystemExit(3)\n")
        result = run_smoke(self.instance, "--keep", "--json", env=self.keep_env())
        self.assertEqual(1, result.returncode)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["ok"])
        kept = payload.get("kept_dir")
        self.assertTrue(kept, "失败时 JSON 里没报保留的临时目录")
        self.assertTrue(Path(kept).is_dir(), "失败后保留的临时目录不存在")

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

    def test_smoke_finds_the_instance_root_when_the_tool_sits_outside_it(self):
        # 工具被拷到实例外面时，靠当前工作目录认出实例根。
        self.install_workflow()
        outside = Path(self.tmp) / "outside"
        outside.mkdir(parents=True, exist_ok=True)
        tool = outside / "opc-smoke"
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

    def test_missing_instance_root_is_reported_not_crashed(self):
        # 找不到实例根也要说人话，不能甩 traceback。
        outside = Path(self.tmp) / "nowhere"
        outside.mkdir(parents=True, exist_ok=True)
        tool = outside / "opc-smoke"
        shutil.copy2(self.instance / "tools" / "opc-smoke", tool)
        tool.chmod(0o755)
        result = subprocess.run(
            [sys.executable, str(tool)],
            cwd=str(outside),
            capture_output=True,
            text=True,
        )
        self.assertEqual(1, result.returncode)
        self.assertIn("冒烟失败", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_explicit_instance_root_wins_over_the_search(self):
        self.install_workflow()
        result = run_smoke(self.instance, "--instance-root", str(self.instance))
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("通过", result.stdout)

    def test_automatic_root_requires_both_instance_marker_and_workflow(self):
        result = run_smoke(self.instance)

        self.assertEqual(1, result.returncode)
        self.assertIn("找不到实例根", result.stderr)
        self.assertNotIn("实例里缺少 tools/opc-workflow", result.stderr)

    def test_explicit_root_requires_both_instance_marker_and_workflow(self):
        workflow_only = Path(self.tmp) / "workflow-only"
        (workflow_only / "tools").mkdir(parents=True)
        shutil.copy2(WORKFLOW, workflow_only / "tools" / "opc-workflow")

        result = run_smoke(
            self.instance,
            "--instance-root",
            str(workflow_only),
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("不是完整 OPC 实例根", result.stderr)
        self.assertIn(".opc/instance.json", result.stderr)
        self.assertIn("tools/opc-workflow", result.stderr)

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
