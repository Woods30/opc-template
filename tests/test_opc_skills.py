#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安装与升级对角色所选技能的校验回归。"""

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


class OpcSkillsTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="opc-skills-test-"))
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

    def run_opc(self, *args):
        return subprocess.run(
            [sys.executable, str(OPC), *args], cwd=str(ROOT), env=self.env,
            capture_output=True, text=True)

    def template_copy(self):
        root = self.tmp / "template-copy"
        shutil.copytree(ROOT / "template", root / "template")
        return root

    def install(self, target, template=ROOT):
        return self.run_opc(
            "install", str(target), "t", "--template", str(template),
            "--no-input", "--skip-smoke")

    def test_missing_selected_skill_warns_and_is_omitted(self):
        template = self.template_copy()
        shutil.rmtree(template / "template" / "skills" / "knowledge-writing")
        target = self.tmp / "instance"

        proc = self.install(target, template)

        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("角色 gm 选中的技能已跳过：knowledge-writing", proc.stderr)
        rendered = (Path(self.env["HERDR_CORE_HOME"]) / "templates" / "t-gm.md").read_text(
            encoding="utf-8")
        self.assertNotIn("- knowledge-writing —", rendered)

    def test_invalid_frontmatter_fails_install(self):
        template = self.template_copy()
        skill = template / "template" / "skills" / "knowledge-writing" / "SKILL.md"
        skill.write_text("# 没有 frontmatter\n", encoding="utf-8")

        proc = self.install(self.tmp / "instance", template)

        self.assertNotEqual(0, proc.returncode)
        self.assertIn("角色 gm 的技能 knowledge-writing 不合法", proc.stderr)
        self.assertIn("frontmatter", proc.stderr)

    def test_frontmatter_name_mismatch_fails_install(self):
        template = self.template_copy()
        skill = template / "template" / "skills" / "knowledge-writing" / "SKILL.md"
        text = skill.read_text(encoding="utf-8").replace(
            "name: knowledge-writing", "name: other", 1)
        skill.write_text(text, encoding="utf-8")

        proc = self.install(self.tmp / "instance", template)

        self.assertNotEqual(0, proc.returncode)
        self.assertIn("name 与目录名不一致", proc.stderr)

    def test_invalid_frontmatter_fails_upgrade_before_overwrite(self):
        target = self.tmp / "instance"
        installed = self.install(target)
        self.assertEqual(0, installed.returncode, installed.stdout + installed.stderr)
        skill = target / "skills" / "knowledge-writing" / "SKILL.md"
        skill.write_text("---\nname: knowledge-writing\ndescription: |\n  多行\n---\n", encoding="utf-8")
        mechanism = target / "scripts" / "opc-up.sh"
        before = mechanism.read_bytes()

        proc = self.run_opc(
            "upgrade", str(target), "--template", str(ROOT), "--skip-smoke",
            "--force-mechanism")

        self.assertNotEqual(0, proc.returncode)
        self.assertIn("description 必须是单行", proc.stderr)
        self.assertEqual(before, mechanism.read_bytes())

    def test_frontmatter_name_mismatch_fails_upgrade(self):
        target = self.tmp / "instance"
        installed = self.install(target)
        self.assertEqual(0, installed.returncode, installed.stdout + installed.stderr)
        skill = target / "skills" / "knowledge-writing" / "SKILL.md"
        text = skill.read_text(encoding="utf-8").replace(
            "name: knowledge-writing", "name: other", 1)
        skill.write_text(text, encoding="utf-8")

        proc = self.run_opc(
            "upgrade", str(target), "--template", str(ROOT), "--skip-smoke")

        self.assertNotEqual(0, proc.returncode)
        self.assertIn("name 与目录名不一致", proc.stderr)

    def test_selected_skill_resolving_outside_fails_upgrade(self):
        target = self.tmp / "instance"
        installed = self.install(target)
        self.assertEqual(0, installed.returncode, installed.stdout + installed.stderr)
        outside = self.tmp / "outside.md"
        outside.write_text(
            "---\nname: knowledge-writing\ndescription: 外部技能\n---\n", encoding="utf-8")
        skill = target / "skills" / "knowledge-writing" / "SKILL.md"
        skill.unlink()
        skill.symlink_to(outside)

        proc = self.run_opc(
            "upgrade", str(target), "--template", str(ROOT), "--skip-smoke")

        self.assertNotEqual(0, proc.returncode)
        self.assertIn("技能路径指向实例外", proc.stderr)

    def test_bash_backstop_keeps_existing_template_on_failure(self):
        target = self.tmp / "instance"
        installed = self.install(target)
        self.assertEqual(0, installed.returncode, installed.stdout + installed.stderr)
        rendered = Path(self.env["HERDR_CORE_HOME"]) / "templates" / "t-gm.md"
        before = rendered.read_bytes()
        skill = target / "skills" / "knowledge-writing" / "SKILL.md"
        skill.write_text("---\nname: wrong\ndescription: 错误技能\n---\n", encoding="utf-8")

        proc = subprocess.run(
            ["bash", str(target / "scripts" / "opc-install.sh"),
             "--no-input", "t", "--skip-smoke"],
            cwd=str(target), env=self.env, capture_output=True, text=True)

        self.assertNotEqual(0, proc.returncode)
        self.assertIn("name 与目录名不一致", proc.stderr)
        self.assertEqual(before, rendered.read_bytes())


if __name__ == "__main__":
    unittest.main()
