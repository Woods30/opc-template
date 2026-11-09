#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""template/tools/opc-lint 的测试。标准库 unittest，不依赖外部包。

跑法：
    python3 tests/test_opc_lint.py
    python3 -m unittest discover -s tests -t . -v
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINT = os.path.join(ROOT, "template", "tools", "opc-lint")
# 规约回归可以用 OPC_RULES_ROOT 指向另一份载荷（例如改动前的 HEAD），用来证明用例先红后绿。
RULES_ROOT = os.environ.get("OPC_RULES_ROOT", ROOT)


def rules_file(rel):
    return os.path.join(RULES_ROOT, "template", rel)


def read_rules(rel):
    with open(rules_file(rel), encoding="utf-8") as fh:
        return fh.read()


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

MANIFEST = {
    "version": 1,
    "name": "opc-template",
    "minOpcVersion": 1,
    "mechanism": {
        "dirs": ["scripts", "agents"],
        "files": ["AGENTS.md"],
    },
    "starters": {
        "dirs": [{"source": "skills", "target": "skills", "type": "skill"}],
    },
    "config": [
        {"source": "roles.json", "target": "roles.json", "arrayPath": "roles",
         "key": "name", "onNew": "append-disabled"},
        {"source": "channels.json", "target": "channels.json", "arrayPath": "channels",
         "key": "id", "onNew": "append-disabled"},
    ],
    "seeds": [
        {"source": "seeds/knowledge/business/品牌口径.md",
         "target": "knowledge/business/品牌口径.md"},
        {"source": "seeds/root/GEMINI.md", "target": "GEMINI.md"},
    ],
    "ui": {
        "mods": ["opc-dashboard", "opc-tabs"],
        "layouts": [
            {"source": "layouts/opc.json", "name": "opc"},
            {"source": "layouts/focus.json", "name": "opc-focus"},
            {"source": "layouts/grid.json", "name": "opc-grid"},
            {"source": "layouts/monitor.json", "name": "opc-monitor"},
        ],
    },
    "templateOnly": ["install-manifest.json"],
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
            "template": "agents/gm/AGENTS.md",
            "description": "OPC 公司总经理。",
            "skills": [],
            "permissionMode": "default",
            "scope": ["knowledge/work/gm"],
            # 模版只定机制：模型留空表示用该 CLI 的默认模型，由实例自己选。
            "model": "",
        }
    ]
}


PAYLOAD_TOP = {"agents", "scripts", "tools", "layouts", "mods", "seeds", "skills"}
PAYLOAD_FILES = {"AGENTS.md", "LICENSE", "roles.json", "channels.json", "install-manifest.json"}


def payload_rel(rel):
    top = rel.split("/", 1)[0]
    if top in PAYLOAD_TOP or rel in PAYLOAD_FILES:
        return os.path.join("template", rel)
    return rel


