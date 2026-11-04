#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/opc-lint 的测试。标准库 unittest，不依赖外部包。

跑法：
    python3 tools/tests/test_opc_lint.py
    python3 -m unittest discover -s tools/tests -t . -v
"""

import importlib.util
import io
import contextlib
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LINT = os.path.join(ROOT, "tools", "opc-lint")


def load_module():
    # 不生成 __pycache__：tools/ 目录不留构建产物
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_loader(
        "opc_lint",
        importlib.machinery.SourceFileLoader("opc_lint", LINT),
    )
    module = importlib.util.module_from_spec(spec)
    # dataclass 装饰器会回查 sys.modules 里的模块对象，先登记再执行
    sys.modules["opc_lint"] = module
    spec.loader.exec_module(module)
    return module


lint = load_module()

SEED = """# 品牌口径

## 公司定位

TODO：一句话说清这家公司做什么。

| 维度 | 结论 |
|---|---|
| 身份 | — |
"""

POLICY = {
    "version": 1,
    "name": "opc-template",
    "templateMarker": ".opc-template-repo",
    "modes": {},
    "rules": [
        {"match": "seeds/", "mode": "seeds"},
        {"match": "scripts/", "mode": "managed"},
        {"match": "agents/", "mode": "managed"},
        {"match": "AGENTS.md", "mode": "managed"},
        {"match": "roles.json", "mode": "merge"},
        {"match": "channels.json", "mode": "merge"},
        {"match": "knowledge/", "mode": "local"},
        {"match": ".opc-template-repo", "mode": "template-only"},
        {"match": "sync-policy.json", "mode": "template-only"},
    ],
    "seeds": [
        {"source": "seeds/knowledge/business/品牌口径.md", "target": "knowledge/business/品牌口径.md"},
    ],
    "mergeConfigs": [],
    "seedRules": {
        "seeds/knowledge/business/品牌口径.md": {
            "requirePlaceholder": True,
            "forbid": ["http://", "https://"],
        },
    },
    "proposalDir": "knowledge/work/*/template-proposals",
    "proposalSections": ["现象", "泛化需求", "期望模版改动", "影响文件", "脱敏自检"],
}

ROLES = {
    "roles": [
        {
            "name": "gm",
            "enabled": True,
            "cli": "claude",
            "template": "agents/opc-gm.md",
            "permissionMode": "default",
            "scope": ["knowledge/work/gm"],
        }
    ]
}


def build_template_repo(base):
    """造一个最小的模版仓库：够跑通规则，又不含真实业务。"""
    os.makedirs(os.path.join(base, "seeds", "knowledge", "business"), exist_ok=True)
    os.makedirs(os.path.join(base, "scripts"), exist_ok=True)
    os.makedirs(os.path.join(base, "agents"), exist_ok=True)

    with open(os.path.join(base, ".opc-template-repo"), "w", encoding="utf-8") as fh:
        json.dump({"kind": "opc-template", "version": 1}, fh)
    with open(os.path.join(base, "sync-policy.json"), "w", encoding="utf-8") as fh:
        json.dump(POLICY, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(base, "roles.json"), "w", encoding="utf-8") as fh:
        json.dump(ROLES, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(base, "channels.json"), "w", encoding="utf-8") as fh:
        json.dump({"channels": []}, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(base, "seeds", "knowledge", "business", "品牌口径.md"), "w", encoding="utf-8") as fh:
        fh.write(SEED)
    with open(os.path.join(base, "AGENTS.md"), "w", encoding="utf-8") as fh:
        fh.write("# 共有规约\n")
    with open(os.path.join(base, "agents", "opc-gm.md"), "w", encoding="utf-8") as fh:
        fh.write("---\nname: {{PREFIX}}-gm\n---\n")
    with open(os.path.join(base, "scripts", "lib.sh"), "w", encoding="utf-8") as fh:
        fh.write('# 判断是不是模版仓库\nopc_is_template_repo() {\n  [[ -f "$1/.opc-template-repo" ]]\n}\n')
    with open(os.path.join(base, "scripts", "opc-install.sh"), "w", encoding="utf-8") as fh:
        fh.write('#!/usr/bin/env bash\nopc_is_template_repo "$ROOT" && exit 2\n')
    return base


def run_lint(root, **kwargs):
    checks = lint.run_checks(root, **kwargs)
    by_id = {c.id: c for c in checks}
    return by_id


class LintTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="opc-lint-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = build_template_repo(os.path.join(self.tmp, "repo"))

    def write(self, rel, content):
        path = os.path.join(self.repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)

    # ---- 真实仓库回归 ----

    def test_real_template_repo_passes(self):
        checks = lint.run_checks(ROOT)
        failed = [c for c in checks if c.status == lint.STATUS_FAIL]
        self.assertEqual([], [(c.id, c.detail) for c in failed])

    # ---- L1 业务路径 ----

    def test_business_file_in_template_fails(self):
        self.write("knowledge/business/wechat/2026-11-04-稿子.md", "# 真稿子\n")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L1"].status)

    # ---- L2 种子集合 ----

    def test_seed_not_declared_in_policy_fails(self):
        self.write("seeds/knowledge/business/多出来.md", "# 多余\n")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L2"].status)

    def test_declared_seed_missing_fails(self):
        os.remove(os.path.join(self.repo, "seeds", "knowledge", "business", "品牌口径.md"))
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L2"].status)

    # ---- L3 占位 ----

    def test_seed_without_placeholder_fails(self):
        self.write("seeds/knowledge/business/品牌口径.md", "# 品牌口径\n\n我们是一家做 AI 内容的公司。\n")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L3"].status)

    # ---- L4 具体日期 ----

    def test_seed_with_real_date_fails(self):
        self.write("seeds/knowledge/business/品牌口径.md", SEED + "\n定稿于 2026-11-04。\n")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L4"].status)

    def test_placeholder_date_is_allowed(self):
        self.write("seeds/knowledge/business/品牌口径.md", SEED + "\n文件名带 YYYY-MM-DD。\n")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_OK, checks["L4"].status)

    # ---- L5 链接与数字 ----

    def test_seed_with_url_fails(self):
        self.write("seeds/knowledge/business/品牌口径.md", SEED + "\n参考 https://example.com\n")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L5"].status)

    def test_seed_with_big_number_fails(self):
        self.write("seeds/knowledge/business/品牌口径.md", SEED + "\n月曝光 120000\n")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L5"].status)

    # ---- L6 私词 ----

    def test_private_word_hit_fails(self):
        words_file = os.path.join(self.tmp, "words.txt")
        with open(words_file, "w", encoding="utf-8") as fh:
            fh.write("# 私词表\n秘密品牌名\n")
        self.write("AGENTS.md", "# 共有规约\n我们做秘密品牌名。\n")
        checks = run_lint(self.repo, words_file=words_file)
        self.assertEqual(lint.STATUS_FAIL, checks["L6"].status)
        # 报告里不出现词本身
        self.assertNotIn("秘密品牌名", " ".join(checks["L6"].detail))

    def test_private_words_absent_is_skip_not_pass(self):
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_SKIP, checks["L6"].status)

    # ---- L7 频道 ----

    def test_template_with_channels_fails(self):
        self.write("channels.json", json.dumps({"channels": [{"id": "wechat", "name": "公众号", "enabled": True}]}))
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L7"].status)

    # ---- L8 角色 ----

    def test_roles_with_bypass_permissions_fails(self):
        roles = json.loads(json.dumps(ROLES))
        roles["roles"][0]["permissionMode"] = "bypassPermissions"
        self.write("roles.json", json.dumps(roles, ensure_ascii=False))
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L8"].status)

    def test_roles_with_bad_scope_fails(self):
        roles = json.loads(json.dumps(ROLES))
        roles["roles"][0]["scope"] = ["../escape"]
        self.write("roles.json", json.dumps(roles, ensure_ascii=False))
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L8"].status)

    # ---- L9 未归类 ----

    def test_unclassified_file_fails(self):
        self.write("没归类.md", "# 随便一个文件\n")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L9"].status)

    # ---- L11 守卫 ----

    def test_missing_marker_fails(self):
        os.remove(os.path.join(self.repo, ".opc-template-repo"))
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L11"].status)

    def test_install_without_guard_fails(self):
        self.write("scripts/opc-install.sh", "#!/usr/bin/env bash\necho hello\n")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L11"].status)

    # ---- L12 本机路径 ----

    def test_local_path_fails(self):
        self.write("AGENTS.md", "# 共有规约\n见 /User" + "s/someone/work/实例\n")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L12"].status)

    # ---- L13 提案格式 ----

    def test_proposal_missing_section_fails(self):
        self.write(
            "knowledge/work/dev/template-proposals/2026-11-04-某事.md",
            "## 现象\n\n少了小节。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L13"].status)

    def test_proposal_with_all_sections_passes(self):
        self.write(
            "knowledge/work/dev/template-proposals/2026-11-04-某事.md",
            "## 现象\n\n## 泛化需求\n\n## 期望模版改动\n\n## 影响文件\n\n## 脱敏自检\n\n- [x] 无真实品牌名\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_OK, checks["L13"].status)

    # ---- 退出码 ----

    def run_main(self, argv):
        """跑 main() 但吞掉它的输出，测试输出保持干净。"""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = lint.main(argv)
        return code

    def test_exit_code_zero_on_clean_repo(self):
        self.assertEqual(0, self.run_main(["--root", self.repo, "--quiet"]))

    def test_exit_code_one_on_violation(self):
        self.write("knowledge/business/x.md", "# 业务\n")
        self.assertEqual(1, self.run_main(["--root", self.repo, "--quiet"]))

    def test_exit_code_two_on_bad_root(self):
        self.assertEqual(2, self.run_main(["--root", os.path.join(self.tmp, "不存在")]))


if __name__ == "__main__":
    unittest.main()