def build_template_repo(base):
    """造一个最小的模版仓库：载荷在 template/，够跑通规则又不含真实业务。"""
    payload = os.path.join(base, "template")
    os.makedirs(os.path.join(payload, "seeds", "knowledge", "business"), exist_ok=True)
    os.makedirs(os.path.join(payload, "seeds", "root"), exist_ok=True)
    os.makedirs(os.path.join(payload, "scripts"), exist_ok=True)
    os.makedirs(os.path.join(payload, "agents"), exist_ok=True)
    os.makedirs(os.path.join(payload, "layouts"), exist_ok=True)
    for mod in ("opc-dashboard", "opc-tabs"):
        os.makedirs(os.path.join(payload, "mods", mod), exist_ok=True)
        with open(os.path.join(payload, "mods", mod, "mod.json"), "w", encoding="utf-8") as fh:
            json.dump({"name": mod}, fh)

    with open(os.path.join(base, ".opc-template-repo"), "w", encoding="utf-8") as fh:
        json.dump({"kind": "opc-template", "version": 1}, fh)
    with open(os.path.join(payload, "install-manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(MANIFEST, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(payload, "roles.json"), "w", encoding="utf-8") as fh:
        json.dump(ROLES, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(payload, "channels.json"), "w", encoding="utf-8") as fh:
        json.dump({"channels": []}, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(payload, "seeds", "knowledge", "business", "品牌口径.md"), "w", encoding="utf-8") as fh:
        fh.write(SEED)
    with open(os.path.join(payload, "seeds", "root", "GEMINI.md"), "w", encoding="utf-8") as fh:
        fh.write("@./AGENTS.md\n")
    with open(os.path.join(payload, "AGENTS.md"), "w", encoding="utf-8") as fh:
        fh.write(
            "# 共有规约\n\n## 启动不自主开工\n\n启动后先汇报现状，等 gm 派工。\n\n"
            "## 通用工作约定\n\n"
            "- **只在本实例目录内取材**：实例目录外的东西不是本实例的业务，不读。\n"
        )
    os.makedirs(os.path.join(payload, "agents", "gm"), exist_ok=True)
    with open(os.path.join(payload, "agents", "gm", "AGENTS.md"), "w", encoding="utf-8") as fh:
        fh.write(
            "## 启动\n\n先读 AGENTS.md，"
            "然后与 owner 对齐方向，等 owner 确认后再派工。\n\n"
            "## 工作方式\n\n"
            "- **只在本实例目录内取材**：实例目录外的东西不是本实例的业务，不读。\n"
        )
    with open(os.path.join(payload, "agents", "gm", "CLAUDE.md"), "w", encoding="utf-8") as fh:
        fh.write("@AGENTS.md\n")
    with open(os.path.join(payload, "agents", "gm", "GEMINI.md"), "w", encoding="utf-8") as fh:
        fh.write("@./AGENTS.md\n")
    with open(os.path.join(payload, "scripts", "lib.sh"), "w", encoding="utf-8") as fh:
        fh.write('# 判断是不是模版仓库\nopc_is_template_repo() {\n  [[ -f "$1/.opc-template-repo" ]]\n}\n')
    with open(os.path.join(payload, "scripts", "opc-install.sh"), "w", encoding="utf-8") as fh:
        fh.write(
            '#!/usr/bin/env bash\n'
            'opc_is_template_repo "$ROOT" && exit 2\n'
            'deny=(\n  "Bash(git:*)"\n  "Bash(rm:*)"\n  "Bash(sudo:*)"\n  "Bash(hc keys:*)"\n)\n'
        )
    with open(os.path.join(payload, "scripts", "opc-up.sh"), "w", encoding="utf-8") as fh:
        fh.write('herdr-app do layout.switch "$(jq -nc --arg n opc \'{name: $n}\')"\n')
    with open(os.path.join(payload, "scripts", "opc-panes.sh"), "w", encoding="utf-8") as fh:
        fh.write('herdr-app do layout.switch \'{"name":"opc-grid"}\'\n')
    for name in ("opc", "focus", "grid", "monitor"):
        body = {"name": name}
        if name == "opc":
            body["tabs"] = {"content": {"mod": "opc-tabs"}}
        with open(os.path.join(payload, "layouts", name + ".json"), "w", encoding="utf-8") as fh:
            json.dump(body, fh, ensure_ascii=False)
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
        path = os.path.join(self.repo, payload_rel(rel))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)

    def add_role(self, name, template_text):
        """再加一个角色，并把它的模板写进 fixture。"""
        roles = json.loads(json.dumps(ROLES))
        roles["roles"].append(
            {
                "name": name,
                "enabled": True,
                "cli": "claude",
                "template": "agents/{}/AGENTS.md".format(name),
                "description": "角色 {}。".format(name),
                "skills": [],
                "permissionMode": "default",
                "scope": ["knowledge/work/{}".format(name)],
                "model": "",
            }
        )
        self.write("roles.json", json.dumps(roles, ensure_ascii=False))
        self.write("agents/{}/AGENTS.md".format(name), template_text)
        self.write("agents/{}/CLAUDE.md".format(name), "@AGENTS.md\n")
        self.write("agents/{}/GEMINI.md".format(name), "@./AGENTS.md\n")

    def instance_copy(self, name):
        """造一个实例：载荷从 template/ 铺到根目录，有实例元数据。"""
        instance = os.path.join(self.tmp, name)
        os.makedirs(instance)
        payload = os.path.join(self.repo, "template")
        for entry in os.listdir(payload):
            shutil.move(os.path.join(payload, entry), os.path.join(instance, entry))
        os.makedirs(os.path.join(instance, ".opc"), exist_ok=True)
        with open(os.path.join(instance, ".opc", "mechanism.json"), "w", encoding="utf-8") as fh:
            json.dump({
                "files": {},
                "policy": {
                    "manifestVersion": 1,
                    "proposalDir": MANIFEST["proposalDir"],
                    "proposalSections": MANIFEST["proposalSections"],
                },
            }, fh, ensure_ascii=False, indent=2)
        with open(os.path.join(instance, ".opc", "instance.json"), "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "kind": "opc-instance", "prefix": "t"}, fh)
        return instance

    # ---- 真实仓库回归 ----

    def test_real_template_repo_passes(self):
        checks = lint.run_checks(ROOT)
        failed = [c for c in checks if c.status == lint.STATUS_FAIL]
        self.assertEqual([], [(c.id, c.detail) for c in failed])

    # ---- 委派契约与选题源契约的规约一致性 ----

    def test_shared_rules_declare_delegation_contract(self):
        text = read_rules("AGENTS.md")
        for phrase in (
            "委派契约", "任务卡", "链边单向直送下游", "不经编排者中转",
            "链条到终点即停", "不设唤醒次数预算",
            "owner 直接下指令", "角色请求裁决", "任务链到达审批点",
            "完成态由工具写入任务卡", "回报只是通知", "选题池",
        ):
            self.assertIn(phrase, text, phrase)

    def test_shared_rules_retire_inbox_dispatch_protocol(self):
        text = read_rules("AGENTS.md")
        for phrase in ("空闲时主动检查", "巡检收件箱", "任务队列", "待办队列"):
            self.assertNotIn(phrase, text, phrase)

    def test_role_rules_retire_inbox_dispatch_protocol(self):
        for role in ("gm", "content", "growth", "dev"):
            text = read_rules("agents/{}/AGENTS.md".format(role))
            for phrase in ("空闲时主动检查", "巡检收件箱", "任务队列", "待办队列"):
                self.assertNotIn(phrase, text, (role, phrase))

    def test_role_rules_start_with_memory_injection_triplet(self):
        for role in ("gm", "content", "growth", "dev"):
            text = read_rules("agents/{}/AGENTS.md".format(role))
            for phrase in (
                "只读三件套", "品牌口径",
                "knowledge/work/{}/LESSONS.md".format(role),
                "本次任务的详情", "整个业务目录", "不读已完成的条目",
                # 收件箱已退休：现在禁的是读别人的任务卡，不是收件箱。
                "不读别人的任务卡",
            ):
                self.assertIn(phrase, text, (role, phrase))
            self.assertRegex(text, r"\*\*不读\*\*整个业务目录")

    def test_topic_source_skill_has_valid_frontmatter_and_no_concrete_source(self):
        path = rules_file("skills/topic-source/SKILL.md")
        self.assertEqual([], lint.skill_frontmatter_problems(path, "topic-source"))
        text = read_rules("skills/topic-source/SKILL.md")
        self.assertIn("不内置任何具体站点", text)
        self.assertNotIn("http://", text)
        self.assertNotIn("https://", text)
        self.assertIn("谁来过滤", text)
        self.assertIn("抓取脚本", text)
        self.assertIn("零接触", text)

    def test_knowledge_writing_skill_declares_writing_four_steps(self):
        # 写作四步与产物槽位是模版约定：技能里必须写清四步、两个固定落点，
        # 以及标题在提纲确认时写进内容卡 title。
        text = read_rules("skills/knowledge-writing/SKILL.md")
        for phrase in (
            "写作四步",
            "knowledge/content/<content_id>/提纲.md",
            "knowledge/content/<content_id>/主稿.md",
            "knowledge/content/<content_id>/配图/",
            "提纲确认",
            "title",
        ):
            self.assertIn(phrase, text, phrase)

    def test_content_rules_reference_writing_four_steps(self):
        # content 规约要指向这套流程，不复制全文。
        text = read_rules("agents/content/AGENTS.md")
        for phrase in ("写作四步", "提纲.md", "配图/"):
            self.assertIn(phrase, text, phrase)

    def test_topic_pool_seed_is_declared_and_url_free(self):
        with open(rules_file("install-manifest.json"), encoding="utf-8") as fh:
            manifest = json.load(fh)
        source = "seeds/knowledge/business/选题池.md"
        self.assertIn(
            {"source": source, "target": "knowledge/business/选题池.md"},
            manifest["seeds"],
        )
        self.assertIn(source, manifest["seedRules"])
        text = read_rules(source)
        self.assertIn("单一副本", text)
        self.assertNotIn("http://", text)
        self.assertNotIn("https://", text)

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
        os.remove(os.path.join(self.repo, "template", "seeds", "knowledge", "business", "品牌口径.md"))
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L2"].status)

    def test_root_gemini_seed_not_declared_fails(self):
        path = os.path.join(self.repo, "template", "install-manifest.json")
        with open(path, encoding="utf-8") as fh:
            manifest = json.load(fh)
        manifest["seeds"] = [
            seed for seed in manifest["seeds"]
            if seed["source"] != "seeds/root/GEMINI.md"
        ]
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L2"].status)

    # ---- L34 CLI 入口文件 ----

    def test_role_missing_cli_entry_file_fails(self):
        os.remove(os.path.join(self.repo, "template", "agents", "gm", "GEMINI.md"))
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L34"].status)

    def test_role_entry_file_with_body_copy_fails(self):
        # 入口文件里一旦拷进正文，两份从此各走各的，再也合不回来。
        self.write("agents/gm/CLAUDE.md", "# gm 角色\n\n你现在是总经理。\n")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L34"].status)

    def test_role_entry_file_without_reference_fails(self):
        self.write("agents/gm/GEMINI.md", "\n")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L34"].status)

    def test_role_entry_file_with_multiple_references_fails(self):
        self.write("agents/gm/GEMINI.md", "@AGENTS.md\n@./AGENTS.md\n")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L34"].status)

    def test_binary_role_entry_file_fails(self):
        path = os.path.join(self.repo, "template", "agents", "gm", "GEMINI.md")
        with open(path, "wb") as fh:
            fh.write(b"@AGENTS.md\0")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L34"].status)

    def test_role_entry_files_present_passes(self):
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_OK, checks["L34"].status)

    # ---- L35–L37 模版不写死模型、不再拿收件箱派工 ----

    def test_l35_template_role_with_model_fails(self):
        # 模版替所有实例决定了模型：模型会下线，实例却改不动。
        roles = json.loads(json.dumps(ROLES))
        roles["roles"][0]["model"] = "spec-model-alpha"
        self.write("roles.json", json.dumps(roles, ensure_ascii=False))
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L35"].status)

    def test_l35_template_role_without_model_field_fails(self):
        # 模版侧要显式留空：字段缺失说不清是「默认」还是「忘了填」。
        roles = json.loads(json.dumps(ROLES))
        roles["roles"][0].pop("model")
        self.write("roles.json", json.dumps(roles, ensure_ascii=False))
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L35"].status)

    def test_l35_template_roles_leave_model_empty_passes(self):
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_OK, checks["L35"].status)

    def test_l36_literal_model_in_payload_fails(self):
        self.write("scripts/lib.sh", '# 用法\nclaude --model spec-model-alpha "$@"\n')
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L36"].status)

    def test_l36_literal_model_in_config_cover_fails(self):
        self.write("scripts/lib.sh", '# 用法\ncodex -c model="spec-model-alpha"\n')
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L36"].status)

    def test_l36_model_variable_in_payload_passes(self):
        self.write("scripts/lib.sh", '# 用法\nclaude --model "$model" "$@"\n')
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_OK, checks["L36"].status)

    def test_l37_inbox_as_dispatch_source_fails(self):
        self.write("AGENTS.md", "# 共有规约\n\n收件箱里的条目是派工来源。\n")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L37"].status)

    def test_l37_idle_self_scan_fails(self):
        self.write("AGENTS.md", "# 共有规约\n\n空闲时主动检查收件箱。\n")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L37"].status)

    def test_l37_role_rule_with_inbox_fails(self):
        self.write("agents/gm/AGENTS.md", "## 启动\n\n先读 AGENTS.md，然后以收件箱为准。\n")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L37"].status)

    def test_l37_negated_inbox_rule_passes(self):
        # 否定句是在禁止，不是在派工：不能被当成违规。
        self.write(
            "AGENTS.md",
            "# 共有规约\n\n不读别人的收件箱，也不要把收件箱当待办来源。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_OK, checks["L37"].status)

    def test_l37_compliant_rules_pass(self):
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_OK, checks["L37"].status)

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

    def test_instance_business_files_not_checked_for_private_words(self):
        # 实例的业务文件里出现真实品牌名是正常的，只该查模版托管的那部分
        os.remove(os.path.join(self.repo, ".opc-template-repo"))
        self.write(".opc/instance.json", json.dumps({"kind": "opc-instance", "version": 1}))
        self.write("knowledge/business/品牌口径.md", "我们做秘密品牌名。\n")
        words_file = os.path.join(self.tmp, "words.txt")
        with open(words_file, "w", encoding="utf-8") as fh:
            fh.write("秘密品牌名\n")
        checks = run_lint(self.repo, words_file=words_file)
        self.assertNotEqual(lint.STATUS_FAIL, checks["L6"].status)

    # ---- L7 频道 ----

    def test_template_with_channels_fails(self):
        self.write("channels.json", json.dumps({"channels": [{"id": "wechat", "name": "公众号", "enabled": True}]}))
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L7"].status)

    # ---- L8 角色 ----

    def test_roles_with_bypass_permissions_is_allowed(self):
        # bypassPermissions 是合法的权限模式：deny 规则在所有模式下都生效，
        # allow 规则失效，所以 L8 不该再把它判成违规。
        roles = json.loads(json.dumps(ROLES))
        roles["roles"][0]["permissionMode"] = "bypassPermissions"
        self.write("roles.json", json.dumps(roles, ensure_ascii=False))
        checks = run_lint(self.repo)
        self.assertNotEqual(lint.STATUS_FAIL, checks["L8"].status)

    def test_deny_list_missing_dangerous_command_fails(self):
        # bypassPermissions 下 allow 规则失效，deny 清单是最后一道闸门：
        # 少了 git / rm / sudo / hc keys 就必须报出来。
        path = os.path.join(self.repo, "template", "scripts", "opc-install.sh")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(src.replace('"Bash(git:*)"\n', ""))
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L15"].status)

    def test_roles_with_bad_scope_fails(self):
        roles = json.loads(json.dumps(ROLES))
        roles["roles"][0]["scope"] = ["../escape"]
        self.write("roles.json", json.dumps(roles, ensure_ascii=False))
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L8"].status)

    # ---- L17 角色启动不自主开工 ----

    def test_role_startup_without_dispatch_instruction_fails(self):
        # 角色启动时如果只说「告诉我你打算做什么」，就会自己开题、自己修 bug。
        self.write(
            "agents/gm/AGENTS.md",
            "## 启动\n\n先读 AGENTS.md，然后告诉我你打算先做什么。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L17"].status)

    def test_role_startup_without_section_fails(self):
        self.write("agents/gm/AGENTS.md", "没有启动小节。\n")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L17"].status)

    def test_shared_rules_without_startup_section_fails(self):
        self.write("AGENTS.md", "# 共有规约\n\n没有启动小节。\n")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L17"].status)

    def test_role_startup_with_dispatch_instruction_passes(self):
        self.add_role(
            "content",
            "## 启动\n\n先读 AGENTS.md，"
            "然后停下来等 gm 派工：汇报现状。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_OK, checks["L17"].status)

    def test_role_startup_negated_dispatch_instruction_fails(self):
        # 出现「等 gm 派工」这几个字不等于说了要等——否定句同样能骗过关键词检查。
        self.add_role(
            "content",
            "## 启动\n\n先读 AGENTS.md，"
            "不用等 gm 派工，自己开题。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L17"].status)

    def test_role_startup_dispatch_with_other_negation_passes(self):
        # 「先不要跑，等 gm 派工」里的「不要」挨的是「跑」，不是「等」——
        # 这种句子说的是要等，不能被误判成否定句。
        self.add_role(
            "content",
            "## 启动\n\n先读 AGENTS.md，"
            "先不要自己开题，等 gm 派工。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_OK, checks["L17"].status)

    def test_role_startup_negated_with_verb_fails(self):
        # 否定词后面隔着一个词（「不需要再等 gm 派工」）仍然是否定。
        self.add_role(
            "content",
            "## 启动\n\n先读 AGENTS.md，"
            "不需要再等 gm 派工，自己开题。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L17"].status)

    def test_role_startup_contradictory_section_fails(self):
        # 前后矛盾最危险：读的人只会记住对自己有利的那句。
        # 只要小节里出现否定的等待指令，就算另外还有一句正面表述也失败。
        self.add_role(
            "content",
            "## 启动\n\n先读 AGENTS.md，"
            "然后停下来等 gm 派工。\n\n不用等 gm 派工，自己开题更快。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L17"].status)

    def test_role_startup_clause_negation_fails(self):
        # 否定词不紧贴关键词，但仍在同一个分句里（「没必要再等 gm 派工」）。
        self.add_role(
            "content",
            "## 启动\n\n先读 AGENTS.md，"
            "没必要再等 gm 派工，自己开题。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L17"].status)

    def test_role_startup_cannot_wait_fails(self):
        # 同义词也要认：「不能等 gm 派工」和「不用等 gm 派工」是一个意思。
        self.add_role(
            "content",
            "## 启动\n\n先读 AGENTS.md，"
            "不能等 gm 派工，先做起来。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L17"].status)

    def test_role_startup_directive_with_autonomy_in_same_sentence_fails(self):
        # 有正面表述、也没有否定词，但同一句里又让角色自己开工——照样是自相矛盾。
        self.add_role(
            "content",
            "## 启动\n\n先读 AGENTS.md，"
            "等 gm 派工后再自己开题。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L17"].status)

    def test_gm_startup_directive_with_autonomy_in_same_sentence_fails(self):
        self.write(
            "agents/gm/AGENTS.md",
            "## 启动\n\n先读 AGENTS.md，"
            "与 owner 对齐后自行决定方向即可。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L17"].status)

    def test_gm_startup_contradictory_section_fails(self):
        self.write(
            "agents/gm/AGENTS.md",
            "## 启动\n\n先读 AGENTS.md，"
            "先与 owner 对齐方向。\n\n但直接派工也行，不必与 owner 对齐。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L17"].status)

    def test_gm_startup_negated_owner_alignment_fails(self):
        self.write(
            "agents/gm/AGENTS.md",
            "## 启动\n\n先读 AGENTS.md，"
            "不用与 owner 对齐，直接派工。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L17"].status)

    def test_role_template_path_escape_fails_in_l8(self):
        # roles.json 是数据文件：模板路径不能读出仓库之外。
        roles = json.loads(json.dumps(ROLES))
        roles["roles"][0]["template"] = "../../etc/passwd"
        self.write("roles.json", json.dumps(roles, ensure_ascii=False))
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L8"].status)
        self.assertTrue(
            any("路径不合法" in d for d in checks["L8"].detail),
            checks["L8"].detail,
        )

    def test_role_template_path_escape_fails_in_l17(self):
        # 同一个坏路径也要在读模板的规则上被挡住，不能只靠 L8 兜底。
        roles = json.loads(json.dumps(ROLES))
        roles["roles"][0]["template"] = "../../etc/passwd"
        self.write("roles.json", json.dumps(roles, ensure_ascii=False))
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L17"].status)
        self.assertTrue(
            any("路径不合法" in d for d in checks["L17"].detail),
            checks["L17"].detail,
        )

    def test_role_content_rules_are_template_side_only(self):
        # 实例里的角色正文归 owner 管：内容规则（L17/L18）只在模版侧跑。
        # owner 把角色简报改写成别的样子，实例 lint 不该拦。
        instance = self.instance_copy("instance")

        checks = run_lint(instance)
        self.assertNotIn("L17", checks)
        self.assertNotIn("L18", checks)
        self.assertEqual([], [c.id for c in checks.values() if c.status == lint.STATUS_FAIL])

        with open(
            os.path.join(instance, "agents", "gm", "AGENTS.md"), "w", encoding="utf-8"
        ) as fh:
            fh.write("# 我自己的角色规约\n\n想怎么写就怎么写。\n")
        checks = run_lint(instance)
        self.assertEqual([], [c.id for c in checks.values() if c.status == lint.STATUS_FAIL])

    def test_instance_missing_role_entry_file_fails(self):
        # 启用角色的入口文件不在：hc 模板渲染不出来，是结构错误，必须失败。
        instance = self.instance_copy("instance2")
        os.remove(os.path.join(instance, "agents", "gm", "AGENTS.md"))

        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_FAIL, checks["L26"].status)

    # ---- L18 只在本实例内取材 ----

    def test_instance_scope_rule_present_passes(self):
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_OK, checks["L18"].status)

    def test_shared_rules_without_instance_scope_rule_fails(self):
        # 少了这条，角色会顺着 `hc ls` 里别的终端的 cwd 去读别的实例目录——
        # 那是别家公司的业务，既越界也可能把结论串味。
        self.write(
            "AGENTS.md",
            "# 共有规约\n\n## 启动不自主开工\n\n启动后先汇报现状，等 gm 派工。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L18"].status)

    def test_role_brief_without_instance_scope_rule_fails(self):
        self.write(
            "agents/gm/AGENTS.md",
            "## 启动\n\n先读 AGENTS.md，"
            "然后与 owner 对齐方向，等 owner 确认后再派工。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L18"].status)

    def test_instance_scope_rule_in_prose_only_fails(self):
        # 关键词出现在散文里不算数：规范句式必须逐字落在行首的加粗项目符号上。
        self.write(
            "agents/gm/AGENTS.md",
            "## 启动\n\n先读 AGENTS.md，"
            "然后与 owner 对齐方向，等 owner 确认后再派工。\n\n"
            "## 工作方式\n\n我们只在本实例目录内取材，请知悉。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L18"].status)

    def test_instance_scope_rule_negated_fails(self):
        # 否定句能骗过关键词检查：必须被当成违规。
        self.write(
            "agents/gm/AGENTS.md",
            "## 启动\n\n先读 AGENTS.md，"
            "然后与 owner 对齐方向，等 owner 确认后再派工。\n\n"
            "## 工作方式\n\n"
            "- **只在本实例目录内取材**：别的实例不读。\n"
            "- 必要时不必只在本实例目录内取材，可以读别的实例。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L18"].status)
        self.assertTrue(
            any("冲突" in d for d in checks["L18"].detail), checks["L18"].detail)

    def test_instance_scope_rule_permissive_wording_fails(self):
        # 明说「可以读实例目录外」也是冲突，跟规范句式并存也不行。
        self.write(
            "agents/gm/AGENTS.md",
            "## 启动\n\n先读 AGENTS.md，"
            "然后与 owner 对齐方向，等 owner 确认后再派工。\n\n"
            "## 工作方式\n\n"
            "- **只在本实例目录内取材**：别的实例不读。\n"
            "- 找不到资料时可以读实例目录外的旧实例。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L18"].status)
        self.assertTrue(
            any("冲突" in d for d in checks["L18"].detail), checks["L18"].detail)

    def test_instance_scope_rule_paraphrases_fail(self):
        # 「其他实例」「读取」「实例之外」都是同一件事的改写，一律算冲突。
        self.write(
            "agents/gm/AGENTS.md",
            "## 启动\n\n先读 AGENTS.md，"
            "然后与 owner 对齐方向，等 owner 确认后再派工。\n\n"
            "## 工作方式\n\n"
            "- **只在本实例目录内取材**：别的实例不读。\n"
            "- 需要时可以读取实例之外的资料。\n"
            "- 也可以参考其他实例的做法。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L18"].status)
        self.assertTrue(
            any("冲突" in d for d in checks["L18"].detail), checks["L18"].detail)

    def test_instance_scope_rule_unknown_permissive_wording_fails(self):
        # 认不出来的放行说法默认拦下（fail-closed），不靠枚举坏句式。
        self.write(
            "agents/gm/AGENTS.md",
            "## 启动\n\n先读 AGENTS.md，"
            "然后与 owner 对齐方向，等 owner 确认后再派工。\n\n"
            "## 工作方式\n\n"
            "- **只在本实例目录内取材**：别的实例不读。\n"
            "- 必要时去旧实例里读一读。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L18"].status)
        self.assertTrue(
            any("冲突" in d for d in checks["L18"].detail), checks["L18"].detail)

    def test_instance_scope_rule_prohibited_out_of_scope_passes(self):
        # 提到实例外但说了「不读」：这是限制，不是冲突。
        self.write(
            "agents/gm/AGENTS.md",
            "## 启动\n\n先读 AGENTS.md，"
            "然后与 owner 对齐方向，等 owner 确认后再派工。\n\n"
            "## 工作方式\n\n"
            "- **只在本实例目录内取材**：别的实例、旧实例残留目录都不在本实例的"
            "业务范围里，不去读。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_OK, checks["L18"].status)

    def test_instance_scope_rule_authorized_out_of_scope_passes(self):
        # 允许读实例外，但要求同分句里先拿到授权：不算冲突。
        self.write(
            "agents/gm/AGENTS.md",
            "## 启动\n\n先读 AGENTS.md，"
            "然后与 owner 对齐方向，等 owner 确认后再派工。\n\n"
            "## 工作方式\n\n"
            "- **只在本实例目录内取材**：别的实例不读。\n"
            "- 要读实例外的东西须先向 gm 说明并拿到授权。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_OK, checks["L18"].status)

    def test_instance_scope_rule_place_and_action_in_different_clauses_fails(self):
        # 「别的实例，可以读」：地点在前一分句、动作用后一分句 —— 主题要递过去，
        # 否则两个分句各缺一半，谁都抓不到。
        self.write(
            "agents/gm/AGENTS.md",
            "## 启动\n\n先读 AGENTS.md，"
            "然后与 owner 对齐方向，等 owner 确认后再派工。\n\n"
            "## 工作方式\n\n"
            "- **只在本实例目录内取材**：别的实例不读。\n"
            "- 别的实例，可以读。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L18"].status)
        self.assertTrue(
            any("冲突" in d for d in checks["L18"].detail), checks["L18"].detail)

    def test_instance_scope_rule_negation_with_filler_fails(self):
        # 否定与动词之间夹着别的字，不算绑在这个动作上。
        self.write(
            "agents/gm/AGENTS.md",
            "## 启动\n\n先读 AGENTS.md，"
            "然后与 owner 对齐方向，等 owner 确认后再派工。\n\n"
            "## 工作方式\n\n"
            "- **只在本实例目录内取材**：别的实例不读。\n"
            "- 不必犹豫读别的实例。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L18"].status)
        self.assertTrue(
            any("冲突" in d for d in checks["L18"].detail), checks["L18"].detail)

    def test_instance_scope_rule_split_authorization_fails(self):
        # 授权写在另一个分句里，够不着前面那个动作——不能算放行。
        self.write(
            "agents/gm/AGENTS.md",
            "## 启动\n\n先读 AGENTS.md，"
            "然后与 owner 对齐方向，等 owner 确认后再派工。\n\n"
            "## 工作方式\n\n"
            "- **只在本实例目录内取材**：别的实例不读。\n"
            "- 可以读别的实例，先向 gm 说明并拿到授权。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L18"].status)
        self.assertTrue(
            any("冲突" in d for d in checks["L18"].detail), checks["L18"].detail)

    def test_instance_scope_rule_negation_split_fails(self):
        # 前半句的「不要」豁免不了后半句的放行。
        self.write(
            "agents/gm/AGENTS.md",
            "## 启动\n\n先读 AGENTS.md，"
            "然后与 owner 对齐方向，等 owner 确认后再派工。\n\n"
            "## 工作方式\n\n"
            "- **只在本实例目录内取材**：别的实例不读。\n"
            "- 不要读本实例的稿子，可以读别的实例。\n",
        )
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L18"].status)
        self.assertTrue(
            any("冲突" in d for d in checks["L18"].detail), checks["L18"].detail)


    # ---- L9 未归类 ----

    def test_unclassified_file_fails(self):
        self.write("template/没归类.md", "# 随便一个文件\n")
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

    def test_guard_only_in_comment_fails(self):
        # 注释里提一句不算守卫，必须是真代码
        self.write("scripts/opc-install.sh", "#!/usr/bin/env bash\n# opc_is_template_repo 守卫\nexit 0\n")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L11"].status)

    def test_lib_without_function_definition_fails(self):
        self.write("scripts/lib.sh", "# opc_is_template_repo 与 .opc-template-repo\n")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L11"].status)

    # ---- 实例自证不能被空文件绕过 ----

    def test_empty_instance_json_does_not_disable_template_checks(self):
        os.remove(os.path.join(self.repo, ".opc-template-repo"))
        self.write(".opc/instance.json", "{}")
        self.write("knowledge/business/x.md", "# 业务\n")
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L1"].status)

    def test_valid_instance_json_switches_to_instance_mode(self):
        os.remove(os.path.join(self.repo, ".opc-template-repo"))
        self.write(".opc/instance.json", json.dumps({"kind": "opc-instance", "version": 1}))
        self.write("knowledge/business/x.md", "# 业务\n")
        checks = run_lint(self.repo)
        self.assertIsNone(checks.get("L1"))

    # ---- 策略里的路径不得越界 ----

    def test_seed_rule_path_traversal_fails(self):
        manifest = json.loads(json.dumps(MANIFEST))
        manifest["seedRules"]["../escape.md"] = {"requirePlaceholder": True}
        self.write("install-manifest.json", json.dumps(manifest, ensure_ascii=False))
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L3"].status)

    def test_seed_target_path_traversal_fails(self):
        manifest = json.loads(json.dumps(MANIFEST))
        manifest["seeds"].append({"source": "seeds/../../escape.md", "target": "../escape.md"})
        self.write("install-manifest.json", json.dumps(manifest, ensure_ascii=False))
        checks = run_lint(self.repo)
        self.assertEqual(lint.STATUS_FAIL, checks["L2"].status)

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

    # ---- L23 技能库 frontmatter ----

    def skill_check(self):
        return run_lint(self.repo)["L23"]

    def test_skill_frontmatter_valid_passes(self):
        self.write(
            "skills/demo/SKILL.md",
            "---\nname: demo\ndescription: 一句话说明这个技能做什么。\n---\n\n正文。\n",
        )
        self.assertEqual(lint.STATUS_OK, self.skill_check().status)

    def test_skill_name_mismatch_fails(self):
        self.write(
            "skills/demo/SKILL.md",
            "---\nname: other\ndescription: 一句话说明这个技能做什么。\n---\n\n正文。\n",
        )
        check = self.skill_check()
        self.assertEqual(lint.STATUS_FAIL, check.status)
        self.assertTrue(any("目录名不一致" in d for d in check.detail))

    def test_skill_missing_description_fails(self):
        self.write("skills/demo/SKILL.md", "---\nname: demo\n---\n\n正文。\n")
        check = self.skill_check()
        self.assertEqual(lint.STATUS_FAIL, check.status)
        self.assertTrue(any("description" in d for d in check.detail))

    def test_skill_multiline_description_fails(self):
        self.write(
            "skills/demo/SKILL.md",
            "---\nname: demo\ndescription: >\n  跨行的说明。\n---\n\n正文。\n",
        )
        check = self.skill_check()
        self.assertEqual(lint.STATUS_FAIL, check.status)
        self.assertTrue(any("单行" in d for d in check.detail))

    def test_skill_without_frontmatter_fails(self):
        self.write("skills/demo/SKILL.md", "# 没有 frontmatter\n")
        check = self.skill_check()
        self.assertEqual(lint.STATUS_FAIL, check.status)
        self.assertTrue(any("frontmatter" in d for d in check.detail))

    def test_skill_without_skill_md_fails(self):
        self.write("skills/demo/参考.md", "参考材料。\n")
        check = self.skill_check()
        self.assertEqual(lint.STATUS_FAIL, check.status)
        self.assertTrue(any("SKILL.md" in d for d in check.detail))

    def test_skill_without_frontmatter_problems_is_reusable(self):
        """校验函数独立可用：#17 可以在别的规则里直接调用。"""
        path = os.path.join(self.repo, "template", "skills", "demo", "SKILL.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("---\nname: demo\ndescription: 说明。\n---\n\n正文。\n")
        self.assertEqual([], lint.skill_frontmatter_problems(path, "demo"))
        self.assertTrue(lint.skill_frontmatter_problems(path, "other"))

    # ---- 实例侧结构规则 L24–L33 ----

    def instance_with_roles(self, name, roles):
        """造一个实例，并把 roles.json 换成给定的角色列表。"""
        instance = self.instance_copy(name)
        with open(os.path.join(instance, "roles.json"), "w", encoding="utf-8") as fh:
            json.dump({"roles": roles}, fh, ensure_ascii=False)
        return instance

    def role_entry(self, **overrides):
        role = {
            "name": "gm",
            "enabled": True,
            "cli": "claude",
            "template": "agents/gm/AGENTS.md",
            "description": "OPC 公司总经理。",
            "skills": [],
            "permissionMode": "default",
            "scope": ["knowledge/work/gm"],
        }
        role.update(overrides)
        return role

    def write_skill(self, instance, name, text):
        path = os.path.join(instance, "skills", name, "SKILL.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def write_team_md(self, instance, row):
        """造一份名册：注册表按安装器写出来的格式给一行角色。"""
        path = os.path.join(instance, "knowledge", "team.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(
                "# 团队名册\n\n## 角色注册表\n\n"
                "| 角色 | 终端名 | 启动器 | HC 模板名 | 所在 tab | CLI | 模型 | 权限模式 | 负责的子树 |\n"
                "|---|---|---|---|---|---|---|---|---|\n"
                "{}\n".format(row))
        return path

    def test_l24_missing_roles_json_fails(self):
        instance = self.instance_copy("l24")
        os.remove(os.path.join(instance, "roles.json"))
        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_FAIL, checks["L24"].status)

    def test_l25_illegal_role_path_fails(self):
        instance = self.instance_with_roles(
            "l25", [self.role_entry(template="../outside/AGENTS.md")])
        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_FAIL, checks["L25"].status)

    def test_l25_absolute_role_path_fails(self):
        instance = self.instance_with_roles(
            "l25b", [self.role_entry(template="/etc/passwd")])
        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_FAIL, checks["L25"].status)

    def test_l26_disabled_role_without_entry_file_passes(self):
        instance = self.instance_with_roles(
            "l26", [self.role_entry(enabled=False)])
        os.remove(os.path.join(instance, "agents", "gm", "AGENTS.md"))
        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_OK, checks["L26"].status)

    def test_l27_empty_description_fails(self):
        instance = self.instance_with_roles(
            "l27", [self.role_entry(description="  ")])
        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_FAIL, checks["L27"].status)

    def test_l28_illegal_skill_name_fails(self):
        instance = self.instance_with_roles(
            "l28", [self.role_entry(skills=["../escape"])])
        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_FAIL, checks["L28"].status)

    def test_l29_broken_skill_frontmatter_fails(self):
        instance = self.instance_with_roles(
            "l29", [self.role_entry(skills=["demo"])])
        self.write_skill(instance, "demo", "没有 frontmatter 的正文。\n")
        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_FAIL, checks["L29"].status)

    def test_l29_skill_without_description_fails(self):
        instance = self.instance_with_roles(
            "l29b", [self.role_entry(skills=["demo"])])
        self.write_skill(instance, "demo", "---\nname: demo\n---\n\n正文。\n")
        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_FAIL, checks["L29"].status)

    def test_l30_skill_name_mismatch_fails(self):
        instance = self.instance_with_roles(
            "l30", [self.role_entry(skills=["demo"])])
        self.write_skill(instance, "demo", "---\nname: other\ndescription: 说明。\n---\n\n正文。\n")
        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_FAIL, checks["L30"].status)

    def test_l31_missing_skill_warns_not_fails(self):
        # 技能缺失只告警：安装器也是告警并跳过，别的角色仍要能启动。
        instance = self.instance_with_roles(
            "l31", [self.role_entry(skills=["demo"])])
        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_WARN, checks["L31"].status)
        self.assertEqual([], [c.id for c in checks.values() if c.status == lint.STATUS_FAIL])

    def test_l31_skill_outside_instance_fails(self):
        # 技能文件是指向实例外的软链接：越界是失败，不只是告警。
        instance = self.instance_with_roles(
            "l31b", [self.role_entry(skills=["demo"])])
        outside = os.path.join(self.tmp, "outside-skill.md")
        with open(outside, "w", encoding="utf-8") as fh:
            fh.write("---\nname: demo\ndescription: 说明。\n---\n\n正文。\n")
        skill_dir = os.path.join(instance, "skills", "demo")
        os.makedirs(skill_dir, exist_ok=True)
        os.symlink(outside, os.path.join(skill_dir, "SKILL.md"))
        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_FAIL, checks["L31"].status)

    def test_l32_missing_root_agents_fails(self):
        instance = self.instance_copy("l32")
        os.remove(os.path.join(instance, "AGENTS.md"))
        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_FAIL, checks["L32"].status)

    def test_l33_illegal_cli_fails(self):
        instance = self.instance_with_roles(
            "l33", [self.role_entry(cli="--danger")])
        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_FAIL, checks["L33"].status)

    def test_l33_illegal_permission_mode_fails(self):
        instance = self.instance_with_roles(
            "l33b", [self.role_entry(permissionMode="乱写")])
        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_FAIL, checks["L33"].status)

    def test_instance_structure_rules_pass_on_clean_instance(self):
        instance = self.instance_with_roles(
            "clean", [self.role_entry(skills=["demo"])])
        self.write_skill(instance, "demo", "---\nname: demo\ndescription: 说明。\n---\n\n正文。\n")
        checks = run_lint(instance)
        for rule in ("L24", "L25", "L26", "L27", "L28", "L29", "L30", "L31", "L32", "L33", "L38"):
            self.assertEqual(lint.STATUS_OK, checks[rule].status, rule)

    # ---- L38–L39 实例的模型字段与名册 ----

    def test_l38_illegal_model_value_fails(self):
        # 模型名会被拼进启动命令行：奇怪字符就是往命令行里塞东西的路。
        instance = self.instance_with_roles(
            "l38", [self.role_entry(model="bad model; rm -rf /")])
        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_FAIL, checks["L38"].status)

    def test_l38_missing_model_field_passes(self):
        # 旧实例没有 model 字段：按该 CLI 的默认模型跑，合法。
        instance = self.instance_with_roles("l38b", [self.role_entry()])
        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_OK, checks["L38"].status)

    def test_l38_valid_model_value_passes(self):
        instance = self.instance_with_roles(
            "l38c", [self.role_entry(model="spec-model-alpha")])
        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_OK, checks["L38"].status)

    def test_l39_missing_team_md_skips(self):
        # 还没装过的实例没有名册：不误杀。
        instance = self.instance_copy("l39")
        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_SKIP, checks["L39"].status)

    def test_l39_empty_cli_cell_fails(self):
        instance = self.instance_copy("l39b")
        self.write_team_md(
            instance,
            "| gm | `t-gm` | `.opc/run/gm.sh` | `t-gm` | `gm` |  | 默认模型 | `default` | `knowledge/work/gm` |")
        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_FAIL, checks["L39"].status)

    def test_l39_empty_tab_cell_fails(self):
        instance = self.instance_copy("l39c")
        self.write_team_md(
            instance,
            "| gm | `t-gm` | `.opc/run/gm.sh` | `t-gm` |  | `claude` | 默认模型 | `default` | `knowledge/work/gm` |")
        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_FAIL, checks["L39"].status)

    def test_l39_valid_registry_passes(self):
        instance = self.instance_copy("l39d")
        self.write_team_md(
            instance,
            "| gm | `t-gm` | `.opc/run/gm.sh` | `t-gm` | `gm` | `claude` | 默认模型 | `default` | `knowledge/work/gm` |")
        checks = run_lint(instance)
        self.assertEqual(lint.STATUS_OK, checks["L39"].status)

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
